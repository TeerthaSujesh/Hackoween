"""Pydantic Schemas for Candidate Review & Report Confirmation."""

from datetime import date, datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class CandidateReviewItem(BaseModel):
    """User review decision for a single staged extraction row."""

    candidate_id: str = Field(..., description="UUID of the staged extraction_rows record.")
    action: Literal["confirm", "reject"] = Field(
        default="confirm",
        description="Whether the user confirms this candidate or rejects it as noise.",
    )
    marker_code: Optional[str] = Field(
        None,
        description="Canonical marker code (e.g. 'creatinine', 'hba1c'). Auto-mapped if omitted.",
    )
    confirmed_value: Optional[float] = Field(
        None,
        description="User-edited numeric value if OCR/table reader misread a digit.",
    )
    confirmed_unit: Optional[str] = Field(
        None,
        description="User-confirmed unit string.",
    )


class ConfirmReportRequest(BaseModel):
    """Payload submitted when the user confirms an uploaded lab report."""

    collection_date: Optional[date] = Field(
        None,
        description="Confirmed specimen collection date if missing or corrected.",
    )
    items: List[CandidateReviewItem] = Field(
        ...,
        description="List of review actions for the staged candidate rows.",
    )


class ObservationRead(BaseModel):
    """Schema for a verified longitudinal observation."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="UUID of the observation.")
    patient_id: str = Field(..., description="UUID of the patient.")
    report_id: str = Field(..., description="UUID of the source report.")
    marker_code: str = Field(..., description="Standard canonical marker code.")
    value: float = Field(..., description="Confirmed numeric value.")
    unit: str = Field(..., description="Canonical unit.")
    observed_date: date = Field(..., description="Test observation date.")
    status: str = Field(..., description="Status ('confirmed').")
    created_at: datetime = Field(..., description="Created timestamp.")


class ConfirmReportResponse(BaseModel):
    """Response returned upon successful report confirmation."""

    report_id: str = Field(..., description="UUID of the confirmed report.")
    status: str = Field(..., description="Updated report status ('confirmed').")
    confirmed_count: int = Field(..., description="Number of candidates confirmed.")
    rejected_count: int = Field(..., description="Number of candidates rejected.")
    observations: List[ObservationRead] = Field(
        default_factory=list,
        description="List of newly created longitudinal observations.",
    )

