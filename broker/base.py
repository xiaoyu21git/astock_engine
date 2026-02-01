"""Broker 抽象层

提供一套极简的券商接口定义，方便将策略 / 实时容器
与具体券商 API （掘金、东方财富等）解耦。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, Protocol


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass
class OrderRequest:
    symbol: str
    side: OrderSide
    quantity: int
    price: Optional[float] = None
    order_type: OrderType = OrderType.LIMIT
    client_order_id: Optional[str] = None


@dataclass
class OrderStatus:
    order_id: str
    filled_quantity: int
    status: str  # 例如 NEW / PARTIALLY_FILLED / FILLED / CANCELED
    avg_price: Optional[float] = None
    raw: Optional[Dict[str, Any]] = None


class Broker(Protocol):
    """券商接口抽象。

    真实接券商时，实现本接口并在实时容器中注入即可。
    """

    def place_order(self, req: OrderRequest) -> OrderStatus:
        ...

    def cancel_order(self, order_id: str) -> bool:
        ...

    def query_positions(self) -> Dict[str, Any]:
        ...

    def query_account(self) -> Dict[str, Any]:
        ...
