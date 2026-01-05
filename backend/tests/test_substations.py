"""
Tests for substation detection and naming utilities.
"""
import pytest

from backend.core.graph.substations import (
    detect_substations_fallback,
    generate_substation_name,
    _extract_name_prefix,
    _find_common_prefix,
    update_substation_voltage_levels,
    apply_jumper_rule,
)
from backend.core.graph.models import (
    BusModel,
    AcBranchModel,
    SubstationModel,
    BranchKind,
    make_case_namespace,
    make_bus_id,
)


@pytest.fixture
def namespace():
    """Create test namespace."""
    return make_case_namespace("test-case")


@pytest.fixture
def sample_buses(namespace):
    """Create sample buses for testing."""
    return [
        BusModel(
            id=make_bus_id(namespace, 1),
            psse_number=1,
            name="NORTH_HV_1",
            base_kv=345.0,
            area=1,
            zone=1,
        ),
        BusModel(
            id=make_bus_id(namespace, 2),
            psse_number=2,
            name="NORTH_HV_2",
            base_kv=345.0,
            area=1,
            zone=1,
        ),
        BusModel(
            id=make_bus_id(namespace, 3),
            psse_number=3,
            name="NORTH_LV_1",
            base_kv=138.0,
            area=1,
            zone=1,
        ),
        BusModel(
            id=make_bus_id(namespace, 4),
            psse_number=4,
            name="SOUTH_HV_1",
            base_kv=345.0,
            area=2,
            zone=2,
        ),
        BusModel(
            id=make_bus_id(namespace, 5),
            psse_number=5,
            name="SOUTH_LV_1",
            base_kv=138.0,
            area=2,
            zone=2,
        ),
    ]


class TestExtractNamePrefix:
    """Tests for _extract_name_prefix."""

    def test_simple_prefix(self):
        """Test extraction of simple prefix."""
        # Extracts prefix by removing trailing numbers
        result = _extract_name_prefix("NORTH_HV_1")
        assert result is not None
        assert "NORTH" in result

    def test_prefix_with_bus_suffix(self):
        """Test removal of BUS suffix."""
        assert _extract_name_prefix("STATION_A BUS 1") == "STATION_A"

    def test_prefix_with_kv_suffix(self):
        """Test removal of kV suffix."""
        # The function removes the kV suffix
        result = _extract_name_prefix("PLANT_345KV")
        assert result is not None
        assert "PLANT" in result

    def test_short_name_returns_none(self):
        """Test that short names return None."""
        assert _extract_name_prefix("AB") is None

    def test_numeric_only_returns_none(self):
        """Test that numeric-only names return None."""
        assert _extract_name_prefix("12345") is None


class TestFindCommonPrefix:
    """Tests for _find_common_prefix."""

    def test_common_prefix_found(self):
        """Test finding common prefix."""
        names = ["NORTH_HV_1", "NORTH_HV_2", "NORTH_LV_1"]
        assert _find_common_prefix(names) == "NORTH_"

    def test_no_common_prefix(self):
        """Test when no common prefix exists."""
        names = ["NORTH_1", "SOUTH_1", "EAST_1"]
        assert _find_common_prefix(names) == ""

    def test_empty_list(self):
        """Test with empty list."""
        assert _find_common_prefix([]) == ""

    def test_single_string(self):
        """Test with single string."""
        assert _find_common_prefix(["STATION"]) == "STATION"


class TestGenerateSubstationName:
    """Tests for generate_substation_name."""

    def test_common_prefix_naming(self, sample_buses):
        """Test naming from common prefix."""
        north_buses = [b for b in sample_buses if "NORTH" in b.name]
        name, source = generate_substation_name(north_buses)
        assert "NORTH" in name
        assert source == "prefix"

    def test_fallback_naming(self):
        """Test fallback naming when no common prefix."""
        buses = [
            BusModel(id="1", psse_number=1, name="A", base_kv=138.0),
            BusModel(id="2", psse_number=2, name="B", base_kv=138.0),
        ]
        name, source = generate_substation_name(buses, area=1, zone=2, index=0)
        assert source == "fallback"
        assert "Station" in name

    def test_empty_buses_fallback(self):
        """Test fallback with empty buses."""
        name, source = generate_substation_name([], area=5, zone=10, index=3)
        assert source == "fallback"
        assert "5" in name and "10" in name


class TestDetectSubstationsFallback:
    """Tests for detect_substations_fallback."""

    def test_groups_by_prefix(self, sample_buses, namespace):
        """Test that buses are grouped by name prefix."""
        substations, mapping = detect_substations_fallback(sample_buses, namespace)

        # Should have at least 2 groups (NORTH and SOUTH)
        assert len(substations) >= 2

        # All buses should be mapped
        assert len(mapping) == len(sample_buses)

    def test_voltage_levels_collected(self, sample_buses, namespace):
        """Test that voltage levels are collected for each substation."""
        substations, _ = detect_substations_fallback(sample_buses, namespace)

        for sub in substations:
            assert len(sub.voltage_levels) >= 1

    def test_deterministic_ids(self, sample_buses, namespace):
        """Test that substation IDs are deterministic."""
        subs1, _ = detect_substations_fallback(sample_buses, namespace)
        subs2, _ = detect_substations_fallback(sample_buses, namespace)

        ids1 = {s.id for s in subs1}
        ids2 = {s.id for s in subs2}
        assert ids1 == ids2


class TestUpdateSubstationVoltageLevels:
    """Tests for update_substation_voltage_levels."""

    def test_updates_voltage_levels(self, namespace):
        """Test voltage level update."""
        sub = SubstationModel(id="sub1", name="Station A", voltage_levels=[])

        buses = [
            BusModel(
                id="bus1",
                psse_number=1,
                name="BUS1",
                base_kv=345.0,
                substation_id="sub1",
            ),
            BusModel(
                id="bus2",
                psse_number=2,
                name="BUS2",
                base_kv=138.0,
                substation_id="sub1",
            ),
        ]

        update_substation_voltage_levels([sub], buses)

        assert 345.0 in sub.voltage_levels
        assert 138.0 in sub.voltage_levels
        assert sub.nominal_kv == 345.0


class TestApplyJumperRule:
    """Tests for apply_jumper_rule."""

    def test_groups_jumper_connected_buses(self, namespace):
        """Test that buses connected by jumpers are grouped."""
        buses = [
            BusModel(id="bus1", psse_number=1, name="BUS1", base_kv=138.0),
            BusModel(id="bus2", psse_number=2, name="BUS2", base_kv=138.0),
            BusModel(id="bus3", psse_number=3, name="BUS3", base_kv=138.0),
        ]

        # Jumper between bus1 and bus2
        branches = [
            AcBranchModel(
                id="br1",
                from_bus_id="bus1",
                to_bus_id="bus2",
                kind=BranchKind.LINE,
                r=0.0,
                x=0.0,
            ),
            # Normal line between bus2 and bus3
            AcBranchModel(
                id="br2",
                from_bus_id="bus2",
                to_bus_id="bus3",
                kind=BranchKind.LINE,
                r=0.01,
                x=0.05,
            ),
        ]

        groups = apply_jumper_rule(buses, branches)

        # bus1 and bus2 should be in same group
        assert groups["bus1"] == groups["bus2"]
        # bus3 should be in different group
        assert groups["bus3"] != groups["bus1"]

    def test_no_jumpers(self, namespace):
        """Test when there are no jumpers."""
        buses = [
            BusModel(id="bus1", psse_number=1, name="BUS1", base_kv=138.0),
            BusModel(id="bus2", psse_number=2, name="BUS2", base_kv=138.0),
        ]

        branches = [
            AcBranchModel(
                id="br1",
                from_bus_id="bus1",
                to_bus_id="bus2",
                kind=BranchKind.LINE,
                r=0.01,
                x=0.1,
            ),
        ]

        groups = apply_jumper_rule(buses, branches)

        # Each bus should be its own group
        assert groups["bus1"] != groups["bus2"]
