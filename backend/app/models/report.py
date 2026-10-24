"""Lab Report Database Model.

Represents an uploaded document (PDF or scanned image) containing laboratory biomarker results.
Links directly to a Patient profile and an owning User account for strict isolation.
"""

from datetime import date
from typing import List, Optional, TYPE_CHECKING
import uuid

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.patient import Patient
    from app.models.user import User
    from app.models.extraction import ExtractionRow
    from app.models.observation import Observation


class Report(Base, TimestampMixin):
    """Uploaded laboratory report document entity."""

    __tablename__ = "reports"

    # UUID primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Patient foreign key
    patient_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Owner user foreign key (enables single-query ownership verification)
    owner_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # File metadata
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    storage_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )

    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    sha256_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    # Clinical metadata (extracted or confirmed)
    collection_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
    )

    lab_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="uploaded",
        index=True,
    )

    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    patient: Mapped["Patient"] = relationship(
        back_populates="reports",
    )

    owner: Mapped["User"] = relationship()

    extraction_rows: Mapped[List["ExtractionRow"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
    )

    observations: Mapped[List["Observation"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
    )
