"""Application Configuration Module.

This module defines the central `Settings` class using `pydantic-settings`.
In FastAPI applications, managing configuration through environment variables
ensures that secrets (like database credentials, API keys, JWT secrets) are
never hardcoded in source code, following the 12-Factor App methodology.

Key Concepts:
-------------
1. Pydantic BaseSettings: Automatically reads values from environment variables
   or a local `.env` file, casting types (e.g., strings to booleans/integers).
2. Field Validator: Provides custom conversion logic. For example, if an OS
   environment has `DEBUG="release"`, Pydantic would normally fail to parse it
   as a boolean. The validator cleanly converts "release"/"prod" to False and
   "dev"/"true" to True.
3. @lru_cache: Ensures we parse environment variables only once and reuse the
   cached instance across all incoming HTTP requests for optimal performance.
"""

from functools import lru_cache
from typing import Optional, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded dynamically from the environment or .env file."""

    # Application metadata
    app_name: str = "Trend Doctor"
    app_env: str = "development"
    debug: bool = True

    # Database connection URL
    # SQLite is used for local development ('sqlite:///./trend_doctor.db').
    # For production with PostgreSQL, this will be set to:
    # 'postgresql+psycopg://username:password@host:port/dbname'
    database_url: str = "sqlite:///./trend_doctor.db"

    # Authentication & JWT settings
    jwt_secret_key: str = "dev-insecure-secret-key-change-in-production-1234567890"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Storage settings
    storage_dir: str = "storage/uploads"
    max_upload_size_mb: int = 10

    # LLM Settings (Google Gemini / OpenAI compatible)
    llm_base_url: Optional[str] = None
    llm_model: str = "gemini-1.5-flash"
    llm_api_key: Optional[str] = None

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, v: Union[bool, str, int]) -> bool:
        """Flexible parser for the DEBUG environment variable.
        
        Developer machines or Windows environments often set DEBUG to strings like
        'release' or 'debug'. This validator maps those strings safely to a boolean.
        """
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            val = v.strip().lower()
            if val in {"true", "1", "yes", "on", "dev", "development", "debug"}:
                return True
            if val in {"false", "0", "no", "off", "release", "prod", "production"}:
                return False
        if isinstance(v, int):
            return bool(v)
        return False

    # Configuration specifying that settings can be loaded from a '.env' file
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore unrelated environment variables
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton instance of the application settings.
    
    Using @lru_cache prevents reading the disk/.env file repeatedly on every
    request or database query.
    """
    return Settings()
