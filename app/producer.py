import asyncio
import uuid
from datetime import datetime
from typing import Optional
from app.models import StreamEvent, EventType
from app.stream_manager import StreamManager
import logging
import random

logger = logging.getLogger(__name__)


class EventProducer:
    def __init__(self, stream_manager: StreamManager):
        self._stream_manager = stream_manager
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._produce_loop())
        logger.info("Event producer started")
    
    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Event producer stopped")
    
    async def _produce_loop(self):
        try:
            while self._running:
                event = self._generate_event()
                await self._stream_manager.broadcast(event)
                await asyncio.sleep(random.uniform(0.5, 2.0))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Producer error: {e}", exc_info=True)
    
    def _generate_event(self) -> StreamEvent:
        data_types = [
            {"type": "metric", "name": "cpu_usage", "value": random.uniform(0, 100)},
            {"type": "metric", "name": "memory_usage", "value": random.uniform(0, 100)},
            {"type": "log", "level": "INFO", "message": f"Process {uuid.uuid4()}"},
            {"type": "alert", "severity": random.choice(["low", "medium", "high"])},
        ]
        
        return StreamEvent(
            id=str(uuid.uuid4()),
            event=EventType.DATA,
            data=random.choice(data_types)
        )


class HeartbeatProducer:
    def __init__(self, stream_manager: StreamManager, interval: int = 30):
        self._stream_manager = stream_manager
        self._interval = interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info(f"Heartbeat started (interval: {self._interval}s)")
    
    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Heartbeat stopped")
    
    async def _heartbeat_loop(self):
        try:
            while self._running:
                event = StreamEvent(
                    id=str(uuid.uuid4()),
                    event=EventType.HEARTBEAT,
                    data={
                        "timestamp": datetime.utcnow().isoformat(),
                        "clients": self._stream_manager.get_client_count()
                    }
                )
                await self._stream_manager.broadcast(event)
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            raise
