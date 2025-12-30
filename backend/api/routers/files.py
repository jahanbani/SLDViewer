"""File upload and management endpoints for SLD Viewer.

Phase 1: File upload with validation and storage.
"""

import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from backend.core.config import get_settings

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload a RAW/RAWX file for processing.

    Validates file extension, generates a unique file_id, and stores the file.
    The file is saved with the generated UUID as the filename, preserving
    the original extension.

    Args:
        file: Uploaded file from request

    Returns:
        JSON response with file_id: {"file_id": "<uuid>"}

    Returns (on error):
        JSONResponse with error structure: {"error": {"code": "...", "message": "..."}}
    """
    settings = get_settings()

    # Validate file extension
    filename = file.filename or ""
    file_ext = Path(filename).suffix.lower()
    if file_ext not in [".raw", ".rawx"]:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_FILE_TYPE",
                    "message": f"File must have .raw or .rawx extension. Got: {file_ext}",
                }
            },
        )

    # Generate unique file_id
    file_id = str(uuid.uuid4())

    # Determine storage path
    storage_path = Path(settings.storage_root)
    storage_path.mkdir(parents=True, exist_ok=True)

    # Save file with UUID as name, preserving original extension
    file_path = storage_path / f"{file_id}{file_ext}"

    try:
        # Stream file content to disk
        with open(file_path, "wb") as f:
            # Read file in chunks for large files
            while chunk := await file.read(8192):  # 8KB chunks
                f.write(chunk)
    except OSError as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "FILE_SAVE_ERROR",
                    "message": f"Failed to save file: {str(e)}",
                }
            },
        )

    return {"file_id": file_id}

