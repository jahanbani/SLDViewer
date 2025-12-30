"""View engine for SLD Viewer.

Generates partial graph views based on ViewSpec.
Supports BUS, SUBSTATION, and STATION_DETAIL modes.
Pure logic: no Cytoscape-specific fields or styling.
"""

from collections import deque
from itertools import chain

from backend.core.config import Settings
from backend.core.graph.graph_builder import GraphHandle
from backend.core.graph.models import (
    ViewMode,
    ViewResult,
    ViewSpec,
)


class UnsupportedViewModeError(Exception):
    """Raised when a view mode is requested that is not yet implemented."""

    pass


def view(graph: GraphHandle, spec: ViewSpec, settings: Settings) -> ViewResult:
    """Generate a view result from a graph handle and view specification.

    Supports three view modes:
    - BUS: Bus-level view with BFS from center buses
    - SUBSTATION: Substation-level overview with BFS from center substations
    - STATION_DETAIL: Detailed view of one substation with all internal buses

    Args:
        graph: GraphHandle containing graphs and lookup dictionaries
        spec: ViewSpec defining the view parameters
        settings: Application settings for default limits

    Returns:
        ViewResult containing buses, branches, substations, equipment, and metadata

    Raises:
        UnsupportedViewModeError: If mode requires substations but none are available
        ValueError: If center points reference non-existent entities
    """
    if spec.mode == ViewMode.BUS:
        return _view_bus_mode(graph, spec, settings)
    elif spec.mode == ViewMode.SUBSTATION:
        return _view_substation_mode(graph, spec, settings)
    elif spec.mode == ViewMode.STATION_DETAIL:
        return _view_station_detail_mode(graph, spec, settings)
    else:
        raise UnsupportedViewModeError(f"Unknown view mode: {spec.mode}")

def _view_bus_mode(graph: GraphHandle, spec: ViewSpec, settings: Settings) -> ViewResult:
    """Generate a bus-level view with BFS from center buses."""
    # Determine seed buses
    seed_bus_ids = _get_seed_bus_ids(graph, spec)

    # Determine node limit
    if not spec.center_bus_numbers:
        # Initial view with no center: use initial_view_limit
        node_limit = settings.initial_view_limit
    else:
        # Use spec.limit if provided, else default
        node_limit = spec.limit if spec.limit is not None else settings.bus_limit_default

    # Run BFS to collect bus IDs
    visited_bus_ids = _bfs_with_limit(
        graph.bus_graph, seed_bus_ids, spec.degrees, node_limit
    )

    # Determine if we hit the limit (truncated)
    truncated = len(visited_bus_ids) >= node_limit

    # Collect buses
    buses = [graph.bus_by_id[bus_id] for bus_id in visited_bus_ids]

    # Collect branches where both endpoints are in the view
    branches = [
        branch
        for branch in graph.branch_by_id.values()
        if branch.from_bus_id in visited_bus_ids
        and branch.to_bus_id in visited_bus_ids
    ]

    # Collect equipment for all buses in the view (if include_equipment is true)
    equipment = []
    if spec.filters.include_equipment:
        allowed_types = spec.filters.equipment_types  # None means all types
        for bus_id in visited_bus_ids:
            bus_equipment = graph.equipment_by_bus_id.get(bus_id, [])
            for eq in bus_equipment:
                # Filter by equipment type if specified
                if allowed_types is None or eq.type in allowed_types:
                    equipment.append(eq)

    # Collect substations for buses in the view
    substation_ids = set()
    for bus in buses:
        if bus.substation_id:
            substation_ids.add(bus.substation_id)
    substations = [graph.substation_by_id[sid] for sid in substation_ids if sid in graph.substation_by_id]

    # Build metadata
    meta = {
        "mode": spec.mode.value,
        "truncated": truncated,
        "node_count": len(buses),
        "edge_count": len(branches),
        "equipment_count": len(equipment),
        "substation_count": len(substations),
        "degrees": spec.degrees,
        "limit": node_limit,
        "center_bus_numbers": spec.center_bus_numbers or [],  # For layout algorithm
    }

    return ViewResult(
        buses=buses,
        branches=branches,
        substations=substations,
        equipment=equipment,
        meta=meta,
    )


def _view_substation_mode(graph: GraphHandle, spec: ViewSpec, settings: Settings) -> ViewResult:
    """Generate a substation-level overview with BFS from center substations.
    
    In this mode, we show substations as nodes and inter-substation branches as edges.
    Equipment is not shown (to keep the overview clean).
    """
    if not graph.substation_graph or not graph.substation_by_id:
        raise UnsupportedViewModeError(
            "SUBSTATION mode requires substations. No substations detected in this file."
        )

    # Determine seed substations
    seed_sub_ids = _get_seed_substation_ids(graph, spec)

    # Determine node limit
    node_limit = spec.limit if spec.limit is not None else settings.substation_limit_default

    # Run BFS on substation graph
    visited_sub_ids = _bfs_with_limit(
        graph.substation_graph, seed_sub_ids, spec.degrees, node_limit
    )

    # Determine if we hit the limit (truncated)
    truncated = len(visited_sub_ids) >= node_limit

    # Collect substations
    substations = [graph.substation_by_id[sub_id] for sub_id in visited_sub_ids]

    # Collect inter-substation branches (branches between visited substations)
    # We need to map branch IDs to the branches
    branches = []
    seen_branch_ids = set()
    for branch in graph.branch_by_id.values():
        from_bus = graph.bus_by_id.get(branch.from_bus_id)
        to_bus = graph.bus_by_id.get(branch.to_bus_id)
        if from_bus and to_bus:
            from_sub = from_bus.substation_id
            to_sub = to_bus.substation_id
            # Include if it connects two visited substations
            if from_sub in visited_sub_ids and to_sub in visited_sub_ids:
                if branch.id not in seen_branch_ids:
                    branches.append(branch)
                    seen_branch_ids.add(branch.id)

    # In substation mode, we don't include individual buses or equipment
    # But we provide aggregated info in metadata
    total_buses = sum(len(graph.buses_by_substation_id.get(sid, [])) for sid in visited_sub_ids)

    # Build bus_id -> substation_id mapping for the converter
    # This allows edges to be remapped from bus endpoints to substation endpoints
    bus_to_substation_id = {}
    for bus in graph.bus_by_id.values():
        if bus.substation_id:
            bus_to_substation_id[bus.id] = bus.substation_id

    meta = {
        "mode": spec.mode.value,
        "truncated": truncated,
        "node_count": len(substations),
        "edge_count": len(branches),
        "equipment_count": 0,  # Not shown in this mode
        "substation_count": len(substations),
        "total_buses_in_view": total_buses,
        "degrees": spec.degrees,
        "limit": node_limit,
        "bus_to_substation_id": bus_to_substation_id,  # For edge remapping in converter
    }

    return ViewResult(
        buses=[],  # Not shown in substation mode
        branches=branches,
        substations=substations,
        equipment=[],  # Not shown in substation mode
        meta=meta,
    )


def _view_station_detail_mode(graph: GraphHandle, spec: ViewSpec, settings: Settings) -> ViewResult:
    """Generate a detailed view of a single substation.
    
    Shows all buses within the substation, internal branches, and equipment.
    Also shows stub nodes for neighboring substations (branches going out).
    """
    if not graph.substation_by_id:
        raise UnsupportedViewModeError(
            "STATION_DETAIL mode requires substations. No substations detected in this file."
        )

    # Get the center substation (exactly one required)
    if not spec.center_substation_ids or len(spec.center_substation_ids) != 1:
        # Try to get substation from center_bus_numbers
        if spec.center_bus_numbers and len(spec.center_bus_numbers) == 1:
            psse_to_bus = {bus.psse_number: bus for bus in graph.bus_by_id.values()}
            center_bus = psse_to_bus.get(spec.center_bus_numbers[0])
            if center_bus and center_bus.substation_id:
                center_sub_id = center_bus.substation_id
            else:
                raise ValueError(
                    "STATION_DETAIL mode requires center_substation_ids with exactly one substation, "
                    "or a center_bus_numbers that belongs to a substation."
                )
        else:
            raise ValueError(
                "STATION_DETAIL mode requires center_substation_ids with exactly one substation."
            )
    else:
        center_sub_id = spec.center_substation_ids[0]

    if center_sub_id not in graph.substation_by_id:
        raise ValueError(f"Substation {center_sub_id} not found in graph")

    center_substation = graph.substation_by_id[center_sub_id]

    # Get all buses in this substation
    buses_in_substation = graph.buses_by_substation_id.get(center_sub_id, [])
    bus_ids_in_substation = {bus.id for bus in buses_in_substation}

    # Collect internal branches (both endpoints in substation)
    internal_branches = []
    # Also collect external branches and track neighbor substations
    neighbor_substation_ids = set()
    external_branches = []
    
    for branch in graph.branch_by_id.values():
        from_in = branch.from_bus_id in bus_ids_in_substation
        to_in = branch.to_bus_id in bus_ids_in_substation
        
        if from_in and to_in:
            # Internal branch
            internal_branches.append(branch)
        elif from_in or to_in:
            # External branch - one end in, one end out
            external_branches.append(branch)
            # Find neighbor substation
            external_bus_id = branch.to_bus_id if from_in else branch.from_bus_id
            external_bus = graph.bus_by_id.get(external_bus_id)
            if external_bus and external_bus.substation_id:
                neighbor_substation_ids.add(external_bus.substation_id)

    # Collect equipment for buses in the substation
    equipment = []
    if spec.filters.include_equipment:
        allowed_types = spec.filters.equipment_types
        for bus in buses_in_substation:
            bus_equipment = graph.equipment_by_bus_id.get(bus.id, [])
            for eq in bus_equipment:
                if allowed_types is None or eq.type in allowed_types:
                    equipment.append(eq)

    # Collect neighbor substations (for stub nodes)
    neighbor_substations = [
        graph.substation_by_id[sid] 
        for sid in neighbor_substation_ids 
        if sid in graph.substation_by_id
    ]

    # All branches to include
    all_branches = internal_branches + external_branches

    meta = {
        "mode": spec.mode.value,
        "truncated": False,  # Station detail is never truncated
        "node_count": len(buses_in_substation),
        "edge_count": len(all_branches),
        "equipment_count": len(equipment),
        "substation_count": 1 + len(neighbor_substations),  # Center + neighbors
        "internal_branches": len(internal_branches),
        "external_branches": len(external_branches),
        "neighbor_substations": len(neighbor_substations),
        "center_substation_id": center_sub_id,
        "center_substation_name": center_substation.name,
    }

    return ViewResult(
        buses=buses_in_substation,
        branches=all_branches,
        substations=[center_substation] + neighbor_substations,
        equipment=equipment,
        meta=meta,
    )


def _get_seed_bus_ids(graph: GraphHandle, spec: ViewSpec) -> list[str]:
    """Determine seed bus IDs from ViewSpec.

    If center_bus_numbers is provided, map PSSE bus numbers to internal IDs.
    Otherwise, return the bus with the smallest psse_number.

    Args:
        graph: GraphHandle with bus lookup
        spec: ViewSpec with center_bus_numbers

    Returns:
        List of bus IDs to use as BFS seeds

    Raises:
        ValueError: If a center_bus_number doesn't exist in the graph
    """
    if spec.center_bus_numbers:
        # Map PSSE bus numbers to internal bus IDs
        psse_to_id = {bus.psse_number: bus.id for bus in graph.bus_by_id.values()}
        seed_ids = []
        for psse_num in spec.center_bus_numbers:
            if psse_num not in psse_to_id:
                raise ValueError(
                    f"Center bus number {psse_num} not found in graph"
                )
            seed_ids.append(psse_to_id[psse_num])
        return seed_ids
    else:
        # Default: bus with smallest psse_number
        if not graph.bus_by_id:
            return []
        default_bus = min(
            graph.bus_by_id.values(), key=lambda bus: bus.psse_number
        )
        return [default_bus.id]


def _get_seed_substation_ids(graph: GraphHandle, spec: ViewSpec) -> list[str]:
    """Determine seed substation IDs from ViewSpec.

    If center_substation_ids is provided, use those.
    Otherwise, try to get from center_bus_numbers or default to first substation.

    Args:
        graph: GraphHandle with substation lookup
        spec: ViewSpec with center_substation_ids or center_bus_numbers

    Returns:
        List of substation IDs to use as BFS seeds

    Raises:
        ValueError: If a center_substation_id doesn't exist in the graph
    """
    if spec.center_substation_ids:
        # Use provided substation IDs directly
        seed_ids = []
        for sub_id in spec.center_substation_ids:
            if sub_id not in graph.substation_by_id:
                raise ValueError(f"Substation {sub_id} not found in graph")
            seed_ids.append(sub_id)
        return seed_ids
    elif spec.center_bus_numbers:
        # Get substations from the center buses
        psse_to_bus = {bus.psse_number: bus for bus in graph.bus_by_id.values()}
        seed_ids = set()
        for psse_num in spec.center_bus_numbers:
            bus = psse_to_bus.get(psse_num)
            if bus and bus.substation_id:
                seed_ids.add(bus.substation_id)
        if seed_ids:
            return list(seed_ids)
        # Fall through to default
    
    # Default: substation with the most buses (typically most "important")
    if not graph.substation_by_id:
        return []
    
    default_sub = max(
        graph.substation_by_id.keys(),
        key=lambda sid: len(graph.buses_by_substation_id.get(sid, []))
    )
    return [default_sub]


def _bfs_with_limit(
    graph, seed_ids: list[str], max_depth: int, node_limit: int
) -> set[str]:
    """Run BFS from seed nodes up to max_depth, stopping at node_limit.

    Args:
        graph: NetworkX graph to traverse
        seed_ids: List of node IDs to start BFS from
        max_depth: Maximum BFS depth (degrees)
        node_limit: Maximum number of nodes to include

    Returns:
        Set of visited node IDs
    """
    if not seed_ids:
        return set()

    visited = set()
    queue = deque()

    # Initialize queue with seed nodes at depth 0
    for seed_id in seed_ids:
        if seed_id in graph:
            visited.add(seed_id)
            queue.append((seed_id, 0))

    # BFS traversal
    while queue and len(visited) < node_limit:
        node_id, depth = queue.popleft()

        # Stop if we've reached max depth
        if depth >= max_depth:
            continue

        # Explore neighbors in BOTH directions (successors and predecessors)
        # This is important because branches can be stored in either direction
        # (e.g., transformer 81->80 should still connect 80 to 81 in BFS)
        all_neighbors = chain(graph.successors(node_id), graph.predecessors(node_id))
        for neighbor_id in all_neighbors:
            if neighbor_id not in visited and len(visited) < node_limit:
                visited.add(neighbor_id)
                queue.append((neighbor_id, depth + 1))

    return visited

