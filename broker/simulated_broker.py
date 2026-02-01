"""基于 EventBus 的模拟券商实现。

用途：
- 在实时策略容器中替代简单的打印式执行器；
- 为将来接入真实券商提供接口示例（place_order / cancel_order 等）。
"""

from __future__ import annotations

import logging
import itertools
from typing import Dict, Any

from astock_engine.core import EventBus, EventType, Event
from .base import Broker, OrderRequest, OrderStatus, OrderSide


logger = logging.getLogger(__name__)


class SimulatedBroker(Broker):
    """极简模拟券商。

    行为：
    - 订阅策略信号 / 下单事件，打印日志；
    - 对收到的下单请求立即回推 ORDER_RESPONSE 和 TRADE 事件；
    - 维护一份极简的头寸与资金快照（不做严格风控，主要用于观察链路）。
    """

    _id_counter = itertools.count(1)

    def __init__(self, bus: EventBus, initial_cash: float = 1_000_000.0):
        self.bus = bus
        self.cash = float(initial_cash)
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.orders: Dict[str, OrderStatus] = {}

        # 订阅策略事件 / 下单事件
        if hasattr(EventType, "STRATEGY_SIGNAL"):
            self.bus.subscribe(EventType.STRATEGY_SIGNAL, self._on_strategy_signal)
        if hasattr(EventType, "ORDER"):
            self.bus.subscribe(EventType.ORDER, self._on_order_event)
        try:
            # 字符串 topic 兼容
            self.bus.subscribe("signal", self._on_generic_signal)
            self.bus.subscribe("place_order", self._on_place_order_event)
        except Exception:  # pragma: no cover - 防御性
            pass

        logger.info("SimulatedBroker 已启动，初始资金=%.2f", self.cash)

    # === Broker 接口实现 ===

    def place_order(self, req: OrderRequest) -> OrderStatus:
        order_id = f"SIM-{next(self._id_counter)}"
        filled_qty = req.quantity
        price = float(req.price or 0.0)

        # 简单市价撮合：立刻完全成交
        if req.side == OrderSide.BUY:
            cost = price * filled_qty
            self.cash -= cost
            pos = self.positions.setdefault(req.symbol, {"quantity": 0, "avg_price": 0.0})
            # 简单加权成本
            total_qty = pos["quantity"] + filled_qty
            if total_qty > 0:
                pos["avg_price"] = (pos["avg_price"] * pos["quantity"] + cost) / total_qty
            pos["quantity"] = total_qty
        else:
            # 卖出：减少持仓，增加现金
            pos = self.positions.setdefault(req.symbol, {"quantity": 0, "avg_price": 0.0})
            sell_qty = min(filled_qty, pos["quantity"])
            proceeds = price * sell_qty
            self.cash += proceeds
            pos["quantity"] -= sell_qty

        status = OrderStatus(
            order_id=order_id,
            filled_quantity=filled_qty,
            status="FILLED",
            avg_price=price,
        )
        self.orders[order_id] = status

        # 通过 EventBus 回推撮合结果
        try:
            resp_evt = Event(
                type=EventType.ORDER_RESPONSE,
                data={
                    "order_id": order_id,
                    "symbol": req.symbol,
                    "side": req.side.value,
                    "quantity": filled_qty,
                    "avg_price": price,
                    "status": status.status,
                },
            )
            self.bus.publish(resp_evt)

            trade_evt = Event(
                type=EventType.TRADE,
                data={
                    "order_id": order_id,
                    "symbol": req.symbol,
                    "side": req.side.value,
                    "quantity": filled_qty,
                    "price": price,
                },
            )
            self.bus.publish(trade_evt)
        except Exception:  # pragma: no cover - 防御性
            pass

        logger.info(
            "[SimBroker] %s %s x%s @ %.2f -> %s",
            req.side.value,
            req.symbol,
            filled_qty,
            price,
            status.status,
        )

        return status

    def cancel_order(self, order_id: str) -> bool:
        status = self.orders.get(order_id)
        if not status or status.status == "FILLED":
            return False
        status.status = "CANCELED"
        logger.info("[SimBroker] 取消订单 %s", order_id)
        return True

    def query_positions(self) -> Dict[str, Any]:
        return {k: dict(v) for k, v in self.positions.items()}

    def query_account(self) -> Dict[str, Any]:
        return {"cash": self.cash}

    # === 事件处理 ===

    def _on_strategy_signal(self, event: Event):
        data = getattr(event, "data", {}) or {}
        symbol = data.get("symbol")
        direction = data.get("direction")
        price = data.get("price")
        logger.info("[STRATEGY_SIGNAL] %s dir=%s price=%s", symbol, direction, price)

    def _on_order_event(self, event: Event):
        data = getattr(event, "data", {}) or {}
        symbol = data.get("symbol")
        side = str(data.get("side", "BUY")).upper()
        qty = int(data.get("quantity", 0) or 0)
        price = float(data.get("price", 0.0) or 0.0)
        logger.info("[ORDER] %s %s x%s @ %s", side, symbol, qty, price)
        if symbol and qty > 0 and price > 0:
            side_enum = OrderSide.BUY if side == "BUY" else OrderSide.SELL
            req = OrderRequest(symbol=symbol, side=side_enum, quantity=qty, price=price)
            self.place_order(req)

    def _on_generic_signal(self, event: Event):
        data = getattr(event, "data", {}) or {}
        logger.info("[signal] %s", data)

    def _on_place_order_event(self, event: Event):
        data = getattr(event, "data", {}) or {}
        symbol = data.get("symbol")
        side = str(data.get("side", "BUY")).upper()
        qty = int(data.get("quantity", 0) or 0)
        price = float(data.get("price", 0.0) or 0.0)
        logger.info("[place_order] %s %s x%s @ %s", side, symbol, qty, price)
        if symbol and qty > 0 and price > 0:
            side_enum = OrderSide.BUY if side == "BUY" else OrderSide.SELL
            req = OrderRequest(symbol=symbol, side=side_enum, quantity=qty, price=price)
            self.place_order(req)
