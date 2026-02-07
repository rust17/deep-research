from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Event(Enum):
    INIT = "init"
    FINISH = "finish"
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    STEP = "step"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


@dataclass
class Pulse:
    type: Event
    content: Any = None
    name: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["type"] = self.type.value
        return data


class StreamHandler:
    def __init__(self):
        self._subscribers: list[Callable[[Pulse], None]] = []

    def subscribe(self, callback: Callable[[Pulse], None]):
        self._subscribers.append(callback)

    def emit(self, pulse: Pulse):
        for subscriber in self._subscribers:
            try:
                subscriber(pulse)
            except Exception as e:
                print(f"Error in subscriber: {e}")


default_stream_handler = StreamHandler()
