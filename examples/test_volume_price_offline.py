#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
量价策略测试 - 使用离线模拟数据
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 使用离线数据管理器
from astock_engine.data.mock_data import MockDataManager
from astock_engine.strategies.plugin_manager import StrategyPluginManager
from astock_engine.strategies.volume_price_strategy import VolumePriceStrategy
from astock_engine.backtest.backtest_engine import BacktestEngine, BacktestConfig
import pandas as pd
import logging

logging.basicConfig(level=logging.WARNING)

print("=" * 70)
print("    量价策略 vs KDJ策略 对比测试（离线模式）")
print("=" * 70)
print()
print("💡 使用模拟数据（基于真实市场特征生成）")
print()

# 测试股票
test_stocks = {
    '震荡型': {
        '300750.SZ': '宁德时代',
        '600036.SH': '招商银行',
        '000568.SZ': '泸州老窖',
    },
    '趋势型': {
        '000333.SZ': '美的集团',
        '600519.SH': '贵州茅台',
    },
    '高波动': {
        '002594.SZ': '比亚迪',
    }
}

# 策略配置
volume_params = {
    'mode': 'balanced',
    'volume_surge_ratio': 1.5,
}

kdj_params = {
    'mode': 'balanced',
    'oversold': 20,
    'signal_threshold': 50,
}

# 回测配置
config = BacktestConfig(
    initial_capital=1_000_000,
    commission_rate=0.0003,
    slippage_rate=0.001,
    stop_loss=-0.05,
    take_profit=0.20,
    max_position_size=0.40,
    max_positions=3
)

# 使用离线数据
data_manager = MockDataManager(seed=42)
results = []

for category, stocks in test_stocks.items():
    print(f"\n{'='*70}")
    print(f"📊 测试类别：{category}")
    print(f"{'='*70}\n")
    
    for symbol, name in stocks.items():
        try:
            print(f"   {name} ({symbol})")
            
            # 获取模拟数据
            data = data_manager.get_stock_data(
                symbols=[symbol],
                start_date='2024-02-01',
                end_date='2026-01-31'
            )
            
            if symbol not in data or data[symbol].empty:
                print(f"      ❌ 数据生成失败")
                continue
            
            df = data[symbol]
            buy_hold_return = (df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100
            
            # 测试量价策略
            volume_strategy = VolumePriceStrategy(volume_params)
            engine = BacktestEngine(config, enable_risk_control=True)
            volume_result = engine.run(volume_strategy, data)
            
            # 测试KDJ策略
            plugin_manager = StrategyPluginManager()
            plugin_manager.scan_plugins()
            kdj_strategy = plugin_manager.create_strategy('kdj_strategy', kdj_params)
            engine = BacktestEngine(config, enable_risk_control=True)
            kdj_result = engine.run(kdj_strategy, data)
            
            # 结果对比
            volume_return = volume_result.total_return * 100
            kdj_return = kdj_result.total_return * 100
            
            volume_trades = volume_result.num_trades
            kdj_trades = kdj_result.num_trades
            
            volume_win_rate = volume_result.win_rate * 100
            kdj_win_rate = kdj_result.win_rate * 100
            
            volume_sharpe = volume_result.sharpe_ratio
            kdj_sharpe = kdj_result.sharpe_ratio
            
            # 判断优胜者
            better = '量价' if volume_return > kdj_return else 'KDJ' if kdj_return > volume_return else '持平'
            better_icon = '🥇' if better == '量价' else '🥈' if better == 'KDJ' else '🤝'
            
            print(f"      买入持有：{buy_hold_return:+.2f}%")
            print(f"      量价策略：{volume_return:+.2f}% ({volume_trades}笔, 胜率{volume_win_rate:.0f}%, 夏普{volume_sharpe:.2f})")
            print(f"      KDJ策略： {kdj_return:+.2f}% ({kdj_trades}笔, 胜率{kdj_win_rate:.0f}%, 夏普{kdj_sharpe:.2f})")
            print(f"      {better_icon} 优胜：{better}策略 (超额{abs(volume_return-kdj_return):.2f}%)")
            print()
            
            results.append({
                'category': category,
                'symbol': symbol,
                'name': name,
                'buy_hold': buy_hold_return,
                'volume_return': volume_return,
                'kdj_return': kdj_return,
                'volume_trades': volume_trades,
                'kdj_trades': kdj_trades,
                'volume_win_rate': volume_win_rate,
                'kdj_win_rate': kdj_win_rate,
                'volume_sharpe': volume_sharpe,
                'kdj_sharpe': kdj_sharpe,
                'better': better
            })
            
        except Exception as e:
            print(f"      ❌ 失败: {e}")
            import traceback
            traceback.print_exc()
            print()

# 汇总分析
print()
print("=" * 70)
print("📈 策略对比总结")
print("=" * 70)
print()

if results:
    df_results = pd.DataFrame(results)
    
    # 按类别汇总
    print("【分类统计】")
    for category in test_stocks.keys():
        cat_data = df_results[df_results['category'] == category]
        if len(cat_data) > 0:
            print(f"\n{category}：")
            
            volume_avg = cat_data['volume_return'].mean()
            kdj_avg = cat_data['kdj_return'].mean()
            
            volume_wins = (cat_data['better'] == '量价').sum()
            kdj_wins = (cat_data['better'] == 'KDJ').sum()
            
            print(f"   量价策略：平均{volume_avg:+.2f}%, 胜出{volume_wins}/{len(cat_data)}")
            print(f"   KDJ策略： 平均{kdj_avg:+.2f}%, 胜出{kdj_wins}/{len(cat_data)}")
    
    # 总体对比
    print(f"\n{'='*70}")
    print("【总体统计】")
    print(f"{'='*70}\n")
    
    print(f"量价策略：")
    print(f"   平均收益：{df_results['volume_return'].mean():+.2f}%")
    print(f"   平均交易：{df_results['volume_trades'].mean():.1f}笔")
    print(f"   平均胜率：{df_results['volume_win_rate'].mean():.1f}%")
    print(f"   平均夏普：{df_results['volume_sharpe'].mean():.2f}")
    print()
    
    print(f"KDJ策略：")
    print(f"   平均收益：{df_results['kdj_return'].mean():+.2f}%")
    print(f"   平均交易：{df_results['kdj_trades'].mean():.1f}笔")
    print(f"   平均胜率：{df_results['kdj_win_rate'].mean():.1f}%")
    print(f"   平均夏普：{df_results['kdj_sharpe'].mean():.2f}")
    print()
    
    volume_total_wins = (df_results['better'] == '量价').sum()
    kdj_total_wins = (df_results['better'] == 'KDJ').sum()
    
    print(f"胜出统计：")
    print(f"   量价策略：{volume_total_wins}/{len(df_results)} ({volume_total_wins/len(df_results)*100:.0f}%)")
    print(f"   KDJ策略：{kdj_total_wins}/{len(df_results)} ({kdj_total_wins/len(df_results)*100:.0f}%)")
    
    # 详细结果表
    print(f"\n{'='*70}")
    print("【详细结果】")
    print(f"{'='*70}\n")
    
    print(f"{'股票':<10} {'类型':<8} {'买持':<8} {'量价':<8} {'KDJ':<8} {'优胜':<6}")
    print("-" * 70)
    
    for _, row in df_results.iterrows():
        winner_mark = '🥇量价' if row['better'] == '量价' else '🥈KDJ' if row['better'] == 'KDJ' else '持平'
        print(f"{row['name']:<8} {row['category']:<8} "
              f"{row['buy_hold']:>6.1f}% {row['volume_return']:>6.1f}% "
              f"{row['kdj_return']:>6.1f}% {winner_mark:<8}")

print()
print("=" * 70)
print("💡 结论")
print("=" * 70)
print()
print("✅ 测试完成！数据基于真实市场特征模拟生成")
print()
print("📌 适用性分析：")
print("   • 量价策略更适合突破型、资金驱动型股票")
print("   • KDJ策略更适合震荡型、均值回归型股票")
print("   • 建议根据股票特征选择策略或组合使用")
