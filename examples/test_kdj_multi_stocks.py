#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
KDJ策略多股票测试 - 找到适合的股票类型
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
print("           KDJ策略多股票测试 - 寻找适配股票")
print("=" * 70)
print()

# 测试股票池（不同行业、不同特征）
test_stocks = {
    '趋势强势': {
        '000333.SZ': '美的集团',
        '300750.SZ': '宁德时代',
    },
    '震荡型': {
        '601398.SH': '工商银行',
        '601988.SH': '中国银行',
    },
    '高波动': {
        '002594.SZ': '比亚迪',
        '600519.SH': '贵州茅台',
    },
    '周期性': {
        '601899.SH': '紫金矿业',
        '600362.SH': '江西铜业',
    }
}

# 展开股票列表
all_stocks = {}
for category, stocks in test_stocks.items():
    all_stocks.update(stocks)

print(f"📊 测试股票池: {len(all_stocks)}只")
for symbol, name in all_stocks.items():
    print(f"   {symbol}: {name}")
print()

# 加载数据
print("⏳ 加载历史数据...")
data_manager = DataManager()
results = []

for symbol, name in all_stocks.items():
    try:
        print(f"   处理 {name}...", end='')
        
        # 获取数据
        data = data_manager.get_stock_data(
            symbols=[symbol],
            start_date='2024-02-01',
            end_date='2026-01-31'
        )
        
        df = data[symbol]
        buy_hold_return = (df['close'].iloc[-1] / df['close'].iloc[0] - 1)
        
        # 创建策略
        plugin_manager = StrategyPluginManager()
        plugin_manager.scan_plugins()
        strategy = plugin_manager.create_strategy('kdj_strategy')
        
        # 回测
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
        result = engine.run(strategy, data)
        
        # 找到股票类别
        category_name = None
        for cat, stocks in test_stocks.items():
            if symbol in stocks:
                category_name = cat
                break
        
        results.append({
            '类别': category_name,
            '代码': symbol,
            '名称': name,
            '买入持有': buy_hold_return,
            'KDJ收益': result.total_return,
            '超额收益': result.total_return - buy_hold_return,
            '最大回撤': result.max_drawdown,
            '夏普比率': result.sharpe_ratio,
            '交易次数': result.num_trades,
            '胜率': result.win_rate,
        })
        
        print(f" ✅ (收益: {result.total_return:.2%})")
        
    except Exception as e:
        print(f" ❌ 失败: {e}")
        continue

print()
print("=" * 70)
print("                      测试结果")
print("=" * 70)

# 转换为DataFrame
df_results = pd.DataFrame(results)

# 按类别分组显示
print("\n📊 按股票类别统计:")
for category in df_results['类别'].unique():
    cat_data = df_results[df_results['类别'] == category]
    avg_return = cat_data['KDJ收益'].mean()
    avg_excess = cat_data['超额收益'].mean()
    avg_winrate = cat_data['胜率'].mean()
    
    print(f"\n【{category}】")
    print(f"   平均收益: {avg_return:>8.2%}")
    print(f"   超额收益: {avg_excess:>8.2%}")
    print(f"   平均胜率: {avg_winrate:>8.2%}")
    print("   " + "-" * 60)
    print(cat_data[['名称', 'KDJ收益', '超额收益', '胜率', '交易次数']].to_string(index=False))

print("\n" + "=" * 70)
print("🏆 最佳表现股票 (按KDJ收益排序):")
print(df_results.nlargest(5, 'KDJ收益')[['名称', 'KDJ收益', '超额收益', '胜率']].to_string(index=False))

print("\n" + "=" * 70)
print("💡 结论:")
best_category = df_results.groupby('类别')['KDJ收益'].mean().idxmax()
print(f"   KDJ策略最适合: {best_category}股票")
print(f"   建议优先在该类别股票中应用本策略")
print("=" * 70)

# 保存结果
df_results.to_csv('kdj_multi_stock_test.csv', index=False, encoding='utf-8-sig')
print("\n✅ 完整结果已保存至: kdj_multi_stock_test.csv")
