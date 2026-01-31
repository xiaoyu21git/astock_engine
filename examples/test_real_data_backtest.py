"""
真实数据回测测试
使用AkShare获取真实历史数据进行策略回测
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from datetime import datetime, timedelta

from astock_engine.data.data_provider import DataManager, AkShareProvider
from astock_engine.strategies.plugin_manager import StrategyPluginManager
from astock_engine.backtest.backtest_engine import BacktestEngine, BacktestConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)


def main():
    print("\n" + "="*70)
    print("真实数据回测测试".center(70))
    print("="*70 + "\n")
    
    # 1. 初始化数据管理器
    print("📊 初始化数据管理器...")
    try:
        data_manager = DataManager()
        print("✅ 数据管理器初始化成功（使用AkShare）")
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        print("提示: 请运行 pip install akshare")
        return
    
    # 2. 选择股票
    symbols = [
        '600519.SH',  # 贵州茅台
        '000858.SZ',  # 五粮液
        '002475.SZ',  # 立讯精密
    ]
    
    print(f"\n📈 选择股票: {symbols}")
    
    # 3. 获取历史数据（最近2年）
    print(f"\n⏳ 获取历史数据（最近2年）...")
    
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')
    
    print(f"   时间范围: {start_date} 至 {end_date}")
    
    data = data_manager.get_stock_data(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date
    )
    
    if not data:
        print("❌ 未获取到数据")
        return
    
    print(f"\n✅ 数据获取成功:")
    for symbol, df in data.items():
        print(f"   {symbol}: {len(df)}条数据, "
              f"{df.index[0].strftime('%Y-%m-%d')} 至 {df.index[-1].strftime('%Y-%m-%d')}")
    
    # 4. 数据质量检查
    print(f"\n🔍 数据质量检查...")
    if data_manager.validate_data(data):
        print("✅ 数据质量检查通过")
    else:
        print("⚠️ 数据质量存在问题")
    
    # 5. 加载策略
    print(f"\n📦 加载策略...")
    manager = StrategyPluginManager()
    manager.scan_plugins()
    
    # 测试多个策略
    strategies_to_test = [
        ('rsi_strategy', 'RSI超买超卖策略'),
        ('macd_strategy', 'MACD趋势策略'),
        ('bollinger_bands_strategy', '布林带均值回归策略')
    ]
    
    print(f"✅ 准备测试 {len(strategies_to_test)} 个策略\n")
    
    # 6. 回测配置
    config = BacktestConfig(
        initial_capital=1_000_000,
        commission_rate=0.0003,
        slippage_rate=0.0005,
        stop_loss=-0.05,
        take_profit=0.20
    )
    
    results_summary = []
    
    # 7. 逐个测试策略
    for strategy_id, strategy_name in strategies_to_test:
        print("="*70)
        print(f"{strategy_name} 回测".center(70))
        print("="*70 + "\n")
        
        try:
            # 创建策略实例
            strategy = manager.create_strategy(strategy_id)
            
            # 创建回测引擎
            engine = BacktestEngine(config=config, enable_risk_control=True)
            
            # 运行回测
            print(f"⏳ 回测中...\n")
            results = engine.run(strategy, data)
            
            # 显示结果
            print(f"\n📊 回测结果:")
            print(f"   总收益率: {results.total_return:.2%}")
            print(f"   年化收益率: {results.annual_return:.2%}")
            print(f"   最大回撤: {results.max_drawdown:.2%}")
            print(f"   夏普比率: {results.sharpe_ratio:.2f}")
            print(f"   交易次数: {results.num_trades}笔")
            print(f"   胜率: {results.win_rate:.2%}")
            print(f"   盈亏比: {results.profit_factor:.2f}")
            print(f"   最终资产: ¥{results.final_value:,.2f}")
            
            # 交易记录
            if engine.trades:
                print(f"\n📋 交易记录（前5笔）:")
                for i, trade in enumerate(engine.trades[:5], 1):
                    action = "买入" if trade.action == 'BUY' else "卖出"
                    pnl_str = f"盈亏={trade.pnl:+,.2f}" if trade.pnl != 0 else ""
                    print(f"   {i}. {trade.timestamp.strftime('%Y-%m-%d')}: "
                          f"{action} {trade.symbol} @ {trade.price:.2f} × {trade.quantity} {pnl_str}")
            
            # 保存结果
            results_summary.append({
                'strategy': strategy_name,
                'return': results.total_return,
                'annual_return': results.annual_return,
                'sharpe': results.sharpe_ratio,
                'max_drawdown': results.max_drawdown,
                'trades': results.num_trades,
                'win_rate': results.win_rate,
                'final_value': results.final_value
            })
            
            print(f"\n")
            
        except Exception as e:
            print(f"❌ 回测失败: {e}\n")
            import traceback
            traceback.print_exc()
    
    # 8. 策略对比
    print("="*70)
    print("策略对比汇总".center(70))
    print("="*70 + "\n")
    
    if results_summary:
        # 按收益率排序
        results_summary.sort(key=lambda x: x['return'], reverse=True)
        
        print(f"{'策略':<25} {'收益率':<12} {'年化':<12} {'夏普':<8} {'回撤':<12} {'交易':<8}")
        print("-"*70)
        
        for r in results_summary:
            print(f"{r['strategy']:<20} {r['return']:>10.2%} {r['annual_return']:>10.2%} "
                  f"{r['sharpe']:>6.2f} {r['max_drawdown']:>10.2%} {r['trades']:>6}笔")
        
        print("\n🏆 最佳策略:")
        best = results_summary[0]
        print(f"   {best['strategy']}: 收益{best['return']:.2%}, "
              f"夏普{best['sharpe']:.2f}, 最终资产¥{best['final_value']:,.2f}")
    
    print("\n" + "="*70 + "\n")


if __name__ == '__main__':
    main()
