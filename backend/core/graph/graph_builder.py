"""
Graph builder for constructing NetworkX graphs from parsed case data.

Uses undirected MultiGraph for connectivity/BFS operations.
Provides indexes for fast lookups.
"""
from collections import defaultdict
from typing import Iterator

import networkx as nx

from backend.core.timing import OperationTimer, logger

from backend.core.graph.models import (
    BusModel,
    AcBranchModel,
    Transformer3WModel,
    EquipmentModel,
    DcLinkModel,
    SubstationModel,
    BranchKind,
    TopologyMode,
)
from backend.core.graph.veragrid_adapter import ParsedCase


class CaseGraph:
    """
    NetworkX-based graph representation of a power system case.

    Uses undirected MultiGraph for adjacency/BFS operations.
    Provides fast lookups via indexes.
    """

    def __init__(self, case: ParsedCase):
        """
        Build graph from parsed case data.

        Args:
            case: ParsedCase from VeraGrid adapter
        """
        self.case = case

        # NetworkX MultiGraph (undirected, allows parallel edges)
        self.graph: nx.MultiGraph = nx.MultiGraph()

        # Indexes for fast lookups
        self.bus_by_id: dict[str, BusModel] = {}
        self.bus_by_psse: dict[int, BusModel] = {}
        self.branch_by_id: dict[str, AcBranchModel] = {}
        self.transformer3_by_id: dict[str, Transformer3WModel] = {}
        self.equipment_by_id: dict[str, EquipmentModel] = {}
        self.equipment_by_bus_id: dict[str, list[EquipmentModel]] = defaultdict(list)
        self.dc_link_by_id: dict[str, DcLinkModel] = {}
        self.substation_by_id: dict[str, SubstationModel] = {}
        self.buses_by_substation_id: dict[str, list[BusModel]] = defaultdict(list)

        # Converter equipment by ID (for DC link endpoints)
        self.converter_by_id: dict[str, EquipmentModel] = {}

        # Build the graph and indexes
        self._build()

    def _build(self) -> None:
        """Build graph and indexes from case data."""
        timer = OperationTimer("Build NetworkX graph", log_phases=False)

        # Index buses
        timer.start_phase("index_buses")
        for bus in self.case.buses:
            self.bus_by_id[bus.id] = bus
            self.bus_by_psse[bus.psse_number] = bus
            self.graph.add_node(bus.id, kind="bus", data=bus)

            if bus.substation_id:
                self.buses_by_substation_id[bus.substation_id].append(bus)
        timer.end_phase("index_buses", len(self.case.buses))

        # Index substations
        timer.start_phase("index_substations")
        for sub in self.case.substations:
            self.substation_by_id[sub.id] = sub
        timer.end_phase("index_substations", len(self.case.substations))

        # Index and add AC branches as edges
        timer.start_phase("index_branches")
        for branch in self.case.ac_branches:
            self.branch_by_id[branch.id] = branch
            self.graph.add_edge(
                branch.from_bus_id,
                branch.to_bus_id,
                key=branch.id,
                kind="ac_branch",
                branch_kind=branch.kind.value,
                data=branch,
            )
        timer.end_phase("index_branches", len(self.case.ac_branches))

        # Index 3W transformers (add adjacency between all bus pairs)
        timer.start_phase("index_xfmr3")
        for xfmr3 in self.case.transformers3w:
            self.transformer3_by_id[xfmr3.id] = xfmr3

            # Add edges between all pairs for BFS adjacency
            bus_ids = [xfmr3.bus1_id, xfmr3.bus2_id, xfmr3.bus3_id]
            for i, bus_a in enumerate(bus_ids):
                for bus_b in bus_ids[i + 1 :]:
                    self.graph.add_edge(
                        bus_a,
                        bus_b,
                        key=f"{xfmr3.id}_leg_{i}",
                        kind="xfmr3_adjacency",
                        transformer_id=xfmr3.id,
                        data=xfmr3,
                    )
        timer.end_phase("index_xfmr3", len(self.case.transformers3w))

        # Index equipment
        timer.start_phase("index_equipment")
        for eq in self.case.equipment:
            self.equipment_by_id[eq.id] = eq
            self.equipment_by_bus_id[eq.bus_id].append(eq)

            # Track converters separately
            if eq.kind.value.startswith("CONVERTER"):
                self.converter_by_id[eq.id] = eq
        timer.end_phase("index_equipment", len(self.case.equipment))

        # Index DC links
        timer.start_phase("index_dc_links")
        for dc in self.case.dc_links:
            self.dc_link_by_id[dc.id] = dc
        timer.end_phase("index_dc_links", len(self.case.dc_links))

        report = timer.finish()
        logger.info(f"  [GRAPH] Nodes: {self.graph.number_of_nodes():,}, Edges: {self.graph.number_of_edges():,}")

    def get_bus(self, bus_id: str) -> BusModel | None:
        """Get bus by ID."""
        return self.bus_by_id.get(bus_id)

    def get_bus_by_psse(self, psse_number: int) -> BusModel | None:
        """Get bus by PSSE number."""
        return self.bus_by_psse.get(psse_number)

    def get_branch(self, branch_id: str) -> AcBranchModel | None:
        """Get AC branch by ID."""
        return self.branch_by_id.get(branch_id)

    def get_transformer3(self, xfmr_id: str) -> Transformer3WModel | None:
        """Get 3W transformer by ID."""
        return self.transformer3_by_id.get(xfmr_id)

    def get_equipment_at_bus(self, bus_id: str) -> list[EquipmentModel]:
        """Get all equipment at a bus."""
        return self.equipment_by_bus_id.get(bus_id, [])

    def get_substation(self, sub_id: str) -> SubstationModel | None:
        """Get substation by ID."""
        return self.substation_by_id.get(sub_id)

    def get_buses_in_substation(self, sub_id: str) -> list[BusModel]:
        """Get all buses in a substation."""
        return self.buses_by_substation_id.get(sub_id, [])

    def get_neighbors(
        self,
        bus_id: str,
        topology_mode: TopologyMode = TopologyMode.AS_MODELED,
    ) -> list[str]:
        """
        Get neighboring bus IDs considering topology mode.

        Args:
            bus_id: Source bus ID
            topology_mode: How to handle switch/out-of-service status

        Returns:
            List of adjacent bus IDs
        """
        if bus_id not in self.graph:
            return []

        neighbors = set()

        for neighbor_id in self.graph.neighbors(bus_id):
            # Check all edges between bus_id and neighbor_id
            edges = self.graph.get_edge_data(bus_id, neighbor_id)
            if not edges:
                continue

            for edge_key, edge_data in edges.items():
                if self._is_edge_traversable(edge_data, topology_mode):
                    neighbors.add(neighbor_id)
                    break  # Only need one traversable edge

        return list(neighbors)

    def _is_edge_traversable(
        self,
        edge_data: dict,
        topology_mode: TopologyMode,
    ) -> bool:
        """
        Check if an edge is traversable given the topology mode.

        Args:
            edge_data: Edge attributes dict
            topology_mode: How to handle switch/out-of-service

        Returns:
            True if the edge should be traversed in BFS
        """
        if topology_mode == TopologyMode.AS_MODELED:
            return True

        # ENERGIZED_ONLY mode
        data = edge_data.get("data")
        if data is None:
            return True

        # Check in_service
        if hasattr(data, "in_service") and not data.in_service:
            return False

        # Check switch status
        if hasattr(data, "is_closed") and data.is_closed is False:
            return False

        # For 3W transformers, check leg status
        if edge_data.get("kind") == "xfmr3_adjacency":
            xfmr = data
            if isinstance(xfmr, Transformer3WModel):
                if not xfmr.in_service:
                    return False
                # Could check individual leg status here if needed

        return True

    def get_branches_between(
        self,
        bus_a_id: str,
        bus_b_id: str,
    ) -> list[AcBranchModel]:
        """Get all AC branches between two buses."""
        if not self.graph.has_edge(bus_a_id, bus_b_id):
            return []

        branches = []
        edges = self.graph.get_edge_data(bus_a_id, bus_b_id) or {}

        for edge_key, edge_data in edges.items():
            if edge_data.get("kind") == "ac_branch":
                branch = edge_data.get("data")
                if branch:
                    branches.append(branch)

        return branches

    def iter_all_branches(self) -> Iterator[AcBranchModel]:
        """Iterate over all AC branches."""
        return iter(self.case.ac_branches)

    def iter_all_equipment(self) -> Iterator[EquipmentModel]:
        """Iterate over all equipment."""
        return iter(self.case.equipment)

    def get_dc_links_for_bus(self, bus_id: str) -> list[DcLinkModel]:
        """Get DC links that have a converter at this bus."""
        result = []

        # Find converters at this bus
        converters_at_bus = [
            eq for eq in self.equipment_by_bus_id.get(bus_id, [])
            if eq.kind.value.startswith("CONVERTER")
        ]

        if not converters_at_bus:
            return result

        converter_ids = {c.id for c in converters_at_bus}

        # Find DC links using these converters
        for dc_link in self.case.dc_links:
            if dc_link.from_converter_id in converter_ids or dc_link.to_converter_id in converter_ids:
                result.append(dc_link)

        return result

    def bus_degree(self, bus_id: str) -> int:
        """Get the degree (number of connections) of a bus."""
        if bus_id not in self.graph:
            return 0
        return self.graph.degree(bus_id)

    def is_junction_bus(
        self,
        bus_id: str,
        max_degree: int = 2,
        equipment_allowed: bool = False,
    ) -> bool:
        """
        Check if a bus qualifies as a junction bus (pass-through node).

        A junction bus:
        - Has degree <= max_degree
        - Has no equipment attached (unless equipment_allowed)

        Args:
            bus_id: Bus to check
            max_degree: Maximum degree for junction
            equipment_allowed: Whether equipment is allowed

        Returns:
            True if bus qualifies as junction
        """
        degree = self.bus_degree(bus_id)
        if degree > max_degree:
            return False

        if not equipment_allowed:
            if self.equipment_by_bus_id.get(bus_id):
                return False

        return True

    def get_bus_connection_counts(self) -> dict[str, int]:
        """
        Compute connection counts for all buses in the full network.

        Counts:
        - AC branches (from/to)
        - 3W transformer legs
        - Equipment

        Used for determining circle vs busbar rendering.

        Returns:
            Dict mapping bus_id to total connection count
        """
        counts: dict[str, int] = defaultdict(int)

        # Count AC branches
        for branch in self.case.ac_branches:
            counts[branch.from_bus_id] += 1
            counts[branch.to_bus_id] += 1

        # Count 3W transformer legs
        for xfmr3 in self.case.transformers3w:
            counts[xfmr3.bus1_id] += 1
            counts[xfmr3.bus2_id] += 1
            counts[xfmr3.bus3_id] += 1

        # Count equipment
        for eq in self.case.equipment:
            counts[eq.bus_id] += 1

        return dict(counts)


def build_case_graph(case: ParsedCase) -> CaseGraph:
    """
    Build a CaseGraph from parsed case data.

    Args:
        case: ParsedCase from VeraGrid adapter

    Returns:
        CaseGraph instance
    """
    return CaseGraph(case)
