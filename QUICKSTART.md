# Quick Start Guide

## Step 1: Install Dependencies

### Backend
```powershell
# From project root
pip install -r backend/requirements.txt
```

### Frontend
```powershell
cd frontend
npm install
```

## Step 2: Start the Backend Server

```powershell
# From project root
python backend/run.py
```

The server will start at `http://localhost:8000`

You can verify it's running by visiting: http://localhost:8000/docs

## Step 3: Upload a File

### Option A: Using PowerShell's Invoke-WebRequest
```powershell
# From project root
$filePath = "ieee118.rawx"
$uri = "http://localhost:8000/api/v1/files/upload"
$form = @{
    file = Get-Item $filePath
}
$response = Invoke-WebRequest -Uri $uri -Method Post -Form $form
$response.Content
```

### Option B: Using curl.exe (Windows 10+)
```powershell
# Use curl.exe explicitly (not the PowerShell alias)
curl.exe -X POST http://localhost:8000/api/v1/files/upload -F "file=@ieee118.rawx"
```

### Option C: Using Python script
```powershell
python test_upload.py
```

## Step 4: Get a Graph View

After uploading, you'll get a `file_id` (UUID). Use it to request a view:

### PowerShell
```powershell
$fileId = "YOUR_FILE_ID_HERE"
$body = @{
    mode = "bus"
    center_bus_numbers = $null
    degrees = 1
    filters = @{}
    layout = "preset"
    limit = $null
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:8000/api/v1/graphs/$fileId/view" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body
```

## (Debug) Get the Full Graph

This can be very large; use only for debugging.

```powershell
$fileId = "YOUR_FILE_ID_HERE"
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/graphs/$fileId" -Method Get
```

### curl.exe
```powershell
curl.exe -X POST "http://localhost:8000/api/v1/graphs/YOUR_FILE_ID/view" `
    -H "Content-Type: application/json" `
    -d '{\"mode\":\"bus\",\"center_bus_numbers\":null,\"degrees\":1,\"filters\":{},\"layout\":\"preset\",\"limit\":null}'
```

## Step 5: Start the Frontend

Open a new terminal:

```powershell
cd frontend
npm run dev
```

The frontend will start at `http://localhost:5173`

## Step 6: Use the UI

1. Open http://localhost:5173 in your browser
2. Enter the `file_id` from Step 3
3. Click "Load Graph"
4. The graph should render!

## Troubleshooting

### Backend won't start
- Make sure you're in the project root or using `python backend/run.py`
- Check that all dependencies are installed: `pip install -r backend/requirements.txt`

### File upload fails
- Make sure `ieee118.rawx` is in the project root directory
- Check that the backend server is running
- Verify the file path is correct

### Frontend won't start
- Make sure Node.js is installed: `node --version`
- Install dependencies: `cd frontend && npm install`
- Check that port 5173 is not in use

