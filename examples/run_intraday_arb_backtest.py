#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""日内套利策略模板回测示例（分钟级 + T0/T1）

功能：
- 使用 MockDataManager 生成 1 分钟级别的模拟行情数据；
- 通过策略插件管理器加载 intraday_arb 插件策略；
- 在 BacktestEngine 上执行回测，观察日内 + T0/T1 行为的效果。

运行方式（在项目根目录）：

    G:/C++/AStockQuantEngine/.venv/Scripts/python.exe \
        astock_engine/examples/run_intraday_arb_backtest.py

可根据需要修改 SYMBOLS、日期、t_mode 等参数。
"""

import sys
from pathlib import Path
from datetime import datetime
import logging
from typing import Dict, Any, List

import pandas as pd

# 将项目根目录加入路径，便于作为脚本直接运行
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from astock_engine.data.mock_data import MockDataManager
from astock_engine.strategies.plugin_manager import StrategyPluginManager
from astock_engine.backtest.backtest_engine import BacktestEngine, BacktestConfig, BacktestMetrics


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


SYMBOLS: List[str] = [
    "300750.SZ",  # 新能源 / 电池
    "600519.SH",  # 白酒 / 高端消费
]

START_DATE = "2024-01-02"
END_DATE = "2024-01-10"


def load_intraday_data(symbols: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
    """使用 MockDataManager 生成分钟级模拟行情。"""
    manager = MockDataManager(seed=42)
    data = manager.get_stock_data(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        frequency="1min",
    )
    logger.info("生成分钟级模拟数据: %d 只标的", len(data))
    return data


def build_backtest_config() -> BacktestConfig:
    """构建一份适合日内策略的回测配置。"""
    return BacktestConfig(
        initial_capital=1_000_000,
        commission_rate=0.0003,
        slippage_rate=0.001,
        max_position_size=0.4,
        max_positions=4,
        stop_loss=-0.06,
        take_profit=None,
    )


def run_intraday_arb_backtest() -> BacktestMetrics:
    # 1. 加载分钟级 Mock 数据
    data = load_intraday_data(SYMBOLS, START_DATE, END_DATE)
    if not data:
        raise SystemExit("未能生成分钟级数据，请检查配置")

    # 2. 加载 intraday_arb 插件策略
    manager = StrategyPluginManager()
    manager.scan_plugins()

    plugin_id = "intraday_arb"
    if plugin_id not in manager.plugins:
        raise SystemExit(f"未找到插件策略 {plugin_id}, 请确认 strategies/plugins/{plugin_id} 存在")

    plugin = manager.plugins[plugin_id]

    # 日内套利 + T0/T1 组合模式
    strategy = plugin.create_instance(params={"t_mode": "T0_T1"})

    # 3. 构建回测引擎并运行
    config = build_backtest_config()
    engine = BacktestEngine(config=config, enable_risk_control=True)

    metrics: BacktestMetrics = engine.run(
        strategy=strategy,
        data=data,
        start_date=START_DATE,
        end_date=END_DATE,
    )

    return metrics


def main():
    logger.info("===== 日内套利策略模板 回测示例 (1min + T0/T1) =====")

    metrics = run_intraday_arb_backtest()

    print("\n回测结果概览:")
    print(f"  总收益率: {metrics.total_return:.2%}")
    print(f"  年化收益率: {metrics.annual_return:.2%}")
    print(f"  最大回撤: {metrics.max_drawdown:.2%}")
    print(f"  夏普比率: {metrics.sharpe_ratio:.2f}")
    print(f"  交易次数: {metrics.num_trades}")
    print(f"  胜率: {metrics.win_rate:.2%}")
    print(f"  最终资产: {metrics.final_value:,.0f}")


if __name__ == "__main__":
    main()
