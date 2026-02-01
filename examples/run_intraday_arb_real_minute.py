#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""日内套利策略 + 真实分钟级 K 线回测示例

功能：
- 使用 AkShareProvider 直接从 AkShare 拉取真实 A 股 1 分钟 K 线；
- 组装成 BacktestEngine 期望的 OHLCV 格式；
- 通过 intraday_arb 插件策略 + T0/T1 行为，做一段短周期的日内回测。

前置条件：
- 当前虚拟环境已安装 akshare:

    G:/C++/AStockQuantEngine/.venv/Scripts/pip install akshare

运行方式（在项目根目录）：

    G:/C++/AStockQuantEngine/.venv/Scripts/python.exe \
        astock_engine/examples/run_intraday_arb_real_minute.py

注意：
- 分钟级真实数据量较大，建议先选少量标的 + 较短时间窗口做验证；
- 本示例仅用于打通“真实分钟线 → 日内策略”链路，未做性能优化。
"""

import sys
from pathlib import Path
from datetime import datetime
import logging
from typing import Dict, List

import pandas as pd

# 将项目根目录加入路径，便于作为脚本直接运行
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from astock_engine.data.data_provider import AkShareProvider
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
    "600519.SH",  # 贵州茅台
    "300750.SZ",  # 宁德时代
]

# 为避免一次性拉太多分钟线，这里选一个相对较短的时间窗口
START_DATE = "2024-01-02"
END_DATE = "2024-01-05"


def load_real_minute_data(symbols: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
    """使用 AkShare 获取真实 1 分钟 K 线，并转换为 OHLCV 结构。

    返回的数据满足 BacktestEngine 和 intraday_arb 策略的要求：
    - 索引: DatetimeIndex（精确到分钟）；
    - 列: ['open', 'high', 'low', 'close', 'volume', 'symbol']。
    """
    provider = AkShareProvider()
    ak = provider.ak

    data: Dict[str, pd.DataFrame] = {}

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=1)  # 包含结束那天

    for symbol in symbols:
        code = symbol.split(".")[0]
        logger.info("从 AkShare 获取分钟线: %s", symbol)

        try:
            # AkShare 分钟线接口：period="1" 表示 1 分钟
            df = ak.stock_zh_a_minute(symbol=code, period="1", adjust="qfq")
        except Exception as exc:  # pragma: no cover - 外部依赖
            logger.error("获取 %s 分钟线失败: %s", symbol, exc)
            continue

        if df is None or df.empty:
            logger.warning("%s 分钟线数据为空", symbol)
            continue

        # 尝试兼容不同版本 akshare 的列名
        # 常见形式: ["day", "time", "open", "high", "low", "close", "volume", "amount"]
        day_col = None
        time_col = None

        for cand in ("day", "date"):  # 不同版本可能使用 day 或 date
            if cand in df.columns:
                day_col = cand
                break

        for cand in ("time", "datetime", "timestamp"):
            if cand in df.columns:
                time_col = cand
                break

        if day_col is None:
            logger.error("%s 分钟线数据中找不到日期列(day/date)，跳过", symbol)
            continue

        if time_col is None:
            # 如果只有日期列，则直接用该列作为完整时间
            df["datetime"] = pd.to_datetime(df[day_col])
        else:
            df["datetime"] = pd.to_datetime(df[day_col].astype(str) + " " + df[time_col].astype(str))

        df.set_index("datetime", inplace=True)
        df.sort_index(inplace=True)

        # 过滤时间窗口
        df = df[(df.index >= start_dt) & (df.index < end_dt)]
        if df.empty:
            logger.warning("%s 在指定时间段内无分钟线数据", symbol)
            continue

        # 标准化列名
        col_map = {}
        for c in ("open", "Open", "OPEN"):
            if c in df.columns:
                col_map[c] = "open"
                break
        for c in ("high", "High", "HIGH"):
            if c in df.columns:
                col_map[c] = "high"
                break
        for c in ("low", "Low", "LOW"):
            if c in df.columns:
                col_map[c] = "low"
                break
        for c in ("close", "Close", "CLOSE", "price"):
            if c in df.columns:
                col_map[c] = "close"
                break
        for c in ("volume", "Vol", "VOL", "vol"):
            if c in df.columns:
                col_map[c] = "volume"
                break

        df = df.rename(columns=col_map)

        required = ["open", "high", "low", "close", "volume"]
        if not all(col in df.columns for col in required):
            logger.error("%s 分钟线数据缺失必要列，实际列: %s", symbol, list(df.columns))
            continue

        out = df[required].copy()
        out["symbol"] = symbol

        data[symbol] = out
        logger.info("%s 分钟线样本量: %d", symbol, len(out))

    # 若所有标的都未能成功获取分钟线，则降级为使用 Mock 1 分钟数据，
    # 这样在非交易时段或 AkShare 不可用时仍可观察策略行为。
    if not data:
        logger.warning("AkShare 未返回任何分钟级真实数据，将降级为使用 MockDataManager 生成 1 分钟模拟数据。")
        manager = MockDataManager(seed=42)
        data = manager.get_stock_data(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            frequency="1min",
        )
        logger.info("使用 MockDataManager 生成分钟级模拟数据: %d 只标的", len(data))

    return data


def build_backtest_config() -> BacktestConfig:
    return BacktestConfig(
        initial_capital=1_000_000,
        commission_rate=0.0003,
        slippage_rate=0.001,
        max_position_size=0.4,
        max_positions=4,
        stop_loss=-0.06,
        take_profit=None,
    )


def build_strategy_params(tag: str) -> dict:
    """构造一组策略参数。

    tag:
        - "baseline": 使用模板内相对宽松的默认值；
        - "practical": 稍微偏实战、稳健一些的配置。
    """

    base = {
        "t_mode": "T0_T1",
    }

    if tag == "practical":
        # 更偏实战的一组示例参数：
        # - 情绪/政策要求略收紧；
        # - 板块/题材要求略收紧；
        # - 做空/平仓在情绪偏乐观时更谨慎；
        # - 竞价阶段若强弱信号明显，则更尊重竞价给出的开盘指引。
        base.update(
            {
                # 做多侧：略微要求不那么悲观
                "min_sentiment_for_long": -0.05,
                "min_policy_for_long": -0.05,
                "min_sector_ret_for_long": -0.001,
                # 做空/平仓侧：当情绪/政策明显偏多时少做空
                "max_sentiment_for_short": 0.05,
                "max_policy_for_short": 0.05,
                "min_cycle_trend_for_short": -0.0005,
                # 竞价因子：
                # - 开盘做多时不接受特别弱的竞价；
                # - 若竞价强势，则在首个 bar 更不急于立刻做空。
                "min_auction_strength_for_open_long": 0.0,
                "max_auction_strength_for_open_short": 0.02,
            }
        )

    elif tag == "conservative":
        # 更保守的一组参数：
        # - 只在情绪/政策和板块都不差时做多；
        # - 做空/平仓在情绪明显转弱时才动；
        # - 竞价阶段要求更强的正向信号才在首 bar 行动。
        base.update(
            {
                # 做多：要求整体环境基本中性偏多
                "min_sentiment_for_long": 0.0,
                "min_policy_for_long": 0.0,
                "min_sector_ret_for_long": 0.0,
                # 做空/平仓：仅在情绪/政策明显不佳时
                "max_sentiment_for_short": 0.0,
                "max_policy_for_short": 0.0,
                "min_cycle_trend_for_short": 0.0,
                # 竞价：首 bar 做多要看到明显正向强度，做空则不逆着强竞价
                "min_auction_strength_for_open_long": 0.02,
                "max_auction_strength_for_open_short": 0.0,
            }
        )

    return base


def run_intraday_arb_real_minute(params: dict | None = None) -> BacktestMetrics:
    # 1. 加载真实 1 分钟数据
    data = load_real_minute_data(SYMBOLS, START_DATE, END_DATE)
    if not data:
        raise SystemExit("未能获取任何分钟级真实数据，请检查 akshare 安装及网络")

    # 2. 加载 intraday_arb 插件策略
    manager = StrategyPluginManager()
    manager.scan_plugins()

    plugin_id = "intraday_arb"
    if plugin_id not in manager.plugins:
        raise SystemExit(f"未找到插件策略 {plugin_id}, 请确认 strategies/plugins/{plugin_id} 存在")

    plugin = manager.plugins[plugin_id]

    # 使用 T0_T1 组合模式 + 可配置的情绪/政策/竞价/板块阈值
    strategy_params = params or build_strategy_params("baseline")
    strategy = plugin.create_instance(params=strategy_params)

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
    logger.info("===== 日内套利策略 + 真实 1 分钟 K 线 回测示例 =====")
    configs = [
        ("baseline", "基线"),
        ("practical", "实战"),
        ("conservative", "保守"),
    ]

    all_results: list[tuple[str, BacktestMetrics]] = []

    for tag, label in configs:
        params = build_strategy_params(tag)
        metrics = run_intraday_arb_real_minute(params=params)
        all_results.append((label, metrics))

        print(f"\n[{label}参数] 回测结果概览 (真实分钟线):")
        print(f"  总收益率: {metrics.total_return:.2%}")
        print(f"  年化收益率: {metrics.annual_return:.2%}")
        print(f"  最大回撤: {metrics.max_drawdown:.2%}")
        print(f"  夏普比率: {metrics.sharpe_ratio:.2f}")
        print(f"  交易次数: {metrics.num_trades}")
        print(f"  胜率: {metrics.win_rate:.2%}")
        print(f"  最终资产: {metrics.final_value:,.0f}")

    # 简单汇总表，便于长期记录和肉眼比较
    print("\n参数组合对比汇总:")
    header = f"{'标签':<6}{'总收益':>10}{'最大回撤':>10}{'交易数':>8}{'胜率':>8}{'夏普':>8}"
    print(header)
    print("-" * len(header))
    for label, m in all_results:
        print(
            f"{label:<6}"
            f"{m.total_return:>10.2%}"
            f"{m.max_drawdown:>10.2%}"
            f"{m.num_trades:>8d}"
            f"{m.win_rate:>8.2%}"
            f"{m.sharpe_ratio:>8.2f}"
        )


if __name__ == "__main__":
    main()
