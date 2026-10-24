"""Authentication and Authorization Endpoint Tests.

Verifies:
1. User registration with input validation and password hashing.
2. Duplicate email registration rejection.
3. Login flow and JWT token issuance.
4. Protected route access (/auth/me) with valid token.
5. Unauthorized access rejection (missing, tampered, or expired tokens).
"""

from datetime import timedelta
from fastapi.testclient import TestClient

from app.core.security import create_access_token


def test_register_user_success(client: TestClient) -> None:
    """Verify that a new user can register successfully."""
    response = client.post(
        "/auth/register",
        json={"email": "newuser@example.com", "password": "SecurePassword123!"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert "id" in data
    # Security Invariant: Password or password hash must NEVER be returned in response
    assert "password" not in data
    assert "hashed_password" not in data


def test_register_duplicate_email_fails(client: TestClient) -> None:
    """Verify that registering an already registered email returns 400 Bad Request."""
    client.post(
        "/auth/register",
        json={"email": "duplicate@example.com", "password": "SecurePassword123!"},
    )
    response = client.post(
        "/auth/register",
        json={"email": "duplicate@example.com", "password": "AnotherPassword456!"},
    )
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()


def test_register_password_too_short_fails(client: TestClient) -> None:
    """Verify that a password shorter than 8 characters is rejected with 422."""
    response = client.post(
        "/auth/register",
        json={"email": "short@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_login_success_returns_jwt(client: TestClient) -> None:
    """Verify that valid login credentials return a JWT access token."""
    client.post(
        "/auth/register",
        json={"email": "loginuser@example.com", "password": "MySecretPassword123"},
    )
    response = client.post(
        "/auth/login",
        json={"email": "loginuser@example.com", "password": "MySecretPassword123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 20


def test_login_invalid_password_fails(client: TestClient) -> None:
    """Verify that an incorrect password fails with 401 Unauthorized."""
    client.post(
        "/auth/register",
        json={"email": "wrongpass@example.com", "password": "CorrectPassword123"},
    )
    response = client.post(
        "/auth/login",
        json={"email": "wrongpass@example.com", "password": "WrongPassword999"},
    )
    assert response.status_code == 401
    assert "invalid email or password" in response.json()["detail"].lower()


def test_login_nonexistent_user_fails(client: TestClient) -> None:
    """Verify that logging in with an unregistered email fails with 401."""
    response = client.post(
        "/auth/login",
        json={"email": "nonexistent@example.com", "password": "SomePassword123"},
    )
    assert response.status_code == 401


def test_get_me_with_valid_token(client: TestClient) -> None:
    """Verify that /auth/me returns the profile of the authenticated user."""
    reg_response = client.post(
        "/auth/register",
        json={"email": "profileuser@example.com", "password": "Password12345"},
    )
    user_id = reg_response.json()["id"]

    login_response = client.post(
        "/auth/login",
        json={"email": "profileuser@example.com", "password": "Password12345"},
    )
    token = login_response.json()["access_token"]

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user_id
    assert data["email"] == "profileuser@example.com"
    assert "hashed_password" not in data


def test_get_me_missing_token_fails(client: TestClient) -> None:
    """Verify that accessing /auth/me without an Authorization header returns 401."""
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_get_me_invalid_token_fails(client: TestClient) -> None:
    """Verify that accessing /auth/me with a corrupted token returns 401."""
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer this.is.not.a.valid.jwt"},
    )
    assert response.status_code == 401


def test_get_me_expired_token_fails(client: TestClient) -> None:
    """Verify that an expired JWT token is rejected with 401."""
    reg_response = client.post(
        "/auth/register",
        json={"email": "expired@example.com", "password": "Password12345"},
    )
    user_id = reg_response.json()["id"]

    # Issue an already expired token (1 second in the past)
    expired_token = create_access_token(
        subject=user_id,
        expires_delta=timedelta(seconds=-1),
    )

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()

