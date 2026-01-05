"""
Tests for the graph builder.
"""
from pathlib import Path
import pytest

from backend.core.graph.graph_builder import CaseGraph, build_case_graph
from backend.core.graph.veragrid_adapter import VeraGridAdapter
from backend.core.graph.models import TopologyMode, BranchKind


FIXTURES_DIR = Path(__file__).parent / "fixtures"
IEEE14_PATH = FIXTURES_DIR / "ieee14.raw"


@pytest.fixture
def ieee14_graph() -> CaseGraph:
    """Build graph from IEEE 14 bus case."""
    adapter = VeraGridAdapter(IEEE14_PATH, "test-ieee14", "raw")
    case = adapter.parse()
    return build_case_graph(case)


class TestCaseGraph:
    """Tests for CaseGraph."""

    def test_graph_has_all_buses(self, ieee14_graph):
        """Test that graph contains all buses as nodes."""
        assert ieee14_graph.graph.number_of_nodes() == 14

    def test_graph_has_edges(self, ieee14_graph):
        """Test that graph has edges for branches."""
        # Should have edges for lines and transformers
        assert ieee14_graph.graph.number_of_edges() >= 17  # 17 lines minimum

    def test_bus_lookup_by_id(self, ieee14_graph):
        """Test bus lookup by ID."""
        # Get first bus
        bus = ieee14_graph.case.buses[0]
        found = ieee14_graph.get_bus(bus.id)
        assert found is not None
        assert found.id == bus.id

    def test_bus_lookup_by_psse(self, ieee14_graph):
        """Test bus lookup by PSSE number."""
        bus = ieee14_graph.get_bus_by_psse(1)
        assert bus is not None
        assert bus.psse_number == 1

    def test_branch_lookup(self, ieee14_graph):
        """Test branch lookup by ID."""
        # Get first branch
        branch = ieee14_graph.case.ac_branches[0]
        found = ieee14_graph.get_branch(branch.id)
        assert found is not None
        assert found.id == branch.id

    def test_equipment_by_bus(self, ieee14_graph):
        """Test equipment lookup by bus."""
        # Bus 1 should have generator
        bus1 = ieee14_graph.get_bus_by_psse(1)
        equipment = ieee14_graph.get_equipment_at_bus(bus1.id)
        assert len(equipment) >= 1

    def test_get_neighbors_as_modeled(self, ieee14_graph):
        """Test get_neighbors in AS_MODELED mode."""
        bus1 = ieee14_graph.get_bus_by_psse(1)
        neighbors = ieee14_graph.get_neighbors(bus1.id, TopologyMode.AS_MODELED)
        assert len(neighbors) >= 1

    def test_buses_by_substation(self, ieee14_graph):
        """Test buses by substation lookup."""
        # Get a substation with buses
        for sub in ieee14_graph.case.substations:
            buses = ieee14_graph.get_buses_in_substation(sub.id)
            if buses:
                assert all(b.substation_id == sub.id for b in buses)
                break

    def test_bus_degree(self, ieee14_graph):
        """Test bus degree calculation."""
        # Bus 1 in IEEE 14 is connected to bus 2 and bus 5
        bus1 = ieee14_graph.get_bus_by_psse(1)
        degree = ieee14_graph.bus_degree(bus1.id)
        assert degree >= 2

    def test_get_branches_between(self, ieee14_graph):
        """Test getting branches between two buses."""
        # Find a pair of buses with a branch
        for branch in ieee14_graph.case.ac_branches:
            branches = ieee14_graph.get_branches_between(
                branch.from_bus_id, branch.to_bus_id
            )
            assert len(branches) >= 1
            assert any(b.id == branch.id for b in branches)
            break


class TestJunctionBus:
    """Tests for junction bus detection."""

    def test_high_degree_not_junction(self, ieee14_graph):
        """Test that high-degree buses are not junctions."""
        # Find a bus with degree > 2
        for bus in ieee14_graph.case.buses:
            if ieee14_graph.bus_degree(bus.id) > 2:
                assert not ieee14_graph.is_junction_bus(bus.id, max_degree=2)
                break

    def test_low_degree_no_equipment_is_junction(self, ieee14_graph):
        """Test that low-degree buses without equipment are junctions."""
        for bus in ieee14_graph.case.buses:
            degree = ieee14_graph.bus_degree(bus.id)
            equipment = ieee14_graph.get_equipment_at_bus(bus.id)

            if degree <= 2 and not equipment:
                assert ieee14_graph.is_junction_bus(bus.id, max_degree=2)
                break


class TestBuildCaseGraph:
    """Tests for build_case_graph function."""

    def test_build_returns_case_graph(self):
        """Test that build_case_graph returns CaseGraph."""
        adapter = VeraGridAdapter(IEEE14_PATH, "test", "raw")
        case = adapter.parse()
        graph = build_case_graph(case)

        assert isinstance(graph, CaseGraph)
        assert graph.case is case
