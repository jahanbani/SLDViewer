#!/usr/bin/env python3
"""Test VeraGrid import directly to see what the actual error is."""

import sys
from pathlib import Path

# Set up path exactly like the server does
project_root = Path(__file__).parent
veragrid_path = project_root / "VeraGrid" / "src"

print("=" * 60)
print("Direct VeraGrid Import Test")
print("=" * 60)
print(f"\nProject root: {project_root}")
print(f"VeraGrid path: {veragrid_path}")
print(f"Path exists: {veragrid_path.exists()}")

if veragrid_path.exists():
    path_str = str(veragrid_path.resolve())
    print(f"Path string: {path_str}")
    
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
        print(f"Added to sys.path")
    else:
        print(f"Already in sys.path")
    
    print(f"\nFirst 3 entries in sys.path:")
    for i, p in enumerate(sys.path[:3]):
        print(f"  {i}: {p}")
    
    print(f"\nTrying to import VeraGridEngine...")
    try:
        from VeraGridEngine.IO.file_handler import FileOpen
        from VeraGridEngine.IO.raw.rawx_parser_writer import parse_rawx
        from VeraGridEngine.IO.raw.raw_to_veragrid import psse_to_veragrid
        from VeraGridEngine.basic_structures import Logger
        print("   [SUCCESS] All imports successful!")
    except ImportError as e:
        print(f"   [FAIL] Import failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
else:
    print(f"\n[FAIL] VeraGrid path does not exist!")
    sys.exit(1)

print("\n" + "=" * 60)
print("[SUCCESS] VeraGrid can be imported!")
print("=" * 60)

