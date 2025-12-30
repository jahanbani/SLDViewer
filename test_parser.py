#!/usr/bin/env python3
"""Test the parser step by step."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("=" * 60)
print("Testing Parser Step by Step")
print("=" * 60)

# Step 1: Test import
print("\n1. Testing import of rawx_parser...")
try:
    from backend.core.graph import rawx_parser
    print("   [OK] Import successful")
except Exception as e:
    print(f"   [FAIL] Import failed: {e}")
    sys.exit(1)

# Step 2: Check if VeraGrid is available
print("\n2. Checking if VeraGrid is available...")
try:
    if rawx_parser.VERAGRID_AVAILABLE:
        print("   [OK] VeraGrid is available")
    else:
        print("   [FAIL] VeraGrid is NOT available")
        print("   This means the parser will raise NotImplementedError")
        sys.exit(1)
except AttributeError:
    print("   [FAIL] VERAGRID_AVAILABLE attribute not found")
    sys.exit(1)

# Step 3: Test file path
print("\n3. Testing file path...")
file_path = Path("backend/storage/user_files/9cef6ed2-0dcb-42d9-9dfc-f70b45e710db.rawx")
if file_path.exists():
    print(f"   [OK] File exists: {file_path.resolve()}")
else:
    print(f"   [FAIL] File not found: {file_path}")
    print(f"   Current directory: {Path.cwd()}")
    # Try absolute path
    abs_path = Path(r"C:\Users\alij\Box\AliPersonal\Company\SLDViewer\backend\storage\user_files\9cef6ed2-0dcb-42d9-9dfc-f70b45e710db.rawx")
    if abs_path.exists():
        print(f"   [OK] Found at absolute path: {abs_path}")
        file_path = abs_path
    else:
        sys.exit(1)

# Step 4: Test parsing
print("\n4. Testing parse_file()...")
try:
    buses, branches = rawx_parser.parse_file(str(file_path))
    print(f"   [OK] Parsing successful!")
    print(f"   Parsed {len(buses)} buses and {len(branches)} branches")
    if buses:
        print(f"   Sample bus: {buses[0].name} (PSSE #{buses[0].psse_number})")
except NotImplementedError as e:
    print(f"   [FAIL] NotImplementedError: {e}")
    print("   This means VERAGRID_AVAILABLE is False")
    sys.exit(1)
except Exception as e:
    print(f"   [FAIL] Parsing failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("[SUCCESS] All tests passed!")
print("=" * 60)

