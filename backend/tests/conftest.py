"""Pytest configuration for the SLDViewer repo.

Ensures the project root is on sys.path so tests can import the `backend` package
when running on Windows/conda environments where the working directory is not
automatically added.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_project_root_on_syspath() -> None:
    # This file is backend/tests/conftest.py -> project root is 2 levels up
    project_root = Path(__file__).resolve().parents[2]
    root_str = str(project_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


_ensure_project_root_on_syspath()


