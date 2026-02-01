"""基于 NEWS 事件维护行业 / 题材舆情因子。

设计目标：
- 监听 EventBus 上的 NEWS 事件（或直接调用 update_from_news_row）；
- 利用 get_symbol_tags(symbol) 将新闻映射到行业 / 题材；
- 维护一个带时间衰减的情绪分数：industry_sentiment / theme_sentiment；
- 为 VolumePrice / Intraday 策略提供 sector_sentiment 因子。

注意：
- 这是一个简单的 in-memory 实现，适用于单进程实时容器；
- 若在多进程或分布式环境使用，应将状态存入外部存储（如 Redis/DB）。
"""

from __future__ import annotations

from typing import Dict, Optional
from datetime import datetime, timedelta

import math

from astock_engine.data.sector_universe import get_symbol_tags


class _DecayAccumulator:
    """带指数衰减的简单累加器。

    s_t = s_{t-1} * decay^{Δt} + score
    """

    def __init__(self, half_life_minutes: float = 60.0):
        # 半衰期（分钟）；越小代表舆情“记忆”越短
        self.half_life_minutes = max(float(half_life_minutes), 1.0)
        self._values: Dict[str, float] = {}
        self._last_ts: Optional[datetime] = None

    def _decay_factor(self, now: datetime) -> float:
        if self._last_ts is None:
            return 1.0
        dt = max((now - self._last_ts).total_seconds() / 60.0, 0.0)
        if dt <= 0:
            return 1.0
        # 半衰期公式：decay = 0.5^(dt / half_life)
        return math.pow(0.5, dt / self.half_life_minutes)

    def update(self, key: str, score: float, now: datetime) -> None:
        decay = self._decay_factor(now)
        if self._last_ts is None:
            self._last_ts = now
        else:
            self._last_ts = now

        prev = self._values.get(key, 0.0)
        self._values[key] = prev * decay + float(score)

    def snapshot(self) -> Dict[str, float]:
        return dict(self._values)


class IndustrySentimentState:
    """全局行业 / 题材舆情状态（单进程内使用）。"""

    def __init__(self, half_life_minutes: float = 60.0):
        self._ind_acc = _DecayAccumulator(half_life_minutes)
        self._theme_acc = _DecayAccumulator(half_life_minutes)

    def update_from_news(
        self,
        symbol: str,
        sentiment_score: float,
        ts: datetime,
    ) -> None:
        """根据一条新闻事件更新行业 / 题材舆情。

        Args:
            symbol: 相关新闻对应的股票代码（如 000001.SZ），可为空字符串
            sentiment_score: 文本情感得分（通常在 [-1, 1]）
            ts: 新闻发布时间
        """

        if not symbol:
            return

        try:
            score = float(sentiment_score)
        except Exception:
            return

        tags = get_symbol_tags(symbol)
        industry = tags.get("industry")
        themes = tags.get("themes") or []

        if industry:
            self._ind_acc.update(industry, score, ts)

        for theme in themes:
            self._theme_acc.update(theme, score, ts)

    def get_industry_sentiment(self) -> Dict[str, float]:
        return self._ind_acc.snapshot()

    def get_theme_sentiment(self) -> Dict[str, float]:
        return self._theme_acc.snapshot()


# 单例状态，供全局使用
GLOBAL_INDUSTRY_SENTIMENT = IndustrySentimentState(half_life_minutes=120.0)


def update_from_news_row(symbol: str, sentiment_score: float, ts: datetime) -> None:
    """便捷函数：从单条新闻（或 NEWS 事件）更新全局行业舆情。"""

    GLOBAL_INDUSTRY_SENTIMENT.update_from_news(symbol, sentiment_score, ts)


def get_sector_sentiment_for_symbol(symbol: str) -> float:
    """获取某只股票所在行业 / 题材的综合舆情得分。

    简化规则：
    - 若同时存在行业和题材舆情，则取两者平均；
    - 若只有其一，则返回该值；
    - 若均不存在，则返回 0.0。
    """

    tags = get_symbol_tags(symbol)
    industry = tags.get("industry")
    themes = tags.get("themes") or []

    ind_map = GLOBAL_INDUSTRY_SENTIMENT.get_industry_sentiment()
    theme_map = GLOBAL_INDUSTRY_SENTIMENT.get_theme_sentiment()

    vals = []
    if industry and industry in ind_map:
        vals.append(float(ind_map[industry]))

    for t in themes:
        if t in theme_map:
            vals.append(float(theme_map[t]))

    if not vals:
        return 0.0

    return float(sum(vals) / len(vals))
