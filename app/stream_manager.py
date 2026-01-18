import asyncio
import uuid
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager
from datetime import datetime
from collections import deque
from app.models import StreamEvent
import logging

logger = logging.getLogger(__name__)


class EventHistory:
    """
    Ring buffer for storing recent events.
    Enables event replay when clients reconnect with Last-Event-ID.
    """
    def __init__(self, max_size: int = 1000):
        self._buffer: deque = deque(maxlen=max_size)
        self._event_index: Dict[str, int] = {}  # event_id -> position hint
        self._lock = asyncio.Lock()
    
    async def add(self, event: StreamEvent):
        """Add an event to the history buffer"""
        async with self._lock:
            self._buffer.append(event)
            # Store index hint for faster lookup
            self._event_index[event.id] = len(self._buffer) - 1
            
            # Clean up old index entries (keep only recent)
            if len(self._event_index) > len(self._buffer) * 2:
                current_ids = {e.id for e in self._buffer}
                self._event_index = {k: v for k, v in self._event_index.items() if k in current_ids}
    
    async def get_events_after(self, last_event_id: str) -> List[StreamEvent]:
        """
        Get all events after the specified event ID.
        Returns empty list if event ID not found (too old or invalid).
        """
        async with self._lock:
            # Find the event with the given ID
            found_index = -1
            for i, event in enumerate(self._buffer):
                if event.id == last_event_id:
                    found_index = i
                    break
            
            if found_index == -1:
                # Event not found - it's too old or invalid
                logger.warning(f"Event {last_event_id} not found in history (may be too old)")
                return []
            
            # Return all events after the found index
            events_after = list(self._buffer)[found_index + 1:]
            logger.info(f"Replaying {len(events_after)} events after {last_event_id}")
            return events_after
    
    def get_size(self) -> int:
        """Get current number of events in buffer"""
        return len(self._buffer)
    
    def get_latest_event_id(self) -> Optional[str]:
        """Get the ID of the most recent event"""
        if self._buffer:
            return self._buffer[-1].id
        return None


class ClientInfo:
    """Stores metadata about a connected client"""
    def __init__(
        self,
        client_id: str,
        queue: asyncio.Queue,
        client_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        topics: Optional[List[str]] = None
    ):
        self.client_id = client_id
        self.queue = queue
        self.client_name = client_name or "anonymous"
        self.tags = tags or []
        self.topics = topics  # None means all topics
        self.connected_at = datetime.utcnow()
        self.events_received = 0
    
    def to_dict(self) -> dict:
        return {
            "client_id": self.client_id,
            "client_name": self.client_name,
            "tags": self.tags,
            "topics": self.topics or ["all"],
            "connected_at": self.connected_at.isoformat(),
            "events_received": self.events_received,
            "queue_size": self.queue.qsize()
        }


class StreamManager:
    def __init__(self, max_queue_size: int = 100, history_size: int = 1000):
        self._clients: Dict[str, ClientInfo] = {}
        self._max_queue_size = max_queue_size
        self._lock = asyncio.Lock()
        self._event_history = EventHistory(max_size=history_size)
        
    async def register_client(
        self,
        client_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        topics: Optional[List[str]] = None
    ) -> tuple[str, asyncio.Queue]:
        client_id = str(uuid.uuid4())
        queue = asyncio.Queue(maxsize=self._max_queue_size)
        
        client_info = ClientInfo(
            client_id=client_id,
            queue=queue,
            client_name=client_name,
            tags=tags,
            topics=topics
        )
        
        async with self._lock:
            self._clients[client_id] = client_info
            
        logger.info(f"Client {client_id} ({client_name or 'anonymous'}) connected. Total: {len(self._clients)}")
        return client_id, queue
    
    async def unregister_client(self, client_id: str):
        async with self._lock:
            if client_id in self._clients:
                client_info = self._clients[client_id]
                del self._clients[client_id]
                logger.info(f"Client {client_id} ({client_info.client_name}) disconnected. Total: {len(self._clients)}")
    
    async def broadcast(self, event: StreamEvent):
        """Broadcast event to all clients and store in history"""
        # Store in history first
        await self._event_history.add(event)
        
        disconnected = []
        
        for client_id, client_info in list(self._clients.items()):
            try:
                client_info.queue.put_nowait(event)
                client_info.events_received += 1
            except asyncio.QueueFull:
                logger.warning(f"Client {client_id} ({client_info.client_name}) queue full, disconnecting")
                disconnected.append(client_id)
        
        for client_id in disconnected:
            await self.unregister_client(client_id)
    
    async def replay_events(self, last_event_id: str, queue: asyncio.Queue) -> int:
        """
        Replay events to a client that reconnected.
        Returns the number of events replayed.
        """
        events = await self._event_history.get_events_after(last_event_id)
        replayed = 0
        
        for event in events:
            try:
                queue.put_nowait(event)
                replayed += 1
            except asyncio.QueueFull:
                logger.warning(f"Queue full during replay, stopped after {replayed} events")
                break
        
        return replayed
    
    def get_client_count(self) -> int:
        return len(self._clients)
    
    def get_history_size(self) -> int:
        """Get current number of events in history buffer"""
        return self._event_history.get_size()
    
    def get_all_clients_info(self) -> List[dict]:
        """Return metadata for all connected clients"""
        return [client_info.to_dict() for client_info in self._clients.values()]
    
    def get_client_info(self, client_id: str) -> Optional[dict]:
        """Get info for a specific client"""
        client_info = self._clients.get(client_id)
        return client_info.to_dict() if client_info else None
    
    @asynccontextmanager
    async def client_stream(
        self,
        client_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        topics: Optional[List[str]] = None
    ):
        client_id, queue = await self.register_client(client_name, tags, topics)
        try:
            yield client_id, queue
        finally:
            await self.unregister_client(client_id)


