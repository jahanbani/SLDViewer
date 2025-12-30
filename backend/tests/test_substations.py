"""Tests for substation inference logic."""

import pytest

from backend.core.graph.models import BranchModel, BusModel
from backend.core.graph.substations import (
    _build_strong_coupling_graph,
    _find_common_prefix,
    _infer_substation_name,
    _majority_vote,
    assign_substations_to_buses,
    infer_substations,
)


def test_majority_vote():
    """Test majority vote function."""
    assert _majority_vote([1, 2, 1, 1]) == 1
    assert _majority_vote([None, 2, 2]) == 2
    assert _majority_vote([None, None]) is None
    assert _majority_vote([]) is None
    assert _majority_vote([5]) == 5


def test_find_common_prefix():
    """Test common prefix finding."""
    assert _find_common_prefix(["abc123", "abc456", "abc789"]) == "abc"
    assert _find_common_prefix(["Station_A_1", "Station_A_2"]) == "Station_A_"
    assert _find_common_prefix(["xyz", "abc"]) == ""
    assert _find_common_prefix([]) == ""
    assert _find_common_prefix(["single"]) == "single"


def test_infer_substation_name():
    """Test substation name inference."""
    # Test common prefix
    buses = [
        BusModel(id="1", psse_number=1, name="MainSt_Bus1", base_kv=138.0, area=1, zone=1, owner=1),
        BusModel(id="2", psse_number=2, name="MainSt_Bus2", base_kv=138.0, area=1, zone=1, owner=1),
    ]
    name = _infer_substation_name(buses, 0)
    assert name == "MainSt_Bus"

    # Test longest name
    buses = [
        BusModel(id="1", psse_number=1, name="Short", base_kv=138.0, area=1, zone=1, owner=1),
        BusModel(id="2", psse_number=2, name="VeryLongName", base_kv=138.0, area=1, zone=1, owner=1),
    ]
    name = _infer_substation_name(buses, 0)
    assert name == "VeryLongName"

    # Test default name
    buses = [
        BusModel(id="1", psse_number=1, name="", base_kv=138.0, area=1, zone=1, owner=1),
    ]
    name = _infer_substation_name(buses, 5)
    assert name == "Substation_6"


def test_build_strong_coupling_graph():
    """Test strong coupling graph construction."""
    buses = [
        BusModel(id="bus1", psse_number=1, name="Bus1", base_kv=138.0, area=1, zone=1, owner=1),
        BusModel(id="bus2", psse_number=2, name="Bus2", base_kv=138.0, area=1, zone=1, owner=1),
        BusModel(id="bus3", psse_number=3, name="Bus3", base_kv=138.0, area=1, zone=1, owner=1),
        BusModel(id="bus4", psse_number=4, name="Bus4", base_kv=69.0, area=1, zone=1, owner=1),
    ]

    branches = [
        # Zero impedance line (switch) - bus1 <-> bus2
        BranchModel(
            id="br1",
            from_bus_id="bus1",
            to_bus_id="bus2",
            circuit="1",
            type="line",
            r=0.0,
            x=0.0,
            b=0.0,
            g=0.0,
        ),
        # Small impedance transformer - bus1 <-> bus4 (connects voltage levels)
        BranchModel(
            id="br2",
            from_bus_id="bus1",
            to_bus_id="bus4",
            circuit="1",
            type="xfmr",
            r=0.001,
            x=0.005,
            b=0.0,
            g=0.0,
        ),
        # Large impedance line - bus2 <-> bus3 (transmission line, not in same station)
        BranchModel(
            id="br3",
            from_bus_id="bus2",
            to_bus_id="bus3",
            circuit="1",
            type="line",
            r=0.1,
            x=0.5,
            b=0.01,
            g=0.0,
        ),
    ]

    bus_by_id = {bus.id: bus for bus in buses}
    graph = _build_strong_coupling_graph(buses, branches, bus_by_id)

    # Check nodes
    assert set(graph.nodes()) == {"bus1", "bus2", "bus3", "bus4"}

    # Check edges - should have bus1-bus2 (zero impedance) and bus1-bus4 (xfmr)
    assert graph.has_edge("bus1", "bus2")  # Zero impedance
    assert graph.has_edge("bus1", "bus4")  # Transformer
    assert not graph.has_edge("bus2", "bus3")  # Large impedance, not strongly coupled


def test_infer_substations_simple():
    """Test basic substation inference without spatial splitting."""
    # Create a simple scenario: two substations
    # Station 1: bus1, bus2 (connected by zero impedance)
    # Station 2: bus3, bus4 (connected by transformer)
    buses = [
        BusModel(id="bus1", psse_number=101, name="StationA_138", base_kv=138.0, area=1, zone=1, owner=1),
        BusModel(id="bus2", psse_number=102, name="StationA_69", base_kv=69.0, area=1, zone=1, owner=1),
        BusModel(id="bus3", psse_number=201, name="StationB_230", base_kv=230.0, area=2, zone=2, owner=1),
        BusModel(id="bus4", psse_number=202, name="StationB_138", base_kv=138.0, area=2, zone=2, owner=1),
    ]

    branches = [
        # Station A: zero impedance between bus1 and bus2
        BranchModel(
            id="br1",
            from_bus_id="bus1",
            to_bus_id="bus2",
            circuit="1",
            type="line",
            r=0.0,
            x=0.0,
            b=0.0,
            g=0.0,
        ),
        # Station B: transformer between bus3 and bus4
        BranchModel(
            id="br2",
            from_bus_id="bus3",
            to_bus_id="bus4",
            circuit="1",
            type="xfmr",
            r=0.001,
            x=0.01,
            b=0.0,
            g=0.0,
        ),
        # Transmission line between stations (high impedance)
        BranchModel(
            id="br3",
            from_bus_id="bus2",
            to_bus_id="bus3",
            circuit="1",
            type="line",
            r=0.5,
            x=1.0,
            b=0.01,
            g=0.0,
        ),
    ]

    substations, bus_to_sub_map = infer_substations(buses, branches)

    # Should have 2 substations
    assert len(substations) == 2

    # Check that bus1 and bus2 are in same substation
    sub1 = bus_to_sub_map["bus1"]
    sub2 = bus_to_sub_map["bus2"]
    assert sub1 == sub2

    # Check that bus3 and bus4 are in same substation
    sub3 = bus_to_sub_map["bus3"]
    sub4 = bus_to_sub_map["bus4"]
    assert sub3 == sub4

    # Check that the two stations are different
    assert sub1 != sub3

    # Check substation properties
    sub_a = next(s for s in substations if s.id == sub1)
    assert set(sub_a.voltage_levels) == {138.0, 69.0}
    assert sub_a.nominal_kv == 138.0
    assert sub_a.area == 1
    assert sub_a.zone == 1

    sub_b = next(s for s in substations if s.id == sub3)
    assert set(sub_b.voltage_levels) == {230.0, 138.0}
    assert sub_b.nominal_kv == 230.0
    assert sub_b.area == 2
    assert sub_b.zone == 2


def test_assign_substations_to_buses():
    """Test assigning substation IDs to buses."""
    buses = [
        BusModel(id="bus1", psse_number=1, name="Bus1", base_kv=138.0, area=1, zone=1, owner=1),
        BusModel(id="bus2", psse_number=2, name="Bus2", base_kv=138.0, area=1, zone=1, owner=1),
    ]

    bus_to_sub_map = {
        "bus1": "sub_a",
        "bus2": "sub_a",
    }

    updated_buses = assign_substations_to_buses(buses, bus_to_sub_map)

    assert len(updated_buses) == 2
    assert updated_buses[0].substation_id == "sub_a"
    assert updated_buses[1].substation_id == "sub_a"
    # Original buses should not be modified
    assert buses[0].substation_id is None
    assert buses[1].substation_id is None


def test_infer_substations_isolated_buses():
    """Test that isolated buses get their own substations."""
    buses = [
        BusModel(id="bus1", psse_number=1, name="Bus1", base_kv=138.0, area=1, zone=1, owner=1),
        BusModel(id="bus2", psse_number=2, name="Bus2", base_kv=138.0, area=1, zone=1, owner=1),
        BusModel(id="bus3", psse_number=3, name="Bus3", base_kv=138.0, area=1, zone=1, owner=1),
    ]

    # No branches - all buses are isolated
    branches = []

    substations, bus_to_sub_map = infer_substations(buses, branches)

    # Each bus should get its own substation
    assert len(substations) == 3
    assert bus_to_sub_map["bus1"] != bus_to_sub_map["bus2"]
    assert bus_to_sub_map["bus2"] != bus_to_sub_map["bus3"]
    assert bus_to_sub_map["bus1"] != bus_to_sub_map["bus3"]


def test_infer_substations_with_lat_lon():
    """Test substation inference with geographic coordinates."""
    # Create two groups of buses that are geographically separated
    # Group 1: bus1, bus2, bus3 (close together, within same station)
    # Group 2: bus4, bus5 (far away, different station)
    buses = [
        # Group 1 - close together (within 1-2 km)
        BusModel(
            id="bus1",
            psse_number=1,
            name="StationA_Bus1",
            base_kv=138.0,
            area=1,
            zone=1,
            owner=1,
            latitude=40.0,
            longitude=-74.0,
        ),
        BusModel(
            id="bus2",
            psse_number=2,
            name="StationA_Bus2",
            base_kv=138.0,
            area=1,
            zone=1,
            owner=1,
            latitude=40.005,  # About 0.5 km away
            longitude=-74.005,
        ),
        BusModel(
            id="bus3",
            psse_number=3,
            name="StationA_Bus3",
            base_kv=69.0,
            area=1,
            zone=1,
            owner=1,
            latitude=40.01,  # About 1 km away
            longitude=-74.01,
        ),
        # Group 2 - far away (about 55 km)
        BusModel(
            id="bus4",
            psse_number=4,
            name="StationB_Bus4",
            base_kv=230.0,
            area=2,
            zone=2,
            owner=1,
            latitude=40.5,
            longitude=-74.5,
        ),
        BusModel(
            id="bus5",
            psse_number=5,
            name="StationB_Bus5",
            base_kv=138.0,
            area=2,
            zone=2,
            owner=1,
            latitude=40.505,
            longitude=-74.505,
        ),
    ]

    branches = [
        # Station A - all connected with small impedance
        BranchModel(
            id="br1",
            from_bus_id="bus1",
            to_bus_id="bus2",
            circuit="1",
            type="line",
            r=0.0001,
            x=0.0001,
            b=0.0,
            g=0.0,
        ),
        BranchModel(
            id="br2",
            from_bus_id="bus2",
            to_bus_id="bus3",
            circuit="1",
            type="xfmr",  # Transformer connecting voltage levels
            r=0.001,
            x=0.01,
            b=0.0,
            g=0.0,
        ),
        # Station B - connected with transformer
        BranchModel(
            id="br3",
            from_bus_id="bus4",
            to_bus_id="bus5",
            circuit="1",
            type="xfmr",
            r=0.001,
            x=0.01,
            b=0.0,
            g=0.0,
        ),
        # Long transmission line between stations (should not create strong coupling)
        BranchModel(
            id="br4",
            from_bus_id="bus3",
            to_bus_id="bus4",
            circuit="1",
            type="line",
            r=0.5,
            x=1.5,
            b=0.01,
            g=0.0,
        ),
    ]

    substations, bus_to_sub_map = infer_substations(buses, branches, spatial_threshold_km=10.0)

    # Check Group 1 (Station A) - all buses should be in same substation
    sub1 = bus_to_sub_map["bus1"]
    sub2 = bus_to_sub_map["bus2"]
    sub3 = bus_to_sub_map["bus3"]
    assert sub1 == sub2 == sub3, "Buses in Station A should be in same substation"

    # Check Group 2 (Station B) - all buses should be in same substation
    sub4 = bus_to_sub_map["bus4"]
    sub5 = bus_to_sub_map["bus5"]
    assert sub4 == sub5, "Buses in Station B should be in same substation"

    # Check that the two stations are different
    assert sub1 != sub4, "Station A and Station B should be different substations"

    # Should have exactly 2 substations
    assert len(substations) == 2

    # Check substation properties for Station A
    sub_a = next(s for s in substations if s.id == sub1)
    assert set(sub_a.voltage_levels) == {138.0, 69.0}
    assert sub_a.nominal_kv == 138.0

    # Check substation properties for Station B
    sub_b = next(s for s in substations if s.id == sub4)
    assert set(sub_b.voltage_levels) == {230.0, 138.0}
    assert sub_b.nominal_kv == 230.0
