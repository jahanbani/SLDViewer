"""Canonical data models for SLD Viewer.

This module defines Pydantic v2 models for power system data:
- Substations, Buses, Branches, and Equipment
- View specifications and results for graph visualization
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ============================================================================
# Branch Types
# ============================================================================

BranchType = Literal["line", "xfmr", "xfmr3", "switch", "dc_line", "hvdc"]


# ============================================================================
# Equipment Types
# ============================================================================

class EquipmentType(str, Enum):
    """Type of equipment attached to a bus."""

    GENERATOR = "generator"
    LOAD = "load"
    SHUNT = "shunt"  # fixed shunt
    SVC = "svc"  # switched shunt / SVC
    STATCOM = "statcom"
    VSC_CONVERTER = "vsc_converter"
    CSC_CONVERTER = "csc_converter"
    OTHER = "other"


# ============================================================================
# Core Domain Models
# ============================================================================

class SubstationModel(BaseModel):
    """Represents a substation containing one or more buses.

    Substations can be defined explicitly in PSSE v35+ files or inferred
    from topology and geography. Each bus belongs to at most one substation.
    """

    id: str  # Internal UUID
    name: str  # From PSSE v35 if present, else inferred
    area: int | None = None
    zone: int | None = None

    nominal_kv: float | None = None  # e.g. max(base_kv) of member buses
    voltage_levels: list[float] = []  # unique base_kv values of member buses

    latitude: float | None = None
    longitude: float | None = None


class BusModel(BaseModel):
    """Represents a single bus (node) in the power system.

    Each bus has a PSSE bus number (user-facing identifier) and an internal
    UUID used for graph operations. Buses may belong to a substation.
    """

    id: str  # Internal UUID
    psse_number: int  # PSSE bus number
    name: str
    base_kv: float
    area: int
    zone: int
    owner: int

    vm: float | None = None  # Voltage magnitude (pu)
    va: float | None = None  # Voltage angle (degrees)
    vmax: float | None = None
    vmin: float | None = None

    substation_id: str | None = None  # SubstationModel.id
    latitude: float | None = None
    longitude: float | None = None


class BranchModel(BaseModel):
    """Represents a branch (line, transformer, switch, or DC link) between buses.

    Each branch is directional: from_bus_id → to_bus_id. Multiple parallel
    circuits between the same buses are separate BranchModel instances with
    different IDs. Power flow values follow the branch's orientation.
    """

    id: str
    from_bus_id: str
    to_bus_id: str
    circuit: str
    type: BranchType

    # Positive sequence
    r: float
    x: float
    b: float
    g: float

    # Zero sequence
    r0: float | None = None
    x0: float | None = None
    b0: float | None = None
    g0: float | None = None

    # Negative sequence
    r2: float | None = None
    x2: float | None = None
    b2: float | None = None
    g2: float | None = None

    rate_a: float | None = None
    rate_b: float | None = None
    rate_c: float | None = None
    rating_mva: float = 1.0  # main rating (RATEA or fallback)

    tap_module: float | None = None
    tap_phase: float | None = None
    length: float | None = None

    p_from_mw: float | None = None  # Power flow from bus (MW)
    q_from_mvar: float | None = None  # Reactive power flow from bus (MVAr)
    p_to_mw: float | None = None  # Power flow to bus (MW)
    q_to_mvar: float | None = None  # Reactive power flow to bus (MVAr)


class EquipmentModel(BaseModel):
    """Represents equipment attached to a bus (generators, loads, shunts, etc.).

    Equipment is not part of the topology graph but is attached to buses.
    When a bus is included in a view, all its equipment (subject to filters)
    is also included as explicit nodes.
    """

    id: str  # internal UUID
    bus_id: str  # BusModel.id
    type: EquipmentType
    name: str | None = None

    status: bool | None = None  # in-service / out-of-service

    p_mw: float | None = None  # Active power (MW)
    q_mvar: float | None = None  # Reactive power (MVAr)

    metadata: dict[str, Any] = {}  # Additional PSSE fields (mbase, control modes, etc.)


# ============================================================================
# View Models
# ============================================================================

class ViewMode(str, Enum):
    """Mode for graph view generation."""

    BUS = "bus"  # Bus-level view with BFS from center buses
    SUBSTATION = "substation"  # Substation-level overview
    STATION_DETAIL = "station_detail"  # Detailed view of one substation


class Filters(BaseModel):
    """Filters applied to a view specification.

    Filters restrict which buses, branches, and equipment are included
    in the view based on voltage, type, area, etc.
    """

    voltage_min: float | None = None
    voltage_max: float | None = None
    branch_types: list[BranchType] | None = None
    areas: list[int] | None = None

    include_equipment: bool = True
    equipment_types: list[EquipmentType] | None = None  # None/[] = all


class ViewSpec(BaseModel):
    """Specification for generating a graph view.

    Defines the mode, center points, BFS depth, filters, and other parameters
    that control which buses, branches, substations, and equipment are included
    in the view result.
    """

    mode: ViewMode = ViewMode.BUS
    center_bus_numbers: list[int] | None = None
    center_substation_ids: list[str] | None = None
    degrees: int = 1  # BFS depth
    include_neighbor_substations: bool = True
    filters: Filters = Field(default_factory=Filters)
    layout: str | dict[str, Any] = "preset"
    limit: int | None = None  # default depends on mode


class ViewResult(BaseModel):
    """Result of a view generation operation.

    Contains all buses, branches, substations, and equipment included in
    the view, along with metadata about the view generation process.
    """

    buses: list[BusModel]
    branches: list[BranchModel]
    substations: list[SubstationModel]
    equipment: list[EquipmentModel]
    meta: dict[str, Any]  # View metadata (node counts, truncated status, etc.)

