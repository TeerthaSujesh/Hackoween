"""Lab Report Management, Confirmation, Timeline & Findings Endpoints.

Handles uploading, querying, updating, confirming lab reports,
querying chronological observations, computing deterministic findings,
and exporting patient records.
"""

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.upload_validator import validate_file_upload
from app.models.patient import Patient
from app.models.report import Report
from app.models.extraction import ExtractionRow
from app.models.observation import Observation
from app.models.user import User
from app.schemas.report import ReportRead, ReportUpdate
from app.schemas.extraction import ExtractionResponse, ExtractionRowRead
from app.schemas.confirmation import ConfirmReportRequest, ConfirmReportResponse, ObservationRead
from app.services.storage import storage_service
from app.services.extraction import extraction_service
from app.services.findings import compute_patient_findings
from app.harmonise.resolver import resolve_marker

router = APIRouter(tags=["Reports & Timeline"])


def _get_verified_patient(patient_id: str, current_user: User, db: Session) -> Patient:
    """Retrieve patient record ensuring strict multi-tenant ownership."""
    patient = (
        db.query(Patient)
        .filter(
            Patient.id == patient_id,
            Patient.owner_user_id == current_user.id,
        )
        .first()
    )
    if not patient:
        # Return 404 (not 403) to prevent unauthorized patient ID enumeration
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found.",
        )
    return patient


def _get_verified_report(report_id: str, current_user: User, db: Session) -> Report:
    """Retrieve report record ensuring strict multi-tenant ownership."""
    report = (
        db.query(Report)
        .filter(
            Report.id == report_id,
            Report.owner_user_id == current_user.id,
        )
        .first()
    )
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )
    return report


@router.post(
    "/patients/{patient_id}/reports",
    response_model=ReportRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new lab report for a patient",
)
async def upload_patient_report(
    patient_id: str,
    file: UploadFile = File(..., description="PDF or image lab report file"),
    collection_date: Optional[date] = Form(None, description="Date specimen was taken"),
    lab_name: Optional[str] = Form(None, description="Laboratory facility name"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Report:
    """Upload a lab report document (PDF, JPEG, PNG).

    Validates file magic bytes and size limit, stores the file with a UUID key,
    and creates a Report record owned by the authenticated user.
    """
    patient = _get_verified_patient(patient_id, current_user, db)

    # Read binary content
    file_bytes = await file.read()
    original_filename = file.filename or "uploaded_report.pdf"

    # Validate file type and magic bytes
    clean_filename, verified_mime = validate_file_upload(file_bytes, original_filename)

    # Save to disk
    storage_key, sha256_hash, file_size = storage_service.save_file(
        file_bytes=file_bytes,
        original_filename=clean_filename,
    )

    # Create Report record
    report = Report(
        patient_id=patient.id,
        owner_user_id=current_user.id,
        filename=clean_filename,
        storage_key=storage_key,
        mime_type=verified_mime,
        file_size_bytes=file_size,
        sha256_hash=sha256_hash,
        collection_date=collection_date,
        lab_name=lab_name,
        status="uploaded",
    )

    db.add(report)
    db.commit()
    db.refresh(report)

    return report


@router.get(
    "/patients/{patient_id}/reports",
    response_model=List[ReportRead],
    summary="List all reports for a specific patient",
)
def list_patient_reports(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Report]:
    """Retrieve all reports for a patient owned by the authenticated user."""
    _get_verified_patient(patient_id, current_user, db)

    reports = (
        db.query(Report)
        .filter(
            Report.patient_id == patient_id,
            Report.owner_user_id == current_user.id,
        )
        .order_by(Report.collection_date.desc(), Report.created_at.desc())
        .all()
    )
    return reports


@router.get(
    "/reports/{report_id}",
    response_model=ReportRead,
    summary="Get details of a specific report",
)
def get_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Report:
    """Retrieve metadata for a specific lab report."""
    return _get_verified_report(report_id, current_user, db)


@router.patch(
    "/reports/{report_id}",
    response_model=ReportRead,
    summary="Update metadata of a report",
)
def update_report(
    report_id: str,
    payload: ReportUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Report:
    """Update clinical metadata (e.g. collection date, lab name, notes) of a report."""
    report = _get_verified_report(report_id, current_user, db)

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(report, field, val)

    db.commit()
    db.refresh(report)
    return report


@router.delete(
    "/reports/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a lab report and its underlying file",
)
def delete_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a report record and delete the stored physical file on disk."""
    report = _get_verified_report(report_id, current_user, db)

    # Delete physical file
    storage_service.delete_file(report.storage_key)

    # Delete database record (cascades to extraction_rows and observations)
    db.delete(report)
    db.commit()


@router.post(
    "/reports/{report_id}/extract",
    response_model=ExtractionResponse,
    summary="Trigger text & table extraction on an uploaded report",
)
def extract_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExtractionResponse:
    """Extract raw test candidates from a report document.

    Executes table parsing and regex line extraction. Discovered biomarkers are staged
    into extraction_rows with status='needs_review'. Non-lab modalities (e.g. ECG)
    trigger the Modality Guardrail setting status='unsupported_modality'.
    """
    report = _get_verified_report(report_id, current_user, db)

    updated_report = extraction_service.process_report_extraction(report.id, db)

    candidates = (
        db.query(ExtractionRow)
        .filter(ExtractionRow.report_id == updated_report.id)
        .all()
    )

    return ExtractionResponse(
        report_id=updated_report.id,
        status=updated_report.status,
        candidates_count=len(candidates),
        candidates=[ExtractionRowRead.model_validate(c) for c in candidates],
    )


@router.get(
    "/reports/{report_id}/candidates",
    response_model=List[ExtractionRowRead],
    summary="List staged extraction candidate rows for a report",
)
def get_report_candidates(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ExtractionRowRead]:
    """Retrieve staged candidate rows awaiting user review and confirmation."""
    report = _get_verified_report(report_id, current_user, db)

    candidates = (
        db.query(ExtractionRow)
        .filter(ExtractionRow.report_id == report.id)
        .all()
    )
    return [ExtractionRowRead.model_validate(c) for c in candidates]


@router.post(
    "/reports/{report_id}/confirm",
    response_model=ConfirmReportResponse,
    summary="Confirm candidate extraction rows into the canonical timeline",
)
def confirm_report_candidates(
    report_id: str,
    payload: ConfirmReportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConfirmReportResponse:
    """Review and confirm staged candidate results into the patient timeline.

    Only confirmed rows become permanent longitudinal observations in the canonical
    `observations` table. Rejected rows are flagged as rejected and shielded from the timeline.
    """
    report = _get_verified_report(report_id, current_user, db)

    if payload.collection_date:
        report.collection_date = payload.collection_date

    obs_date = report.collection_date or date.today()

    # Clear prior observations from this report if re-confirming
    db.query(Observation).filter(Observation.report_id == report.id).delete()

    confirmed_count = 0
    rejected_count = 0
    created_observations: List[Observation] = []

    for item in payload.items:
        candidate = (
            db.query(ExtractionRow)
            .filter(
                ExtractionRow.id == item.candidate_id,
                ExtractionRow.report_id == report.id,
            )
            .first()
        )
        if not candidate:
            continue

        if item.action == "reject":
            candidate.status = "rejected"
            rejected_count += 1
            continue

        # Confirmation flow
        candidate.status = "confirmed"
        final_value = item.confirmed_value if item.confirmed_value is not None else candidate.numeric_value
        if final_value is None:
            continue

        # Resolve standard marker code and unit
        if item.marker_code:
            marker_code = item.marker_code
            unit = item.confirmed_unit or candidate.raw_unit or ""
        else:
            resolved_code, auto_unit = resolve_marker(candidate.raw_marker_name)
            marker_code = resolved_code or candidate.raw_marker_name.lower().replace(" ", "_")
            unit = item.confirmed_unit or auto_unit or candidate.raw_unit or ""

        obs = Observation(
            patient_id=report.patient_id,
            report_id=report.id,
            owner_user_id=current_user.id,
            marker_code=marker_code,
            value=final_value,
            unit=unit,
            observed_date=obs_date,
            source_raw_name=candidate.raw_marker_name,
            source_raw_value=candidate.raw_value,
            source_raw_unit=candidate.raw_unit,
            status="confirmed",
        )
        db.add(obs)
        created_observations.append(obs)
        confirmed_count += 1

    report.status = "confirmed"
    db.commit()

    return ConfirmReportResponse(
        report_id=report.id,
        status="confirmed",
        confirmed_count=confirmed_count,
        rejected_count=rejected_count,
        observations=[ObservationRead.model_validate(o) for o in created_observations],
    )


@router.get(
    "/patients/{patient_id}/timeline",
    response_model=List[ObservationRead],
    summary="Get longitudinal confirmed observations timeline for a patient",
)
def get_patient_timeline(
    patient_id: str,
    marker: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ObservationRead]:
    """Retrieve verified longitudinal observations for charting and trend evaluation.

    Filters strictly by patient ownership and confirmed status.
    """
    _get_verified_patient(patient_id, current_user, db)

    query = (
        db.query(Observation)
        .filter(
            Observation.patient_id == patient_id,
            Observation.owner_user_id == current_user.id,
            Observation.status == "confirmed",
        )
    )

    if marker:
        query = query.filter(Observation.marker_code == marker.lower())

    observations = query.order_by(Observation.observed_date.asc()).all()
    return [ObservationRead.model_validate(o) for o in observations]


@router.get(
    "/patients/{patient_id}/findings",
    response_model=List[Dict[str, Any]],
    summary="Compute evidence-backed clinical trend findings for a patient",
)
def get_patient_findings(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Execute deterministic trend statistics on confirmed patient observations.

    Evaluates personal baseline bands, Reference Change Value (RCV), Theil-Sen slope,
    and Westgard-style rules R0-R5. Returns structured finding objects matching the Section 5.3 contract.
    """
    patient = _get_verified_patient(patient_id, current_user, db)
    return compute_patient_findings(patient, db)


@router.get(
    "/patients/{patient_id}/export",
    summary="Export all patient health records and observations (Patient Ownership)",
)
def export_patient_data(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Export the complete patient profile, report metadata, confirmed observations, and findings.

    Patient-owned data export feature (Section 5.6 of Refactor Specification).
    """
    patient = _get_verified_patient(patient_id, current_user, db)

    reports = (
        db.query(Report)
        .filter(Report.patient_id == patient.id)
        .order_by(Report.collection_date.asc())
        .all()
    )

    observations = (
        db.query(Observation)
        .filter(Observation.patient_id == patient.id, Observation.status == "confirmed")
        .order_by(Observation.observed_date.asc())
        .all()
    )

    findings = compute_patient_findings(patient, db)

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "data_license": "Patient Owned — Confidential Health Record",
        "patient": {
            "id": patient.id,
            "full_name": patient.full_name,
            "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
            "biological_sex": patient.biological_sex,
        },
        "reports": [
            {
                "id": r.id,
                "filename": r.filename,
                "collection_date": r.collection_date.isoformat() if r.collection_date else None,
                "lab_name": r.lab_name,
                "status": r.status,
                "sha256_hash": r.sha256_hash,
            }
            for r in reports
        ],
        "observations": [
            {
                "id": o.id,
                "marker_code": o.marker_code,
                "value": o.value,
                "unit": o.unit,
                "observed_date": o.observed_date.isoformat(),
                "source_raw_name": o.source_raw_name,
            }
            for o in observations
        ],
        "findings": findings,
    }
