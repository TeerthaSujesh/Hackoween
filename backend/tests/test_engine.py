"""Unit tests for the Trend Doctor Trend Engine.

Tests deterministic implementations:
- CKD-EPI 2021 eGFR calculations
- Biological variation and RCV thresholds
- Theil-Sen robust slope estimator
- Pure `analyse()` function on Rajesh persona and kidney evaluation cohort
"""

import json
from pathlib import Path
import pytest

from app.engine.egfr import calculate_egfr
from app.engine.rcv import (
    calculate_percent_change,
    get_rcv_threshold,
    is_rcv_exceeded,
)
from app.engine.slope import calculate_theil_sen_slope
from app.engine.analyse import analyse


def test_egfr_ckdepi_2021_matches_rajesh_ground_truth():
    """Verify eGFR calculations match Rajesh's ground truth exact values."""
    # Rajesh: 46yo male, creatinine 0.8 mg/dL -> expected 110.5
    egfr_1 = calculate_egfr(scr=0.8, age=46, female=False)
    assert egfr_1 == 110.5

    # Rajesh: 47yo male, creatinine 1.0 mg/dL -> expected 93.4
    egfr_2 = calculate_egfr(scr=1.0, age=47, female=False)
    assert egfr_2 == 93.4


def test_egfr_female_factor():
    """Verify eGFR applies sex-specific coefficients."""
    egfr_male = calculate_egfr(scr=0.9, age=40, female=False)
    egfr_female = calculate_egfr(scr=0.9, age=40, female=True)
    # Female formula has different kappa/alpha and 1.012 multiplier
    assert egfr_male != egfr_female


def test_egfr_invalid_inputs():
    """Verify input validation on eGFR."""
    with pytest.raises(ValueError):
        calculate_egfr(scr=-1.0, age=40)
    with pytest.raises(ValueError):
        calculate_egfr(scr=1.0, age=-5)


def test_rcv_threshold_calculation():
    """Verify 95% RCV threshold for creatinine."""
    # CV_I = 4.5, CV_A = 2.5 -> 2.77 * sqrt(20.25 + 6.25) = 2.77 * 5.1478 = 14.26%
    rcv_cr = get_rcv_threshold("creatinine")
    assert rcv_cr == 14.26

    # Delta of 25.0% (0.8 to 1.0) breaches 14.26%
    exceeded, delta_pct, thresh = is_rcv_exceeded("creatinine", baseline=0.8, current=1.0)
    assert exceeded is True
    assert delta_pct == 25.0
    assert thresh == 14.26


def test_theil_sen_slope():
    """Verify Theil-Sen slope calculation in units per year."""
    # 1.0 unit increase over 1 year (365.25 days)
    points = [("2023-01-01", 1.0), ("2024-01-01", 2.0)]
    slope = calculate_theil_sen_slope(points)
    assert round(slope, 1) == 1.0

    # Less than 2 points returns 0.0
    assert calculate_theil_sen_slope([("2023-01-01", 1.0)]) == 0.0


def test_analyse_rajesh_kidney_lead_time():
    """Verify analyse() catches Rajesh's drift at Report 2 (430 days lead time)."""
    ground_truth_path = Path(__file__).resolve().parents[2] / "data" / "personas" / "rajesh" / "ground_truth.json"
    if not ground_truth_path.exists():
        pytest.skip("Rajesh ground truth file not found.")

    with open(ground_truth_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Format reports for pure analyse() function
    rajesh_reports = []
    for r in data["reports"]:
        rajesh_reports.append({
            "report_index": r["report_index"],
            "date": r["date"],
            "age": r["age_at_report"],
            "values": {
                "creatinine": r["values"]["creatinine"]["value"],
            },
        })

    # 1. Report 1 alone: baseline established, no findings
    findings_r1 = analyse(biological_sex="male", reports=rajesh_reports[:1])
    assert len(findings_r1) == 0

    # 2. Report 1 + Report 2: creatinine went from 0.8 to 1.0 (+25.0% > 14.26% RCV)
    # Even though 1.0 is strictly in the normal lab range [0.7, 1.3], Trend Doctor triggers!
    findings_r2 = analyse(biological_sex="male", reports=rajesh_reports[:2])
    assert len(findings_r2) == 1

    alert = findings_r2[0]
    assert alert["pattern"] == "kidney_decline"
    assert alert["severity"] in ("watch", "consult_soon")
    assert alert["date"] == "2023-12-10"
    assert "creatinine" in alert["markers"]
    assert alert["evidence"]["delta_percent"] == 25.0
    assert alert["evidence"]["current_egfr"] == 93.4
