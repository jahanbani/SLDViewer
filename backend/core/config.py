"""
Application configuration using Pydantic Settings.
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="SLD_", env_file=".env")

    # App info
    app_name: str = "SLD Viewer"
    app_version: str = "0.1.0"
    debug: bool = False

    # Storage
    storage_root: Path = Path("storage/user_files")
    max_upload_size_mb: int = 100

    # Cache settings
    cache_ttl_seconds: int = 3600  # 1 hour
    cache_max_entries: int = 25

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]


# Global settings instance
settings = Settings()
