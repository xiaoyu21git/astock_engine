#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试KDJ策略 - 美的集团
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timedelta
from astock_engine.data.data_provider import DataManager
from astock_engine.strategies.plugin_manager import StrategyPluginManager
from astock_engine.backtest.backtest_engine import BacktestEngine, BacktestConfig
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)

print("=" * 70)
print("                   KDJ策略回测 - 美的集团")
print("=" * 70)
print()

# 1. 获取数据
print("📊 获取美的集团历史数据...")
data_manager = DataManager()
symbol = '000333.SZ'

data = data_manager.get_stock_data(
    symbols=[symbol],
    start_date='2024-02-01',
    end_date='2026-01-31'
)

df = data[symbol]
print(f"✅ 获取{len(df)}条数据")
print(f"   时间: {df.index[0].strftime('%Y-%m-%d')} 至 {df.index[-1].strftime('%Y-%m-%d')}")
print(f"   涨幅: {(df['close'].iloc[-1] / df['close'].iloc[0] - 1):.2%}")
print()

# 2. 创建KDJ策略
print("📦 加载KDJ策略...")
plugin_manager = StrategyPluginManager()
plugin_manager.scan_plugins()
kdj_strategy = plugin_manager.create_strategy('kdj_strategy')
print(f"✅ {kdj_strategy.get_description()}")
print()

# 3. 回测
print("⏳ 开始回测...")
config = BacktestConfig(
    initial_capital=1_000_000,
    commission_rate=0.0003,
    slippage_rate=0.001,
    stop_loss=-0.05,
    take_profit=0.20,
    max_position_size=0.30,
    max_positions=10
)

engine = BacktestEngine(config, enable_risk_control=True)
results = engine.run(kdj_strategy, data)

print()
print("=" * 70)
print("                      回测结果")
print("=" * 70)
print(f"总收益率: {results.total_return:>10.2%}")
print(f"年化收益: {results.annual_return:>10.2%}")
print(f"最大回撤: {results.max_drawdown:>10.2%}")
print(f"夏普比率: {results.sharpe_ratio:>10.2f}")
print(f"交易次数: {results.num_trades:>10}笔")
print(f"胜率:     {results.win_rate:>10.2%}")
print(f"盈亏比:   {results.profit_factor:>10.2f}")
print(f"最终资产: ¥{results.final_value:>13,.2f}")
print("=" * 70)
