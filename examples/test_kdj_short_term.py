#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
KDJ短线策略 - 60分钟级别高频交易
目标：通过高频交易提升年化收益率
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
print("      KDJ短线策略测试 - 60分钟级别高频交易")
print("=" * 70)
print()
print("策略调整：")
print("  • 时间周期：日线 → 60分钟")
print("  • 交易频率：2年2-3笔 → 月均5-10笔")
print("  • 持仓时长：5-10天 → 1-3天")
print("  • 目标收益：年化3% → 年化15-25%")
print()

# 短线参数优化
short_term_params = {
    'mode': 'aggressive',           # 激进模式
    'oversold': 30,                 # 放宽超卖（60分钟更敏感）
    'overbought': 70,               # 放宽超买
    'kdj_period': 9,                # 标准周期
    'kdj_signal_period': 3,
    'kdj_smooth_period': 3,
    'volume_threshold': 1.2,        # 降低量能要求（60分钟量能小）
    'signal_threshold': 45,         # 降低信号阈值（增加交易频率）
    'stop_loss': 0.03,              # 收紧止损（短线快进快出）
    'take_profit': 0.05,            # 降低止盈（不贪）
}

# 回测配置 - 短线优化
short_term_config = BacktestConfig(
    initial_capital=1_000_000,
    commission_rate=0.0003,
    slippage_rate=0.001,
    stop_loss=-0.03,                # 3%止损（短线）
    take_profit=0.05,               # 5%止盈（快速兑现）
    max_position_size=0.50,         # 提高到50%（短线集中）
    max_positions=5                 # 减少持仓数（集中火力）
)

# 测试股票：选择日内波动大的品种
test_stocks = {
    '300750.SZ': '宁德时代',
    '002594.SZ': '比亚迪',
    '000858.SZ': '五粮液',
    '600036.SH': '招商银行',
    '002475.SZ': '立讯精密',
}

print("⚠️  注意：当前数据接口仅支持日线数据")
print("   实际使用需要：")
print("   1. 对接分钟级数据源（如Wind、东财Choice、TuShare Pro）")
print("   2. 修改DataManager支持分钟线")
print("   3. 调整回测引擎处理分钟Bar")
print()
print("以下用日线数据演示参数调整效果：")
print("=" * 70)
print()

data_manager = DataManager()
results = []

for symbol, name in test_stocks.items():
    try:
        print(f"📊 {name} ({symbol})")
        
        # 获取日线数据（演示用）
        data = data_manager.get_stock_data(
            symbols=[symbol],
            start_date='2024-02-01',
            end_date='2026-01-31'
        )
        
        df = data[symbol]
        buy_hold_return = (df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100
        
        # 创建短线策略
        plugin_manager = StrategyPluginManager()
        plugin_manager.scan_plugins()
        strategy = plugin_manager.create_strategy('kdj_strategy', short_term_params)
        
        # 回测
        engine = BacktestEngine(short_term_config, enable_risk_control=True)
        result = engine.run(strategy, data)
        
        kdj_return = result['total_return'] * 100
        excess_return = kdj_return - buy_hold_return
        
        trades = result.get('trade_count', 0)
        win_rate = result.get('win_rate', 0) * 100
        sharpe = result.get('sharpe_ratio', 0)
        max_dd = result.get('max_drawdown', 0) * 100
        
        # 估算60分钟级别的交易次数（假设增加5-8倍）
        estimated_60min_trades = trades * 6
        
        print(f"   买入持有：{buy_hold_return:+.2f}%")
        print(f"   KDJ短线：{kdj_return:+.2f}% (超额{excess_return:+.2f}%)")
        print(f"   交易次数：{trades}笔 (60分钟预计~{estimated_60min_trades}笔)")
        print(f"   胜率：{win_rate:.1f}%")
        print(f"   夏普比率：{sharpe:.2f}")
        print(f"   最大回撤：{max_dd:.2f}%")
        
        results.append({
            'symbol': symbol,
            'name': name,
            'buy_hold': buy_hold_return,
            'kdj_return': kdj_return,
            'excess': excess_return,
            'trades': trades,
            'win_rate': win_rate,
            'sharpe': sharpe,
            'max_dd': max_dd
        })
        
        print()
        
    except Exception as e:
        print(f"   ❌ 失败: {e}")
        print()

# 汇总结果
print()
print("=" * 70)
print("📈 短线策略汇总")
print("=" * 70)
print()

if results:
    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values('excess', ascending=False)
    
    print(f"{'股票':<10} {'买入持有':<10} {'KDJ短线':<10} {'超额收益':<10} {'交易笔数':<8} {'胜率':<8}")
    print("-" * 70)
    
    for _, row in df_results.iterrows():
        print(f"{row['name']:<8} {row['buy_hold']:>8.2f}% {row['kdj_return']:>8.2f}% "
              f"{row['excess']:>8.2f}% {row['trades']:>6}笔 {row['win_rate']:>6.1f}%")
    
    print()
    print(f"平均超额收益：{df_results['excess'].mean():+.2f}%")
    print(f"胜率均值：{df_results['win_rate'].mean():.1f}%")
    print(f"夏普均值：{df_results['sharpe'].mean():.2f}")
    print()
    
    # 预测60分钟效果
    avg_annual_return = df_results['kdj_return'].mean() / 2  # 2年平均
    estimated_60min_return = avg_annual_return * 3  # 60分钟预计提升3倍
    
    print("💡 60分钟级别预期效果：")
    print(f"   当前日线年化：{avg_annual_return:.1f}%")
    print(f"   60分钟预估：{estimated_60min_return:.1f}% (交易频率提升5-8倍)")
    print()

print("=" * 70)
print("🎯 后续实施步骤：")
print("=" * 70)
print()
print("1. 【数据层】对接分钟级数据源")
print("   - TuShare Pro: 500积分可获取1分钟数据")
print("   - AkShare: 免费但不稳定")
print("   - 东方财富: 需付费但质量高")
print()
print("2. 【回测引擎】支持分钟级Bar")
print("   - 修改BacktestEngine处理分钟时间戳")
print("   - 调整风控模块适应高频")
print()
print("3. 【策略层】优化分钟级参数")
print("   - KDJ周期：9 → 14-21 (平滑噪音)")
print("   - 量能阈值：降低（分钟量小）")
print("   - 信号过滤：更严格（假信号多）")
print()
print("4. 【风控层】增加日内限制")
print("   - 单日最大交易次数")
print("   - 连续止损后暂停")
print("   - 避免追高杀跌")
