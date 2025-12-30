"""Substation inference and detection for SLD Viewer.

Implements topology-based substation inference for cases where PSSE substations
are not available or need to be refined. Uses strong-coupling analysis to cluster
buses into substations.
"""

import uuid
from collections import defaultdict
from statistics import median
from typing import Optional

import networkx as nx

from backend.core.graph.models import BranchModel, BusModel, SubstationModel


# Thresholds for strong coupling detection
ZERO_IMPEDANCE_THRESHOLD = 1e-6  # |r| + |x| < threshold means zero impedance
SMALL_IMPEDANCE_THRESHOLD = 1e-3  # Small impedance for short lines
MAX_SPATIAL_EXTENT_KM = 5.0  # Maximum extent for a single substation (if lat/lon available)


def infer_substations(
    buses: list[BusModel],
    branches: list[BranchModel],
    spatial_threshold_km: float = MAX_SPATIAL_EXTENT_KM,
) -> tuple[list[SubstationModel], dict[str, str]]:
    """Infer substations from buses and branches using topology analysis.

    Uses strong-coupling analysis to cluster buses into substations. Buses are
    considered strongly coupled if connected by:
    - Zero-impedance branches (|r|+|x| ≈ 0)
    - Small impedance branches (short lines)
    - Transformers (which typically connect voltage levels within a station)

    If buses have lat/lon coordinates, clusters are split if their spatial extent
    exceeds the threshold (indicating buses from different physical locations).

    Args:
        buses: List of bus models
        branches: List of branch models
        spatial_threshold_km: Maximum spatial extent (km) for a single substation

    Returns:
        Tuple of (substations, bus_to_substation_map) where:
        - substations: List of inferred SubstationModel instances
        - bus_to_substation_map: Dict mapping bus_id to substation_id
    """
    if not buses:
        return [], {}

    # Build bus lookup by ID
    bus_by_id = {bus.id: bus for bus in buses}

    # Build strong-coupling graph
    strong_coupling_graph = _build_strong_coupling_graph(buses, branches, bus_by_id)

    # Find connected components (initial clusters)
    initial_clusters = list(nx.connected_components(strong_coupling_graph))

    # Split clusters by spatial extent if lat/lon is available
    final_clusters = []
    for cluster in initial_clusters:
        sub_clusters = _split_cluster_by_spatial_extent(
            cluster, bus_by_id, spatial_threshold_km
        )
        final_clusters.extend(sub_clusters)

    # Build substations from clusters
    substations = []
    bus_to_substation_map = {}

    for cluster_idx, cluster_bus_ids in enumerate(final_clusters):
        cluster_buses = [bus_by_id[bus_id] for bus_id in cluster_bus_ids]

        # Create substation model
        substation = _create_substation_from_cluster(
            cluster_idx, cluster_buses
        )
        substations.append(substation)

        # Map buses to this substation
        for bus_id in cluster_bus_ids:
            bus_to_substation_map[bus_id] = substation.id

    return substations, bus_to_substation_map


def _build_strong_coupling_graph(
    buses: list[BusModel],
    branches: list[BranchModel],
    bus_by_id: dict[str, BusModel],
) -> nx.Graph:
    """Build an undirected graph where edges represent strong coupling between buses.

    Strong coupling includes:
    - Zero-impedance branches (switches, ideal buses)
    - Small impedance branches (short lines within a station)
    - Transformers (connect voltage levels in a station)

    Args:
        buses: List of buses
        branches: List of branches
        bus_by_id: Bus lookup dictionary

    Returns:
        NetworkX undirected graph with bus IDs as nodes
    """
    graph = nx.Graph()

    # Add all buses as nodes
    for bus in buses:
        graph.add_node(bus.id)

    # Add edges for strongly coupled branches
    for branch in branches:
        # Check if both buses exist
        if branch.from_bus_id not in bus_by_id or branch.to_bus_id not in bus_by_id:
            continue

        is_strongly_coupled = False

        # Check for zero impedance
        impedance_magnitude = abs(branch.r) + abs(branch.x)
        if impedance_magnitude < ZERO_IMPEDANCE_THRESHOLD:
            is_strongly_coupled = True

        # Check for small impedance (short lines)
        elif impedance_magnitude < SMALL_IMPEDANCE_THRESHOLD:
            is_strongly_coupled = True

        # Check for transformers (typically connect buses in same substation)
        elif branch.type in ["xfmr", "xfmr3"]:
            # Transformers usually connect different voltage levels in same station
            # But only if impedance is reasonably small (not transmission-level transformers)
            if impedance_magnitude < 0.1:  # Typical station transformer impedance
                is_strongly_coupled = True

        if is_strongly_coupled:
            graph.add_edge(branch.from_bus_id, branch.to_bus_id)

    return graph


def _split_cluster_by_spatial_extent(
    cluster_bus_ids: set[str],
    bus_by_id: dict[str, BusModel],
    threshold_km: float,
) -> list[set[str]]:
    """Split a cluster into sub-clusters if spatial extent exceeds threshold.

    If buses have lat/lon coordinates and the cluster spans more than threshold_km,
    split it into smaller clusters based on spatial proximity.

    Args:
        cluster_bus_ids: Set of bus IDs in the cluster
        bus_by_id: Bus lookup dictionary
        threshold_km: Maximum spatial extent (km) for a single cluster

    Returns:
        List of sub-clusters (each a set of bus IDs)
    """
    cluster_buses = [bus_by_id[bus_id] for bus_id in cluster_bus_ids]

    # Check if we have lat/lon for all buses
    buses_with_coords = [
        bus for bus in cluster_buses
        if bus.latitude is not None and bus.longitude is not None
    ]

    if len(buses_with_coords) < 2:
        # Not enough coordinate data, keep cluster as-is
        return [cluster_bus_ids]

    # Calculate spatial extent (simple bounding box diagonal)
    lats = [bus.latitude for bus in buses_with_coords]
    lons = [bus.longitude for bus in buses_with_coords]

    lat_span = max(lats) - min(lats)
    lon_span = max(lons) - min(lons)

    # Approximate distance in km (rough conversion at mid-latitudes)
    # 1 degree lat ≈ 111 km, 1 degree lon ≈ 111 * cos(lat) km
    avg_lat = sum(lats) / len(lats)
    import math
    lat_km = lat_span * 111.0
    lon_km = lon_span * 111.0 * math.cos(math.radians(avg_lat))
    extent_km = math.sqrt(lat_km**2 + lon_km**2)

    if extent_km <= threshold_km:
        # Cluster is small enough, keep as-is
        return [cluster_bus_ids]

    # Cluster is too large, split it
    # Use a simple approach: split by median lat/lon
    median_lat = median(lats)
    median_lon = median(lons)

    # Create 4 quadrants
    quadrants = [set() for _ in range(4)]

    for bus in cluster_buses:
        if bus.latitude is not None and bus.longitude is not None:
            # Assign to quadrant based on lat/lon relative to median
            quadrant_idx = 0
            if bus.latitude >= median_lat:
                quadrant_idx += 2
            if bus.longitude >= median_lon:
                quadrant_idx += 1
            quadrants[quadrant_idx].add(bus.id)
        else:
            # Bus without coordinates goes to first quadrant
            quadrants[0].add(bus.id)

    # Filter out empty quadrants and recursively check their extent
    result = []
    for quadrant in quadrants:
        if quadrant:
            # Recursively check if quadrant needs further splitting
            sub_clusters = _split_cluster_by_spatial_extent(
                quadrant, bus_by_id, threshold_km
            )
            result.extend(sub_clusters)

    return result if result else [cluster_bus_ids]


def _create_substation_from_cluster(
    cluster_idx: int,
    cluster_buses: list[BusModel],
) -> SubstationModel:
    """Create a SubstationModel from a cluster of buses.

    Infers substation properties from the buses in the cluster:
    - name: Heuristic based on bus names (common prefix or longest name)
    - voltage_levels: Distinct base_kv values in cluster
    - nominal_kv: Maximum voltage level
    - area/zone: Majority vote from buses
    - lat/lon: Average/median of bus coordinates

    Args:
        cluster_idx: Index of this cluster (for unique naming)
        cluster_buses: List of buses in the cluster

    Returns:
        SubstationModel for this cluster
    """
    if not cluster_buses:
        raise ValueError("Cannot create substation from empty cluster")

    substation_id = str(uuid.uuid4())

    # Infer name from bus names
    name = _infer_substation_name(cluster_buses, cluster_idx)

    # Collect voltage levels
    voltage_levels = sorted(set(bus.base_kv for bus in cluster_buses))
    nominal_kv = max(voltage_levels) if voltage_levels else None

    # Determine area and zone by majority vote
    area = _majority_vote([bus.area for bus in cluster_buses])
    zone = _majority_vote([bus.zone for bus in cluster_buses])

    # Calculate average lat/lon if available
    lats = [bus.latitude for bus in cluster_buses if bus.latitude is not None]
    lons = [bus.longitude for bus in cluster_buses if bus.longitude is not None]

    latitude = sum(lats) / len(lats) if lats else None
    longitude = sum(lons) / len(lons) if lons else None

    return SubstationModel(
        id=substation_id,
        name=name,
        area=area,
        zone=zone,
        nominal_kv=nominal_kv,
        voltage_levels=voltage_levels,
        latitude=latitude,
        longitude=longitude,
    )


def _infer_substation_name(buses: list[BusModel], cluster_idx: int) -> str:
    """Infer a substation name from bus names.

    Uses heuristics:
    1. Find common prefix of bus names
    2. If no common prefix, use the longest bus name
    3. If no good name, use "Substation_N"

    Args:
        buses: List of buses in the substation
        cluster_idx: Index of this cluster

    Returns:
        Inferred substation name
    """
    if not buses:
        return f"Substation_{cluster_idx + 1}"

    bus_names = [bus.name for bus in buses if bus.name]

    if not bus_names:
        return f"Substation_{cluster_idx + 1}"

    # Try to find common prefix
    if len(bus_names) > 1:
        common_prefix = _find_common_prefix(bus_names)
        if common_prefix and len(common_prefix) >= 3:
            # Clean up prefix (remove trailing numbers, spaces, underscores)
            cleaned = common_prefix.rstrip("0123456789 _-")
            if len(cleaned) >= 3:
                return cleaned

    # Fall back to longest name
    longest_name = max(bus_names, key=len)
    if len(longest_name) > 5:
        return longest_name

    # Last resort: use first bus name or default
    if bus_names[0]:
        return bus_names[0]

    return f"Substation_{cluster_idx + 1}"


def _find_common_prefix(strings: list[str]) -> str:
    """Find the longest common prefix of a list of strings.

    Args:
        strings: List of strings

    Returns:
        Common prefix string (empty if no common prefix)
    """
    if not strings:
        return ""

    # Start with first string
    prefix = strings[0]

    for string in strings[1:]:
        # Reduce prefix until it matches beginning of string
        while not string.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""

    return prefix


def _majority_vote(values: list[Optional[int]]) -> Optional[int]:
    """Return the most common value from a list, or None if list is empty.

    Args:
        values: List of values (can contain None)

    Returns:
        Most common non-None value, or None if no values
    """
    # Filter out None values
    non_none_values = [v for v in values if v is not None]

    if not non_none_values:
        return None

    # Count occurrences
    counts = defaultdict(int)
    for value in non_none_values:
        counts[value] += 1

    # Return most common
    return max(counts, key=counts.get)


def assign_substations_to_buses(
    buses: list[BusModel],
    bus_to_substation_map: dict[str, str],
) -> list[BusModel]:
    """Assign substation IDs to buses based on a mapping.

    Creates new BusModel instances with substation_id set.

    Args:
        buses: List of buses to update
        bus_to_substation_map: Mapping from bus_id to substation_id

    Returns:
        New list of BusModel instances with substation_id assigned
    """
    updated_buses = []

    for bus in buses:
        substation_id = bus_to_substation_map.get(bus.id)

        # Create new bus with substation_id set
        updated_bus = bus.model_copy(update={"substation_id": substation_id})
        updated_buses.append(updated_bus)

    return updated_buses
