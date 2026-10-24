"""SQLAlchemy Base Declarative Model and Common Mixins.

This module defines the foundational `Base` class and reusable column mixins
using modern SQLAlchemy 2.0 type-annotated declarations.

Why SQLAlchemy 2.0 Style:
-------------------------
In older SQLAlchemy 1.4, columns were defined as `Column(String, primary_key=True)`.
In SQLAlchemy 2.0+, we use `Mapped[str] = mapped_column(String(36), primary_key=True)`.
This gives:
1. Full IDE autocompletion and static type checking (Mypy, Pyright).
2. Clean separation between the Python type (`Mapped[str]`) and the SQL schema (`String(36)`).
3. Explicit typing for relationships and nullable fields (`Mapped[Optional[date]]`).
"""

from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative Base class that all ORM entities in Trend Doctor inherit from.
    
    Alembic reads `Base.metadata` to inspect all mapped tables and autogenerate
    migration scripts.
    """
    pass


class TimestampMixin:
    """Reusable Mixin providing automatic UTC audit timestamps for any model.
    
    In health data systems, knowing exactly when a record was created or modified
    is essential for audit trails, data provenance, and clinical traceability.
    
    - `server_default=func.now()`: Instructs the database engine (SQLite/PostgreSQL)
      to set the timestamp at the instant the row is inserted using its internal clock.
    - `onupdate=func.now()`: Instructs the database or ORM to update the timestamp
      whenever any field in this row is updated.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
