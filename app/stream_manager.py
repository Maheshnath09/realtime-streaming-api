import asyncio
import uuid
from typing import Dict
from contextlib import asynccontextmanager
from app.models import StreamEvent
import logging

logger = logging.getLogger(__name__)


class StreamManager:
    def __init__(self, max_queue_size: int = 100):
        self._clients: Dict[str, asyncio.Queue] = {}
        self._max_queue_size = max_queue_size
        self._lock = asyncio.Lock()
        
    async def register_client(self) -> tuple[str, asyncio.Queue]:
        client_id = str(uuid.uuid4())
        queue = asyncio.Queue(maxsize=self._max_queue_size)
        
        async with self._lock:
            self._clients[client_id] = queue
            
        logger.info(f"Client {client_id} connected. Total: {len(self._clients)}")
        return client_id, queue
    
    async def unregister_client(self, client_id: str):
        async with self._lock:
            if client_id in self._clients:
                del self._clients[client_id]
                logger.info(f"Client {client_id} disconnected. Total: {len(self._clients)}")
    
    async def broadcast(self, event: StreamEvent):
        disconnected = []
        
        for client_id, queue in list(self._clients.items()):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"Client {client_id} queue full, disconnecting")
                disconnected.append(client_id)
        
        for client_id in disconnected:
            await self.unregister_client(client_id)
    
    def get_client_count(self) -> int:
        return len(self._clients)
    
    @asynccontextmanager
    async def client_stream(self):
        client_id, queue = await self.register_client()
        try:
            yield client_id, queue
        finally:
            await self.unregister_client(client_id)
