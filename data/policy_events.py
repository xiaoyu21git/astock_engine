"""简化版政策事件定义

用于示例和测试：将少量政策/消息事件映射到题材（theme），
并在因子计算时按日期和题材合成为每只股票的 policy_score。

真实环境下，可以替换为从数据库或外部数据源加载的事件表。
"""

from dataclasses import dataclass
from datetime import date
from typing import List


@dataclass
class PolicyEvent:
    """政策/消息事件

    Attributes:
        date: 生效日期（按交易日对齐）
        theme: 受影响题材名称，例如 "新能源"、"白酒" 等
        score: 影响分数，>0 为利好，<0 为利空
    """

    date: date
    theme: str
    score: float


# 为测试时间段 2024-01-02 ~ 2024-01-10 定义几条示例事件
POLICY_EVENTS: List[PolicyEvent] = [
    # 对新能源相关题材的利好（交易日）
    PolicyEvent(date=date(2024, 1, 4), theme="新能源", score=0.8),
    # 对白酒题材的小幅利空（同样选择一个交易日，便于回测数据命中）
    PolicyEvent(date=date(2024, 1, 5), theme="白酒", score=-0.5),
]


def iter_policy_events() -> List[PolicyEvent]:
    """返回当前定义的所有政策事件列表。"""

    return list(POLICY_EVENTS)
