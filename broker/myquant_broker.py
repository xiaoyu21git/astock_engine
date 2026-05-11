"""掘金 MyQuant Broker 适配层。

注意：
- 仅作为对接 gm.api 的骨架示例，不做任何风险控制；
- 默认使用环境变量 GM_TOKEN 和可选的 GM_ACCOUNT_ID；
- 建议先在掘金仿真环境下联调，确认稳定后再用于实盘。
"""

from __future__ import annotations


import logging
import os
import asyncio
from typing import Dict, Any, Optional, List, Callable

from .base import Broker, OrderRequest, OrderStatus, OrderSide, OrderType


logger = logging.getLogger(__name__)


# 可选：在此写死默认 token / account_id，便于本地快速联调
# 使用方式：直接把 None 替换成你的实际值（不要提交到公共仓库）
DEFAULT_GM_TOKEN = None
DEFAULT_GM_ACCOUNT_ID = None


class MyQuantBroker(Broker):
    # 掘金订单状态码映射
    GM_ORDER_STATUS_MAP = {
        10: "NEW",
        11: "FILLED",
        12: "PARTIALLY_FILLED",
        13: "CANCELLED",
        14: "REJECTED",
        15: "EXPIRED",
    }

    @classmethod
    def _map_gm_status(cls, status_raw):
        # 支持 int 或 str 类型
        try:
            code = int(status_raw)
            return cls.GM_ORDER_STATUS_MAP.get(code, str(status_raw))
        except Exception:
            return str(status_raw)
    """基于掘金 gm.api 的 Broker 实现。

    约定：
    - 使用 gm.api 提供的 set_token / set_account_id / order_volume / get_position / get_cash 等接口；
    - token 与 account_id 通过参数或环境变量传入：
      - token: 显式参数优先，其次读取 GM_TOKEN 环境变量；
      - account_id: 显式参数优先，其次读取 GM_ACCOUNT_ID 环境变量；
    - 仅实现最基础的“按量委托 + 查询资金/持仓”能力，进阶用法可在此基础上扩展。
    """

    def __init__(self, token: Optional[str] = None, account_id: Optional[str] = None):
        try:
            from gm.api import set_token, set_account_id
        except Exception as exc:  # pragma: no cover - 运行时检查
            raise RuntimeError("导入 gm.api 失败，请确认已安装 `gm` 包") from exc

        # 优先级：显式参数 > 写死的默认值 > 环境变量
        token = token or DEFAULT_GM_TOKEN or os.getenv("GM_TOKEN")
        if not token:
            raise RuntimeError("未提供掘金 token，请通过参数或环境变量 GM_TOKEN 配置")

        set_token(token)

        self.account_id = account_id or DEFAULT_GM_ACCOUNT_ID or os.getenv("GM_ACCOUNT_ID")
        if self.account_id:
            set_account_id(self.account_id)

        logger.info(
            "MyQuantBroker 初始化完成，account_id=%s (token 已设置)",
            self.account_id or "<default>",
        )

    @staticmethod
    def _to_gm_symbol(symbol: str) -> str:
        """将内部使用的代码（如 000001.SZ / 600000.SH）转换为掘金要求的格式。

        掘金 gm.api 约定：股票代码通常为 "SZSE.000001" / "SHSE.600000" 这一类形式，
        因此这里做一个简单的映射：

        - 000001.SZ -> SZSE.000001
        - 600000.SH -> SHSE.600000
        - 若已经是 SZSE.000001 / SHSE.600000 之类，则原样返回。
        """

        s = (symbol or "").strip().upper()
        if not s:
            return s

        # 如果已经是 "SZSE.000001" / "SHSE.600000" 形式，直接返回
        if s.startswith("SZSE.") or s.startswith("SHSE."):
            return s

        if "." in s:
            code, exch = s.split(".", 1)
            exch = exch.strip().upper()
            if exch in {"SZ", "SZSE"}:
                return f"SZSE.{code}"
            if exch in {"SH", "SHSE"}:
                return f"SHSE.{code}"
            if exch in {"BJ", "BSE"}:
                return f"BSE.{code}"

        # 兜底：保持原样，交给下游处理（便于发现其他品种的编码问题）
        return s

    @staticmethod
    def _from_gm_symbol(symbol: str) -> str:
        """将掘金代码（如 SZSE.000001 / SHSE.600000）转换为内部统一格式。

        约定：
        - SZSE.000001 -> 000001.SZ
        - SHSE.600000 -> 600000.SH
        - 其他前缀暂时保持不变，交由上层自行处理。
        """

        s = (symbol or "").strip().upper()
        if not s:
            return s

        if s.startswith("SZSE."):
            return f"{s[5:]}.SZ"
        if s.startswith("SHSE."):
            return f"{s[5:]}.SH"
        if s.startswith("BSE."):
            return f"{s[4:]}.BJ"

        return s

    # === Broker 接口实现 ===

    def place_order(self, req: OrderRequest) -> OrderStatus:
        """同步下单，原有实现。"""
        from gm.api import (
            order_volume,
            OrderSide_Buy,
            OrderSide_Sell,
            OrderType_Limit,
            OrderType_Market,
            PositionEffect_Open,
            OrderDuration_Unknown,
            OrderQualifier_Unknown,
        )
        side_const = OrderSide_Buy if req.side == OrderSide.BUY else OrderSide_Sell
        if req.order_type == OrderType.MARKET:
            order_type_const = OrderType_Market
            price = float(req.price or 0.0)
        else:
            order_type_const = OrderType_Limit
            if req.price is None:
                raise ValueError("限价单必须提供 price")
            price = float(req.price)
        volume = int(req.quantity)
        gm_symbol = self._to_gm_symbol(req.symbol)
        logger.info(
            "[MyQuantBroker] 下单: %s %s x%s @ %.4f (type=%s)",
            req.side.value,
            gm_symbol,
            req.quantity,
            price,
            req.order_type.value,
        )
        try:
            from tools.live_action_logger import log_action
            log_action(
                action_type="ORDER_NEW",
                symbol=req.symbol,
                side=req.side.value,
                quantity=float(req.quantity),
                price=price,
                status="SENT",
            )
        except Exception:
            pass
        orders: List[Dict[str, Any]] = order_volume(
            symbol=gm_symbol,
            volume=volume,
            side=side_const,
            order_type=order_type_const,
            position_effect=PositionEffect_Open,
            price=price,
            order_duration=OrderDuration_Unknown,
            order_qualifier=OrderQualifier_Unknown,
        )
        primary: Dict[str, Any] = orders[0] if orders else {}
        order_id = str(
            primary.get("cl_ord_id")
            or primary.get("order_id")
            or primary.get("ord_id")
            or primary.get("id")
            or req.client_order_id
            or "GM_ORDER_UNKNOWN"
        )
        status_text = self._map_gm_status(primary.get("status", "NEW"))
        filled_qty = int(primary.get("filled_volume") or 0)
        avg_price = float(primary.get("price") or price)
        try:
            from tools.live_action_logger import log_action
            log_action(
                action_type="ORDER_ACK",
                symbol=req.symbol,
                side=req.side.value,
                quantity=float(req.quantity),
                price=avg_price,
                status=status_text,
                extra={"broker_order_id": order_id},
            )
        except Exception:
            pass
        return OrderStatus(
            order_id=order_id,
            filled_quantity=filled_qty,
            status=status_text,
            avg_price=avg_price,
            raw=primary or None,
        )

    async def place_order_async(self, req: OrderRequest, callback: Optional[Callable[[OrderStatus], None]] = None) -> OrderStatus:
        """异步下单，支持回调。"""
        from gm.api import (
            order_volume,
            OrderSide_Buy,
            OrderSide_Sell,
            OrderType_Limit,
            OrderType_Market,
            PositionEffect_Open,
            OrderDuration_Unknown,
            OrderQualifier_Unknown,
        )
        loop = asyncio.get_event_loop()
        def sync_place():
            side_const = OrderSide_Buy if req.side == OrderSide.BUY else OrderSide_Sell
            if req.order_type == OrderType.MARKET:
                order_type_const = OrderType_Market
                price = float(req.price or 0.0)
            else:
                order_type_const = OrderType_Limit
                if req.price is None:
                    raise ValueError("限价单必须提供 price")
                price = float(req.price)
            volume = int(req.quantity)
            gm_symbol = self._to_gm_symbol(req.symbol)
            logger.info(
                "[MyQuantBroker] 下单: %s %s x%s @ %.4f (type=%s)",
                req.side.value,
                gm_symbol,
                req.quantity,
                price,
                req.order_type.value,
            )
            try:
                from tools.live_action_logger import log_action
                log_action(
                    action_type="ORDER_NEW",
                    symbol=req.symbol,
                    side=req.side.value,
                    quantity=float(req.quantity),
                    price=price,
                    status="SENT",
                )
            except Exception:
                pass
            orders: List[Dict[str, Any]] = order_volume(
                symbol=gm_symbol,
                volume=volume,
                side=side_const,
                order_type=order_type_const,
                position_effect=PositionEffect_Open,
                price=price,
                order_duration=OrderDuration_Unknown,
                order_qualifier=OrderQualifier_Unknown,
            )
            primary: Dict[str, Any] = orders[0] if orders else {}
            order_id = str(
                primary.get("cl_ord_id")
                or primary.get("order_id")
                or primary.get("ord_id")
                or primary.get("id")
                or req.client_order_id
                or "GM_ORDER_UNKNOWN"
            )
            status_text = self._map_gm_status(primary.get("status", "NEW"))
            filled_qty = int(primary.get("filled_volume") or 0)
            avg_price = float(primary.get("price") or price)
            try:
                from tools.live_action_logger import log_action
                log_action(
                    action_type="ORDER_ACK",
                    symbol=req.symbol,
                    side=req.side.value,
                    quantity=float(req.quantity),
                    price=avg_price,
                    status=status_text,
                    extra={"broker_order_id": order_id},
                )
            except Exception:
                pass
            return OrderStatus(
                order_id=order_id,
                filled_quantity=filled_qty,
                status=status_text,
                avg_price=avg_price,
                raw=primary or None,
            )
        result = await loop.run_in_executor(None, sync_place)
        if callback:
            callback(result)
        return result

    def cancel_order(self, order_id: str) -> bool:
        from gm.api import order_cancel

        if not order_id:
            return False

        payload = {"cl_ord_id": order_id}
        if self.account_id:
            payload["account_id"] = self.account_id

        try:
            order_cancel(payload)
            logger.info("[MyQuantBroker] 已提交撤单请求: %s", order_id)
            try:  # pragma: no cover
                from tools.live_action_logger import log_action

                log_action(
                    action_type="ORDER_CANCEL",
                    symbol="",
                    side="",
                    quantity=0.0,
                    price=0.0,
                    status="SENT",
                    extra={"broker_order_id": order_id},
                )
            except Exception:
                pass
            return True
        except Exception as exc:  # pragma: no cover - 运行期错误
            logger.warning("[MyQuantBroker] 撤单失败 %s: %s", order_id, exc)
            return False

    def query_positions(self) -> Dict[str, Any]:
        from gm.api import get_position

        try:
            positions = get_position(account_id=self.account_id)  # type: ignore[arg-type]
        except Exception as exc:  # pragma: no cover
            logger.warning("[MyQuantBroker] 查询持仓失败: %s", exc)
            return {}

        # 直接返回掘金的结构，由上层自行解析
        return {"positions": positions}


    async def query_account_async(self, callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        """异步获取资金信息，支持回调。"""
        from gm.api import get_cash
        loop = asyncio.get_event_loop()
        try:
            cash_info = await loop.run_in_executor(None, get_cash, self.account_id)
        except Exception as exc:
            logger.warning("[MyQuantBroker] 查询资金失败: %s", exc)
            cash_info = {}
        if callback:
            callback(cash_info or {})
        return cash_info or {}

    # === 规范化账户/持仓视图，便于上层风控与对账使用 ===


    async def get_account_snapshot_async(self, callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        """异步返回规范化账户资金快照，支持回调。"""
        info = await self.query_account_async()
        if isinstance(info, list) and info:
            base: Dict[str, Any] = info[0]  # type: ignore[assignment]
        elif isinstance(info, dict):
            base = info
        else:
            base = {}

        def _f(name: str) -> float:
            try:
                return float(base.get(name) or 0.0)
            except Exception:
                return 0.0

        total_asset = _f("asset") or _f("nav") or _f("cash")
        cash = _f("cash") or _f("available")
        available = _f("available") or cash
        buying_power = _f("buying_power") or _f("buyingpower")

        result = {
            "total_asset": total_asset,
            "cash": cash,
            "available": available,
            "buying_power": buying_power,
            "raw": info,
        }
        if callback:
            callback(result)
        return result

    def get_normalized_positions(self) -> List[Dict[str, Any]]:
        """返回规范化的持仓列表。

        每条记录包含：
        - symbol: 内部统一代码（如 000001.SZ）
        - gm_symbol: 掘金原始代码（如 SZSE.000001）
        - quantity: 持仓数量（正数）
        - price: 参考成本价或均价（>0）
        - direction: LONG/SHORT（如能识别，否则为 "LONG"）
        - entry_time: 原始时间戳字段（如 updated_at/created_at），未做类型转换
        - raw: 原始持仓字典
        """

        payload = self.query_positions() or {}
        raw_positions: Any = None

        if isinstance(payload, dict):
            raw_positions = payload.get("positions") or payload.get("data") or payload
        else:
            raw_positions = payload

        if not isinstance(raw_positions, list):
            return []

        normalized: List[Dict[str, Any]] = []
        for pos in raw_positions:
            if not isinstance(pos, dict):
                continue

            try:
                gm_symbol = str(pos.get("symbol") or "").strip()
            except Exception:
                continue

            internal_symbol = self._from_gm_symbol(gm_symbol)

            try:
                qty = int(
                    pos.get("volume")
                    or pos.get("qty")
                    or pos.get("volume_today")
                    or 0
                )
                price = float(
                    pos.get("price")
                    or pos.get("vwap")
                    or pos.get("cost_price")
                    or 0.0
                )
            except Exception:
                continue

            if qty <= 0 or price <= 0:
                continue

            direction = str(pos.get("side") or pos.get("direction") or "LONG").upper()
            entry_time = pos.get("updated_at") or pos.get("created_at")

            normalized.append(
                {
                    "symbol": internal_symbol,
                    "gm_symbol": gm_symbol,
                    "quantity": qty,
                    "price": price,
                    "direction": direction,
                    "entry_time": entry_time,
                    "raw": pos,
                }
            )

        return normalized
