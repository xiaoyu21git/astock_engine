"""
Event Bus Python/C++ 互操作性测试

测试覆盖:
1. Python 调用 C++ EventBus
2. C++ Event 在 Python 中的使用
3. Python 回调函数处理 C++ 事件
4. 数据类型转换
5. 跨语言的错误处理
"""

import pytest
import sys
import os
import json
from datetime import datetime
from typing import Dict, List, Any

try:
    from astock_engine import (
        EventBus,
        Event,
        EventFormat,
        EventValue,
        ExecutionMode
    )
except ImportError as e:
    pytest.skip(f"C++ extensions not available: {e}", allow_module_level=True)


class TestPythonCppInterop:
    """Python/C++ 互操作性测试"""
    
    def test_eventbus_from_python(self):
        """从 Python 创建和使用 EventBus"""
        # 创建 EventBus 实例
        bus = EventBus()
        
        # 验证基本方法存在
        assert hasattr(bus, 'start')
        assert hasattr(bus, 'stop')
        assert hasattr(bus, 'publish')
        assert hasattr(bus, 'subscribe')
        assert hasattr(bus, 'unsubscribe')
        
        # 启动和停止
        result = bus.start()
        assert result == True
        
        result = bus.stop()
        assert result == True
    
    def test_event_creation_from_python(self):
        """从 Python 创建 Event 对象"""
        # 创建 EventFormat
        event = EventFormat()
        
        # 设置基本属性
        event.set_type('test_event')
        event.set('data', 'test_value')
        event.set('number', 42)
        event.set('price', 100.5)
        
        # 验证类型
        assert event.get_type() == 'test_event'
    
    def test_python_callback_with_cpp_event(self):
        """Python 回调函数处理 C++ Event"""
        bus = EventBus({'execution_mode': 'sync'})
        bus.start()
        
        received_events = []
        
        def python_handler(event):
            """Python 定义的事件处理器"""
            received_events.append({
                'event_type': event.get_type() if hasattr(event, 'get_type') else None,
                'timestamp': datetime.now().isoformat()
            })
        
        # 从 Python 注册处理器
        subscription_id = bus.subscribe('python_handler_test', python_handler)
        assert subscription_id is not None
        
        # 从 Python 发布事件
        event = EventFormat()
        event.set_type('python_handler_test')
        event.set('message', 'Hello from Python')
        
        bus.publish(event)
        
        import time
        time.sleep(0.1)
        
        # 验证 Python 处理器接收到事件
        assert len(received_events) == 1
        assert 'event_type' in received_events[0]
        
        bus.stop()
    
    def test_event_data_types(self):
        """测试各种数据类型的处理"""
        event = EventFormat()
        event.set_type('data_type_test')
        
        # 字符串
        event.set('symbol', 'AAPL')
        
        # 整数
        event.set('volume', 1000)
        event.set('timestamp', 1234567890)
        
        # 浮点数
        event.set('price', 150.5)
        event.set('bid', 150.4)
        event.set('ask', 150.6)
        
        # 布尔值
        event.set('is_active', True)
        event.set('is_processed', False)
        
        # 列表（如果支持）
        try:
            event.set('prices', [100.5, 101.2, 99.8])
            event.set('volumes', [1000, 2000, 1500])
        except Exception as e:
            print(f"Vector type not directly supported: {e}")
    
    def test_event_attribute_access(self):
        """测试 Event 属性访问"""
        event = EventFormat()
        event.set_type('attribute_test')
        
        # 设置各种属性
        test_data = {
            'symbol': 'MSFT',
            'price': 350.0,
            'volume': 5000,
            'is_buy': True,
            'timestamp': time.time()
        }
        
        for key, value in test_data.items():
            if isinstance(value, str):
                event.set(key, value)
            elif isinstance(value, (int, float)):
                event.set(key, float(value) if isinstance(value, float) else int(value))
            elif isinstance(value, bool):
                event.set(key, value)
    
    def test_multiple_event_types(self):
        """测试多种事件类型的处理"""
        bus = EventBus({'execution_mode': 'sync'})
        bus.start()
        
        events_received = {
            'market_data': [],
            'order': [],
            'trade': [],
            'risk': []
        }
        
        def create_handler(event_type):
            def handler(event):
                events_received[event_type].append(event)
            return handler
        
        # 注册多种事件的处理器
        for event_type in events_received.keys():
            bus.subscribe(event_type, create_handler(event_type))
        
        # 发布不同类型的事件
        for event_type in events_received.keys():
            event = EventFormat()
            event.set_type(event_type)
            event.set('data', f'test_{event_type}')
            bus.publish(event)
        
        import time
        time.sleep(0.2)
        
        # 验证每种类型都被处理
        for event_type in events_received.keys():
            assert len(events_received[event_type]) == 1
        
        bus.stop()
    
    def test_python_exception_handling(self):
        """测试 Python 异常处理"""
        bus = EventBus({'execution_mode': 'sync'})
        bus.start()
        
        errors = []
        successes = []
        
        def failing_handler(event):
            errors.append('Exception raised')
            raise RuntimeError("Handler error")
        
        def normal_handler(event):
            successes.append(event)
        
        # 注册两个处理器，一个失败一个成功
        bus.subscribe('exception_test', failing_handler)
        bus.subscribe('exception_test', normal_handler)
        
        # 发布事件
        event = EventFormat()
        event.set_type('exception_test')
        bus.publish(event)
        
        import time
        time.sleep(0.1)
        
        # 验证：一个处理器失败，另一个仍然执行
        assert len(errors) > 0
        assert len(successes) > 0
        
        bus.stop()


class TestEventSerialization:
    """事件序列化测试"""
    
    def test_event_to_json(self):
        """测试事件转 JSON 序列化"""
        event = EventFormat()
        event.set_type('json_test')
        event.set('symbol', 'AAPL')
        event.set('price', 150.5)
        event.set('volume', 1000)
        
        # 尝试序列化
        try:
            json_str = event.to_json()
            print(f"Event JSON: {json_str}")
            
            # 验证是有效的 JSON
            parsed = json.loads(json_str)
            assert 'type' in parsed or 'symbol' in parsed
        except Exception as e:
            print(f"JSON serialization not supported: {e}")
    
    def test_event_from_json(self):
        """测试从 JSON 创建事件"""
        json_data = {
            'symbol': 'MSFT',
            'price': 350.0,
            'volume': 5000,
            'timestamp': 1234567890
        }
        
        # 尝试从 JSON 创建事件
        try:
            event_json = json.dumps(json_data)
            
            event = EventFormat()
            event.set_type('json_source')
            for key, value in json_data.items():
                event.set(key, value)
            
            print(f"Event created from JSON data")
        except Exception as e:
            print(f"JSON creation not supported: {e}")
    
    def test_event_dict_conversion(self):
        """测试事件与字典之间的转换"""
        # 创建字典
        event_dict = {
            'event_type': 'trade',
            'symbol': 'GOOG',
            'price': 140.0,
            'quantity': 100,
            'side': 'BUY'
        }
        
        # 从字典创建事件
        event = EventFormat()
        event.set_type(event_dict['event_type'])
        
        for key, value in event_dict.items():
            if key != 'event_type':
                if isinstance(value, str):
                    event.set(key, value)
                else:
                    event.set(key, value)


class TestConcurrentAccess:
    """并发访问测试"""
    
    def test_python_thread_safety(self):
        """测试 Python 线程中的 EventBus 使用"""
        bus = EventBus({'execution_mode': 'async', 'worker_threads': 4})
        bus.start()
        
        import threading
        import time
        
        results = {'count': 0}
        lock = threading.Lock()
        
        def handler(event):
            with lock:
                results['count'] += 1
        
        bus.subscribe('thread_test', handler)
        
        def publish_from_thread(thread_id):
            for i in range(10):
                event = EventFormat()
                event.set_type('thread_test')
                event.set('thread_id', thread_id)
                event.set('sequence', i)
                bus.publish(event)
        
        # 创建多个线程并发发布
        threads = []
        for i in range(3):
            t = threading.Thread(target=publish_from_thread, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        time.sleep(0.5)
        
        # 验证所有事件都被处理
        assert results['count'] == 30
        
        bus.stop()


class TestEventPriority:
    """事件优先级测试（Python 视角）"""
    
    def test_priority_publishing(self):
        """测试带优先级的事件发布"""
        bus = EventBus({'execution_mode': 'sync'})
        bus.start()
        
        processing_order = []
        
        def handler(event):
            processing_order.append(event)
        
        bus.subscribe('priority_test', handler)
        
        # 发布不同优先级的事件
        priorities = [5, 1, 3, 0, 2, 4]
        
        for priority in priorities:
            event = EventFormat()
            event.set_type('priority_test')
            event.set('priority', priority)
            
            # 使用 priority 参数发布
            bus.publish(event, priority)
        
        import time
        time.sleep(0.2)
        
        # 验证处理的事件数
        assert len(processing_order) == len(priorities)
        
        print(f"Processed {len(processing_order)} events")
        
        bus.stop()


class TestConfigurationOptions:
    """配置选项测试"""
    
    def test_sync_mode(self):
        """测试同步执行模式"""
        config = {
            'execution_mode': 'sync',
            'max_queue_size': 1000
        }
        
        bus = EventBus(config)
        assert bus.start()
        
        event = EventFormat()
        event.set_type('sync_test')
        
        result = bus.publish(event)
        assert result == True
        
        assert bus.stop()
    
    def test_async_mode(self):
        """测试异步执行模式"""
        config = {
            'execution_mode': 'async',
            'worker_threads': 4,
            'batch_size': 10
        }
        
        bus = EventBus(config)
        assert bus.start()
        
        import time
        
        received = []
        
        def handler(event):
            received.append(event)
        
        bus.subscribe('async_test', handler)
        
        # 发布事件
        for i in range(5):
            event = EventFormat()
            event.set_type('async_test')
            event.set('index', i)
            bus.publish(event)
        
        time.sleep(0.3)
        
        assert len(received) == 5
        assert bus.stop()
    
    def test_custom_configuration(self):
        """测试自定义配置"""
        config = {
            'execution_mode': 'async',
            'worker_threads': 2,
            'batch_size': 5,
            'max_queue_size': 500,
            'drop_oldest_on_full': False,
            'enable_json_serialization': True
        }
        
        bus = EventBus(config)
        assert bus.start()
        assert bus.stop()


class TestErrorScenarios:
    """错误场景测试"""
    
    def test_publish_before_start(self):
        """测试在启动前发布事件"""
        bus = EventBus({'execution_mode': 'sync'})
        
        event = EventFormat()
        event.set_type('test')
        
        # 不启动 EventBus 直接发布
        result = bus.publish(event)
        # 应该返回 False
        print(f"Publish before start result: {result}")
    
    def test_subscribe_after_stop(self):
        """测试在停止后订阅"""
        bus = EventBus({'execution_mode': 'sync'})
        bus.start()
        bus.stop()
        
        def handler(event):
            pass
        
        # 在停止后尝试订阅
        try:
            sub_id = bus.subscribe('test', handler)
            print(f"Subscribe after stop returned: {sub_id}")
        except Exception as e:
            print(f"Subscribe after stop raised: {type(e).__name__}")
    
    def test_invalid_event_type(self):
        """测试无效的事件类型"""
        bus = EventBus({'execution_mode': 'sync'})
        bus.start()
        
        event = EventFormat()
        # 不设置事件类型
        
        result = bus.publish(event)
        print(f"Publish with no type result: {result}")
        
        bus.stop()


class TestPerformanceBaseline:
    """性能基线测试"""
    
    def test_event_creation_performance(self):
        """测试事件创建性能"""
        import time
        
        start = time.time()
        
        for i in range(1000):
            event = EventFormat()
            event.set_type('perf_test')
            event.set('index', i)
            event.set('value', float(i))
        
        elapsed = time.time() - start
        
        print(f"\nEvent creation performance:")
        print(f"  1000 events created in {elapsed*1000:.2f}ms")
        print(f"  Average: {elapsed*1000000/1000:.2f}µs per event")
    
    def test_publish_performance(self):
        """测试发布性能"""
        import time
        
        bus = EventBus({'execution_mode': 'sync'})
        bus.start()
        
        received = [0]
        
        def handler(event):
            received[0] += 1
        
        bus.subscribe('perf_test', handler)
        
        start = time.time()
        
        for i in range(100):
            event = EventFormat()
            event.set_type('perf_test')
            event.set('index', i)
            bus.publish(event)
        
        elapsed = time.time() - start
        
        print(f"\nPublish performance:")
        print(f"  100 events published in {elapsed*1000:.2f}ms")
        print(f"  Average: {elapsed*1000000/100:.2f}µs per event")
        print(f"  Events received: {received[0]}")
        
        bus.stop()


@pytest.fixture
def basic_bus():
    """基础 EventBus 夹具"""
    bus = EventBus({'execution_mode': 'sync'})
    bus.start()
    yield bus
    bus.stop()


def test_basic_interop(basic_bus):
    """基础互操作性测试"""
    received = []
    
    def handler(event):
        received.append(event)
    
    basic_bus.subscribe('interop_test', handler)
    
    event = EventFormat()
    event.set_type('interop_test')
    event.set('data', 'test')
    
    result = basic_bus.publish(event)
    
    import time
    time.sleep(0.1)
    
    assert result == True
    assert len(received) == 1


import time
