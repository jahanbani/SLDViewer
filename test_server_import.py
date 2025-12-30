#!/usr/bin/env python3
"""Test if the server can import and use the parser correctly."""

import sys
from pathlib import Path

# Simulate how uvicorn imports the module
print("=" * 60)
print("Testing Server-Side Import")
print("=" * 60)

# Add project root (like run.py does)
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print(f"\n1. Project root: {project_root}")
print(f"   Current working directory: {Path.cwd()}")

print("\n2. Importing rawx_parser (as server would)...")
try:
    from backend.core.graph import rawx_parser
    print("   [OK] Import successful")
except Exception as e:
    print(f"   [FAIL] Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n3. Checking VERAGRID_AVAILABLE...")
if rawx_parser.VERAGRID_AVAILABLE:
    print("   [OK] VeraGrid is available")
else:
    print("   [FAIL] VeraGrid is NOT available")
    print("   This is the problem!")
    sys.exit(1)

print("\n4. Testing parse_file with a test file...")
test_file = project_root / "ieee118.rawx"
if test_file.exists():
    try:
        buses, branches = rawx_parser.parse_file(str(test_file))
        print(f"   [OK] Parsing works! ({len(buses)} buses, {len(branches)} branches)")
    except Exception as e:
        print(f"   [FAIL] Parsing failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
else:
    print(f"   [SKIP] Test file not found: {test_file}")

print("\n" + "=" * 60)
print("[SUCCESS] Server-side import test passed!")
print("=" * 60)

