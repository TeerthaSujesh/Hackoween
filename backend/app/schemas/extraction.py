"""Pydantic Schemas for Extraction Candidate Rows."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ExtractionRowRead(BaseModel):
    """Schema for reading a staged extraction candidate row."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique UUID of the staged candidate row.")
    report_id: str = Field(..., description="UUID of the parent report.")
    raw_marker_name: str = Field(..., description="Extracted marker name as printed on report.")
    raw_value: str = Field(..., description="Original raw value string.")
    numeric_value: Optional[float] = Field(None, description="Parsed numeric value for calculations.")
    raw_unit: Optional[str] = Field(None, description="Extracted unit.")
    raw_reference_range: Optional[str] = Field(None, description="Extracted reference interval.")
    flag: Optional[str] = Field(None, description="Extracted abnormality flag (H/L/Normal).")
    confidence: float = Field(..., description="Parser confidence score.")
    status: str = Field(..., description="Status ('needs_review', 'confirmed', 'rejected').")
    created_at: datetime = Field(..., description="Staged timestamp.")
    updated_at: datetime = Field(..., description="Last update timestamp.")


class ExtractionResponse(BaseModel):
    """Summary response after triggering report extraction."""

    report_id: str = Field(..., description="UUID of the extracted report.")
    status: str = Field(..., description="New report status (needs_review, unsupported_modality, ocr_fallback_required).")
    candidates_count: int = Field(..., description="Total candidate rows staged for review.")
    candidates: List[ExtractionRowRead] = Field(default_factory=list, description="List of staged candidate rows.")

