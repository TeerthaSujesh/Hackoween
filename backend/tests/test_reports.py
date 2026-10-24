"""Tests for Lab Report Upload, Storage, and Multi-Tenant Isolation.

Verifies:
1. Valid lab report PDF upload using realistic persona fixture (Rajesh Report 1).
2. Magic bytes validation (rejects invalid headers or disguised files).
3. Secure file persistence on disk and sha256 checksum integrity.
4. Retrieval, listing, and metadata updates.
5. Two-account multi-tenant isolation:
   - User B cannot upload to User A's patient (404).
   - User B cannot view User A's report (404).
   - User B cannot delete User A's report (404).
6. File and record cleanup on report deletion.
"""

import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.services.storage import storage_service


def _get_auth_headers(client: TestClient, email: str, password: str = "SecurePass123!") -> dict:
    """Helper to register and login a user, returning auth headers."""
    client.post("/auth/register", json={"email": email, "password": password})
    login_res = client.post("/auth/login", json={"email": email, "password": password})
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Load real PDF fixture or generate standard PDF header bytes."""
    fixture_path = Path(__file__).resolve().parents[2] / "data" / "personas" / "rajesh" / "report_1.pdf"
    if fixture_path.exists():
        return fixture_path.read_bytes()
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def test_upload_report_pdf_success(client: TestClient, sample_pdf_bytes: bytes):
    """Verify authenticated user can upload a valid lab report PDF."""
    headers = _get_auth_headers(client, "uploader@example.com")

    # 1. Create patient
    p_res = client.post(
        "/patients",
        json={"full_name": "Rajesh Kumar", "date_of_birth": "1977-05-12", "biological_sex": "male"},
        headers=headers,
    )
    assert p_res.status_code == 201
    patient_id = p_res.json()["id"]

    # 2. Upload PDF
    files = {"file": ("report_1.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
    data = {"collection_date": "2023-01-15", "lab_name": "Sunrise Diagnostics"}
    r_res = client.post(
        f"/patients/{patient_id}/reports",
        files=files,
        data=data,
        headers=headers,
    )

    assert r_res.status_code == 201
    report = r_res.json()
    assert report["patient_id"] == patient_id
    assert report["filename"] == "report_1.pdf"
    assert report["mime_type"] == "application/pdf"
    assert report["collection_date"] == "2023-01-15"
    assert report["lab_name"] == "Sunrise Diagnostics"
    assert report["status"] == "uploaded"
    assert len(report["sha256_hash"]) == 64

    # Verify physical file exists on disk
    file_path = storage_service.get_file_path(report["storage_key"])
    assert file_path.exists()
    assert file_path.stat().st_size == len(sample_pdf_bytes)


def test_upload_fake_pdf_rejected_by_magic_bytes(client: TestClient):
    """Verify that a text file disguised as a .pdf is rejected."""
    headers = _get_auth_headers(client, "fakepdf@example.com")

    p_res = client.post(
        "/patients",
        json={"full_name": "Patient X", "date_of_birth": "1990-01-01", "biological_sex": "female"},
        headers=headers,
    )
    assert p_res.status_code == 201
    patient_id = p_res.json()["id"]

    # File with .pdf extension but plain text content
    fake_pdf = b"This is not a real PDF document at all."
    files = {"file": ("fake.pdf", io.BytesIO(fake_pdf), "application/pdf")}

    res = client.post(
        f"/patients/{patient_id}/reports",
        files=files,
        headers=headers,
    )
    assert res.status_code == 400
    assert "File content does not match supported PDF or Image headers" in res.json()["detail"]


def test_upload_disallowed_extension_rejected(client: TestClient):
    """Verify that executable or script extensions are rejected."""
    headers = _get_auth_headers(client, "badext@example.com")

    p_res = client.post(
        "/patients",
        json={"full_name": "Patient Y", "date_of_birth": "1990-01-01", "biological_sex": "male"},
        headers=headers,
    )
    assert p_res.status_code == 201
    patient_id = p_res.json()["id"]

    files = {"file": ("malicious.exe", io.BytesIO(b"%PDF-fake"), "application/octet-stream")}
    res = client.post(
        f"/patients/{patient_id}/reports",
        files=files,
        headers=headers,
    )
    assert res.status_code == 400
    assert "Unsupported file format" in res.json()["detail"]


def test_list_and_get_reports(client: TestClient, sample_pdf_bytes: bytes):
    """Verify listing reports for a patient and fetching report by ID."""
    headers = _get_auth_headers(client, "lister@example.com")

    p_res = client.post(
        "/patients",
        json={"full_name": "Meena Iyer", "date_of_birth": "1985-08-20", "biological_sex": "female"},
        headers=headers,
    )
    assert p_res.status_code == 201
    patient_id = p_res.json()["id"]

    # Upload report
    files = {"file": ("report.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
    upload_res = client.post(
        f"/patients/{patient_id}/reports",
        files=files,
        headers=headers,
    )
    assert upload_res.status_code == 201
    report_id = upload_res.json()["id"]

    # List reports
    list_res = client.get(f"/patients/{patient_id}/reports", headers=headers)
    assert list_res.status_code == 200
    reports = list_res.json()
    assert len(reports) == 1
    assert reports[0]["id"] == report_id

    # Get single report
    get_res = client.get(f"/reports/{report_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == report_id


def test_update_and_delete_report(client: TestClient, sample_pdf_bytes: bytes):
    """Verify updating metadata and deleting a report removes both DB record and file."""
    headers = _get_auth_headers(client, "updater@example.com")

    p_res = client.post(
        "/patients",
        json={"full_name": "Arun Menon", "date_of_birth": "1968-11-04", "biological_sex": "male"},
        headers=headers,
    )
    assert p_res.status_code == 201
    patient_id = p_res.json()["id"]

    # Upload report
    files = {"file": ("arun_r1.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
    upload_res = client.post(f"/patients/{patient_id}/reports", files=files, headers=headers)
    assert upload_res.status_code == 201
    report_id = upload_res.json()["id"]
    storage_key = upload_res.json()["storage_key"]

    file_path = storage_service.get_file_path(storage_key)
    assert file_path.exists()

    # Update metadata
    patch_res = client.patch(
        f"/reports/{report_id}",
        json={"lab_name": "City Care Labs", "notes": "Fasting sample"},
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["lab_name"] == "City Care Labs"
    assert patch_res.json()["notes"] == "Fasting sample"

    # Delete report
    del_res = client.delete(f"/reports/{report_id}", headers=headers)
    assert del_res.status_code == 204

    # Verify report is gone from DB
    get_res = client.get(f"/reports/{report_id}", headers=headers)
    assert get_res.status_code == 404

    # Verify physical file is cleaned up from disk
    assert not file_path.exists()


def test_two_user_isolation_reports(client: TestClient, sample_pdf_bytes: bytes):
    """Verify strict multi-tenant isolation: User B cannot access User A's reports."""
    headers_a = _get_auth_headers(client, "usera_rep@example.com")
    headers_b = _get_auth_headers(client, "userb_rep@example.com")

    # User A creates a patient and uploads a report
    p_res = client.post(
        "/patients",
        json={"full_name": "User A Patient", "date_of_birth": "1980-01-01", "biological_sex": "male"},
        headers=headers_a,
    )
    assert p_res.status_code == 201
    patient_a_id = p_res.json()["id"]

    files = {"file": ("report.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
    upload_res = client.post(f"/patients/{patient_a_id}/reports", files=files, headers=headers_a)
    assert upload_res.status_code == 201
    report_a_id = upload_res.json()["id"]

    # 1. User B tries to upload to User A's patient -> 404 Not Found
    b_files = {"file": ("breach.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
    b_upload = client.post(f"/patients/{patient_a_id}/reports", files=b_files, headers=headers_b)
    assert b_upload.status_code == 404

    # 2. User B tries to list User A's patient reports -> 404 Not Found
    b_list = client.get(f"/patients/{patient_a_id}/reports", headers=headers_b)
    assert b_list.status_code == 404

    # 3. User B tries to get User A's report by ID -> 404 Not Found
    b_get = client.get(f"/reports/{report_a_id}", headers=headers_b)
    assert b_get.status_code == 404

    # 4. User B tries to update User A's report -> 404 Not Found
    b_patch = client.patch(f"/reports/{report_a_id}", json={"lab_name": "Hacked"}, headers=headers_b)
    assert b_patch.status_code == 404

    # 5. User B tries to delete User A's report -> 404 Not Found
    b_del = client.delete(f"/reports/{report_a_id}", headers=headers_b)
    assert b_del.status_code == 404

