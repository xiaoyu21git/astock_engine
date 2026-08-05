"""
金融事件发布客户端
==================
将 FinancialEvent 转换为 C++ EventFormat 并发布到 EventBus。

双模式:
  - publish_batch(): 盘前/盘后批量新闻推送 (每批 ≤200 条)
  - publish_one():   盘中实时新闻即时推送

失败处理: 单条失败不影响同批次其他事件; 重试 2 次后丢弃并告警
"""

import logging
import time
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .event_types import FinancialEvent


class EventPublisher:
    """金融事件 → C++ EventBus 发布器"""

    BATCH_SIZE = 200          # 每批最多发布条数
    MAX_RETRIES = 2            # 发布失败重试次数
    RETRY_DELAY_MS = 500       # 重试间隔 (毫秒)

    def __init__(self):
        self._bus = None
        self._published_count: int = 0
        self._failed_count: int = 0
        self._last_publish_time: float = 0.0
        self._initialized: bool = False

    # ── EventBus 延迟获取 ──

    def _ensure_bus(self) -> bool:
        """延迟获取全局 EventBus (避免循环导入)"""
        if self._initialized:
            return self._bus is not None

        self._initialized = True
        try:
            from astock_engine.core.eventbus_bridge_cpp_python import (
                get_engine_bus,
            )
            self._bus = get_engine_bus()
            if self._bus is not None:
                logging.info("[EventPublisher] C++ EventBus 已连接")
                return True
        except ImportError:
            logging.debug("[EventPublisher] C++ EventBus 不可用, 使用 Python fallback")

        try:
            from astock_engine.core.eventbus_unified import EventBus
            self._bus = EventBus()
            logging.info("[EventPublisher] Python EventBus 已启用")
            return True
        except ImportError:
            logging.error("[EventPublisher] 无可用的 EventBus")
            self._bus = None
            return False

    # ── 批量发布 (盘前/盘后) ──

    def publish_batch(self, events: List["FinancialEvent"]) -> int:
        """批量发布金融事件

        策略:
          - 每批 ≤200 条, 超出则分批
          - 单条失败不影响同批其他事件 (独立 try-catch)
          - 失败事件重试 MAX_RETRIES 次

        Returns:
            成功发布数
        """
        self._ensure_bus()
        if self._bus is None:
            logging.warning(
                "[EventPublisher] EventBus 不可用, 丢弃 %d 条事件", len(events))
            self._failed_count += len(events)
            return 0

        success = 0
        for i in range(0, len(events), self.BATCH_SIZE):
            batch = events[i : i + self.BATCH_SIZE]
            for event in batch:
                if self._publish_one(event):
                    success += 1

        self._last_publish_time = time.monotonic()
        if success > 0:
            logging.info(
                "[EventPublisher] 批量发布完成: %d/%d 成功",
                success, len(events))
        return success

    # ── 单条发布 (盘中实时) ──

    def publish_one(self, event: "FinancialEvent") -> bool:
        """单条实时发布 (盘中突发新闻)"""
        if not self._ensure_bus() or self._bus is None:
            return False
        return self._publish_one(event)

    def _publish_one(self, event: "FinancialEvent") -> bool:
        """发布单条事件 (含重试)"""
        payload = event.to_event_format_data()

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                # 尝试 C++ EventBus (EventFormat + priority)
                try:
                    fmt = self._to_event_format(event)
                    self._bus.publish(fmt, priority=1)
                except (ImportError, TypeError):
                    # Python EventBus: 构造 Event 对象, 单参调用
                    from astock_engine.core.eventbus_simple import Event as PyEvent
                    self._bus.publish(PyEvent(
                        type=event.event_type.value,
                        data=payload["data"],
                    ))
                self._published_count += 1
                return True
            except Exception as e:
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY_MS / 1000.0)
                else:
                    logging.error(
                        "[EventPublisher] 发布失败(已重试%d次): %s | %s",
                        self.MAX_RETRIES, event.title[:50], e)
                    self._failed_count += 1
        return False

    # ── 格式转换 ──

    @staticmethod
    def _to_event_format(event: "FinancialEvent"):
        """FinancialEvent → C++ EventFormat (pybind11), 仅 C++ EventBus 路径使用"""
        from eventbus_native import EventFormat, EventPriority
        fmt = EventFormat()
        fmt.type = event.event_type.value
        fmt.priority = EventPriority.NORMAL
        payload = event.to_event_format_data()
        for key, value in payload["data"].items():
            fmt.data[key] = value
        for key, value in payload["metadata"].items():
            fmt.metadata[key] = value
        return fmt

    # ── 统计 ──

    def stats(self) -> dict:
        """发布统计"""
        return {
            "published": self._published_count,
            "failed": self._failed_count,
            "last_publish_time": self._last_publish_time,
            "bus_connected": self._bus is not None,
        }

    def reset_stats(self):
        """重置统计计数器"""
        self._published_count = 0
        self._failed_count = 0
