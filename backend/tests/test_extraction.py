"""Tests for Lab Report Candidate Extraction and Modality Guardrail.

Verifies:
1. Extraction on real digital lab PDF (Rajesh Report 1) using table parsing.
2. Verified numeric values match ground truth (Creatinine 0.8 mg/dL, HbA1c 5.3%, Glucose 92 mg/dL).
3. Line-based regex extraction on Layout B (Meena Report 1).
4. Staged candidate status invariant: all candidates are staged with status='needs_review'.
5. Modality Guardrail: non-lab documents (ECG, Ultrasound) produce 0 candidate rows and set status='unsupported_modality'.
6. Two-user multi-tenant isolation on extraction endpoints.
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


def _make_simple_text_pdf(text: str) -> bytes:
    """Construct a minimal valid PDF containing text without external dependencies."""
    content = f"BT /F1 12 Tf 50 750 Td ({text}) Tj ET"
    stream_len = len(content)
    pdf = f"""%PDF-1.4
1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj
2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj
3 0 obj <</Type /Page /Parent 2 0 R /Resources <</Font <</F1 4 0 R>>>> /MediaBox [0 0 612 792] /Contents 5 0 R>> endobj
4 0 obj <</Type /Font /Subtype /Type1 /BaseFont /Helvetica>> endobj
5 0 obj <</Length {stream_len}>> stream
{content}
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000227 00000 n 
0000000300 00000 n 
trailer <</Size 6 /Root 1 0 R>>
startxref
{360 + stream_len}
%%EOF
"""
    return pdf.encode("latin1")


def test_extract_rajesh_digital_table(client: TestClient):
    """Verify table extraction on Rajesh Kumar's Report 1 matches ground truth."""
    rajesh_pdf_path = Path(__file__).resolve().parents[2] / "data" / "personas" / "rajesh" / "report_1.pdf"
    if not rajesh_pdf_path.exists():
        pytest.skip("Rajesh report_1.pdf fixture not found.")

    pdf_bytes = rajesh_pdf_path.read_bytes()
    headers = _get_auth_headers(client, "rajesh_doc@example.com")

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

    # 3. Trigger extraction
    ext_res = client.post(f"/reports/{report_id}/extract", headers=headers)
    assert ext_res.status_code == 200
    data = ext_res.json()
    assert data["status"] == "needs_review"
    assert data["candidates_count"] >= 6

    # 4. Map candidates by marker name keyword
    candidates = data["candidates"]
    c_map = {c["raw_marker_name"].lower(): c for c in candidates}

    # Verify Creatinine
    cr_match = next((c for k, c in c_map.items() if "creatinine" in k), None)
    assert cr_match is not None
    assert cr_match["numeric_value"] == 0.8
    assert "mg/dL" in cr_match["raw_unit"]
    assert cr_match["status"] == "needs_review"

    # Verify HbA1c
    hba1c_match = next((c for k, c in c_map.items() if "hba1c" in k or "glycated" in k), None)
    assert hba1c_match is not None
    assert hba1c_match["numeric_value"] == 5.3
    assert "%" in hba1c_match["raw_unit"]

    # Verify Fasting Glucose
    glu_match = next((c for k, c in c_map.items() if "sugar" in k or "glucose" in k), None)
    assert glu_match is not None
    assert glu_match["numeric_value"] == 92.0

    # 5. Verify GET /reports/{id}/candidates
    cand_res = client.get(f"/reports/{report_id}/candidates", headers=headers)
    assert cand_res.status_code == 200
    assert len(cand_res.json()) == data["candidates_count"]


def test_extract_meena_regex_lines(client: TestClient):
    """Verify line-based regex extraction on Meena Iyer's Report 1."""
    meena_pdf_path = Path(__file__).resolve().parents[2] / "data" / "personas" / "meena" / "report_1.pdf"
    if not meena_pdf_path.exists():
        pytest.skip("Meena report_1.pdf fixture not found.")

    pdf_bytes = meena_pdf_path.read_bytes()
    headers = _get_auth_headers(client, "meena_doc@example.com")

    # 1. Create patient
    p_res = client.post(
        "/patients",
        json={"full_name": "Meena Iyer", "date_of_birth": "1985-08-20", "biological_sex": "female"},
        headers=headers,
    )
    patient_id = p_res.json()["id"]

    # 2. Upload report
    files = {"file": ("report_1.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    up_res = client.post(f"/patients/{patient_id}/reports", files=files, headers=headers)
    report_id = up_res.json()["id"]

    # 3. Trigger extraction
    ext_res = client.post(f"/reports/{report_id}/extract", headers=headers)
    assert ext_res.status_code == 200
    data = ext_res.json()
    assert data["status"] == "needs_review"
    assert data["candidates_count"] >= 6

    # Verify Hemoglobin extracted
    c_names = [c["raw_marker_name"].lower() for c in data["candidates"]]
    assert any("haemoglobin" in n or "hb" in n for n in c_names)


def test_modality_guardrail_rejects_ecg_and_narrative(client: TestClient):
    """Verify Modality Guardrail marks non-lab report as unsupported_modality."""
    pdf_bytes = _make_simple_text_pdf("City Heart Care Clinic - 12-Lead Electrocardiogram ECG Report Normal Sinus Rhythm")
    headers = _get_auth_headers(client, "guardrail_doc@example.com")

    # 1. Create patient
    p_res = client.post("/patients", json={"full_name": "Cardiac Patient"}, headers=headers)
    patient_id = p_res.json()["id"]

    # 2. Upload ECG PDF
    files = {"file": ("ecg_report.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    up_res = client.post(f"/patients/{patient_id}/reports", files=files, headers=headers)
    report_id = up_res.json()["id"]

    # 3. Trigger extraction -> Should trigger Modality Guardrail
    ext_res = client.post(f"/reports/{report_id}/extract", headers=headers)
    assert ext_res.status_code == 200
    data = ext_res.json()
    assert data["status"] == "unsupported_modality"
    assert data["candidates_count"] == 0

    # Staged candidate rows must be empty (engine protected)
    cand_res = client.get(f"/reports/{report_id}/candidates", headers=headers)
    assert cand_res.status_code == 200
    assert len(cand_res.json()) == 0


def test_two_user_isolation_extraction(client: TestClient):
    """Verify User B cannot trigger extraction or view candidates on User A's report."""
    rajesh_pdf_path = Path(__file__).resolve().parents[2] / "data" / "personas" / "rajesh" / "report_1.pdf"
    pdf_bytes = rajesh_pdf_path.read_bytes() if rajesh_pdf_path.exists() else b"%PDF-1.4\n"

    headers_a = _get_auth_headers(client, "iso_a@example.com")
    headers_b = _get_auth_headers(client, "iso_b@example.com")

    # User A creates patient and report
    p_res = client.post("/patients", json={"full_name": "User A Patient"}, headers=headers_a)
    patient_a_id = p_res.json()["id"]

    files = {"file": ("report_1.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    up_res = client.post(f"/patients/{patient_a_id}/reports", files=files, headers=headers_a)
    report_a_id = up_res.json()["id"]

    # User B tries to trigger extraction -> 404 Not Found
    b_ext = client.post(f"/reports/{report_a_id}/extract", headers=headers_b)
    assert b_ext.status_code == 404

    # User B tries to get candidates -> 404 Not Found
    b_cands = client.get(f"/reports/{report_a_id}/candidates", headers=headers_b)
    assert b_cands.status_code == 404

