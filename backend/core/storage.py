"""
Storage provider abstraction for file management.
Local filesystem implementation for development.
"""
import shutil
import uuid
from pathlib import Path
from typing import Protocol

from backend.core.config import settings
from backend.core.errors import FileNotFoundError as SLDFileNotFoundError


class StorageProvider(Protocol):
    """Protocol for storage providers."""

    def save(self, content: bytes, filename: str) -> tuple[str, Path]:
        """Save file content and return (file_id, path)."""
        ...

    def get_path(self, file_id: str) -> Path:
        """Get the path for a file by ID."""
        ...

    def exists(self, file_id: str) -> bool:
        """Check if a file exists."""
        ...

    def delete(self, file_id: str) -> None:
        """Delete a file by ID."""
        ...

    def get_format(self, file_id: str) -> str:
        """Get the format (extension) of a file."""
        ...


class LocalStorageProvider:
    """Local filesystem storage provider for development."""

    def __init__(self, root: Path | None = None):
        self.root = root or settings.storage_root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, content: bytes, filename: str) -> tuple[str, Path]:
        """
        Save file content to local storage.

        Args:
            content: File bytes
            filename: Original filename (used to extract extension)

        Returns:
            Tuple of (file_id, file_path)
        """
        file_id = str(uuid.uuid4())
        ext = Path(filename).suffix.lower()
        file_path = self.root / f"{file_id}{ext}"

        file_path.write_bytes(content)
        return file_id, file_path

    def get_path(self, file_id: str) -> Path:
        """
        Get the path for a file by ID.

        Searches for files matching the ID with any extension.
        """
        # Look for files matching file_id with any extension
        for ext in [".raw", ".rawx"]:
            path = self.root / f"{file_id}{ext}"
            if path.exists():
                return path

        raise SLDFileNotFoundError(file_id)

    def exists(self, file_id: str) -> bool:
        """Check if a file exists."""
        try:
            self.get_path(file_id)
            return True
        except SLDFileNotFoundError:
            return False

    def delete(self, file_id: str) -> None:
        """Delete a file by ID."""
        path = self.get_path(file_id)
        path.unlink(missing_ok=True)

    def get_format(self, file_id: str) -> str:
        """Get the format (extension without dot) of a file."""
        path = self.get_path(file_id)
        return path.suffix.lower().lstrip(".")


# Global storage instance
storage = LocalStorageProvider()
