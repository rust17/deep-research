import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(Enum):
    WORKFLOW_START = "workflow_start"
    AGENT_THINK = "agent_think"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    STEP_COMPLETE = "step_complete"
    ERROR = "error"
    INFO = "info"
    WARNING = "warning"
    WORKFLOW_END = "workflow_end"


@dataclass
class Event:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class StreamHandler:
    def __init__(self):
        self._subscribers: list[Callable[[Event], None]] = []

    def subscribe(self, callback: Callable[[Event], None]):
        """Register a callback function to handle events."""
        self._subscribers.append(callback)

    def emit(self, event_type: EventType, data: dict[str, Any] | None = None):
        """Emit an event to all subscribers."""
        event = Event(type=event_type, data=data or {})
        for subscriber in self._subscribers:
            try:
                subscriber(event)
            except Exception as e:
                # We don't want a failing subscriber to break the main workflow
                print(f"Error in subscriber: {e}")


# Global instance for easy access if needed,
# though passing it through constructors is preferred for testing.
default_stream_handler = StreamHandler()
