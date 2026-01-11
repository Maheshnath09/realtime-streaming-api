"""
Test suite for Real-Time Streaming API

Run with: pytest test_streaming.py -v
"""

import asyncio
import pytest
from app.models import StreamEvent, EventType
from app.stream_manager import StreamManager
from app.producer import EventProducer, HeartbeatProducer


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
    print("✅ All tests passed!")
