"""Pydantic Schemas for Lab Report Resource."""

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ReportRead(BaseModel):
    """Schema returned when reading a Report resource."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique UUID of the lab report.")
    patient_id: str = Field(..., description="UUID of the associated patient.")
    owner_user_id: str = Field(..., description="UUID of the owning user.")
    filename: str = Field(..., description="Original filename of the uploaded report.")
    storage_key: str = Field(..., description="Unique storage key.")
    mime_type: str = Field(..., description="MIME type of the uploaded file.")
    file_size_bytes: int = Field(..., description="File size in bytes.")
    sha256_hash: str = Field(..., description="SHA-256 integrity checksum.")
    collection_date: Optional[date] = Field(None, description="Date specimen was collected.")
    lab_name: Optional[str] = Field(None, description="Name of the laboratory facility.")
    status: str = Field(..., description="Processing status (e.g. uploaded, needs_review, confirmed).")
    notes: Optional[str] = Field(None, description="Clinical or patient notes.")
    created_at: datetime = Field(..., description="Timestamp of upload.")
    updated_at: datetime = Field(..., description="Timestamp of last update.")


class ReportUpdate(BaseModel):
    """Schema for updating report metadata."""

    collection_date: Optional[date] = Field(None, description="Updated specimen collection date.")
    lab_name: Optional[str] = Field(None, description="Updated laboratory name.")
    notes: Optional[str] = Field(None, description="Updated clinical notes.")

