"""
KDJ策略模式对比测试
对比短线模式(swing)和趋势模式(trend)的表现差异
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from datetime import datetime
from astock_engine import AStockEngine

def test_kdj_modes():
    """测试KDJ策略的两种模式"""
    
    print("\n" + "=" * 70)
    print("KDJ策略模式对比测试")
    print("=" * 70)
    
    # 初始化引擎
    engine = AStockEngine()
    
    # 获取数据
    print("\n📊 获取美的集团历史数据...")
    data = engine.data_manager.get_stock_data(
        symbols=['000333.SZ'],
        start_date='2024-02-01',
        end_date='2026-01-31'
    )
    print(f"✅ 获取{len(data['000333.SZ'])}条数据")
    
    results = {}
    
    # 测试1: 短线模式 (默认)
    print("\n" + "=" * 70)
    print("【测试1】短线波段模式 (Swing Trading)")
    print("特点: 接近压力位(前20日高点-2%)主动止盈")
    print("=" * 70)
    
    swing_params = {
        'n': 9,
        'oversold': 20,
        'overbought': 80,
        'mode': 'swing',  # 短线模式
        'resistance_period': 20,
        'resistance_buffer': 0.02
    }
    
    swing_strategy = engine.strategy_manager.create_strategy('kdj_strategy', swing_params)
    
    result_swing = engine.backtest(
        data=data,
        strategy=swing_strategy,
        initial_capital=1000000,
        commission_rate=0.0003
    )
    
    results['swing'] = result_swing
    
    print(f"\n短线模式结果:")
    print(f"  总收益率: {result_swing['total_return']:.2f}%")
    print(f"  交易次数: {result_swing['total_trades']}笔")
    print(f"  胜率: {result_swing['win_rate']:.2f}%")
    print(f"  最大回撤: {result_swing['max_drawdown']:.2f}%")
    
    # 测试2: 趋势模式
    print("\n" + "=" * 70)
    print("【测试2】趋势跟踪模式 (Trend Following)")
    print("特点: 不主动止盈,等待趋势反转(跌破MA20)或KDJ死叉")
    print("=" * 70)
    
    trend_params = {
        'n': 9,
        'oversold': 20,
        'overbought': 80,
        'mode': 'trend',  # 趋势模式
    }
    
    trend_strategy = engine.strategy_manager.create_strategy('kdj_strategy', trend_params)
    
    result_trend = engine.backtest(
        data=data,
        strategy=trend_strategy,
        initial_capital=1000000,
        commission_rate=0.0003
    )
    
    results['trend'] = result_trend
    
    print(f"\n趋势模式结果:")
    print(f"  总收益率: {result_trend['total_return']:.2f}%")
    print(f"  交易次数: {result_trend['total_trades']}笔")
    print(f"  胜率: {result_trend['win_rate']:.2f}%")
    print(f"  最大回撤: {result_trend['max_drawdown']:.2f}%")
    
    # 对比分析
    print("\n" + "=" * 70)
    print("📊 模式对比分析")
    print("=" * 70)
    
    print("\n| 指标         | 短线模式    | 趋势模式    | 优势模式 |")
    print("|--------------|-------------|-------------|----------|")
    
    metrics = [
        ('总收益率', 'total_return', '%'),
        ('交易次数', 'total_trades', '笔'),
        ('胜率', 'win_rate', '%'),
        ('最大回撤', 'max_drawdown', '%'),
        ('夏普比率', 'sharpe_ratio', ''),
    ]
    
    for name, key, unit in metrics:
        swing_val = results['swing'][key]
        trend_val = results['trend'][key]
        
        # 判断优势模式
        if key == 'max_drawdown':
            better = '短线' if swing_val < trend_val else '趋势'
        else:
            better = '短线' if swing_val > trend_val else '趋势'
        
        print(f"| {name:<12} | {swing_val:>10.2f}{unit} | {trend_val:>10.2f}{unit} | {better:^8} |")
    
    # 建议
    print("\n💡 策略建议:")
    
    if results['swing']['total_return'] > results['trend']['total_return']:
        print("  ✅ 短线模式表现更好 - 适合波动市场,快进快出")
        print("     特点: 利用压力位止盈,降低回撤风险")
    else:
        print("  ✅ 趋势模式表现更好 - 适合单边行情,吃透趋势")
        print("     特点: 不设压力位止盈,追求更大波段利润")
    
    print("\n" + "=" * 70)

if __name__ == '__main__':
    test_kdj_modes()
