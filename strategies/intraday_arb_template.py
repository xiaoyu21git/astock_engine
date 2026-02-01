"""日内套利策略模板（分钟级 + T 模式）

设计目标：
- 针对分钟级 K 线（如 1min）构建一个更贴近期货风格的日内策略骨架；
- 复用现有 VolumePriceStrategy 的指标链路（含 5 分钟周期线、板块因子、情绪/政策因子）；
- 叠加 T+0 / T+1 行为，通过 t_mode 参数控制平仓方式；
- 作为模板提供清晰的结构和注释，便于你根据实际逻辑二次开发。

使用方式（示例）：
- 在回测中：

    from astock_engine.strategies.intraday_arb_template import IntradayArbTemplateStrategy

    strategy = IntradayArbTemplateStrategy(params={
        "t_mode": "T0_T1",  # 或 "T0" / "T1" / "NONE"
    })

    # BacktestEngine 会在分钟级数据上调用 strategy.generate_signals(data, context)

本文件只定义策略类，不直接接入插件管理器；
如需在插件体系或实时容器中使用，可参考 VolumePricePluginStrategy 的接入方式。
"""

from __future__ import annotations

from typing import Dict, List, Optional
from datetime import datetime

import pandas as pd

from astock_engine.strategies.base_strategy import BaseStrategy, Signal
from astock_engine.strategies.volume_price_strategy import VolumePriceStrategy
from astock_engine.strategies.plugins.volume_price.strategy import (
    VolumePricePluginStrategy,
)


class IntradayArbTemplateStrategy(VolumePricePluginStrategy):
    """基于分钟级 + T 模式的日内套利策略模板。

    关键特性：
    - 期望 data 为包含多标的分钟级 K 线的 DataFrame，至少含列：
      ['symbol', 'open', 'high', 'low', 'close', 'volume']，索引为 DatetimeIndex；
    - 内部使用 VolumePriceStrategy.calculate_indicators 计算：
      - 价量指标
      - 5 分钟周期线（cycle_5m_*）
      - 板块/题材因子（industry_ret/theme_ret 等）
      - 情绪因子（market_sentiment）
      - 政策因子（policy_score）
    - 示例性给出一组偏“期货化”的日内进出场逻辑：
      - 在 5 分钟支撑位附近、情绪和政策不差时做多；
      - 在 5 分钟压力位附近、情绪或政策走弱时平仓/做空；
      - 叠加 t_mode 控制 T+0 / T+1 平仓行为。
    """

    def __init__(self, params: Optional[Dict] = None):
        name = "日内套利策略模板"
        super().__init__(params=params or {})
        # 覆盖 BaseStrategy 中的名称，便于日志识别
        self.name = name
        # 日内套利模板自身的阈值，可通过 params 覆盖
        p = self.params
        # 触发“支撑反弹做多”的最小情绪/板块要求
        self.min_sentiment_for_long = float(p.get("min_sentiment_for_long", -0.1))
        self.min_policy_for_long = float(p.get("min_policy_for_long", -0.1))
        self.min_sector_ret_for_long = float(p.get("min_sector_ret_for_long", -0.002))
        # 行业 / 板块舆情的最小要求（来自 NEWS 聚合），为 0 表示只要不明显负面即可
        self.min_sector_sentiment_for_long = float(p.get("min_sector_sentiment_for_long", 0.0))

        # 触发“压力位做空/平仓”的条件
        self.max_sentiment_for_short = float(p.get("max_sentiment_for_short", 0.1))
        self.max_policy_for_short = float(p.get("max_policy_for_short", 0.1))
        self.min_cycle_trend_for_short = float(p.get("min_cycle_trend_for_short", -0.001))
        
        # 竞价因子相关阈值
        # 开盘阶段：若竞价明显走弱，则抑制做多；若竞价明显强势，则可以略微放宽做多条件
        self.min_auction_strength_for_open_long = float(p.get("min_auction_strength_for_open_long", -0.02))
        self.max_auction_strength_for_open_short = float(p.get("max_auction_strength_for_open_short", 0.03))

    def _split_by_symbol(self, data: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """将带 symbol 列的合并 DataFrame 拆分为 {symbol: df}。"""
        if "symbol" not in data.columns:
            return {}

        result: Dict[str, pd.DataFrame] = {}
        for symbol in data["symbol"].unique():
            df = data[data["symbol"] == symbol].copy()
            df = df.drop(columns=["symbol"])
            result[str(symbol)] = df
        return result

    def generate_signals(
        self, data: pd.DataFrame, context: Optional[Dict] = None
    ) -> List[Signal]:
        # 兜底当前时间
        if context is None:
            context = {"date": datetime.now()}
        current_dt = context.get("date", datetime.now())

        if not isinstance(data, pd.DataFrame) or "symbol" not in data.columns:
            return []

        # 要求分钟级数据（存在非 00:00 的时间部分）；否则直接不交易
        if not isinstance(data.index, pd.DatetimeIndex):
            return []
        if not ((data.index.hour != 0) | (data.index.minute != 0)).any():
            return []

        # 拆分为 {symbol: df} 并计算全部指标
        by_symbol = self._split_by_symbol(data)
        if not by_symbol:
            return []

        by_symbol = self.core_strategy.calculate_indicators(by_symbol)

        signals: List[Signal] = []

        for symbol, df in by_symbol.items():
            if df is None or df.empty:
                continue

            if len(df) < 20:
                # 数据太短，指标不稳定，跳过
                continue

            latest = df.iloc[-1]

            price = float(latest.get("close", 0.0))

            # 5 分钟周期线信息
            is_rebound_from_5m_support = bool(
                latest.get("is_rebound_from_5m_support", False)
            )
            is_near_5m_resistance = bool(latest.get("is_near_5m_resistance", False))
            cycle_5m_trend = float(latest.get("cycle_5m_trend", 0.0) or 0.0)

            # 情绪 / 政策 / 板块因子
            market_sentiment = float(latest.get("market_sentiment", 0.0) or 0.0)
            policy_score = float(latest.get("policy_score", 0.0) or 0.0)
            industry_ret = float(latest.get("industry_ret", 0.0) or 0.0)
            theme_ret = float(latest.get("theme_ret", 0.0) or 0.0)
            # 行业 / 板块舆情（若存在，由上游因子或实时舆情模块写入）
            sector_sentiment = float(latest.get("sector_sentiment", 0.0) or 0.0)

            # 竞价因子：在当日所有 bar 上恒定，但 is_auction_bar 标记首个 bar
            auction_gap = float(latest.get("auction_gap", 0.0) or 0.0)
            auction_strength = float(latest.get("auction_strength", 0.0) or 0.0)
            is_auction_bar = bool(latest.get("is_auction_bar", False))

            meta_base = {
                "cycle_5m_trend": cycle_5m_trend,
                "is_rebound_from_5m_support": is_rebound_from_5m_support,
                "is_near_5m_resistance": is_near_5m_resistance,
                "market_sentiment": market_sentiment,
                "policy_score": policy_score,
                "industry_ret": industry_ret,
                "theme_ret": theme_ret,
                "sector_sentiment": sector_sentiment,
                "auction_gap": auction_gap,
                "auction_strength": auction_strength,
                "is_auction_bar": is_auction_bar,
            }

            # === 示例性“做多模板”：支撑位反弹 + 情绪/政策/板块不太差（略偏激进） ===
            # 在开盘竞价阶段，如果 auction_strength 明显偏弱，则抑制做多；
            # 若竞价较强，则可以略微放宽做多条件（由阈值控制）。
            long_base = (
                is_rebound_from_5m_support
                and market_sentiment >= self.min_sentiment_for_long
                and policy_score >= self.min_policy_for_long
                and (industry_ret >= self.min_sector_ret_for_long or theme_ret >= self.min_sector_ret_for_long)
                and sector_sentiment >= self.min_sector_sentiment_for_long
            )

            if is_auction_bar:
                # 开盘首个 bar：只有在竞价强度不特别差的情况下才允许做多
                long_setup = long_base and auction_strength >= self.min_auction_strength_for_open_long
            else:
                long_setup = long_base

            if long_setup:
                signals.append(
                    Signal(
                        symbol=symbol,
                        direction=1,
                        strength=1.0,
                        timestamp=current_dt,
                        price=price,
                        reason="intraday_long_rebound_template",
                        metadata={
                            "pattern": "intraday_long_rebound",
                            **meta_base,
                        },
                    )
                )

                continue

            # === 示例性“平仓/做空模板”：压力位附近 + 趋势走弱 + 情绪或政策明显不乐观 ===
            short_base = (
                is_near_5m_resistance
                and cycle_5m_trend <= self.min_cycle_trend_for_short
                and (
                    market_sentiment <= self.max_sentiment_for_short
                    or policy_score <= self.max_policy_for_short
                )
            )

            if is_auction_bar:
                # 若竞价本身已经非常强势，则在首个 bar 上更倾向于不立即做空/平仓，避免在强势高开时过早对冲；
                short_setup = short_base and auction_strength <= self.max_auction_strength_for_open_short
            else:
                short_setup = short_base

            if short_setup:
                signals.append(
                    Signal(
                        symbol=symbol,
                        direction=-1,
                        strength=1.0,
                        timestamp=current_dt,
                        price=price,
                        reason="intraday_exit_or_short_template",
                        metadata={
                            "pattern": "intraday_exit_or_short",
                            **meta_base,
                        },
                    )
                )
                continue

        # 叠加 T+0 / T+1 强制平仓信号
        t_signals = self._generate_t_signals(data, context)

        all_signals: List[Signal] = []
        for s in list(signals) + list(t_signals):
            if isinstance(s, Signal):
                all_signals.append(s)

        return all_signals
