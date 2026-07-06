"""
金融事件类型定义
与 C++ EventFormat.hpp EventTypes namespace 一一对应
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class FinancialEventType(str, Enum):
    """金融事件类型 — 与 C++ EventTypes::NEWS_* 同步"""
    EARNINGS      = "news.earnings"       # 业绩预告/快报
    POLICY        = "news.policy"         # 政策/监管
    MATERIAL      = "news.material"       # 重大事项(重组/增减持/分红)
    SOCIAL        = "news.social"         # 社交媒体情绪异动
    QUOTE_ALERT   = "news.quote_alert"    # 行情异动(放量/涨跌停/盘口)
    ALERT         = "news.alert"          # 突发/快讯


class InfoSource(str, Enum):
    """信息源标识"""
    EASTMONEY   = "eastmoney"     # 东方财富
    CNINFO      = "cninfo"        # 巨潮资讯
    XUEQIU      = "xueqiu"        # 雪球
    CLS         = "cls"           # 财联社
    SINA        = "sina"          # 新浪财经
    GM_SDK      = "gm_sdk"        # 掘金SDK (行情异动)


@dataclass
class FinancialEvent:
    """标准化金融事件对象 — 通过 EventPublisher 转为 C++ EventFormat"""
    source: str                              # 信息源标识
    title: str                               # 标题
    summary: str                             # 摘要 (≤500字)
    symbols: List[str] = field(default_factory=list)  # 关联标的代码
    sentiment_score: float = 0.0             # 情感分 -1.0 ~ 1.0
    event_type: FinancialEventType = FinancialEventType.ALERT
    confidence: float = 0.0                  # NLP 置信度 0.0 ~ 1.0
    tags: Dict[str, str] = field(default_factory=dict)  # {"超预期":"true","风险类型":"立案调查"}
    timestamp: int = 0                       # Unix 毫秒

    def to_event_format_data(self) -> dict:
        """转为 C++ EventFormat 兼容格式

        Returns:
            {"data": {...}, "metadata": {...}}
        """
        return {
            "data": {
                "source":          self.source,
                "title":           self.title,
                "summary":         self.summary,
                "symbols":         self.symbols,
                "sentiment_score": str(self.sentiment_score),
                "confidence":      str(self.confidence),
            },
            "metadata": {
                "timestamp": str(self.timestamp),
                **{f"tag.{k}": v for k, v in self.tags.items()},
            }
        }

    def __repr__(self) -> str:
        syms = ",".join(self.symbols[:3])
        if len(self.symbols) > 3:
            syms += f",+{len(self.symbols)-3}"
        return (f"FinancialEvent({self.event_type.value}, "
                f"source={self.source}, "
                f"symbols=[{syms}], "
                f"sentiment={self.sentiment_score:.2f}, "
                f"confidence={self.confidence:.2f})")
