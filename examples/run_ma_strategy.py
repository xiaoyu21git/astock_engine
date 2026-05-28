"""
双均线策略运行示例
演示如何使用EventBus运行策略
"""
import sys
import os
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from astock_engine.core import EventBus, EventType, Event, get_global_bus
from astock_engine.strategies.ma_crossover_strategy import MovingAverageCrossoverStrategy
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class MockMarketDataProvider:
    """模拟市场数据提供者"""
    
    def __init__(self, bus: EventBus, symbols: list):
        self.bus = bus
        self.symbols = symbols
        self.current_idx = 0
        self.data = self._generate_mock_data()
    
    def _generate_mock_data(self) -> pd.DataFrame:
        """生成模拟数据"""
        # 生成100天的数据
        dates = pd.date_range(end=datetime.now(), periods=100, freq='D')
        
        data_list = []
        for symbol in self.symbols:
            # 生成随机价格走势
            base_price = np.random.uniform(10, 50)
            trend = np.random.choice([-0.5, 0, 0.5])  # 上升、震荡、下降
            
            prices = [base_price]
            for i in range(1, 100):
                change = np.random.normal(trend, 1.5)
                new_price = prices[-1] * (1 + change / 100)
                new_price = max(new_price, base_price * 0.5)  # 防止跌太多
                prices.append(new_price)
            
            for date, price in zip(dates, prices):
                data_list.append({
                    'date': date,
                    'symbol': symbol,
                    'close': price,
                    'volume': np.random.randint(1000000, 10000000)
                })
        
        df = pd.DataFrame(data_list)
        logger.info(f"生成模拟数据: {len(df)} 条记录")
        return df
    
    def start(self):
        """开始推送数据"""
        logger.info("开始推送市场数据...")
        
        dates = sorted(self.data['date'].unique())
        
        for i, date in enumerate(dates):
            # 获取当日数据
            daily_data = self.data[self.data['date'] == date]
            
            logger.info(f"\n{'='*60}")
            logger.info(f"日期: {date.strftime('%Y-%m-%d')} ({i+1}/{len(dates)})")
            logger.info(f"{'='*60}")
            
            # 推送每只股票的数据
            for _, row in daily_data.iterrows():
                event = Event(
                    type=EventType.MARKET_DATA,
                    data={
                        'symbol': row['symbol'],
                        'close': row['close'],
                        'volume': row['volume'],
                        'timestamp': row['date']
                    },
                    timestamp=row['date']
                )
                self.bus.publish(event)
            
            # 模拟实时推送延迟
            time.sleep(0.1)
        
        logger.info("\n数据推送完成")


class MockOrderExecutor:
    """模拟订单执行器"""
    
    def __init__(self, bus: EventBus):
        self.bus = bus
        self.bus.subscribe(EventType.SIGNAL, self.on_signal)
        logger.info("订单执行器已启动")
    
    def on_signal(self, event: Event):
        """处理交易信号"""
        data = event.data
        symbol = data['symbol']
        direction = data['direction']
        price = data['price']
        
        # 模拟订单执行
        action = 'BUY' if direction == 1 else 'SELL'
        quantity = 1000 if direction == 1 else 1000  # 简化：固定数量
        
        logger.info(f"📋 执行订单: {action} {symbol} @ {price:.2f}, 数量={quantity}")
        
        # 模拟成交延迟
        time.sleep(0.05)
        
        # 发布订单响应事件
        response_event = Event(
            type=EventType.ORDER_RESPONSE,
            data={
                'symbol': symbol,
                'action': action,
                'status': 'FILLED',
                'quantity': quantity,
                'price': price,
                'timestamp': datetime.now()
            }
        )
        self.bus.publish(response_event)


def main():
    """主函数"""
    print("\n" + "="*80)
    print("双均线交叉策略回测示例")
    print("="*80 + "\n")
    
    # 1. 创建EventBus
    logger.info("1️⃣  初始化EventBus...")
    bus = get_global_bus()
    
    # 2. 创建策略
    logger.info("2️⃣  创建策略...")
    strategy_params = {
        'initial_capital': 1000000,  # 100万初始资金
        'short_window': 5,  # 短期均线5日
        'long_window': 20,  # 长期均线20日
        'positionSize': 0.3,  # 每次交易30%仓位
        'max_positions': 3,  # 最多持有3只股票
        'commission_rate': 0.0003  # 万3手续费
    }
    strategy = MovingAverageCrossoverStrategy(params=strategy_params)
    strategy.initialize(bus)
    
    # 3. 创建订单执行器
    logger.info("3️⃣  创建订单执行器...")
    executor = MockOrderExecutor(bus)
    
    # 4. 创建数据提供者
    logger.info("4️⃣  创建数据提供者...")
    symbols = ['000001.SZ', '600000.SH', '000002.SZ']
    data_provider = MockMarketDataProvider(bus, symbols)
    
    # 5. 运行回测
    logger.info("\n5️⃣  开始回测...\n")
    start_time = time.time()
    
    try:
        data_provider.start()
    except KeyboardInterrupt:
        logger.info("\n用户中断")
    
    elapsed = time.time() - start_time
    
    # 6. 输出结果
    print("\n" + "="*80)
    print("回测结果")
    print("="*80)
    
    summary = strategy.get_positions_summary()
    
    print(f"\n初始资金: ¥{strategy.initial_capital:,.2f}")
    print(f"剩余现金: ¥{summary['cash']:,.2f}")
    print(f"持仓市值: ¥{sum(p['current_price'] * p['quantity'] for p in summary['positions']):,.2f}")
    print(f"总资产:   ¥{summary['total_value']:,.2f}")
    
    pnl = summary['total_value'] - strategy.initial_capital
    pnl_pct = pnl / strategy.initial_capital
    print(f"\n盈亏:     ¥{pnl:,.2f} ({pnl_pct:+.2%})")
    
    print(f"\n持仓数量: {len(summary['positions'])}")
    if summary['positions']:
        print("\n持仓明细:")
        print(f"{'股票':<12} {'数量':>8} {'成本':>10} {'现价':>10} {'盈亏':>12} {'盈亏率':>10}")
        print("-" * 80)
        for pos in summary['positions']:
            print(f"{pos['symbol']:<12} {pos['quantity']:>8} "
                  f"{pos['entry_price']:>10.2f} {pos['current_price']:>10.2f} "
                  f"{pos['pnl']:>12.2f} {pos['pnl_pct']:>9.2%}")
    
    print(f"\n耗时: {elapsed:.2f}秒")
    print("="*80 + "\n")
    
    # 7. 清理
    strategy.shutdown()


if __name__ == "__main__":
    main()
