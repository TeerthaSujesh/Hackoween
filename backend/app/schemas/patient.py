"""Patient Request and Response Schemas.

Pydantic v2 schemas for creating, updating, and returning patient profiles.
Security Invariant:
-------------------
`PatientCreate` never accepts `owner_user_id` from the client request body.
Ownership is always injected securely from the authenticated `current_user` principal.
"""

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class PatientCreate(BaseModel):
    """Schema for creating a new patient profile."""

    full_name: str = Field(..., min_length=1, max_length=255, description="Full name of the patient.")
    date_of_birth: Optional[date] = Field(
        None,
        description="Date of birth (YYYY-MM-DD), used for clinical equations like CKD-EPI.",
    )
    biological_sex: Optional[str] = Field(
        None,
        description="Biological sex ('male', 'female', or other), used for sex-specific lab ranges.",
    )


class PatientUpdate(BaseModel):
    """Schema for updating an existing patient profile."""

    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    date_of_birth: Optional[date] = None
    biological_sex: Optional[str] = None


class PatientResponse(BaseModel):
    """Schema returned by patient profile endpoints."""

    id: str = Field(..., description="Unique UUID of the patient profile.")
    owner_user_id: str = Field(..., description="ID of the user who owns this patient profile.")
    full_name: str = Field(..., description="Patient full name.")
    date_of_birth: Optional[date] = Field(None, description="Patient date of birth.")
    biological_sex: Optional[str] = Field(None, description="Patient biological sex.")
    created_at: datetime = Field(..., description="Record creation timestamp.")
    updated_at: datetime = Field(..., description="Record last updated timestamp.")

    model_config = ConfigDict(from_attributes=True)

