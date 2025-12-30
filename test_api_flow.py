#!/usr/bin/env python3
"""Test the API flow without starting the server."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("=" * 60)
print("Testing API Flow (Parser Integration)")
print("=" * 60)

# Test the _load_and_cache_graph function logic
file_id = "9cef6ed2-0dcb-42d9-9dfc-f70b45e710db"

print(f"\n1. Testing file lookup for file_id: {file_id}")

from backend.core.config import get_settings
settings = get_settings()
storage_path = Path(settings.storage_root)

print(f"   Storage path: {storage_path}")
print(f"   Storage path exists: {storage_path.exists()}")

# Try to find the file
file_path = None
for ext in [".rawx", ".raw"]:
    candidate = storage_path / f"{file_id}{ext}"
    if candidate.exists():
        file_path = candidate
        print(f"   [OK] Found file: {candidate}")
        break

if file_path is None:
    print(f"   [FAIL] File not found")
    sys.exit(1)

print(f"\n2. Testing parser import...")
try:
    from backend.core.graph import rawx_parser
    print(f"   [OK] Parser imported successfully")
except Exception as e:
    print(f"   [FAIL] Import failed: {e}")
    sys.exit(1)

print(f"\n3. Checking VeraGrid availability...")
if not getattr(rawx_parser, "VERAGRID_AVAILABLE", False):
    print(f"   [FAIL] VeraGrid is not available")
    sys.exit(1)
else:
    print(f"   [OK] VeraGrid is available")

print(f"\n4. Testing parse_file()...")
try:
    buses, branches = rawx_parser.parse_file(str(file_path))
    print(f"   [OK] Parsing successful!")
    print(f"   Parsed {len(buses)} buses and {len(branches)} branches")
except NotImplementedError as e:
    print(f"   [FAIL] NotImplementedError: {e}")
    sys.exit(1)
except Exception as e:
    print(f"   [FAIL] Parsing failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print(f"\n5. Testing graph building...")
try:
    from backend.core.graph.graph_builder import build_graphs
    handle = build_graphs(buses, branches)
    print(f"   [OK] Graph built successfully!")
    print(f"   Graph has {len(handle.bus_by_id)} buses and {len(handle.branch_by_id)} branches")
except Exception as e:
    print(f"   [FAIL] Graph building failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("[SUCCESS] All API flow tests passed!")
print("=" * 60)
print("\nThe parser should work correctly in the API now.")
print("Please restart your backend server and try again.")

