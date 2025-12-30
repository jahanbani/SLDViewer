"""Tests for graph_builder module."""

import pytest

from backend.core.graph.graph_builder import GraphHandle, build_graphs
from backend.core.graph.models import BranchModel, BusModel


def test_build_graphs_empty():
    """Test building graphs with empty input."""
    handle = build_graphs([], [])
    assert isinstance(handle, GraphHandle)
    assert len(handle.bus_by_id) == 0
    assert len(handle.branch_by_id) == 0
    assert handle.bus_graph.number_of_nodes() == 0
    assert handle.bus_graph.number_of_edges() == 0


def test_build_graphs_single_bus():
    """Test building graphs with a single bus."""
    bus = BusModel(
        id="bus-1",
        psse_number=1001,
        name="Test Bus",
        base_kv=230.0,
        area=1,
        zone=1,
        owner=1,
    )
    handle = build_graphs([bus], [])
    assert len(handle.bus_by_id) == 1
    assert handle.bus_by_id["bus-1"] == bus
    assert handle.bus_graph.has_node("bus-1")
    assert handle.bus_graph.number_of_edges() == 0


def test_build_graphs_with_branch():
    """Test building graphs with buses and a branch."""
    bus1 = BusModel(
        id="bus-1",
        psse_number=1001,
        name="Bus 1",
        base_kv=230.0,
        area=1,
        zone=1,
        owner=1,
    )
    bus2 = BusModel(
        id="bus-2",
        psse_number=1002,
        name="Bus 2",
        base_kv=230.0,
        area=1,
        zone=1,
        owner=1,
    )
    branch = BranchModel(
        id="branch-1",
        from_bus_id="bus-1",
        to_bus_id="bus-2",
        circuit="1",
        type="line",
        r=0.01,
        x=0.1,
        b=0.0,
        g=0.0,
    )
    handle = build_graphs([bus1, bus2], [branch])
    assert len(handle.bus_by_id) == 2
    assert len(handle.branch_by_id) == 1
    assert handle.bus_graph.has_edge("bus-1", "bus-2", key="branch-1")
    assert handle.bus_graph.number_of_edges() == 1


def test_build_graphs_invalid_branch():
    """Test that building graphs with invalid branch raises error."""
    bus = BusModel(
        id="bus-1",
        psse_number=1001,
        name="Test Bus",
        base_kv=230.0,
        area=1,
        zone=1,
        owner=1,
    )
    branch = BranchModel(
        id="branch-1",
        from_bus_id="bus-1",
        to_bus_id="nonexistent",
        circuit="1",
        type="line",
        r=0.01,
        x=0.1,
        b=0.0,
        g=0.0,
    )
    with pytest.raises(ValueError, match="non-existent"):
        build_graphs([bus], [branch])

