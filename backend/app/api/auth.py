"""Authentication API Router.

Endpoints for user registration, login (JWT token issuance), and profile retrieval.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.core.auth import get_current_user
from app.models.user import User
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
def register(
    payload: UserRegisterRequest,
    db: Session = Depends(get_db),
) -> User:
    """Register a new user with email and password.
    
    Validates:
    - Email is not already registered.
    - Password is hashed using Argon2id before persistence.
    """
    # Check if a user with this email already exists
    existing_user = db.scalar(select(User).where(User.email == payload.email))
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists.",
        )

    # Hash the password using Argon2id (never store plaintext passwords)
    hashed_pass = hash_password(payload.password)

    # Create and persist the user record
    user = User(
        email=payload.email,
        hashed_password=hashed_pass,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Log in and obtain a JWT access token",
)
def login(
    payload: UserLoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate credentials and return a signed JWT access token."""
    # Look up user by email
    user = db.scalar(select(User).where(User.email == payload.email))

    # Verify user exists and password hash matches
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate signed JWT access token with user.id as the subject ('sub')
    access_token = create_access_token(subject=user.id)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
    )


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get profile of the currently authenticated user",
)
def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    """Return the currently authenticated user's profile.
    
    Requires a valid 'Authorization: Bearer <token>' header.
    """
    return current_user

