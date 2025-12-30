"""Graph builder for SLD Viewer.

Builds NetworkX graphs from canonical models (buses, branches, equipment, substations).
Supports both bus-level and substation-level graph representations.
"""

from collections import defaultdict
from dataclasses import dataclass, field

import networkx as nx

from backend.core.graph.models import BranchModel, BusModel, EquipmentModel, SubstationModel


@dataclass
class GraphHandle:
    """Container for graph structures and lookup dictionaries.

    Holds the NetworkX graphs and dictionaries for efficient lookups
    by ID. Equipment is stored as a sidecar structure keyed by bus_id.
    Substation graph connects substations based on inter-substation branches.
    """

    bus_graph: nx.MultiDiGraph
    bus_by_id: dict[str, BusModel]
    branch_by_id: dict[str, BranchModel]
    equipment_by_id: dict[str, EquipmentModel] = field(default_factory=dict)
    equipment_by_bus_id: dict[str, list[EquipmentModel]] = field(default_factory=dict)
    substation_graph: nx.MultiDiGraph | None = None
    substation_by_id: dict[str, SubstationModel] = field(default_factory=dict)
    buses_by_substation_id: dict[str, list[BusModel]] = field(default_factory=dict)


def build_graphs(
    buses: list[BusModel],
    branches: list[BranchModel],
    equipment: list[EquipmentModel] | None = None,
    substations: list[SubstationModel] | None = None,
) -> GraphHandle:
    """Build NetworkX graphs from buses, branches, equipment, and substations.

    Creates two graphs:
    1. Bus-level MultiDiGraph: nodes are buses, edges are branches
    2. Substation-level MultiDiGraph: nodes are substations, edges are inter-substation branches

    Args:
        buses: List of bus models to add as nodes
        branches: List of branch models to add as edges
        equipment: Optional list of equipment models attached to buses
        substations: Optional list of substation models (buses reference these via substation_id)

    Returns:
        GraphHandle containing both graphs, lookup dictionaries, and equipment

    Raises:
        ValueError: If a branch references a bus_id that doesn't exist
    """
    # Build lookup dictionaries
    bus_by_id = {bus.id: bus for bus in buses}
    branch_by_id = {branch.id: branch for branch in branches}

    # Build equipment lookups
    equipment = equipment or []
    equipment_by_id = {eq.id: eq for eq in equipment}
    equipment_by_bus_id: dict[str, list[EquipmentModel]] = defaultdict(list)
    for eq in equipment:
        equipment_by_bus_id[eq.bus_id].append(eq)

    # Build substation lookups
    substations = substations or []
    substation_by_id = {sub.id: sub for sub in substations}
    buses_by_substation_id: dict[str, list[BusModel]] = defaultdict(list)
    for bus in buses:
        if bus.substation_id:
            buses_by_substation_id[bus.substation_id].append(bus)

    # Create bus-level graph
    bus_graph = nx.MultiDiGraph()

    # Add all buses as nodes with their full model data as attributes
    for bus in buses:
        # Convert Pydantic model to dict for NetworkX attributes
        bus_attrs = bus.model_dump()
        bus_graph.add_node(bus.id, **bus_attrs)

    # Add all branches as edges, preserving parallel circuits via edge keys
    for branch in branches:
        # Validate that both buses exist
        if branch.from_bus_id not in bus_by_id:
            raise ValueError(
                f"Branch {branch.id} references non-existent from_bus_id: {branch.from_bus_id}"
            )
        if branch.to_bus_id not in bus_by_id:
            raise ValueError(
                f"Branch {branch.id} references non-existent to_bus_id: {branch.to_bus_id}"
            )

        # Convert Pydantic model to dict for NetworkX edge attributes
        branch_attrs = branch.model_dump()
        # Use branch.id as the edge key to preserve parallel circuits
        bus_graph.add_edge(
            branch.from_bus_id, branch.to_bus_id, key=branch.id, **branch_attrs
        )

    # Create substation-level graph if we have substations
    substation_graph = None
    if substations:
        substation_graph = nx.MultiDiGraph()
        
        # Add all substations as nodes
        for sub in substations:
            sub_attrs = sub.model_dump()
            substation_graph.add_node(sub.id, **sub_attrs)
        
        # Add edges for branches that connect different substations
        for branch in branches:
            from_bus = bus_by_id.get(branch.from_bus_id)
            to_bus = bus_by_id.get(branch.to_bus_id)
            
            if from_bus and to_bus:
                from_sub_id = from_bus.substation_id
                to_sub_id = to_bus.substation_id
                
                # Only add edge if substations are different (inter-substation branch)
                if from_sub_id and to_sub_id and from_sub_id != to_sub_id:
                    branch_attrs = branch.model_dump()
                    # Use branch.id as edge key to preserve parallel circuits
                    substation_graph.add_edge(
                        from_sub_id, to_sub_id, key=branch.id, **branch_attrs
                    )

    return GraphHandle(
        bus_graph=bus_graph,
        bus_by_id=bus_by_id,
        branch_by_id=branch_by_id,
        equipment_by_id=equipment_by_id,
        equipment_by_bus_id=dict(equipment_by_bus_id),
        substation_graph=substation_graph,
        substation_by_id=substation_by_id,
        buses_by_substation_id=dict(buses_by_substation_id),
    )

