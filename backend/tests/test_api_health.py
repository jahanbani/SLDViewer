"""
Tests for basic API health and file upload.
"""
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


def test_health_endpoint(client):
    """Test that /health returns ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_root_endpoint(client):
    """Test that / returns API info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data
    assert data["docs"] == "/docs"


def test_upload_rejects_invalid_extension(client):
    """Test that upload rejects non .raw/.rawx files."""
    response = client.post(
        "/api/v1/files/upload",
        files={"file": ("test.txt", b"some content", "text/plain")},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["code"] == "FILE_INVALID_FORMAT"


def test_upload_accepts_raw_file(client, tmp_path):
    """Test that upload accepts .raw files."""
    # Create a minimal RAW-like content (doesn't need to be valid for this test)
    content = b"0, 100.00, 35   / PSS(R)E-35.0"

    response = client.post(
        "/api/v1/files/upload",
        files={"file": ("test_case.raw", content, "application/octet-stream")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "file_id" in data
    assert data["format"] == "raw"


def test_upload_accepts_rawx_file(client):
    """Test that upload accepts .rawx files."""
    content = b'{"network": {}}'

    response = client.post(
        "/api/v1/files/upload",
        files={"file": ("test_case.rawx", content, "application/json")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "file_id" in data
    assert data["format"] == "rawx"
