from collections.abc import Callable
from ..models import Event, Pulse


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
