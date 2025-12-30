#!/usr/bin/env python3
"""Test if we can access VeraGrid when imported like the server does."""

import sys
from pathlib import Path

# Simulate exactly what happens when uvicorn imports backend.api.main
print("=" * 60)
print("Testing VeraGrid Import in Server Context")
print("=" * 60)

# Step 1: Add project root (like run.py does)
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
print(f"\n1. Added project root to path: {project_root}")

# Step 2: Add VeraGrid (like run.py does)
veragrid_path = project_root / "VeraGrid" / "src"
if veragrid_path.exists():
    sys.path.insert(0, str(veragrid_path))
    print(f"2. Added VeraGrid to path: {veragrid_path}")
else:
    print(f"2. [FAIL] VeraGrid path not found: {veragrid_path}")
    sys.exit(1)

# Step 3: Import like the server would
print("\n3. Importing backend.api.main (this triggers all imports)...")
try:
    # This will import main.py, which imports routers, which import rawx_parser
    from backend.api import main
    print("   [OK] Imported backend.api.main")
except Exception as e:
    print(f"   [FAIL] Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 4: Check rawx_parser
print("\n4. Checking rawx_parser.VERAGRID_AVAILABLE...")
try:
    from backend.core.graph import rawx_parser
    if rawx_parser.VERAGRID_AVAILABLE:
        print("   [OK] VERAGRID_AVAILABLE = True")
    else:
        print("   [FAIL] VERAGRID_AVAILABLE = False")
        print(f"   sys.path: {sys.path[:5]}")  # Show first 5 paths
        sys.exit(1)
except Exception as e:
    print(f"   [FAIL] Error checking: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("[SUCCESS] Server context test passed!")
print("=" * 60)

