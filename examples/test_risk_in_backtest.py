"""
测试风控在回测中的止损止盈功能
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

from astock_engine.strategies.plugin_manager import StrategyPluginManager
from astock_engine.backtest.backtest_engine import BacktestEngine, BacktestConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)


def generate_volatile_data(days=300, symbols=['600519.SH', '000858.SZ']):
    """生成高波动数据（测试止损止盈）"""
    np.random.seed(42)
    
    data = {}
    start_date = datetime.now() - timedelta(days=days)
    dates = pd.date_range(start=start_date, periods=days, freq='D')
    
    for i, symbol in enumerate(symbols):
        base_price = 50 + i * 10
        
        # 600519: 先涨20%后跌10%（测试止盈）
        # 000858: 先跌10%（测试止损）
        if i == 0:
            # 涨势股
            trend = np.concatenate([
                np.linspace(0, base_price * 0.25, 150),  # 前半年涨25%
                np.linspace(base_price * 0.25, base_price * 0.15, 150)  # 后半年回调
            ])
        else:
            # 跌势股
            trend = np.concatenate([
                np.linspace(0, -base_price * 0.15, 150),  # 前半年跌15%
                np.linspace(-base_price * 0.15, -base_price * 0.10, 150)  # 后半年小幅反弹
            ])
        
        # 随机波动
        noise = np.random.normal(0, base_price * 0.01, days)
        
        prices = base_price + trend + noise
        prices = np.maximum(prices, base_price * 0.5)
        
        df = pd.DataFrame({
            'symbol': symbol,
            'open': prices * (1 + np.random.uniform(-0.01, 0.01, days)),
            'high': prices * (1 + np.random.uniform(0, 0.02, days)),
            'low': prices * (1 - np.random.uniform(0, 0.02, days)),
            'close': prices,
            'volume': np.random.randint(1000000, 10000000, days)
        }, index=dates)
        
        data[symbol] = df
    
    return data


def main():
    print("\n" + "="*60)
    print("风控止损止盈功能测试".center(60))
    print("="*60 + "\n")
    
    # 1. 生成波动数据
    print("📊 生成高波动行情数据...")
    data = generate_volatile_data(days=300)
    print(f"✅ 生成数据完成: {len(data)}只股票, {len(list(data.values())[0])}个交易日")
    print(f"   600519.SH: 先涨后跌（测试止盈）")
    print(f"   000858.SZ: 持续下跌（测试止损）")
    
    # 2. 加载RSI策略（容易触发信号）
    print("\n📦 加载RSI策略...")
    manager = StrategyPluginManager()
    manager.scan_plugins()
    
    strategy = manager.create_strategy('rsi_strategy')
    print(f"✅ 策略加载成功")
    
    # 3. 对比测试：有风控 vs 无风控
    print("\n" + "="*60)
    print("测试1: 无风控回测（基准）".center(60))
    print("="*60 + "\n")
    
    config_no_risk = BacktestConfig(
        initial_capital=1_000_000,
        commission_rate=0.0003,
        slippage_rate=0.0005
    )
    engine_no_risk = BacktestEngine(config=config_no_risk, enable_risk_control=False)
    
    results_no_risk = engine_no_risk.run(strategy, data)
    
    print(f"\n📊 无风控结果:")
    print(f"   总收益率: {results_no_risk.total_return:.2%}")
    print(f"   最大回撤: {results_no_risk.max_drawdown:.2%}")
    print(f"   夏普比率: {results_no_risk.sharpe_ratio:.2f}")
    print(f"   交易次数: {results_no_risk.num_trades}笔")
    print(f"   最终资产: ¥{results_no_risk.final_value:,.2f}")
    
    # 4. 开启风控
    print("\n" + "="*60)
    print("测试2: 开启风控回测（止损-5%, 止盈+20%）".center(60))
    print("="*60 + "\n")
    
    config_with_risk = BacktestConfig(
        initial_capital=1_000_000,
        commission_rate=0.0003,
        slippage_rate=0.0005,
        stop_loss=-0.05,  # 止损-5%
        take_profit=0.20  # 止盈+20%
    )
    engine_with_risk = BacktestEngine(config=config_with_risk, enable_risk_control=True)
    
    # 重新创建策略实例（避免状态污染）
    strategy = manager.create_strategy('rsi_strategy')
    results_with_risk = engine_with_risk.run(strategy, data)
    
    print(f"\n📊 开启风控结果:")
    print(f"   总收益率: {results_with_risk.total_return:.2%}")
    print(f"   最大回撤: {results_with_risk.max_drawdown:.2%}")
    print(f"   夏普比率: {results_with_risk.sharpe_ratio:.2f}")
    print(f"   交易次数: {results_with_risk.num_trades}笔")
    print(f"   最终资产: ¥{results_with_risk.final_value:,.2f}")
    
    # 5. 对比分析
    print("\n" + "="*60)
    print("对比分析".center(60))
    print("="*60 + "\n")
    
    print(f"📈 收益对比:")
    print(f"   无风控: {results_no_risk.total_return:.2%}")
    print(f"   有风控: {results_with_risk.total_return:.2%}")
    diff_return = results_with_risk.total_return - results_no_risk.total_return
    print(f"   差异: {diff_return:+.2%} {'✅ 风控提升' if diff_return > 0 else '⚠️ 风控降低'}")
    
    print(f"\n📉 回撤对比:")
    print(f"   无风控: {results_no_risk.max_drawdown:.2%}")
    print(f"   有风控: {results_with_risk.max_drawdown:.2%}")
    diff_dd = results_with_risk.max_drawdown - results_no_risk.max_drawdown
    print(f"   差异: {diff_dd:+.2%} {'✅ 风控降低回撤' if diff_dd > 0 else '⚠️ 回撤增加'}")
    
    print(f"\n📊 夏普比率对比:")
    print(f"   无风控: {results_no_risk.sharpe_ratio:.2f}")
    print(f"   有风控: {results_with_risk.sharpe_ratio:.2f}")
    diff_sharpe = results_with_risk.sharpe_ratio - results_no_risk.sharpe_ratio
    print(f"   差异: {diff_sharpe:+.2f} {'✅ 风控提升' if diff_sharpe > 0 else '⚠️ 风控降低'}")
    
    print(f"\n🔄 交易次数对比:")
    print(f"   无风控: {results_no_risk.num_trades}笔")
    print(f"   有风控: {results_with_risk.num_trades}笔")
    print(f"   差异: {results_with_risk.num_trades - results_no_risk.num_trades:+d}笔")
    
    # 6. 查看风控触发记录
    print(f"\n📋 风控触发记录（前10笔）:")
    risk_trades = [t for t in engine_with_risk.trades if '风控' in str(t)]
    if risk_trades:
        for i, trade in enumerate(risk_trades[:10], 1):
            print(f"   {i}. {trade.timestamp.strftime('%Y-%m-%d')}: "
                  f"{trade.action} {trade.symbol} @ {trade.price:.2f}, "
                  f"盈亏={trade.pnl:+,.2f}")
    else:
        print("   未触发风控平仓")
    
    print("\n" + "="*60 + "\n")


if __name__ == '__main__':
    main()
