"""Unit Tests for API Health Route.

This test suite verifies the operational health endpoint (`GET /health`).
It serves as the smoke test for the web layer.
"""

from fastapi.testclient import TestClient


def test_health_check_returns_ok(client: TestClient) -> None:
    """Verify that GET /health responds with HTTP 200 and expected status body.
    
    Checks:
    - Status code is 200 OK.
    - Response payload contains `{"status": "ok", "app": "Trend Doctor"}`.
    """
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "Trend Doctor"
