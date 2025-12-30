"""Layout algorithms for SLD Viewer.

Computes node positions for graph visualization.
"""

from collections import defaultdict
from typing import Any

from backend.core.graph.models import ViewResult, BusModel, BranchModel


# Layout constants
SUBSTATION_SPACING = 300  # Horizontal spacing between substations
BUS_SPACING = 80  # Vertical spacing between buses within a substation
EQUIPMENT_OFFSET = 50  # Distance from bus to equipment
TRANSFORMER_OFFSET = 40  # Distance from bus to transformer


def compute_substation_layout(result: ViewResult) -> dict[str, dict[str, float]]:
    """Compute positions for all nodes using substation-based layout.

    Layout strategy:
    1. Group buses by substation
    2. Arrange substations horizontally (left to right)
    3. Stack buses vertically within each substation
    4. Position transformers between their connected buses
    5. Position equipment offset from their parent bus

    Args:
        result: ViewResult containing buses, branches, equipment, substations

    Returns:
        Dictionary mapping node IDs to {x, y} position dicts
    """
    positions: dict[str, dict[str, float]] = {}

    # Group buses by substation
    buses_by_substation: dict[str | None, list[BusModel]] = defaultdict(list)
    for bus in result.buses:
        buses_by_substation[bus.substation_id].append(bus)

    # Sort buses within each substation by voltage (highest first)
    for sub_id in buses_by_substation:
        buses_by_substation[sub_id].sort(key=lambda b: -b.base_kv)

    # Get ordered list of substations (by number of buses, then name)
    substation_order = _order_substations(result, buses_by_substation)

    # Position substations and their buses
    current_x = 0
    substation_positions: dict[str | None, dict[str, float]] = {}
    bus_positions: dict[str, dict[str, float]] = {}

    for sub_id in substation_order:
        buses = buses_by_substation.get(sub_id, [])
        if not buses:
            continue

        # Calculate substation width based on number of buses
        sub_height = len(buses) * BUS_SPACING
        sub_center_y = sub_height / 2

        # Position substation group node
        if sub_id:
            substation_positions[sub_id] = {
                "x": current_x + SUBSTATION_SPACING / 2,
                "y": sub_center_y,
            }
            positions[sub_id] = substation_positions[sub_id]

        # Position buses within substation (stacked vertically)
        for i, bus in enumerate(buses):
            bus_y = i * BUS_SPACING + BUS_SPACING / 2
            bus_positions[bus.id] = {
                "x": current_x + SUBSTATION_SPACING / 2,
                "y": bus_y,
            }
            positions[bus.id] = bus_positions[bus.id]

        current_x += SUBSTATION_SPACING

    # Handle buses without substation (place them at the end)
    orphan_buses = buses_by_substation.get(None, [])
    for i, bus in enumerate(orphan_buses):
        bus_positions[bus.id] = {
            "x": current_x + SUBSTATION_SPACING / 2,
            "y": i * BUS_SPACING + BUS_SPACING / 2,
        }
        positions[bus.id] = bus_positions[bus.id]

    # Position transformers (between their connected buses)
    transformer_positions = _position_transformers(result.branches, bus_positions)
    positions.update(transformer_positions)

    # Position equipment (offset from their parent bus)
    equipment_positions = _position_equipment(result, bus_positions)
    positions.update(equipment_positions)

    # Position terminal nodes (along their parent bus)
    terminal_positions = _position_terminals(result, bus_positions)
    positions.update(terminal_positions)

    return positions


def _order_substations(
    result: ViewResult,
    buses_by_substation: dict[str | None, list[BusModel]],
) -> list[str | None]:
    """Determine the order of substations for layout.

    Uses a simple heuristic: order by connectivity (most connected first),
    then by name alphabetically.
    """
    # Count connections between substations
    substation_connections: dict[str | None, int] = defaultdict(int)
    bus_to_sub: dict[str, str | None] = {b.id: b.substation_id for b in result.buses}

    for branch in result.branches:
        from_sub = bus_to_sub.get(branch.from_bus_id)
        to_sub = bus_to_sub.get(branch.to_bus_id)
        if from_sub != to_sub:  # Inter-substation connection
            substation_connections[from_sub] += 1
            substation_connections[to_sub] += 1

    # Get substation names for sorting
    sub_names: dict[str | None, str] = {None: "zzz_orphan"}
    for sub in result.substations:
        sub_names[sub.id] = sub.name

    # Sort: most connected first, then alphabetically
    sub_ids = list(buses_by_substation.keys())
    sub_ids.sort(key=lambda s: (-substation_connections.get(s, 0), sub_names.get(s, "")))

    # Remove None (orphans) from main list - they go at end
    if None in sub_ids:
        sub_ids.remove(None)

    return sub_ids


def _position_transformers(
    branches: list[BranchModel],
    bus_positions: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    """Position transformer nodes between their connected buses."""
    positions: dict[str, dict[str, float]] = {}

    for branch in branches:
        if branch.type not in ("xfmr", "xfmr3"):
            continue

        from_pos = bus_positions.get(branch.from_bus_id)
        to_pos = bus_positions.get(branch.to_bus_id)

        if from_pos and to_pos:
            # Position transformer midway between the two buses
            positions[branch.id] = {
                "x": (from_pos["x"] + to_pos["x"]) / 2,
                "y": (from_pos["y"] + to_pos["y"]) / 2,
            }
        elif from_pos:
            # Only from_bus in view - offset from it
            positions[branch.id] = {
                "x": from_pos["x"] + TRANSFORMER_OFFSET,
                "y": from_pos["y"],
            }
        elif to_pos:
            # Only to_bus in view - offset from it
            positions[branch.id] = {
                "x": to_pos["x"] - TRANSFORMER_OFFSET,
                "y": to_pos["y"],
            }

    return positions


def _position_equipment(
    result: ViewResult,
    bus_positions: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    """Position equipment nodes offset from their parent bus."""
    positions: dict[str, dict[str, float]] = {}

    # Group equipment by bus
    equipment_by_bus: dict[str, list] = defaultdict(list)
    for eq in result.equipment:
        equipment_by_bus[eq.bus_id].append(eq)

    for bus_id, equipment_list in equipment_by_bus.items():
        bus_pos = bus_positions.get(bus_id)
        if not bus_pos:
            continue

        # Spread equipment horizontally below the bus
        num_eq = len(equipment_list)
        total_width = (num_eq - 1) * 30 if num_eq > 1 else 0
        start_x = bus_pos["x"] - total_width / 2

        for i, eq in enumerate(equipment_list):
            positions[eq.id] = {
                "x": start_x + i * 30,
                "y": bus_pos["y"] + EQUIPMENT_OFFSET,
            }

    return positions


def _position_terminals(
    result: ViewResult,
    bus_positions: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    """Position terminal nodes along their parent bus.

    Note: Terminal positions are computed on frontend based on edge directions.
    This provides default positions that can be overridden.
    """
    positions: dict[str, dict[str, float]] = {}

    # Count terminals per bus from branches
    terminal_count: dict[str, int] = defaultdict(int)
    for branch in result.branches:
        terminal_count[branch.from_bus_id] += 1
        terminal_count[branch.to_bus_id] += 1

    # Generate terminal positions
    terminal_index: dict[str, int] = defaultdict(int)

    for branch in result.branches:
        for bus_id in [branch.from_bus_id, branch.to_bus_id]:
            bus_pos = bus_positions.get(bus_id)
            if not bus_pos:
                continue

            term_id = f"{bus_id}_term_{terminal_index[bus_id]}"
            count = terminal_count[bus_id]

            # Spread terminals vertically along the bus
            spread = min(count - 1, 4) * 10  # Max spread of 40px
            offset = -spread / 2 + terminal_index[bus_id] * (spread / max(count - 1, 1))

            positions[term_id] = {
                "x": bus_pos["x"],
                "y": bus_pos["y"] + offset,
            }

            terminal_index[bus_id] += 1

    return positions
