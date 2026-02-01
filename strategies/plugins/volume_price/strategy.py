"""
量价关系策略插件版本
包装现有 VolumePriceStrategy 以适配插件体系和回测引擎
"""

from typing import Dict, List, Optional
from datetime import datetime

import pandas as pd

from astock_engine.strategies.base_strategy import BaseStrategy, Signal
from astock_engine.strategies.volume_price_strategy import VolumePriceStrategy as CoreVolumePriceStrategy


class VolumePricePluginStrategy(BaseStrategy):
    """量价关系策略 (插件版)

    说明:
    - 内部复用已有的 CoreVolumePriceStrategy, 保持原有量价逻辑
    - 对外实现 BaseStrategy 接口, 供 BacktestEngine 与插件管理器使用
    """

    def __init__(self, params: Optional[Dict] = None):
        name = "量价关系策略(插件版)"
        super().__init__(name=name, params=params or {})
        # 复用核心量价策略逻辑
        self.core_strategy = CoreVolumePriceStrategy(params=self.params)

        # T 交易模式: None / "T0" / "T1" / "T0_T1"
        self.t_mode: str = str(self.params.get("t_mode", "")).upper() or "NONE"

    def _generate_t_signals(self, data: pd.DataFrame, context: Optional[Dict]) -> List[Signal]:
        """基于当前持仓与时间生成 T+0 / T+1 平仓信号。

        - T+0: 当日最后一根分钟 K 线（15:00）对所有标的发出平仓信号；
        - T+1: 每个交易日首根分钟 K 线（09:30）对所有标的发出平仓信号。

        实际是否有持仓由回测引擎决定：若某标的当前没有持仓，则对应卖出信号会被回测引擎忽略。
        """
        if not isinstance(data, pd.DataFrame):
            return []

        if context is None:
            return []

        current_time = context.get("date")
        if not isinstance(current_time, datetime):
            return []

        # 仅在分钟级数据上启用 T 逻辑
        if not isinstance(data.index, pd.DatetimeIndex):
            return []

        # 按 symbol 获取最新一条 K 线（<= 当前时间）
        if "symbol" not in data.columns:
            return []

        latest_per_symbol = data.groupby("symbol").tail(1)

        t_signals: List[Signal] = []

        # T+0: 收盘前对所有标的发出平仓信号
        if self.t_mode in {"T0", "T0_T1"}:
            # 这里按模拟数据生成规则，15:00 视为最后一根 K 线
            if current_time.hour == 15 and current_time.minute == 0:
                for _, row in latest_per_symbol.iterrows():
                    symbol = str(row["symbol"])
                    price = float(row["close"])

                    t_signals.append(
                        Signal(
                            symbol=symbol,
                            direction=-1,
                            strength=1.0,
                            timestamp=current_time,
                            price=price,
                            reason="T0_end_of_day_exit",
                            metadata={
                                "horizon": "T0",
                                "exit_type": "end_of_day",
                            },
                        )
                    )

        # T+1: 每个交易日首根分钟 K 线对所有标的发出平仓信号
        if self.t_mode in {"T1", "T0_T1"}:
            if current_time.hour == 9 and current_time.minute == 30:
                for _, row in latest_per_symbol.iterrows():
                    symbol = str(row["symbol"])
                    price = float(row["close"])

                    t_signals.append(
                        Signal(
                            symbol=symbol,
                            direction=-1,
                            strength=1.0,
                            timestamp=current_time,
                            price=price,
                            reason="T1_next_day_exit",
                            metadata={
                                "horizon": "T1",
                                "exit_type": "next_day",
                            },
                        )
                    )

        return t_signals

    def generate_signals(self, data: pd.DataFrame, context: Optional[Dict] = None) -> List[Signal]:
        """生成交易信号

        Args:
            data: 回测引擎传入的历史数据 (通常为合并后的 DataFrame, 含 symbol 列)
            context: 上下文字典, 至少包含当前日期字段, 例如 {'date': datetime}
        """
        if context is None:
            # 兜底提供当前时间, 避免下游依赖报错
            context = {"date": datetime.now()}

        # CoreVolumePriceStrategy 已经支持:
        # - data 为合并后的 DataFrame, 内部按 symbol 拆分
        # - 返回 List[Signal] 列表
        base_signals = self.core_strategy.generate_signals(data, context)

        # 叠加 T+0 / T+1 强制平仓信号（若启用）
        t_signals = self._generate_t_signals(data, context)

        # 确保类型安全: 过滤掉意外的非 Signal 元素
        clean_signals: List[Signal] = []
        for s in list(base_signals) + list(t_signals):
            if isinstance(s, Signal):
                clean_signals.append(s)

        return clean_signals
