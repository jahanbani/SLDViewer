"""
Tests for the views API endpoints.
"""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.core.storage import storage
from backend.core.cache import parsed_case_cache

client = TestClient(app)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
IEEE14_PATH = FIXTURES_DIR / "ieee14.raw"


@pytest.fixture(autouse=True)
def cleanup_storage():
    """Clean up storage and cache before and after each test."""
    # Clear cache
    parsed_case_cache._cache.clear()
    yield
    parsed_case_cache._cache.clear()


@pytest.fixture
def uploaded_file():
    """Upload a test file and return file_id."""
    with open(IEEE14_PATH, "rb") as f:
        response = client.post(
            "/api/v1/files/upload",
            files={"file": ("ieee14.raw", f, "application/octet-stream")},
        )
    assert response.status_code == 200
    return response.json()["file_id"]


class TestViewsEndpoint:
    """Tests for POST /api/v1/views/{file_id}."""

    def test_generate_bus_view(self, uploaded_file):
        """Test generating a bus-mode view."""
        spec = {
            "mode": "bus",
            "center_bus_numbers": [1],
            "max_depth": 2,
            "node_limit": 100,
            "edge_limit": 200,
            "include_equipment": True,
            "include_dc": True,
            "include_switches": True,
            "topology_mode": "as_modeled",
            "terminal_mode": "explicit_nodes",
            "terminal_limit": 500,
            "max_terminals_per_bus_render": 24,
            "collapse_junction_buses": False,
        }

        response = client.post(f"/api/v1/views/{uploaded_file}", json=spec)
        assert response.status_code == 200

        payload = response.json()
        assert "elements" in payload
        assert "nodes" in payload["elements"]
        assert "edges" in payload["elements"]
        assert "meta" in payload

    def test_view_contains_buses(self, uploaded_file):
        """Test that view contains bus nodes."""
        spec = {
            "mode": "bus",
            "center_bus_numbers": [1],
            "max_depth": 1,
        }

        response = client.post(f"/api/v1/views/{uploaded_file}", json=spec)
        assert response.status_code == 200

        payload = response.json()
        bus_nodes = [n for n in payload["elements"]["nodes"] if n["data"]["kind"] == "bus"]
        assert len(bus_nodes) >= 1

    def test_view_contains_terminals(self, uploaded_file):
        """Test that view contains terminal nodes."""
        spec = {
            "mode": "bus",
            "center_bus_numbers": [1],
            "max_depth": 2,
        }

        response = client.post(f"/api/v1/views/{uploaded_file}", json=spec)
        assert response.status_code == 200

        payload = response.json()
        terminal_nodes = [n for n in payload["elements"]["nodes"] if n["data"]["kind"] == "terminal"]
        assert len(terminal_nodes) >= 1

    def test_view_no_positions(self, uploaded_file):
        """Test that view contains no position data."""
        spec = {
            "mode": "bus",
            "center_bus_numbers": [1],
            "max_depth": 2,
        }

        response = client.post(f"/api/v1/views/{uploaded_file}", json=spec)
        assert response.status_code == 200

        payload = response.json()
        for node in payload["elements"]["nodes"]:
            assert "position" not in node
            assert "x" not in node.get("data", {})
            assert "y" not in node.get("data", {})

    def test_view_invalid_bus(self, uploaded_file):
        """Test that requesting invalid bus returns 404."""
        spec = {
            "mode": "bus",
            "center_bus_numbers": [99999],
            "max_depth": 1,
        }

        response = client.post(f"/api/v1/views/{uploaded_file}", json=spec)
        assert response.status_code == 404
        assert "VIEW_BUS_NOT_FOUND" in str(response.json())

    def test_view_file_not_found(self):
        """Test that requesting non-existent file returns 404."""
        spec = {
            "mode": "bus",
            "center_bus_numbers": [1],
            "max_depth": 1,
        }

        response = client.post("/api/v1/views/nonexistent-file", json=spec)
        assert response.status_code == 404


class TestSummaryEndpoint:
    """Tests for GET /api/v1/files/{file_id}/summary."""

    def test_get_summary(self, uploaded_file):
        """Test getting case summary."""
        response = client.get(f"/api/v1/files/{uploaded_file}/summary")
        assert response.status_code == 200

        summary = response.json()
        assert summary["file_id"] == uploaded_file
        assert summary["format"] == "raw"
        assert summary["bus_count"] == 14
        assert summary["ac_branch_count"] >= 18
        assert "voltage_levels" in summary

    def test_summary_file_not_found(self):
        """Test that requesting non-existent file returns 404."""
        response = client.get("/api/v1/files/nonexistent-file/summary")
        assert response.status_code == 404


class TestBusSearchEndpoint:
    """Tests for GET /api/v1/files/{file_id}/buses/search."""

    def test_search_by_number_exact(self, uploaded_file):
        """Test exact numeric search."""
        response = client.get(f"/api/v1/files/{uploaded_file}/buses/search?q=1")
        assert response.status_code == 200

        results = response.json()["results"]
        assert len(results) >= 1
        # First result should be exact match
        assert results[0]["psse_number"] == 1

    def test_search_by_number_prefix(self, uploaded_file):
        """Test prefix numeric search."""
        response = client.get(f"/api/v1/files/{uploaded_file}/buses/search?q=1")
        assert response.status_code == 200

        results = response.json()["results"]
        # Should include buses starting with 1 (1, 10, 11, 12, 13, 14)
        for result in results:
            assert str(result["psse_number"]).startswith("1")

    def test_search_by_name(self, uploaded_file):
        """Test text search by name."""
        response = client.get(f"/api/v1/files/{uploaded_file}/buses/search?q=BUS")
        assert response.status_code == 200

        results = response.json()["results"]
        # IEEE 14 buses are named "BUS 1", "BUS 2", etc.
        assert len(results) >= 1
        for result in results:
            assert "BUS" in result["name"].upper()

    def test_search_limit(self, uploaded_file):
        """Test search limit parameter."""
        response = client.get(f"/api/v1/files/{uploaded_file}/buses/search?q=BUS&limit=3")
        assert response.status_code == 200

        results = response.json()["results"]
        assert len(results) <= 3

    def test_search_no_results(self, uploaded_file):
        """Test search with no matches."""
        response = client.get(f"/api/v1/files/{uploaded_file}/buses/search?q=NONEXISTENT")
        assert response.status_code == 200

        results = response.json()["results"]
        assert len(results) == 0


class TestRefreshEndpoint:
    """Tests for POST /api/v1/files/{file_id}/refresh."""

    def test_refresh_cache(self, uploaded_file):
        """Test cache refresh."""
        # First request to populate cache
        client.get(f"/api/v1/files/{uploaded_file}/summary")

        # Refresh
        response = client.post(f"/api/v1/files/{uploaded_file}/refresh")
        assert response.status_code == 200
        assert response.json()["status"] == "refreshed"

    def test_refresh_file_not_found(self):
        """Test refresh for non-existent file."""
        response = client.post("/api/v1/files/nonexistent-file/refresh")
        assert response.status_code == 404
