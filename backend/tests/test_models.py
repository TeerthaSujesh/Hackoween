"""Database Model and Integrity Tests.

This test suite verifies:
1. ORM model persistence (`User`, `Patient`).
2. Unique constraints (e.g. duplicate email prevention).
3. Foreign key integrity enforcement in SQLite (ensuring orphan patients cannot be created).
4. Cascading deletion behavior (deleting a User automatically deletes their owned Patients).

These constraints form the foundational layer of patient data security in Trend Doctor.
"""

import uuid
from datetime import date
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.patient import Patient


def test_create_user(db_session: Session) -> None:
    """Verify that a User record can be created, persisted, and retrieved.
    
    Verifies that:
    - UUID primary key is generated automatically.
    - Fields are saved accurately.
    - created_at and updated_at timestamps are populated by default.
    """
    user = User(
        email="patient@example.com",
        hashed_password="hashed_secret_string",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert user.id is not None
    assert user.email == "patient@example.com"
    assert user.created_at is not None
    assert user.updated_at is not None


def test_user_email_unique_enforced(db_session: Session) -> None:
    """Verify that the database enforces uniqueness on the User.email column.
    
    Attempting to insert two users with the same email address must raise an
    IntegrityError to prevent duplicate accounts and identity collisions.
    """
    user1 = User(
        email="duplicate@example.com",
        hashed_password="hashed_secret_1",
    )
    db_session.add(user1)
    db_session.commit()

    user2 = User(
        email="duplicate@example.com",
        hashed_password="hashed_secret_2",
    )
    db_session.add(user2)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_create_patient_with_owner_relationship(db_session: Session) -> None:
    """Verify that a Patient can be linked to a User via owner_user_id.
    
    Verifies bidirectional relationship navigation:
    - `patient.owner` resolves to the parent User.
    - `user.patients` list contains the newly added Patient.
    """
    user = User(
        email="owner@example.com",
        hashed_password="hashed_secret_pass",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    patient = Patient(
        owner_user_id=user.id,
        full_name="Aarav Sharma",
        date_of_birth=date(1985, 4, 12),
        biological_sex="male",
    )
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)

    # Assert attributes and bidirectional ORM relationship
    assert patient.id is not None
    assert patient.owner_user_id == user.id
    assert patient.owner.email == "owner@example.com"
    assert len(user.patients) == 1
    assert user.patients[0].id == patient.id


def test_patient_foreign_key_constraint_enforced(db_session: Session) -> None:
    """Verify SQLite foreign key enforcement: an orphan Patient cannot be saved.
    
    Attempting to create a Patient with a non-existent `owner_user_id` must fail
    with an IntegrityError. This proves that SQLite PRAGMA foreign_keys=ON is active.
    """
    non_existent_user_id = str(uuid.uuid4())
    patient = Patient(
        owner_user_id=non_existent_user_id,
        full_name="Orphan Patient",
    )
    db_session.add(patient)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_cascade_delete_patient_when_owner_deleted(db_session: Session) -> None:
    """Verify that deleting a User cascades to delete all their owned Patients.
    
    In a patient-owned data model, deleting an account holder must clean up all
    associated patient profiles, ensuring no orphaned health data is retained.
    """
    user = User(
        email="to_delete@example.com",
        hashed_password="secret_password",
    )
    db_session.add(user)
    db_session.commit()

    patient = Patient(
        owner_user_id=user.id,
        full_name="Dependent Patient",
    )
    db_session.add(patient)
    db_session.commit()

    patient_id = patient.id

    # Delete the user and verify the cascade removes the patient record
    db_session.delete(user)
    db_session.commit()

    remaining_patient = db_session.get(Patient, patient_id)
    assert remaining_patient is None
