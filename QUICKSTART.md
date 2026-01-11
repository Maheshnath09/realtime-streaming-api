# Quick Start Guide

## Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

## Run Server

```bash
# Development mode (auto-reload)
uvicorn main:app --reload

# Production mode
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Test Clients

### 1. Browser Client (Recommended)
Open `examples/browser_client.html` in your browser

### 2. Python Client
```bash
python examples/python_client.py
```

### 3. Curl Client
```bash
curl -N -H "Accept: text/event-stream" http://localhost:8000/stream
```

### 4. JavaScript (Node.js)
```javascript
const EventSource = require('eventsource');
const es = new EventSource('http://localhost:8000/stream');

es.addEventListener('data', (e) => {
    console.log('Data:', JSON.parse(e.data));
});

es.addEventListener('heartbeat', (e) => {
    console.log('Heartbeat:', JSON.parse(e.data));
});
```

## API Endpoints

- `GET /` - Health check
- `GET /health` - Detailed health status
- `GET /stream` - SSE event stream

## Expected Output

```
id: 550e8400-e29b-41d4-a716-446655440000
event: data
data: {"type": "metric", "name": "cpu_usage", "value": 45.2}
retry: 5000

id: 550e8400-e29b-41d4-a716-446655440001
event: heartbeat
data: {"timestamp": "2024-01-01T12:00:00", "clients": 3}
retry: 5000
```

## Troubleshooting

**Port already in use:**
```bash
uvicorn main:app --port 8001
```

**Module not found:**
```bash
# Ensure you're in the project root
cd "c:\Realtime-app-stuffs\Real-Time Streaming API"
python -m pip install -r requirements.txt
```

**CORS issues (browser):**
Add to `app/api.py`:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```
