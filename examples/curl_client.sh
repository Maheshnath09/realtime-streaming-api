#!/bin/bash
echo "Connecting to SSE stream..."
echo "Press Ctrl+C to disconnect"
echo ""
curl -N -H "Accept: text/event-stream" http://localhost:8000/stream
