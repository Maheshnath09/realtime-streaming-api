from fastapi import FastAPI, Request, Query, Header
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.stream_manager import StreamManager
from app.producer import EventProducer, HeartbeatProducer
from typing import Optional, List
from pathlib import Path
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

stream_manager: StreamManager = None
event_producer: EventProducer = None
heartbeat_producer: HeartbeatProducer = None

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    global stream_manager, event_producer, heartbeat_producer
    
    logger.info("Starting Real-Time Streaming API v1.2")
    stream_manager = StreamManager(max_queue_size=100, history_size=1000)
    event_producer = EventProducer(stream_manager)
    heartbeat_producer = HeartbeatProducer(stream_manager, interval=30)
    
    await event_producer.start()
    await heartbeat_producer.start()
    logger.info("All producers started")
    
    yield
    
    logger.info("Shutting down")
    await event_producer.stop()
    await heartbeat_producer.stop()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Real-Time Streaming API",
    description="Production-ready SSE streaming with event replay, topic subscriptions, and client metadata",
    version="1.2.0",
    lifespan=lifespan
)

# CORS Middleware - Allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "status": "running",
        "version": "1.2.0",
        "clients": stream_manager.get_client_count(),
        "history_size": stream_manager.get_history_size(),
        "endpoints": {
            "demo": "/demo",
            "stream": "/stream",
            "health": "/health",
            "clients": "/clients",
            "docs": "/docs"
        },
        "features": ["cors", "topic_subscriptions", "client_metadata", "event_replay"]
    }


@app.get("/demo")
async def demo():
    """
    Serve the interactive browser demo client.
    Open this in your browser to see real-time events streaming!
    """
    demo_file = PROJECT_ROOT / "examples" / "browser_client.html"
    return FileResponse(demo_file, media_type="text/html")


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "connected_clients": stream_manager.get_client_count(),
        "event_history_size": stream_manager.get_history_size(),
        "producers": {"event_producer": "running", "heartbeat_producer": "running"}
    }


@app.get("/clients")
async def list_clients():
    """List all connected clients with their metadata"""
    return {
        "count": stream_manager.get_client_count(),
        "clients": stream_manager.get_all_clients_info()
    }


@app.get("/stream")
async def stream_events(
    request: Request,
    topics: Optional[str] = Query(None, description="Comma-separated topics to subscribe to (e.g., 'cpu,memory,alert')"),
    client_name: Optional[str] = Query(None, description="Human-readable client name"),
    tags: Optional[str] = Query(None, description="Comma-separated tags (e.g., 'dashboard,production')"),
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID", description="Resume from this event ID")
):
    """
    SSE streaming endpoint with topic filtering, client metadata, and event replay.
    
    - **topics**: Filter events by topic (cpu, memory, log, alert, heartbeat). Leave empty for all.
    - **client_name**: Identify your client (e.g., 'main-dashboard')
    - **tags**: Add tags for grouping (e.g., 'finance,priority-high')
    - **Last-Event-ID**: (Header) Resume streaming from this event ID after reconnection
    """
    # Parse topics and tags
    topic_list = [t.strip().lower() for t in topics.split(",")] if topics else None
    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    
    async def event_generator():
        # Register client with metadata
        async with stream_manager.client_stream(
            client_name=client_name,
            tags=tag_list,
            topics=topic_list
        ) as (client_id, queue):
            logger.info(f"Client {client_id} ({client_name or 'anonymous'}) streaming, topics={topic_list}")
            
            # Handle event replay if Last-Event-ID is provided
            if last_event_id:
                logger.info(f"Client {client_id} reconnecting with Last-Event-ID: {last_event_id}")
                replayed = await stream_manager.replay_events(last_event_id, queue)
                logger.info(f"Replayed {replayed} events to client {client_id}")
            
            try:
                while True:
                    if await request.is_disconnected():
                        logger.info(f"Client {client_id} disconnected")
                        break
                    
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=1.0)
                        
                        # Topic filtering
                        if topic_list:
                            event_topic = event.data.get("type", event.event.value) if isinstance(event.data, dict) else event.event.value
                            # Always allow heartbeat unless explicitly filtered out
                            if event.event.value == "heartbeat" and "heartbeat" not in topic_list:
                                continue
                            elif event.event.value != "heartbeat" and event_topic not in topic_list:
                                continue
                        
                        yield event.to_sse_format()
                    except asyncio.TimeoutError:
                        continue
                        
            except Exception as e:
                logger.error(f"Stream error {client_id}: {e}")
            finally:
                logger.info(f"Client {client_id} closed")
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

