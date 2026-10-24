"""Clinical Dataset Benchmarks Router.

Provides endpoints to query real clinical datasets and evaluation benchmarks,
specifically the 400-patient Apollo Hospitals Chronic Kidney Disease cohort
(supervised by Dr. P. Soundarapandian, Senior Consultant Nephrologist,
Apollo Hospitals Karaikudi; UCI Machine Learning Repository).
"""

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query

from app.engine.egfr import calculate_egfr

router = APIRouter(prefix="/benchmarks", tags=["Clinical Benchmarks"])

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "real"
REPORT_JSON = DATA_DIR / "apollo_validation_report.json"
CLEAN_CSV = DATA_DIR / "apollo_ckd.csv"


@router.get("/apollo-cohort", summary="Get Apollo Hospitals Real Dataset Benchmark")
def get_apollo_cohort_benchmark() -> Dict:
    """Retrieve the summary evaluation metrics comparing standard lab cutoffs

    against Trend Doctor's CKD-EPI 2021 filtration engine on the 400-patient
    Apollo Hospitals cohort.
    """
    if not REPORT_JSON.exists():
        raise HTTPException(status_code=404, detail="Apollo benchmark report not found. Run scripts/eval_real_kaggle.py first.")

    with open(REPORT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "status": "success",
        "benchmark": data,
        "clinical_significance": (
            "Demonstrates that standard reference ranges (Scr > 1.3 mg/dL) miss real "
            "patients in Stage 3 CKD whose creatinine is normal but whose filtration "
            "rate has declined below 60 mL/min/1.73m2."
        )
    }


@router.get("/apollo-cohort/patients", summary="List Real Apollo Patients with Dynamic eGFR")
def list_apollo_patients(
    limit: int = Query(20, ge=1, le=100, description="Number of patients to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    filter_type: Optional[str] = Query("all", enum=["all", "ckd", "notckd", "occult"], description="Filter cohort")
) -> Dict:
    """List individual real patients from Apollo Hospitals Karaikudi,

    dynamically calculating eGFR and KDIGO stage through Trend Doctor's engine.
    """
    if not CLEAN_CSV.exists():
        raise HTTPException(status_code=404, detail="Apollo dataset CSV not found. Run scripts/eval_real_kaggle.py first.")

    with open(CLEAN_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        all_patients = list(reader)

    enriched_patients = []
    for p in all_patients:
        age = int(p["age"])
        sex = p["sex"]
        sc = float(p["sc"])
        is_female = (sex == "F")
        cls = p["classification"]

        # Calculate eGFR on the fly using Trend Doctor's engine
        egfr = calculate_egfr(scr=sc, age=age, female=is_female)

        # Standard lab cutoff
        ref_hi = 1.1 if is_female else 1.3
        is_oor = (sc > ref_hi)
        is_stage_3_plus = (egfr < 60.0)
        is_occult = (cls == "ckd" and not is_oor and is_stage_3_plus)

        # KDIGO Stage
        if egfr >= 90:
            stage = "G1 (Normal)"
        elif egfr >= 60:
            stage = "G2 (Mild Decrease)"
        elif egfr >= 45:
            stage = "G3a (Mild to Moderate)"
        elif egfr >= 30:
            stage = "G3b (Moderate to Severe)"
        elif egfr >= 15:
            stage = "G4 (Severe)"
        else:
            stage = "G5 (Kidney Failure)"

        # Filtering logic
        if filter_type == "ckd" and cls != "ckd":
            continue
        elif filter_type == "notckd" and cls != "notckd":
            continue
        elif filter_type == "occult" and not is_occult:
            continue

        enriched_patients.append({
            "id": p["id"],
            "age": age,
            "sex": sex,
            "creatinine_mg_dl": sc,
            "reference_limit": ref_hi,
            "standard_lab_status": "Out-of-Range" if is_oor else "Normal Reference",
            "calculated_egfr": round(egfr, 1),
            "kdigo_stage": stage,
            "trend_doctor_verdict": "Stage 3+ CKD Detected" if is_stage_3_plus else "Normal/Preserved",
            "ground_truth_diagnosis": "Chronic Kidney Disease" if cls == "ckd" else "Healthy Control",
            "blood_pressure": int(p["bp"]),
            "hemoglobin_g_dl": float(p["hemo"]),
            "blood_glucose_mg_dl": int(p["bgr"]),
            "is_occult_case": is_occult
        })

    total_matched = len(enriched_patients)
    paginated = enriched_patients[offset:offset + limit]

    return {
        "total_count": total_matched,
        "limit": limit,
        "offset": offset,
        "filter": filter_type,
        "source": "Apollo Hospitals, Karaikudi, Tamil Nadu (Dr. P. Soundarapandian)",
        "patients": paginated
    }

