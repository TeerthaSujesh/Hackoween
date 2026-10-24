"""Authentication Request and Response Schemas.

Pydantic v2 schemas enforce validation at the API boundary, protecting the database
from malformed inputs and ensuring sensitive fields (like password hashes) are never
accidentally serialized into API responses.
"""

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class UserRegisterRequest(BaseModel):
    """Schema for registering a new user account."""

    email: EmailStr = Field(..., description="Unique email address for user login.")
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password with minimum 8 characters.",
    )


class UserLoginRequest(BaseModel):
    """Schema for logging into an existing account."""

    email: EmailStr = Field(..., description="Registered account email.")
    password: str = Field(..., description="Account password.")


class TokenResponse(BaseModel):
    """Schema for returning a JWT access token upon successful login."""

    access_token: str = Field(..., description="Bearer JWT token string.")
    token_type: str = Field(default="bearer", description="Token type prefix.")


class UserResponse(BaseModel):
    """Safe public schema for user profile data (NEVER exposes password hash)."""

    id: str = Field(..., description="Unique UUID identifier of the user.")
    email: EmailStr = Field(..., description="User email address.")
    created_at: datetime = Field(..., description="Account creation UTC timestamp.")
    updated_at: datetime = Field(..., description="Account last updated UTC timestamp.")

    # Enable ORM mode so Pydantic can read attributes directly from SQLAlchemy User model
    model_config = ConfigDict(from_attributes=True)

