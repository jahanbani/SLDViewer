"""Layout algorithms for SLD Viewer.

Computes node positions for graph visualization using a hierarchical
layered layout that creates clean routing channels for orthogonal edges.
"""

from collections import defaultdict, deque

from backend.core.graph.models import ViewResult, BusModel, BranchModel


# Layout constants
LAYER_SPACING = 200  # Vertical spacing between layers
NODE_SPACING = 180   # Horizontal spacing between nodes in a layer
STAGGER_OFFSET = 60  # Horizontal offset for staggering to avoid vertical alignment
EQUIPMENT_OFFSET = 60  # Distance from bus to equipment
EQUIPMENT_SPACING = 35  # Horizontal spacing between equipment items
TRANSFORMER_OFFSET = 40  # Distance from bus to transformer


def compute_substation_layout(result: ViewResult) -> dict[str, dict[str, float]]:
    """Compute positions for all nodes using hierarchical layered layout.

    Uses BFS from center bus to assign layers, then positions nodes
    within each layer with staggering to prevent vertical alignment.
    This creates natural routing channels for orthogonal (taxi) edges.

    Args:
        result: ViewResult containing buses, branches, equipment, substations

    Returns:
        Dictionary mapping node IDs to {x, y} position dicts
    """
    positions: dict[str, dict[str, float]] = {}

    if not result.buses:
        return positions

    # Build adjacency from branches
    adjacency: dict[str, list[str]] = defaultdict(list)
    for branch in result.branches:
        adjacency[branch.from_bus_id].append(branch.to_bus_id)
        adjacency[branch.to_bus_id].append(branch.from_bus_id)

    # Find center bus
    center_bus_id = _find_center_bus(result, adjacency)

    # Assign layers using BFS from center
    bus_ids = {bus.id for bus in result.buses}
    layers = _assign_layers_bfs(center_bus_id, adjacency, bus_ids)

    # Position buses using hierarchical layout with staggering
    bus_positions = _position_buses_hierarchical(layers, adjacency)
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


def _assign_layers_bfs(
    center_id: str,
    adjacency: dict[str, list[str]],
    node_ids: set[str],
) -> dict[int, list[str]]:
    """Assign nodes to layers using BFS from center.

    Layer 0 = center node
    Layer 1 = immediate neighbors
    Layer 2 = neighbors of neighbors
    etc.

    Returns:
        Dict mapping layer number to list of node IDs in that layer
    """
    layers: dict[int, list[str]] = defaultdict(list)
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque()

    # Start from center
    if center_id in node_ids:
        queue.append((center_id, 0))
        visited.add(center_id)

    while queue:
        node_id, layer = queue.popleft()
        layers[layer].append(node_id)

        for neighbor_id in adjacency.get(node_id, []):
            if neighbor_id not in visited and neighbor_id in node_ids:
                visited.add(neighbor_id)
                queue.append((neighbor_id, layer + 1))

    # Add any disconnected nodes to layer 0
    for node_id in node_ids:
        if node_id not in visited:
            layers[0].append(node_id)

    return dict(layers)


def _position_buses_hierarchical(
    layers: dict[int, list[str]],
    adjacency: dict[str, list[str]],
) -> dict[str, dict[str, float]]:
    """Position buses in a hierarchical layout with staggering.

    - Layer 0 (center) is in the middle vertically
    - Layers alternate above and below the center
    - Nodes within a layer are spread horizontally
    - Staggering prevents vertical alignment between adjacent layers

    Returns:
        Dict mapping bus ID to {x, y} position
    """
    positions: dict[str, dict[str, float]] = {}

    if not layers:
        return positions

    # Sort layer numbers
    sorted_layers = sorted(layers.keys())
    max_layer = max(sorted_layers) if sorted_layers else 0

    # Calculate base Y position for each layer
    # Layer 0 at center, odd layers below, even layers above (alternating)
    layer_y: dict[int, float] = {}
    center_y = (max_layer + 1) * LAYER_SPACING / 2

    for layer_num in sorted_layers:
        if layer_num == 0:
            layer_y[layer_num] = center_y
        elif layer_num % 2 == 1:
            # Odd layers go below: 1, 3, 5...
            layer_y[layer_num] = center_y + ((layer_num + 1) // 2) * LAYER_SPACING
        else:
            # Even layers go above: 2, 4, 6...
            layer_y[layer_num] = center_y - (layer_num // 2) * LAYER_SPACING

    # Position nodes within each layer
    for layer_num, node_ids in layers.items():
        num_nodes = len(node_ids)
        if num_nodes == 0:
            continue

        # Calculate total width for this layer
        total_width = (num_nodes - 1) * NODE_SPACING
        start_x = -total_width / 2

        # Apply stagger offset for non-zero layers to avoid vertical alignment
        stagger = STAGGER_OFFSET if layer_num % 2 == 1 else 0

        for i, node_id in enumerate(node_ids):
            x = start_x + i * NODE_SPACING + stagger
            y = layer_y[layer_num]
            positions[node_id] = {"x": x, "y": y}

    # Shift all positions to be positive with padding
    if positions:
        min_x = min(p["x"] for p in positions.values())
        min_y = min(p["y"] for p in positions.values())
        for pos in positions.values():
            pos["x"] = pos["x"] - min_x + 100  # Add padding
            pos["y"] = pos["y"] - min_y + 100

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
