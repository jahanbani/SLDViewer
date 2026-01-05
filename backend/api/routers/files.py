"""
File management endpoints: upload, summary, bus search, refresh.
"""
from fastapi import APIRouter, File, UploadFile, HTTPException, status, Query
from pydantic import BaseModel

from backend.core.config import settings
from backend.core.storage import storage
from backend.core.cache import parsed_case_cache
from backend.core.errors import (
    InvalidFileFormatError,
    FileTooLargeError,
    sld_error_to_http_exception,
    SLDError,
)
from backend.core.graph.models import CaseSummary
from backend.core.graph.veragrid_adapter import VeraGridAdapter
from backend.core.graph.graph_builder import build_case_graph
from backend.core.timing import OperationTimer, logger

router = APIRouter(prefix="/api/v1/files", tags=["files"])

ALLOWED_EXTENSIONS = {".raw", ".rawx"}


class UploadResponse(BaseModel):
    """Response model for file upload."""

    file_id: str
    format: str


class BusSearchResult(BaseModel):
    """Individual bus search result."""

    psse_number: int
    name: str
    base_kv: float
    substation_id: str | None = None
    area: int | None = None
    zone: int | None = None


class BusSearchResponse(BaseModel):
    """Response model for bus search."""

    results: list[BusSearchResult]


class RefreshResponse(BaseModel):
    """Response model for cache refresh."""

    file_id: str
    status: str


def _get_case_graph(file_id: str):
    """Get or build case graph, with caching."""
    # Check cache first
    cached = parsed_case_cache.get(file_id)
    if cached is not None:
        logger.info(f"[CACHE HIT] file_id={file_id}")
        return cached

    logger.info(f"[CACHE MISS] file_id={file_id} - parsing file")

    # Load file
    path = storage.get_path(file_id)
    if path is None or not path.exists():
        from backend.core.errors import FileNotFoundError

        raise FileNotFoundError(file_id)

    # Determine format from extension
    ext = path.suffix.lower().lstrip(".")

    # Start overall timing
    timer = OperationTimer(f"Load case {file_id}")

    # Phase 1: Parse with VeraGrid adapter
    timer.start_phase("veragrid_parse")
    adapter = VeraGridAdapter(path, file_id, ext)
    case = adapter.parse()
    timer.end_phase("veragrid_parse", len(case.buses))

    # Phase 2: Build graph
    timer.start_phase("build_graph")
    graph = build_case_graph(case)
    timer.end_phase("build_graph")

    # Phase 3: Cache it
    timer.start_phase("cache_store")
    parsed_case_cache.set(file_id, graph)
    timer.end_phase("cache_store")

    timer.finish()

    return graph


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)) -> UploadResponse:
    """
    Upload a PSSE case file (.raw or .rawx).

    Returns the file_id and format for subsequent operations.
    """
    timer = OperationTimer(f"Upload {file.filename}")

    try:
        # Validate filename
        if not file.filename:
            raise InvalidFileFormatError("unnamed", list(ALLOWED_EXTENSIONS))

        # Check extension
        ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise InvalidFileFormatError(file.filename, list(ALLOWED_EXTENSIONS))

        # Read content
        timer.start_phase("read_upload")
        content = await file.read()
        size_mb = len(content) / (1024 * 1024)
        timer.end_phase("read_upload")
        logger.info(f"  [SIZE] {size_mb:.2f} MB")

        # Check file size
        if size_mb > settings.max_upload_size_mb:
            raise FileTooLargeError(size_mb, settings.max_upload_size_mb)

        # Save file
        timer.start_phase("save_to_disk")
        file_id, path = storage.save(content, file.filename)
        timer.end_phase("save_to_disk")

        # Determine format from extension
        file_format = ext.lstrip(".")

        timer.finish()
        logger.info(f"  [RESULT] file_id={file_id}")

        return UploadResponse(file_id=file_id, format=file_format)

    except SLDError as e:
        raise sld_error_to_http_exception(e)
    except Exception as e:
        logger.error(f"  [ERROR] Upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "UPLOAD_FAILED", "message": str(e)},
        )


@router.get("/{file_id}/summary", response_model=CaseSummary)
async def get_summary(file_id: str) -> CaseSummary:
    """
    Get summary of a parsed case file.

    Returns counts, voltage levels, and parse warnings.
    """
    logger.info(f"[API] GET /files/{file_id}/summary")
    timer = OperationTimer(f"Get summary {file_id}")

    try:
        timer.start_phase("get_case_graph")
        graph = _get_case_graph(file_id)
        timer.end_phase("get_case_graph")

        case = graph.case

        # Build summary
        timer.start_phase("build_summary")
        summary = CaseSummary(
            file_id=file_id,
            format=case.file_format,
            bus_count=len(case.buses),
            ac_branch_count=len(case.ac_branches),
            transformer3w_count=len(case.transformers3w),
            equipment_count=len(case.equipment),
            dc_link_count=len(case.dc_links),
            substation_count=len(case.substations),
            voltage_levels=sorted(case.voltage_levels, reverse=True),
            parse_warnings=case.warnings,
        )
        timer.end_phase("build_summary")

        timer.finish()
        return summary

    except SLDError as e:
        raise sld_error_to_http_exception(e)
    except Exception as e:
        logger.error(f"  [ERROR] Summary failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "SUMMARY_FAILED", "message": str(e)},
        )


@router.get("/{file_id}/buses/search", response_model=BusSearchResponse)
async def search_buses(
    file_id: str,
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
) -> BusSearchResponse:
    """
    Search for buses by number or name.

    - If q is all digits: exact match on psse_number first, then prefix matches
    - If q contains text: case-insensitive substring match on name
    """
    try:
        graph = _get_case_graph(file_id)
        buses = graph.case.buses
        results: list[BusSearchResult] = []

        if q.isdigit():
            # Numeric search: exact match first, then prefix
            q_int = int(q)
            q_str = q

            # Exact match first
            exact = graph.get_bus_by_psse(q_int)
            if exact:
                results.append(
                    BusSearchResult(
                        psse_number=exact.psse_number,
                        name=exact.name,
                        base_kv=exact.base_kv,
                        substation_id=exact.substation_id,
                        area=exact.area,
                        zone=exact.zone,
                    )
                )

            # Prefix matches (excluding exact)
            prefix_matches = [
                b
                for b in buses
                if str(b.psse_number).startswith(q_str) and b.psse_number != q_int
            ]
            prefix_matches.sort(key=lambda b: b.psse_number)

            for bus in prefix_matches[: limit - len(results)]:
                results.append(
                    BusSearchResult(
                        psse_number=bus.psse_number,
                        name=bus.name,
                        base_kv=bus.base_kv,
                        substation_id=bus.substation_id,
                        area=bus.area,
                        zone=bus.zone,
                    )
                )
        else:
            # Text search: case-insensitive substring match on name
            q_lower = q.lower()
            matches = [b for b in buses if q_lower in b.name.lower()]
            matches.sort(key=lambda b: (b.name, b.psse_number))

            for bus in matches[:limit]:
                results.append(
                    BusSearchResult(
                        psse_number=bus.psse_number,
                        name=bus.name,
                        base_kv=bus.base_kv,
                        substation_id=bus.substation_id,
                        area=bus.area,
                        zone=bus.zone,
                    )
                )

        return BusSearchResponse(results=results)

    except SLDError as e:
        raise sld_error_to_http_exception(e)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "SEARCH_FAILED", "message": str(e)},
        )


@router.post("/{file_id}/refresh", response_model=RefreshResponse)
async def refresh_cache(file_id: str) -> RefreshResponse:
    """
    Invalidate cache and re-parse the file.

    Useful for dev/debug when the file has been modified.
    """
    try:
        # Invalidate cache
        parsed_case_cache.delete(file_id)

        # Re-parse by getting case graph (will re-cache)
        _get_case_graph(file_id)

        return RefreshResponse(file_id=file_id, status="refreshed")

    except SLDError as e:
        raise sld_error_to_http_exception(e)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "REFRESH_FAILED", "message": str(e)},
        )
