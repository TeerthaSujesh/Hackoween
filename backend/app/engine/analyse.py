"""Deterministic Trend Engine Analysis.

Pure Python analysis module (no DB, no network) that consumes longitudinal
lab reports and returns evidence-backed findings.

Supports:
1. Kidney Decline (Creatinine + CKD-EPI 2021 eGFR)
2. Glycaemic / Prediabetes Drift (HbA1c + Fasting Glucose)
3. Iron Deficiency Anemia (Hemoglobin + MCV + RDW triad)
"""

from datetime import date
from typing import Any, Dict, List, Optional, Union

from app.engine.egfr import calculate_egfr
from app.engine.rcv import (
    REFERENCE_RANGES,
    calculate_percent_change,
    get_rcv_threshold,
    is_rcv_exceeded,
)
from app.engine.slope import calculate_theil_sen_slope


def _normalize_sex(sex_str: str) -> str:
    """Normalize biological sex representation to 'M' or 'F'."""
    s = str(sex_str).strip().upper()
    if s in ("M", "MALE"):
        return "M"
    if s in ("F", "FEMALE"):
        return "F"
    return "M"


def _parse_date(d: Union[date, str]) -> date:
    """Parse date object or ISO string."""
    return date.fromisoformat(d) if isinstance(d, str) else d


def analyse(biological_sex: str, reports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Analyze longitudinal reports up to the latest report and return triggered findings.

    This function is pure: it performs deterministic calculations without side effects,
    network access, or persistence.

    Args:
        biological_sex: 'M', 'F', 'male', or 'female'.
        reports: Causal list of report dicts up to the current date.
                 Each report has:
                   - 'date': ISO str ('YYYY-MM-DD') or datetime.date
                   - 'age': int or float
                   - 'values': dict mapping marker name to numeric value
                   - 'report_index': optional int

    Returns:
        List of finding dictionaries triggered at the latest report.
    """
    if not reports:
        return []

    sex = _normalize_sex(biological_sex)
    is_female = (sex == "F")

    # Sort reports causally by date
    sorted_reports = sorted(reports, key=lambda r: _parse_date(r["date"]))
    current_report = sorted_reports[-1]
    current_date_str = str(current_report["date"])
    current_age = current_report.get("age", 50)
    current_values = current_report.get("values", {})
    baseline_report = sorted_reports[0]

    findings: List[Dict[str, Any]] = []

    # =========================================================================
    # 1. Kidney Group: Creatinine & eGFR
    # =========================================================================
    if "creatinine" in current_values:
        curr_cr = float(current_values["creatinine"])
        curr_egfr = calculate_egfr(curr_cr, current_age, female=is_female)

        cr_ref_lo, cr_ref_hi = REFERENCE_RANGES["creatinine"][sex]
        rcv_cr = get_rcv_threshold("creatinine")

        cr_history = [(r["date"], float(r["values"]["creatinine"])) for r in sorted_reports if "creatinine" in r.get("values", {})]
        base_cr = float(cr_history[0][1]) if cr_history else curr_cr
        base_age = baseline_report.get("age", current_age)
        base_egfr = calculate_egfr(base_cr, base_age, female=is_female)

        delta_cr_pct = calculate_percent_change(base_cr, curr_cr)
        slope_cr = calculate_theil_sen_slope(cr_history) if len(cr_history) >= 2 else 0.0

        is_oor = curr_cr > cr_ref_hi
        rcv_breached = delta_cr_pct >= rcv_cr

        if is_oor or (len(cr_history) >= 2 and rcv_breached):
            if is_oor or curr_egfr < 60.0:
                severity = "urgent"
            elif curr_egfr < 90.0 or (base_egfr - curr_egfr) >= 15.0:
                severity = "consult_soon"
            else:
                severity = "watch"

            findings.append({
                "report_index": current_report.get("report_index"),
                "date": current_date_str,
                "pattern": "kidney_decline",
                "severity": severity,
                "markers": ["creatinine", "egfr"],
                "evidence": {
                    "baseline_date": str(baseline_report["date"]),
                    "baseline_creatinine": base_cr,
                    "current_creatinine": curr_cr,
                    "delta_percent": delta_cr_pct,
                    "rcv_threshold": rcv_cr,
                    "slope_per_year": slope_cr,
                    "current_egfr": curr_egfr,
                    "baseline_egfr": base_egfr,
                    "reference_range": [cr_ref_lo, cr_ref_hi],
                },
            })

    # =========================================================================
    # 2. Glycaemic / Prediabetes Drift: HbA1c & Fasting Glucose
    # =========================================================================
    if "hba1c" in current_values or "fasting_glucose" in current_values:
        curr_hba1c = float(current_values["hba1c"]) if "hba1c" in current_values else None
        curr_glu = float(current_values["fasting_glucose"]) if "fasting_glucose" in current_values else None

        hba1c_history = [(r["date"], float(r["values"]["hba1c"])) for r in sorted_reports if "hba1c" in r.get("values", {})]
        base_hba1c = float(hba1c_history[0][1]) if hba1c_history else curr_hba1c
        delta_hba1c_pct = calculate_percent_change(base_hba1c, curr_hba1c) if (base_hba1c and curr_hba1c) else 0.0
        rcv_hba1c = get_rcv_threshold("hba1c")

        glu_history = [(r["date"], float(r["values"]["fasting_glucose"])) for r in sorted_reports if "fasting_glucose" in r.get("values", {})]
        base_glu = float(glu_history[0][1]) if glu_history else curr_glu
        delta_glu_pct = calculate_percent_change(base_glu, curr_glu) if (base_glu and curr_glu) else 0.0

        is_diabetic = (curr_hba1c and curr_hba1c >= 6.5) or (curr_glu and curr_glu >= 126.0)
        is_prediabetic = (curr_hba1c and curr_hba1c >= 5.7) or (curr_glu and curr_glu >= 100.0)
        hba1c_rcv_breached = delta_hba1c_pct >= rcv_hba1c

        if is_diabetic:
            severity = "urgent"
        elif is_prediabetic and (hba1c_rcv_breached or delta_glu_pct >= 8.0):
            severity = "consult_soon"
        elif len(hba1c_history) >= 2 and (hba1c_rcv_breached or delta_glu_pct >= 10.0):
            severity = "watch"
        else:
            severity = None

        if severity is not None:
            active_markers = []
            if curr_hba1c is not None:
                active_markers.append("hba1c")
            if curr_glu is not None:
                active_markers.append("fasting_glucose")

            findings.append({
                "report_index": current_report.get("report_index"),
                "date": current_date_str,
                "pattern": "prediabetes_drift",
                "severity": severity,
                "markers": active_markers,
                "evidence": {
                    "baseline_date": str(baseline_report["date"]),
                    "baseline_hba1c": base_hba1c,
                    "current_hba1c": curr_hba1c,
                    "delta_hba1c_pct": delta_hba1c_pct,
                    "rcv_threshold": rcv_hba1c,
                    "baseline_glucose": base_glu,
                    "current_glucose": curr_glu,
                    "delta_glucose_pct": delta_glu_pct,
                },
            })

    # =========================================================================
    # 3. Hematology: Iron Deficiency Anemia (Hb, MCV, RDW Triad)
    # =========================================================================
    if "hb" in current_values:
        curr_hb = float(current_values["hb"])
        hb_ref_lo, hb_ref_hi = REFERENCE_RANGES["hb"][sex]
        rcv_hb = get_rcv_threshold("hb")

        hb_history = [(r["date"], float(r["values"]["hb"])) for r in sorted_reports if "hb" in r.get("values", {})]
        base_hb = float(hb_history[0][1]) if hb_history else curr_hb
        delta_hb_pct = calculate_percent_change(base_hb, curr_hb)

        curr_mcv = float(current_values["mcv"]) if "mcv" in current_values else None
        curr_rdw = float(current_values["rdw"]) if "rdw" in current_values else None

        is_anemic = curr_hb < hb_ref_lo
        hb_rcv_dropped = delta_hb_pct <= -rcv_hb

        # Multi-marker triad support: MCV dropping (< 83) or RDW expanding (>= 13.8)
        triad_support = (curr_mcv and curr_mcv <= 83.0) or (curr_rdw and curr_rdw >= 13.8)

        if is_anemic:
            severity = "urgent"
        elif len(hb_history) >= 2 and hb_rcv_dropped and triad_support:
            severity = "consult_soon"
        elif len(hb_history) >= 2 and hb_rcv_dropped:
            severity = "watch"
        else:
            severity = None

        if severity is not None:
            active_markers = ["hb"]
            if curr_mcv is not None:
                active_markers.append("mcv")
            if curr_rdw is not None:
                active_markers.append("rdw")

            findings.append({
                "report_index": current_report.get("report_index"),
                "date": current_date_str,
                "pattern": "iron_deficiency_anemia",
                "severity": severity,
                "markers": active_markers,
                "evidence": {
                    "baseline_date": str(baseline_report["date"]),
                    "baseline_hb": base_hb,
                    "current_hb": curr_hb,
                    "delta_hb_pct": delta_hb_pct,
                    "rcv_threshold": rcv_hb,
                    "current_mcv": curr_mcv,
                    "current_rdw": curr_rdw,
                    "reference_range": [hb_ref_lo, hb_ref_hi],
                },
            })

    return findings
