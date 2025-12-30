"""Layout algorithms for SLD Viewer.

Computes node positions for graph visualization.
"""

from collections import defaultdict

from backend.core.graph.models import ViewResult, BusModel, BranchModel


# Layout constants
BUS_SPACING = 200  # Horizontal spacing between buses
EQUIPMENT_OFFSET = 60  # Distance from bus to equipment (below)
EQUIPMENT_SPACING = 35  # Horizontal spacing between equipment items
TRANSFORMER_OFFSET = 40  # Distance from bus to transformer
BUS_Y = 100  # Y position for all buses (same horizontal line)


def compute_substation_layout(result: ViewResult) -> dict[str, dict[str, float]]:
    """Compute positions for all nodes using horizontal bus layout.

    Layout strategy:
    1. Place center bus in the middle
    2. Spread connected buses left and right using BFS
    3. All buses on the SAME horizontal line
    4. Equipment positioned BELOW their parent bus
    5. Transformers between connected buses

    Args:
        result: ViewResult containing buses, branches, equipment, substations

    Returns:
        Dictionary mapping node IDs to {x, y} position dicts
    """
    positions: dict[str, dict[str, float]] = {}

    if not result.buses:
        return positions

    # Build adjacency list for BFS ordering
    adjacency: dict[str, list[str]] = defaultdict(list)
    for branch in result.branches:
        adjacency[branch.from_bus_id].append(branch.to_bus_id)
        adjacency[branch.to_bus_id].append(branch.from_bus_id)

    # Find center bus (from metadata or most connected)
    center_bus_id = _find_center_bus(result, adjacency)

    # BFS to order buses by distance from center
    bus_order = _bfs_order_buses(center_bus_id, adjacency, result.buses)

    # Position buses on horizontal line, center bus in middle
    bus_positions = _position_buses_horizontal(bus_order, center_bus_id)
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


def _bfs_order_buses(
    center_id: str,
    adjacency: dict[str, list[str]],
    buses: list[BusModel],
) -> list[str]:
    """Order buses using BFS from center, alternating left/right."""
    bus_ids = {b.id for b in buses}
    visited = set()
    order = []

    # BFS from center
    queue = [center_id] if center_id in bus_ids else []
    while queue:
        bus_id = queue.pop(0)
        if bus_id in visited or bus_id not in bus_ids:
            continue
        visited.add(bus_id)
        order.append(bus_id)

        # Add neighbors
        for neighbor in adjacency.get(bus_id, []):
            if neighbor not in visited and neighbor in bus_ids:
                queue.append(neighbor)

    # Add any disconnected buses
    for bus in buses:
        if bus.id not in visited:
            order.append(bus.id)

    return order


def _position_buses_horizontal(
    bus_order: list[str],
    center_id: str,
) -> dict[str, dict[str, float]]:
    """Position buses on a horizontal line, center bus in middle."""
    positions: dict[str, dict[str, float]] = {}

    if not bus_order:
        return positions

    # Find center index
    try:
        center_idx = bus_order.index(center_id)
    except ValueError:
        center_idx = 0

    # Position center at x=0
    center_x = len(bus_order) * BUS_SPACING / 2

    # Assign positions: center bus first, then alternate left/right
    left_buses = bus_order[:center_idx]
    right_buses = bus_order[center_idx + 1:]

    # Center bus
    positions[center_id] = {"x": center_x, "y": BUS_Y}

    # Buses to the left of center
    for i, bus_id in enumerate(reversed(left_buses)):
        positions[bus_id] = {
            "x": center_x - (i + 1) * BUS_SPACING,
            "y": BUS_Y,
        }

    # Buses to the right of center
    for i, bus_id in enumerate(right_buses):
        positions[bus_id] = {
            "x": center_x + (i + 1) * BUS_SPACING,
            "y": BUS_Y,
        }

    return positions


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

    Terminals are positioned on the bus bar itself (same Y as bus).
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

            # Terminal at same position as bus (will be refined by frontend)
            positions[term_id] = {
                "x": bus_pos["x"],
                "y": bus_pos["y"],
            }

            terminal_index[bus_id] += 1

    return positions
