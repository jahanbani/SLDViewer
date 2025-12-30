#!/usr/bin/env python3
"""Run the SLD Viewer backend server."""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Add VeraGrid to Python path BEFORE any imports that might need it
veragrid_path = project_root / "VeraGrid" / "src"
if veragrid_path.exists() and str(veragrid_path) not in sys.path:
    sys.path.insert(0, str(veragrid_path))

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

