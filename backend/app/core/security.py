"""Security, Password Hashing, and JWT Utilities.

This module provides cryptographic primitives for:
1. One-way password hashing using Argon2id via `pwdlib`.
2. JSON Web Token (JWT) signing, issuance, and verification via `pyjwt`.

Why Argon2id:
-------------
Argon2id won the Password Hashing Competition (PHC) and is recommended by OWASP
over older algorithms (MD5, SHA256, and even basic bcrypt). It is memory-hard,
making brute-force attacks via GPUs and specialized ASICs prohibitively expensive.

Why JWT (JSON Web Tokens):
--------------------------
JWTs allow stateless, cryptographically signed authentication. The server signs a payload
containing the user's ID (`sub`) and an expiration timestamp (`exp`). When incoming requests
present this token in the `Authorization: Bearer <token>` header, the server verifies the
signature without needing to query a centralized session cache (like Redis).
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

settings = get_settings()

# Initialize recommended password hasher (Argon2id)
password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Generate a secure Argon2id hash for a plain-text password.
    
    Args:
        password: Plain text password provided by the user.
        
    Returns:
        Salted, irreversible password hash string.
    """
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify that a plain-text password matches a stored password hash.
    
    Args:
        plain_password: Password attempt from login request.
        hashed_password: Stored Argon2id hash from database.
        
    Returns:
        True if password matches, False otherwise.
    """
    return password_hash.verify(plain_password, hashed_password)


def create_access_token(
    subject: str,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """Create a signed JWT access token.
    
    Args:
        subject: The unique user identifier (e.g. user UUID) stored in the 'sub' claim.
        expires_delta: Optional custom expiration duration; defaults to settings duration.
        extra_claims: Optional additional dictionary claims to embed in the token.
        
    Returns:
        Encoded and signed JWT string.
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.access_token_expire_minutes)

    to_encode: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": expire,
    }

    if extra_claims:
        to_encode.update(extra_claims)

    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and cryptographically verify a JWT access token.
    
    Args:
        token: Bearer JWT string from HTTP header.
        
    Returns:
        Decoded payload dictionary containing claims ('sub', 'exp', etc.).
        
    Raises:
        jwt.PyJWTError: If signature is invalid, token is expired, or malformed.
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )

