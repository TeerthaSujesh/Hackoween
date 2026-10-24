"""Patient Clinical Findings and Timeline Analytics Service.

Bridges confirmed database observations with the pure deterministic trend engine,
producing evidence-backed clinical findings compliant with the Review Response Spec (Section 5.3).
"""

from datetime import date
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.patient import Patient
from app.models.observation import Observation
from app.engine.analyse import analyse
from app.engine.rcv import REFERENCE_RANGES, get_rcv_threshold


def _calculate_age(dob: Optional[date], at_date: date) -> int:
    """Compute chronological age in years at a specific date."""
    if not dob:
        return 50  # Default adult fallback if DOB not entered
    return at_date.year - dob.year - ((at_date.month, at_date.day) < (dob.month, dob.day))


SPECIALIST_MAP = {
    "kidney_decline": ("Nephrologist", "Urine ACR in 3 months", ["EFLM Biological Variation", "KDIGO 2024 eGFR Guideline"]),
    "prediabetes_drift": ("Endocrinologist", "Repeat Fasting Glucose + HbA1c in 3 months", ["ADA Standards of Care 2024"]),
    "iron_deficiency_anemia": ("Hematologist", "Serum Ferritin & Iron Panel", ["WHO Haemoglobin Guidelines 2024"]),
}


def compute_patient_findings(patient: Patient, db: Session) -> List[Dict[str, Any]]:
    """Compute deterministic longitudinal findings for a patient from confirmed observations."""
    observations = (
        db.query(Observation)
        .filter(
            Observation.patient_id == patient.id,
            Observation.status == "confirmed",
        )
        .order_by(Observation.observed_date.asc())
        .all()
    )

    if not observations:
        return []

    # Group observations chronologically by date
    grouped_reports: Dict[date, Dict[str, float]] = {}
    for obs in observations:
        d = obs.observed_date
        if d not in grouped_reports:
            grouped_reports[d] = {}
        grouped_reports[d][obs.marker_code] = obs.value

    sorted_dates = sorted(grouped_reports.keys())
    reports_payload: List[Dict[str, Any]] = []

    for idx, d in enumerate(sorted_dates, start=1):
        age_at_rep = _calculate_age(patient.date_of_birth, d)
        reports_payload.append({
            "report_index": idx,
            "date": d.isoformat(),
            "age": age_at_rep,
            "values": grouped_reports[d],
        })

    # Execute deterministic analysis
    sex = patient.biological_sex or "M"
    raw_findings = analyse(sex, reports_payload)

    # Format findings according to Section 5.3 Specification Contract
    formatted_findings: List[Dict[str, Any]] = []
    norm_sex = "F" if sex.strip().upper() in ("F", "FEMALE") else "M"

    for f in raw_findings:
        pattern = f["pattern"]
        markers = f["markers"]
        primary_marker = markers[0] if markers else "unknown"
        ev = f.get("evidence", {})
        spec, next_test, refs = SPECIALIST_MAP.get(pattern, ("General Physician", "Routine checkup", []))

        base_val = ev.get("baseline_creatinine") or ev.get("baseline_hba1c") or ev.get("baseline_hb") or 1.0
        curr_val = ev.get("current_creatinine") or ev.get("current_hba1c") or ev.get("current_hb") or 1.0
        rcv_pct = ev.get("rcv_threshold") or get_rcv_threshold(primary_marker)
        delta_pct = ev.get("delta_percent") or ev.get("delta_hba1c_pct") or ev.get("delta_hb_pct") or 0.0

        ref_range = REFERENCE_RANGES.get(primary_marker, {}).get(norm_sex, (0.0, 100.0))
        band_low = round(base_val * (1.0 - rcv_pct / 100.0), 2)
        band_high = round(base_val * (1.0 + rcv_pct / 100.0), 2)

        # Rules fired
        rules_fired = ["R1"]
        if abs(delta_pct) >= rcv_pct:
            rules_fired.append("R2")
        if f["severity"] in ("consult_soon", "urgent"):
            rules_fired.append("R3")
            rules_fired.append("R4")

        finding_obj = {
            "marker": primary_marker,
            "type": "personal_baseline_shift",
            "severity": f["severity"],
            "pattern": pattern,
            "rules_fired": rules_fired,
            "confidence": "high",
            "baseline": {
                "value": base_val,
                "date": ev.get("baseline_date"),
                "method": "personal_median_baseline",
            },
            "personal_band": {
                "low": band_low,
                "high": band_high,
            },
            "population_range": {
                "low": ref_range[0],
                "high": ref_range[1],
            },
            "latest": {
                "value": curr_val,
                "date": f["date"],
            },
            "change_pct": delta_pct,
            "rcv_pct": rcv_pct,
            "rcv_exceeded": abs(delta_pct) >= rcv_pct,
            "specialist": spec,
            "next_test": next_test,
            "evidence_refs": refs,
        }

        # Include eGFR if renal finding
        if "current_egfr" in ev:
            finding_obj["egfr"] = {
                "from": ev.get("baseline_egfr"),
                "to": ev.get("current_egfr"),
                "change_pct": round(
                    ((ev.get("current_egfr", 100) - ev.get("baseline_egfr", 100)) / ev.get("baseline_egfr", 100)) * 100, 1
                ) if ev.get("baseline_egfr") else 0.0,
            }

        formatted_findings.append(finding_obj)

    return formatted_findings
