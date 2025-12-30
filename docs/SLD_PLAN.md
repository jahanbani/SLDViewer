
# SLD Viewer Web Application – Architecture & Implementation Plan (v3, with Equipment)

## 1. Overview

Build an independent web-based Single Line Diagram (SLD) viewer for PSSE power system data.

* Use **VeraGrid** only for parsing RAWX files.
* Maintain our own **canonical models**, graph engine, and web UI.
* Design for **large networks** (~100k buses, ~110k branches).
* Default interaction model: **partial graph views**, not full-network hairballs.

**New requirement**:
Whenever we include a bus in a view, we want to show **all elements attached to it**:

* Generators
* Loads
* Fixed shunts and SVCs/FACTS
* HVDC converters, STATCOMs, etc.

These appear as **explicit symbols (nodes)** attached to the bus.

---

## 2. Architecture

### 2.1 Backend: RESTful API Service

* **Language / Framework**: Python 3.11+ (min 3.8 for VeraGrid) + FastAPI.
* **Models & config**: Pydantic v2 (>= 2.0).
* **Graph engine**: NetworkX MultiDiGraph (behind an abstraction).
* **Role of VeraGrid**: Only in `rawx_parser.py` to parse RAW/RAWX → our models.
* **Data format**: Cytoscape.js‑friendly JSON.
* **Performance**:

  * Parse once per file; cache graphs in memory (optional Redis later).
  * All normal views are **partial**; full-graph endpoint is debug-only.
  * Node caps per view mode.

### 2.2 Frontend: Web Application

* **Language / Framework**: React 18 + **TypeScript**.
* **Build tool**: Vite.
* **Graph renderer**: Cytoscape.js (with WebGL + perf options for bigger views).
* **Data fetching**: TanStack Query (React Query) in Phase 2+.
* **Error handling**: React Error Boundaries.
* **Design**:

  * Graph viewer with node/edge click → detail panel.
  * Controls to change **mode**, **degrees**, **filters**, **equipment visibility**.
  * API responses are clean JSON, consumable by React Native later.

---

## 3. Project Structure

```txt
SLDViewer/
├── backend/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app, CORS, startup/shutdown
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── files.py         # File upload/management
│   │   │   └── graphs.py        # /view and graph-related endpoints
│   ├── core/
│   │   ├── __init__.py
│   │   ├── graph/
│   │   │   ├── __init__.py
│   │   │   ├── models.py        # Bus, Branch, Substation, Equipment, ViewSpec, ...
│   │   │   ├── rawx_parser.py   # VeraGrid wrapper: RAWX → models
│   │   │   ├── substations.py   # Substation inference
│   │   │   ├── graph_builder.py # Build NetworkX graphs (bus/substation level)
│   │   │   ├── view_engine.py   # GraphHandle + ViewSpec → ViewResult (pure)
│   │   │   ├── layouts.py       # Layout domain (Phase 3+)
│   │   │   └── cytoscape_converter.py # ViewResult → Cytoscape JSON
│   │   └── config.py            # Pydantic Settings (env vars)
│   ├── storage/
│   │   └── user_files/          # Per-user file storage (configurable)
│   ├── tests/
│   │   ├── test_rawx_parser.py
│   │   ├── test_graph_builder.py
│   │   ├── test_cytoscape_converter.py
│   │   ├── test_view_engine.py
│   │   ├── test_substations.py          # Phase 2
│   │   ├── test_equipment_parsing.py    # Phase 2
│   │   └── test_view_engine_equipment.py
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── README.md
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── GraphViewer.tsx      # Main Cytoscape component
│   │   │   ├── BusSearch.tsx        # Bus search/expand
│   │   │   ├── DetailPanel.tsx      # Show details for bus/branch/equipment
│   │   │   └── ControlsPanel.tsx    # Mode, filters, equipment toggle
│   │   ├── services/
│   │   │   └── api.ts               # Typed API client
│   │   ├── hooks/
│   │   │   ├── useGraphView.ts      # Wraps /view via React Query
│   │   │   └── useCytoscape.ts      # Initialize Cytoscape
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── tsconfig.json
│   └── README.md
├── sample_data/
│   ├── small.rawx
│   ├── medium.rawx
│   └── large_100k.rawx
└── README.md
```

### Future (Phase 4+) Modules

Auth, DB, subscriptions, comparison service, etc. live under `core/security`, `core/db`, and extra routers as in your earlier plan. 

---

## 4. Canonical Data Models

All domain objects are Pydantic v2 models in `core/graph/models.py`.

### 4.1 SubstationModel

```python
class SubstationModel(BaseModel):
    id: str                       # Internal UUID
    name: str                     # From PSSE v35 if present, else inferred
    area: int | None = None
    zone: int | None = None

    nominal_kv: float | None = None      # e.g. max(base_kv) of member buses
    voltage_levels: list[float] = []     # unique base_kv values of member buses

    latitude: float | None = None
    longitude: float | None = None
```

* If a PSSE v35 SUBSTATION section exists, we fill from that.
* Otherwise, `substations.py` infers substations via topology + lat/lon. 

### 4.2 BusModel

```python
class BusModel(BaseModel):
    id: str                 # Internal UUID
    psse_number: int        # PSSE bus number
    name: str
    base_kv: float
    area: int
    zone: int
    owner: int

    vm: float | None = None
    va: float | None = None
    vmax: float | None = None
    vmin: float | None = None

    substation_id: str | None = None     # SubstationModel.id
    latitude: float | None = None
    longitude: float | None = None
```

* API uses `psse_number` for user-facing queries.
* Internal graph uses `id` (UUID) for everything.

### 4.3 BranchModel (lines/transformers/DC)

```python
BranchType = Literal["line", "xfmr", "xfmr3", "switch", "dc_line", "hvdc"]

class BranchModel(BaseModel):
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

    p_from_mw: float | None = None
    q_from_mvar: float | None = None
    p_to_mw: float | None = None
    q_to_mvar: float | None = None
```

**Directional convention**:

* The branch is oriented `from_bus_id → to_bus_id`.
* `p_from_mw > 0` means physical power flows in that direction; negative means opposite.

**Parallel circuits**:

* Each `BranchModel` is a separate parallel circuit; `id` is used as the NetworkX edge key so multiple edges between the same pair are preserved. 

### 4.4 EquipmentModel – all elements attached to buses

We capture *everything on the bus that is not a bus‑to‑bus branch*:

* Generators
* Loads
* Fixed shunts
* Switched shunts / SVCs / STATCOM
* HVDC converter terminals
* Others as needed

```python
class EquipmentType(str, Enum):
    GENERATOR = "generator"
    LOAD = "load"
    SHUNT = "shunt"              # fixed shunt
    SVC = "svc"                  # switched shunt / SVC
    STATCOM = "statcom"
    VSC_CONVERTER = "vsc_converter"
    CSC_CONVERTER = "csc_converter"
    OTHER = "other"

class EquipmentModel(BaseModel):
    id: str               # internal UUID
    bus_id: str           # BusModel.id
    type: EquipmentType
    name: str | None = None

    status: bool | None = None      # in-service / out-of-service

    p_mw: float | None = None
    q_mvar: float | None = None

    metadata: dict[str, Any] = {}
```

**Parsing** (Phase 2):

* PSSE GEN records → `type=GENERATOR`
* LOAD records → `type=LOAD`
* SHUNT/SVC/FACTS → `type=SHUNT` or `SVC` etc.
* HVDC terminals → `VSC_CONVERTER` or `CSC_CONVERTER`
* Additional PSSE fields (e.g. `mbase`, `pl`, `ql`, control modes) go in `metadata`
  – with some documented common keys for generators and loads.

### 4.5 Graph & View Models

We also define:

```python
class ViewMode(str, Enum):
    BUS = "bus"
    SUBSTATION = "substation"
    STATION_DETAIL = "station_detail"
    # Future: VOLTAGE_LEVEL = "voltage_level"

class Filters(BaseModel):
    voltage_min: float | None = None
    voltage_max: float | None = None
    branch_types: list[BranchType] | None = None
    areas: list[int] | None = None

    include_equipment: bool = True
    equipment_types: list[EquipmentType] | None = None  # None/[] = all

class ViewSpec(BaseModel):
    mode: ViewMode = ViewMode.BUS
    center_bus_numbers: list[int] | None = None
    center_substation_ids: list[str] | None = None
    degrees: int = 1
    include_neighbor_substations: bool = True
    filters: Filters = Field(default_factory=Filters)
    layout: str | dict[str, Any] = "preset"
    limit: int | None = None  # default depends on mode

class ViewResult(BaseModel):
    buses: list[BusModel]
    branches: list[BranchModel]
    substations: list[SubstationModel]
    equipment: list[EquipmentModel]
    meta: dict[str, Any]
```

---

## 5. Graph Structure & Substation Inference

### 5.1 NetworkX Graphs

**Bus-level graph**:

* `nx.MultiDiGraph`
* Nodes: bus IDs
* Edges: one per `BranchModel`, keyed by `branch.id`
* Used for BFS and bus‑mode views.

**Substation-level graph**:

* `nx.MultiDiGraph`
* Nodes: substation IDs
* For each branch, look up `from_bus.substation_id` and `to_bus.substation_id`.
* If they differ, create edge from `from_substation_id → to_substation_id`, keyed by `branch.id`.
* **No aggregation**: multiple circuits = multiple edges. 

**Equipment**:

* Equipment is *not* part of the topology graphs.
* `EquipmentModel` instances are stored in sidecar structures keyed by `bus_id`.
* They get **added to views** whenever their bus is included.

### 5.2 Substation Inference (`substations.py`)

**Goal**: handle mixed PSSE versions:

* Use SUBSTATION section if present (v35+).
* Otherwise infer substations based on topology + geography. 

**Algorithm v1**:

1. If PSSE v35 SUBSTATION exists:

   * Build `SubstationModel` from PSSE fields.
   * Map buses to substations directly.

2. Else:

   * Build a **strong-coupling bus graph**:

     * Nodes: buses
     * Edges: branches that are

       * zero-impedance (|r|+|x| ≈ 0), or
       * very small impedance (short lines), or
       * transformers (`xfmr` / `xfmr3`).
   * Take connected components as electrical clusters.
   * Use bus lat/lon to split a cluster if spatial extent is too large.
   * For each resulting cluster:

     * Build a `SubstationModel`:

       * name: heuristic (longest bus name, common prefix, etc.)
       * voltage_levels: distinct `base_kv` values in cluster.
       * nominal_kv: typically `max(voltage_levels)`.
       * area/zone: majority vote.
       * lat/lon: average/median of member buses.
     * Assign `substation_id` to buses in that cluster.

**Future options**:

* Manual override CSV: `bus_number,substation_name`.
* Debug view to inspect clusters.
* Alternative implementation using **pypowsybl** for import + substation layout. 

---

## 6. Unified API Design

Everything funnels through one core endpoint:

```http
POST /api/v1/graphs/{file_id}/view
```

### 6.1 Request Body (`ViewSpec`)

Example:

```json
{
  "mode": "bus",
  "center_bus_numbers": [100001],
  "center_substation_ids": null,
  "degrees": 2,
  "include_neighbor_substations": true,
  "filters": {
    "voltage_min": 115.0,
    "voltage_max": 345.0,
    "branch_types": ["line", "xfmr"],
    "areas": [101],
    "include_equipment": true,
    "equipment_types": ["generator", "load", "shunt"]
  },
  "layout": "preset",
  "limit": 500
}
```

* `center_bus_numbers`: used in BUS mode (and station_detail if you want to seed by a bus).
* `center_substation_ids`: used in SUBSTATION and STATION_DETAIL modes.
* `degrees`: BFS depth.
* `limit`: **max count of buses/substations**, depending on mode. Equipment is additive.

### 6.2 View Modes & Equipment Behavior

```python
class ViewMode(str, Enum):
    BUS = "bus"
    SUBSTATION = "substation"
    STATION_DETAIL = "station_detail"
```

**Common rule**:

* `limit` is always applied to **buses or substations only**:

  * BUS: max # of buses in view.
  * SUBSTATION: max # of substations in view.
* Equipment does **not** count towards `limit`. It is attached to included buses.

#### BUS mode

* Graph: bus-level.
* Seeds: `center_bus_numbers` → bus IDs.
* BFS: on bus graph, up to `degrees`, subject to `limit` (default `BUS_LIMIT_DEFAULT = 300`).
* Nodes in view:

  * Buses found by BFS.
  * If `filters.include_equipment` is true:

    * All equipment whose `bus_id` is in those buses and whose type is in `equipment_types` (or all if null).
* Edges in view:

  * All branches whose endpoints are both in the bus set.
  * Bus↔equipment edges (synthetic edges for visualization).

#### SUBSTATION mode

* Graph: substation-level.
* Seeds: `center_substation_ids`.
* BFS on substation graph, subject to `limit` (default `SUBSTATION_LIMIT_DEFAULT = 500`).
* Nodes:

  * Substations in the BFS frontier.
* Edges:

  * Branches mapped between those substations (one edge per branch; no aggregation).
* Equipment:

  * **MVP**: ignore `include_equipment` in this mode; do not draw equipment symbols (keep overview clean).
  * Optionally include equipment counts per substation in `meta` later.

#### STATION_DETAIL mode

* Required: exactly one `center_substation_id`.
* Nodes:

  * All buses where `bus.substation_id == center_substation_id`.
  * Stub nodes for neighboring substations (one stub per neighbor).
  * If `filters.include_equipment` is true:

    * All equipment for buses in this station (subject to type filter).
* Edges:

  * All branches between internal buses.
  * For branches from internal bus to a bus in another substation:

    * Edge from internal bus → neighbor stub (still **one per branch**).
  * Bus↔equipment edges.

### 6.3 Layout

Phase 1–2:

* `layout` is a string: `"preset"`, `"breadthfirst"`, etc.
* Equipment positioning: Radial arrangement around buses (frontend-side, Cytoscape layout)

Phase 3+:

* `layout` can be a `LayoutSpec` object, e.g.:

```json
{
  "layout": {
    "mode": "voltage_band",
    "y_by": "base_kv",
    "group_by": "area",
    "equipment_arrangement": "radial",  // or "grid", "force_directed"
    "equipment_collision_avoidance": true
  }
}
```

Backend may compute layouts (especially for station_detail) and return node `position` to Cytoscape as a "preset" layout. Equipment positions are computed alongside bus positions to avoid overlaps.

---

## 7. View Engine & Cytoscape Converter

### 7.1 View Engine

`view_engine.view(graph_handle: GraphHandle, view_spec: ViewSpec) -> ViewResult`

* Pure logic: BFS, filters, building sets of bus/substation IDs, selecting branches and equipment.
* No Cytoscape-specific fields or styling.

### 7.2 Cytoscape Converter

Transforms `ViewResult` → JSON:

**Nodes**:

* Bus nodes:

```js
{
  data: {
    id: bus.id,
    kind: "bus",
    psse_number: bus.psse_number,
    name: bus.name,
    base_kv: bus.base_kv,
    substation_id: bus.substation_id,
    area: bus.area,
    zone: bus.zone
  }
}
```

* Substation nodes:

```js
{
  data: {
    id: sub.id,
    kind: "substation",
    name: sub.name,
    nominal_kv: sub.nominal_kv,
    voltage_levels: sub.voltage_levels
  }
}
```

* Equipment nodes:

```js
{
  data: {
    id: eq.id,
    kind: "equipment",
    equipment_type: eq.type, // generator, load, shunt, svc, ...
    bus_id: eq.bus_id,
    name: eq.name,
    p_mw: eq.p_mw,
    q_mvar: eq.q_mvar,
    status: eq.status
    // metadata...
  }
}
```

* Neighbor stub nodes (station_detail):

```js
{
  data: {
    id: `stub-${neighbor_sub_id}`,
    kind: "neighbor_substation_stub",
    substation_id: neighbor_sub_id
  }
}
```

**Edges**:

* Branch edges:

```js
{
  data: {
    id: branch.id,
    kind: "branch",
    type: branch.type,
    source: branch.from_bus_id,
    target: branch.to_bus_id,
    rating_mva: branch.rating_mva,
    p_from_mw: branch.p_from_mw
  }
}
```

* Station_detail stub edges: same branch, but mapped to stub node when remote bus is external.

* Bus↔equipment edges:

```js
{
  data: {
    id: `bus-${eq.bus_id}-equip-${eq.id}`,
    kind: "equipment_link",
    source: eq.bus_id,
    target: eq.id
  }
}
```

These can be thin or visually subtle; the main visual focus is the equipment symbol nodes.

**Equipment Positioning & Collision Avoidance**:

* **Single render pass**: All nodes (buses + equipment) and edges (branches + equipment links) are sent in one API response. Cytoscape renders everything simultaneously - no progressive rendering delay.

* **Positioning strategy** (Phase 2-3):
  * **Phase 2 (MVP)**: Use Cytoscape's layout algorithms with equipment nodes positioned via:
    * **Radial arrangement**: Equipment placed in a circle around the bus at fixed radius (e.g., 50-100px offset)
    * **Angular distribution**: Equipment evenly spaced around bus (360° / num_equipment)
    * **Type-based grouping**: Generators on one side, loads on another, shunts on a third
    * Bus↔equipment edges are very thin/hidden; visual grouping via proximity
  
  * **Phase 3 (Advanced)**: Backend-computed positions:
    * **Collision detection**: Algorithm checks for overlaps between equipment nodes and adjusts positions
    * **Force-directed refinement**: Use force-directed layout to resolve overlaps while maintaining bus positions
    * **Bus size scaling**: Bus node size increases based on number of attached equipment (visual accommodation)
    * **Line connection points**: Lines connect to bus perimeter at angles that avoid equipment positions

* **Collision avoidance algorithm** (Phase 3):
  * For each bus with equipment:
    1. **Initial placement**: Radial arrangement (equipment at fixed radius, evenly spaced)
    2. **Overlap detection**: Check bounding boxes of equipment nodes for intersections
    3. **Resolution strategies**:
       * **Increase radius**: If equipment overlap, increase distance from bus
       * **Adjust angles**: Shift overlapping equipment to different angles
       * **Grid fallback**: For buses with many equipment (>5), switch to grid layout
       * **Bus expansion**: Increase bus node size to accommodate more equipment
    4. **Line routing**: Ensure branch edges don't pass through equipment nodes (use edge routing/curved edges)

* **Implementation notes**:
  * Equipment positioning can be computed in `layouts.py` (Phase 3)
  * Cytoscape supports `position` in node data for preset layouts
  * For dynamic layouts, use Cytoscape's `layout` options with custom positioning callbacks
  * Consider using Cytoscape's `compound` nodes feature (bus as parent) for automatic grouping, but test performance impact

**Note on size**:

* Equipment significantly increases node count: a bus with 1 gen + 2 loads becomes 3 nodes, plus edges.
* Because `limit` is on buses only, we keep BFS manageable but must:

  * Use Cytoscape WebGL and performance options for larger views (> ~1000 total elements).
  * Provide a UI toggle to hide/show equipment for clearer topological views.
  * Consider equipment count limits per bus (e.g., max 10 equipment per bus) to prevent visual clutter.

---

## 8. Implementation Phases

### Week-by-Week Breakdown

**Week 1 (Phase 1)**: MVP - Topology only, BUS mode
- **Days 1-2**: Backend setup, models, parser
- **Days 3-4**: Graph builder, view engine (bus mode)
- **Days 5-6**: Cytoscape converter, API endpoints
- **Day 7**: Frontend setup, basic visualization, testing

**Week 2 (Phase 2)**: Substations + Equipment + Interactive UX
- **Days 1-2**: Substation inference, equipment parsing
- **Days 3-4**: View engine extensions (substation/station_detail modes), equipment attachment
- **Days 5-6**: Frontend interactive features (search, expand, detail panel)
- **Day 7**: Testing, polish, equipment visualization

**Week 3 (Phase 3)**: Layout & Styling, Flows
- **Days 1-3**: Layout algorithms, equipment positioning (collision detection)
- **Days 4-5**: Frontend styling, legends, flow visualization
- **Days 6-7**: Polish, performance optimization, documentation

**Week 4+ (Phase 4)**: Auth, Persistence & Advanced Features
- Auth, DB, subscriptions, comparison, export features

### Phase 1 – MVP (Topology only, BUS mode)

**Backend**:

* Set up FastAPI project, config, logging.
* Define canonical models: `BusModel`, `BranchModel`, `SubstationModel`, and **stub** `EquipmentModel` / `EquipmentType` (types defined, but **no parsing yet**).
* Implement `rawx_parser.py`:

  * Use VeraGrid to parse RAW/RAWX → `BusModel[]` + `BranchModel[]`.
* Implement `graph_builder.py`:

  * Build bus-level NetworkX MultiDiGraph.
  * Optionally build a trivial substation graph or leave stubbed.
* Implement `view_engine.py`:

  * Support only `mode="bus"`.
  * BFS by `degrees`, enforce `limit` (bus count).
  * Use default `INITIAL_VIEW_LIMIT = 100` for first view when no center given.
* Implement `cytoscape_converter.py`:

  * Output nodes = buses, edges = branches.
* Implement endpoints:

  * `POST /api/v1/files/upload` → `file_id` (streaming upload for large files, validate .rawx extension and size limits).
  * `POST /api/v1/graphs/{file_id}/view` (BUS mode only).
  * `GET /api/v1/graphs/{file_id}` (full graph, **debug only**).
* In-memory cache for graphs (document memory limits).
* Structured error responses: `{"error": {"code": "...", "message": "..."}}` format.

**Frontend**:

* Vite + React + TypeScript project.
* GraphViewer.tsx:

  * Call `/view` with BUS mode spec.
  * Render nodes/edges in Cytoscape.
  * Use `preset` or `breadthfirst`.
  * Zoom/pan.
* ErrorBoundary & basic loading states.
* Node/edge click: log to console.

**Tests**:

* `test_rawx_parser.py` (buses/branches).
* `test_graph_builder.py` (MultiGraph, parallel circuits).
* `test_cytoscape_converter.py` (structure).
* `test_view_engine.py` (BUS mode BFS, limit behavior, seed bus logic).

### Phase 2 – Substations + Equipment + Interactive UX

**Backend**:

* Implement `substations.py` and integrate into parsing pipeline.
* Enhance `graph_builder.py` to build substation-level graph.
* Extend models: ensure `EquipmentModel` / `EquipmentType` fields are final.
* Extend `rawx_parser.py`:

  * Parse PSSE GEN/LOAD/SHUNT/SVC/HVDC into `EquipmentModel[]`.
* Extend `ViewSpec.Filters`:

  * Add `include_equipment` and `equipment_types`.
* Extend `view_engine.py`:

  * Implement `mode="substation"` and `"station_detail"`.
  * Attach equipment for included buses when `include_equipment = true`.
* Extend `cytoscape_converter.py`:

  * Output equipment nodes and bus↔equipment edges.
* Add endpoints:

  * `GET /api/v1/graphs/{file_id}/stats`
  * `POST /api/v1/graphs/{file_id}/expand`
  * `GET /api/v1/graphs/{file_id}/subgraph`
  * `GET /api/v1/graphs/{file_id}/nodes/{node_id}`

    * For bus nodes: include a summary of attached equipment.
  * `GET /api/v1/graphs/{file_id}/branches/{branch_id}`
  * `GET /api/v1/graphs/{file_id}/equipment/{equipment_id}` (new)

**Frontend**:

* Adopt TanStack Query for `/view` + detail endpoints.
* Implement BusSearch (by psse_number/name) and expand-by-degrees UI.
* ControlsPanel:

  * Mode select (bus/substation/station_detail).
  * Degrees.
  * Filters (voltage, type).
  * “Show equipment” toggle.
* DetailPanel:

  * Show bus details + list of equipment.
  * Show branch details.
  * Show equipment details (P/Q, type, status, metadata).
* Better error + retry behavior.

### Phase 3 – Layout & Styling, Flows

**Backend**:

* `layouts.py` + `LayoutSpec` for:

  * Voltage-band layout within a station.
  * Area/zone grouping.
  * **Equipment positioning algorithm**:
    * Radial arrangement with collision detection
    * Bus size scaling based on equipment count
    * Line connection point calculation (avoid equipment)
* Optional server-side layout caching for common views.
* Optionally integrate PowSyBl-diagram or powsybl-diagram server for single-line / network-area layouts (import coordinates as "preset").
* Include flows (P/Q) in BranchModel from PF results.

**Frontend**:

* Layout selector (spring, hierarchical, voltage-band).
* Styling:

  * Color buses by base_kv.
  * Color edges by type.
  * Use arrowheads and color/width to show flow direction & loading.
  * Distinct symbols for equipment types.
* **Equipment positioning**:
  * Use backend-computed positions when available (preset layout)
  * Fallback to frontend radial arrangement for dynamic layouts
  * Visual feedback for collision resolution (smooth transitions)
* Legends for voltage, branch type, flow.

### Phase 4 – Auth, Persistence & Advanced

**Backend**:

* Auth (JWT), user accounts, subscriptions.
* DB for users/files/subscriptions.
* Persistent cache (Redis).
* Comparison endpoints (graph diffs).

**Frontend**:

* Login/registration.
* File management UI.
* Comparison views.
* Export (PNG/PDF) using server-side capture or front-end export.

---

## 9. Key Design Decisions (Recap)

* **Partial views only**: view node caps:

  * `BUS_LIMIT_DEFAULT = 300` (buses)
  * `SUBSTATION_LIMIT_DEFAULT = 500` (substations)
  * `INITIAL_VIEW_LIMIT = 100` (initial BFS) 
* **Equipment is first-class but additive**:

  * Equipment nodes do *not* affect `limit` or BFS.
  * Nodes get added for every generator/load/shunt/etc. attached to visible buses.
* **No aggregation of branches**:

  * Every physical circuit stays a separate edge in all modes.
* **Directional flows**:

  * Branch orientation is fixed; flows follow that convention; visual arrows & color reflect `p_from_mw`.
* **Substations as containers**:

  * Inferred when missing; first-class for substation & station_detail modes.
* **Pure view engine**:

  * Graph + ViewSpec → ViewResult, no Cytoscape specifics.
* **Presentation layer**:

  * Cytoscape converter transforms ViewResult into elements; can be swapped for another renderer.
* **Python-first & PSSE-centric**:

  * Clean integration with VeraGrid + Python tooling.
* **File upload**: Streaming uploads for large files (100MB+), progress tracking, validation (.rawx extension, size limits).
* **Error handling**: Structured error responses (`{"error": {"code": "...", "message": "..."}}`), React Error Boundaries on frontend.
* **Profiling & metrics**: Log timing for parse, view_engine, Cytoscape render. Log each `/view` request with mode, node/edge counts, truncated status.
* **Sample datasets**: Maintain test cases (small/medium/large) in `sample_data/` for automated tests and manual profiling.
* **Equipment positioning & collision avoidance**:

  * **Single render pass**: All nodes (buses + equipment) and edges (branches + equipment links) sent in one API response. Cytoscape renders simultaneously - no progressive rendering delay.
  * **Phase 2 (MVP)**: Radial arrangement around buses (frontend-side, simple). Equipment evenly spaced in circle around bus.
  * **Phase 3 (Advanced)**: Backend-computed positions with collision detection:
    * Radial arrangement with overlap detection
    * Bus size scales with equipment count
    * Line routing avoids equipment nodes (curved edges or connection point adjustment)
    * Algorithm: initial radial placement → detect overlaps → increase radius/adjust angles → grid fallback for many equipment
  * **Visual strategy**: Bus↔equipment edges are thin/hidden; equipment positioned close to buses via proximity and layout.

* **Extensible**:

  * Future: voltage-level view mode, geospatial mode (Mapbox/MapLibre), alternative renderers (NetV.js, Sigma.js), or PowSyBl-diagram integration. 

