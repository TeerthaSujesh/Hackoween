"""Database Engine and Session Management Module.

This module configures the database connection using SQLAlchemy 2.0, establishes
connection hooks, and provides the FastAPI dependency for request-scoped database sessions.

Key Architecture & Concepts:
----------------------------
1. SQLAlchemy 2.x Engine:
   The `Engine` is the core factory for database connections. It manages a connection
   pool and executes SQL statements against the underlying database driver.

2. SQLite Foreign Key Enforcement (`PRAGMA foreign_keys=ON`):
   By default, SQLite does NOT enforce FOREIGN KEY constraints for backward compatibility!
   If User A is deleted, orphaned Patient records would remain unless foreign keys are
   turned on. The `@event.listens_for(Engine, "connect")` listener intercepts every new
   SQLite connection and executes `PRAGMA foreign_keys=ON` to enforce referential integrity.

3. `check_same_thread=False`:
   SQLite connections are tied to the thread that opened them by default. Because FastAPI
   handles concurrent requests across different threads in an async event loop, we pass
   `check_same_thread=False` to allow SQLite sessions to be accessed safely per request.

4. Session Lifecycle & Dependency Injection (`get_db`):
   In web applications, each HTTP request should have its own isolated database session:
   - Route begins -> session is opened.
   - Operations occur within that session.
   - Route completes -> session is closed, returning the connection back to the pool.
   FastAPI's dependency injection (`Depends(get_db)`) guarantees cleanup using Python generators
   and the `finally:` block.
"""

from collections.abc import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import get_settings

# Load configuration (database URL, debug status, etc.)
settings = get_settings()

# Prepare connection arguments
connect_args = {}
if settings.database_url.startswith("sqlite"):
    # Allow SQLite to be shared across threads in FastAPI
    connect_args["check_same_thread"] = False

# Create the SQLAlchemy Engine
engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    # In production with PostgreSQL, pool_size and max_overflow can be tuned here
)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable SQLite Foreign Key support upon establishing a connection.
    
    Without this event listener, SQLite ignores foreign key relationships, which
    can lead to orphaned records and silent integrity violations.
    When switching to PostgreSQL in production, this hook automatically steps aside.
    """
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# SessionLocal is a factory that produces new Session objects.
# autocommit=False ensures transactions remain explicit (you must call session.commit()).
# autoflush=False avoids premature queries flushing uncommitted state unexpectedly.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI Dependency for request-scoped database sessions.
    
    Usage in route handlers:
        @router.get("/patients")
        def list_patients(db: Session = Depends(get_db)):
            ...
    
    How it works:
        1. A new Session is created for the incoming HTTP request.
        2. `yield db` passes control to the endpoint handler with the active session.
        3. Once the endpoint returns its HTTP response, the `finally:` block executes,
           guaranteeing that the session is closed and connections do not leak.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
