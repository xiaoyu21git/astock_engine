#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
量价策略测试 - 对比KDJ策略
验证量价关系在不同市场的表现
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
print("         量价策略 vs KDJ策略 对比测试")
print("=" * 70)
print()
print("量价策略信号：")
print("  📈 买入信号：")
print("     1. 量价齐升 - 放量上涨（最强）")
print("     2. 缩量下跌后放量反弹 - 底部反转")
print("     3. OBV金叉 - 资金流入")
print("     4. 突破平台+放量 - 突破确认")
print()
print("  📉 卖出信号：")
print("     1. 巨量滞涨 - 顶部信号")
print("     2. 量价背离 - 价涨量缩")
print("     3. OBV死叉 - 资金流出")
print("=" * 70)
print()

# 测试股票（不同特征）
test_stocks = {
    '放量突破型': {
        '300750.SZ': '宁德时代',
        '002594.SZ': '比亚迪',
    },
    '震荡型': {
        '600036.SH': '招商银行',
        '000568.SZ': '泸州老窖',
    },
    '趋势型': {
        '000333.SZ': '美的集团',
        '600519.SH': '贵州茅台',
    }
}

# 策略配置
volume_params = {
    'mode': 'balanced',
    'volume_surge_ratio': 1.5,
    'volume_ma_period': 20,
    'price_ma_short': 5,
    'price_ma_long': 20,
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

data_manager = DataManager()
results = []

for category, stocks in test_stocks.items():
    print(f"\n{'='*70}")
    print(f"📊 测试类别：{category}")
    print(f"{'='*70}\n")
    
    for symbol, name in stocks.items():
        try:
            print(f"   {name} ({symbol})")
            
            # 获取数据
            data = data_manager.get_stock_data(
                symbols=[symbol],
                start_date='2024-02-01',
                end_date='2026-01-31'
            )
            
            df = data[symbol]
            buy_hold_return = (df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100
            
            # 测试量价策略
            plugin_manager = StrategyPluginManager()
            plugin_manager.scan_plugins()
            
            volume_strategy = plugin_manager.create_strategy('volume_price_strategy', volume_params)
            engine = BacktestEngine(config, enable_risk_control=True)
            volume_result = engine.run(volume_strategy, data)
            
            # 测试KDJ策略
            kdj_strategy = plugin_manager.create_strategy('kdj_strategy', kdj_params)
            engine = BacktestEngine(config, enable_risk_control=True)
            kdj_result = engine.run(kdj_strategy, data)
            
            # 结果对比
            volume_return = volume_result['total_return'] * 100
            kdj_return = kdj_result['total_return'] * 100
            
            volume_trades = volume_result.get('trade_count', 0)
            kdj_trades = kdj_result.get('trade_count', 0)
            
            volume_win_rate = volume_result.get('win_rate', 0) * 100
            kdj_win_rate = kdj_result.get('win_rate', 0) * 100
            
            volume_sharpe = volume_result.get('sharpe_ratio', 0)
            kdj_sharpe = kdj_result.get('sharpe_ratio', 0)
            
            # 判断哪个更好
            better = '量价' if volume_return > kdj_return else 'KDJ' if kdj_return > volume_return else '持平'
            
            print(f"      买入持有：{buy_hold_return:+.2f}%")
            print(f"      量价策略：{volume_return:+.2f}% ({volume_trades}笔, 胜率{volume_win_rate:.0f}%, 夏普{volume_sharpe:.2f})")
            print(f"      KDJ策略： {kdj_return:+.2f}% ({kdj_trades}笔, 胜率{kdj_win_rate:.0f}%, 夏普{kdj_sharpe:.2f})")
            print(f"      ✅ 优胜：{better}策略")
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
            print()

# 汇总分析
print()
print("=" * 70)
print("📈 策略对比总结")
print("=" * 70)
print()

if results:
    df = pd.DataFrame(results)
    
    # 按类别汇总
    for category in test_stocks.keys():
        cat_data = df[df['category'] == category]
        if len(cat_data) > 0:
            print(f"【{category}】")
            
            volume_avg = cat_data['volume_return'].mean()
            kdj_avg = cat_data['kdj_return'].mean()
            
            volume_wins = (cat_data['better'] == '量价').sum()
            kdj_wins = (cat_data['better'] == 'KDJ').sum()
            
            print(f"   量价策略平均收益：{volume_avg:+.2f}%")
            print(f"   KDJ策略平均收益：{kdj_avg:+.2f}%")
            print(f"   量价胜出次数：{volume_wins}/{len(cat_data)}")
            print(f"   KDJ胜出次数：{kdj_wins}/{len(cat_data)}")
            print()
    
    # 总体对比
    print("【总体统计】")
    print(f"   量价策略：")
    print(f"      平均收益：{df['volume_return'].mean():+.2f}%")
    print(f"      平均交易：{df['volume_trades'].mean():.0f}笔")
    print(f"      平均胜率：{df['volume_win_rate'].mean():.1f}%")
    print(f"      平均夏普：{df['volume_sharpe'].mean():.2f}")
    print()
    print(f"   KDJ策略：")
    print(f"      平均收益：{df['kdj_return'].mean():+.2f}%")
    print(f"      平均交易：{df['kdj_trades'].mean():.0f}笔")
    print(f"      平均胜率：{df['kdj_win_rate'].mean():.1f}%")
    print(f"      平均夏普：{df['kdj_sharpe'].mean():.2f}")
    print()
    
    volume_total_wins = (df['better'] == '量价').sum()
    kdj_total_wins = (df['better'] == 'KDJ').sum()
    
    print(f"   胜出统计：")
    print(f"      量价策略：{volume_total_wins}/{len(df)} ({volume_total_wins/len(df)*100:.0f}%)")
    print(f"      KDJ策略：{kdj_total_wins}/{len(df)} ({kdj_total_wins/len(df)*100:.0f}%)")

print()
print("=" * 70)
print("💡 策略适用性分析")
print("=" * 70)
print()
print("【量价策略】适合：")
print("   ✅ 资金驱动型股票（主力控盘明显）")
print("   ✅ 突破型行情（放量突破阻力）")
print("   ✅ 热点题材股（资金快进快出）")
print("   ✅ 成交量活跃股票")
print()
print("【KDJ策略】适合：")
print("   ✅ 震荡型股票（频繁超买超卖）")
print("   ✅ 均值回归特征明显")
print("   ✅ 波动规律性强")
print()
print("【组合建议】")
print("   🎯 方案1：双策略并行")
print("      同时运行两个策略，取两者共同信号（更稳健）")
print()
print("   🎯 方案2：分类应用")
print("      量价策略用于放量突破股")
print("      KDJ策略用于震荡股")
print()
print("   🎯 方案3：信号互补")
print("      量价作为主策略（信号生成）")
print("      KDJ作为过滤器（位置判断）")
