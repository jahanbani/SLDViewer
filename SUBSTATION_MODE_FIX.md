# Substation Mode Fix

## Problem
When switching to SUBSTATION or STATION_DETAIL view modes in the frontend, the user received an error. The modes were not working.

## Root Causes

### 1. API Router Blocking Modes (PRIMARY ISSUE)
**File**: `backend/api/routers/graphs.py` (lines 166-175)

**Problem**: An old Phase 1 validation check was rejecting all modes except BUS:
```python
if spec.mode != ViewMode.BUS:
    return JSONResponse(
        status_code=400,
        content={"error": {"message": "Only BUS mode is currently supported"}}
    )
```

**Solution**: Removed the restrictive check. All modes are now allowed to pass through to the view_engine, which handles mode-specific validation.

### 2. Edge Remapping in Substation Mode (SECONDARY ISSUE)
**Files**:
- `backend/core/graph/view_engine.py` (lines 174-191)
- `backend/core/graph/cytoscape_converter.py` (lines 229-253)

**Problem**: In SUBSTATION mode, branches still referenced bus IDs (from_bus_id, to_bus_id) but the frontend needed them to reference substation IDs since individual buses aren't shown.

**Solution**:
1. **view_engine.py**: Added `bus_to_substation_id` mapping to metadata in SUBSTATION mode
   ```python
   bus_to_substation_id = {}
   for bus in graph.bus_by_id.values():
       if bus.substation_id:
           bus_to_substation_id[bus.id] = bus.substation_id

   meta = {
       ...
       "bus_to_substation_id": bus_to_substation_id,  # For edge remapping
   }
   ```

2. **cytoscape_converter.py**: Use the mapping to remap edges from bus endpoints to substation endpoints
   ```python
   if view_mode == "substation" and not result.buses:
       bus_to_sub = result.meta.get("bus_to_substation_id", {})

       new_edges = []
       for edge in edges:
           source_sub_id = bus_to_sub.get(edge["data"]["source"])
           target_sub_id = bus_to_sub.get(edge["data"]["target"])

           if source_sub_id and target_sub_id:
               edge_data = edge["data"].copy()
               edge_data["source"] = source_sub_id
               edge_data["target"] = target_sub_id
               new_edges.append({"data": edge_data})

       edges = new_edges
   ```

## Files Modified

1. **backend/api/routers/graphs.py**
   - Removed mode restriction
   - Updated docstring to reflect all supported modes

2. **backend/core/graph/view_engine.py**
   - Added bus_to_substation_id mapping to SUBSTATION mode metadata

3. **backend/core/graph/cytoscape_converter.py**
   - Added edge remapping logic for SUBSTATION mode
   - Edges now connect substations instead of buses

## Testing

### Unit Tests
All existing tests pass:
```
tests/test_view_engine.py::test_view_substation_mode_requires_substations PASSED
tests/test_cytoscape_converter.py::test_view_result_to_cytoscape_empty PASSED
tests/test_cytoscape_converter.py::test_view_result_to_cytoscape_with_buses PASSED
tests/test_cytoscape_converter.py::test_view_result_to_cytoscape_with_branches PASSED
```

### Manual Testing Needed

1. **SUBSTATION Mode**:
   ```
   - Load a file (e.g., IEEE 118 bus)
   - Switch mode dropdown to "Substation"
   - Expected: Graph shows substations as nodes, inter-substation lines as edges
   - Verify: Substations are colored/styled correctly
   - Verify: Can click on substations to see details
   ```

2. **STATION_DETAIL Mode**:
   ```
   - Switch mode dropdown to "Station Detail"
   - Enter a bus number in "Center" field
   - Expected: Shows all buses within that bus's substation
   - Expected: Shows stub nodes for neighboring substations
   - Verify: Internal buses and transformers visible
   - Verify: Equipment shown if "Equipment" checkbox is checked
   ```

3. **Mode Switching**:
   ```
   - Switch between BUS → SUBSTATION → STATION_DETAIL → BUS
   - Verify: No errors in browser console
   - Verify: Layout caching works (positions preserved when possible)
   ```

## Expected Behavior

### BUS Mode
- Shows individual buses as nodes
- Shows branches connecting buses
- Shows equipment if enabled
- Substation grouping boxes visible if "Substations" checkbox enabled

### SUBSTATION Mode
- Shows substations as large rectangular nodes
- Shows only inter-substation transmission lines
- Equipment checkbox disabled (not applicable in overview mode)
- Buses hidden, counts shown in metadata

### STATION_DETAIL Mode
- Shows all buses within one substation
- Shows transformers connecting voltage levels within substation
- Shows stub nodes for neighboring substations
- Shows equipment if enabled
- Requires center bus number or substation ID

## API Changes

### Endpoint: POST /api/v1/graphs/{file_id}/view

**Before**: Only accepted `mode: "bus"`

**After**: Accepts all three modes:
- `mode: "bus"` - Bus-level view
- `mode: "substation"` - Substation-level overview
- `mode: "station_detail"` - Detailed view of one substation

**Error Handling**:
- If file has no substations and user requests SUBSTATION or STATION_DETAIL mode:
  - Returns HTTP 400 with error code `MODE_NOT_SUPPORTED`
  - Message: "SUBSTATION mode requires substations. No substations detected in this file."

## Notes

- No database schema changes
- No new dependencies
- Backward compatible (existing BUS mode unchanged)
- Substation inference is automatic (uses VeraGrid or fallback algorithm)

## Next Steps

After testing, document the following for users:
1. How to use SUBSTATION mode for large network overviews
2. How to use STATION_DETAIL mode to drill into specific substations
3. Keyboard shortcuts or UI patterns for quick mode switching
4. Performance characteristics of each mode (SUBSTATION is fastest for large networks)
