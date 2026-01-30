# EventBus Python 接口
"""
EventBus - 统一的事件总线接口

优先使用 C++ 原生实现（高性能 769K events/sec）
如果 C++ 模块不可用，回退到 Pure Python 实现
"""

from typing import Callable, Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)

# 尝试导入 C++ 原生 EventBus
_native_available = False
_cpp_eventbus = None

try:
    # 方式1: 尝试从单独的 eventbus_native 模块导入
    import eventbus_native as native_eb
    _native_available = True
    _cpp_eventbus = native_eb
    logger.info("Using C++ Native EventBus (High Performance)")
except ImportError:
    try:
        # 方式2: 尝试从 _native 模块中获取
        import _native
        if hasattr(_native, 'EventBus'):
            _native_available = True
            _cpp_eventbus = _native
            logger.info("Using C++ Native EventBus from _native module")
    except ImportError:
        pass

# 如果 C++ 不可用，导入 Pure Python 实现
if not _native_available:
    logger.warning("C++ EventBus not available, using Pure Python implementation (slower)")
    from .eventbus_simple import (
        EventBus as PythonEventBus,
        EventType,
        Event,
        subscribe,
        publish,
        unsubscribe,
        get_global_bus
    )


# ===== 统一的 EventType 枚举 =====
if _native_available:
    # 使用 C++ 的 EventType
    EventType = _cpp_eventbus.EventType
else:
    # 已从 eventbus_simple 导入
    pass


# ===== Event 类封装 =====
if _native_available:
    @dataclass
    class Event:
        """Python Event 封装（兼容 C++ Event）"""
        type: EventType
        data: Dict[str, Any]
        timestamp: Optional[float] = None
        
        def __post_init__(self):
            if self.timestamp is None:
                self.timestamp = datetime.now().timestamp()
        
        def to_cpp_event(self):
            """转换为 C++ Event"""
            cpp_event = _cpp_eventbus.Event(self.type.name)
            cpp_event.timestamp = int(self.timestamp * 1000000)  # 微秒
            
            # 设置属性
            for key, value in self.data.items():
                cpp_event.set_attribute(key, str(value))
            
            return cpp_event
        
        def to_cpp_format(self):
            """转换为 C++ EventFormat"""
            import json
            
            evt_format = _cpp_eventbus.EventFormat()
            evt_format.type = self.type
            evt_format.topic = self.data.get('topic', self.type.name.lower())
            evt_format.source = self.data.get('source', 'python')
            
            # 序列化 data
            if 'payload' not in self.data:
                self.data['payload'] = {}
            
            return evt_format
else:
    # 已从 eventbus_simple 导入
    pass


# ===== EventBus 统一接口 =====
class EventBus:
    """
    EventBus 统一接口
    
    自动选择 C++ 实现或 Python 实现
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化 EventBus
        
        Args:
            config: 配置参数
                - worker_threads: 工作线程数（仅C++）
                - execution_mode: 'sync' 或 'async'
                - max_queue_size: 最大队列大小
        """
        self._impl = None
        self._is_cpp = False
        
        if _native_available:
            # 使用 C++ 实现
            self._init_cpp_eventbus(config or {})
            self._is_cpp = True
        else:
            # 使用 Python 实现
            self._impl = PythonEventBus(
                queue_size=config.get('max_queue_size', 1000) if config else 1000
            )
            self._is_cpp = False
    
    def _init_cpp_eventbus(self, config: Dict):
        """初始化 C++ EventBus"""
        cpp_config = _cpp_eventbus.EventBusConfig()
        
        # 设置配置
        cpp_config.worker_threads = config.get('worker_threads', 4)
        cpp_config.max_queue_size = config.get('max_queue_size', 10000)
        cpp_config.execution_mode = (
            _cpp_eventbus.ExecutionMode.ASYNC 
            if config.get('execution_mode') == 'async' 
            else _cpp_eventbus.ExecutionMode.SYNC
        )
        
        # 创建 EventBus
        self._impl = _cpp_eventbus.EventBus.create(cpp_config)
        self._impl.start()
        
        logger.info(f"C++ EventBus initialized: {cpp_config.worker_threads} threads, "
                   f"queue={cpp_config.max_queue_size}")
    
    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> str:
        """
        订阅事件
        
        Args:
            event_type: 事件类型
            callback: 回调函数
            
        Returns:
            subscription_id: 订阅ID
        """
        if self._is_cpp:
            # C++ 订阅
            topic = event_type.name.lower()
            
            def cpp_callback(cpp_event):
                # 将 C++ EventFormat 转换为 Python Event
                py_event = Event(
                    type=event_type,
                    data={'cpp_event': cpp_event},
                    timestamp=datetime.now().timestamp()
                )
                callback(py_event)
            
            subscription_id = self._impl.subscribe(topic, cpp_callback)
            return subscription_id
        else:
            # Python 订阅
            self._impl.subscribe(event_type, callback)
            return f"python_{event_type.name}"
    
    def publish(self, event: Event):
        """
        发布事件
        
        Args:
            event: 事件对象
        """
        if self._is_cpp:
            # 发布到 C++ EventBus
            cpp_format = event.to_cpp_format()
            result = self._impl.publish_format(cpp_format)
            
            if not result:
                logger.warning(f"Failed to publish event: {event.type}")
        else:
            # 发布到 Python EventBus
            self._impl.publish(event)
    
    def unsubscribe(self, subscription_id: str):
        """取消订阅"""
        if self._is_cpp:
            self._impl.unsubscribe(subscription_id)
        else:
            # Python 实现的取消订阅逻辑
            pass
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if self._is_cpp:
            return self._impl.get_stats()
        else:
            return self._impl.get_stats()
    
    def shutdown(self):
        """关闭 EventBus"""
        if self._is_cpp:
            self._impl.shutdown()
        else:
            self._impl.shutdown()
    
    def __repr__(self):
        impl_type = "C++ Native" if self._is_cpp else "Pure Python"
        return f"<EventBus ({impl_type})>"


# ===== 全局 EventBus 单例 =====
_global_bus: Optional[EventBus] = None

def get_global_bus() -> EventBus:
    """获取全局 EventBus 单例"""
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus


def subscribe(event_type: EventType, callback: Callable[[Event], None]):
    """订阅全局 EventBus"""
    get_global_bus().subscribe(event_type, callback)


def publish(event: Event):
    """发布到全局 EventBus"""
    get_global_bus().publish(event)


def unsubscribe(subscription_id: str):
    """取消订阅"""
    get_global_bus().unsubscribe(subscription_id)


# 导出
__all__ = [
    'EventBus',
    'EventType',
    'Event',
    'subscribe',
    'publish',
    'unsubscribe',
    'get_global_bus',
]
