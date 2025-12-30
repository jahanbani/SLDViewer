"""Layout algorithms for SLD Viewer.

Computes node positions for graph visualization using NetworkX.
"""

from collections import defaultdict

import networkx as nx

from backend.core.graph.models import ViewResult, BusModel, BranchModel


# Layout constants
SCALE = 200  # Scale factor for layout
EQUIPMENT_OFFSET = 60  # Distance from bus to equipment (below)
EQUIPMENT_SPACING = 35  # Horizontal spacing between equipment items
TRANSFORMER_OFFSET = 40  # Distance from bus to transformer


def compute_substation_layout(result: ViewResult) -> dict[str, dict[str, float]]:
    """Compute positions for all nodes using NetworkX layout algorithms.

    Uses Kamada-Kawai layout which minimizes edge crossings better than
    simple heuristics. Falls back to spring layout if KK fails.

    Args:
        result: ViewResult containing buses, branches, equipment, substations

    Returns:
        Dictionary mapping node IDs to {x, y} position dicts
    """
    positions: dict[str, dict[str, float]] = {}

    if not result.buses:
        return positions

    # Build NetworkX graph from buses and branches
    G = nx.Graph()
    for bus in result.buses:
        G.add_node(bus.id)
    for branch in result.branches:
        if branch.from_bus_id in G and branch.to_bus_id in G:
            G.add_edge(branch.from_bus_id, branch.to_bus_id)

    # Find center bus for positioning reference
    adjacency: dict[str, list[str]] = defaultdict(list)
    for branch in result.branches:
        adjacency[branch.from_bus_id].append(branch.to_bus_id)
        adjacency[branch.to_bus_id].append(branch.from_bus_id)
    center_bus_id = _find_center_bus(result, adjacency)

    # Use Kamada-Kawai layout (minimizes edge crossings)
    try:
        nx_positions = nx.kamada_kawai_layout(G, scale=SCALE)
    except Exception:
        # Fallback to spring layout
        nx_positions = nx.spring_layout(G, scale=SCALE, seed=42)

    # Convert NetworkX positions to our format and shift to positive coordinates
    min_x = min(pos[0] for pos in nx_positions.values()) if nx_positions else 0
    min_y = min(pos[1] for pos in nx_positions.values()) if nx_positions else 0

    bus_positions: dict[str, dict[str, float]] = {}
    for bus_id, (x, y) in nx_positions.items():
        bus_positions[bus_id] = {
            "x": (x - min_x) + SCALE / 2,  # Shift to positive, add padding
            "y": (y - min_y) + SCALE / 2,
        }
    positions.update(bus_positions)

    # Position substation groups around their buses
    substation_positions = _position_substations(result, bus_positions)
    positions.update(substation_positions)

    # Position transformers (between their connected buses)
    transformer_positions = _position_transformers(result.branches, bus_positions)
    positions.update(transformer_positions)

    # Position equipment BELOW their parent bus
    equipment_positions = _position_equipment(result, bus_positions)
    positions.update(equipment_positions)

    # Position terminal nodes (along their parent bus)
    terminal_positions = _position_terminals(result, bus_positions)
    positions.update(terminal_positions)

    return positions


def _find_center_bus(result: ViewResult, adjacency: dict[str, list[str]]) -> str:
    """Find the center bus for layout.

    Uses center_bus from metadata if available, otherwise picks
    the most connected bus.
    """
    # Check metadata for center bus numbers
    center_numbers = result.meta.get("center_bus_numbers", [])
    if center_numbers:
        # Find bus with matching psse_number
        for bus in result.buses:
            if bus.psse_number in center_numbers:
                return bus.id

    # Fallback: most connected bus
    if result.buses:
        return max(result.buses, key=lambda b: len(adjacency.get(b.id, []))).id

    return result.buses[0].id if result.buses else ""


def _position_substations(
    result: ViewResult,
    bus_positions: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    """Position substation group nodes at the centroid of their buses."""
    positions: dict[str, dict[str, float]] = {}

    # Group buses by substation
    buses_by_sub: dict[str, list[str]] = defaultdict(list)
    for bus in result.buses:
        if bus.substation_id:
            buses_by_sub[bus.substation_id].append(bus.id)

    for sub_id, bus_ids in buses_by_sub.items():
        if not bus_ids:
            continue

        # Compute centroid of bus positions
        x_sum = sum(bus_positions[bid]["x"] for bid in bus_ids if bid in bus_positions)
        y_sum = sum(bus_positions[bid]["y"] for bid in bus_ids if bid in bus_positions)
        count = len([bid for bid in bus_ids if bid in bus_positions])

        if count > 0:
            positions[sub_id] = {
                "x": x_sum / count,
                "y": y_sum / count - 30,  # Slightly above buses
            }

    return positions


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
    """Position equipment nodes BELOW their parent bus."""
    positions: dict[str, dict[str, float]] = {}

    # Group equipment by bus
    equipment_by_bus: dict[str, list] = defaultdict(list)
    for eq in result.equipment:
        equipment_by_bus[eq.bus_id].append(eq)

    for bus_id, equipment_list in equipment_by_bus.items():
        bus_pos = bus_positions.get(bus_id)
        if not bus_pos:
            continue

        # Spread equipment horizontally BELOW the bus
        num_eq = len(equipment_list)
        total_width = (num_eq - 1) * EQUIPMENT_SPACING if num_eq > 1 else 0
        start_x = bus_pos["x"] - total_width / 2

        for i, eq in enumerate(equipment_list):
            positions[eq.id] = {
                "x": start_x + i * EQUIPMENT_SPACING,
                "y": bus_pos["y"] + EQUIPMENT_OFFSET,  # BELOW bus (positive Y is down)
            }

    return positions


def _position_terminals(
    result: ViewResult,
    bus_positions: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    """Position terminal nodes along their parent bus.

    Terminals are spread vertically along the bus bar to prevent
    lines from overlapping when they go to different destinations.
    """
    positions: dict[str, dict[str, float]] = {}

    # Count terminals per bus from branches
    terminal_count: dict[str, int] = defaultdict(int)
    for branch in result.branches:
        terminal_count[branch.from_bus_id] += 1
        terminal_count[branch.to_bus_id] += 1

    # Generate terminal positions - spread vertically along bus
    terminal_index: dict[str, int] = defaultdict(int)

    for branch in result.branches:
        for bus_id in [branch.from_bus_id, branch.to_bus_id]:
            bus_pos = bus_positions.get(bus_id)
            if not bus_pos:
                continue

            term_id = f"{bus_id}_term_{terminal_index[bus_id]}"
            count = terminal_count[bus_id]
            idx = terminal_index[bus_id]

            # Spread terminals vertically along the bus bar
            # Bus bar is ~50px tall, spread terminals within that
            if count <= 1:
                y_offset = 0
            else:
                spread = min(40, (count - 1) * 15)  # Max 40px spread
                y_offset = -spread / 2 + idx * (spread / (count - 1))

            positions[term_id] = {
                "x": bus_pos["x"],
                "y": bus_pos["y"] + y_offset,
            }

            terminal_index[bus_id] += 1

    return positions
