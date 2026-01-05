"""
View generation endpoints: Cytoscape payload generation from ViewSpec.
"""
from fastapi import APIRouter, HTTPException, status

from backend.core.storage import storage
from backend.core.cache import parsed_case_cache
from backend.core.errors import (
    SLDError,
    BusNotFoundError,
    SubstationNotFoundError,
    sld_error_to_http_exception,
)
from backend.core.graph.models import ViewSpec, CytoscapePayload, ViewMode
from backend.core.graph.veragrid_adapter import VeraGridAdapter
from backend.core.graph.graph_builder import build_case_graph
from backend.core.graph.slicer import slice_view
from backend.core.graph.cytoscape_converter import convert_to_cytoscape
from backend.core.timing import OperationTimer, logger

router = APIRouter(prefix="/api/v1/views", tags=["views"])


def _get_case_graph(file_id: str):
    """Get or build case graph, with caching."""
    # Check cache first
    cached = parsed_case_cache.get(file_id)
    if cached is not None:
        return cached

    # Load file
    path = storage.get_path(file_id)
    if path is None or not path.exists():
        from backend.core.errors import FileNotFoundError

        raise FileNotFoundError(file_id)

    # Determine format from extension
    ext = path.suffix.lower().lstrip(".")

    # Parse with VeraGrid adapter
    adapter = VeraGridAdapter(path, file_id, ext)
    case = adapter.parse()

    # Build graph
    graph = build_case_graph(case)

    # Cache it
    parsed_case_cache.set(file_id, graph)

    return graph


@router.post("/{file_id}", response_model=CytoscapePayload)
async def generate_view(file_id: str, spec: ViewSpec) -> CytoscapePayload:
    """
    Generate a Cytoscape.js payload for the given file and view spec.

    The payload contains nodes and edges with NO positions.
    Positions are computed by the frontend layout engine.
    """
    timer = OperationTimer(f"generate_view file={file_id} mode={spec.mode.value}")

    try:
        # Get case graph (includes parsing + graph building)
        timer.start_phase("get_case_graph")
        graph = _get_case_graph(file_id)
        timer.end_phase("get_case_graph", count=len(graph.case.buses))

        # Validate center buses exist
        timer.start_phase("validation")
        if spec.mode == ViewMode.BUS and spec.center_bus_numbers:
            for bus_num in spec.center_bus_numbers:
                if graph.get_bus_by_psse(bus_num) is None:
                    raise BusNotFoundError(bus_num)

        # Validate center substations exist
        if spec.mode in (ViewMode.SUBSTATION, ViewMode.STATION_DETAIL):
            if spec.center_substation_ids:
                for sub_id in spec.center_substation_ids:
                    found = any(s.id == sub_id for s in graph.case.substations)
                    if not found:
                        raise SubstationNotFoundError(sub_id)
        timer.end_phase("validation")

        # Slice view
        timer.start_phase("slice_view")
        slice_result = slice_view(graph, spec)
        timer.end_phase("slice_view", count=len(slice_result.buses))

        # Get full network connection counts (for circle vs busbar rendering)
        timer.start_phase("get_connection_counts")
        full_network_counts = graph.get_bus_connection_counts()
        timer.end_phase("get_connection_counts", count=len(full_network_counts))

        # Convert to Cytoscape payload
        timer.start_phase("convert_to_cytoscape")
        payload = convert_to_cytoscape(slice_result, spec, full_network_counts)
        timer.end_phase("convert_to_cytoscape", count=len(payload.elements))

        report = timer.finish()
        logger.info(report.summary())

        return payload

    except SLDError as e:
        timer.finish()
        raise sld_error_to_http_exception(e)
    except Exception as e:
        timer.finish()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "VIEW_GENERATION_FAILED", "message": str(e)},
        )
