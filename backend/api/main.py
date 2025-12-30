"""FastAPI application entrypoint for SLD Viewer backend.

Creates and configures the FastAPI app with CORS, routers, and settings.
"""

import sys
from pathlib import Path

# Ensure VeraGrid is in path (in case uvicorn reload changes context)
# This file is in backend/api/main.py, so project root is 2 levels up
_project_root = Path(__file__).resolve().parent.parent.parent
_veragrid_path = _project_root / "VeraGrid" / "src"
if _veragrid_path.exists() and str(_veragrid_path) not in sys.path:
    sys.path.insert(0, str(_veragrid_path))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import get_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Sets up CORS, includes routers, and loads application settings.

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title="SLD Viewer API",
        description="Single Line Diagram Viewer for PSSE power system data",
        version="1.0.0",
    )

    # Load settings
    settings = get_settings()

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],  # Allow all HTTP methods
        allow_headers=["*"],  # Allow all headers
    )

    # Include routers under /api/v1 prefix
    # Routers will be implemented in subsequent steps
    try:
        from backend.api.routers import files, graphs

        app.include_router(files.router, prefix="/api/v1", tags=["files"])
        app.include_router(graphs.router, prefix="/api/v1", tags=["graphs"])
    except (ImportError, AttributeError):
        # Routers may not be fully implemented yet - this is OK for Phase 1 setup
        pass

    return app


# Expose app at module level
app = create_app()

