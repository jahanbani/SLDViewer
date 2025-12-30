#!/usr/bin/env python3
"""Test script to upload a file and get a view."""

import json
import sys
from pathlib import Path

import requests

API_BASE = "http://localhost:8000/api/v1"


def upload_file(file_path: str) -> str:
    """Upload a file and return the file_id."""
    print(f"Uploading {file_path}...")

    with open(file_path, "rb") as f:
        files = {"file": (Path(file_path).name, f, "application/octet-stream")}
        response = requests.post(f"{API_BASE}/files/upload", files=files)

    if response.status_code != 200:
        print(f"Upload failed: {response.status_code}")
        print(response.text)
        sys.exit(1)

    data = response.json()
    file_id = data["file_id"]
    print(f"✓ Upload successful! File ID: {file_id}")
    return file_id


def get_view(file_id: str, center_bus: int = None, degrees: int = 1):
    """Get a graph view for a file."""
    print(f"\nRequesting view for file {file_id}...")

    view_spec = {
        "mode": "bus",
        "center_bus_numbers": [center_bus] if center_bus else None,
        "center_substation_ids": None,
        "degrees": degrees,
        "filters": {},
        "layout": "preset",
        "limit": None,
    }

    response = requests.post(
        f"{API_BASE}/graphs/{file_id}/view",
        json=view_spec,
        headers={"Content-Type": "application/json"},
    )

    if response.status_code != 200:
        print(f"View request failed: {response.status_code}")
        print(response.text)
        sys.exit(1)

    data = response.json()
    nodes = len(data["elements"]["nodes"])
    edges = len(data["elements"]["edges"])
    meta = data["meta"]

    print(f"✓ View generated!")
    print(f"  Nodes: {nodes}")
    print(f"  Edges: {edges}")
    print(f"  Mode: {meta.get('mode')}")
    print(f"  Truncated: {meta.get('truncated')}")

    return data


def main():
    """Main test function."""
    # Check if file path provided
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        file_path = "ieee118.rawx"
        # file_path = "v35.rawx"

    if not Path(file_path).exists():
        print(f"Error: File not found: {file_path}")
        print("Usage: python test_upload.py [file_path]")
        sys.exit(1)

    try:
        # Upload file
        file_id = upload_file(file_path)

        # Get view
        view_data = get_view(file_id, center_bus=1, degrees=1)

        print("\n" + "=" * 60)
        print("SUCCESS! API is working correctly.")
        print("=" * 60)
        print(f"\nYou can now use file_id '{file_id}' in the frontend UI!")

    except requests.exceptions.ConnectionError:
        print("\nError: Could not connect to backend server.")
        print("Make sure the backend is running: python backend/run.py")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
