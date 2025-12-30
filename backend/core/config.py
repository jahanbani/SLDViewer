"""Configuration settings for SLD Viewer backend.

Uses Pydantic v2 BaseSettings to load configuration from environment variables
with sensible defaults. Settings can be overridden via environment variables.
"""

import sys
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


def _get_project_root() -> Path:
    """Get the project root directory (SLDViewer folder)."""
    # This file is in backend/core/config.py
    # Project root is 2 levels up
    config_file = Path(__file__).resolve()
    project_root = config_file.parent.parent.parent
    return project_root


def _get_default_storage_root() -> str:
    """Get default storage root as absolute path."""
    project_root = _get_project_root()
    storage_path = project_root / "backend" / "storage" / "user_files"
    return str(storage_path.resolve())


class Settings(BaseSettings):
    """Application settings with defaults from SLD_PLAN.md.

    All settings can be overridden via environment variables using the
    same field names (uppercase, e.g., STORAGE_ROOT, BUS_LIMIT_DEFAULT).
    """

    # Storage configuration - defaults to absolute path relative to project root
    storage_root: str = _get_default_storage_root()

    # CORS configuration
    cors_origins: list[str] = ["http://localhost:5173"]

    # View limits (from SLD_PLAN.md section 9)
    bus_limit_default: int = 300  # BUS_LIMIT_DEFAULT
    substation_limit_default: int = 500  # SUBSTATION_LIMIT_DEFAULT
    initial_view_limit: int = 100  # INITIAL_VIEW_LIMIT

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache()
def get_settings() -> Settings:
    """Get singleton Settings instance.

    Uses functools.lru_cache() to ensure only one Settings instance
    is created and reused across the application.

    Returns:
        Settings: The singleton settings instance
    """
    return Settings()

