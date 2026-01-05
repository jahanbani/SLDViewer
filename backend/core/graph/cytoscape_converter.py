"""
Cytoscape payload converter.

Converts SliceResult to Cytoscape.js elements format.
Creates terminal nodes and proper edge structure (terminal→terminal, not bus→bus).
NO positions are included (frontend owns geometry).
"""
from collections import defaultdict
from typing import Any

from backend.core.timing import OperationTimer, logger

from backend.core.graph.models import (
    BusModel,
    AcBranchModel,
    Transformer3WModel,
    EquipmentModel,
    DcLinkModel,
    SubstationModel,
    CytoscapePayload,
    ViewSpec,
    TerminalMode,
    BranchKind,
    EquipmentKind,
)
from backend.core.graph.slicer import SliceResult


def _make_terminal_id(bus_id: str, connection_id: str) -> str:
    """Generate a terminal node ID."""
    return f"term::{bus_id}::{connection_id}"


def _make_bus_stub_edge_id(bus_id: str, terminal_id: str) -> str:
    """Generate a bus_stub edge ID."""
    return f"stub_edge::{bus_id}::{terminal_id}"


class CytoscapeConverter:
    """
    Converts a SliceResult to Cytoscape.js payload format.

    Creates:
    - Bus nodes
    - Terminal nodes (connection points on buses)
    - Transformer nodes (2W and 3W)
    - Equipment nodes
    - bus_stub edges (bus→terminal, hidden in UI)
    - branch edges (terminal→terminal)
    - equipment_link edges (bus→equipment)
    - dc_link edges (converter→converter)
    """

    def __init__(
        self,
        slice_result: SliceResult,
        spec: ViewSpec,
        full_network_connection_counts: dict[str, int] | None = None,
    ):
        """
        Initialize converter.

        Args:
            slice_result: SliceResult to convert
            spec: ViewSpec with rendering options
            full_network_connection_counts: Connection counts from full network (not slice).
                Used for determining circle vs busbar rendering.
        """
        self.result = slice_result
        self.spec = spec

        # Output containers
        self.nodes: list[dict] = []
        self.edges: list[dict] = []

        # Track created elements
        self._terminal_ids: set[str] = set()
        self._bus_ids: set[str] = set()

        # Connection counts per bus (for circle vs busbar rendering)
        # Use full network counts if provided, otherwise will be computed from slice
        self._full_network_counts = full_network_connection_counts or {}

        # Parallel edge tracking for offset computation
        self._parallel_groups: dict[str, list[str]] = defaultdict(list)

    def convert(self) -> CytoscapePayload:
        """
        Convert slice result to Cytoscape payload.

        Returns:
            CytoscapePayload with nodes and edges (no positions)
        """
        # Create bus nodes
        self._create_bus_nodes()

        # Create transformer nodes (both 2W and 3W)
        self._create_transformer2w_nodes()
        self._create_transformer3w_nodes()

        # Create terminals and edges for branches
        self._create_branch_terminals_and_edges()

        # Create terminals and edges for 3W transformers
        self._create_transformer3w_terminals_and_edges()

        # Create equipment nodes and links
        self._create_equipment_nodes()

        # Create DC link edges
        self._create_dc_link_edges()

        # Compute parallel edge hints
        self._compute_parallel_hints()

        # Build metadata
        meta = {
            "truncated": self.result.truncated,
            "truncation_reason": self.result.truncation_reason,
            "warnings": self.result.warnings,
            "seed_bus_numbers": self.result.seed_bus_numbers,
            "effective_max_depth": self.result.effective_max_depth,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "bus_count": len(self.result.buses),
            "terminal_count": len(self._terminal_ids),
        }

        return CytoscapePayload(
            elements={"nodes": self.nodes, "edges": self.edges},
            meta=meta,
        )

    def _count_bus_connections(self) -> dict[str, int]:
        """
        Count connections per bus for rendering decisions.

        Connection types counted:
        - AC branches (lines, switches, series, xfmr2)
        - Transformer 3W legs
        - Equipment (generators, loads, shunts, converters)

        Returns:
            Dict mapping bus_id to connection count
        """
        counts: dict[str, int] = defaultdict(int)

        # Count AC branches (each branch connects 2 buses)
        for branch in self.result.ac_branches:
            counts[branch.from_bus_id] += 1
            counts[branch.to_bus_id] += 1

        # Count 3W transformer legs (each leg connects 1 bus)
        for xfmr3 in self.result.transformers3w:
            counts[xfmr3.bus1_id] += 1
            counts[xfmr3.bus2_id] += 1
            counts[xfmr3.bus3_id] += 1

        # Count equipment
        for eq in self.result.equipment:
            counts[eq.bus_id] += 1

        return counts

    def _create_bus_nodes(self) -> None:
        """Create bus nodes."""
        for bus in self.result.buses:
            self._bus_ids.add(bus.id)

            # Determine render kind
            render_kind = "bus"
            if self.spec.collapse_junction_buses:
                # Check if this is a junction bus
                # (would need access to graph for full check)
                pass  # Keep as "bus" by default

            # Check if this is a stub bus
            is_stub = bus.metadata.get("is_stub", False)
            if is_stub:
                render_kind = "stub"

            # Get connection count from FULL network (not slice)
            # This ensures a bus doesn't become a circle just because it's at the edge of a view
            conn_count = self._full_network_counts.get(bus.id, 0)
            # isCircleBus: true if 1-2 connections in full network
            is_circle_bus = conn_count <= 2

            node = {
                "data": {
                    "id": bus.id,
                    "kind": "bus",
                    "psse_number": bus.psse_number,
                    "name": bus.name,
                    "base_kv": bus.base_kv,
                    "area": bus.area,
                    "zone": bus.zone,
                    "substation_id": bus.substation_id,
                    "inService": bus.in_service,
                    "bfs_depth": self.result.bfs_depth.get(bus.id, 0),
                    "orientation": "VERT",  # Default; frontend can toggle
                    "renderKind": render_kind,
                    "connectionCount": conn_count,  # Full network count
                    "isCircleBus": is_circle_bus,  # For CSS: true = render as circle
                }
            }

            self.nodes.append(node)

    def _create_transformer2w_nodes(self) -> None:
        """Create 2-winding transformer symbol nodes."""
        for branch in self.result.ac_branches:
            if branch.kind != BranchKind.XFMR2:
                continue

            xfmr_node_id = f"xfmr2::{branch.id}"

            node = {
                "data": {
                    "id": xfmr_node_id,
                    "kind": "transformer2",
                    "branchId": branch.id,
                    "inService": branch.in_service,
                    "fromBusId": branch.from_bus_id,
                    "toBusId": branch.to_bus_id,
                }
            }

            self.nodes.append(node)

    def _create_transformer3w_nodes(self) -> None:
        """Create 3-winding transformer symbol nodes."""
        for xfmr in self.result.transformers3w:
            xfmr_node_id = f"xfmr3::{xfmr.id}"

            node = {
                "data": {
                    "id": xfmr_node_id,
                    "kind": "transformer3",
                    "transformerId": xfmr.id,
                    "name": xfmr.name,
                    "inService": xfmr.in_service,
                    "bus1Id": xfmr.bus1_id,
                    "bus2Id": xfmr.bus2_id,
                    "bus3Id": xfmr.bus3_id,
                }
            }

            self.nodes.append(node)

    def _create_branch_terminals_and_edges(self) -> None:
        """Create terminals and edges for AC branches."""
        for branch in self.result.ac_branches:
            if branch.kind == BranchKind.XFMR2:
                # 2W transformers have special handling (via transformer node)
                self._create_xfmr2_terminals_and_edges(branch)
            else:
                # Line/switch/series: terminal→terminal edges
                self._create_simple_branch_terminals_and_edges(branch)

    def _create_simple_branch_terminals_and_edges(self, branch: AcBranchModel) -> None:
        """Create terminals and edges for line/switch/series branches."""
        from_bus_id = branch.from_bus_id
        to_bus_id = branch.to_bus_id

        # Skip if buses not in view
        if from_bus_id not in self._bus_ids or to_bus_id not in self._bus_ids:
            return

        # Create terminals
        from_term_id = self._ensure_terminal(
            from_bus_id,
            branch.id,
            connection_kind="ac_branch",
            peer_bus_ids=[to_bus_id],
        )
        to_term_id = self._ensure_terminal(
            to_bus_id,
            branch.id,
            connection_kind="ac_branch",
            peer_bus_ids=[from_bus_id],
        )

        # Create branch edge (terminal→terminal)
        edge = {
            "data": {
                "id": f"branch::{branch.id}",
                "kind": "branch",
                "branchKind": branch.kind.value,
                "source": from_term_id,
                "target": to_term_id,
                "inService": branch.in_service,
                "isClosed": branch.is_closed,
                "circuit": branch.circuit,
                # Parallel edge hints (computed later)
                "parallel_key": None,
                "parallel_index": None,
                "parallel_count": None,
            }
        }

        # Track for parallel computation
        parallel_key = self._make_parallel_key(from_bus_id, to_bus_id, branch.kind.value)
        self._parallel_groups[parallel_key].append(edge["data"]["id"])
        edge["data"]["parallel_key"] = parallel_key

        self.edges.append(edge)

    def _create_xfmr2_terminals_and_edges(self, branch: AcBranchModel) -> None:
        """Create terminals and edges for 2W transformers (via transformer node)."""
        from_bus_id = branch.from_bus_id
        to_bus_id = branch.to_bus_id
        xfmr_node_id = f"xfmr2::{branch.id}"

        if from_bus_id not in self._bus_ids or to_bus_id not in self._bus_ids:
            return

        # Create terminals pointing to transformer
        from_term_id = self._ensure_terminal(
            from_bus_id,
            f"{branch.id}_from",
            connection_kind="xfmr2_leg",
            peer_bus_ids=[to_bus_id],
            peer_transformer_id=xfmr_node_id,
        )
        to_term_id = self._ensure_terminal(
            to_bus_id,
            f"{branch.id}_to",
            connection_kind="xfmr2_leg",
            peer_bus_ids=[from_bus_id],
            peer_transformer_id=xfmr_node_id,
        )

        # Create xfmr2_leg edges (terminal→transformer node)
        from_leg_edge = {
            "data": {
                "id": f"xfmr2_leg::{branch.id}::from",
                "kind": "xfmr2_leg",
                "source": from_term_id,
                "target": xfmr_node_id,
                "inService": branch.in_service,
            }
        }
        to_leg_edge = {
            "data": {
                "id": f"xfmr2_leg::{branch.id}::to",
                "kind": "xfmr2_leg",
                "source": to_term_id,
                "target": xfmr_node_id,
                "inService": branch.in_service,
            }
        }

        self.edges.append(from_leg_edge)
        self.edges.append(to_leg_edge)

    def _create_transformer3w_terminals_and_edges(self) -> None:
        """Create terminals and edges for 3W transformers."""
        for xfmr in self.result.transformers3w:
            xfmr_node_id = f"xfmr3::{xfmr.id}"

            legs = [
                (xfmr.bus1_id, xfmr.leg1_in_service, "leg1"),
                (xfmr.bus2_id, xfmr.leg2_in_service, "leg2"),
                (xfmr.bus3_id, xfmr.leg3_in_service, "leg3"),
            ]

            for bus_id, leg_in_service, leg_name in legs:
                if bus_id not in self._bus_ids:
                    continue

                # Create terminal
                term_id = self._ensure_terminal(
                    bus_id,
                    f"{xfmr.id}_{leg_name}",
                    connection_kind="xfmr3_leg",
                    peer_transformer_id=xfmr_node_id,
                )

                # Create leg edge
                leg_edge = {
                    "data": {
                        "id": f"xfmr3_leg::{xfmr.id}::{leg_name}",
                        "kind": "xfmr3_leg",
                        "source": term_id,
                        "target": xfmr_node_id,
                        "inService": xfmr.in_service and leg_in_service,
                        "legName": leg_name,
                    }
                }

                self.edges.append(leg_edge)

    def _ensure_terminal(
        self,
        bus_id: str,
        connection_id: str,
        connection_kind: str,
        peer_bus_ids: list[str] | None = None,
        peer_transformer_id: str | None = None,
    ) -> str:
        """
        Ensure a terminal node exists and return its ID.

        Creates the terminal if it doesn't exist, along with the bus_stub edge.
        """
        term_id = _make_terminal_id(bus_id, connection_id)

        if term_id in self._terminal_ids:
            return term_id

        self._terminal_ids.add(term_id)

        # Create terminal node
        terminal_node = {
            "data": {
                "id": term_id,
                "kind": "terminal",
                "parentBusId": bus_id,
                "connectionId": connection_id,
                "connectionKind": connection_kind,
                "peerBusIds": peer_bus_ids or [],
                "peerTransformerId": peer_transformer_id,
                "peerTargetKind": "transformer_node" if peer_transformer_id else "terminal",
                # slotIndex and side are NOT included (frontend computes)
            }
        }
        self.nodes.append(terminal_node)

        # Create bus_stub edge (bus→terminal, hidden in UI)
        stub_edge_id = _make_bus_stub_edge_id(bus_id, term_id)
        stub_edge = {
            "data": {
                "id": stub_edge_id,
                "kind": "bus_stub",
                "source": bus_id,
                "target": term_id,
                "inService": True,
            }
        }
        self.edges.append(stub_edge)

        return term_id

    def _create_equipment_nodes(self) -> None:
        """Create equipment nodes with dedicated terminals and equipment_link edges."""
        for eq in self.result.equipment:
            if eq.bus_id not in self._bus_ids:
                continue

            # Map equipment kind to simpler class
            eq_class = self._map_equipment_class(eq.kind)

            eq_node = {
                "data": {
                    "id": eq.id,
                    "kind": "equipment",
                    "equipmentKind": eq.kind.value,
                    "equipmentClass": eq_class,
                    "name": eq.name,
                    "busId": eq.bus_id,
                    "inService": eq.in_service,
                    "p_mw": eq.p_mw,
                    "q_mvar": eq.q_mvar,
                }
            }
            self.nodes.append(eq_node)

            # Create a dedicated terminal for this equipment (separate from line terminals)
            # Equipment terminals use connection_kind="equipment" to distinguish them
            eq_term_id = self._ensure_terminal(
                eq.bus_id,
                f"eq_{eq.id}",  # Unique connection ID for this equipment
                connection_kind="equipment",
                peer_bus_ids=None,
                peer_transformer_id=None,
            )

            # Create equipment_link edge (terminal→equipment, not bus→equipment)
            # Include equipmentKind for style-based coloring
            link_edge = {
                "data": {
                    "id": f"eq_link::{eq.id}",
                    "kind": "equipment_link",
                    "equipmentKind": eq.kind.value,
                    "source": eq_term_id,
                    "target": eq.id,
                    "inService": eq.in_service,
                }
            }
            self.edges.append(link_edge)

    def _map_equipment_class(self, kind: EquipmentKind) -> str:
        """Map equipment kind to rendering class."""
        mapping = {
            EquipmentKind.GENERATOR: "gen",
            EquipmentKind.LOAD: "load",
            EquipmentKind.SHUNT_FIXED: "shunt",
            EquipmentKind.SHUNT_SWITCHED: "shunt",
            EquipmentKind.SVC: "svc",
            EquipmentKind.STATCOM: "statcom",
            EquipmentKind.FACTS: "facts",
            EquipmentKind.CONVERTER_CSC: "converter",
            EquipmentKind.CONVERTER_VSC: "converter",
            EquipmentKind.OTHER: "other",
        }
        return mapping.get(kind, "other")

    def _create_dc_link_edges(self) -> None:
        """Create DC link edges (converter→converter)."""
        for dc in self.result.dc_links:
            # Find converter nodes
            from_conv_id = dc.from_converter_id
            to_conv_id = dc.to_converter_id

            # Check if converters are in view (as equipment nodes)
            from_conv = next(
                (eq for eq in self.result.equipment if eq.id == from_conv_id), None
            )
            to_conv = next(
                (eq for eq in self.result.equipment if eq.id == to_conv_id), None
            )

            if not from_conv or not to_conv:
                continue

            dc_edge = {
                "data": {
                    "id": f"dc_link::{dc.id}",
                    "kind": "dc_link",
                    "source": from_conv_id,
                    "target": to_conv_id,
                    "technology": dc.technology.value,
                    "inService": dc.in_service,
                    "rating_mw": dc.rating_mw,
                }
            }
            self.edges.append(dc_edge)

    def _make_parallel_key(self, bus_a: str, bus_b: str, kind: str) -> str:
        """Create a key for parallel edge grouping."""
        # Normalize bus order
        if bus_a > bus_b:
            bus_a, bus_b = bus_b, bus_a
        return f"{bus_a}::{bus_b}::{kind}"

    def _compute_parallel_hints(self) -> None:
        """Compute parallel edge indices and counts."""
        # Build a map from edge ID to edge data
        edge_map = {e["data"]["id"]: e["data"] for e in self.edges}

        for parallel_key, edge_ids in self._parallel_groups.items():
            if len(edge_ids) <= 1:
                continue

            # Sort edges deterministically by (circuit, id)
            sorted_ids = sorted(
                edge_ids,
                key=lambda eid: (edge_map.get(eid, {}).get("circuit") or "", eid),
            )

            for idx, edge_id in enumerate(sorted_ids):
                if edge_id in edge_map:
                    edge_map[edge_id]["parallel_index"] = idx
                    edge_map[edge_id]["parallel_count"] = len(sorted_ids)


def convert_to_cytoscape(
    slice_result: SliceResult,
    spec: ViewSpec,
    full_network_connection_counts: dict[str, int] | None = None,
) -> CytoscapePayload:
    """
    Convert a SliceResult to Cytoscape payload.

    Args:
        slice_result: SliceResult to convert
        spec: ViewSpec with rendering options
        full_network_connection_counts: Connection counts from full network.
            Used for circle vs busbar rendering decisions.

    Returns:
        CytoscapePayload with nodes and edges (no positions)
    """
    timer = OperationTimer("Cytoscape conversion", log_phases=True)

    timer.start_phase("init_converter")
    converter = CytoscapeConverter(slice_result, spec, full_network_connection_counts)
    timer.end_phase("init_converter")

    timer.start_phase("convert_elements")
    payload = converter.convert()
    timer.end_phase("convert_elements", count=len(payload.elements))

    timer.set_count("nodes", len(converter.nodes))
    timer.set_count("edges", len(converter.edges))
    timer.set_count("terminals", len(converter._terminal_ids))

    report = timer.finish()
    logger.info(report.summary())

    return payload
