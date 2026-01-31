#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
KDJ策略参数优化 - 宁德时代专用
基于多股票测试的发现，针对宁德时代优化参数
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from astock_engine.data.data_provider import DataManager
from astock_engine.strategies.plugin_manager import StrategyPluginManager
from astock_engine.backtest.backtest_engine import BacktestEngine, BacktestConfig
import pandas as pd
import logging

logging.basicConfig(level=logging.WARNING)

print("=" * 70)
print("         KDJ策略参数优化 - 宁德时代（当前最佳股票）")
print("=" * 70)
print()

# 1. 加载宁德时代数据
print("📊 加载宁德时代数据...")
data_manager = DataManager()
symbol = '300750.SZ'
data = data_manager.get_stock_data(
    symbols=[symbol],
    start_date='2024-02-01',
    end_date='2026-01-31'
)
print(f"✅ 数据加载完成: {len(data[symbol])}条")
buy_hold = (data[symbol]['close'].iloc[-1] / data[symbol]['close'].iloc[0] - 1)
print(f"   买入持有收益: {buy_hold:.2%}")
print()

# 2. 参数网格
param_grid = {
    'oversold': [15, 20, 25, 30],           # 超卖阈值
    'stop_loss': [0.03, 0.05, 0.07, 0.10],  # 止损
    'signal_threshold': [45, 50, 55, 60],   # 信号质量阈值
}

print("🔍 参数空间:")
print(f"   超卖阈值: {param_grid['oversold']}")
print(f"   止损比例: {[f'{x:.0%}' for x in param_grid['stop_loss']]}")
print(f"   信号阈值: {param_grid['signal_threshold']}分")
total = len(param_grid['oversold']) * len(param_grid['stop_loss']) * len(param_grid['signal_threshold'])
print(f"   总组合数: {total}")
print()

# 3. 网格搜索
plugin_manager = StrategyPluginManager()
plugin_manager.scan_plugins()

results = []
current = 0

print("⏳ 开始优化...")
for oversold in param_grid['oversold']:
    for stop_loss in param_grid['stop_loss']:
        for signal_threshold in param_grid['signal_threshold']:
            current += 1
            
            strategy = plugin_manager.create_strategy('kdj_strategy', params={
                'oversold': oversold,
                'signal_threshold': signal_threshold,
            })
            
            config = BacktestConfig(
                initial_capital=1_000_000,
                commission_rate=0.0003,
                slippage_rate=0.001,
                stop_loss=-stop_loss,
                take_profit=0.20,
                max_position_size=0.30,
                max_positions=10
            )
            
            engine = BacktestEngine(config, enable_risk_control=True)
            result = engine.run(strategy, data)
            
            results.append({
                '超卖阈值': oversold,
                '止损': f'{stop_loss:.0%}',
                '信号阈值': signal_threshold,
                '总收益': result.total_return,
                '超额收益': result.total_return - buy_hold,
                '夏普': result.sharpe_ratio,
                '回撤': result.max_drawdown,
                '交易': result.num_trades,
                '胜率': result.win_rate,
            })
            
            if current % 8 == 0 or current == total:
                print(f"进度: {current}/{total} ({current/total:.0%})")

print()
print("=" * 70)
print("                优化结果（Top 10）")
print("=" * 70)

df = pd.DataFrame(results)
df = df.sort_values('总收益', ascending=False)

print("\n🏆 按总收益排序:")
print(df.head(10).to_string(index=False))

print("\n" + "=" * 70)
print("📊 最优参数:")
best = df.iloc[0]
print(f"   超卖阈值: {best['超卖阈值']}")
print(f"   止损比例: {best['止损']}")
print(f"   信号阈值: {best['信号阈值']}分")
print(f"   总收益率: {best['总收益']:.2%}")
print(f"   超额收益: {best['超额收益']:.2%}")
print(f"   夏普比率: {best['夏普']:.2f}")
print(f"   胜率:     {best['胜率']:.2%}")
print(f"   交易次数: {int(best['交易'])}笔")
print("=" * 70)

# 对比分析
print("\n💡 改进分析:")
default_result = df[(df['超卖阈值']==20) & (df['止损']=='5%') & (df['信号阈值']==50)]
if not default_result.empty:
    default_return = default_result.iloc[0]['总收益']
    improvement = best['总收益'] - default_return
    print(f"   默认参数收益: {default_return:.2%}")
    print(f"   最优参数收益: {best['总收益']:.2%}")
    print(f"   改进幅度:     {improvement:.2%} ({improvement/abs(default_return)*100:.1f}%)")
else:
    print("   默认参数未在测试范围内")

df.to_csv('kdj_ningde_optimization.csv', index=False, encoding='utf-8-sig')
print("\n✅ 完整结果已保存至: kdj_ningde_optimization.csv")
