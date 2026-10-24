"""Health Check API Router.

A dedicated `/health` route is the industry standard for monitoring and orchestrating
distributed services (Docker, Kubernetes, Render, AWS ECS, etc.).

Why this endpoint exists:
-------------------------
1. Liveness probes: Verifies that the FastAPI process is alive and responding to HTTP requests.
2. Deployment smoke tests: After deploying or migrating the database, automated scripts
   ping `/health` to verify that the application booted successfully before routing real user traffic.
3. Decoupled router: By placing this in `app/api/health.py` rather than directly in `main.py`,
   our project follows the Single Responsibility Principle, making it trivial to add `/auth`,
   `/patients`, `/reports`, `/timeline`, and `/findings` routers in subsequent milestones.
"""

from fastapi import APIRouter

# Create an APIRouter tagged for clear grouping in OpenAPI (/docs) documentation
router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Return application operational status.
    
    Returns:
        JSON response indicating 'status': 'ok' and application name.
    """
    return {
        "status": "ok",
        "app": "Trend Doctor",
    }
