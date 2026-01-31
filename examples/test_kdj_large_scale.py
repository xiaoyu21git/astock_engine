#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
KDJ策略大规模股票池测试 - 建立统计显著性
测试50+只股票，找出真正适合KDJ的股票特征
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from astock_engine.data.data_provider import DataManager
from astock_engine.strategies.plugin_manager import StrategyPluginManager
from astock_engine.backtest.backtest_engine import BacktestEngine, BacktestConfig
import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.WARNING)

print("=" * 70)
print("        KDJ策略大规模测试 - 50+股票样本")
print("=" * 70)
print()

# 扩大股票池 - 覆盖多个行业和市值
test_stocks = {
    # 大盘蓝筹（低波动）
    '601398.SH': '工商银行',
    '601988.SH': '中国银行',
    '600036.SH': '招商银行',
    '601288.SH': '农业银行',
    '600000.SH': '浦发银行',
    
    # 白马股（稳健增长）
    '000333.SZ': '美的集团',
    '000858.SZ': '五粮液',
    '600519.SH': '贵州茅台',
    '000568.SZ': '泸州老窖',
    '600887.SH': '伊利股份',
    
    # 科技成长（高波动）
    '300750.SZ': '宁德时代',
    '002594.SZ': '比亚迪',
    '300059.SZ': '东方财富',
    '002475.SZ': '立讯精密',
    '300782.SZ': '卓胜微',
    
    # 周期股
    '601899.SH': '紫金矿业',
    '600362.SH': '江西铜业',
    '600547.SH': '山东黄金',
    '601088.SH': '中国神华',
    '600028.SH': '中国石化',
    
    # 医药生物
    '300015.SZ': '爱尔眼科',
    '000661.SZ': '长春高新',
    '300760.SZ': '迈瑞医疗',
    '600276.SH': '恒瑞医药',
    '000538.SZ': '云南白药',
    
    # 消费
    '002304.SZ': '洋河股份',
    '600809.SH': '山西汾酒',
    '002714.SZ': '牧原股份',
    '000895.SZ': '双汇发展',
    '603288.SH': '海天味业',
    
    # 新能源
    '601012.SH': '隆基绿能',
    '688599.SH': '天合光能',
    '300274.SZ': '阳光电源',
    '002459.SZ': '晶澳科技',
    '601865.SH': '福莱特',
    
    # 军工
    '002415.SZ': '海康威视',
    '600893.SH': '航发动力',
    '000768.SZ': '中航西飞',
    '600760.SH': '中航沈飞',
    
    # 房地产
    '000002.SZ': '万科A',
    '600048.SH': '保利发展',
    '001979.SZ': '招商蛇口',
    '600340.SH': '华夏幸福',
    
    # 互联网
    '300033.SZ': '同花顺',
    '002230.SZ': '科大讯飞',
    '300223.SZ': '北京君正',
    
    # 汽车
    '601633.SH': '长城汽车',
    '000625.SZ': '长安汽车',
    '600104.SH': '上汽集团',
}

print(f"📊 测试股票池: {len(test_stocks)}只")
print(f"   行业覆盖: 银行、白马、科技、周期、医药、消费、新能源等")
print()

# 数据收集
data_manager = DataManager()
results = []
failed_stocks = []

print("⏳ 开始测试（预计5-10分钟）...")
print()

for idx, (symbol, name) in enumerate(test_stocks.items(), 1):
    try:
        print(f"[{idx}/{len(test_stocks)}] {name}...", end='', flush=True)
        
        # 获取数据
        data = data_manager.get_stock_data(
            symbols=[symbol],
            start_date='2024-02-01',
            end_date='2026-01-31'
        )
        
        if symbol not in data or data[symbol].empty:
            print(" ⚠️ 无数据")
            failed_stocks.append((symbol, name, "无数据"))
            continue
        
        df = data[symbol]
        
        # 计算股票特征
        buy_hold_return = (df['close'].iloc[-1] / df['close'].iloc[0] - 1)
        
        # 波动率（标准差/均值）
        volatility = df['close'].pct_change().std() * np.sqrt(252)
        
        # 趋势性（线性回归斜率）
        x = np.arange(len(df))
        y = df['close'].values
        trend_slope = np.polyfit(x, y, 1)[0] / y.mean()
        
        # 振幅（最大最小差/均值）
        price_range = (df['close'].max() - df['close'].min()) / df['close'].mean()
        
        # 回测KDJ策略
        plugin_manager = StrategyPluginManager()
        plugin_manager.scan_plugins()
        strategy = plugin_manager.create_strategy('kdj_strategy')
        
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
        
        # 记录结果
        results.append({
            '代码': symbol,
            '名称': name,
            '买入持有': buy_hold_return,
            'KDJ收益': result.total_return,
            '超额收益': result.total_return - buy_hold_return,
            '夏普': result.sharpe_ratio,
            '最大回撤': result.max_drawdown,
            '交易次数': result.num_trades,
            '胜率': result.win_rate,
            '波动率': volatility,
            '趋势性': trend_slope,
            '振幅': price_range,
        })
        
        status = "✅" if result.total_return > 0 else "❌"
        print(f" {status} KDJ:{result.total_return:>7.2%} (持有:{buy_hold_return:>7.2%})")
        
    except Exception as e:
        print(f" ❌ 失败: {str(e)[:50]}")
        failed_stocks.append((symbol, name, str(e)[:50]))
        continue

print()
print("=" * 70)
print("                     测试结果统计")
print("=" * 70)

if len(results) == 0:
    print("\n⚠️ 所有股票测试失败")
    print("失败列表:")
    for symbol, name, reason in failed_stocks:
        print(f"   {symbol} {name}: {reason}")
    import sys
    sys.exit(1)

df = pd.DataFrame(results)

# 1. 整体统计
print(f"\n📊 样本统计:")
print(f"   成功测试: {len(results)}只")
print(f"   失败跳过: {len(failed_stocks)}只")
print(f"   盈利数量: {len(df[df['KDJ收益'] > 0])}只 ({len(df[df['KDJ收益'] > 0])/len(df)*100:.1f}%)")
print(f"   跑赢持有: {len(df[df['超额收益'] > 0])}只 ({len(df[df['超额收益'] > 0])/len(df)*100:.1f}%)")

print(f"\n💰 收益统计:")
print(f"   平均KDJ收益: {df['KDJ收益'].mean():.2%}")
print(f"   中位数收益:   {df['KDJ收益'].median():.2%}")
print(f"   最佳收益:     {df['KDJ收益'].max():.2%}")
print(f"   最差收益:     {df['KDJ收益'].min():.2%}")
print(f"   平均超额:     {df['超额收益'].mean():.2%}")

print(f"\n📈 交易统计:")
print(f"   平均交易次数: {df['交易次数'].mean():.1f}笔")
print(f"   平均胜率:     {df['胜率'].mean():.2%}")
print(f"   平均夏普:     {df['夏普'].mean():.2f}")

# 2. Top & Bottom
print("\n" + "=" * 70)
print("🏆 表现最佳 Top 10:")
print(df.nlargest(10, 'KDJ收益')[['名称', 'KDJ收益', '超额收益', '胜率', '交易次数']].to_string(index=False))

print("\n" + "=" * 70)
print("⚠️ 表现最差 Bottom 10:")
print(df.nsmallest(10, 'KDJ收益')[['名称', 'KDJ收益', '超额收益', '胜率', '交易次数']].to_string(index=False))

# 3. 特征分析 - 找出成功股票的共同特征
print("\n" + "=" * 70)
print("🔍 成功股票特征分析")
print("=" * 70)

profitable = df[df['KDJ收益'] > 0]
unprofitable = df[df['KDJ收益'] <= 0]

if len(profitable) > 0:
    print(f"\n盈利组 ({len(profitable)}只) vs 亏损组 ({len(unprofitable)}只):")
    print(f"   波动率: {profitable['波动率'].mean():.2%} vs {unprofitable['波动率'].mean():.2%}")
    print(f"   趋势性: {profitable['趋势性'].mean():.4f} vs {unprofitable['趋势性'].mean():.4f}")
    print(f"   振幅:   {profitable['振幅'].mean():.2%} vs {unprofitable['振幅'].mean():.2%}")
    print(f"   交易数: {profitable['交易次数'].mean():.1f} vs {unprofitable['交易次数'].mean():.1f}")
    
    print("\n💡 关键发现:")
    if profitable['波动率'].mean() > unprofitable['波动率'].mean():
        print("   ✅ 盈利股票波动率更高")
    if abs(profitable['趋势性'].mean()) < abs(unprofitable['趋势性'].mean()):
        print("   ✅ 盈利股票趋势性更弱（更震荡）")
    if profitable['振幅'].mean() > unprofitable['振幅'].mean():
        print("   ✅ 盈利股票振幅更大")

# 4. 相关性分析
print("\n" + "=" * 70)
print("📊 收益与特征相关性:")
print("=" * 70)
print(f"   波动率 相关系数: {df['波动率'].corr(df['KDJ收益']):.3f}")
print(f"   趋势性 相关系数: {df['趋势性'].corr(df['KDJ收益']):.3f}")
print(f"   振幅   相关系数: {df['振幅'].corr(df['KDJ收益']):.3f}")

# 5. 建议的股票池
print("\n" + "=" * 70)
print("🎯 推荐KDJ策略股票池（收益>0%）:")
print("=" * 70)

if len(profitable) > 0:
    profitable_sorted = profitable.sort_values('KDJ收益', ascending=False)
    print(profitable_sorted[['名称', 'KDJ收益', '胜率', '波动率', '交易次数']].to_string(index=False))
    
    print(f"\n✅ 共{len(profitable)}只股票适合KDJ策略")
    print(f"   样本量: {len(results)}只（统计显著性: {'✅充足' if len(results) >= 30 else '⚠️偏少'}）")
else:
    print("   ⚠️ 无盈利股票")

# 保存结果
df.to_csv('kdj_large_scale_test.csv', index=False, encoding='utf-8-sig')
print("\n✅ 完整结果已保存至: kdj_large_scale_test.csv")
print("=" * 70)
