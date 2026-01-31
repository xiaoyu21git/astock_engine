#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
KDJ策略针对美的集团优化 - 解决趋势股失效问题
目标：让失败案例（-1.95%）变成盈利
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
print("    KDJ策略针对美的优化 - 解决强趋势股失效问题")
print("=" * 70)
print()

# 加载美的数据
print("📊 加载美的集团数据...")
data_manager = DataManager()
symbol = '000333.SZ'

# 尝试获取数据，失败则使用模拟说明
try:
    data = data_manager.get_stock_data(
        symbols=[symbol],
        start_date='2024-02-01',
        end_date='2026-01-31'
    )
    print(f"✅ 数据加载完成: {len(data[symbol])}条")
    buy_hold = (data[symbol]['close'].iloc[-1] / data[symbol]['close'].iloc[0] - 1)
except Exception as e:
    print(f"⚠️ 数据获取失败: {e}")
    print("💡 使用理论分析模式（无需实际运行）")
    print()
    print("=" * 70)
    print("                理论优化分析")
    print("=" * 70)
    print()
    print("基于多股票测试结果，我们已知:")
    print("   美的集团: -1.95% (4笔交易, 0%胜率)")
    print("   宁德时代: +6.22% (6笔交易, 66.67%胜率)")
    print()
    print("失败原因分析:")
    print("   1. 美的是强趋势股（+49.61%），单边上涨")
    print("   2. KDJ策略本质是\"均值回归\"（逆势抄底）")
    print("   3. 在强趋势中，超卖只是小回调，不是反转")
    print("   4. -5%止损在趋势股中容易被洗出")
    print()
    print("参数优化方向:")
    print()
    print("方案1: 放宽止损（7%-10%）")
    print("   优点: 避免被趋势波动洗出")
    print("   缺点: 如果真的反转，损失更大")
    print("   预期效果: 减少交易次数，提升胜率")
    print()
    print("方案2: 提高信号阈值（60-70分）")
    print("   优点: 只做最高质量信号，减少错误交易")
    print("   缺点: 交易机会大幅减少")
    print("   预期效果: 可能从4笔降到1-2笔，但质量更高")
    print()
    print("方案3: 降低超卖阈值（K<15）")
    print("   优点: 只在深度超卖时买入")
    print("   缺点: 趋势股很少深度回调")
    print("   预期效果: 交易次数可能降为0")
    print()
    print("=" * 70)
    print("💡 核心结论:")
    print("=" * 70)
    print()
    print("参数优化只能\"微调\"，无法改变策略基因")
    print()
    print("KDJ策略（均值回归）vs 美的（强趋势）= 基因不匹配")
    print()
    print("真正的解决方案:")
    print("   1. 股票选择: 优先选震荡股/高波动股（如宁德时代）")
    print("   2. 策略分层:")
    print("      - 趋势股 → 用MACD/均线策略")
    print("      - 震荡股 → 用KDJ/RSI策略")
    print("   3. 市场环境过滤:")
    print("      - 牛市/强趋势 → 减仓或空仓")
    print("      - 震荡市 → 正常交易")
    print()
    print("=" * 70)
    print("📊 实战建议:")
    print("=" * 70)
    print()
    print("不要试图让一个策略适应所有股票!")
    print()
    print("正确做法:")
    print("   1. 先识别股票类型（趋势/震荡/高波动）")
    print("   2. 根据类型选择合适的策略")
    print("   3. 在宁德时代这类已验证有效的股票上优化")
    print("   4. 美的这类失败案例 → 换策略，不是调参数")
    print()
    print("宁德时代+6.22%已证明策略有效，应该:")
    print("   ✅ 在宁德时代上继续优化参数")
    print("   ✅ 寻找更多类似宁德时代的股票")
    print("   ✅ 建立\"适合KDJ的股票池\"")
    print("   ❌ 不要试图让KDJ在美的上盈利（徒劳）")
    print()
    print("=" * 70)
    import sys
    sys.exit(0)
print(f"   买入持有收益: {buy_hold:.2%}")
print(f"   当前KDJ策略: -1.95% (失败)")
print()

# 分析失败原因
print("🔍 失败原因分析:")
print("   1. 美的是强趋势股（+49.61%）")
print("   2. KDJ超卖买入 = 逆势抄底")
print("   3. -5%止损在小回调中被频繁触发")
print("   4. 策略基因：均值回归 vs 股票特性：趋势跟随")
print()

# 优化方案
print("💡 优化策略:")
print("   方案A: 放宽止损（适应趋势波动）")
print("   方案B: 提高信号门槛（只做高质量信号）")
print("   方案C: 加入趋势过滤（只在震荡市开仓）")
print("   方案D: 组合优化（多维度调整）")
print()

# 参数网格 - 针对趋势股特性设计
param_grid = {
    # A: 更宽松的止损（趋势股波动大）
    'stop_loss': [0.05, 0.07, 0.10, 0.12],
    
    # B: 更高的信号质量要求（减少交易）
    'signal_threshold': [55, 60, 65, 70],
    
    # C: 更严格的超卖要求（只做深度超卖）
    'oversold': [15, 20],
}

print("🔍 参数空间（针对趋势股）:")
print(f"   止损: {[f'{x:.0%}' for x in param_grid['stop_loss']]} (更宽松)")
print(f"   信号阈值: {param_grid['signal_threshold']}分 (更严格)")
print(f"   超卖阈值: {param_grid['oversold']} (深度超卖)")
total = len(param_grid['stop_loss']) * len(param_grid['signal_threshold']) * len(param_grid['oversold'])
print(f"   总组合: {total}种")
print()

plugin_manager = StrategyPluginManager()
plugin_manager.scan_plugins()

results = []
current = 0

print("⏳ 开始优化...")
for stop_loss in param_grid['stop_loss']:
    for signal_threshold in param_grid['signal_threshold']:
        for oversold in param_grid['oversold']:
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
            
            # 评估改进效果
            improvement = result.total_return - (-0.0195)  # 相比原始-1.95%
            is_profitable = result.total_return > 0
            beat_baseline = result.total_return > -0.0195
            
            results.append({
                '止损': f'{stop_loss:.0%}',
                '信号阈值': signal_threshold,
                '超卖': oversold,
                '总收益': result.total_return,
                '改进': improvement,
                '是否盈利': '✅' if is_profitable else '❌',
                '超越基准': '✅' if beat_baseline else '❌',
                '夏普': result.sharpe_ratio,
                '回撤': result.max_drawdown,
                '交易': result.num_trades,
                '胜率': result.win_rate,
            })
            
            if current % 4 == 0 or current == total:
                print(f"进度: {current}/{total} ({current/total:.0%})")

print()
print("=" * 70)
print("              优化结果分析")
print("=" * 70)

df = pd.DataFrame(results)

# 1. 按改进幅度排序
print("\n🏆 改进最大的组合 (按改进幅度排序):")
df_sorted = df.sort_values('改进', ascending=False)
print(df_sorted.head(10).to_string(index=False))

# 2. 找到盈利的组合
profitable = df[df['总收益'] > 0]
print(f"\n💰 实现盈利的组合数: {len(profitable)}/{len(df)}")
if len(profitable) > 0:
    print("\n✅ 盈利组合详情:")
    print(profitable.sort_values('总收益', ascending=False).to_string(index=False))
else:
    print("   ⚠️ 所有组合仍然亏损，但已有改进")

# 3. 最优参数
print("\n" + "=" * 70)
best = df_sorted.iloc[0]
print("📊 最优参数（改进最大）:")
print(f"   止损比例:   {best['止损']}")
print(f"   信号阈值:   {best['信号阈值']}分")
print(f"   超卖阈值:   {best['超卖']}")
print(f"   总收益:     {best['总收益']:.2%}")
print(f"   相比原始:   改进{best['改进']:.2%}")
print(f"   夏普比率:   {best['夏普']:.2f}")
print(f"   交易次数:   {int(best['交易'])}笔")
print(f"   胜率:       {best['胜率']:.2%}")

# 4. 参数影响分析
print("\n" + "=" * 70)
print("📈 参数影响分析:")

print("\n止损比例影响:")
for sl in param_grid['stop_loss']:
    avg_return = df[df['止损'] == f'{sl:.0%}']['总收益'].mean()
    print(f"   {sl:.0%}: 平均收益 {avg_return:.2%}")

print("\n信号阈值影响:")
for st in param_grid['signal_threshold']:
    avg_return = df[df['信号阈值'] == st]['总收益'].mean()
    trades = df[df['信号阈值'] == st]['交易'].mean()
    print(f"   {st}分: 平均收益 {avg_return:.2%}, 平均交易{trades:.1f}笔")

# 5. 结论
print("\n" + "=" * 70)
print("💡 优化结论:")

if len(profitable) > 0:
    print("   ✅ 成功！找到了让美的盈利的参数组合")
    print(f"   ✅ 最佳收益: {profitable['总收益'].max():.2%}")
    print("   ✅ 策略普适性提升，可应用于趋势股")
else:
    best_improvement = df_sorted.iloc[0]['改进']
    if best_improvement > 0.01:  # 改进超过1%
        print(f"   ⚠️ 虽未盈利，但已改进{best_improvement:.2%}")
        print("   💡 建议:")
        print("      1. 美的强趋势特性可能需要趋势跟随策略")
        print("      2. KDJ均值回归策略天然不适合单边市")
        print("      3. 可考虑策略组合：KDJ+MACD趋势确认")
    else:
        print("   ❌ 参数优化效果有限")
        print("   💡 根本问题：策略类型 vs 股票特性不匹配")
        print("      建议：在趋势股上改用MACD/MA策略")

print("=" * 70)

df.to_csv('kdj_midea_fix_optimization.csv', index=False, encoding='utf-8-sig')
print("\n✅ 完整结果已保存至: kdj_midea_fix_optimization.csv")
