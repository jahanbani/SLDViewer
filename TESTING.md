# Testing Guide

## Backend Tests

All backend tests are located in `backend/tests/` and use pytest.

### Running Tests

From the project root:
```bash
pytest backend/tests/
```

Or with verbose output:
```bash
pytest backend/tests/ -v
```

### Test Coverage

#### ✅ test_graph_builder.py
- Empty graph building
- Single bus graph
- Graph with branches
- Invalid branch handling (error cases)

#### ✅ test_view_engine.py
- BUS mode view generation
- Unsupported mode error handling
- Default seed bus selection

#### ✅ test_cytoscape_converter.py
- Empty view result conversion
- View result with buses
- View result with branches

#### ✅ test_rawx_parser.py
- Parser stub (NotImplementedError)

### Test Results

All 11 tests pass:
- 4 graph builder tests
- 3 view engine tests
- 3 cytoscape converter tests
- 1 rawx parser test

## Manual Testing

### Backend API Testing

1. **Start the backend server**:
```bash
cd backend
python run.py
# Or: uvicorn backend.api.main:app --reload
```

2. **Test file upload** (using curl or Postman):
```bash
curl -X POST http://localhost:8000/api/v1/files/upload \
  -F "file=@v35.rawx"
```

Expected response:
```json
{"file_id": "uuid-here"}
```

3. **Test graph view** (replace `{file_id}` with actual UUID):
```bash
curl -X POST http://localhost:8000/api/v1/graphs/{file_id}/view \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "bus",
    "center_bus_numbers": null,
    "degrees": 1,
    "filters": {},
    "layout": "preset",
    "limit": null
  }'
```

Expected response: Cytoscape JSON with nodes and edges

4. **Test error cases**:
   - Invalid file extension → 400 error
   - Non-existent file_id → 404 error
   - Unsupported mode → 400 error

### Frontend Testing

1. **Install dependencies**:
```bash
cd frontend
npm install
```

2. **Start development server**:
```bash
npm run dev
```

3. **Manual testing**:
   - Upload a file via API to get a file_id
   - Enter file_id in the UI
   - Click "Load Graph"
   - Verify graph renders
   - Click nodes/edges and check console logs
   - Test zoom/pan functionality

### API Documentation

Once the backend is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Integration Testing

### End-to-End Flow

1. Upload a RAW/RAWX file → Get file_id
2. Request graph view with file_id → Get Cytoscape JSON
3. Verify JSON structure:
   - `elements.nodes` array
   - `elements.edges` array
   - `meta` object with counts
4. Load in frontend → Verify visualization

## Known Limitations (Phase 1)

- ⚠️ RAW/RAWX parser is a stub (returns NotImplementedError)
- ⚠️ Only BUS mode is supported
- ⚠️ No equipment or substation visualization
- ⚠️ In-memory cache (no persistence)
- ⚠️ No authentication

## Next Steps for Testing

- [ ] Add integration tests for full API flow
- [ ] Add frontend component tests (React Testing Library)
- [ ] Add E2E tests (Playwright/Cypress)
- [ ] Add performance tests for large graphs
- [ ] Add mock data for testing without real RAW files

