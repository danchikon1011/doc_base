"""FastAPI application entry point."""
import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError

from .api import admin, auth, documents
from .core.config import get_settings
from .core.database import engine
from .models import Base  # noqa: F401

logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(title=settings.project_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {"status": "ok"}

def _get_frontend_dir() -> Path:
    frontend_override = os.getenv("FRONTEND_DIR")
    if frontend_override:
        return Path(frontend_override)

    possible_dirs = [
        Path(__file__).resolve().parents[2] / "frontend",
        Path(__file__).resolve().parents[1] / "frontend",
    ]

    for candidate in possible_dirs:
        if candidate.exists():
            return candidate

    # Fall back to the first option so FastAPI still raises a helpful
    # error if the directory truly does not exist.
    return possible_dirs[0]


frontend_dir = _get_frontend_dir()
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


@app.on_event("startup")
def _init_database() -> None:
    """Create database schema on startup without crashing if DB is unavailable."""

    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError as exc:  # pragma: no cover - depends on deployment state
        logger.warning("Database unavailable; skipping schema creation: %s", exc)
