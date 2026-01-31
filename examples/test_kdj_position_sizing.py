#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
KDJ高仓位策略 - 提升资金利用率
通过提高单笔仓位和总仓位上限提升收益
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
print("       KDJ高仓位策略 - 提升资金利用率")
print("=" * 70)
print()
print("对比测试：")
print("  保守配置：单只30%，总仓位不超过100%")
print("  激进配置：单只50%，允许A级信号满仓")
print("=" * 70)
print()

# 测试配置
configs = {
    '保守配置': {
        'params': {
            'mode': 'balanced',
            'oversold': 20,
            'signal_threshold': 60,
        },
        'config': BacktestConfig(
            initial_capital=1_000_000,
            commission_rate=0.0003,
            slippage_rate=0.001,
            stop_loss=-0.05,
            take_profit=0.20,
            max_position_size=0.30,      # 30%上限
            max_positions=3              # 最多3只
        )
    },
    '激进配置': {
        'params': {
            'mode': 'aggressive',
            'oversold': 25,
            'signal_threshold': 50,       # 降低阈值增加信号
        },
        'config': BacktestConfig(
            initial_capital=1_000_000,
            commission_rate=0.0003,
            slippage_rate=0.001,
            stop_loss=-0.07,              # 放宽止损
            take_profit=0.25,
            max_position_size=0.50,       # 50%上限
            max_positions=2               # 集中持仓
        )
    },
    '满仓配置': {
        'params': {
            'mode': 'aggressive',
            'oversold': 25,
            'signal_threshold': 65,        # 仅A级信号
        },
        'config': BacktestConfig(
            initial_capital=1_000_000,
            commission_rate=0.0003,
            slippage_rate=0.001,
            stop_loss=-0.08,
            take_profit=0.30,
            max_position_size=1.00,        # 允许满仓！
            max_positions=1                # 单只集中
        )
    }
}

# 测试股票：最适合KDJ的
test_stocks = {
    '300750.SZ': '宁德时代',
    '600036.SH': '招商银行',
    '000568.SZ': '泸州老窖',
}

data_manager = DataManager()
all_results = []

for config_name, config_dict in configs.items():
    print(f"\n{'='*70}")
    print(f"🔬 测试配置：{config_name}")
    print(f"{'='*70}\n")
    
    for symbol, name in test_stocks.items():
        try:
            print(f"   {name}...", end=' ')
            
            # 获取数据
            data = data_manager.get_stock_data(
                symbols=[symbol],
                start_date='2024-02-01',
                end_date='2026-01-31'
            )
            
            df = data[symbol]
            buy_hold_return = (df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100
            
            # 创建策略
            plugin_manager = StrategyPluginManager()
            plugin_manager.scan_plugins()
            strategy = plugin_manager.create_strategy('kdj_strategy', config_dict['params'])
            
            # 回测
            engine = BacktestEngine(config_dict['config'], enable_risk_control=True)
            result = engine.run(strategy, data)
            
            kdj_return = result['total_return'] * 100
            excess = kdj_return - buy_hold_return
            trades = result.get('trade_count', 0)
            win_rate = result.get('win_rate', 0) * 100
            max_dd = result.get('max_drawdown', 0) * 100
            
            print(f"收益{kdj_return:+.2f}% (超额{excess:+.2f}%) "
                  f"{trades}笔 胜率{win_rate:.0f}% 回撤{max_dd:.1f}%")
            
            all_results.append({
                'config': config_name,
                'symbol': symbol,
                'name': name,
                'kdj_return': kdj_return,
                'excess': excess,
                'trades': trades,
                'win_rate': win_rate,
                'max_dd': max_dd
            })
            
        except Exception as e:
            print(f"失败: {e}")

# 汇总分析
print()
print("=" * 70)
print("📊 仓位配置对比分析")
print("=" * 70)
print()

if all_results:
    df = pd.DataFrame(all_results)
    
    for config_name in configs.keys():
        config_data = df[df['config'] == config_name]
        if len(config_data) > 0:
            avg_return = config_data['kdj_return'].mean()
            avg_excess = config_data['excess'].mean()
            avg_trades = config_data['trades'].mean()
            avg_win_rate = config_data['win_rate'].mean()
            avg_dd = config_data['max_dd'].mean()
            
            print(f"【{config_name}】")
            print(f"  平均收益：{avg_return:+.2f}% (超额{avg_excess:+.2f}%)")
            print(f"  平均交易：{avg_trades:.0f}笔")
            print(f"  平均胜率：{avg_win_rate:.1f}%")
            print(f"  平均回撤：{avg_dd:.2f}%")
            print(f"  收益/回撤：{avg_return/avg_dd:.2f}" if avg_dd > 0 else "  收益/回撤：N/A")
            print()

print("=" * 70)
print("💡 建议配置方案")
print("=" * 70)
print()
print("📌 方案1：稳健型（风险厌恶）")
print("   单只仓位：30%")
print("   最大持仓：3只（总90%）")
print("   适用：保守投资者，年化目标5-8%")
print()
print("📌 方案2：进取型（平衡风险收益）")
print("   单只仓位：40-50%")
print("   最大持仓：2只（总80-100%）")
print("   信号过滤：B级以上")
print("   适用：一般投资者，年化目标10-15%")
print()
print("📌 方案3：激进型（追求高收益）")
print("   单只仓位：80-100%")
print("   最大持仓：1只（满仓）")
print("   信号过滤：仅A级（80分以上）")
print("   止损：8-10%")
print("   适用：风险承受力强，年化目标20%+")
print()
print("⚠️  风险提示：")
print("   • 高仓位 = 高波动，回撤可能达15-20%")
print("   • 集中持仓风险：单只黑天鹅事件影响大")
print("   • 建议根据市场环境动态调整：")
print("     - 牛市：激进配置")
print("     - 震荡市：进取配置")
print("     - 熊市：保守配置或空仓")
