# System Architecture

## Design Principles

### 1. Non-Blocking Everything

Every operation is async/await. No blocking I/O, no thread pools, no synchronous calls.

**Why?** Single-threaded async can handle 10K+ concurrent connections efficiently.

### 2. Backpressure at the Edge

Slow clients are dropped, not queued indefinitely.

**Why?** Prevents memory exhaustion and cascading failures.

### 3. O(1) Broadcast

Event fan-out is constant time per client.

**Why?** System performance doesn't degrade with client count.

### 4. Fail Fast

Errors are caught early and clients are disconnected cleanly.

**Why?** Prevents resource leaks and zombie connections.

## Data Flow

```
Producer → StreamManager → Client Queues → SSE Response
   ↓            ↓              ↓              ↓
Generate    Broadcast      Buffer         Format
Events      O(N)           Per-Client     SSE Protocol
```

## Component Details

### StreamManager

**Responsibilities:**
- Client registration/unregistration
- Event broadcasting
- Slow client detection

**Key Methods:**
- `register_client()`: Creates queue, returns (id, queue)
- `broadcast()`: Sends event to all clients (non-blocking)
- `unregister_client()`: Cleanup on disconnect

**Concurrency:**
- Lock only for dict modifications
- No lock for broadcast (read-only iteration)
- put_nowait ensures non-blocking writes

### Event Producers

**EventProducer:**
- Simulates real-time data source
- Runs in background asyncio task
- Generates events at variable rate

**HeartbeatProducer:**
- Sends periodic keep-alive events
- Detects dead connections
- Prevents proxy timeouts

**Lifecycle:**
- Started in FastAPI lifespan startup
- Gracefully cancelled on shutdown
- Uses asyncio.Task for background execution

### SSE Endpoint

**Request Flow:**
1. Client connects to /stream
2. StreamManager registers client
3. Generator yields events from queue
4. Periodic disconnect checks
5. Cleanup on exit (context manager)

**Response Headers:**
- `Content-Type: text/event-stream`
- `Cache-Control: no-cache`
- `Connection: keep-alive`
- `X-Accel-Buffering: no` (nginx)

## Memory Model

**Per Client:**
- Queue: ~8KB + (event_size * queue_size)
- Metadata: ~1KB

**Total:**
- 1000 clients × 100 events × 1KB = ~100MB
- Plus Python overhead

**Mitigation:**
- Bounded queues (maxsize)
- Automatic client cleanup
- Event size limits

## Failure Modes

### Slow Client

**Symptom:** Queue fills up
**Detection:** put_nowait raises QueueFull
**Action:** Disconnect client
**Impact:** None on other clients

### Producer Crash

**Symptom:** No new events
**Detection:** Task exception
**Action:** Log error, restart producer
**Impact:** Clients stay connected, receive heartbeats

### Network Partition

**Symptom:** Client disconnected
**Detection:** request.is_disconnected()
**Action:** Exit generator, cleanup
**Impact:** Client auto-reconnects

## Scalability

### Vertical (Single Server)

- **CPU**: Async I/O is CPU-light
- **Memory**: Bounded by client_count × queue_size
- **Network**: Limited by NIC bandwidth

**Limits:** ~10K clients per server

### Horizontal (Multi-Server)

**Option 1: Redis Pub/Sub**
- Producers publish to Redis
- Each server subscribes
- Clients connect to any server

**Option 2: Redis Streams**
- Producers write to stream
- Servers consume with consumer groups
- Better persistence and replay

**Option 3: Message Queue**
- Kafka/RabbitMQ for events
- Servers consume from queue
- Best for high throughput

## Security Considerations

### Authentication

- JWT tokens in Authorization header
- Validate before streaming
- Refresh token mechanism

### Rate Limiting

- Per-IP connection limits
- Event rate limits
- Queue size limits

### DoS Protection

- Connection timeouts
- Max clients per IP
- Reverse proxy (nginx)

## Monitoring

**Metrics:**
- Connected clients
- Events/second
- Queue depths
- Disconnect rate
- Memory usage

**Alerts:**
- High disconnect rate
- Memory threshold
- Producer failures
- Queue saturation
