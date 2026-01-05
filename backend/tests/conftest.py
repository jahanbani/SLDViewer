"""
Pytest configuration and shared fixtures.
"""
import sys
from pathlib import Path

# Add backend to Python path for imports
backend_path = Path(__file__).parent.parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))
