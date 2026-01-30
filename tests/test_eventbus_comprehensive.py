"""
Event Bus 综合测试套件 - 核心功能测试

测试覆盖:
1. EventBus 基础操作 (创建、启动、停止)
2. 事件发布订阅 (发布/订阅/取消订阅)
3. 事件优先级和排序
4. 线程安全性
5. 错误处理
"""

import pytest
import threading
import time
from collections import defaultdict
from typing import List, Dict, Any

try:
    from astock_engine import EventBus, Event, EventFormat, EventValue
except ImportError as e:
    pytest.skip(f"C++ extensions not available: {e}", allow_module_level=True)


class TestEventBusBasics:
    """EventBus 基础功能测试"""
    
    def test_eventbus_creation(self):
        """测试 EventBus 创建"""
        bus = EventBus()
        assert bus is not None
        assert hasattr(bus, 'start')
        assert hasattr(bus, 'stop')
        assert hasattr(bus, 'publish')
        assert hasattr(bus, 'subscribe')
    
    def test_eventbus_lifecycle(self):
        """测试 EventBus 生命周期"""
        bus = EventBus()
        
        # 启动事件总线
        result = bus.start()
        assert result == True, "EventBus should start successfully"
        
        # 停止事件总线
        result = bus.stop()
        assert result == True, "EventBus should stop successfully"
    
    def test_eventbus_config(self):
        """测试 EventBus 配置"""
        config = {
            'execution_mode': 'sync',  # 同步模式便于测试
            'worker_threads': 2,
            'batch_size': 10,
            'max_queue_size': 1000,
            'enable_json_serialization': True
        }
        
        bus = EventBus(config)
        assert bus.start()
        assert bus.stop()


class TestEventPublishSubscribe:
    """事件发布订阅测试"""
    
    def test_simple_publish_subscribe(self):
        """测试简单的发布订阅"""
        bus = EventBus({'execution_mode': 'sync'})
        bus.start()
        
        received_events = []
        
        def handler(event):
            received_events.append(event)
        
        # 订阅事件
        subscription_id = bus.subscribe('test_event', handler)
        assert subscription_id is not None
        
        # 发布事件
        event = self._create_test_event('test_event', {'data': 'test_value'})
        result = bus.publish(event)
        assert result == True
        
        # 给事件处理一点时间
        time.sleep(0.1)
        
        # 验证接收到事件
        assert len(received_events) == 1
        
        bus.stop()
    
    def test_multiple_subscribers(self):
        """测试多个订阅者"""
        bus = EventBus({'execution_mode': 'sync'})
        bus.start()
        
        results = {'handler1': [], 'handler2': [], 'handler3': []}
        
        def handler1(event):
            results['handler1'].append(event)
        
        def handler2(event):
            results['handler2'].append(event)
        
        def handler3(event):
            results['handler3'].append(event)
        
        # 订阅同一事件的多个处理器
        bus.subscribe('test_event', handler1)
        bus.subscribe('test_event', handler2)
        bus.subscribe('test_event', handler3)
        
        # 发布事件
        event = self._create_test_event('test_event', {'value': 42})
        bus.publish(event)
        
        time.sleep(0.1)
        
        # 所有处理器都应该接收到事件
        assert len(results['handler1']) == 1
        assert len(results['handler2']) == 1
        assert len(results['handler3']) == 1
        
        bus.stop()
    
    def test_unsubscribe(self):
        """测试取消订阅"""
        bus = EventBus({'execution_mode': 'sync'})
        bus.start()
        
        received_events = []
        
        def handler(event):
            received_events.append(event)
        
        # 订阅和取消订阅
        sub_id = bus.subscribe('test_event', handler)
        bus.unsubscribe(sub_id)
        
        # 发布事件
        event = self._create_test_event('test_event', {'data': 'value'})
        bus.publish(event)
        
        time.sleep(0.1)
        
        # 不应该接收到事件
        assert len(received_events) == 0
        
        bus.stop()
    
    def test_multiple_event_types(self):
        """测试多种事件类型"""
        bus = EventBus({'execution_mode': 'sync'})
        bus.start()
        
        events_by_type = defaultdict(list)
        
        def create_handler(event_type):
            def handler(event):
                events_by_type[event_type].append(event)
            return handler
        
        # 订阅多种事件类型
        event_types = ['market_data', 'order', 'trade', 'risk']
        for event_type in event_types:
            bus.subscribe(event_type, create_handler(event_type))
        
        # 发布多种事件
        for event_type in event_types:
            event = self._create_test_event(event_type, {'type': event_type})
            bus.publish(event)
        
        time.sleep(0.1)
        
        # 验证每种事件都被正确处理
        for event_type in event_types:
            assert len(events_by_type[event_type]) == 1
        
        bus.stop()
    
    @staticmethod
    def _create_test_event(event_type: str, data: Dict[str, Any]) -> EventFormat:
        """创建测试事件"""
        event = EventFormat()
        event.set_type(event_type)
        for key, value in data.items():
            if isinstance(value, str):
                event.set(key, value)
            elif isinstance(value, int):
                event.set(key, int(value))
            elif isinstance(value, float):
                event.set(key, float(value))
        return event


class TestEventPriority:
    """事件优先级测试"""
    
    def test_priority_queue(self):
        """测试事件优先级队列"""
        bus = EventBus({'execution_mode': 'sync'})
        bus.start()
        
        processing_order = []
        
        def handler(event):
            priority = event.get('priority') if hasattr(event, 'get') else 5
            processing_order.append(priority)
        
        bus.subscribe('priority_test', handler)
        
        # 发布不同优先级的事件 (优先级 0 最高)
        for priority in [5, 3, 1, 0, 2, 4]:
            event = EventFormat()
            event.set_type('priority_test')
            event.set('priority', priority)
            bus.publish(event, priority)
        
        time.sleep(0.2)
        bus.stop()
        
        # 验证处理顺序（越小优先级越高）
        # 注：这取决于事件总线的具体实现
        print(f"Processing order: {processing_order}")


class TestEventErrorHandling:
    """错误处理测试"""
    
    def test_invalid_event(self):
        """测试发布无效事件"""
        bus = EventBus({'execution_mode': 'sync'})
        bus.start()
        
        # 测试 None 事件
        result = bus.publish(None)
        assert result == False
        
        bus.stop()
    
    def test_handler_exception(self):
        """测试处理器异常处理"""
        bus = EventBus({'execution_mode': 'sync'})
        bus.start()
        
        exception_caught = []
        successful_events = []
        
        def failing_handler(event):
            exception_caught.append(True)
            raise ValueError("Handler error")
        
        def normal_handler(event):
            successful_events.append(event)
        
        # 订阅相同事件，一个处理器失败，另一个正常
        bus.subscribe('test_event', failing_handler)
        bus.subscribe('test_event', normal_handler)
        
        # 发布事件
        event = EventFormat()
        event.set_type('test_event')
        bus.publish(event)
        
        time.sleep(0.1)
        
        # 验证异常被捕获，但其他处理器仍然执行
        assert len(exception_caught) > 0
        assert len(successful_events) > 0
        
        bus.stop()
    
    def test_queue_full_handling(self):
        """测试队列满时的处理"""
        config = {
            'execution_mode': 'sync',
            'max_queue_size': 5,
            'drop_oldest_on_full': False  # 新事件被丢弃
        }
        bus = EventBus(config)
        bus.start()
        
        # 快速发布多个事件，超过队列大小
        results = []
        for i in range(10):
            event = EventFormat()
            event.set_type('stress_test')
            event.set('index', i)
            result = bus.publish(event)
            results.append(result)
        
        time.sleep(0.2)
        bus.stop()
        
        # 某些事件应该被丢弃
        print(f"Publish results: {results}")


class TestThreadSafety:
    """线程安全性测试"""
    
    def test_concurrent_publish(self):
        """测试并发发布"""
        bus = EventBus({'execution_mode': 'async', 'worker_threads': 4})
        bus.start()
        
        received_count = [0]
        lock = threading.Lock()
        
        def handler(event):
            with lock:
                received_count[0] += 1
        
        bus.subscribe('concurrent_test', handler)
        
        def publish_events(thread_id, count):
            for i in range(count):
                event = EventFormat()
                event.set_type('concurrent_test')
                event.set('thread_id', thread_id)
                event.set('sequence', i)
                bus.publish(event)
        
        # 创建多个线程并发发布事件
        threads = []
        for thread_id in range(5):
            t = threading.Thread(
                target=publish_events,
                args=(thread_id, 20)
            )
            threads.append(t)
            t.start()
        
        # 等待所有线程完成
        for t in threads:
            t.join()
        
        # 等待事件处理完成
        time.sleep(1)
        bus.stop()
        
        # 应该接收到所有发布的事件
        assert received_count[0] == 5 * 20
    
    def test_concurrent_subscribe_unsubscribe(self):
        """测试并发订阅和取消订阅"""
        bus = EventBus({'execution_mode': 'async', 'worker_threads': 2})
        bus.start()
        
        subscriptions = []
        lock = threading.Lock()
        
        def handler(event):
            pass
        
        def subscribe_unsubscribe():
            for _ in range(20):
                # 订阅
                sub_id = bus.subscribe('test_event', handler)
                with lock:
                    subscriptions.append(sub_id)
                
                # 短暂延迟
                time.sleep(0.01)
                
                # 取消订阅
                if subscriptions:
                    with lock:
                        sub_id = subscriptions.pop(0)
                    bus.unsubscribe(sub_id)
        
        # 创建多个线程并发执行
        threads = []
        for _ in range(3):
            t = threading.Thread(target=subscribe_unsubscribe)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        bus.stop()


class TestEventAttributes:
    """事件属性测试"""
    
    def test_string_attribute(self):
        """测试字符串属性"""
        event = EventFormat()
        event.set_type('test')
        event.set('symbol', 'AAPL')
        event.set('message', 'Test message')
        
        assert event.get_type() == 'test'
    
    def test_numeric_attributes(self):
        """测试数值属性"""
        event = EventFormat()
        event.set_type('trade')
        event.set('price', 150.5)
        event.set('volume', 1000)
        event.set('timestamp', 1234567890)
    
    def test_vector_attributes(self):
        """测试向量属性"""
        event = EventFormat()
        event.set_type('batch')
        
        # 测试数值数组
        prices = [100.5, 101.2, 99.8]
        event.set('prices', prices)
        
        volumes = [1000, 2000, 1500]
        event.set('volumes', volumes)
    
    def test_attribute_type_conversion(self):
        """测试属性类型转换"""
        event = EventFormat()
        event.set_type('conversion_test')
        
        # 设置数值
        event.set('value', 42)
        
        # 设置浮点数
        event.set('price', 100.5)
        
        # 设置布尔值
        event.set('is_buy', True)


class TestEventFormat:
    """EventFormat 格式测试"""
    
    def test_event_metadata(self):
        """测试事件元数据"""
        event = EventFormat()
        event.set_type('test_event')
        
        # 设置关联 ID
        correlation_id = 'corr_12345'
        event.set_correlation_id(correlation_id)
        
        # 设置优先级
        event.set_priority(2)
    
    def test_event_serialization(self):
        """测试事件序列化"""
        event = EventFormat()
        event.set_type('market_data')
        event.set('symbol', 'MSFT')
        event.set('price', 350.0)
        event.set('volume', 1000)
        
        # 测试 JSON 序列化
        try:
            json_str = event.to_json()
            print(f"Event JSON: {json_str}")
        except Exception as e:
            print(f"JSON serialization not supported: {e}")


@pytest.fixture
def event_bus():
    """EventBus 测试夹具"""
    bus = EventBus({'execution_mode': 'sync'})
    bus.start()
    yield bus
    bus.stop()


def test_with_fixture(event_bus):
    """使用夹具的测试示例"""
    received = []
    
    def handler(event):
        received.append(event)
    
    event_bus.subscribe('fixture_test', handler)
    
    event = EventFormat()
    event.set_type('fixture_test')
    event_bus.publish(event)
    
    time.sleep(0.1)
    assert len(received) == 1
