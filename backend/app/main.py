"""FastAPI Application Entry Point.

This file initializes the top-level FastAPI application, wires global configuration,
enables CORS middleware for browser and Swagger UI interactions, registers API routers,
and prepares the application for ASGI servers like Uvicorn.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.patients import router as patients_router
from app.api.reports import router as reports_router
from app.api.benchmarks import router as benchmarks_router

# Load cached application settings
settings = get_settings()

# Instantiate the FastAPI web application
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Patient-owned lab-report timeline and longitudinal trend-awareness API.",
    # Enable Swagger UI and ReDoc in development
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
)

# Enable Cross-Origin Resource Sharing (CORS) for Swagger UI and React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(patients_router)
app.include_router(reports_router)
app.include_router(benchmarks_router)
