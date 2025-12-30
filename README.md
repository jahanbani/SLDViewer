# SLD Viewer

A web-based Single Line Diagram (SLD) viewer for PSSE power system data.

## Architecture

- **Backend**: FastAPI (Python 3.11+)
- **Frontend**: React + TypeScript + Vite + Cytoscape.js
- **Graph Engine**: NetworkX

## Setup

### Backend Setup

1. Install Python dependencies:
```bash
# From project root:
pip install -r backend/requirements.txt

# Or from backend directory:
cd backend
pip install -r requirements.txt
```

2. Run the backend server:
```bash
# Option 1: From project root (recommended):
python backend/run.py

# Option 2: From backend directory:
cd backend
python run.py

# Option 3: Using uvicorn directly (from project root):
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
```

**Note**: The server must be run from the project root or use `run.py` which handles the path automatically.

The API will be available at `http://localhost:8000`

API documentation: `http://localhost:8000/docs`

### Frontend Setup

1. Install Node.js dependencies:
```bash
cd frontend
npm install
```

2. Run the development server:
```bash
npm run dev
```

The frontend will be available at `http://localhost:5173`

## Testing

### Backend Tests

Run pytest from the project root:
```bash
pytest backend/tests/
```

Or from the backend directory:
```bash
cd backend
pytest tests/
```

### Frontend Tests

(To be added in future phases)

## Usage

### Phase 1 (Current)

1. **Upload a file**: POST to `/api/v1/files/upload` with a `.raw` or `.rawx` file
   - Returns a `file_id` (UUID)

2. **View graph**: POST to `/api/v1/graphs/{file_id}/view` with a `ViewSpec`
   - Currently supports BUS mode only
   - Returns Cytoscape.js-compatible JSON

3. **(Debug) Full graph**: GET `/api/v1/graphs/{file_id}`
   - Returns the full bus+branch graph as Cytoscape.js-compatible JSON
   - Intended for debugging only (can be very large)

4. **Frontend**: Enter the `file_id` in the UI and click "Load Graph"

### Example API Request

```bash
# Upload file
curl -X POST http://localhost:8000/api/v1/files/upload \
  -F "file=@sample.rawx"

# View graph (replace {file_id} with actual UUID)
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

## Project Structure

```
SLDViewer/
├── backend/
│   ├── api/              # FastAPI routes
│   ├── core/             # Core business logic
│   │   └── graph/        # Graph models, builders, view engine
│   ├── tests/            # Test files
│   └── requirements.txt  # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── components/   # React components
│   │   └── App.tsx       # Main app component
│   └── package.json      # Node.js dependencies
└── docs/
    └── SLD_PLAN.md       # Architecture and implementation plan
```

## Phase 1 Status

✅ Backend models (Bus, Branch, ViewSpec, etc.)
✅ Graph builder (bus-level graph)
✅ View engine (BUS mode)
✅ Cytoscape converter
✅ File upload endpoint
✅ Graph view endpoint
✅ Frontend GraphViewer component
✅ RAW/RAWX parser (VeraGrid integration)

## Next Steps (Phase 2)

- Implement RAW/RAWX parser using VeraGrid
- Add substation inference
- Add equipment parsing and visualization
- Add substation and station_detail view modes
- Add React Query for data fetching
- Add interactive features (search, expand, detail panel)

## Development Notes

- Backend uses in-memory cache for graphs (no Redis yet)
- Frontend uses hardcoded API URL (should use env vars in production)
- No authentication yet (Phase 4)
- No database persistence yet (Phase 4)

