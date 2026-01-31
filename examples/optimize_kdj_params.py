#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
KDJ策略参数优化 - 网格搜索
测试不同参数组合，找到最优配置
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime
from astock_engine.data.data_provider import DataManager
from astock_engine.strategies.plugin_manager import StrategyPluginManager
from astock_engine.backtest.backtest_engine import BacktestEngine, BacktestConfig
import pandas as pd
import logging

logging.basicConfig(level=logging.WARNING)  # 只显示警告，减少输出

print("=" * 70)
print("              KDJ策略参数优化 - 网格搜索")
print("=" * 70)
print()

# 1. 准备数据
print("📊 加载数据...")
data_manager = DataManager()
symbol = '000333.SZ'
data = data_manager.get_stock_data(
    symbols=[symbol],
    start_date='2024-02-01',
    end_date='2026-01-31'
)
print(f"✅ 数据加载完成: {len(data[symbol])}条")
print()

# 2. 定义参数空间
param_grid = {
    'oversold': [15, 20, 25, 30],           # 超卖阈值
    'stop_loss': [0.03, 0.05, 0.07, 0.10],  # 止损比例
    'signal_threshold': [50, 60, 65],       # 信号质量阈值（D级分数线）
}

print("🔍 参数搜索空间:")
print(f"   超卖阈值: {param_grid['oversold']}")
print(f"   止损比例: {[f'{x:.0%}' for x in param_grid['stop_loss']]}")
print(f"   信号阈值: {param_grid['signal_threshold']}分")
print(f"   总组合数: {len(param_grid['oversold']) * len(param_grid['stop_loss']) * len(param_grid['signal_threshold'])}")
print()

# 3. 网格搜索
plugin_manager = StrategyPluginManager()
plugin_manager.scan_plugins()

results = []
total = len(param_grid['oversold']) * len(param_grid['stop_loss']) * len(param_grid['signal_threshold'])
current = 0

print("⏳ 开始参数优化...")
for oversold in param_grid['oversold']:
    for stop_loss in param_grid['stop_loss']:
        for signal_threshold in param_grid['signal_threshold']:
            current += 1
            
            # 创建策略
            strategy = plugin_manager.create_strategy('kdj_strategy', params={
                'oversold': oversold,
                'signal_threshold': signal_threshold,  # 添加到策略参数
            })
            
            # 配置回测
            config = BacktestConfig(
                initial_capital=1_000_000,
                commission_rate=0.0003,
                slippage_rate=0.001,
                stop_loss=-stop_loss,  # 动态止损
                take_profit=0.20,
                max_position_size=0.30,
                max_positions=10
            )
            
            # 运行回测
            engine = BacktestEngine(config, enable_risk_control=True)
            result = engine.run(strategy, data)
            
            # 记录结果
            results.append({
                '超卖阈值': oversold,
                '止损比例': f'{stop_loss:.0%}',
                '信号阈值': signal_threshold,
                '总收益': result.total_return,
                '年化收益': result.annual_return,
                '最大回撤': result.max_drawdown,
                '夏普比率': result.sharpe_ratio,
                '交易次数': result.num_trades,
                '胜率': result.win_rate,
                '盈亏比': result.profit_factor,
            })
            
            # 进度显示
            if current % 5 == 0 or current == total:
                print(f"进度: {current}/{total} ({current/total:.0%})")

print()
print("=" * 70)
print("                   优化结果（按总收益排序）")
print("=" * 70)

# 转换为DataFrame并排序
df_results = pd.DataFrame(results)
df_results = df_results.sort_values('总收益', ascending=False)

# 显示前10名
print("\n🏆 Top 10 参数组合:")
print(df_results.head(10).to_string(index=False))

print("\n" + "=" * 70)
print("📊 最优参数:")
best = df_results.iloc[0]
print(f"   超卖阈值: {best['超卖阈值']}")
print(f"   止损比例: {best['止损比例']}")
print(f"   信号阈值: {best['信号阈值']}分")
print(f"   总收益率: {best['总收益']:.2%}")
print(f"   夏普比率: {best['夏普比率']:.2f}")
print(f"   胜率:     {best['胜率']:.2%}")
print("=" * 70)

# 保存结果
df_results.to_csv('kdj_optimization_results.csv', index=False, encoding='utf-8-sig')
print("\n✅ 完整结果已保存至: kdj_optimization_results.csv")
