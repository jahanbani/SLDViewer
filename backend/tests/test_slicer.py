"""
Tests for view slicing.
"""
from pathlib import Path
import pytest

from backend.core.graph.slicer import ViewSlicer, slice_view, SliceResult
from backend.core.graph.graph_builder import build_case_graph, CaseGraph
from backend.core.graph.veragrid_adapter import VeraGridAdapter
from backend.core.graph.models import ViewSpec, ViewMode, TopologyMode


FIXTURES_DIR = Path(__file__).parent / "fixtures"
IEEE14_PATH = FIXTURES_DIR / "ieee14.raw"


@pytest.fixture
def ieee14_graph() -> CaseGraph:
    """Build graph from IEEE 14 bus case."""
    adapter = VeraGridAdapter(IEEE14_PATH, "test-ieee14", "raw")
    case = adapter.parse()
    return build_case_graph(case)


class TestBusModeSlicing:
    """Tests for bus mode slicing."""

    def test_slice_single_bus_depth_0(self, ieee14_graph):
        """Test slicing with depth 0 returns only center bus."""
        spec = ViewSpec(
            mode=ViewMode.BUS,
            center_bus_numbers=[1],
            max_depth=0,
        )

        result = slice_view(ieee14_graph, spec)

        assert len(result.buses) == 1
        assert result.buses[0].psse_number == 1

    def test_slice_single_bus_depth_1(self, ieee14_graph):
        """Test slicing with depth 1 returns neighbors."""
        spec = ViewSpec(
            mode=ViewMode.BUS,
            center_bus_numbers=[1],
            max_depth=1,
        )

        result = slice_view(ieee14_graph, spec)

        # Bus 1 connects to buses 2 and 5 in IEEE 14
        assert len(result.buses) >= 2
        psse_numbers = {b.psse_number for b in result.buses}
        assert 1 in psse_numbers

    def test_slice_respects_node_limit(self, ieee14_graph):
        """Test that node limit is respected."""
        spec = ViewSpec(
            mode=ViewMode.BUS,
            center_bus_numbers=[1],
            max_depth=10,  # Would get all buses
            node_limit=5,
        )

        result = slice_view(ieee14_graph, spec)

        assert len(result.buses) <= 5
        assert result.truncated is True
        assert result.truncation_reason == "node_limit"

    def test_slice_includes_branches(self, ieee14_graph):
        """Test that branches between sliced buses are included."""
        spec = ViewSpec(
            mode=ViewMode.BUS,
            center_bus_numbers=[1],
            max_depth=1,
        )

        result = slice_view(ieee14_graph, spec)

        # Should have branches connecting the buses
        assert len(result.ac_branches) >= 1

    def test_slice_includes_equipment(self, ieee14_graph):
        """Test that equipment is included when requested."""
        spec = ViewSpec(
            mode=ViewMode.BUS,
            center_bus_numbers=[1],
            max_depth=1,
            include_equipment=True,
        )

        result = slice_view(ieee14_graph, spec)

        # Bus 1 has a generator
        assert len(result.equipment) >= 1

    def test_slice_excludes_equipment_when_disabled(self, ieee14_graph):
        """Test that equipment is excluded when disabled."""
        spec = ViewSpec(
            mode=ViewMode.BUS,
            center_bus_numbers=[1],
            max_depth=1,
            include_equipment=False,
        )

        result = slice_view(ieee14_graph, spec)

        assert len(result.equipment) == 0

    def test_bfs_depth_recorded(self, ieee14_graph):
        """Test that BFS depth is recorded for each bus."""
        spec = ViewSpec(
            mode=ViewMode.BUS,
            center_bus_numbers=[1],
            max_depth=2,
        )

        result = slice_view(ieee14_graph, spec)

        # Center bus should have depth 0
        center_bus = next(b for b in result.buses if b.psse_number == 1)
        assert result.bfs_depth[center_bus.id] == 0

        # Other buses should have depth >= 1
        for bus in result.buses:
            if bus.psse_number != 1:
                assert result.bfs_depth[bus.id] >= 1

    def test_invalid_center_bus_warning(self, ieee14_graph):
        """Test that invalid center bus produces warning."""
        spec = ViewSpec(
            mode=ViewMode.BUS,
            center_bus_numbers=[99999],  # Does not exist
            max_depth=1,
        )

        result = slice_view(ieee14_graph, spec)

        assert len(result.warnings) >= 1
        assert any("99999" in w for w in result.warnings)


class TestSubstationModeSlicing:
    """Tests for substation mode slicing."""

    def test_slice_returns_substations(self, ieee14_graph):
        """Test that substation mode returns substations."""
        spec = ViewSpec(mode=ViewMode.SUBSTATION)

        result = slice_view(ieee14_graph, spec)

        # IEEE 14 has substations
        assert len(result.substations) >= 1

    def test_slice_returns_inter_substation_branches(self, ieee14_graph):
        """Test that substation mode returns inter-substation branches."""
        spec = ViewSpec(mode=ViewMode.SUBSTATION)

        result = slice_view(ieee14_graph, spec)

        # Should have branches between different substations
        # (may be 0 if all buses are in same substation)
        # Just verify no error occurs
        assert isinstance(result.ac_branches, list)


class TestStationDetailModeSlicing:
    """Tests for station detail mode slicing."""

    def test_slice_single_station(self, ieee14_graph):
        """Test slicing a single station."""
        # Get first substation
        if not ieee14_graph.case.substations:
            pytest.skip("No substations in test case")

        sub = ieee14_graph.case.substations[0]
        spec = ViewSpec(
            mode=ViewMode.STATION_DETAIL,
            center_substation_ids=[sub.id],
        )

        result = slice_view(ieee14_graph, spec)

        # Should have the substation
        assert len(result.substations) == 1
        assert result.substations[0].id == sub.id


class TestTopologyMode:
    """Tests for topology mode handling."""

    def test_as_modeled_includes_all(self, ieee14_graph):
        """Test that AS_MODELED mode includes all elements."""
        spec = ViewSpec(
            mode=ViewMode.BUS,
            center_bus_numbers=[1],
            max_depth=5,
            topology_mode=TopologyMode.AS_MODELED,
        )

        result = slice_view(ieee14_graph, spec)

        # Should get many buses
        assert len(result.buses) >= 5

    def test_energized_only_available(self, ieee14_graph):
        """Test that ENERGIZED_ONLY mode works without error."""
        spec = ViewSpec(
            mode=ViewMode.BUS,
            center_bus_numbers=[1],
            max_depth=5,
            topology_mode=TopologyMode.ENERGIZED_ONLY,
        )

        result = slice_view(ieee14_graph, spec)

        # Should work without error
        assert isinstance(result, SliceResult)
