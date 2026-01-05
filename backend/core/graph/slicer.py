"""
View slicing: BFS expansion with budgets for bus/substation/station_detail modes.
"""
from collections import deque
from dataclasses import dataclass, field
from typing import Iterator

from backend.core.timing import OperationTimer, logger

from backend.core.graph.models import (
    BusModel,
    AcBranchModel,
    Transformer3WModel,
    EquipmentModel,
    DcLinkModel,
    SubstationModel,
    ViewSpec,
    ViewResult,
    TopologyMode,
    ViewMode,
)
from backend.core.graph.graph_builder import CaseGraph


@dataclass
class SliceResult:
    """Result of a view slice operation."""

    buses: list[BusModel] = field(default_factory=list)
    ac_branches: list[AcBranchModel] = field(default_factory=list)
    transformers3w: list[Transformer3WModel] = field(default_factory=list)
    equipment: list[EquipmentModel] = field(default_factory=list)
    dc_links: list[DcLinkModel] = field(default_factory=list)
    substations: list[SubstationModel] = field(default_factory=list)

    # BFS depth for each bus (distance from seed)
    bfs_depth: dict[str, int] = field(default_factory=dict)

    # Metadata
    truncated: bool = False
    truncation_reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    seed_bus_numbers: list[int] = field(default_factory=list)
    effective_max_depth: int = 0


class ViewSlicer:
    """
    Slices a CaseGraph according to a ViewSpec.

    Supports:
    - BFS expansion from center bus(es)
    - Node/edge budgets
    - topology_mode (as_modeled vs energized_only)
    - Voltage filtering
    - Area/zone filtering
    """

    def __init__(self, graph: CaseGraph, spec: ViewSpec):
        """
        Initialize the slicer.

        Args:
            graph: CaseGraph to slice
            spec: ViewSpec defining the slice parameters
        """
        self.graph = graph
        self.spec = spec
        self.result = SliceResult()

        # Track visited elements
        self._visited_buses: set[str] = set()
        self._visited_branches: set[str] = set()
        self._visited_xfmr3: set[str] = set()

    def slice(self) -> SliceResult:
        """
        Perform the view slice.

        Returns:
            SliceResult with sliced data and metadata
        """
        if self.spec.mode == ViewMode.BUS:
            return self._slice_bus_mode()
        elif self.spec.mode == ViewMode.SUBSTATION:
            return self._slice_substation_mode()
        elif self.spec.mode == ViewMode.STATION_DETAIL:
            return self._slice_station_detail_mode()
        else:
            raise ValueError(f"Unknown view mode: {self.spec.mode}")

    def _slice_bus_mode(self) -> SliceResult:
        """Slice in bus mode: BFS from center buses."""
        if not self.spec.center_bus_numbers:
            self.result.warnings.append("No center bus specified")
            return self.result

        # Find seed buses
        seed_buses: list[BusModel] = []
        for psse_num in self.spec.center_bus_numbers:
            bus = self.graph.get_bus_by_psse(psse_num)
            if bus:
                seed_buses.append(bus)
                self.result.seed_bus_numbers.append(psse_num)
            else:
                self.result.warnings.append(f"Center bus {psse_num} not found")

        if not seed_buses:
            self.result.warnings.append("No valid center buses found")
            return self.result

        # BFS expansion
        self._bfs_expand(seed_buses)

        # Add branches between visited buses
        self._add_branches_in_view()

        # Add 3W transformers with buses in view
        self._add_transformers3w_in_view()

        # Add equipment if requested
        if self.spec.include_equipment:
            self._add_equipment_in_view()

        # Add DC links if requested
        if self.spec.include_dc:
            self._add_dc_links_in_view()

        # Add substations for visited buses
        self._add_substations_for_buses()

        return self.result

    def _slice_substation_mode(self) -> SliceResult:
        """Slice in substation overview mode."""
        # In substation mode, we return substations as nodes
        # and inter-substation branches as edges

        # Get all substations (or filter by center if specified)
        substations_to_include: list[SubstationModel] = []

        if self.spec.center_substation_ids:
            for sub_id in self.spec.center_substation_ids:
                sub = self.graph.get_substation(sub_id)
                if sub:
                    substations_to_include.append(sub)
                else:
                    self.result.warnings.append(f"Substation {sub_id} not found")
        else:
            # Include all substations
            substations_to_include = list(self.graph.substation_by_id.values())

        # Apply node limit
        if len(substations_to_include) > self.spec.node_limit:
            substations_to_include = substations_to_include[: self.spec.node_limit]
            self.result.truncated = True
            self.result.truncation_reason = "node_limit"

        self.result.substations = substations_to_include
        sub_ids = {s.id for s in substations_to_include}

        # Find inter-substation branches
        inter_sub_branches: list[AcBranchModel] = []
        seen_branch_ids: set[str] = set()

        for branch in self.graph.case.ac_branches:
            # Get substations for from/to buses
            from_bus = self.graph.get_bus(branch.from_bus_id)
            to_bus = self.graph.get_bus(branch.to_bus_id)

            if not from_bus or not to_bus:
                continue

            from_sub = from_bus.substation_id
            to_sub = to_bus.substation_id

            # Include if connects different substations that are both in view
            if from_sub and to_sub and from_sub != to_sub:
                if from_sub in sub_ids and to_sub in sub_ids:
                    if branch.id not in seen_branch_ids:
                        inter_sub_branches.append(branch)
                        seen_branch_ids.add(branch.id)

        # Apply edge limit
        if len(inter_sub_branches) > self.spec.edge_limit:
            inter_sub_branches = inter_sub_branches[: self.spec.edge_limit]
            self.result.truncated = True
            self.result.truncation_reason = "edge_limit"

        self.result.ac_branches = inter_sub_branches

        # Add DC links between substations if requested
        if self.spec.include_dc:
            self._add_dc_links_between_substations(sub_ids)

        return self.result

    def _slice_station_detail_mode(self) -> SliceResult:
        """Slice in station detail mode: all buses in one substation."""
        if not self.spec.center_substation_ids:
            self.result.warnings.append("No center substation specified")
            return self.result

        sub_id = self.spec.center_substation_ids[0]
        substation = self.graph.get_substation(sub_id)

        if not substation:
            self.result.warnings.append(f"Substation {sub_id} not found")
            return self.result

        self.result.substations = [substation]

        # Get all buses in the substation
        buses_in_station = self.graph.get_buses_in_substation(sub_id)

        for bus in buses_in_station:
            if self._should_include_bus(bus):
                self._add_bus(bus, bfs_depth=0)

        # Add internal branches
        self._add_branches_in_view()

        # Add 3W transformers
        self._add_transformers3w_in_view()

        # Add equipment
        if self.spec.include_equipment:
            self._add_equipment_in_view()

        # Add DC links
        if self.spec.include_dc:
            self._add_dc_links_in_view()

        # Create stub buses for external connections
        self._create_stub_buses(sub_id)

        return self.result

    def _bfs_expand(self, seed_buses: list[BusModel]) -> None:
        """
        BFS expansion from seed buses.

        Respects max_depth, node_limit, edge_limit, and topology_mode.
        """
        # Initialize queue with (bus, depth)
        queue: deque[tuple[BusModel, int]] = deque()

        for bus in seed_buses:
            if self._should_include_bus(bus):
                self._add_bus(bus, bfs_depth=0)
                queue.append((bus, 0))

        # Check for isolated center bus
        if seed_buses and not queue:
            # Center bus was filtered out
            self.result.warnings.append("Center bus is filtered by view constraints")
            return

        # Track effective depth reached
        max_depth_reached = 0

        while queue:
            # Check budgets
            if len(self.result.buses) >= self.spec.node_limit:
                self.result.truncated = True
                self.result.truncation_reason = "node_limit"
                break

            if len(self._visited_branches) >= self.spec.edge_limit:
                self.result.truncated = True
                self.result.truncation_reason = "edge_limit"
                break

            current_bus, depth = queue.popleft()
            max_depth_reached = max(max_depth_reached, depth)

            # Check depth limit
            if depth >= self.spec.max_depth:
                continue

            # Get neighbors based on topology mode
            neighbors = self.graph.get_neighbors(
                current_bus.id, self.spec.topology_mode
            )

            for neighbor_id in neighbors:
                if neighbor_id in self._visited_buses:
                    continue

                neighbor = self.graph.get_bus(neighbor_id)
                if not neighbor:
                    continue

                if not self._should_include_bus(neighbor):
                    continue

                self._add_bus(neighbor, bfs_depth=depth + 1)
                queue.append((neighbor, depth + 1))

        self.result.effective_max_depth = max_depth_reached

        # Check for isolated bus
        if len(self.result.buses) == 1 and seed_buses:
            seed = seed_buses[0]
            if self.graph.bus_degree(seed.id) == 0:
                self.result.warnings.append("Center bus is isolated in this view.")

    def _should_include_bus(self, bus: BusModel) -> bool:
        """Check if a bus should be included based on filters."""
        # Voltage filter
        if self.spec.voltage_kv_min is not None:
            if bus.base_kv < self.spec.voltage_kv_min:
                return False
        if self.spec.voltage_kv_max is not None:
            if bus.base_kv > self.spec.voltage_kv_max:
                return False

        # Area filter
        if self.spec.area_ids is not None:
            if bus.area not in self.spec.area_ids:
                return False

        # Zone filter
        if self.spec.zone_ids is not None:
            if bus.zone not in self.spec.zone_ids:
                return False

        return True

    def _add_bus(self, bus: BusModel, bfs_depth: int) -> None:
        """Add a bus to the result."""
        if bus.id in self._visited_buses:
            return

        self._visited_buses.add(bus.id)
        self.result.buses.append(bus)
        self.result.bfs_depth[bus.id] = bfs_depth

    def _add_branches_in_view(self) -> None:
        """Add branches where both endpoints are in view."""
        for branch in self.graph.case.ac_branches:
            if branch.id in self._visited_branches:
                continue

            # Check if both endpoints are in view
            if (
                branch.from_bus_id in self._visited_buses
                and branch.to_bus_id in self._visited_buses
            ):
                # In energized_only mode, still include out-of-service branches
                # for rendering (dashed), but they weren't used for BFS expansion
                self._visited_branches.add(branch.id)
                self.result.ac_branches.append(branch)

    def _add_transformers3w_in_view(self) -> None:
        """Add 3W transformers with at least 2 buses in view."""
        for xfmr in self.graph.case.transformers3w:
            if xfmr.id in self._visited_xfmr3:
                continue

            buses_in_view = sum(
                1
                for bus_id in [xfmr.bus1_id, xfmr.bus2_id, xfmr.bus3_id]
                if bus_id in self._visited_buses
            )

            # Include if at least 2 buses are in view
            if buses_in_view >= 2:
                self._visited_xfmr3.add(xfmr.id)
                self.result.transformers3w.append(xfmr)

    def _add_equipment_in_view(self) -> None:
        """Add equipment at buses in view."""
        for bus_id in self._visited_buses:
            equipment = self.graph.get_equipment_at_bus(bus_id)
            for eq in equipment:
                self.result.equipment.append(eq)

    def _add_dc_links_in_view(self) -> None:
        """Add DC links where both converters are at buses in view."""
        for dc_link in self.graph.case.dc_links:
            # Find converter buses
            from_conv = self.graph.converter_by_id.get(dc_link.from_converter_id)
            to_conv = self.graph.converter_by_id.get(dc_link.to_converter_id)

            if not from_conv or not to_conv:
                continue

            # Check if both converter buses are in view
            if (
                from_conv.bus_id in self._visited_buses
                and to_conv.bus_id in self._visited_buses
            ):
                self.result.dc_links.append(dc_link)

    def _add_dc_links_between_substations(self, sub_ids: set[str]) -> None:
        """Add DC links connecting different substations (for substation mode)."""
        for dc_link in self.graph.case.dc_links:
            from_conv = self.graph.converter_by_id.get(dc_link.from_converter_id)
            to_conv = self.graph.converter_by_id.get(dc_link.to_converter_id)

            if not from_conv or not to_conv:
                continue

            from_bus = self.graph.get_bus(from_conv.bus_id)
            to_bus = self.graph.get_bus(to_conv.bus_id)

            if not from_bus or not to_bus:
                continue

            from_sub = from_bus.substation_id
            to_sub = to_bus.substation_id

            # Include if connects different substations both in view
            if from_sub and to_sub and from_sub != to_sub:
                if from_sub in sub_ids and to_sub in sub_ids:
                    self.result.dc_links.append(dc_link)

    def _add_substations_for_buses(self) -> None:
        """Add substations that contain buses in the view."""
        sub_ids: set[str] = set()

        for bus in self.result.buses:
            if bus.substation_id:
                sub_ids.add(bus.substation_id)

        for sub_id in sub_ids:
            sub = self.graph.get_substation(sub_id)
            if sub:
                self.result.substations.append(sub)

    def _create_stub_buses(self, station_sub_id: str) -> None:
        """Create stub buses for external connections in station detail mode."""
        # Find branches with one endpoint outside the station
        external_bus_ids: set[str] = set()

        for branch in self.result.ac_branches:
            # Check if either endpoint is outside the station
            from_bus = self.graph.get_bus(branch.from_bus_id)
            to_bus = self.graph.get_bus(branch.to_bus_id)

            if from_bus and from_bus.substation_id != station_sub_id:
                external_bus_ids.add(branch.from_bus_id)
            if to_bus and to_bus.substation_id != station_sub_id:
                external_bus_ids.add(branch.to_bus_id)

        # Create stub bus models for external buses
        for ext_bus_id in external_bus_ids:
            ext_bus = self.graph.get_bus(ext_bus_id)
            if ext_bus:
                stub_bus = BusModel(
                    id=f"stub::{ext_bus.id}",
                    psse_number=ext_bus.psse_number,
                    name=f"[Stub] {ext_bus.name}",
                    base_kv=ext_bus.base_kv,
                    area=ext_bus.area,
                    zone=ext_bus.zone,
                    substation_id=ext_bus.substation_id,
                    in_service=ext_bus.in_service,
                    metadata={"is_stub": True, "original_bus_id": ext_bus.id},
                )
                self.result.buses.append(stub_bus)
                self.result.bfs_depth[stub_bus.id] = -1  # Special marker for stubs


def slice_view(graph: CaseGraph, spec: ViewSpec) -> SliceResult:
    """
    Slice a graph according to a view specification.

    Args:
        graph: CaseGraph to slice
        spec: ViewSpec defining the view parameters

    Returns:
        SliceResult with sliced data
    """
    timer = OperationTimer(f"Slice view mode={spec.mode.value}", log_phases=True)

    timer.start_phase("init_slicer")
    slicer = ViewSlicer(graph, spec)
    timer.end_phase("init_slicer")

    timer.start_phase("perform_slice")
    result = slicer.slice()
    timer.end_phase("perform_slice", count=len(result.buses))

    timer.set_count("buses", len(result.buses))
    timer.set_count("branches", len(result.ac_branches))
    timer.set_count("equipment", len(result.equipment))
    timer.set_count("xfmr3", len(result.transformers3w))

    report = timer.finish()
    logger.info(report.summary())

    return result
