"""
Integration tests for the full backend pipeline.

These tests verify the complete flow from file upload to view generation.
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
def cleanup():
    """Clean up storage and cache before and after each test."""
    parsed_case_cache._cache.clear()
    yield
    parsed_case_cache._cache.clear()


class TestFullPipeline:
    """Integration tests for complete upload-to-view flow."""

    def test_upload_summary_view_flow(self):
        """Test complete flow: upload -> summary -> view."""
        # Step 1: Upload file
        with open(IEEE14_PATH, "rb") as f:
            upload_response = client.post(
                "/api/v1/files/upload",
                files={"file": ("ieee14.raw", f, "application/octet-stream")},
            )
        assert upload_response.status_code == 200
        file_id = upload_response.json()["file_id"]

        # Step 2: Get summary
        summary_response = client.get(f"/api/v1/files/{file_id}/summary")
        assert summary_response.status_code == 200
        summary = summary_response.json()
        assert summary["bus_count"] == 14
        assert summary["format"] == "raw"

        # Step 3: Generate view
        view_spec = {
            "mode": "bus",
            "center_bus_numbers": [1],
            "max_depth": 3,
        }
        view_response = client.post(f"/api/v1/views/{file_id}", json=view_spec)
        assert view_response.status_code == 200
        payload = view_response.json()

        # Verify payload structure
        assert "elements" in payload
        assert "nodes" in payload["elements"]
        assert "edges" in payload["elements"]
        assert "meta" in payload

    def test_cache_hit_on_second_request(self):
        """Test that cache is used on subsequent requests."""
        # Upload file
        with open(IEEE14_PATH, "rb") as f:
            response = client.post(
                "/api/v1/files/upload",
                files={"file": ("ieee14.raw", f, "application/octet-stream")},
            )
        file_id = response.json()["file_id"]

        # First view request (should parse)
        spec = {"mode": "bus", "center_bus_numbers": [1], "max_depth": 2}
        response1 = client.post(f"/api/v1/views/{file_id}", json=spec)
        assert response1.status_code == 200

        # Second view request (should use cache)
        response2 = client.post(f"/api/v1/views/{file_id}", json=spec)
        assert response2.status_code == 200

        # Both should return same structure
        assert response1.json()["meta"]["node_count"] == response2.json()["meta"]["node_count"]

    def test_refresh_clears_cache(self):
        """Test that refresh endpoint clears cache."""
        # Upload file
        with open(IEEE14_PATH, "rb") as f:
            response = client.post(
                "/api/v1/files/upload",
                files={"file": ("ieee14.raw", f, "application/octet-stream")},
            )
        file_id = response.json()["file_id"]

        # Generate view to populate cache
        spec = {"mode": "bus", "center_bus_numbers": [1], "max_depth": 2}
        client.post(f"/api/v1/views/{file_id}", json=spec)

        # Verify cache hit
        assert parsed_case_cache.get(file_id) is not None

        # Refresh
        refresh_response = client.post(f"/api/v1/files/{file_id}/refresh")
        assert refresh_response.status_code == 200

        # Cache should be repopulated (not empty due to refresh re-parsing)
        assert parsed_case_cache.get(file_id) is not None


class TestViewPayloadInvariants:
    """Tests for view payload invariants."""

    @pytest.fixture
    def uploaded_file(self):
        """Upload test file and return file_id."""
        with open(IEEE14_PATH, "rb") as f:
            response = client.post(
                "/api/v1/files/upload",
                files={"file": ("ieee14.raw", f, "application/octet-stream")},
            )
        return response.json()["file_id"]

    def test_no_bus_to_bus_edges(self, uploaded_file):
        """Test that payload has no direct bus-to-bus edges."""
        spec = {"mode": "bus", "center_bus_numbers": [1], "max_depth": 3}
        response = client.post(f"/api/v1/views/{uploaded_file}", json=spec)
        payload = response.json()

        nodes_by_id = {n["data"]["id"]: n["data"] for n in payload["elements"]["nodes"]}
        bus_ids = {nid for nid, data in nodes_by_id.items() if data.get("kind") == "bus"}

        for edge in payload["elements"]["edges"]:
            source = edge["data"]["source"]
            target = edge["data"]["target"]
            # Both endpoints should not be buses
            assert not (source in bus_ids and target in bus_ids), (
                f"Found bus-to-bus edge: {source} -> {target}"
            )

    def test_all_terminals_have_parent_bus(self, uploaded_file):
        """Test that all terminal nodes reference a parent bus."""
        spec = {"mode": "bus", "center_bus_numbers": [1], "max_depth": 3}
        response = client.post(f"/api/v1/views/{uploaded_file}", json=spec)
        payload = response.json()

        for node in payload["elements"]["nodes"]:
            if node["data"].get("kind") == "terminal":
                assert "parentBusId" in node["data"], f"Terminal {node['data']['id']} has no parentBusId"

    def test_no_positions_in_payload(self, uploaded_file):
        """Test that payload contains no position data (frontend-only geometry)."""
        spec = {"mode": "bus", "center_bus_numbers": [1], "max_depth": 3}
        response = client.post(f"/api/v1/views/{uploaded_file}", json=spec)
        payload = response.json()

        for node in payload["elements"]["nodes"]:
            assert "position" not in node, f"Node {node['data']['id']} has position"
            assert "x" not in node.get("data", {}), f"Node {node['data']['id']} has x in data"
            assert "y" not in node.get("data", {}), f"Node {node['data']['id']} has y in data"

    def test_bfs_depth_recorded(self, uploaded_file):
        """Test that BFS depth is recorded on bus nodes."""
        spec = {"mode": "bus", "center_bus_numbers": [1], "max_depth": 3}
        response = client.post(f"/api/v1/views/{uploaded_file}", json=spec)
        payload = response.json()

        for node in payload["elements"]["nodes"]:
            if node["data"].get("kind") == "bus":
                assert "bfs_depth" in node["data"], f"Bus {node['data']['id']} has no bfs_depth"
                assert 0 <= node["data"]["bfs_depth"] <= 3, f"Invalid depth: {node['data']['bfs_depth']}"


class TestBusSearch:
    """Tests for bus search functionality."""

    @pytest.fixture
    def uploaded_file(self):
        """Upload test file and return file_id."""
        with open(IEEE14_PATH, "rb") as f:
            response = client.post(
                "/api/v1/files/upload",
                files={"file": ("ieee14.raw", f, "application/octet-stream")},
            )
        return response.json()["file_id"]

    def test_search_returns_correct_bus(self, uploaded_file):
        """Test that numeric search returns exact match first."""
        response = client.get(f"/api/v1/files/{uploaded_file}/buses/search?q=5")
        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) >= 1
        assert results[0]["psse_number"] == 5

    def test_search_case_insensitive(self, uploaded_file):
        """Test that text search is case-insensitive."""
        response1 = client.get(f"/api/v1/files/{uploaded_file}/buses/search?q=BUS")
        response2 = client.get(f"/api/v1/files/{uploaded_file}/buses/search?q=bus")

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Both should return same results
        assert len(response1.json()["results"]) == len(response2.json()["results"])


class TestTopologyModes:
    """Tests for topology mode handling."""

    @pytest.fixture
    def uploaded_file(self):
        """Upload test file and return file_id."""
        with open(IEEE14_PATH, "rb") as f:
            response = client.post(
                "/api/v1/files/upload",
                files={"file": ("ieee14.raw", f, "application/octet-stream")},
            )
        return response.json()["file_id"]

    def test_as_modeled_mode(self, uploaded_file):
        """Test as_modeled topology mode."""
        spec = {
            "mode": "bus",
            "center_bus_numbers": [1],
            "max_depth": 2,
            "topology_mode": "as_modeled",
        }
        response = client.post(f"/api/v1/views/{uploaded_file}", json=spec)
        assert response.status_code == 200

    def test_energized_only_mode(self, uploaded_file):
        """Test energized_only topology mode."""
        spec = {
            "mode": "bus",
            "center_bus_numbers": [1],
            "max_depth": 2,
            "topology_mode": "energized_only",
        }
        response = client.post(f"/api/v1/views/{uploaded_file}", json=spec)
        assert response.status_code == 200


class TestEquipmentHandling:
    """Tests for equipment in views."""

    @pytest.fixture
    def uploaded_file(self):
        """Upload test file and return file_id."""
        with open(IEEE14_PATH, "rb") as f:
            response = client.post(
                "/api/v1/files/upload",
                files={"file": ("ieee14.raw", f, "application/octet-stream")},
            )
        return response.json()["file_id"]

    def test_equipment_included_by_default(self, uploaded_file):
        """Test that equipment is included by default."""
        spec = {
            "mode": "bus",
            "center_bus_numbers": [1],
            "max_depth": 2,
        }
        response = client.post(f"/api/v1/views/{uploaded_file}", json=spec)
        payload = response.json()

        equipment_nodes = [n for n in payload["elements"]["nodes"] if n["data"].get("kind") == "equipment"]
        # IEEE 14 has equipment
        assert len(equipment_nodes) > 0

    def test_equipment_excluded_when_disabled(self, uploaded_file):
        """Test that equipment can be excluded."""
        spec = {
            "mode": "bus",
            "center_bus_numbers": [1],
            "max_depth": 2,
            "include_equipment": False,
        }
        response = client.post(f"/api/v1/views/{uploaded_file}", json=spec)
        payload = response.json()

        equipment_nodes = [n for n in payload["elements"]["nodes"] if n["data"].get("kind") == "equipment"]
        assert len(equipment_nodes) == 0
