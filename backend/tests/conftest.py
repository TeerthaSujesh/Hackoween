"""Pytest Configuration and Reusable Test Fixtures.

This module sets up testing infrastructure for the Trend Doctor backend using pytest.
A reliable test setup is crucial in healthcare applications to guarantee that patient
data isolation, referential integrity, and business logic are continuously verified.

Testing Principles Applied:
---------------------------
1. Isolation per Test:
   Every test runs against a clean database state. Tables are created fresh at the start
   of each test and dropped at the end. Tests never leak data into one another.

2. In-Memory SQLite (`sqlite:///:memory:`) with `StaticPool`:
   By using an in-memory SQLite database for unit tests, tests execute in milliseconds
   without touching physical disk files. `StaticPool` ensures all threads in the test
   client share the exact same in-memory database instance during the test run.

3. Foreign Key Enforcement in Tests:
   Just like in the production engine, we attach an event listener to `test_engine`
   to enforce `PRAGMA foreign_keys=ON`. This allows us to write negative tests proving
   that inserting orphaned child records fails with an `IntegrityError`.

4. FastAPI `dependency_overrides`:
   FastAPI allows overriding dependencies (`app.dependency_overrides[get_db] = override_get_db`).
   This redirects any database session requested by API endpoints during test runs to our
   isolated test database rather than the physical development database file.
"""

import os
import sys
from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# Ensure backend root is on sys.path so tests can cleanly import `app`
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.models import Base
from app.core.database import get_db
from app.main import app

# In-memory test database URL
TEST_DATABASE_URL = "sqlite:///:memory:"

# Create test engine using StaticPool so in-memory tables persist across connections in one test
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enforce foreign key constraints inside the test SQLite engine."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Provide an isolated database session per test function.
    
    Workflow:
    1. Create all database tables defined in Base.metadata.
    2. Yield an active session to the test function.
    3. Close the session and drop all tables after the test finishes.
    """
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient with `get_db` overridden to use the test session.
    
    Any API request made via `client.get(...)` or `client.post(...)` will query
    the clean in-memory database rather than writing to disk.
    """
    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
