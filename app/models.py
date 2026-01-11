from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime
from enum import Enum
import json


class EventType(str, Enum):
    DATA = "data"
    HEARTBEAT = "heartbeat"
    SYSTEM = "system"


class StreamEvent(BaseModel):
    id: str
    event: EventType
    data: Any
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    def to_sse_format(self) -> str:
        lines = [
            f"id: {self.id}",
            f"event: {self.event.value}",
            f"data: {json.dumps(self.data, default=str)}",
            "retry: 5000",
            ""
        ]
        return "\n".join(lines) + "\n"
