"""Extraction Candidate Row Model.

Represents an extracted biomarker result staged from an uploaded lab report.
Crucial Health-Data Invariant:
------------------------------
All rows remain in `status='needs_review'` until explicitly reviewed and confirmed
by the patient. Staged extraction rows are NEVER included in official timeline
queries or trend calculations until confirmed.
"""

from typing import Optional, TYPE_CHECKING
import uuid

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.report import Report


class ExtractionRow(Base, TimestampMixin):
    """Staged candidate result extracted from an uploaded lab report."""

    __tablename__ = "extraction_rows"

    # UUID primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Associated report foreign key (cascade delete when report is removed)
    report_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Raw extracted values from document
    raw_marker_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    raw_value: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    numeric_value: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    raw_unit: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    raw_reference_range: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    flag: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )

    # Confidence score (e.g., 0.95 for digital table, 0.80 for OCR/Vision)
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
    )

    # Status: 'needs_review', 'confirmed', or 'rejected'
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="needs_review",
        index=True,
    )

    # Relationship back to Report
    report: Mapped["Report"] = relationship(
        back_populates="extraction_rows",
    )

