"""
Event Bus 业务场景集成测试

测试覆盖:
1. 市场数据流处理
2. 订单生命周期
3. 交易执行流程
4. 风险监控场景
5. 策略反馈循环
"""

import pytest
import time
import threading
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any

try:
    from astock_engine import EventBus, EventFormat
except ImportError as e:
    pytest.skip(f"C++ extensions not available: {e}", allow_module_level=True)


class MarketDataSimulator:
    """市场数据模拟器"""
    
    def __init__(self, bus: EventBus):
        self.bus = bus
        self.running = False
    
    def start(self):
        """启动市场数据模拟"""
        self.running = True
        self.thread = threading.Thread(target=self._generate_market_data)
        self.thread.daemon = True
        self.thread.start()
    
    def stop(self):
        """停止市场数据模拟"""
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join(timeout=2)
    
    def _generate_market_data(self):
        """生成市场数据"""
        symbols = ['AAPL', 'MSFT', 'GOOG', 'AMZN']
        prices = {'AAPL': 150.0, 'MSFT': 350.0, 'GOOG': 140.0, 'AMZN': 160.0}
        
        tick = 0
        while self.running and tick < 20:
            for symbol in symbols:
                # 模拟价格波动
                price = prices[symbol] + (tick % 3 - 1) * 0.5
                volume = 1000 + (tick * 100) % 5000
                
                event = EventFormat()
                event.set_type('market_data')
                event.set('symbol', symbol)
                event.set('price', price)
                event.set('volume', volume)
                event.set('timestamp', time.time())
                event.set('bid', price - 0.1)
                event.set('ask', price + 0.1)
                
                self.bus.publish(event, priority=1)  # 高优先级
            
            tick += 1
            time.sleep(0.05)


class OrderManager:
    """订单管理器 - 业务逻辑"""
    
    def __init__(self, bus: EventBus):
        self.bus = bus
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.order_counter = 0
        self._lock = threading.Lock()
        
        # 订阅订单相关事件
        self.bus.subscribe('place_order', self._on_place_order)
        self.bus.subscribe('cancel_order', self._on_cancel_order)
    
    def _on_place_order(self, event):
        """处理下单事件"""
        with self._lock:
            self.order_counter += 1
            order_id = f"ORD_{self.order_counter:06d}"
            
            symbol = event.get('symbol') if hasattr(event, 'get') else 'UNKNOWN'
            price = event.get('price') if hasattr(event, 'get') else 0
            quantity = event.get('quantity') if hasattr(event, 'get') else 0
            side = event.get('side') if hasattr(event, 'get') else 'BUY'
            
            # 创建订单
            order = {
                'order_id': order_id,
                'symbol': symbol,
                'price': price,
                'quantity': quantity,
                'side': side,
                'status': 'PENDING',
                'filled_quantity': 0,
                'created_time': datetime.now(),
                'filled_time': None
            }
            
            self.orders[order_id] = order
            
            # 发布订单已创建事件
            response_event = EventFormat()
            response_event.set_type('order_created')
            response_event.set('order_id', order_id)
            response_event.set('symbol', symbol)
            response_event.set('status', 'PENDING')
            
            self.bus.publish(response_event, priority=2)
    
    def _on_cancel_order(self, event):
        """处理取消订单事件"""
        order_id = event.get('order_id') if hasattr(event, 'get') else None
        
        with self._lock:
            if order_id in self.orders:
                self.orders[order_id]['status'] = 'CANCELLED'
                
                # 发布订单已取消事件
                response_event = EventFormat()
                response_event.set_type('order_cancelled')
                response_event.set('order_id', order_id)
                response_event.set('status', 'CANCELLED')
                
                self.bus.publish(response_event, priority=2)
    
    def fill_order(self, order_id: str, filled_quantity: int):
        """成交订单"""
        with self._lock:
            if order_id in self.orders:
                order = self.orders[order_id]
                order['filled_quantity'] += filled_quantity
                
                if order['filled_quantity'] >= order['quantity']:
                    order['status'] = 'FILLED'
                else:
                    order['status'] = 'PARTIALLY_FILLED'
                
                order['filled_time'] = datetime.now()
                
                # 发布订单成交事件
                trade_event = EventFormat()
                trade_event.set_type('trade')
                trade_event.set('order_id', order_id)
                trade_event.set('symbol', order['symbol'])
                trade_event.set('price', order['price'])
                trade_event.set('quantity', filled_quantity)
                trade_event.set('side', order['side'])
                trade_event.set('timestamp', time.time())
                
                self.bus.publish(trade_event, priority=0)  # 最高优先级
    
    def get_orders(self) -> Dict[str, Dict[str, Any]]:
        """获取所有订单"""
        with self._lock:
            return dict(self.orders)


class StrategyEngine:
    """策略引擎 - 处理市场数据并生成订单"""
    
    def __init__(self, bus: EventBus, order_manager: OrderManager):
        self.bus = bus
        self.order_manager = order_manager
        self.market_data = defaultdict(lambda: {'price': 0, 'volume': 0})
        self.positions = defaultdict(int)
        self.pnl = 0.0
        self.trade_count = 0
        
        # 订阅市场数据事件
        self.bus.subscribe('market_data', self._on_market_data)
        self.bus.subscribe('trade', self._on_trade)
    
    def _on_market_data(self, event):
        """处理市场数据"""
        symbol = event.get('symbol') if hasattr(event, 'get') else None
        price = event.get('price') if hasattr(event, 'get') else 0
        volume = event.get('volume') if hasattr(event, 'get') else 0
        
        if symbol:
            self.market_data[symbol] = {
                'price': price,
                'volume': volume,
                'bid': event.get('bid') if hasattr(event, 'get') else price - 0.1,
                'ask': event.get('ask') if hasattr(event, 'get') else price + 0.1,
                'timestamp': time.time()
            }
            
            # 简单策略：基于价格波动进行交易
            self._execute_strategy(symbol, price, volume)
    
    def _execute_strategy(self, symbol: str, price: float, volume: int):
        """执行策略逻辑"""
        # 简单策略示例：价格低于基准价时买入，高于基准价时卖出
        base_price = {'AAPL': 150.0, 'MSFT': 350.0, 'GOOG': 140.0, 'AMZN': 160.0}
        
        if symbol in base_price:
            current_base = base_price[symbol]
            
            # 低价买入
            if price < current_base - 1.0 and self.positions[symbol] < 100:
                order_event = EventFormat()
                order_event.set_type('place_order')
                order_event.set('symbol', symbol)
                order_event.set('price', price)
                order_event.set('quantity', 10)
                order_event.set('side', 'BUY')
                
                self.bus.publish(order_event, priority=1)
            
            # 高价卖出
            elif price > current_base + 1.0 and self.positions[symbol] > 0:
                order_event = EventFormat()
                order_event.set_type('place_order')
                order_event.set('symbol', symbol)
                order_event.set('price', price)
                order_event.set('quantity', min(10, self.positions[symbol]))
                order_event.set('side', 'SELL')
                
                self.bus.publish(order_event, priority=1)
    
    def _on_trade(self, event):
        """处理成交事件"""
        symbol = event.get('symbol') if hasattr(event, 'get') else None
        quantity = event.get('quantity') if hasattr(event, 'get') else 0
        side = event.get('side') if hasattr(event, 'get') else 'BUY'
        price = event.get('price') if hasattr(event, 'get') else 0
        
        if symbol:
            if side == 'BUY':
                self.positions[symbol] += quantity
                self.pnl -= price * quantity
            else:
                self.positions[symbol] -= quantity
                self.pnl += price * quantity
            
            self.trade_count += 1
    
    def get_state(self) -> Dict[str, Any]:
        """获取策略状态"""
        return {
            'positions': dict(self.positions),
            'pnl': self.pnl,
            'trade_count': self.trade_count,
            'market_data': dict(self.market_data)
        }


class RiskMonitor:
    """风险监控器"""
    
    def __init__(self, bus: EventBus, strategy_engine: StrategyEngine):
        self.bus = bus
        self.strategy_engine = strategy_engine
        self.max_position = 100
        self.max_loss = -10000.0
        self.max_notional = 100000.0
        self.alerts = []
        
        # 订阅相关事件
        self.bus.subscribe('trade', self._check_risk)
        self.bus.subscribe('market_data', self._monitor_market)
    
    def _check_risk(self, event):
        """检查交易风险"""
        order_id = event.get('order_id') if hasattr(event, 'get') else None
        symbol = event.get('symbol') if hasattr(event, 'get') else None
        quantity = event.get('quantity') if hasattr(event, 'get') else 0
        
        state = self.strategy_engine.get_state()
        
        # 检查头寸限制
        if symbol and state['positions'].get(symbol, 0) > self.max_position:
            alert_event = EventFormat()
            alert_event.set_type('risk_alert')
            alert_event.set('level', 'WARNING')
            alert_event.set('message', f'Position limit exceeded for {symbol}')
            alert_event.set('symbol', symbol)
            alert_event.set('position', state['positions'][symbol])
            
            self.bus.publish(alert_event, priority=0)  # 最高优先级
            self.alerts.append(('position_limit', symbol))
        
        # 检查损失限制
        if state['pnl'] < self.max_loss:
            alert_event = EventFormat()
            alert_event.set_type('risk_alert')
            alert_event.set('level', 'CRITICAL')
            alert_event.set('message', 'Loss limit exceeded')
            alert_event.set('pnl', state['pnl'])
            
            self.bus.publish(alert_event, priority=0)
            self.alerts.append(('loss_limit', None))
    
    def _monitor_market(self, event):
        """监控市场数据"""
        # 可以在这里添加市场级别的风险检查
        pass
    
    def get_alerts(self) -> List[tuple]:
        """获取所有风险警报"""
        return self.alerts


class TestMarketDataScenario:
    """市场数据处理场景测试"""
    
    def test_market_data_flow(self):
        """测试市场数据流处理"""
        bus = EventBus({'execution_mode': 'async', 'worker_threads': 4})
        bus.start()
        
        # 启动市场数据模拟
        simulator = MarketDataSimulator(bus)
        simulator.start()
        
        # 创建业务组件
        order_manager = OrderManager(bus)
        strategy_engine = StrategyEngine(bus, order_manager)
        risk_monitor = RiskMonitor(bus, strategy_engine)
        
        # 运行一段时间
        time.sleep(2)
        
        simulator.stop()
        
        # 验证结果
        state = strategy_engine.get_state()
        
        print(f"\n市场数据场景测试结果:")
        print(f"  - 交易数量: {state['trade_count']}")
        print(f"  - 持仓: {state['positions']}")
        print(f"  - P&L: {state['pnl']:.2f}")
        print(f"  - 风险警报: {len(risk_monitor.alerts)}")
        
        assert state['trade_count'] > 0
        assert len(state['positions']) > 0
        
        bus.stop()
    
    def test_order_lifecycle(self):
        """测试订单完整生命周期"""
        bus = EventBus({'execution_mode': 'sync'})
        bus.start()
        
        order_manager = OrderManager(bus)
        
        # 下单
        order_event = EventFormat()
        order_event.set_type('place_order')
        order_event.set('symbol', 'AAPL')
        order_event.set('price', 150.0)
        order_event.set('quantity', 100)
        order_event.set('side', 'BUY')
        
        bus.publish(order_event)
        time.sleep(0.1)
        
        orders = order_manager.get_orders()
        assert len(orders) == 1
        
        order_id = list(orders.keys())[0]
        order = orders[order_id]
        
        # 验证订单状态
        assert order['status'] == 'PENDING'
        assert order['symbol'] == 'AAPL'
        assert order['quantity'] == 100
        assert order['filled_quantity'] == 0
        
        # 成交订单
        order_manager.fill_order(order_id, 50)
        time.sleep(0.1)
        
        orders = order_manager.get_orders()
        order = orders[order_id]
        
        assert order['status'] == 'PARTIALLY_FILLED'
        assert order['filled_quantity'] == 50
        
        # 完全成交
        order_manager.fill_order(order_id, 50)
        time.sleep(0.1)
        
        orders = order_manager.get_orders()
        order = orders[order_id]
        
        assert order['status'] == 'FILLED'
        assert order['filled_quantity'] == 100
        
        bus.stop()


class TestStrategyExecution:
    """策略执行场景测试"""
    
    def test_strategy_with_market_data(self):
        """测试策略对市场数据的响应"""
        bus = EventBus({'execution_mode': 'async', 'worker_threads': 2})
        bus.start()
        
        order_manager = OrderManager(bus)
        strategy_engine = StrategyEngine(bus, order_manager)
        
        # 模拟市场数据
        test_data = [
            ('AAPL', 148.5, 2000),  # 低价买入
            ('AAPL', 150.5, 2000),  # 正常价格
            ('AAPL', 151.5, 2000),  # 高价卖出
            ('MSFT', 348.0, 1000),  # 低价买入
            ('MSFT', 350.0, 1000),  # 正常价格
            ('MSFT', 351.5, 1000),  # 高价卖出
        ]
        
        for symbol, price, volume in test_data:
            event = EventFormat()
            event.set_type('market_data')
            event.set('symbol', symbol)
            event.set('price', price)
            event.set('volume', volume)
            event.set('bid', price - 0.1)
            event.set('ask', price + 0.1)
            
            bus.publish(event)
        
        time.sleep(1)
        
        # 验证策略执行结果
        state = strategy_engine.get_state()
        
        print(f"\n策略执行测试结果:")
        print(f"  - 交易数量: {state['trade_count']}")
        print(f"  - 持仓: {state['positions']}")
        print(f"  - P&L: {state['pnl']:.2f}")
        
        bus.stop()


class TestRiskMonitoring:
    """风险监控场景测试"""
    
    def test_risk_alerts(self):
        """测试风险警报生成"""
        bus = EventBus({'execution_mode': 'sync'})
        bus.start()
        
        order_manager = OrderManager(bus)
        strategy_engine = StrategyEngine(bus, order_manager)
        risk_monitor = RiskMonitor(bus, strategy_engine)
        
        # 降低头寸限制用于测试
        risk_monitor.max_position = 50
        
        # 创建超过头寸限制的交易
        trade_event = EventFormat()
        trade_event.set_type('trade')
        trade_event.set('order_id', 'ORD_001')
        trade_event.set('symbol', 'AAPL')
        trade_event.set('price', 150.0)
        trade_event.set('quantity', 100)
        trade_event.set('side', 'BUY')
        
        # 手动更新头寸以触发风险检查
        strategy_engine.positions['AAPL'] = 100
        strategy_engine.pnl = -5000
        
        bus.publish(trade_event)
        time.sleep(0.1)
        
        # 验证警报
        alerts = risk_monitor.get_alerts()
        print(f"\n风险监控测试结果:")
        print(f"  - 生成的警报数: {len(alerts)}")
        
        bus.stop()


class TestEventOrdering:
    """事件顺序和时序性测试"""
    
    def test_event_sequence(self):
        """测试事件处理顺序"""
        bus = EventBus({'execution_mode': 'sync'})
        bus.start()
        
        sequence = []
        
        def create_handler(name):
            def handler(event):
                sequence.append(name)
            return handler
        
        # 订阅同一事件的多个处理器
        bus.subscribe('order_test', create_handler('handler_1'))
        bus.subscribe('order_test', create_handler('handler_2'))
        bus.subscribe('order_test', create_handler('handler_3'))
        
        # 发布事件
        event = EventFormat()
        event.set_type('order_test')
        bus.publish(event)
        
        time.sleep(0.1)
        
        # 验证所有处理器都执行了
        assert len(sequence) == 3
        assert 'handler_1' in sequence
        assert 'handler_2' in sequence
        assert 'handler_3' in sequence
        
        print(f"\n事件顺序测试:")
        print(f"  - 执行顺序: {sequence}")
        
        bus.stop()


@pytest.fixture
def business_setup():
    """业务场景测试夹具"""
    bus = EventBus({'execution_mode': 'async', 'worker_threads': 2})
    bus.start()
    
    order_manager = OrderManager(bus)
    strategy_engine = StrategyEngine(bus, order_manager)
    risk_monitor = RiskMonitor(bus, strategy_engine)
    
    yield {
        'bus': bus,
        'order_manager': order_manager,
        'strategy_engine': strategy_engine,
        'risk_monitor': risk_monitor
    }
    
    bus.stop()


def test_complete_trading_flow(business_setup):
    """完整的交易流程测试"""
    bus = business_setup['bus']
    order_manager = business_setup['order_manager']
    strategy_engine = business_setup['strategy_engine']
    risk_monitor = business_setup['risk_monitor']
    
    # 模拟一个完整的交易周期
    # 1. 市场数据到达
    market_event = EventFormat()
    market_event.set_type('market_data')
    market_event.set('symbol', 'AAPL')
    market_event.set('price', 148.5)
    market_event.set('volume', 5000)
    bus.publish(market_event)
    
    time.sleep(0.2)
    
    # 2. 策略应该已经下单
    orders = order_manager.get_orders()
    assert len(orders) > 0
    
    # 3. 成交订单
    for order_id, order in orders.items():
        if order['status'] == 'PENDING':
            order_manager.fill_order(order_id, order['quantity'])
    
    time.sleep(0.2)
    
    # 4. 检查最终状态
    state = strategy_engine.get_state()
    
    print(f"\n完整交易流程测试:")
    print(f"  - 订单数: {len(orders)}")
    print(f"  - 交易数: {state['trade_count']}")
    print(f"  - 持仓: {state['positions']}")
    print(f"  - P&L: {state['pnl']:.2f}")
    
    assert state['trade_count'] > 0
