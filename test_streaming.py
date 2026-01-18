"""
Test suite for Real-Time Streaming API v1.1

Run with: pytest test_streaming.py -v
"""

import asyncio
import pytest
from app.models import StreamEvent, EventType
from app.stream_manager import StreamManager, ClientInfo


@pytest.mark.asyncio
async def test_stream_manager_registration():
    """Test client registration and unregistration"""
    manager = StreamManager(max_queue_size=10)
    
    client_id, queue = await manager.register_client()
    assert client_id is not None
    assert manager.get_client_count() == 1
    
    await manager.unregister_client(client_id)
    assert manager.get_client_count() == 0


@pytest.mark.asyncio
async def test_broadcast_to_multiple_clients():
    """Test broadcasting events to multiple clients"""
    manager = StreamManager(max_queue_size=10)
    
    # Register 3 clients
    clients = []
    for _ in range(3):
        client_id, queue = await manager.register_client()
        clients.append((client_id, queue))
    
    assert manager.get_client_count() == 3
    
    # Broadcast event
    event = StreamEvent(id="test-1", event=EventType.DATA, data={"test": "data"})
    await manager.broadcast(event)
    
    # Verify all clients received event
    for client_id, queue in clients:
        received_event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received_event.id == "test-1"
        assert received_event.data == {"test": "data"}
    
    # Cleanup
    for client_id, _ in clients:
        await manager.unregister_client(client_id)


@pytest.mark.asyncio
async def test_backpressure_handling():
    """Test that slow clients are disconnected when queue is full"""
    manager = StreamManager(max_queue_size=2)
    
    client_id, queue = await manager.register_client()
    assert manager.get_client_count() == 1
    
    # Fill queue to capacity
    event1 = StreamEvent(id="1", event=EventType.DATA, data={"num": 1})
    event2 = StreamEvent(id="2", event=EventType.DATA, data={"num": 2})
    await manager.broadcast(event1)
    await manager.broadcast(event2)
    
    # Queue is now full (maxsize=2)
    # Next broadcast should disconnect the client
    event3 = StreamEvent(id="3", event=EventType.DATA, data={"num": 3})
    await manager.broadcast(event3)
    
    # Client should be disconnected
    assert manager.get_client_count() == 0


@pytest.mark.asyncio
async def test_sse_format():
    """Test SSE event formatting"""
    event = StreamEvent(
        id="test-123",
        event=EventType.DATA,
        data={"message": "hello"}
    )
    
    sse_output = event.to_sse_format()
    
    assert "id: test-123" in sse_output
    assert "event: data" in sse_output
    assert '"message": "hello"' in sse_output
    assert "retry: 5000" in sse_output
    assert sse_output.endswith("\n\n")


@pytest.mark.asyncio
async def test_event_producer_lifecycle():
    """Test producer start and stop"""
    from app.producer import EventProducer
    
    manager = StreamManager(max_queue_size=10)
    producer = EventProducer(manager)
    
    # Start producer
    await producer.start()
    assert producer._running is True
    
    # Let it produce some events
    await asyncio.sleep(0.1)
    
    # Stop producer
    await producer.stop()
    assert producer._running is False


@pytest.mark.asyncio
async def test_heartbeat_producer():
    """Test heartbeat producer"""
    from app.producer import HeartbeatProducer
    
    manager = StreamManager(max_queue_size=10)
    heartbeat = HeartbeatProducer(manager, interval=0.1)  # Fast interval for testing
    
    # Register a client
    client_id, queue = await manager.register_client()
    
    # Start heartbeat
    await heartbeat.start()
    
    # Wait for heartbeat event
    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event.event == EventType.HEARTBEAT
    assert "timestamp" in event.data
    assert "clients" in event.data
    
    # Stop heartbeat
    await heartbeat.stop()
    await manager.unregister_client(client_id)


@pytest.mark.asyncio
async def test_concurrent_clients():
    """Test system with many concurrent clients"""
    manager = StreamManager(max_queue_size=10)
    num_clients = 100
    
    # Register many clients
    clients = []
    for _ in range(num_clients):
        client_id, queue = await manager.register_client()
        clients.append((client_id, queue))
    
    assert manager.get_client_count() == num_clients
    
    # Broadcast event
    event = StreamEvent(id="broadcast-test", event=EventType.DATA, data={"test": "concurrent"})
    await manager.broadcast(event)
    
    # Verify all clients received event
    for client_id, queue in clients:
        received_event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received_event.id == "broadcast-test"
    
    # Cleanup
    for client_id, _ in clients:
        await manager.unregister_client(client_id)
    
    assert manager.get_client_count() == 0


@pytest.mark.asyncio
async def test_context_manager():
    """Test client_stream context manager"""
    manager = StreamManager(max_queue_size=10)
    
    async with manager.client_stream() as (client_id, queue):
        assert client_id is not None
        assert manager.get_client_count() == 1
        
        # Broadcast event
        event = StreamEvent(id="ctx-test", event=EventType.DATA, data={"test": "context"})
        await manager.broadcast(event)
        
        # Receive event
        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received.id == "ctx-test"
    
    # After context exit, client should be unregistered
    assert manager.get_client_count() == 0


# ==================== NEW TESTS FOR v1.1 FEATURES ====================

@pytest.mark.asyncio
async def test_client_metadata():
    """Test client registration with metadata"""
    manager = StreamManager(max_queue_size=10)
    
    # Register client with metadata
    client_id, queue = await manager.register_client(
        client_name="test-dashboard",
        tags=["production", "finance"],
        topics=["cpu", "memory"]
    )
    
    assert manager.get_client_count() == 1
    
    # Get client info
    client_info = manager.get_client_info(client_id)
    assert client_info is not None
    assert client_info["client_name"] == "test-dashboard"
    assert client_info["tags"] == ["production", "finance"]
    assert client_info["topics"] == ["cpu", "memory"]
    assert "connected_at" in client_info
    
    await manager.unregister_client(client_id)


@pytest.mark.asyncio
async def test_get_all_clients_info():
    """Test retrieving all clients info"""
    manager = StreamManager(max_queue_size=10)
    
    # Register multiple clients with different metadata
    await manager.register_client(client_name="client-1", tags=["web"])
    await manager.register_client(client_name="client-2", tags=["mobile"])
    await manager.register_client(client_name="client-3", tags=["desktop"])
    
    all_clients = manager.get_all_clients_info()
    
    assert len(all_clients) == 3
    client_names = [c["client_name"] for c in all_clients]
    assert "client-1" in client_names
    assert "client-2" in client_names
    assert "client-3" in client_names


@pytest.mark.asyncio
async def test_client_info_events_received_counter():
    """Test that events_received counter increments"""
    manager = StreamManager(max_queue_size=10)
    
    client_id, queue = await manager.register_client(client_name="counter-test")
    
    # Broadcast 3 events
    for i in range(3):
        event = StreamEvent(id=f"event-{i}", event=EventType.DATA, data={"num": i})
        await manager.broadcast(event)
    
    client_info = manager.get_client_info(client_id)
    assert client_info["events_received"] == 3
    
    await manager.unregister_client(client_id)


@pytest.mark.asyncio
async def test_context_manager_with_metadata():
    """Test client_stream context manager with metadata"""
    manager = StreamManager(max_queue_size=10)
    
    async with manager.client_stream(
        client_name="context-test",
        tags=["test"],
        topics=["alert"]
    ) as (client_id, queue):
        client_info = manager.get_client_info(client_id)
        assert client_info["client_name"] == "context-test"
        assert client_info["tags"] == ["test"]
        assert client_info["topics"] == ["alert"]
    
    # After context exit, client should be unregistered
    assert manager.get_client_count() == 0


@pytest.mark.asyncio
async def test_anonymous_client_default_name():
    """Test that clients without name get 'anonymous' as default"""
    manager = StreamManager(max_queue_size=10)
    
    client_id, queue = await manager.register_client()
    client_info = manager.get_client_info(client_id)
    
    assert client_info["client_name"] == "anonymous"
    assert client_info["tags"] == []
    assert client_info["topics"] == ["all"]  # None converts to ["all"]
    
    await manager.unregister_client(client_id)


# ==================== NEW TESTS FOR v1.2 - EVENT REPLAY ====================

@pytest.mark.asyncio
async def test_event_history_basic():
    """Test EventHistory buffer stores and retrieves events"""
    from app.stream_manager import EventHistory
    
    history = EventHistory(max_size=100)
    
    # Add events
    event1 = StreamEvent(id="evt-1", event=EventType.DATA, data={"num": 1})
    event2 = StreamEvent(id="evt-2", event=EventType.DATA, data={"num": 2})
    event3 = StreamEvent(id="evt-3", event=EventType.DATA, data={"num": 3})
    
    await history.add(event1)
    await history.add(event2)
    await history.add(event3)
    
    assert history.get_size() == 3
    assert history.get_latest_event_id() == "evt-3"


@pytest.mark.asyncio
async def test_event_history_get_events_after():
    """Test retrieving events after a specific event ID"""
    from app.stream_manager import EventHistory
    
    history = EventHistory(max_size=100)
    
    # Add 5 events
    for i in range(1, 6):
        event = StreamEvent(id=f"evt-{i}", event=EventType.DATA, data={"num": i})
        await history.add(event)
    
    # Get events after evt-2 (should return evt-3, evt-4, evt-5)
    events_after = await history.get_events_after("evt-2")
    assert len(events_after) == 3
    assert events_after[0].id == "evt-3"
    assert events_after[1].id == "evt-4"
    assert events_after[2].id == "evt-5"


@pytest.mark.asyncio
async def test_event_history_ring_buffer_overflow():
    """Test that ring buffer properly discards old events"""
    from app.stream_manager import EventHistory
    
    history = EventHistory(max_size=5)  # Small buffer
    
    # Add 10 events (overflow the buffer)
    for i in range(1, 11):
        event = StreamEvent(id=f"evt-{i}", event=EventType.DATA, data={"num": i})
        await history.add(event)
    
    # Buffer should only have last 5 events
    assert history.get_size() == 5
    assert history.get_latest_event_id() == "evt-10"
    
    # Old events should not be found
    old_events = await history.get_events_after("evt-1")
    assert len(old_events) == 0  # evt-1 is too old, not in buffer


@pytest.mark.asyncio
async def test_replay_events_to_queue():
    """Test replaying events to a client queue"""
    manager = StreamManager(max_queue_size=100, history_size=100)
    
    # Broadcast some events first
    for i in range(1, 6):
        event = StreamEvent(id=f"evt-{i}", event=EventType.DATA, data={"num": i})
        await manager.broadcast(event)
    
    # Verify history size
    assert manager.get_history_size() == 5
    
    # Create a new queue and replay from evt-2
    replay_queue = asyncio.Queue(maxsize=100)
    replayed_count = await manager.replay_events("evt-2", replay_queue)
    
    assert replayed_count == 3  # evt-3, evt-4, evt-5
    assert replay_queue.qsize() == 3
    
    # Verify the replayed events
    event = await replay_queue.get()
    assert event.id == "evt-3"


if __name__ == "__main__":
    # Run tests manually
    asyncio.run(test_stream_manager_registration())
    asyncio.run(test_broadcast_to_multiple_clients())
    asyncio.run(test_backpressure_handling())
    asyncio.run(test_sse_format())
    asyncio.run(test_event_producer_lifecycle())
    asyncio.run(test_heartbeat_producer())
    asyncio.run(test_concurrent_clients())
    asyncio.run(test_context_manager())
    asyncio.run(test_client_metadata())
    asyncio.run(test_get_all_clients_info())
    asyncio.run(test_client_info_events_received_counter())
    asyncio.run(test_context_manager_with_metadata())
    asyncio.run(test_anonymous_client_default_name())
    asyncio.run(test_event_history_basic())
    asyncio.run(test_event_history_get_events_after())
    asyncio.run(test_event_history_ring_buffer_overflow())
    asyncio.run(test_replay_events_to_queue())
    print("✅ All tests passed!")


