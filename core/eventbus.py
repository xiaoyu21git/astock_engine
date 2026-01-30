# EventBus.py
"""
Python-friendly wrapper for the C++ EventBus (pybind11 bindings).
Handles:
- Subscribing and publishing events
- Event filtering
- Synchronous wait for events
"""

from typing import Callable, Dict, Any, Optional
import threading
from dataclasses import dataclass
from enum import Enum
import json
import time

try:
    # Prefer the compiled package extension if available
    from . import _native as native
except Exception:
    try:
        # fallback to shim that re-exports native symbols
        from . import quant_core_native as native
    except Exception:
        import quant_core_native as native


class EventType(Enum):
    SYSTEM = "system"
    MARKET_DATA = "market_data"
    STRATEGY_SIGNAL = "strategy_signal"
    ORDER = "order"
    RISK = "risk"
    TRADE = "trade"
    PERFORMANCE = "performance"


@dataclass
class Event:
    type: EventType
    data: Dict[str, Any]
    timestamp: Optional[float] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()

    def to_native(self) -> native.Event:
        """Convert Python Event to native C++ Event"""
        attrs = {
            "event_type": self.type.value,
            "timestamp": str(self.timestamp),
            "data": json.dumps(self.data, ensure_ascii=False)
        }
        attrs.update(self.data)
        return native.Event(
            type=native.EventType.USER_CUSTOM,
            timestamp=int(self.timestamp * 1e6),
            attributes=attrs
        )


class EventBus:
    """Python-friendly EventBus wrapper"""

    def __init__(self, executor_threads: int = 4):
        self._native_bus = native.EventBus()
        self._subscribers = {}  # subscription_id -> metadata
        self._lock = threading.RLock()

    def subscribe(
        self,
        event_type: EventType,
        callback: Callable[[Event], None],
        filter_func: Optional[Callable[[Event], bool]] = None
    ):
        """Subscribe to events with optional filter"""

        def wrapped_callback(native_event):
            try:
                py_event = self._native_to_python(native_event)
                if filter_func and not filter_func(py_event):
                    return
                callback(py_event)
            except Exception as e:
                print(f"Error in event handler: {e}")

        native_type = self._python_to_native_type(event_type)
        subscription_id = self._native_bus.subscribe(native_type, wrapped_callback)

        with self._lock:
            self._subscribers[subscription_id] = {
                "event_type": event_type,
                "callback": callback,
                "filter": filter_func
            }

        return subscription_id

    def unsubscribe(self, subscription_id):
        """Unsubscribe from an event"""
        with self._lock:
            self._subscribers.pop(subscription_id, None)
        return self._native_bus.unsubscribe(subscription_id)

    def publish(self, event: Event):
        """Publish an Event object"""
        native_event = event.to_native()
        return self._native_bus.publish(native_event)

    def publish_dict(self, event_type: EventType, data: Dict[str, Any]):
        """Convenience method: publish a dictionary directly"""
        event = Event(type=event_type, data=data)
        return self.publish(event)

    def start(self):
        return self._native_bus.start()

    def stop(self):
        return self._native_bus.stop()

    def wait_for_event(
        self,
        event_type: EventType,
        timeout: float = 5.0,
        condition: Optional[Callable[[Event], bool]] = None
    ):
        """Synchronously wait for a specific event"""
        event_received = threading.Event()
        received_event = None

        def handler(event: Event):
            nonlocal received_event
            if condition is None or condition(event):
                received_event = event
                event_received.set()

        subscription_id = self.subscribe(event_type, handler)
        try:
            if event_received.wait(timeout):
                return received_event
            else:
                raise TimeoutError(f"Timeout waiting for event: {event_type}")
        finally:
            self.unsubscribe(subscription_id)

    # ------------------ private helpers ------------------

    def _native_to_python(self, native_event) -> Event:
        """Convert a native C++ event to Python Event"""
        attrs = {key: native_event.get_attribute(key) for key in native_event.attributes}
        event_type_str = attrs.get("event_type", "strategy_signal")
        event_type = EventType(event_type_str)
        data_str = attrs.get("data", "{}")
        try:
            data = json.loads(data_str)
        except Exception:
            data = attrs
        timestamp = float(attrs.get("timestamp", 0))
        if timestamp == 0:
            timestamp = native_event.timestamp / 1e6
        return Event(type=event_type, data=data, timestamp=timestamp)

    def _python_to_native_type(self, event_type: EventType):
        """Map Python EventType to native EventType"""
        mapping = {
            EventType.SYSTEM: native.EventType.SYSTEM,
            EventType.MARKET_DATA: native.EventType.MARKET_DATA,
            EventType.STRATEGY_SIGNAL: native.EventType.USER_CUSTOM,
            EventType.ORDER: native.EventType.USER_CUSTOM,
            EventType.RISK: native.EventType.WARNING,
            EventType.TRADE: native.EventType.USER_CUSTOM,
            EventType.PERFORMANCE: native.EventType.USER_CUSTOM,
        }
        return mapping.get(event_type, native.EventType.USER_CUSTOM)
