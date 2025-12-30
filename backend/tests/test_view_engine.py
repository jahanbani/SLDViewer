"""Tests for view_engine module."""

import pytest

from backend.core.config import Settings, get_settings
from backend.core.graph.graph_builder import GraphHandle, build_graphs
from backend.core.graph.models import BranchModel, BusModel, ViewMode, ViewSpec
from backend.core.graph.view_engine import UnsupportedViewModeError, view


def test_view_bus_mode():
    """Test view generation in BUS mode."""
    # Create test data
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
    settings = get_settings()
    spec = ViewSpec(mode=ViewMode.BUS, center_bus_numbers=[1001], degrees=1)
    result = view(handle, spec, settings)
    assert len(result.buses) >= 1
    assert len(result.branches) >= 0
    assert result.meta["mode"] == "bus"
    assert "node_count" in result.meta
    assert "edge_count" in result.meta


def test_view_substation_mode_requires_substations():
    """Test that SUBSTATION mode raises error when no substations are available."""
    bus = BusModel(
        id="bus-1",
        psse_number=1001,
        name="Bus 1",
        base_kv=230.0,
        area=1,
        zone=1,
        owner=1,
    )
    handle = build_graphs([bus], [])
    settings = get_settings()
    spec = ViewSpec(mode=ViewMode.SUBSTATION)  # Requires substations
    with pytest.raises(UnsupportedViewModeError) as exc_info:
        view(handle, spec, settings)
    assert "substations" in str(exc_info.value).lower()


def test_view_default_seed():
    """Test view generation with default seed (no center_bus_numbers)."""
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
    handle = build_graphs([bus1, bus2], [])
    settings = get_settings()
    spec = ViewSpec(mode=ViewMode.BUS, center_bus_numbers=None, degrees=1)
    result = view(handle, spec, settings)
    # Should use bus with smallest psse_number (1001)
    assert len(result.buses) >= 1

