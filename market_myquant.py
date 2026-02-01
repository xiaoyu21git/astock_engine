"""基于掘金 gm.api 的实时行情数据源封装。

注意：
- 该模块假定在外部已经通过 MyQuantBroker 或 gm.api.set_token 完成鉴权；
- 为了避免强依赖 gm 的事件循环，这里采用简单的轮询 current() 方式获取最新价；
- 字段名与具体行为可能需根据本地 gm.api 版本微调。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Sequence

from .core import Event, EventType
from .broker import MyQuantBroker

logger = logging.getLogger(__name__)


class MyQuantRealtimeDataFeed:
    """从掘金 gm.api 获取实时行情，并通过 EventBus 推送 MARKET_DATA 事件。

    设计目标：
    - 尽量不侵入 gm 的策略运行框架，仅作为行情轮询器；
    - 将掘金代码（SZSE.000001 / SHSE.600000）转换为内部统一格式（000001.SZ / 600000.SH）。
    """

    def __init__(
        self,
        bus: Any,  # EventBus 协议
        symbols: Sequence[str],
        interval: float = 1.0,
    ) -> None:
        self.bus = bus
        self.symbols = [str(s) for s in symbols]
        self.interval = float(interval)
        # 复用 MyQuantBroker 的代码映射逻辑
        self._gm_symbols: List[str] = [MyQuantBroker._to_gm_symbol(s) for s in self.symbols]  # type: ignore[attr-defined]
        self._stopped = False

        try:
            import gm.api as _  # noqa: F401
        except Exception as exc:  # pragma: no cover - 运行期检查
            raise RuntimeError("导入 gm.api 失败，请确认已安装并可用掘金 SDK") from exc

        logger.info(
            "MyQuantRealtimeDataFeed 初始化: symbols=%s interval=%.2fs",
            ",".join(self.symbols),
            self.interval,
        )

    @staticmethod
    def _from_gm_symbol(symbol: str) -> str:
        """将 SZSE.000001 / SHSE.600000 转为内部格式 000001.SZ / 600000.SH。"""
        s = (symbol or "").strip().upper()
        if s.startswith("SZSE."):
            return f"{s[5:]}.SZ"
        if s.startswith("SHSE."):
            return f"{s[5:]}.SH"
        return s

    def stop(self) -> None:
        self._stopped = True

    def run(self) -> None:
        """启动轮询循环，持续向 EventBus 推送 MARKET_DATA。

        通常在独立线程或主线程中调用；通过 KeyboardInterrupt 或调用 stop() 停止。
        """
        from gm.api import current  # type: ignore[import]

        joined = ",".join(self._gm_symbols)
        logger.info("MyQuantRealtimeDataFeed 开始轮询行情: %s", joined)

        try:
            while not self._stopped:
                now = datetime.now()
                try:
                    # 兼容不同版本 gm.api.current 的返回：
                    # - 某些版本支持 df=True，直接返回 DataFrame；
                    # - 也有版本默认返回 DataFrame 或 list[dict]，不支持 df 参数。
                    data = current(symbols=joined, fields="symbol,price,volume,amount")
                except TypeError:
                    # 回退方案：老版本 current 可能不接受 fields 关键字
                    try:  # pragma: no cover - 运行期兼容
                        data = current(joined)
                    except Exception as exc:  # pragma: no cover
                        logger.warning("MyQuantRealtimeDataFeed 调用 gm.current 失败: %s", exc)
                        time.sleep(self.interval)
                        continue
                except Exception as exc:  # pragma: no cover - 运行期错误
                    logger.warning("MyQuantRealtimeDataFeed 调用 gm.current 失败: %s", exc)
                    time.sleep(self.interval)
                    continue

                # 空结果直接轮询下一次
                if data is None:
                    time.sleep(self.interval)
                    continue

                # 判断是否为 DataFrame（带 iterrows 方法）
                if hasattr(data, "iterrows"):
                    rows_iter = data.iterrows()  # type: ignore[assignment]
                    has_any = False
                    for _, row in rows_iter:
                        has_any = True
                        gm_symbol = str(row.get("symbol"))
                        symbol = self._from_gm_symbol(gm_symbol)
                        try:
                            price_val = row.get("price")
                            if price_val is None:
                                price_val = row.get("last_price")
                            close = float(price_val) if price_val is not None else None
                        except Exception:
                            close = None

                        if not symbol or close is None:
                            continue

                        try:
                            volume_raw = row.get("volume", 0)
                            volume = int(volume_raw or 0)
                        except Exception:
                            volume = 0

                        evt = Event(
                            type=EventType.MARKET_DATA,
                            data={
                                "symbol": symbol,
                                "close": close,
                                "volume": volume,
                                "timestamp": now,
                            },
                            timestamp=now,
                        )
                        self.bus.publish(evt)

                    if not has_any:
                        time.sleep(self.interval)
                        continue
                else:
                    # 尝试按可迭代的记录序列处理（如 list[dict]）
                    try:
                        iterator = iter(data)  # type: ignore[arg-type]
                    except TypeError:
                        time.sleep(self.interval)
                        continue

                    had_row = False
                    for row in iterator:
                        had_row = True
                        # 期望 row 为 dict-like
                        try:
                            gm_symbol = str(row.get("symbol"))  # type: ignore[union-attr]
                        except Exception:
                            continue
                        symbol = self._from_gm_symbol(gm_symbol)
                        try:
                            price_val = row.get("price")  # type: ignore[union-attr]
                            if price_val is None:
                                price_val = row.get("last_price")  # type: ignore[union-attr]
                            close = float(price_val) if price_val is not None else None
                        except Exception:
                            close = None

                        if not symbol or close is None:
                            continue

                        try:
                            volume_raw = row.get("volume", 0)  # type: ignore[union-attr]
                            volume = int(volume_raw or 0)
                        except Exception:
                            volume = 0

                        evt = Event(
                            type=EventType.MARKET_DATA,
                            data={
                                "symbol": symbol,
                                "close": close,
                                "volume": volume,
                                "timestamp": now,
                            },
                            timestamp=now,
                        )
                        self.bus.publish(evt)

                    if not had_row:
                        time.sleep(self.interval)
                        continue

                time.sleep(self.interval)
        except KeyboardInterrupt:  # pragma: no cover - 便于手动中断
            logger.info("MyQuantRealtimeDataFeed 收到中断信号，准备停止")
        finally:
            logger.info("MyQuantRealtimeDataFeed 已停止")


__all__ = ["MyQuantRealtimeDataFeed"]
