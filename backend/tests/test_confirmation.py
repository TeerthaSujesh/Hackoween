"""Tests for Candidate Review, Report Confirmation, Longitudinal Timeline & Findings.

Verifies:
1. Candidate review flow: user confirms valid candidates and rejects noise.
2. Canonical observations table population: confirmed rows become permanent timeline observations.
3. Health-data safety invariant: rejected/unreviewed rows are strictly excluded from timeline.
4. User edit overrides during confirmation (e.g. corrected numeric value).
5. Longitudinal timeline query (`GET /patients/{id}/timeline`) and marker filtering.
6. Deterministic findings generation (`GET /patients/{id}/findings`) matching Section 5.3 contract.
7. Patient-owned data export (`GET /patients/{id}/export`).
8. Two-user multi-tenant isolation on confirmation, timeline, and export endpoints.
"""

import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient


def _get_auth_headers(client: TestClient, email: str, password: str = "SecurePass123!") -> dict:
    """Helper to register and login a user, returning auth headers."""
    client.post("/auth/register", json={"email": email, "password": password})
    login_res = client.post("/auth/login", json={"email": email, "password": password})
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_confirm_candidates_and_populate_timeline(client: TestClient):
    """Verify confirming extracted candidates populates canonical longitudinal timeline."""
    rajesh_pdf_path = Path(__file__).resolve().parents[2] / "data" / "personas" / "rajesh" / "report_1.pdf"
    if not rajesh_pdf_path.exists():
        pytest.skip("Rajesh report_1.pdf fixture not found.")

    pdf_bytes = rajesh_pdf_path.read_bytes()
    headers = _get_auth_headers(client, "confirm_user@example.com")

    # 1. Create patient
    p_res = client.post(
        "/patients",
        json={"full_name": "Rajesh Kumar", "date_of_birth": "1977-05-12", "biological_sex": "male"},
        headers=headers,
    )
    patient_id = p_res.json()["id"]

    # 2. Upload report
    files = {"file": ("report_1.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    up_res = client.post(f"/patients/{patient_id}/reports", files=files, headers=headers)
    report_id = up_res.json()["id"]

    # 3. Extract candidates
    ext_res = client.post(f"/reports/{report_id}/extract", headers=headers)
    candidates = ext_res.json()["candidates"]
    assert len(candidates) >= 6

    # 4. Build confirmation payload: confirm all standard markers, reject Blood Urea
    items = []
    for c in candidates:
        if "urea" in c["raw_marker_name"].lower():
            items.append({"candidate_id": c["id"], "action": "reject"})
        else:
            items.append({"candidate_id": c["id"], "action": "confirm"})

    # 5. Submit confirmation
    confirm_payload = {
        "collection_date": "2023-01-15",
        "items": items,
    }
    conf_res = client.post(f"/reports/{report_id}/confirm", json=confirm_payload, headers=headers)
    assert conf_res.status_code == 200
    data = conf_res.json()
    assert data["status"] == "confirmed"
    assert data["rejected_count"] == 1
    assert data["confirmed_count"] == len(items) - 1

    # 6. Verify GET /patients/{id}/timeline contains only confirmed observations
    tl_res = client.get(f"/patients/{patient_id}/timeline", headers=headers)
    assert tl_res.status_code == 200
    timeline = tl_res.json()
    assert len(timeline) == data["confirmed_count"]

    marker_codes = [obs["marker_code"] for obs in timeline]
    assert "creatinine" in marker_codes
    assert "hba1c" in marker_codes
    assert "fasting_glucose" in marker_codes
    assert "hb" in marker_codes
    assert "urea" not in marker_codes  # Rejected row was excluded!


def test_user_edit_override_during_confirmation(client: TestClient):
    """Verify user can correct a misread number during confirmation."""
    rajesh_pdf_path = Path(__file__).resolve().parents[2] / "data" / "personas" / "rajesh" / "report_1.pdf"
    pdf_bytes = rajesh_pdf_path.read_bytes() if rajesh_pdf_path.exists() else b"%PDF-1.4\n"

    headers = _get_auth_headers(client, "edit_user@example.com")
    p_res = client.post("/patients", json={"full_name": "Edit Patient"}, headers=headers)
    patient_id = p_res.json()["id"]

    files = {"file": ("report_1.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    up_res = client.post(f"/patients/{patient_id}/reports", files=files, headers=headers)
    report_id = up_res.json()["id"]

    ext_res = client.post(f"/reports/{report_id}/extract", headers=headers)
    candidates = ext_res.json()["candidates"]

    # Locate Creatinine candidate and override value to 0.85
    cr_cand = next(c for c in candidates if "creatinine" in c["raw_marker_name"].lower())
    confirm_payload = {
        "collection_date": "2023-01-15",
        "items": [
            {
                "candidate_id": cr_cand["id"],
                "action": "confirm",
                "marker_code": "creatinine",
                "confirmed_value": 0.85,
                "confirmed_unit": "mg/dL",
            }
        ],
    }

    conf_res = client.post(f"/reports/{report_id}/confirm", json=confirm_payload, headers=headers)
    assert conf_res.status_code == 200

    # Verify timeline reflects the edited value 0.85
    tl_res = client.get(f"/patients/{patient_id}/timeline?marker=creatinine", headers=headers)
    assert tl_res.status_code == 200
    obs = tl_res.json()
    assert len(obs) == 1
    assert obs[0]["value"] == 0.85


def test_patient_findings_and_export(client: TestClient):
    """Verify computing deterministic findings and exporting patient health records."""
    headers = _get_auth_headers(client, "findings_user@example.com")

    # 1. Create patient
    p_res = client.post(
        "/patients",
        json={"full_name": "Rajesh Kumar", "date_of_birth": "1977-05-12", "biological_sex": "male"},
        headers=headers,
    )
    patient_id = p_res.json()["id"]

    rajesh_r1_path = Path(__file__).resolve().parents[2] / "data" / "personas" / "rajesh" / "report_1.pdf"
    rajesh_r2_path = Path(__file__).resolve().parents[2] / "data" / "personas" / "rajesh" / "report_2.pdf"

    # Upload & confirm Report 1 (cr: 0.8, date: 2023-01-15)
    f1 = {"file": ("r1.pdf", io.BytesIO(rajesh_r1_path.read_bytes()), "application/pdf")}
    rep1_id = client.post(f"/patients/{patient_id}/reports", files=f1, headers=headers).json()["id"]
    cands1 = client.post(f"/reports/{rep1_id}/extract", headers=headers).json()["candidates"]
    client.post(
        f"/reports/{rep1_id}/confirm",
        json={"collection_date": "2023-01-15", "items": [{"candidate_id": c["id"], "action": "confirm"} for c in cands1]},
        headers=headers,
    )

    # Upload & confirm Report 2 (cr: 1.0, date: 2023-12-10) -> Triggers RCV jump!
    f2 = {"file": ("r2.pdf", io.BytesIO(rajesh_r2_path.read_bytes()), "application/pdf")}
    rep2_id = client.post(f"/patients/{patient_id}/reports", files=f2, headers=headers).json()["id"]
    cands2 = client.post(f"/reports/{rep2_id}/extract", headers=headers).json()["candidates"]
    client.post(
        f"/reports/{rep2_id}/confirm",
        json={"collection_date": "2023-12-10", "items": [{"candidate_id": c["id"], "action": "confirm"} for c in cands2]},
        headers=headers,
    )

    # 2. Query GET /patients/{id}/findings
    findings_res = client.get(f"/patients/{patient_id}/findings", headers=headers)
    assert findings_res.status_code == 200
    findings = findings_res.json()
    assert len(findings) >= 1

    kd_finding = next((f for f in findings if f["pattern"] == "kidney_decline"), None)
    assert kd_finding is not None
    assert kd_finding["marker"] == "creatinine"
    assert kd_finding["type"] == "personal_baseline_shift"
    assert kd_finding["severity"] in ("watch", "consult_soon")
    assert kd_finding["rcv_exceeded"] is True
    assert "personal_band" in kd_finding
    assert "Nephrologist" in kd_finding["specialist"]

    # 3. Query GET /patients/{id}/export (Patient Ownership)
    export_res = client.get(f"/patients/{patient_id}/export", headers=headers)
    assert export_res.status_code == 200
    export_data = export_res.json()
    assert export_data["patient"]["full_name"] == "Rajesh Kumar"
    assert len(export_data["reports"]) == 2
    assert len(export_data["observations"]) >= 10
    assert len(export_data["findings"]) >= 1


def test_two_user_isolation_confirmation(client: TestClient):
    """Verify User B cannot confirm User A's report or access User A's timeline/findings."""
    rajesh_pdf_path = Path(__file__).resolve().parents[2] / "data" / "personas" / "rajesh" / "report_1.pdf"
    pdf_bytes = rajesh_pdf_path.read_bytes() if rajesh_pdf_path.exists() else b"%PDF-1.4\n"

    headers_a = _get_auth_headers(client, "conf_a@example.com")
    headers_b = _get_auth_headers(client, "conf_b@example.com")

    # User A creates patient, report, and extracts
    p_res = client.post("/patients", json={"full_name": "Patient A"}, headers=headers_a)
    patient_a_id = p_res.json()["id"]

    files = {"file": ("report_1.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    up_res = client.post(f"/patients/{patient_a_id}/reports", files=files, headers=headers_a)
    report_a_id = up_res.json()["id"]

    ext_res = client.post(f"/reports/{report_a_id}/extract", headers=headers_a)
    cands_a = ext_res.json()["candidates"]

    # User B tries to confirm User A's report -> 404 Not Found
    payload = {
        "items": [{"candidate_id": cands_a[0]["id"], "action": "confirm"}]
    }
    b_conf = client.post(f"/reports/{report_a_id}/confirm", json=payload, headers=headers_b)
    assert b_conf.status_code == 404

    # User B tries to read User A's timeline -> 404 Not Found
    b_tl = client.get(f"/patients/{patient_a_id}/timeline", headers=headers_b)
    assert b_tl.status_code == 404

    # User B tries to get User A's findings -> 404 Not Found
    b_findings = client.get(f"/patients/{patient_a_id}/findings", headers=headers_b)
    assert b_findings.status_code == 404

    # User B tries to export User A's data -> 404 Not Found
    b_export = client.get(f"/patients/{patient_a_id}/export", headers=headers_b)
    assert b_export.status_code == 404
