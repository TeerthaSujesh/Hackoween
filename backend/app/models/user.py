"""User Model for Authentication and Ownership.

In Trend Doctor's architecture, a `User` represents the authenticated account holder
(the human logging in with an email and password).

Architecture & Privacy Design:
------------------------------
1. Separation of `User` and `Patient`:
   A user account is NOT identical to a patient record:
   - A single user account might manage health records for themselves, an elderly parent,
     or a child (family profiles).
   - Therefore, a `User` owns one or more `Patient` records (`user.patients`).
2. Security Invariants:
   - The user table stores `hashed_password` (via Argon2/bcrypt in Milestone 2).
     Cleartext passwords are NEVER stored or logged.
   - `id` uses random UUID v4 strings rather than auto-incrementing integers (1, 2, 3...)
     to prevent ID enumeration attacks (where an attacker guesses `/api/users/2`).
3. Cascading Deletions:
   - If a user deletes their account, GDPR and privacy guidelines mandate that
     associated patient profiles and medical records are removed (`cascade="all, delete-orphan"`).
"""

import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

# TYPE_CHECKING is True only during static type analysis (e.g. VS Code / mypy).
# It prevents circular import cycles at Python runtime.
if TYPE_CHECKING:
    from app.models.patient import Patient


class User(Base, TimestampMixin):
    """User account entity representing an authenticated account holder."""

    __tablename__ = "users"

    # UUID primary key generated automatically as a 36-character string
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Unique, indexed email address for authentication
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    # Cryptographic hash of the user's password (never plain text)
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Bidirectional one-to-many relationship: One User owns zero or more Patient profiles.
    # cascade="all, delete-orphan" guarantees that if a User is deleted, their owned
    # Patient profiles are also deleted from the database.
    patients: Mapped[list["Patient"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
    )
