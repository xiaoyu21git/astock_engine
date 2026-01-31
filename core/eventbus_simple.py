"""
Simplified EventBus Implementation (Pure Python Fallback)
当 C++ 原生模块不可用时使用的纯Python实现
"""

import threading
import queue
import time
from typing import Callable, Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


class EventType(Enum):
    """事件类型枚举"""
    SYSTEM = "system"
    MARKET_DATA = "market_data"
    STRATEGY_SIGNAL = "strategy_signal"
    SIGNAL = "signal"  # 交易信号
    ORDER = "order"
    ORDER_RESPONSE = "order_response"  # 订单响应
    RISK = "risk"
    TRADE = "trade"
    PERFORMANCE = "performance"
    ANOMALY = "anomaly"
    NEWS = "news"


@dataclass
class Event:
    """事件数据类"""
    type: EventType
    data: Dict[str, Any]
    timestamp: Optional[float] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().timestamp()
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'type': self.type.value if isinstance(self.type, EventType) else str(self.type),
            'data': self.data,
            'timestamp': self.timestamp
        }
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


class EventBus:
    """
    纯Python EventBus实现
    支持发布/订阅模式的事件总线
    """
    
    def __init__(self, queue_size: int = 1000):
        """
        初始化EventBus
        
        Args:
            queue_size: 事件队列大小
        """
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._event_queue = queue.Queue(maxsize=queue_size)
        self._lock = threading.RLock()
        self._worker_thread = None
        self._running = False
        self._event_count = 0
        
        logger.info("EventBus initialized (Pure Python implementation)")
        self._start_worker()
    
    def _start_worker(self):
        """启动工作线程"""
        self._running = True
        self._worker_thread = threading.Thread(target=self._process_events, daemon=True)
        self._worker_thread.start()
    
    def _process_events(self):
        """处理事件队列"""
        while self._running:
            try:
                event = self._event_queue.get(timeout=0.1)
                self._dispatch_event(event)
                self._event_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing event: {e}", exc_info=True)
    
    def _dispatch_event(self, event: Event):
        """
        分发事件给订阅者
        
        Args:
            event: 要分发的事件
        """
        with self._lock:
            subscribers = self._subscribers.get(event.type, [])
            
            for callback in subscribers:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"Error in event handler: {e}", exc_info=True)
    
    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]):
        """
        订阅事件
        
        Args:
            event_type: 事件类型（可以是字符串或EventType枚举）
            callback: 回调函数
        """
        # 支持字符串类型的event_type
        if isinstance(event_type, str):
            event_type_str = event_type
        else:
            event_type_str = event_type.value if hasattr(event_type, 'value') else str(event_type)
            
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)
                logger.debug(f"Subscribed to {event_type_str}, total subscribers: {len(self._subscribers[event_type])}")
                
        # 返回订阅ID
        import uuid
        return str(uuid.uuid4())
    
    def unsubscribe(self, event_type: EventType, callback: Callable[[Event], None]):
        """
        取消订阅
        
        Args:
            event_type: 事件类型
            callback: 回调函数
        """
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)
                    logger.debug(f"Unsubscribed from {event_type.value}")
                except ValueError:
                    pass
    
    def publish(self, event_type_or_event, data=None):
        """
        发布事件
        
        Args:
            event_type_or_event: Event对象或事件类型字符串
            data: 事件数据（当第一个参数是字符串时使用）
            
        Returns:
            处理该事件的订阅者数量
        """
        # 兼容两种调用方式
        if isinstance(event_type_or_event, Event):
            event = event_type_or_event
        else:
            # 从字符串和数据创建Event对象
            event = Event(
                type=event_type_or_event,
                data=data if data is not None else {},
                timestamp=time.time()
            )
        
        try:
            self._event_queue.put(event, block=False)
            self._event_count += 1
            
            event_type_str = event.type if isinstance(event.type, str) else event.type.value
            logger.debug(f"Event published: {event_type_str}, queue size: {self._event_queue.qsize()}")
            
            # 返回订阅者数量
            return len(self._subscribers.get(event.type, []))
        except queue.Full:
            event_type_str = event.type if isinstance(event.type, str) else event.type.value
            logger.warning(f"Event queue full, dropping event: {event_type_str}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取EventBus统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            subscriber_counts = {}
            for event_type, callbacks in self._subscribers.items():
                key = event_type.value if hasattr(event_type, 'value') else str(event_type)
                subscriber_counts[key] = len(callbacks)
            
            return {
                'total_events': self._event_count,
                'queue_size': self._event_queue.qsize(),
                'subscribers': subscriber_counts,
                'running': self._running
            }
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息（兼容接口）"""
        stats = self.get_stats()
        return {
            'total_events': stats['total_events'],
            'total_subscribers': sum(stats['subscribers'].values()),
            'queue_size': stats['queue_size'],
            'running': stats['running']
        }
    
    def shutdown(self):
        """关闭EventBus"""
        logger.info("Shutting down EventBus...")
        self._running = False
        
        if self._worker_thread:
            self._worker_thread.join(timeout=2.0)
        
        logger.info("EventBus shutdown complete")
    
    def __del__(self):
        """析构函数"""
        self.shutdown()


# 全局EventBus单例
_global_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()


def get_global_bus() -> EventBus:
    """
    获取全局EventBus单例
    
    Returns:
        EventBus实例
    """
    global _global_bus
    
    with _bus_lock:
        if _global_bus is None:
            _global_bus = EventBus()
        return _global_bus


# 便捷函数
def subscribe(event_type: EventType, callback: Callable[[Event], None]):
    """订阅全局EventBus的事件"""
    get_global_bus().subscribe(event_type, callback)


def publish(event: Event):
    """发布事件到全局EventBus"""
    get_global_bus().publish(event)


def unsubscribe(event_type: EventType, callback: Callable[[Event], None]):
    """取消订阅全局EventBus的事件"""
    get_global_bus().unsubscribe(event_type, callback)
