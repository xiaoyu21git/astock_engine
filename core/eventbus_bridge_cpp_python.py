"""Bridge C++ Engine EventBus → Python EventBus

- 从 eventbus_native.get_engine_bus() 获取引擎内部 C++ EventBus 实例
- 在 C++ EventBus 上订阅指定事件类型（字符串），收到 astock.EventFormat
- 将其转换为当前使用的 Python EventType / Event，并发布到 Python EventBus

用于打通 C++ Trigger / Engine 产生的事件到 Python 侧
"""

from __future__ import annotations

from typing import Callable, Dict, Any, Optional, List
import logging

from .eventbus import EventBus as PyEventBus, EventType as PyEventType, Event as PyEvent, get_global_bus

logger = logging.getLogger(__name__)

try:
    import eventbus_native  # C++ bindings
except ImportError:  # pragma: no cover - 环境未编译 C++ 模块时自动失效
    eventbus_native = None  # type: ignore[misc]


class CppToPythonEventBridge:
    """将 C++ Engine EventBus 事件转发到 Python EventBus。

    用法：
        bridge = CppToPythonEventBridge()
        bridge.start(["strategy_signal", "order", "order_filled"])
    """

    def __init__(self, py_bus: Optional[PyEventBus] = None) -> None:
        self.py_bus: PyEventBus = py_bus or get_global_bus()
        self._cpp_bus = None
        self._subscriptions: List[Any] = []

    def _ensure_cpp_bus(self) -> Optional[Any]:
        if eventbus_native is None:
            logger.warning("eventbus_native not available, C++→Python EventBus bridge disabled")
            return None
        if self._cpp_bus is None:
            try:
                self._cpp_bus = eventbus_native.get_engine_bus()
                logger.info("Attached to C++ Engine EventBus via eventbus_native.get_engine_bus()")
            except Exception as exc:  # pragma: no cover - 依赖 C++ 环境
                logger.warning("Failed to get engine C++ EventBus: %s", exc)
                self._cpp_bus = None
        return self._cpp_bus

    def _map_event_type(self, type_str: str) -> Optional[PyEventType]:
        """将 C++ 事件类型字符串映射到 Python EventType。

        这里先做一个简单的名称映射，后续可以按需要扩展。
        """
        mapping = {
            "strategy_signal": PyEventType.STRATEGY_SIGNAL,
            "signal": PyEventType.SIGNAL,
            "order": PyEventType.ORDER,
            "order_new": PyEventType.ORDER,
            "order_filled": PyEventType.TRADE,
            "risk": PyEventType.RISK,
            "performance": PyEventType.PERFORMANCE,
            "anomaly": PyEventType.ANOMALY,
            "news": PyEventType.NEWS,
            # 可以继续补充 C++ EventType → Python EventType 的映射
        }
        t = type_str.lower()
        return mapping.get(t)

    def _on_cpp_event(self, evt_format) -> None:
        """C++ EventBus 回调：接收 astock::EventFormat，转为 Python Event。
        """
        try:
            type_str = getattr(evt_format, "event_type", "") or getattr(evt_format, "type", "")
            source = getattr(evt_format, "source", "")
            ts_us = getattr(evt_format, "timestamp_us", None)

            py_type = self._map_event_type(str(type_str))
            if py_type is None:
                # 未映射的事件类型先忽略
                logger.debug("Skip unmapped C++ event type: %s", type_str)
                return

            # 转成 Python Event.data
            # 由于 EventFormat 暴露的是 to_attributes/to_json，这里用 to_attributes() 更方便
            attrs: Dict[str, Any] = {}
            try:
                if hasattr(evt_format, "to_attributes"):
                    attrs = dict(evt_format.to_attributes())  # type: ignore[arg-type]
            except Exception:
                # 兜底：不让解析失败影响主流程
                attrs = {}

            data: Dict[str, Any] = {
                "source": source,
                "payload": attrs,
            }

            timestamp = None
            if ts_us is not None:
                try:
                    timestamp = float(ts_us) / 1_000_000.0
                except Exception:
                    timestamp = None

            py_event = PyEvent(type=py_type, data=data, timestamp=timestamp)
            self.py_bus.publish(py_event)
        except Exception as exc:  # pragma: no cover - 防御性
            logger.error("Error in C++→Python EventBus bridge callback: %s", exc, exc_info=True)

    def start(self, event_types: Optional[list[str]] = None) -> None:
        """开始从 C++ EventBus 订阅并转发到 Python EventBus。

        Args:
            event_types: 要订阅的 C++ 事件类型字符串列表；
                         如果为 None，则默认订阅几个核心类型。
        """
        cpp_bus = self._ensure_cpp_bus()
        if cpp_bus is None:
            return

        if not event_types:
            # 默认订阅：策略信号 / 订单相关 / 风控 / 异常 等
            event_types = [
                "strategy_signal",
                "order_new",
                "order_filled",
                "order",
                "risk",
                "performance",
                "anomaly",
                "news",
            ]

        for et in event_types:
            try:
                sub_id = cpp_bus.subscribe(et, self._on_cpp_event)
                self._subscriptions.append(sub_id)
                logger.info("Subscribed C++ Engine EventBus: %s", et)
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed to subscribe C++ Engine EventBus for '%s': %s", et, exc)

    def stop(self) -> None:
        cpp_bus = self._cpp_bus
        if not cpp_bus:
            return
        # 当前底层 EventBus::unsubscribe 接口按订阅 ID/Uuid 工作；
        # eventbus_binding 返回的 sub_id 类型取决于 C++ 实现，这里只调用而不强依赖。
        for sub in self._subscriptions:
            try:
                cpp_bus.unsubscribe(sub)
            except Exception:
                pass
        self._subscriptions.clear()


__all__ = ["CppToPythonEventBridge"]
