# How to Restart the Server

## Step-by-Step Instructions

### 1. Stop the Current Server
In the terminal where the server is running:
- Press `Ctrl+C` to stop the server
- Wait for it to fully stop (you should see the prompt return)

### 2. Start the Server Again
From the **project root** (SLDViewer directory):

```powershell
python backend/run.py
```

**OR** from the backend directory:

```powershell
cd backend
python run.py
```

### 3. Verify Server Started
You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [...]
INFO:     Started server process [...]
INFO:     Application startup complete.
```

### 4. Test the API
Open a new terminal and run:

```powershell
python test_upload.py ieee118.rawx
```

Or test in the UI at http://localhost:5173

## Troubleshooting

If you still get "VeraGrid is not available":
1. Make sure you're running from the project root
2. Check that VeraGrid folder exists: `dir VeraGrid\src`
3. Try running: `python test_server_import.py` to verify imports work

