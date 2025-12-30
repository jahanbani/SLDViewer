"""Cytoscape converter for SLD Viewer.

Converts ViewResult to Cytoscape.js-compatible JSON format.
Includes buses, branches, equipment nodes, and equipment_link edges.

Terminal nodes are created for each bus connection point, allowing
edges to connect at distributed points along the bus bar.
"""

from collections import defaultdict
from typing import Any

from backend.core.graph.models import ViewResult
from backend.core.graph.layouts import compute_substation_layout


def _count_bus_connections(result: ViewResult) -> dict[str, int]:
    """Count the number of connections each bus has.

    Counts branches (excluding equipment links) to determine
    how many terminal nodes each bus needs.
    """
    connection_count: dict[str, int] = defaultdict(int)

    for branch in result.branches:
        connection_count[branch.from_bus_id] += 1
        connection_count[branch.to_bus_id] += 1

    return dict(connection_count)


def view_result_to_cytoscape(result: ViewResult) -> dict[str, Any]:
    """Convert a ViewResult to Cytoscape.js-compatible JSON format.

    Transforms buses, branches, and equipment into Cytoscape nodes and edges.

    Args:
        result: ViewResult containing buses, branches, equipment, and metadata

    Returns:
        Dictionary with "elements" (nodes and edges) and "meta" keys,
        suitable for JSON serialization and Cytoscape.js consumption
    """
    # Compute positions using substation-based layout
    positions = compute_substation_layout(result)

    # In BUS mode, add substation nodes as compound parents (invisible containers)
    # This makes buses in the same substation cluster together in the layout
    view_mode = result.meta.get("mode", "bus")
    substation_ids_in_view = set()

    if view_mode == "bus":
        # Collect substation IDs that have buses in this view
        for bus in result.buses:
            if bus.substation_id:
                substation_ids_in_view.add(bus.substation_id)

    # Count connections per bus for terminal node creation
    bus_connections = _count_bus_connections(result)

    # Track terminal assignment: bus_id -> list of terminal IDs
    # and next available terminal index per bus
    bus_terminal_ids: dict[str, list[str]] = {}
    bus_terminal_next: dict[str, int] = defaultdict(int)

    # Convert buses to nodes
    nodes = []

    # First, add substation compound nodes (parents) in BUS mode
    if view_mode == "bus":
        for sub in result.substations:
            if sub.id in substation_ids_in_view:
                node_data: dict[str, Any] = {
                    "data": {
                        "id": sub.id,
                        "kind": "substation_group",  # Invisible compound parent
                        "name": sub.name,
                    }
                }
                # Add position if available
                if sub.id in positions:
                    node_data["position"] = positions[sub.id]
                nodes.append(node_data)

    # Build bus_id to substation_id lookup for assigning parents to transformers/equipment
    bus_to_substation = {}
    for bus in result.buses:
        if bus.substation_id:
            bus_to_substation[bus.id] = bus.substation_id

    # Add bus nodes with parent reference for compound grouping
    for bus in result.buses:
        bus_data = {
            "id": bus.id,
            "kind": "bus",
            "psse_number": bus.psse_number,
            "name": bus.name,
            "base_kv": bus.base_kv,
            "substation_id": bus.substation_id,
            "area": bus.area,
            "zone": bus.zone,
            "vm": bus.vm,
            "va": bus.va,
            "vmax": bus.vmax,
            "vmin": bus.vmin,
            "owner": bus.owner,
        }
        
        # In BUS mode, set parent to substation for compound grouping
        if view_mode == "bus" and bus.substation_id and bus.substation_id in substation_ids_in_view:
            bus_data["parent"] = bus.substation_id

        # Add connection count for dynamic bus sizing
        bus_data["connection_count"] = bus_connections.get(bus.id, 0)

        bus_node: dict[str, Any] = {"data": bus_data}
        # Add position if available
        if bus.id in positions:
            bus_node["position"] = positions[bus.id]
        nodes.append(bus_node)

        # Create terminal nodes for this bus (one per connection)
        num_terminals = bus_connections.get(bus.id, 0)
        terminal_ids = []
        for i in range(num_terminals):
            terminal_id = f"{bus.id}_term_{i}"
            terminal_ids.append(terminal_id)

            terminal_data = {
                "id": terminal_id,
                "kind": "terminal",
                "bus_id": bus.id,
                "terminal_index": i,
                "terminal_count": num_terminals,
            }

            # Terminals belong to same substation as their bus
            if view_mode == "bus" and bus.substation_id and bus.substation_id in substation_ids_in_view:
                terminal_data["parent"] = bus.substation_id

            terminal_node: dict[str, Any] = {"data": terminal_data}
            # Add position if available
            if terminal_id in positions:
                terminal_node["position"] = positions[terminal_id]
            nodes.append(terminal_node)

        bus_terminal_ids[bus.id] = terminal_ids

    # Helper function to get next terminal for a bus
    def get_next_terminal(bus_id: str) -> str:
        """Get the next available terminal ID for a bus."""
        terminals = bus_terminal_ids.get(bus_id, [])
        if not terminals:
            # No terminals - connect directly to bus (fallback)
            return bus_id
        idx = bus_terminal_next[bus_id]
        bus_terminal_next[bus_id] = (idx + 1) % len(terminals)
        return terminals[idx]

    # Convert branches to edges (lines) or nodes+edges (transformers)
    edges = []
    for branch in result.branches:
        # Common branch data dict
        branch_data = {
            "id": branch.id,
            "kind": "branch",
            "type": branch.type,
            "circuit": branch.circuit,
            "r": branch.r,
            "x": branch.x,
            "b": branch.b,
            "g": branch.g,
            "r0": branch.r0,
            "x0": branch.x0,
            "b0": branch.b0,
            "rate_a": branch.rate_a,
            "rate_b": branch.rate_b,
            "rate_c": branch.rate_c,
            "rating_mva": branch.rating_mva,
            "tap_module": branch.tap_module,
            "tap_phase": branch.tap_phase,
            "length": branch.length,
            "p_from_mw": branch.p_from_mw,
            "q_from_mvar": branch.q_from_mvar,
            "p_to_mw": branch.p_to_mw,
            "q_to_mvar": branch.q_to_mvar,
            "from_bus_id": branch.from_bus_id,
            "to_bus_id": branch.to_bus_id,
        }

        # Transformers become nodes with two connecting edges
        if branch.type in ("xfmr", "xfmr3"):
            # Determine transformer's parent substation (use from_bus's substation)
            # This ensures transformer node is grouped with its connected buses
            transformer_parent = None
            if view_mode == "bus":
                from_sub = bus_to_substation.get(branch.from_bus_id)
                to_sub = bus_to_substation.get(branch.to_bus_id)
                # Use from_bus's substation, or to_bus's if from is not in view
                transformer_parent = from_sub if from_sub in substation_ids_in_view else (
                    to_sub if to_sub in substation_ids_in_view else None
                )

            # Build transformer node data
            transformer_data = {
                **branch_data,
                "kind": "transformer",  # Override kind for node
                "name": f"T {branch.circuit}",
            }
            if transformer_parent:
                transformer_data["parent"] = transformer_parent

            # Add transformer as a node
            transformer_node: dict[str, Any] = {"data": transformer_data}
            # Add position if available
            if branch.id in positions:
                transformer_node["position"] = positions[branch.id]
            nodes.append(transformer_node)

            # Get terminals for from_bus and to_bus
            from_terminal = get_next_terminal(branch.from_bus_id)
            to_terminal = get_next_terminal(branch.to_bus_id)

            # Edge from terminal to transformer
            edges.append(
                {
                    "data": {
                        "id": f"xfmr-from-{branch.id}",
                        "kind": "transformer_link",
                        "source": from_terminal,
                        "target": branch.id,
                        "from_bus_id": branch.from_bus_id,  # Keep reference to original bus
                    }
                }
            )
            # Edge from transformer to terminal
            edges.append(
                {
                    "data": {
                        "id": f"xfmr-to-{branch.id}",
                        "kind": "transformer_link",
                        "source": branch.id,
                        "target": to_terminal,
                        "to_bus_id": branch.to_bus_id,  # Keep reference to original bus
                    }
                }
            )
        else:
            # Lines and other branch types - connect to terminals
            from_terminal = get_next_terminal(branch.from_bus_id)
            to_terminal = get_next_terminal(branch.to_bus_id)

            edges.append(
                {
                    "data": {
                        **branch_data,
                        "source": from_terminal,
                        "target": to_terminal,
                    }
                }
            )

    # Convert equipment to nodes
    for eq in result.equipment:
        equipment_data = {
            "id": eq.id,
            "kind": "equipment",
            "equipment_type": eq.type.value,  # e.g. "generator", "load", "shunt"
            "bus_id": eq.bus_id,
            "name": eq.name,
            "status": eq.status,
            "p_mw": eq.p_mw,
            "q_mvar": eq.q_mvar,
            "metadata": eq.metadata,
        }
        
        # Assign equipment to same substation as its bus
        if view_mode == "bus":
            eq_sub = bus_to_substation.get(eq.bus_id)
            if eq_sub and eq_sub in substation_ids_in_view:
                equipment_data["parent"] = eq_sub

        equipment_node: dict[str, Any] = {"data": equipment_data}
        # Add position if available
        if eq.id in positions:
            equipment_node["position"] = positions[eq.id]
        nodes.append(equipment_node)
        # Add equipment_link edge from bus to equipment
        edges.append(
            {
                "data": {
                    "id": f"eqlink-{eq.id}",
                    "kind": "equipment_link",
                    "source": eq.bus_id,
                    "target": eq.id,
                    "status": eq.status,  # For styling: solid if in-service, dashed if out
                }
            }
        )

    # Only add substation nodes in SUBSTATION or STATION_DETAIL mode
    view_mode = result.meta.get("mode")

    if view_mode in ("substation", "station_detail"):
        for idx, sub in enumerate(result.substations):
            # First substation in station_detail mode is the center, rest are neighbors
            is_neighbor_stub = view_mode == "station_detail" and idx > 0

            nodes.append(
                {
                    "data": {
                        "id": sub.id,
                        "kind": "neighbor_substation_stub" if is_neighbor_stub else "substation",
                        "name": sub.name,
                        "area": sub.area,
                        "zone": sub.zone,
                        "nominal_kv": sub.nominal_kv,
                        "voltage_levels": sub.voltage_levels,
                        "latitude": sub.latitude,
                        "longitude": sub.longitude,
                    }
                }
            )

    # For substation mode, remap branch endpoints to substation IDs
    if view_mode == "substation" and not result.buses:
        # In substation mode, branches connect substations, not buses
        # Get the bus_to_substation_id mapping from metadata
        bus_to_sub = result.meta.get("bus_to_substation_id", {})

        # Remap edges to connect substations instead of buses
        new_edges = []
        for edge in edges:  # Use existing edges from branches
            # Get the original bus IDs
            source_bus_id = edge["data"]["source"]
            target_bus_id = edge["data"]["target"]

            # Remap to substation IDs
            source_sub_id = bus_to_sub.get(source_bus_id)
            target_sub_id = bus_to_sub.get(target_bus_id)

            # Only include edge if both endpoints map to substations
            if source_sub_id and target_sub_id:
                edge_data = edge["data"].copy()
                edge_data["source"] = source_sub_id
                edge_data["target"] = target_sub_id
                new_edges.append({"data": edge_data})

        edges = new_edges

    return {
        "elements": {
            "nodes": nodes,
            "edges": edges,
        },
        "meta": result.meta,
    }

