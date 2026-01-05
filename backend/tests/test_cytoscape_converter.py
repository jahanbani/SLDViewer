"""
Tests for Cytoscape payload converter.
"""
from pathlib import Path
import pytest

from backend.core.graph.cytoscape_converter import (
    CytoscapeConverter,
    convert_to_cytoscape,
)
from backend.core.graph.slicer import slice_view
from backend.core.graph.graph_builder import build_case_graph, CaseGraph
from backend.core.graph.veragrid_adapter import VeraGridAdapter
from backend.core.graph.models import ViewSpec, ViewMode, CytoscapePayload


FIXTURES_DIR = Path(__file__).parent / "fixtures"
IEEE14_PATH = FIXTURES_DIR / "ieee14.raw"


@pytest.fixture
def ieee14_graph() -> CaseGraph:
    """Build graph from IEEE 14 bus case."""
    adapter = VeraGridAdapter(IEEE14_PATH, "test-ieee14", "raw")
    case = adapter.parse()
    return build_case_graph(case)


@pytest.fixture
def ieee14_slice(ieee14_graph):
    """Get a slice of IEEE 14 bus case."""
    spec = ViewSpec(
        mode=ViewMode.BUS,
        center_bus_numbers=[1],
        max_depth=2,
        include_equipment=True,
    )
    return slice_view(ieee14_graph, spec), spec


class TestCytoscapeConverter:
    """Tests for CytoscapeConverter."""

    def test_convert_returns_payload(self, ieee14_slice):
        """Test that conversion returns a CytoscapePayload."""
        slice_result, spec = ieee14_slice
        payload = convert_to_cytoscape(slice_result, spec)

        assert isinstance(payload, CytoscapePayload)
        assert "nodes" in payload.elements
        assert "edges" in payload.elements

    def test_payload_has_bus_nodes(self, ieee14_slice):
        """Test that payload contains bus nodes."""
        slice_result, spec = ieee14_slice
        payload = convert_to_cytoscape(slice_result, spec)

        bus_nodes = [n for n in payload.elements["nodes"] if n["data"]["kind"] == "bus"]
        assert len(bus_nodes) >= 1

    def test_bus_nodes_have_required_fields(self, ieee14_slice):
        """Test that bus nodes have required fields."""
        slice_result, spec = ieee14_slice
        payload = convert_to_cytoscape(slice_result, spec)

        bus_nodes = [n for n in payload.elements["nodes"] if n["data"]["kind"] == "bus"]
        assert len(bus_nodes) >= 1

        bus = bus_nodes[0]["data"]
        assert "id" in bus
        assert "kind" in bus
        assert "psse_number" in bus
        assert "name" in bus
        assert "base_kv" in bus
        assert "inService" in bus
        assert "bfs_depth" in bus
        assert "orientation" in bus
        assert "renderKind" in bus

    def test_payload_has_terminal_nodes(self, ieee14_slice):
        """Test that payload contains terminal nodes."""
        slice_result, spec = ieee14_slice
        payload = convert_to_cytoscape(slice_result, spec)

        terminal_nodes = [
            n for n in payload.elements["nodes"] if n["data"]["kind"] == "terminal"
        ]
        # Should have terminals for branch connections
        assert len(terminal_nodes) >= 1

    def test_terminal_nodes_have_parent_bus(self, ieee14_slice):
        """Test that terminal nodes reference their parent bus."""
        slice_result, spec = ieee14_slice
        payload = convert_to_cytoscape(slice_result, spec)

        terminal_nodes = [
            n for n in payload.elements["nodes"] if n["data"]["kind"] == "terminal"
        ]

        for term in terminal_nodes:
            assert "parentBusId" in term["data"]
            assert term["data"]["parentBusId"] is not None

    def test_payload_has_bus_stub_edges(self, ieee14_slice):
        """Test that payload contains bus_stub edges."""
        slice_result, spec = ieee14_slice
        payload = convert_to_cytoscape(slice_result, spec)

        stub_edges = [
            e for e in payload.elements["edges"] if e["data"]["kind"] == "bus_stub"
        ]
        # Should have stub edges connecting buses to terminals
        assert len(stub_edges) >= 1

    def test_bus_stub_edges_connect_bus_to_terminal(self, ieee14_slice):
        """Test that bus_stub edges connect bus to terminal."""
        slice_result, spec = ieee14_slice
        payload = convert_to_cytoscape(slice_result, spec)

        stub_edges = [
            e for e in payload.elements["edges"] if e["data"]["kind"] == "bus_stub"
        ]

        bus_ids = {n["data"]["id"] for n in payload.elements["nodes"] if n["data"]["kind"] == "bus"}
        term_ids = {n["data"]["id"] for n in payload.elements["nodes"] if n["data"]["kind"] == "terminal"}

        for edge in stub_edges:
            # Source should be bus, target should be terminal
            assert edge["data"]["source"] in bus_ids
            assert edge["data"]["target"] in term_ids

    def test_payload_has_branch_edges(self, ieee14_slice):
        """Test that payload contains branch edges."""
        slice_result, spec = ieee14_slice
        payload = convert_to_cytoscape(slice_result, spec)

        branch_edges = [
            e for e in payload.elements["edges"] if e["data"]["kind"] == "branch"
        ]
        # Should have branch edges for lines
        assert len(branch_edges) >= 1

    def test_branch_edges_connect_terminals(self, ieee14_slice):
        """Test that branch edges connect terminal to terminal."""
        slice_result, spec = ieee14_slice
        payload = convert_to_cytoscape(slice_result, spec)

        term_ids = {
            n["data"]["id"]
            for n in payload.elements["nodes"]
            if n["data"]["kind"] == "terminal"
        }

        branch_edges = [
            e for e in payload.elements["edges"] if e["data"]["kind"] == "branch"
        ]

        for edge in branch_edges:
            # Both source and target should be terminals
            assert edge["data"]["source"] in term_ids
            assert edge["data"]["target"] in term_ids

    def test_payload_has_equipment_nodes(self, ieee14_slice):
        """Test that payload contains equipment nodes."""
        slice_result, spec = ieee14_slice
        payload = convert_to_cytoscape(slice_result, spec)

        eq_nodes = [
            n for n in payload.elements["nodes"] if n["data"]["kind"] == "equipment"
        ]
        # IEEE 14 bus 1 has a generator
        assert len(eq_nodes) >= 1

    def test_equipment_nodes_have_equipment_link(self, ieee14_slice):
        """Test that equipment nodes have equipment_link edges."""
        slice_result, spec = ieee14_slice
        payload = convert_to_cytoscape(slice_result, spec)

        eq_nodes = [
            n for n in payload.elements["nodes"] if n["data"]["kind"] == "equipment"
        ]
        eq_link_edges = [
            e for e in payload.elements["edges"] if e["data"]["kind"] == "equipment_link"
        ]

        # Should have one link per equipment
        assert len(eq_link_edges) == len(eq_nodes)

    def test_no_positions_in_payload(self, ieee14_slice):
        """Test that no position data is included."""
        slice_result, spec = ieee14_slice
        payload = convert_to_cytoscape(slice_result, spec)

        for node in payload.elements["nodes"]:
            assert "position" not in node
            assert "x" not in node.get("data", {})
            assert "y" not in node.get("data", {})

    def test_payload_has_metadata(self, ieee14_slice):
        """Test that payload has metadata."""
        slice_result, spec = ieee14_slice
        payload = convert_to_cytoscape(slice_result, spec)

        assert "node_count" in payload.meta
        assert "edge_count" in payload.meta
        assert "bus_count" in payload.meta
        assert "terminal_count" in payload.meta


class TestGraphStructureInvariants:
    """Tests for graph structure invariants."""

    def test_no_bus_to_bus_edges(self, ieee14_slice):
        """Test that there are no direct bus→bus edges."""
        slice_result, spec = ieee14_slice
        payload = convert_to_cytoscape(slice_result, spec)

        bus_ids = {
            n["data"]["id"]
            for n in payload.elements["nodes"]
            if n["data"]["kind"] == "bus"
        }

        for edge in payload.elements["edges"]:
            source = edge["data"]["source"]
            target = edge["data"]["target"]
            kind = edge["data"]["kind"]

            # Branch edges should NOT be bus→bus
            if kind == "branch":
                assert not (source in bus_ids and target in bus_ids), (
                    f"Branch edge {edge['data']['id']} connects buses directly"
                )

    def test_all_terminals_have_bus_stubs(self, ieee14_slice):
        """Test that all terminals have corresponding bus_stub edges."""
        slice_result, spec = ieee14_slice
        payload = convert_to_cytoscape(slice_result, spec)

        term_ids = {
            n["data"]["id"]
            for n in payload.elements["nodes"]
            if n["data"]["kind"] == "terminal"
        }

        stub_targets = {
            e["data"]["target"]
            for e in payload.elements["edges"]
            if e["data"]["kind"] == "bus_stub"
        }

        # Every terminal should be target of a bus_stub edge
        assert term_ids == stub_targets


class TestParallelEdgeHints:
    """Tests for parallel edge hint computation."""

    def test_parallel_edges_have_indices(self, ieee14_slice):
        """Test that parallel edges have index hints when applicable."""
        slice_result, spec = ieee14_slice
        payload = convert_to_cytoscape(slice_result, spec)

        branch_edges = [
            e for e in payload.elements["edges"] if e["data"]["kind"] == "branch"
        ]

        # Each branch should have parallel_key
        for edge in branch_edges:
            assert "parallel_key" in edge["data"]
