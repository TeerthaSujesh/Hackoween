"""Confirmed Longitudinal Observation Model.

Represents a patient-confirmed biomarker result stored in the canonical clinical timeline.

Crucial Health-Data Safety Invariant:
-------------------------------------
Only records in this table represent the patient's verified health history.
The deterministic trend engine, timeline charts, and rate-of-change models
strictly query this table, ensuring unconfirmed extraction candidates NEVER
contaminate clinical calculations.
"""

from datetime import date
from typing import Optional, TYPE_CHECKING
import uuid

from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.patient import Patient
    from app.models.report import Report
    from app.models.user import User


class Observation(Base, TimestampMixin):
    """Canonical longitudinal biomarker observation."""

    __tablename__ = "observations"

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

    # Source report foreign key
    report_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Owner user foreign key (for multi-tenant isolation)
    owner_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Standardized marker code (e.g. 'creatinine', 'hba1c', 'fasting_glucose', 'hb', 'mcv', 'rdw')
    marker_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # Verified numeric value and canonical unit
    value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    unit: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # Specimen collection or test date
    observed_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    # Source traceability to the raw document extraction
    source_raw_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    source_raw_value: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    source_raw_unit: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="confirmed",
        index=True,
    )

    # Relationships
    patient: Mapped["Patient"] = relationship(
        back_populates="observations",
    )

    report: Mapped["Report"] = relationship(
        back_populates="observations",
    )

    owner: Mapped["User"] = relationship()

