# astock_engine/core/__init__.py
"""
Core Python API for ASTOCK Quant Engine
"""

# 先尝试从eventbus导入
try:
    from .eventbus import EventBus, EventType, Event
    # 创建create_event函数
    def create_event(event_type: EventType, data: dict) -> Event:
        """创建事件对象的便捷函数"""
        return Event(event_type, data)
    
except ImportError as e:
    print(f"Warning: Could not import from eventbus: {e}")
    # 提供回退实现
    from enum import Enum
    from dataclasses import dataclass
    from typing import Dict, Any, Optional
    import time
    
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
    
    class EventBus:
        def __init__(self, executor_threads: int = 4):
            self._executor_threads = executor_threads
            print(f"Fallback EventBus created with {executor_threads} threads")
        
        def subscribe(self, event_type, callback, filter_func=None):
            print(f"Fallback: Subscribed to {event_type}")
            return 1
        
        def unsubscribe(self, subscription_id):
            print(f"Fallback: Unsubscribed {subscription_id}")
            return True
    
    def create_event(event_type: EventType, data: dict) -> Event:
        return Event(event_type, data)

# 导出公共API
__all__ = ["EventBus", "EventType", "Event", "create_event"]