"""
掘金数据源 - 与C++ EventBus集成
从掘金API获取实时数据并通过EventBus传递
"""

import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Callable
import threading

logger = logging.getLogger(__name__)


class JuejinDataSource:
    """掘金数据源 - 集成C++ EventBus"""
    
    def __init__(self, event_bus=None):
        """
        初始化掘金数据源
        
        Args:
            event_bus: EventBus实例（可选）
        """
        self.event_bus = event_bus
        self.config = None
        self.running = False
        self.thread = None
        
        # 掘金API实例（需要C++模块）
        self.juejin_api = None
        
        # 订阅管理
        self.subscriptions = {}  # symbol -> callback list
        self.symbols = []
        
        # 配置等待
        self.config_received = False
        self.config_cv = threading.Condition()
        
        logger.info("掘金数据源初始化")
    
    def initialize(self) -> bool:
        """
        初始化数据源
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            # 导入C++ EventBus模块
            from astock_engine.core.eventbus_simple import EventBus
            
            # 创建EventBus实例
            self.event_bus = EventBus()
            logger.info("EventBus初始化成功")
            
            # 这里应该初始化掘金C++ API
            # 由于掘金C++ SDK需要实际集成，这里先使用模拟模式
            logger.info("掘金API初始化（模拟模式）")
            
            # 启动事件处理线程
            self.running = True
            self.thread = threading.Thread(target=self._event_loop, daemon=True)
            self.thread.start()
            
            logger.info("掘金数据源初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"数据源初始化失败: {e}")
            return False
    
    def connect(self) -> bool:
        """
        连接到掘金平台
        
        Returns:
            bool: 连接是否成功
        """
        try:
            # 这里应该调用掘金C++ API的connect方法
            # 由于是模拟模式，直接返回成功
            logger.info("连接到掘金平台（模拟模式）")
            
            # 发布连接成功事件
            if self.event_bus:
                # 确保config不为None
                account_id = ''
                if self.config:
                    account_id = self.config.get('juejin', {}).get('account_id', '')
                
                self.event_bus.publish('juejin.connected', {
                    'timestamp': datetime.now().isoformat(),
                    'platform': '掘金量化',
                    'account_id': account_id
                })
            
            return True
            
        except Exception as e:
            logger.error(f"连接掘金平台失败: {e}")
            return False
    
    def subscribe_market_data(self, symbols: List[str], callback: Optional[Callable] = None) -> bool:
        """
        订阅市场数据
        
        Args:
            symbols: 股票代码列表
            callback: 数据回调函数（可选）
            
        Returns:
            bool: 订阅是否成功
        """
        try:
            for symbol in symbols:
                if symbol not in self.subscriptions:
                    self.subscriptions[symbol] = []
                
                if callback and callback not in self.subscriptions[symbol]:
                    self.subscriptions[symbol].append(callback)
                
                # 添加到订阅列表
                if symbol not in self.symbols:
                    self.symbols.append(symbol)
                
                logger.info(f"订阅市场数据: {symbol}")
                
                # 发布订阅事件
                if self.event_bus:
                    self.event_bus.publish('juejin.subscribed', {
                        'symbol': symbol,
                        'timestamp': datetime.now().isoformat()
                    })
            
            return True
            
        except Exception as e:
            logger.error(f"订阅市场数据失败: {e}")
            return False
    
    def unsubscribe_market_data(self, symbols: List[str]) -> bool:
        """
        取消订阅市场数据
        
        Args:
            symbols: 股票代码列表
            
        Returns:
            bool: 取消订阅是否成功
        """
        try:
            for symbol in symbols:
                if symbol in self.subscriptions:
                    del self.subscriptions[symbol]
                
                if symbol in self.symbols:
                    self.symbols.remove(symbol)
                
                logger.info(f"取消订阅市场数据: {symbol}")
                
                # 发布取消订阅事件
                if self.event_bus:
                    self.event_bus.publish('juejin.unsubscribed', {
                        'symbol': symbol,
                        'timestamp': datetime.now().isoformat()
                    })
            
            return True
            
        except Exception as e:
            logger.error(f"取消订阅市场数据失败: {e}")
            return False
    
    def get_historical_data(self, symbol: str, 
                           start_date: str, 
                           end_date: str) -> List[Dict]:
        """
        获取历史数据（模拟）
        
        Args:
            symbol: 股票代码
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            
        Returns:
            List[Dict]: 历史数据列表
        """
        try:
            # 模拟历史数据
            import random
            from datetime import datetime, timedelta
            
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            
            data = []
            current = start
            base_price = 10.0
            
            while current <= end:
                # 生成模拟数据
                change = random.uniform(-0.05, 0.05)
                price = base_price * (1 + change)
                base_price = price
                
                data_point = {
                    'symbol': symbol,
                    'date': current.strftime('%Y-%m-%d'),
                    'open': round(price * (1 + random.uniform(-0.02, 0.02)), 2),
                    'high': round(price * (1 + random.uniform(0, 0.03)), 2),
                    'low': round(price * (1 - random.uniform(0, 0.03)), 2),
                    'close': round(price, 2),
                    'volume': random.randint(10000, 100000),
                    'timestamp': current.isoformat()
                }
                
                data.append(data_point)
                current += timedelta(days=1)
            
            logger.info(f"获取历史数据: {symbol}, {len(data)}条")
            
            # 发布历史数据事件
            if self.event_bus and data:
                self.event_bus.publish('juejin.historical_data', {
                    'symbol': symbol,
                    'count': len(data),
                    'start_date': start_date,
                    'end_date': end_date,
                    'data': data[:5]  # 只发送前5条作为示例
                })
            
            return data
            
        except Exception as e:
            logger.error(f"获取历史数据失败: {e}")
            return []
    
    def start_real_time(self) -> bool:
        """
        启动实时数据流
        
        Returns:
            bool: 启动是否成功
        """
        try:
            if not self.symbols:
                logger.warning("没有订阅的股票，无法启动实时数据")
                return False
            
            logger.info(f"启动实时数据流: {len(self.symbols)}只股票")
            
            # 发布启动事件
            if self.event_bus:
                self.event_bus.publish('juejin.realtime_started', {
                    'timestamp': datetime.now().isoformat(),
                    'symbol_count': len(self.symbols),
                    'symbols': self.symbols
                })
            
            return True
            
        except Exception as e:
            logger.error(f"启动实时数据流失败: {e}")
            return False
    
    def stop_real_time(self) -> bool:
        """
        停止实时数据流
        
        Returns:
            bool: 停止是否成功
        """
        try:
            logger.info("停止实时数据流")
            
            # 发布停止事件
            if self.event_bus:
                self.event_bus.publish('juejin.realtime_stopped', {
                    'timestamp': datetime.now().isoformat()
                })
            
            return True
            
        except Exception as e:
            logger.error(f"停止实时数据流失败: {e}")
            return False
    
    def shutdown(self):
        """关闭数据源"""
        try:
            self.running = False
            
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=2.0)
            
            # 发布关闭事件
            if self.event_bus:
                self.event_bus.publish('juejin.shutdown', {
                    'timestamp': datetime.now().isoformat()
                })
            
            logger.info("掘金数据源已关闭")
            
        except Exception as e:
            logger.error(f"关闭数据源失败: {e}")
    
    def _event_loop(self):
        """事件处理循环（模拟实时数据）"""
        import random
        
        logger.info("事件处理循环启动")
        
        while self.running:
            try:
                if self.symbols and self.event_bus:
                    # 模拟实时数据
                    for symbol in self.symbols:
                        # 生成模拟tick数据
                        tick_data = {
                            'symbol': symbol,
                            'price': round(10.0 * (1 + random.uniform(-0.05, 0.05)), 2),
                            'volume': random.randint(100, 10000),
                            'timestamp': datetime.now().isoformat(),
                            'bid_price': round(10.0 * (1 + random.uniform(-0.06, -0.04)), 2),
                            'ask_price': round(10.0 * (1 + random.uniform(0.04, 0.06)), 2),
                            'bid_volume': random.randint(100, 5000),
                            'ask_volume': random.randint(100, 5000)
                        }
                        
                        # 发布tick事件
                        self.event_bus.publish('market.tick', tick_data)
                        
                        # 调用回调函数
                        if symbol in self.subscriptions:
                            for callback in self.subscriptions[symbol]:
                                try:
                                    callback(tick_data)
                                except Exception as e:
                                    logger.error(f"回调函数执行失败: {e}")
                
                # 休眠一段时间
                time.sleep(1.0)  # 1秒更新一次
                
            except Exception as e:
                logger.error(f"事件处理循环错误: {e}")
                time.sleep(5.0)
        
        logger.info("事件处理循环停止")
    
    def get_status(self) -> Dict:
        """获取数据源状态"""
        config_info = {
            'platform': '掘金量化',
            'token': '',
            'account_id': ''
        }
        
        if self.config:
            config_info['token'] = self.config.get('juejin', {}).get('token', '')[:10] + '...'
            config_info['account_id'] = self.config.get('juejin', {}).get('account_id', '')[:10] + '...'
        
        return {
            'running': self.running,
            'connected': bool(self.event_bus),
            'subscription_count': len(self.symbols),
            'symbols': self.symbols,
            'config': config_info
        }


# 便捷函数
def create_juejin_data_source(config_path: str = "bin/config/config.json") -> JuejinDataSource:
    """
    创建掘金数据源实例
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        JuejinDataSource: 数据源实例
    """
    return JuejinDataSource(config_path)


def test_juejin_data_source():
    """测试掘金数据源"""
    print("=" * 60)
    print("🔧 测试掘金数据源")
    print("=" * 60)
    
    try:
        # 创建数据源
        data_source = create_juejin_data_source()
        
        # 初始化
        if not data_source.initialize():
            print("❌ 数据源初始化失败")
            return False
        
        print("✅ 数据源初始化成功")
        
        # 连接
        if not data_source.connect():
            print("❌ 连接掘金平台失败")
            return False
        
        print("✅ 连接到掘金平台")
        
        # 订阅数据
        symbols = ['600000.SH', '000001.SZ', '000002.SZ']
        if not data_source.subscribe_market_data(symbols):
            print("❌ 订阅市场数据失败")
            return False
        
        print(f"✅ 订阅市场数据: {symbols}")
        
        # 获取历史数据
        historical_data = data_source.get_historical_data(
            '600000.SH', 
            '2024-01-01', 
            '2024-01-10'
        )
        
        if historical_data:
            print(f"✅ 获取历史数据: {len(historical_data)}条")
        else:
            print("❌ 获取历史数据失败")
        
        # 启动实时数据
        if not data_source.start_real_time():
            print("❌ 启动实时数据失败")
            return False
        
        print("✅ 启动实时数据流")
        
        # 显示状态
        status = data_source.get_status()
        print(f"📊 数据源状态:")
        print(f"   运行状态: {'运行中' if status['running'] else '已停止'}")
        print(f"   连接状态: {'已连接' if status['connected'] else '未连接'}")
        print(f"   订阅数量: {status['subscription_count']}")
        print(f"   订阅标的: {status['symbols']}")
        
        # 等待一段时间接收数据
        print("\n📡 等待接收实时数据（5秒）...")
        
        # 定义回调函数
        def data_callback(data):
            print(f"   📨 收到数据: {data['symbol']} - 价格: {data['price']}")
        
        # 添加回调
        data_source.subscribe_market_data(['600000.SH'], data_callback)
        
        time.sleep(5)
        
        # 停止实时数据
        data_source.stop_real_time()
        print("✅ 停止实时数据流")
        
        # 关闭数据源
        data_source.shutdown()
        print("✅ 数据源已关闭")
        
        print("\n" + "=" * 60)
        print("🎉 掘金数据源测试完成")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


if __name__ == "__main__":
    # 运行测试
    test_juejin_data_source()