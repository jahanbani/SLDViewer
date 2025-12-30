#!/usr/bin/env python3
"""Fix storage path issues - move files from wrong location to correct location."""

import shutil
from pathlib import Path

# Project root
project_root = Path(__file__).parent.resolve()

# Correct storage path
correct_storage = project_root / "backend" / "storage" / "user_files"

# Wrong storage path (double backend)
wrong_storage = project_root / "backend" / "backend" / "storage" / "user_files"

print("=" * 60)
print("Storage Path Fixer")
print("=" * 60)
print(f"\nProject root: {project_root}")
print(f"Correct storage: {correct_storage}")
print(f"Wrong storage: {wrong_storage}")

if wrong_storage.exists():
    print(f"\nFound files in wrong location: {wrong_storage}")
    files = list(wrong_storage.glob("*.*"))
    print(f"Found {len(files)} files")
    
    if files:
        # Create correct directory
        correct_storage.mkdir(parents=True, exist_ok=True)
        
        # Move files
        print(f"\nMoving files to: {correct_storage}")
        for file in files:
            dest = correct_storage / file.name
            if dest.exists():
                print(f"  Skipping {file.name} (already exists in correct location)")
            else:
                shutil.move(str(file), str(dest))
                print(f"  Moved {file.name}")
        
        # Try to remove empty wrong directory
        try:
            wrong_storage.rmdir()
            print(f"\nRemoved empty directory: {wrong_storage}")
        except OSError:
            print(f"\nCould not remove directory (may not be empty): {wrong_storage}")
        
        print("\n✓ Files moved successfully!")
    else:
        print("No files to move.")
else:
    print(f"\nNo files found in wrong location.")

print(f"\nCorrect storage location: {correct_storage}")
print("=" * 60)

