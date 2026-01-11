# System Diagrams

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Application                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐         ┌──────────────────┐              │
│  │   Lifespan   │────────▶│  Stream Manager  │              │
│  │   Manager    │         │                  │              │
│  └──────────────┘         │  - Client Dict   │              │
│         │                 │  - Broadcast     │              │
│         │                 │  - Backpressure  │              │
│         ▼                 └────────┬─────────┘              │
│  ┌──────────────┐                 │                         │
│  │  Producers   │                 │                         │
│  │              │                 │                         │
│  │ ┌──────────┐ │                 │                         │
│  │ │  Event   │─┼─────────────────┘                         │
│  │ │ Producer │ │  broadcast()                              │
│  │ └──────────┘ │                                            │
│  │              │                                            │
│  │ ┌──────────┐ │                                            │
│  │ │Heartbeat │─┼─────────────────┐                         │
│  │ │ Producer │ │                 │                         │
│  │ └──────────┘ │                 │                         │
│  └──────────────┘                 │                         │
│                                    ▼                         │
│                         ┌─────────────────┐                 │
│                         │  SSE Endpoint   │                 │
│                         │   /stream       │                 │
│                         └────────┬────────┘                 │
└──────────────────────────────────┼──────────────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
                    ▼              ▼              ▼
              ┌─────────┐    ┌─────────┐    ┌─────────┐
              │ Client  │    │ Client  │    │ Client  │
              │   #1    │    │   #2    │    │   #N    │
              │         │    │         │    │         │
              │ Queue   │    │ Queue   │    │ Queue   │
              │ [100]   │    │ [100]   │    │ [100]   │
              └─────────┘    └─────────┘    └─────────┘
```

## Event Flow

```
Producer Thread              Stream Manager              Client Queues
─────────────────           ────────────────            ──────────────

     │                             │                          │
     │  generate_event()           │                          │
     ├────────────────────────────▶│                          │
     │                             │                          │
     │                             │  for each client:        │
     │                             │    queue.put_nowait()    │
     │                             ├─────────────────────────▶│
     │                             │                          │
     │                             │                          │ Client #1
     │                             │                          │ receives
     │                             │                          │
     │                             ├─────────────────────────▶│
     │                             │                          │
     │                             │                          │ Client #2
     │                             │                          │ receives
     │                             │                          │
     │                             ├─────────────────────────▶│
     │                             │                          │
     │                             │                          │ Client #N
     │                             │                          │ receives
     │                             │                          │
     │  sleep(random)              │                          │
     │                             │                          │
     │  generate_event()           │                          │
     ├────────────────────────────▶│                          │
     │                             │                          │
     ▼                             ▼                          ▼
```

## Backpressure Handling

```
Normal Flow:
───────────

Producer ──▶ StreamManager ──▶ Client Queue [■■■□□□□□□□] ──▶ Client
                                   (3/10 full)              ✓ OK


Slow Client:
────────────

Producer ──▶ StreamManager ──▶ Client Queue [■■■■■■■■■■] ──X Client
                                   (10/10 FULL)            (slow)
                                        │
                                        │ QueueFull Exception
                                        ▼
                                  Disconnect Client
                                  Remove from dict
```