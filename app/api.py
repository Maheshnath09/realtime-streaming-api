from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from app.stream_manager import StreamManager
from app.producer import EventProducer, HeartbeatProducer
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

stream_manager: StreamManager = None
event_producer: EventProducer = None
heartbeat_producer: HeartbeatProducer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global stream_manager, event_producer, heartbeat_producer
    
    logger.info("Starting Real-Time Streaming API")
    stream_manager = StreamManager(max_queue_size=100)
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
    description="Production-ready SSE streaming with async event buffers",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    return {
        "status": "running",
        "clients": stream_manager.get_client_count(),
        "endpoints": {"stream": "/stream", "health": "/health"}
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "connected_clients": stream_manager.get_client_count(),
        "producers": {"event_producer": "running", "heartbeat_producer": "running"}
    }


@app.get("/stream")
async def stream_events(request: Request):
    async def event_generator():
        async with stream_manager.client_stream() as (client_id, queue):
            logger.info(f"Client {client_id} streaming")
            
            try:
                while True:
                    if await request.is_disconnected():
                        logger.info(f"Client {client_id} disconnected")
                        break
                    
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=1.0)
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
