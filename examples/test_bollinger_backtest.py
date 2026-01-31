"""
布林带策略回测测试
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

from astock_engine.strategies.plugin_manager import StrategyPluginManager
from astock_engine.backtest.backtest_engine import BacktestEngine, BacktestConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)


def generate_oscillating_data(days=800, symbols=['600519.SH', '000858.SZ', '002475.SZ']):
    """
    生成震荡行情数据（横盘整理+宽幅震荡）
    适合测试布林带策略
    """
    np.random.seed(42)
    
    data = {}
    start_date = datetime.now() - timedelta(days=days)
    dates = pd.date_range(start=start_date, periods=days, freq='D')
    
    for symbol in symbols:
        base_price = np.random.uniform(30, 80)
        
        # 整体横盘（小幅上升）
        trend = np.linspace(0, base_price * 0.15, days)  # 15%整体涨幅
        
        # 多周期震荡（宽幅震荡）
        t = np.arange(days)
        
        # 主周期：40天
        cycle1 = np.sin(2 * np.pi * t / 40) * base_price * 0.12
        
        # 次周期：60天
        cycle2 = np.sin(2 * np.pi * t / 60 + np.pi/4) * base_price * 0.08
        
        # 短周期：15天（制造快速波动）
        cycle3 = np.sin(2 * np.pi * t / 15) * base_price * 0.05
        
        # 随机波动
        noise = np.random.normal(0, base_price * 0.015, days)
        
        # 合成价格
        prices = base_price + trend + cycle1 + cycle2 + cycle3 + noise
        prices = np.maximum(prices, base_price * 0.7)  # 避免价格过低
        
        df = pd.DataFrame({
            'symbol': symbol,
            'open': prices * (1 + np.random.uniform(-0.01, 0.01, days)),
            'high': prices * (1 + np.random.uniform(0, 0.02, days)),
            'low': prices * (1 - np.random.uniform(0, 0.02, days)),
            'close': prices,
            'volume': np.random.randint(1000000, 10000000, days)
        }, index=dates)
        
        data[symbol] = df
    
    return data


def evaluate_strategy(results: dict) -> dict:
    """评估策略表现"""
    sharpe_ratio = results['sharpe_ratio']
    max_drawdown = results['max_drawdown']
    total_return = results['total_return']
    win_rate = results['win_rate']
    num_trades = results['trade_count']
    profit_factor = results.get('profit_factor', 0)
    
    # 综合评分
    score = 0
    
    # 夏普比率（30分）
    if sharpe_ratio > 2:
        score += 30
    elif sharpe_ratio > 1.5:
        score += 25
    elif sharpe_ratio > 1:
        score += 20
    elif sharpe_ratio > 0.5:
        score += 10
    elif sharpe_ratio > 0:
        score += 5
    
    # 最大回撤（25分）
    if max_drawdown < 0.1:
        score += 25
    elif max_drawdown < 0.15:
        score += 20
    elif max_drawdown < 0.2:
        score += 15
    elif max_drawdown < 0.3:
        score += 10
    elif max_drawdown < 0.4:
        score += 5
    
    # 胜率（20分）
    if win_rate > 0.7:
        score += 20
    elif win_rate > 0.6:
        score += 15
    elif win_rate > 0.5:
        score += 10
    elif win_rate > 0.4:
        score += 5
    
    # 总收益率（15分）
    if total_return > 0.5:
        score += 15
    elif total_return > 0.3:
        score += 12
    elif total_return > 0.2:
        score += 10
    elif total_return > 0.1:
        score += 7
    elif total_return > 0:
        score += 3
    
    # 交易次数（10分）- 布林带策略适中频率
    if 20 <= num_trades <= 60:
        score += 10
    elif 15 <= num_trades < 20 or 60 < num_trades <= 80:
        score += 7
    elif 10 <= num_trades < 15 or 80 < num_trades <= 100:
        score += 5
    elif num_trades >= 10:
        score += 2
    
    # 评级
    if score >= 80:
        rating = "⭐⭐⭐⭐⭐ 优秀"
    elif score >= 60:
        rating = "⭐⭐⭐⭐ 良好"
    elif score >= 40:
        rating = "⭐⭐⭐ 合格"
    elif score >= 20:
        rating = "⭐⭐ 待改进"
    else:
        rating = "⭐ 不推荐"
    
    # 生成建议
    suggestions = []
    if sharpe_ratio < 1:
        suggestions.append("⚠️ 夏普比率偏低，建议优化参数或增加过滤条件")
    if max_drawdown > 0.15:
        suggestions.append("⚠️ 最大回撤较大，建议加强风控（止损/仓位管理）")
    if win_rate < 0.5:
        suggestions.append("⚠️ 胜率低于50%，需检查入场时机")
    if num_trades < 10:
        suggestions.append("⚠️ 交易次数过少，需更长周期验证")
    if num_trades > 100:
        suggestions.append("⚠️ 交易过于频繁，可能产生过多手续费")
    if total_return < 0:
        suggestions.append("❌ 策略整体亏损，不建议实盘使用")
    if profit_factor < 1.5 and profit_factor > 0:
        suggestions.append("⚠️ 盈亏比偏低，建议优化止盈止损策略")
    
    if score >= 60:
        suggestions.append("✅ 策略表现良好，可进行样本外测试")
    
    return {
        'score': score,
        'rating': rating,
        'suggestions': suggestions
    }


def main():
    print("\n" + "="*60)
    print("布林带均值回归策略回测".center(60))
    print("="*60 + "\n")
    
    # 1. 生成震荡数据
    print("📊 生成震荡行情数据...")
    data = generate_oscillating_data(days=800, symbols=['600519.SH', '000858.SZ', '002475.SZ'])
    print(f"✅ 生成数据完成: {len(data)}只股票, {len(list(data.values())[0])}个交易日")
    
    # 2. 加载布林带策略
    print("\n📦 加载布林带策略插件...")
    manager = StrategyPluginManager()
    loaded = manager.scan_plugins()
    print(f"✅ 扫描完成，加载了 {loaded} 个插件")
    
    plugin = manager.get_plugin('bollinger_bands_strategy')
    if not plugin:
        print("❌ 未找到布林带策略插件")
        return
    
    print(f"✅ 加载成功: {plugin.metadata.name} v{plugin.metadata.version}")
    print(f"   参数: 周期={plugin.metadata.parameters['period']['default']}, "
          f"标准差={plugin.metadata.parameters['std_dev']['default']}")
    
    # 3. 创建策略实例
    strategy = manager.create_strategy('bollinger_bands_strategy')
    
    # 4. 初始化回测引擎
    print("\n🚀 初始化回测引擎...")
    config = BacktestConfig(
        initial_capital=1_000_000,
        commission_rate=0.0003,
        slippage_rate=0.0005
    )
    engine = BacktestEngine(config=config)
    
    # 5. 运行回测
    print("\n⏳ 开始回测...\n")
    results = engine.run(strategy, data)
    
    # 6. 显示结果
    print("\n" + "="*60)
    print("回测结果".center(60))
    print("="*60 + "\n")
    
    print(f"📊 收益指标:")
    print(f"   初始资金: ¥{config.initial_capital:,.2f}")
    print(f"   最终资产: ¥{results.final_value:,.2f}")
    print(f"   总收益率: {results.total_return:.2%}")
    print(f"   年化收益率: {results.annual_return:.2%}")
    
    print(f"\n📉 风险指标:")
    print(f"   最大回撤: {results.max_drawdown:.2%}")
    print(f"   波动率: {results.volatility:.2%}")
    print(f"   夏普比率: {results.sharpe_ratio:.2f}")
    print(f"   卡玛比率: {results.calmar_ratio:.2f}")
    
    print(f"\n📈 交易指标:")
    print(f"   交易次数: {results.num_trades}笔")
    print(f"   胜率: {results.win_rate:.2%}")
    print(f"   盈亏比: {results.profit_factor:.2f}")
    print(f"   平均持仓天数: {results.avg_holding_period:.1f}天")
    
    # 7. 交易记录
    if engine.trades:
        print(f"\n📋 交易记录（前10笔）:")
        for i, trade in enumerate(engine.trades[:10], 1):
            action = "买入" if trade.action == 'BUY' else "卖出"
            pnl_str = f"盈亏={trade.pnl:+.2f}" if trade.pnl != 0 else ""
            print(f"   {i}. {trade.timestamp.strftime('%Y-%m-%d')}: "
                  f"{action} {trade.symbol} @ {trade.price:.2f} × {trade.quantity} {pnl_str}")
    
    # 8. 策略评估
    print("\n" + "="*60)
    print("策略评估".center(60))
    print("="*60 + "\n")
    
    results_dict = {
        'sharpe_ratio': results.sharpe_ratio,
        'max_drawdown': results.max_drawdown,
        'total_return': results.total_return,
        'win_rate': results.win_rate,
        'trade_count': results.num_trades,
        'profit_factor': results.profit_factor
    }
    
    evaluation = evaluate_strategy(results_dict)
    
    print(f"综合评分: {evaluation['score']}/100")
    print(f"策略评级: {evaluation['rating']}")
    
    print(f"\n改进建议:")
    for suggestion in evaluation['suggestions']:
        print(f"  {suggestion}")
    
    print("\n" + "="*60 + "\n")


if __name__ == '__main__':
    main()
