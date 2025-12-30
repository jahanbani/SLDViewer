"""Graph view endpoints for SLD Viewer.

Supports BUS, SUBSTATION, and STATION_DETAIL view modes.
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.core.config import Settings, get_settings
from backend.core.graph import cytoscape_converter, graph_builder, view_engine
from backend.core.graph.models import ViewMode, ViewResult, ViewSpec

router = APIRouter(prefix="/graphs", tags=["graphs"])

# In-memory cache for GraphHandle instances
# Key: file_id (str), Value: GraphHandle
graphs_cache: dict[str, graph_builder.GraphHandle] = {}

# Cache for file paths
# Key: file_id (str), Value: Path
file_paths_cache: dict[str, Path] = {}


def _load_and_cache_graph(file_id: str, settings: Settings) -> graph_builder.GraphHandle:
    """Load a file, parse it, build graphs, and cache the result.

    Args:
        file_id: UUID of the uploaded file
        settings: Application settings

    Returns:
        GraphHandle for the file

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If parsing or graph building fails
    """
    # Construct file path (storage_root is now absolute)
    storage_path = Path(settings.storage_root)
    
    # Try both .raw and .rawx extensions
    file_path = None
    for ext in [".rawx", ".raw"]:
        candidate = storage_path / f"{file_id}{ext}"
        if candidate.exists():
            file_path = candidate
            break
    
    # If not found, also check the old location (for backwards compatibility)
    if file_path is None:
        # Check if there's a double-backend path (legacy issue)
        project_root = storage_path.parent.parent.parent  # Go up from backend/storage/user_files
        legacy_path = project_root / "backend" / "backend" / "storage" / "user_files"
        if legacy_path.exists():
            for ext in [".rawx", ".raw"]:
                candidate = legacy_path / f"{file_id}{ext}"
                if candidate.exists():
                    file_path = candidate
                    break
    
    if file_path is None:
        raise FileNotFoundError(
            f"File {file_id} not found in storage. "
            f"Checked: {storage_path.resolve()}"
        )

    # Import and use the parser
    try:
        from backend.core.graph import rawx_parser
    except (ImportError, AttributeError) as e:
        # Only catch import errors for the module itself
        raise NotImplementedError(
            f"Failed to import rawx_parser: {e}. "
            f"File path: {file_path}"
        )
    
    # Check if VeraGrid is available - if not, try to set up path and re-check
    if not getattr(rawx_parser, "VERAGRID_AVAILABLE", False):
        # Try to force re-import by ensuring path is set up
        import sys
        
        # Get project root (this file is in backend/api/routers/)
        # Path is already imported at module level
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        veragrid_path = project_root / "VeraGrid" / "src"
        
        if veragrid_path.exists():
            path_str = str(veragrid_path.resolve())
            if path_str not in sys.path:
                sys.path.insert(0, path_str)
            
            # Try to re-import VeraGrid using the retry function
            if hasattr(rawx_parser, "try_import_veragrid"):
                rawx_parser.try_import_veragrid()
            
            # Check again
            if not getattr(rawx_parser, "VERAGRID_AVAILABLE", False):
                # Get the import error for better debugging
                import_error = getattr(rawx_parser, "_veragrid_import_error", "Unknown error")
                # Try one more direct import attempt for debugging
                try:
                    import sys
                    test_path = str(veragrid_path.resolve())
                    if test_path not in sys.path:
                        sys.path.insert(0, test_path)
                    # Clear cache and try direct import
                    modules_to_remove = [k for k in sys.modules.keys() if k.startswith('VeraGridEngine')]
                    for m in modules_to_remove:
                        del sys.modules[m]
                    from VeraGridEngine.IO.file_handler import FileOpen
                    # If we get here, import worked - update the flag
                    rawx_parser.VERAGRID_AVAILABLE = True
                except Exception as direct_error:
                    raise NotImplementedError(
                        f"VeraGrid is not available. Cannot parse RAW/RAWX files. "
                        f"File path: {file_path}. "
                        f"VeraGrid path: {veragrid_path} (exists: {veragrid_path.exists()}). "
                        f"Import error: {import_error}. "
                        f"Direct import test error: {direct_error}"
                    )
        else:
            raise NotImplementedError(
                f"VeraGrid path not found: {veragrid_path}. "
                f"File path: {file_path}"
            )
    
    # Parse the file (now includes substations)
    try:
        buses, branches, equipment, substations = rawx_parser.parse_file(str(file_path))
    except NotImplementedError:
        # Re-raise NotImplementedError as-is (from parse_file if VeraGrid unavailable)
        raise
    except Exception as e:
        # Wrap other exceptions with more context
        raise ValueError(
            f"Failed to parse file {file_path}: {e}"
        ) from e

    # Build graphs (bus-level and substation-level)
    handle = graph_builder.build_graphs(buses, branches, equipment, substations)

    # Cache the handle and file path
    graphs_cache[file_id] = handle
    file_paths_cache[file_id] = file_path

    return handle


@router.post("/{file_id}/view")
async def view_graph(file_id: str, spec: ViewSpec) -> dict[str, Any]:
    """Generate a graph view for a specific file.

    Supports BUS, SUBSTATION, and STATION_DETAIL modes.

    Args:
        file_id: UUID of the uploaded file
        spec: ViewSpec defining the view parameters

    Returns:
        Cytoscape.js-compatible JSON with nodes, edges, and metadata

    Returns (on error):
        JSONResponse with error structure: {"error": {"code": "...", "message": "..."}}
    """
    settings = get_settings()

    # Mode validation is now handled by view_engine.py
    # All modes (BUS, SUBSTATION, STATION_DETAIL) are supported

    # Get or load graph handle
    try:
        if file_id not in graphs_cache:
            handle = _load_and_cache_graph(file_id, settings)
        else:
            handle = graphs_cache[file_id]
    except FileNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "FILE_NOT_FOUND",
                    "message": str(e),
                }
            },
        )
    except NotImplementedError as e:
        return JSONResponse(
            status_code=501,
            content={
                "error": {
                    "code": "PARSER_NOT_IMPLEMENTED",
                    "message": str(e),
                }
            },
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "GRAPH_BUILD_ERROR",
                    "message": f"Failed to build graph: {str(e)}",
                }
            },
        )

    # Generate view
    try:
        result = view_engine.view(handle, spec, settings)
    except view_engine.UnsupportedViewModeError as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "MODE_NOT_SUPPORTED",
                    "message": str(e),
                }
            },
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "VIEW_GENERATION_ERROR",
                    "message": f"Failed to generate view: {str(e)}",
                }
            },
        )

    # Convert to Cytoscape JSON
    cytoscape_json = cytoscape_converter.view_result_to_cytoscape(result)

    return cytoscape_json


@router.get("/{file_id}")
async def get_full_graph(file_id: str) -> dict[str, Any]:
    """Debug-only: return the full graph for a specific file.

    Loads/parses/builds graphs (cached) and returns all buses + all branches
    converted to Cytoscape.js-compatible JSON.
    """
    settings = get_settings()

    # Get or load graph handle
    try:
        if file_id not in graphs_cache:
            handle = _load_and_cache_graph(file_id, settings)
        else:
            handle = graphs_cache[file_id]
    except FileNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "FILE_NOT_FOUND",
                    "message": str(e),
                }
            },
        )
    except NotImplementedError as e:
        return JSONResponse(
            status_code=501,
            content={
                "error": {
                    "code": "PARSER_NOT_IMPLEMENTED",
                    "message": str(e),
                }
            },
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "GRAPH_BUILD_ERROR",
                    "message": f"Failed to build graph: {str(e)}",
                }
            },
        )

    # Convert full graph to Cytoscape JSON using the same converter
    buses = list(handle.bus_by_id.values())
    branches = list(handle.branch_by_id.values())
    equipment = list(handle.equipment_by_id.values())
    substations = list(handle.substation_by_id.values())

    result = ViewResult(
        buses=buses,
        branches=branches,
        substations=substations,
        equipment=equipment,
        meta={
            "mode": "full_graph",
            "truncated": False,
            "node_count": len(buses),
            "edge_count": len(branches),
            "equipment_count": len(equipment),
            "substation_count": len(substations),
        },
    )

    return cytoscape_converter.view_result_to_cytoscape(result)
