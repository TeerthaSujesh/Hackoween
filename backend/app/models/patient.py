r"""Patient Model for Longitudinal Health Records.

In Trend Doctor, the `Patient` entity represents the clinical subject whose lab reports,
extracted observations, and trend engine findings are tracked across time.

Clinical and Multi-Tenant Design:
---------------------------------
1. Strict Ownership (`owner_user_id`):
   Every patient record MUST have a non-nullable foreign key pointing to `users.id`.
   In subsequent milestones, every query for patient reports, timeline results, and findings
   filters by `owner_user_id == current_user.id`. This guarantees that User A can NEVER view
   or modify User B's patient data, even if User A knows the patient UUID.

2. Clinical Parameters:
   - `date_of_birth`: Essential for age-adjusted calculations. For example, the CKD-EPI 2021
     eGFR equation requires the patient's age in years.
   - `biological_sex`: Required by clinical equations (e.g. creatinine-to-eGFR formulas use
     different exponents $\kappa$ and $\alpha$ for male vs. female patients).
"""

import uuid
from datetime import date
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import String, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

# Avoid circular imports at runtime
if TYPE_CHECKING:
    from app.models.user import User
    from app.models.report import Report
    from app.models.observation import Observation


class Patient(Base, TimestampMixin):
    """Patient entity whose health records and longitudinal trendline are tracked."""

    __tablename__ = "patients"

    # UUID primary key to avoid sequential ID exposure
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Foreign Key linking the patient to the owning user account.
    # ondelete="CASCADE" ensures database-level referential integrity cleanup.
    # Indexed to guarantee fast authorization checks on queries filtering by owner.
    owner_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Full name of the patient profile
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Date of birth (used to compute age for equations like CKD-EPI 2021)
    date_of_birth: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
    )

    # Biological sex ('male', 'female', or other, needed for sex-specific lab ranges & eGFR formulas)
    biological_sex: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )

    # Bidirectional relationship back to the owner User
    owner: Mapped["User"] = relationship(
        back_populates="patients",
    )

    # Associated lab reports
    reports: Mapped[List["Report"]] = relationship(
        back_populates="patient",
        cascade="all, delete-orphan",
    )

    # Confirmed longitudinal observations
    observations: Mapped[List["Observation"]] = relationship(
        back_populates="patient",
        cascade="all, delete-orphan",
    )
