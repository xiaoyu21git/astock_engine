#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
单股票回测测试脚本
支持用户指定股票代码进行回测
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timedelta
from astock_engine.data.data_provider import DataManager
from astock_engine.strategies.plugin_manager import StrategyPluginManager
from astock_engine.backtest.backtest_engine import BacktestEngine, BacktestConfig
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ASTOCK量化引擎标识
BANNER = """
    ___   _____ ________  ________ ____ 
   /   | / ___/_  __/ _ \/ ___/ //_/  /
  / /| | \__ \ / / / // / /__/ ,<    / 
 / ___ |___/ // / /____/\___/_/|_|  /  
/_/  |_/____//_/                   /_/  
                                        
    ASTOCK Quant Engine v0.1.0 - 单股票回测
"""


def print_banner():
    """打印横幅"""
    print(BANNER)
    print()


def get_stock_input():
    """获取用户输入的股票代码"""
    print("=" * 70)
    print("                        股票选择")
    print("=" * 70)
    print()
    print("💡 股票代码格式说明:")
    print("   上海: 600519.SH (如: 贵州茅台)")
    print("   深圳: 000858.SZ (如: 五粮液)")
    print("   深圳: 002475.SZ (如: 立讯精密)")
    print()
    print("📋 热门股票参考:")
    print("   600519.SH - 贵州茅台")
    print("   000858.SZ - 五粮液")
    print("   600036.SH - 招商银行")
    print("   000001.SZ - 平安银行")
    print("   601318.SH - 中国平安")
    print("   002475.SZ - 立讯精密")
    print("   000333.SZ - 美的集团")
    print("   300750.SZ - 宁德时代")
    print()
    
    while True:
        symbol = input("请输入股票代码 (或输入 q 退出): ").strip().upper()
        
        if symbol.lower() == 'q':
            print("👋 再见！")
            sys.exit(0)
        
        # 验证格式
        if not symbol:
            print("❌ 股票代码不能为空，请重新输入")
            continue
        
        # 自动补全后缀
        if '.' not in symbol:
            if symbol.startswith('6'):
                symbol = symbol + '.SH'
                print(f"   自动识别为上海股票: {symbol}")
            elif symbol.startswith('0') or symbol.startswith('3'):
                symbol = symbol + '.SZ'
                print(f"   自动识别为深圳股票: {symbol}")
            else:
                print("❌ 无法识别的股票代码格式")
                continue
        
        return symbol


def get_strategy_input():
    """获取用户选择的策略"""
    print()
    print("=" * 70)
    print("                        策略选择")
    print("=" * 70)
    print()
    print("可用策略:")
    print("  1. RSI超买超卖策略 (均值回归)")
    print("  2. MACD趋势策略 (趋势跟踪)")
    print("  3. 布林带均值回归策略 (超卖反弹)")
    print("  4. 测试全部策略")
    print()
    
    strategies = {
        '1': 'rsi_strategy',
        '2': 'macd_strategy',
        '3': 'bollinger_bands_strategy',
        '4': 'all'
    }
    
    while True:
        choice = input("请选择策略 (1/2/3/4): ").strip()
        
        if choice in strategies:
            return strategies[choice]
        else:
            print("❌ 无效选择，请输入 1-4")


def get_date_range():
    """获取回测时间范围"""
    print()
    print("=" * 70)
    print("                        时间范围")
    print("=" * 70)
    print()
    print("可选时间范围:")
    print("  1. 最近3个月")
    print("  2. 最近6个月")
    print("  3. 最近1年")
    print("  4. 最近2年 (推荐)")
    print("  5. 自定义")
    print()
    
    while True:
        choice = input("请选择时间范围 (1/2/3/4/5): ").strip()
        
        end_date = datetime.now()
        
        if choice == '1':
            start_date = end_date - timedelta(days=90)
            break
        elif choice == '2':
            start_date = end_date - timedelta(days=180)
            break
        elif choice == '3':
            start_date = end_date - timedelta(days=365)
            break
        elif choice == '4':
            start_date = end_date - timedelta(days=730)
            break
        elif choice == '5':
            print("请输入开始日期 (格式: YYYY-MM-DD):")
            start_str = input("> ").strip()
            try:
                start_date = datetime.strptime(start_str, '%Y-%m-%d')
                break
            except ValueError:
                print("❌ 日期格式错误，请使用 YYYY-MM-DD 格式")
                continue
        else:
            print("❌ 无效选择，请输入 1-5")
            continue
    
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')


def run_backtest(symbol, strategy_id, data, strategy_name):
    """运行单个策略回测"""
    print()
    print("=" * 70)
    print(f"                     {strategy_name} 回测")
    print("=" * 70)
    print()
    
    # 创建策略实例
    plugin_manager = StrategyPluginManager()
    
    # 先扫描加载所有插件
    plugin_manager.scan_plugins()
    
    strategy = plugin_manager.create_strategy(strategy_id)
    
    if not strategy:
        print(f"❌ 策略 {strategy_id} 加载失败")
        return None
    
    # 配置回测引擎
    config = BacktestConfig(
        initial_capital=1_000_000,      # 100万初始资金
        commission_rate=0.0003,          # 万3手续费
        slippage_rate=0.001,             # 0.1%滑点
        stop_loss=-0.05,                 # -5%止损
        take_profit=0.20,                # +20%止盈
        max_position_size=0.30,          # 单股最大30%
        max_positions=10                 # 最多10个持仓
    )
    
    # 创建回测引擎（开启风控）
    engine = BacktestEngine(config, enable_risk_control=True)
    
    print("⏳ 回测中...\n")
    
    # 运行回测
    try:
        results = engine.run(strategy, data)
        
        # 打印结果
        print("📊 回测结果:")
        print(f"   总收益率: {results.total_return:.2%}")
        print(f"   年化收益率: {results.annual_return:.2%}")
        print(f"   最大回撤: {results.max_drawdown:.2%}")
        print(f"   夏普比率: {results.sharpe_ratio:.2f}")
        print(f"   交易次数: {results.num_trades}笔")
        print(f"   胜率: {results.win_rate:.2%}")
        print(f"   盈亏比: {results.profit_factor:.2f}")
        print(f"   最终资产: ¥{results.final_value:,.2f}")
        print()
        
        return results
        
    except Exception as e:
        print(f"❌ 回测失败: {str(e)}")
        logger.exception("回测异常")
        return None


def main():
    """主函数"""
    print_banner()
    
    # 1. 获取股票代码
    symbol = get_stock_input()
    
    # 2. 获取策略选择
    strategy_choice = get_strategy_input()
    
    # 3. 获取时间范围
    start_date, end_date = get_date_range()
    
    print()
    print("=" * 70)
    print("                        数据获取")
    print("=" * 70)
    print()
    
    # 4. 初始化数据管理器
    print("📊 初始化数据管理器...")
    data_manager = DataManager()
    print("✅ 数据管理器初始化成功（使用AkShare）")
    print()
    
    # 5. 获取历史数据
    print(f"📈 股票: {symbol}")
    print(f"⏳ 获取历史数据...")
    print(f"   时间范围: {start_date} 至 {end_date}")
    
    try:
        data = data_manager.get_stock_data(
            symbols=[symbol],
            start_date=start_date,
            end_date=end_date
        )
        
        if not data or symbol not in data:
            print(f"❌ 无法获取股票 {symbol} 的数据")
            print("   可能原因:")
            print("   1. 股票代码错误")
            print("   2. 该时间段无交易数据")
            print("   3. 网络连接问题")
            return
        
        df = data[symbol]
        print(f"✅ 数据获取成功: {len(df)}条数据")
        print(f"   时间范围: {df.index[0].strftime('%Y-%m-%d')} 至 {df.index[-1].strftime('%Y-%m-%d')}")
        print()
        
        # 显示股票基本信息
        print("📈 股票行情概览:")
        print(f"   最新价格: ¥{df['close'].iloc[-1]:.2f}")
        print(f"   期间涨跌: {(df['close'].iloc[-1] / df['close'].iloc[0] - 1):.2%}")
        print(f"   最高价: ¥{df['high'].max():.2f}")
        print(f"   最低价: ¥{df['low'].min():.2f}")
        print()
        
    except Exception as e:
        print(f"❌ 数据获取失败: {str(e)}")
        logger.exception("数据获取异常")
        return
    
    # 6. 运行回测
    if strategy_choice == 'all':
        # 测试所有策略
        strategies = [
            ('rsi_strategy', 'RSI超买超卖策略'),
            ('macd_strategy', 'MACD趋势策略'),
            ('bollinger_bands_strategy', '布林带均值回归策略')
        ]
        
        all_results = []
        
        for strategy_id, strategy_name in strategies:
            result = run_backtest(symbol, strategy_id, data, strategy_name)
            if result:
                all_results.append((strategy_name, result))
        
        # 策略对比
        if len(all_results) > 1:
            print()
            print("=" * 70)
            print("                        策略对比汇总")
            print("=" * 70)
            print()
            print(f"{'策略':<20} {'收益率':>10} {'年化':>10} {'夏普':>8} "
                  f"{'回撤':>10} {'交易':>8}")
            print("-" * 70)
            
            # 按收益率排序
            all_results.sort(key=lambda x: x[1].total_return, reverse=True)
            
            for name, result in all_results:
                print(f"{name:<20} "
                      f"{result.total_return:>9.2%} "
                      f"{result.annual_return:>9.2%} "
                      f"{result.sharpe_ratio:>7.2f} "
                      f"{result.max_drawdown:>9.2%} "
                      f"{result.num_trades:>6}笔")
            
            print()
            best_name, best_result = all_results[0]
            print(f"🏆 最佳策略:")
            print(f"   {best_name}: 收益{best_result.total_return:.2%}, "
                  f"夏普{best_result.sharpe_ratio:.2f}, "
                  f"最终资产¥{best_result.final_value:,.2f}")
            print()
    
    else:
        # 单个策略回测
        strategy_names = {
            'rsi_strategy': 'RSI超买超卖策略',
            'macd_strategy': 'MACD趋势策略',
            'bollinger_bands_strategy': '布林带均值回归策略'
        }
        
        strategy_name = strategy_names.get(strategy_choice, strategy_choice)
        run_backtest(symbol, strategy_choice, data, strategy_name)
    
    print("=" * 70)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 用户中断，再见！")
    except Exception as e:
        print(f"\n❌ 程序异常: {str(e)}")
        logger.exception("程序异常")
