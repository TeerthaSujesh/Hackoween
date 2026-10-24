"""Patient Profile and Multi-Tenant Isolation Tests.

Verifies:
1. Patient CRUD operations by the owning user.
2. Cross-user isolation: User B cannot view, update, or delete User A's patient records.
3. Unauthenticated access rejection.
"""

from fastapi.testclient import TestClient


def _get_auth_token(client: TestClient, email: str, password: str = "SecurePass123!") -> str:
    """Helper to register and login a user, returning a valid JWT token."""
    client.post("/auth/register", json={"email": email, "password": password})
    login_res = client.post("/auth/login", json={"email": email, "password": password})
    return login_res.json()["access_token"]


def test_create_patient_success(client: TestClient) -> None:
    """Verify that an authenticated user can create a patient profile."""
    token = _get_auth_token(client, "user_create_pat@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "full_name": "Rajesh Kumar",
        "date_of_birth": "1976-05-20",
        "biological_sex": "male",
    }
    response = client.post("/patients", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["full_name"] == "Rajesh Kumar"
    assert data["date_of_birth"] == "1976-05-20"
    assert data["biological_sex"] == "male"
    assert "id" in data
    assert "owner_user_id" in data


def test_list_patients_scoped_to_current_user(client: TestClient) -> None:
    """Verify that GET /patients returns only the patient profiles owned by the caller."""
    token_a = _get_auth_token(client, "user_a@example.com")
    token_b = _get_auth_token(client, "user_b@example.com")

    # User A creates 2 patients
    client.post("/patients", json={"full_name": "Patient A1"}, headers={"Authorization": f"Bearer {token_a}"})
    client.post("/patients", json={"full_name": "Patient A2"}, headers={"Authorization": f"Bearer {token_a}"})

    # User B creates 1 patient
    client.post("/patients", json={"full_name": "Patient B1"}, headers={"Authorization": f"Bearer {token_b}"})

    # User A listing patients should only see their 2 patients
    res_a = client.get("/patients", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.status_code == 200
    patients_a = res_a.json()
    assert len(patients_a) == 2
    names_a = {p["full_name"] for p in patients_a}
    assert names_a == {"Patient A1", "Patient A2"}

    # User B listing patients should only see their 1 patient
    res_b = client.get("/patients", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.status_code == 200
    patients_b = res_b.json()
    assert len(patients_b) == 1
    assert patients_b[0]["full_name"] == "Patient B1"


def test_get_patient_by_id_success(client: TestClient) -> None:
    """Verify that an owner can fetch their patient profile by ID."""
    token = _get_auth_token(client, "get_pat@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    create_res = client.post("/patients", json={"full_name": "Meena Iyer"}, headers=headers)
    patient_id = create_res.json()["id"]

    response = client.get(f"/patients/{patient_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == patient_id
    assert response.json()["full_name"] == "Meena Iyer"


def test_update_patient_partial(client: TestClient) -> None:
    """Verify that an owner can update fields on their patient profile."""
    token = _get_auth_token(client, "update_pat@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    create_res = client.post(
        "/patients",
        json={"full_name": "Arun Menon", "biological_sex": "male"},
        headers=headers,
    )
    patient_id = create_res.json()["id"]

    update_res = client.patch(
        f"/patients/{patient_id}",
        json={"full_name": "Arun K. Menon"},
        headers=headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["full_name"] == "Arun K. Menon"
    # Unchanged fields remain intact
    assert update_res.json()["biological_sex"] == "male"


def test_delete_patient(client: TestClient) -> None:
    """Verify that an owner can delete their patient profile."""
    token = _get_auth_token(client, "delete_pat@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    create_res = client.post("/patients", json={"full_name": "To Delete"}, headers=headers)
    patient_id = create_res.json()["id"]

    delete_res = client.delete(f"/patients/{patient_id}", headers=headers)
    assert delete_res.status_code == 204

    # Subsequent GET returns 404
    get_res = client.get(f"/patients/{patient_id}", headers=headers)
    assert get_res.status_code == 404


# ==============================================================================
# Cross-User Security & Isolation Tests (Healthcare Invariant)
# ==============================================================================


def test_two_user_isolation_get_denied(client: TestClient) -> None:
    """User B cannot fetch User A's patient profile; returns 404 (no enumeration)."""
    token_a = _get_auth_token(client, "alice@example.com")
    token_b = _get_auth_token(client, "bob@example.com")

    # User A creates a patient
    res_a = client.post(
        "/patients",
        json={"full_name": "Alice Private Dependent"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    patient_a_id = res_a.json()["id"]

    # User B attempts to fetch User A's patient profile
    res_b = client.get(
        f"/patients/{patient_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    # Security Rule: Return 404 so User B cannot confirm the patient ID exists
    assert res_b.status_code == 404
    assert "not found" in res_b.json()["detail"].lower()


def test_two_user_isolation_update_denied(client: TestClient) -> None:
    """User B cannot modify User A's patient profile; returns 404."""
    token_a = _get_auth_token(client, "alice_edit@example.com")
    token_b = _get_auth_token(client, "bob_edit@example.com")

    res_a = client.post(
        "/patients",
        json={"full_name": "Alice Patient Original"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    patient_a_id = res_a.json()["id"]

    # User B attempts to tamper with User A's patient
    res_b = client.patch(
        f"/patients/{patient_a_id}",
        json={"full_name": "Hacked by Bob"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_b.status_code == 404

    # Verify User A's patient was NOT modified
    verify_res = client.get(
        f"/patients/{patient_a_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert verify_res.json()["full_name"] == "Alice Patient Original"


def test_two_user_isolation_delete_denied(client: TestClient) -> None:
    """User B cannot delete User A's patient profile; returns 404."""
    token_a = _get_auth_token(client, "alice_del@example.com")
    token_b = _get_auth_token(client, "bob_del@example.com")

    res_a = client.post(
        "/patients",
        json={"full_name": "Alice Patient Keep"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    patient_a_id = res_a.json()["id"]

    # User B attempts to delete User A's patient
    res_b = client.delete(
        f"/patients/{patient_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_b.status_code == 404

    # Verify patient still exists for User A
    verify_res = client.get(
        f"/patients/{patient_a_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert verify_res.status_code == 200


def test_unauthenticated_requests_denied(client: TestClient) -> None:
    """Verify that requests without an Authorization header return 401 Unauthorized."""
    assert client.get("/patients").status_code == 401
    assert client.post("/patients", json={"full_name": "Anon"}).status_code == 401
    assert client.get("/patients/some-id").status_code == 401
    assert client.patch("/patients/some-id", json={"full_name": "Anon"}).status_code == 401
    assert client.delete("/patients/some-id").status_code == 401

