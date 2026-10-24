"""Authentication Dependency and Current User Extraction.

This module provides the `get_current_user` dependency for FastAPI routes.
Any endpoint that requires authentication simply adds:
    `current_user: User = Depends(get_current_user)`

Security & Privacy Design:
--------------------------
1. Bearer Token Verification:
   Inspects the `Authorization: Bearer <token>` header, decodes the token, and verifies
   both cryptographic signature and expiration time.
2. Tenant Boundary Isolation:
   Once `current_user` is resolved, downstream routes and services MUST filter all queries
   using `current_user.id` (e.g. `Patient.owner_user_id == current_user.id`).
   Never trust a client-supplied user ID in request bodies.
3. Consistent 401 Unauthorized:
   Expired, tampered, or missing tokens consistently return HTTP 401 with standard
   WWW-Authenticate headers, avoiding leakage of internal system state.
"""

from typing import Optional
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User

# HTTPBearer security scheme parses 'Authorization: Bearer <token>' headers
security = HTTPBearer(auto_error=False)


def get_current_user(
    auth_credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Dependency that extracts, verifies, and returns the authenticated User.
    
    Raises:
        HTTPException 401: If token is missing, expired, tampered with, or user no longer exists.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if auth_credentials is None or not auth_credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Clean up token by stripping accidental whitespace or quotes copied from JSON
    token = auth_credentials.credentials.strip().strip('"').strip("'")

    try:
        payload = decode_access_token(token)
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise credentials_exception

    # Query the user from the database to confirm account is still active and valid
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user

