"""
测试RSI策略回测
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from astock_engine.strategies.plugin_manager import get_plugin_manager
from astock_engine.backtest.backtest_engine import BacktestEngine, BacktestConfig
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def generate_mock_data(symbols: list, days: int = 252) -> dict:
    """生成模拟数据（震荡行情，适合RSI策略）"""
    data = {}
    
    for symbol in symbols:
        dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
        
        # 生成震荡行情（周期性波动）
        base_price = np.random.uniform(20, 100)
        
        # 创建震荡行情：正弦波 + 随机噪声
        t = np.arange(days)
        cycle_period = np.random.uniform(20, 40)  # 震荡周期
        trend = np.sin(2 * np.pi * t / cycle_period) * base_price * 0.15  # 振幅15%
        noise = np.random.normal(0, base_price * 0.02, days)  # 噪声2%
        
        prices = base_price + trend + noise
        prices = np.maximum(prices, base_price * 0.5)  # 防止负值
        
        df = pd.DataFrame({
            'open': prices * np.random.uniform(0.99, 1.01, days),
            'high': prices * np.random.uniform(1.0, 1.02, days),
            'low': prices * np.random.uniform(0.98, 1.0, days),
            'close': prices,
            'volume': np.random.randint(1000000, 10000000, days)
        }, index=dates)
        
        data[symbol] = df
    
    logger.info(f"生成模拟数据: {len(symbols)}只股票, {days}个交易日（震荡行情）")
    return data


def main():
    print("\n" + "="*80)
    print("RSI策略回测测试")
    print("="*80 + "\n")
    
    # 1. 加载RSI策略插件
    logger.info("1️⃣  加载RSI策略插件...")
    manager = get_plugin_manager()
    manager.scan_plugins()
    
    rsi_strategy = manager.create_strategy('rsi_strategy', params={
        'rsi_period': 14,
        'oversold': 30,
        'overbought': 70,
        'initial_capital': 1000000
    })
    
    print(f"✅ 策略加载: {rsi_strategy.name}")
    print(f"   RSI周期: {rsi_strategy.rsi_period}")
    print(f"   超卖线: {rsi_strategy.oversold}")
    print(f"   超买线: {rsi_strategy.overbought}\n")
    
    # 2. 生成测试数据
    logger.info("2️⃣  生成测试数据...")
    symbols = ['600000.SH', '000001.SZ', '000002.SZ']
    data = generate_mock_data(symbols, days=252)  # 1年数据
    
    # 3. 配置回测
    logger.info("3️⃣  配置回测引擎...")
    config = BacktestConfig(
        initial_capital=1000000,
        commission_rate=0.0003,
        slippage_rate=0.001,
        max_position_size=0.3,
        max_positions=3
    )
    
    engine = BacktestEngine(config)
    
    # 4. 运行回测
    print("\n" + "-"*80)
    logger.info("4️⃣  开始回测...")
    print("-"*80 + "\n")
    
    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    metrics = engine.run(
        strategy=rsi_strategy,
        data=data,
        start_date=start_date,
        end_date=end_date
    )
    
    # 5. 输出结果
    print("\n" + "="*80)
    print("回测结果")
    print("="*80)
    
    print(f"\n📊 收益指标:")
    print(f"  初始资金:     ¥{config.initial_capital:,.2f}")
    print(f"  最终资产:     ¥{metrics.final_value:,.2f}")
    print(f"  总收益率:     {metrics.total_return:+.2%}")
    print(f"  年化收益率:   {metrics.annual_return:+.2%}")
    
    print(f"\n📉 风险指标:")
    print(f"  最大回撤:     {metrics.max_drawdown:.2%}")
    print(f"  波动率:       {metrics.volatility:.2%}")
    print(f"  夏普比率:     {metrics.sharpe_ratio:.2f}")
    print(f"  卡玛比率:     {metrics.calmar_ratio:.2f}")
    
    print(f"\n📈 交易指标:")
    print(f"  交易次数:     {metrics.num_trades}笔")
    print(f"  胜率:         {metrics.win_rate:.2%}")
    print(f"  盈亏比:       {metrics.profit_factor:.2f}")
    print(f"  平均盈利:     ¥{metrics.avg_win:,.2f}")
    print(f"  平均亏损:     ¥{metrics.avg_loss:,.2f}")
    
    print(f"\n⏱️  时间指标:")
    print(f"  交易天数:     {metrics.trading_days}天")
    
    # 6. 净值曲线
    print(f"\n📉 净值曲线（最近10天）:")
    equity_df = engine.get_equity_curve()
    print(equity_df.tail(10).to_string(index=False))
    
    # 7. 交易记录
    print(f"\n📋 交易记录（最近10笔）:")
    trades_df = engine.get_trades_df()
    if not trades_df.empty:
        print(trades_df.tail(10).to_string(index=False))
    
    # 8. 评估
    print("\n" + "="*80)
    print("策略评估")
    print("="*80)
    
    # 评分规则
    score = 0
    评级 = ""
    
    if metrics.sharpe_ratio > 2:
        score += 30
    elif metrics.sharpe_ratio > 1:
        score += 20
    elif metrics.sharpe_ratio > 0:
        score += 10
    
    if metrics.max_drawdown < 0.1:
        score += 25
    elif metrics.max_drawdown < 0.2:
        score += 15
    elif metrics.max_drawdown < 0.3:
        score += 5
    
    if metrics.win_rate > 0.6:
        score += 20
    elif metrics.win_rate > 0.5:
        score += 10
    
    if metrics.total_return > 0:
        score += 15
    
    if metrics.num_trades > 10:
        score += 10
    
    if score >= 80:
        评级 = "⭐⭐⭐⭐⭐ 优秀"
    elif score >= 60:
        评级 = "⭐⭐⭐⭐ 良好"
    elif score >= 40:
        评级 = "⭐⭐⭐ 合格"
    elif score >= 20:
        评级 = "⭐⭐ 待改进"
    else:
        评级 = "⭐ 不推荐"
    
    print(f"\n综合评分: {score}/100")
    print(f"策略评级: {评级}")
    
    print(f"\n建议:")
    if metrics.sharpe_ratio < 1:
        print("  ⚠️  夏普比率偏低，建议优化参数或增加过滤条件")
    if metrics.max_drawdown > 0.2:
        print("  ⚠️  回撤较大，建议添加止损机制")
    if metrics.win_rate < 0.5:
        print("  ⚠️  胜率偏低，考虑调整RSI阈值")
    if metrics.num_trades < 10:
        print("  ⚠️  交易次数过少，样本不足，需要更长周期验证")
    
    if score >= 60:
        print("  ✅ 策略表现符合预期，可进行样本外测试")
    
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    main()
