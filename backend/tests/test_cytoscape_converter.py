"""Tests for cytoscape_converter module."""

from backend.core.graph.cytoscape_converter import view_result_to_cytoscape
from backend.core.graph.models import BranchModel, BusModel, ViewResult


def test_view_result_to_cytoscape_empty():
    """Test converting empty view result."""
    result = ViewResult(
        buses=[],
        branches=[],
        substations=[],
        equipment=[],
        meta={"mode": "bus", "truncated": False, "node_count": 0, "edge_count": 0},
    )
    cytoscape_data = view_result_to_cytoscape(result)
    assert "elements" in cytoscape_data
    assert "meta" in cytoscape_data
    assert len(cytoscape_data["elements"]["nodes"]) == 0
    assert len(cytoscape_data["elements"]["edges"]) == 0


def test_view_result_to_cytoscape_with_buses():
    """Test converting view result with buses."""
    bus = BusModel(
        id="bus-1",
        psse_number=1001,
        name="Test Bus",
        base_kv=230.0,
        area=1,
        zone=1,
        owner=1,
    )
    result = ViewResult(
        buses=[bus],
        branches=[],
        substations=[],
        equipment=[],
        meta={"mode": "bus", "truncated": False, "node_count": 1, "edge_count": 0},
    )
    cytoscape_data = view_result_to_cytoscape(result)
    assert len(cytoscape_data["elements"]["nodes"]) == 1
    node = cytoscape_data["elements"]["nodes"][0]
    assert node["data"]["id"] == "bus-1"
    assert node["data"]["kind"] == "bus"
    assert node["data"]["psse_number"] == 1001
    assert node["data"]["name"] == "Test Bus"


def test_view_result_to_cytoscape_with_branches():
    """Test converting view result with branches."""
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
    result = ViewResult(
        buses=[bus1, bus2],
        branches=[branch],
        substations=[],
        equipment=[],
        meta={"mode": "bus", "truncated": False, "node_count": 2, "edge_count": 1},
    )
    cytoscape_data = view_result_to_cytoscape(result)
    assert len(cytoscape_data["elements"]["edges"]) == 1
    edge = cytoscape_data["elements"]["edges"][0]
    assert edge["data"]["id"] == "branch-1"
    assert edge["data"]["kind"] == "branch"
    assert edge["data"]["source"] == "bus-1"
    assert edge["data"]["target"] == "bus-2"

