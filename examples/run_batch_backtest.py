#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量回测入口脚本

功能：
- 支持多只股票 × 多个策略，在统一配置下顺序回测
- 默认使用离线 Mock 数据，避免网络依赖
- 输出统一的回测结果表（控制台 + CSV 文件）

使用方式（在项目根目录）：

    G:/C++/AStockQuantEngine/.venv/Scripts/python.exe astock_engine/examples/run_batch_backtest.py

后续可以在此基础上逐步扩展为：
- 命令行参数/配置文件驱动
- 并行回测
- Web/GUI 调用入口
"""

import sys
from pathlib import Path
from datetime import datetime
import logging
from typing import List, Dict, Any

import pandas as pd

# 将项目根目录加入路径，便于作为脚本直接运行
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from astock_engine.data.data_provider import DataManager
from astock_engine.data.mock_data import MockDataManager
from astock_engine.strategies.plugin_manager import StrategyPluginManager
from astock_engine.backtest.backtest_engine import BacktestEngine, BacktestConfig, BacktestMetrics


# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


BANNER = r"""
    ___   _____ ________  ________ ____ 
   /   | / ___/_  __/ _ \/ ___/ //_/  /
  / /| | \__ \ / / / // / /__/ ,<    / 
 / ___ |___/ // / /____/\___/_/|_|  /  
/_/  |_/____//_/                   /_/  
                                        
    ASTOCK Quant Engine v0.1.0 - 批量回测入口
"""


def print_banner():
    print(BANNER)
    print()


def get_default_config() -> Dict[str, Any]:
    """返回一组默认的批量回测配置"""
    return {
        # 使用 Mock 离线数据，避免网络依赖
        'use_mock_data': True,

        # 回测标的（可以根据需要修改）
        'symbols': [
            '600519.SH',  # 贵州茅台（趋势+白马）
            '000333.SZ',  # 美的集团（趋势）
            '300750.SZ',  # 宁德时代（高成长、高波动）
            '600036.SH',  # 招商银行（典型震荡）
        ],

        # 使用的策略插件 ID（对应 strategies/plugins 下的目录名）
        'strategy_ids': [
            'kdj_strategy',       # KDJ 超买超卖策略
            'ma_crossover',       # 均线交叉策略
            'macd_strategy',      # MACD 趋势策略
            'volume_price',       # 量价关系策略（插件版）
        ],

        # 回测时间区间
        'start_date': '2024-01-01',
        'end_date': '2026-01-31',

        # 回测配置（可根据需要调整）
        'backtest_config': BacktestConfig(
            initial_capital=1_000_000,
            commission_rate=0.0003,
            slippage_rate=0.001,
            max_position_size=0.4,
            max_positions=5,
            stop_loss=-0.08,
            take_profit=None,
        ),

        # 结果保存路径
        'output_csv': project_root / 'batch_backtest_results.csv',
    }


def load_data(symbols: List[str], start_date: str, end_date: str, use_mock: bool):
    """根据配置加载数据（Mock 或 真实）"""
    if use_mock:
        logger.info("使用 MockDataManager 生成离线数据")
        manager = MockDataManager(seed=42)
        data = manager.get_stock_data(symbols, start_date=start_date, end_date=end_date)
    else:
        logger.info("使用 DataManager(akshare/tushare) 获取真实数据")
        manager = DataManager()
        data = manager.get_stock_data(symbols, start_date=start_date, end_date=end_date)

    if not data:
        logger.warning("未获取到任何标的数据，请检查配置")
    else:
        logger.info(f"成功获取 {len(data)} 只股票的数据")

    return data


def run_batch_backtest(config: Dict[str, Any]) -> pd.DataFrame:
    """执行批量回测，返回结果 DataFrame"""
    symbols: List[str] = config['symbols']
    strategy_ids: List[str] = config['strategy_ids']
    start_date: str = config['start_date']
    end_date: str = config['end_date']
    backtest_config: BacktestConfig = config['backtest_config']
    use_mock: bool = config['use_mock_data']

    # 1. 数据准备
    data_all = load_data(symbols, start_date, end_date, use_mock=use_mock)
    if not data_all:
        return pd.DataFrame()

    # 2. 策略插件加载
    plugin_manager = StrategyPluginManager()
    plugin_manager.scan_plugins()

    # 验证策略是否存在
    missing = [sid for sid in strategy_ids if sid not in plugin_manager.plugins]
    if missing:
        logger.warning(f"以下策略插件未找到，将被跳过: {missing}")
        strategy_ids = [sid for sid in strategy_ids if sid in plugin_manager.plugins]

    if not strategy_ids:
        logger.error("没有可用的策略插件，无法执行回测")
        return pd.DataFrame()

    # 3. 批量回测
    results = []
    total_tasks = len(symbols) * len(strategy_ids)
    task_idx = 0

    start_ts = datetime.now()

    for strategy_id in strategy_ids:
        plugin = plugin_manager.plugins[strategy_id]
        logger.info(f"===== 策略: {plugin.metadata.name} ({strategy_id}) =====")

        for symbol in symbols:
            task_idx += 1
            if symbol not in data_all:
                logger.warning(f"{symbol} 无数据，跳过")
                continue

            logger.info(f"[{task_idx}/{total_tasks}] 回测 {symbol} with {strategy_id}")

            # 为每个策略×标的组合创建独立的策略实例和回测引擎
            strategy = plugin.create_instance(params=None)
            engine = BacktestEngine(config=backtest_config, enable_risk_control=True)

            metrics: BacktestMetrics = engine.run(
                strategy=strategy,
                data={symbol: data_all[symbol]},
                start_date=start_date,
                end_date=end_date,
            )

            results.append({
                'symbol': symbol,
                'strategy_id': strategy_id,
                'strategy_name': plugin.metadata.name,
                'total_return': metrics.total_return,
                'annual_return': metrics.annual_return,
                'max_drawdown': metrics.max_drawdown,
                'sharpe_ratio': metrics.sharpe_ratio,
                'num_trades': metrics.num_trades,
                'win_rate': metrics.win_rate,
                'final_value': metrics.final_value,
                'trading_days': metrics.trading_days,
            })

    end_ts = datetime.now()
    elapsed = (end_ts - start_ts).total_seconds()

    if not results:
        logger.warning("没有产生任何回测结果")
        return pd.DataFrame()

    df_result = pd.DataFrame(results)
    df_result.sort_values(by=['strategy_id', 'symbol'], inplace=True)

    logger.info("===== 批量回测完成 =====")
    logger.info(f"任务总数: {total_tasks}, 实际回测: {len(df_result)}")
    logger.info(f"总耗时: {elapsed:.2f} 秒")

    return df_result


def save_and_print_results(df_result: pd.DataFrame, output_path: Path):
    """保存结果为 CSV，并在控制台打印简要汇总"""
    if df_result.empty:
        print("无回测结果可展示")
        return

    # 保存到 CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_result.to_csv(output_path, index=False, encoding='utf-8-sig')

    print("\n回测结果已保存至:")
    print(f"  {output_path}")
    print()

    # 打印按策略聚合的统计
    grouped = df_result.groupby('strategy_name').agg({
        'annual_return': 'mean',
        'max_drawdown': 'mean',
        'sharpe_ratio': 'mean',
        'num_trades': 'mean',
        'win_rate': 'mean',
    }).reset_index()

    print("按策略汇总表现:")
    print(grouped.to_string(index=False, formatters={
        'annual_return': '{:.2%}'.format,
        'max_drawdown': '{:.2%}'.format,
        'sharpe_ratio': '{:.2f}'.format,
        'win_rate': '{:.2%}'.format,
        'num_trades': '{:.1f}'.format,
    }))

    print("\n详细结果（前几行）:")
    display_cols = [
        'symbol', 'strategy_name', 'total_return', 'annual_return',
        'max_drawdown', 'sharpe_ratio', 'num_trades', 'win_rate', 'final_value'
    ]
    head = df_result[display_cols].copy()
    for col in ['total_return', 'annual_return', 'max_drawdown', 'win_rate']:
        head[col] = head[col].map(lambda x: f"{x:.2%}")
    head['sharpe_ratio'] = head['sharpe_ratio'].map(lambda x: f"{x:.2f}")
    print(head.head().to_string(index=False))


if __name__ == '__main__':
    print_banner()
    cfg = get_default_config()
    df_res = run_batch_backtest(cfg)
    save_and_print_results(df_res, cfg['output_csv'])
