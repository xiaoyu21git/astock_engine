"""日内套利策略插件版本

包装 IntradayArbTemplateStrategy 以适配插件体系和回测/实时容器。

插件 ID: intraday_arb
- 可在 StrategyPluginManager 中通过 strategy_id="intraday_arb" 加载；
- 可在 run_realtime_strategy_container.py 中通过配置切换到该日内策略。
"""

from typing import Dict, Optional, List

from datetime import datetime
import logging

import pandas as pd

from astock_engine.strategies.base_strategy import BaseStrategy, Signal
from astock_engine.strategies.intraday_arb_template import IntradayArbTemplateStrategy
from astock_engine.core import EventBus, EventType, Event


logger = logging.getLogger(__name__)


class IntradayArbPluginStrategy(IntradayArbTemplateStrategy):
    """日内套利策略 (插件版)

    说明:
    - 直接继承 IntradayArbTemplateStrategy，复用其全部逻辑；
    - 额外实现 EventBus 驱动的实时模式（订阅 MARKET_DATA 并发布 SIGNAL 事件）；
    - 仅在名称和插件语义上做区分，方便在插件列表中识别。
    """

    def __init__(self, params: Optional[Dict] = None):
        super().__init__(params=params or {})
        self.name = "日内套利策略(插件版)"

        # 实时模式下用于累积分钟级 K 线的数据缓存
        self._realtime_data: pd.DataFrame | None = None
        # 控制实时指标计算的窗口长度，防止数据无限增长
        p = self.params or {}
        self.realtime_window: int = int(p.get("realtime_window", 300))

        self.bus: Optional[EventBus] = None

    # === 实时模式接口（供实时容器调用） ===

    def initialize(self, bus: EventBus):
        """在实时容器中注入 EventBus 并订阅 MARKET_DATA。"""
        self.bus = bus
        try:
            bus.subscribe(EventType.MARKET_DATA, self.on_market_data)
            logger.info("[插件] 日内套利策略已订阅 MARKET_DATA 事件")
        except Exception as exc:  # pragma: no cover - 防御性
            logger.warning("[插件] 日内套利策略订阅 MARKET_DATA 失败: %s", exc)

    def on_market_data(self, event: Event):
        """处理实时 MARKET_DATA 事件并转换为 Signal。"""
        data = getattr(event, "data", {}) or {}
        symbol = data.get("symbol")
        close = data.get("close")
        volume = data.get("volume", 0)
        ts = data.get("timestamp") or getattr(event, "timestamp", None) or datetime.now()

        if symbol is None or close is None:
            return

        try:
            ts_dt = pd.to_datetime(ts)
        except Exception:
            ts_dt = datetime.now()

        try:
            close_f = float(close)
        except Exception:
            return

        try:
            volume_i = int(volume or 0)
        except Exception:
            volume_i = 0

        # 将 tick 近似为一分钟 bar：O/H/L 取当前价
        row = {
            "symbol": str(symbol),
            "open": close_f,
            "high": close_f,
            "low": close_f,
            "close": close_f,
            "volume": volume_i,
        }

        if self._realtime_data is None:
            self._realtime_data = pd.DataFrame([row], index=[ts_dt])
        else:
            self._realtime_data.loc[ts_dt] = row
            # 仅保留最近 realtime_window 条记录，避免无限增长
            self._realtime_data.sort_index(inplace=True)
            if self.realtime_window > 0 and len(self._realtime_data) > self.realtime_window:
                self._realtime_data = self._realtime_data.iloc[-self.realtime_window :].copy()

        # 为分钟级模板生成信号：使用当前缓存窗口的一个副本
        data_win = self._realtime_data.copy()

        # IntradayArbTemplateStrategy.generate_signals 期望 data.index 为 DatetimeIndex，且包含 symbol 列
        try:
            signals = self.generate_signals(data_win, context={"date": ts_dt})
        except Exception as exc:  # pragma: no cover - 防御性
            logger.warning("[插件] 日内套利策略实时信号计算失败: %s", exc)
            return

        for sig in signals:
            if isinstance(sig, Signal):
                self._publish_signal(sig)

    def _publish_signal(self, signal: Signal):
        """将模板策略产生的 Signal 发布为 EventBus 事件。"""
        if not self.bus:
            return

        evt = Event(
            type=EventType.SIGNAL,
            data={
                "symbol": signal.symbol,
                "direction": signal.direction,
                "strength": signal.strength,
                "price": signal.price,
                "reason": signal.reason,
                "metadata": {"strategy": "plugin:intraday_arb", **(signal.metadata or {})},
                "timestamp": signal.timestamp,
            },
            timestamp=signal.timestamp,
        )
        self.bus.publish(evt)
        logger.info("[插件] 📡 发布日内套利信号: %s %s", signal.symbol, signal.reason)

    def shutdown(self):
        """关闭策略，取消订阅。"""
        if self.bus:
            try:
                self.bus.unsubscribe(EventType.MARKET_DATA, self.on_market_data)
            except Exception:
                pass
        logger.info("[插件] 日内套利策略(插件版) 已关闭")
