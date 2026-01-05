"""
Substation detection and naming utilities.

This module wraps VeraGrid's substation detection and provides:
- Primary: VeraGrid's built-in substation detection
- Fallback: prefix-based grouping with naming heuristics
- Naming fallback for unnamed substations
"""
from collections import defaultdict

from backend.core.graph.models import (
    BusModel,
    SubstationModel,
    make_substation_id,
)


def detect_substations_fallback(
    buses: list[BusModel],
    namespace: str,
    prefix_min_length: int = 3,
) -> tuple[list[SubstationModel], dict[str, str]]:
    """
    Fallback substation detection using bus name prefixes.

    This is used when VeraGrid doesn't provide substation groupings.

    Args:
        buses: List of BusModel objects
        namespace: Case namespace for generating IDs
        prefix_min_length: Minimum prefix length to consider

    Returns:
        Tuple of (substations list, bus_id -> substation_id mapping)
    """
    # Group buses by common name prefix
    prefix_groups: dict[str, list[BusModel]] = defaultdict(list)

    for bus in buses:
        # Extract prefix (everything before the last number/space)
        prefix = _extract_name_prefix(bus.name, prefix_min_length)
        if prefix:
            prefix_groups[prefix].append(bus)
        else:
            # No prefix found, group by area/zone
            key = f"area_{bus.area or 0}_zone_{bus.zone or 0}"
            prefix_groups[key].append(bus)

    # Create substations from groups
    substations: list[SubstationModel] = []
    bus_to_substation: dict[str, str] = {}

    for idx, (prefix, group_buses) in enumerate(sorted(prefix_groups.items())):
        # Generate substation name
        if prefix.startswith("area_"):
            # Fallback naming
            name = f"Station_{prefix}"
            name_source = "fallback"
        else:
            name = prefix.strip()
            name_source = "prefix"

        sub_id = make_substation_id(namespace, name, idx)

        # Collect voltage levels
        voltage_levels = sorted(set(b.base_kv for b in group_buses), reverse=True)

        # Get area/zone from first bus
        first_bus = group_buses[0]

        substation = SubstationModel(
            id=sub_id,
            name=name,
            area=first_bus.area,
            zone=first_bus.zone,
            voltage_levels=voltage_levels,
            nominal_kv=max(voltage_levels) if voltage_levels else None,
            metadata={"name_source": name_source, "bus_count": len(group_buses)},
        )

        substations.append(substation)

        # Map buses to this substation
        for bus in group_buses:
            bus_to_substation[bus.id] = sub_id

    return substations, bus_to_substation


def _extract_name_prefix(name: str, min_length: int = 3) -> str | None:
    """
    Extract a common prefix from a bus name.

    Tries to find a meaningful prefix by removing trailing numbers,
    bus designators, and voltage levels.

    Args:
        name: Bus name
        min_length: Minimum prefix length to return

    Returns:
        Prefix string or None if no valid prefix found
    """
    if not name:
        return None

    # Remove common suffixes
    import re

    # Remove trailing numbers and common suffixes
    cleaned = re.sub(r"[\s_-]*\d+[\s_-]*$", "", name)
    cleaned = re.sub(r"[\s_-]*(BUS|HV|LV|MV|KV)[\s_-]*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\s_-]*\d+[\s_-]*KV[\s_-]*$", "", cleaned, flags=re.IGNORECASE)

    cleaned = cleaned.strip()

    if len(cleaned) >= min_length:
        return cleaned

    return None


def generate_substation_name(
    buses: list[BusModel],
    area: int | None = None,
    zone: int | None = None,
    index: int = 0,
) -> tuple[str, str]:
    """
    Generate a substation name from its buses.

    Strategy:
    1. Find common prefix of bus names (length >= 3)
    2. Fall back to "Station_{area}_{zone}_{index}"

    Args:
        buses: Buses in this substation
        area: Area number
        zone: Zone number
        index: Substation index for uniqueness

    Returns:
        Tuple of (name, name_source)
    """
    if not buses:
        return f"Station_{area or 0}_{zone or 0}_{index}", "fallback"

    # Try to find common prefix
    names = [b.name for b in buses if b.name]
    if not names:
        return f"Station_{area or 0}_{zone or 0}_{index}", "fallback"

    # Find longest common prefix
    prefix = _find_common_prefix(names)

    if prefix and len(prefix) >= 3:
        return prefix.strip(), "prefix"

    # Fallback
    return f"Station_{area or 0}_{zone or 0}_{index}", "fallback"


def _find_common_prefix(strings: list[str]) -> str:
    """Find the longest common prefix of a list of strings."""
    if not strings:
        return ""

    # Start with first string
    prefix = strings[0]

    for s in strings[1:]:
        # Shorten prefix until it matches
        while not s.startswith(prefix) and prefix:
            prefix = prefix[:-1]

        if not prefix:
            break

    return prefix


def update_substation_voltage_levels(
    substations: list[SubstationModel],
    buses: list[BusModel],
) -> None:
    """
    Update voltage_levels for each substation based on its buses.

    Args:
        substations: List of substations (modified in place)
        buses: List of buses with substation_id set
    """
    # Group buses by substation
    buses_by_sub: dict[str, list[BusModel]] = defaultdict(list)
    for bus in buses:
        if bus.substation_id:
            buses_by_sub[bus.substation_id].append(bus)

    # Update voltage levels
    sub_by_id = {s.id: s for s in substations}

    for sub_id, sub_buses in buses_by_sub.items():
        if sub_id in sub_by_id:
            sub = sub_by_id[sub_id]
            voltage_levels = sorted(set(b.base_kv for b in sub_buses), reverse=True)
            sub.voltage_levels = voltage_levels
            if voltage_levels and sub.nominal_kv is None:
                sub.nominal_kv = max(voltage_levels)


def apply_jumper_rule(
    buses: list[BusModel],
    branches: list,  # AcBranchModel
    r_x_threshold: float = 0.0001,
) -> dict[str, str]:
    """
    Apply hardened jumper rule to group buses connected by low-impedance branches.

    A "jumper" is a branch with abs(R) + abs(X) <= threshold.
    Buses connected by jumpers are considered part of the same substation.

    Args:
        buses: List of buses
        branches: List of AC branches
        r_x_threshold: Threshold for R+X sum

    Returns:
        Mapping of bus_id -> group_id (representative bus ID for the group)
    """
    # Build adjacency for jumper connections
    bus_id_set = {b.id for b in buses}
    jumper_adj: dict[str, set[str]] = defaultdict(set)

    for branch in branches:
        if branch.from_bus_id not in bus_id_set or branch.to_bus_id not in bus_id_set:
            continue

        r = abs(branch.r or 0)
        x = abs(branch.x or 0)

        if r + x <= r_x_threshold:
            jumper_adj[branch.from_bus_id].add(branch.to_bus_id)
            jumper_adj[branch.to_bus_id].add(branch.from_bus_id)

    # Find connected components using union-find
    parent: dict[str, str] = {b.id: b.id for b in buses}

    def find(x: str) -> str:
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x: str, y: str) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for bus_id, neighbors in jumper_adj.items():
        for neighbor in neighbors:
            union(bus_id, neighbor)

    # Return mapping to group representative
    return {bus_id: find(bus_id) for bus_id in parent}
