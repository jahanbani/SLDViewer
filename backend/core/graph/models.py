"""
Pydantic v2 data models for the SLD Viewer.

All models follow these conventions:
- metadata: dict = {} for forward compatibility
- in_service: bool = True (no redundant status string)
- psse_number for user-facing bus ID
- Optional fields are None if unavailable
"""
from datetime import datetime, timezone
from enum import Enum
from hashlib import md5
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, Field


# =============================================================================
# Deterministic ID Helpers
# =============================================================================


def make_case_namespace(file_id: str) -> str:
    """
    Create a deterministic namespace for a case file.

    Args:
        file_id: The unique file identifier

    Returns:
        A short hash string derived from the file_id (first 16 chars of MD5)
    """
    # Use MD5 for speed - we just need determinism, not cryptographic security
    return md5(file_id.encode()).hexdigest()[:16]


def make_deterministic_id(namespace: str, key: str) -> str:
    """
    Generate a deterministic hash-based ID.

    Args:
        namespace: The case namespace (from make_case_namespace)
        key: A unique key string for this element

    Returns:
        A deterministic ID string (MD5 hash)
    """
    return md5(f"{namespace}::{key}".encode()).hexdigest()


def make_deterministic_id_fast(namespace: str, key: str) -> str:
    """
    Fast version of make_deterministic_id using MD5.

    This is now the same as make_deterministic_id since MD5 is already fast.
    Kept for API compatibility.
    """
    return md5(f"{namespace}::{key}".encode()).hexdigest()


def get_namespace_uuid(namespace: str) -> str:
    """
    Get namespace string (kept for API compatibility).

    With MD5-based IDs, no UUID conversion is needed.
    """
    return namespace


def make_bus_id(namespace: str, psse_number: int) -> str:
    """Generate deterministic bus ID."""
    return make_deterministic_id(namespace, f"bus::{psse_number}")


def make_ac_branch_id(
    namespace: str,
    kind: str,
    from_psse: int,
    to_psse: int,
    circuit: str | None = None,
    index_hint: int = 0,
) -> str:
    """Generate deterministic AC branch ID."""
    circuit_str = circuit or ""
    return make_deterministic_id(
        namespace, f"ac::{kind}::{from_psse}::{to_psse}::{circuit_str}::{index_hint}"
    )


def make_transformer3w_id(
    namespace: str,
    bus1_psse: int,
    bus2_psse: int,
    bus3_psse: int,
    name: str | None = None,
) -> str:
    """Generate deterministic 3-winding transformer ID."""
    name_str = name or ""
    return make_deterministic_id(
        namespace, f"xfmr3::{bus1_psse}::{bus2_psse}::{bus3_psse}::{name_str}"
    )


def make_equipment_id(
    namespace: str,
    kind: str,
    bus_psse: int,
    name: str | None = None,
    index_hint: int = 0,
) -> str:
    """Generate deterministic equipment ID."""
    name_str = name or ""
    return make_deterministic_id(
        namespace, f"eq::{kind}::{bus_psse}::{name_str}::{index_hint}"
    )


def make_converter_id(namespace: str, dc_id: str, side: Literal["A", "B"]) -> str:
    """Generate deterministic converter ID."""
    return make_deterministic_id(namespace, f"conv::{dc_id}::{side}")


def make_dc_link_id(
    namespace: str, technology: str, conv_a_id: str, conv_b_id: str
) -> str:
    """Generate deterministic DC link ID."""
    return make_deterministic_id(namespace, f"dc::{technology}::{conv_a_id}::{conv_b_id}")


def make_substation_id(namespace: str, name: str, index: int = 0) -> str:
    """Generate deterministic substation ID."""
    return make_deterministic_id(namespace, f"substation::{name}::{index}")


# =============================================================================
# Enums
# =============================================================================


class EquipmentKind(str, Enum):
    """Types of equipment that can be attached to a bus."""

    GENERATOR = "GENERATOR"
    LOAD = "LOAD"
    SHUNT_FIXED = "SHUNT_FIXED"
    SHUNT_SWITCHED = "SHUNT_SWITCHED"
    SVC = "SVC"
    STATCOM = "STATCOM"
    FACTS = "FACTS"
    CONVERTER_CSC = "CONVERTER_CSC"
    CONVERTER_VSC = "CONVERTER_VSC"
    OTHER = "OTHER"


class BranchKind(str, Enum):
    """Types of 2-terminal AC branches."""

    LINE = "line"
    XFMR2 = "xfmr2"
    SWITCH = "switch"
    SERIES = "series"


class DcTechnology(str, Enum):
    """DC link technology types."""

    TTDC = "ttdc"  # Two-terminal DC (classic HVDC)
    VSCDC = "vscdc"  # VSC DC


class ViewMode(str, Enum):
    """View modes for the SLD viewer."""

    BUS = "bus"
    SUBSTATION = "substation"
    STATION_DETAIL = "station_detail"


class TopologyMode(str, Enum):
    """Topology connectivity modes."""

    AS_MODELED = "as_modeled"
    ENERGIZED_ONLY = "energized_only"


class TerminalMode(str, Enum):
    """Terminal node rendering modes."""

    EXPLICIT_NODES = "explicit_nodes"
    REDUCED = "reduced"


# =============================================================================
# Core Models
# =============================================================================


class BusModel(BaseModel):
    """Power system bus (node)."""

    id: str
    psse_number: int
    name: str
    base_kv: float
    area: int | None = None
    zone: int | None = None
    owner: int | None = None
    in_service: bool = True
    vm: float | None = None  # Voltage magnitude (pu)
    va: float | None = None  # Voltage angle (deg)
    vmax: float | None = None
    vmin: float | None = None
    substation_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    metadata: dict = Field(default_factory=dict)


class AcBranchModel(BaseModel):
    """2-terminal AC branch (line, transformer, switch, series device)."""

    id: str
    from_bus_id: str
    to_bus_id: str
    circuit: str | None = None
    kind: BranchKind
    in_service: bool = True
    is_closed: bool | None = None  # Meaningful for switches
    r: float | None = None
    x: float | None = None
    b: float | None = None
    g: float | None = None
    rate_a: float | None = None
    rate_b: float | None = None
    rate_c: float | None = None
    effective_rate_mva: float | None = None  # Computed: rate_a || rate_b || rate_c
    length_km: float | None = None
    tap_module: float | None = None
    tap_phase_deg: float | None = None
    p_from_mw: float | None = None
    q_from_mvar: float | None = None
    p_to_mw: float | None = None
    q_to_mvar: float | None = None
    metadata: dict = Field(default_factory=dict)

    def model_post_init(self, __context) -> None:
        """Compute effective_rate_mva if not set."""
        if self.effective_rate_mva is None:
            self.effective_rate_mva = self.rate_a or self.rate_b or self.rate_c


class Transformer3WModel(BaseModel):
    """3-winding transformer (multi-terminal device)."""

    id: str
    name: str | None = None
    bus1_id: str
    bus2_id: str
    bus3_id: str
    in_service: bool = True
    leg1_in_service: bool = True  # bus1 leg
    leg2_in_service: bool = True  # bus2 leg
    leg3_in_service: bool = True  # bus3 leg
    metadata: dict = Field(default_factory=dict)


class EquipmentModel(BaseModel):
    """Single-terminal equipment attached to a bus."""

    id: str
    bus_id: str
    kind: EquipmentKind
    name: str | None = None
    in_service: bool = True
    p_mw: float | None = None
    q_mvar: float | None = None
    dc_bus_id: str | None = None  # Future: MTDC
    metadata: dict = Field(default_factory=dict)


class DcLinkModel(BaseModel):
    """Point-to-point DC link between converters."""

    id: str
    technology: DcTechnology
    from_converter_id: str
    to_converter_id: str
    in_service: bool = True
    rating_mw: float | None = None
    p_from_mw: float | None = None
    p_to_mw: float | None = None
    losses_mw: float | None = None
    metadata: dict = Field(default_factory=dict)


class SubstationModel(BaseModel):
    """Substation grouping of buses."""

    id: str
    name: str
    area: int | None = None
    zone: int | None = None
    voltage_levels: list[float] = Field(default_factory=list)
    nominal_kv: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    metadata: dict = Field(default_factory=dict)  # Include name_source


# =============================================================================
# API Models
# =============================================================================


class CaseSummary(BaseModel):
    """Summary of a parsed case file."""

    file_id: str
    format: Literal["raw", "rawx"]
    bus_count: int
    ac_branch_count: int
    transformer3w_count: int
    equipment_count: int
    dc_link_count: int
    substation_count: int
    voltage_levels: list[float] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)
    created_at_iso: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ViewSpec(BaseModel):
    """Request specification for generating a view."""

    mode: ViewMode = ViewMode.BUS
    center_bus_numbers: list[int] | None = None
    center_substation_ids: list[str] | None = None
    max_depth: int = 1
    node_limit: int = 400
    edge_limit: int = 800
    include_equipment: bool = True
    include_dc: bool = True
    include_switches: bool = True
    topology_mode: TopologyMode = TopologyMode.AS_MODELED
    terminal_mode: TerminalMode = TerminalMode.EXPLICIT_NODES
    terminal_limit: int = 2000
    max_terminals_per_bus_render: int = 24
    voltage_kv_min: float | None = None
    voltage_kv_max: float | None = None
    area_ids: list[int] | None = None
    zone_ids: list[int] | None = None
    collapse_junction_buses: bool = False


class ViewResult(BaseModel):
    """Backend internal response for a view."""

    buses: list[BusModel] = Field(default_factory=list)
    ac_branches: list[AcBranchModel] = Field(default_factory=list)
    transformers3w: list[Transformer3WModel] = Field(default_factory=list)
    equipment: list[EquipmentModel] = Field(default_factory=list)
    dc_links: list[DcLinkModel] = Field(default_factory=list)
    substations: list[SubstationModel] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


class CytoscapePayload(BaseModel):
    """API response with Cytoscape.js elements (NO positions)."""

    elements: dict = Field(default_factory=lambda: {"nodes": [], "edges": []})
    meta: dict = Field(default_factory=dict)
