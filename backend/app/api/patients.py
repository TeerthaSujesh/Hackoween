"""Patient Management API Router.

Provides CRUD endpoints for patient profiles owned by the authenticated user.

Security & Multi-Tenant Invariants:
-----------------------------------
1. Implicit Ownership:
   `owner_user_id` is always derived from `current_user.id` obtained from the validated JWT.
   A client cannot spoof or assign a patient to another user account.

2. Strict Scoping in Queries:
   Every read, update, and delete query includes `where(Patient.owner_user_id == current_user.id)`.

3. Prevention of ID Enumeration:
   If User B attempts to access User A's patient UUID, the API returns HTTP 404 (Not Found)
   rather than HTTP 403 (Forbidden). This prevents malicious users from determining
   whether a specific patient UUID exists on the platform.
"""

from collections.abc import Sequence
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientUpdate, PatientResponse

router = APIRouter(prefix="/patients", tags=["patients"])


@router.post(
    "",
    response_model=PatientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new patient profile",
)
def create_patient(
    payload: PatientCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Patient:
    """Create a new patient profile owned by the authenticated user."""
    patient = Patient(
        owner_user_id=current_user.id,
        full_name=payload.full_name,
        date_of_birth=payload.date_of_birth,
        biological_sex=payload.biological_sex,
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


@router.get(
    "",
    response_model=list[PatientResponse],
    status_code=status.HTTP_200_OK,
    summary="List all patient profiles owned by the current user",
)
def list_patients(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Sequence[Patient]:
    """Retrieve all patient profiles belonging to the authenticated user."""
    stmt = (
        select(Patient)
        .where(Patient.owner_user_id == current_user.id)
        .order_by(Patient.created_at.desc())
    )
    return db.scalars(stmt).all()


@router.get(
    "/{patient_id}",
    response_model=PatientResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a specific patient profile by ID",
)
def get_patient(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Patient:
    """Retrieve a single patient profile by ID, verifying ownership."""
    stmt = select(Patient).where(
        Patient.id == patient_id,
        Patient.owner_user_id == current_user.id,
    )
    patient = db.scalar(stmt)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found.",
        )
    return patient


@router.patch(
    "/{patient_id}",
    response_model=PatientResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a patient profile",
)
def update_patient(
    patient_id: str,
    payload: PatientUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Patient:
    """Update fields on an owned patient profile."""
    stmt = select(Patient).where(
        Patient.id == patient_id,
        Patient.owner_user_id == current_user.id,
    )
    patient = db.scalar(stmt)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found.",
        )

    # Apply only provided fields (partial update)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(patient, field, value)

    db.commit()
    db.refresh(patient)
    return patient


@router.delete(
    "/{patient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a patient profile",
)
def delete_patient(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a patient profile and its associated health records via cascade."""
    stmt = select(Patient).where(
        Patient.id == patient_id,
        Patient.owner_user_id == current_user.id,
    )
    patient = db.scalar(stmt)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found.",
        )

    db.delete(patient)
    db.commit()
    return None

