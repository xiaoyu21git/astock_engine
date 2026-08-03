"""
金融事件感知调度器
==================
盘前/盘中/盘后按不同频率拉取信息源 → NLP → 发布到 C++ EventBus。

启动: python -m astock_engine.events.scheduler
"""

import asyncio
import logging
import signal
import sys
import time
from datetime import datetime
from typing import List

from .adapter import BaseAdapter, create_adapters
from .config import EventModuleConfig
from .financial_lexicon import FinancialLexicon
from .nlp_pipeline import EntityRecognizer, NLPPipeline
from .publisher import EventPublisher
from .event_types import FinancialEvent

logger = logging.getLogger("EventScheduler")


class EventScheduler:
    """金融事件感知调度器 — 多源轮询 → NLP → 发布"""

    def __init__(self, config: EventModuleConfig = None):
        self._config = config or EventModuleConfig.defaults()
        self._lexicon = FinancialLexicon()
        self._pipeline = NLPPipeline(
            lexicon=self._lexicon,
            entity_recognizer=EntityRecognizer(),
        )
        self._publisher = EventPublisher()
        self._adapters: List[BaseAdapter] = []
        self._commodity_hook = None  # 延迟初始化
        self._running = False
        self._poll_count = 0
        self._event_count = 0
        self._commodity_event_count = 0

    def start(self):
        logger.info("=" * 50)
        logger.info("EventScheduler 启动")
        logger.info("  信息源: %s", self._config.enabled_sources)
        logger.info("  盘前间隔: %ds  盘中: %ds  盘后: %ds",
                    self._config.poll_interval_pre_market,
                    self._config.poll_interval_intra_day,
                    self._config.poll_interval_post_market)

        self._adapters = create_adapters(self._pipeline, self._config.enabled_sources)
        if not self._adapters:
            logger.error("无可用适配器, 退出")
            return

        self._running = True
        try:
            asyncio.run(self._run_loop())
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False
            self._cleanup()
            logger.info("EventScheduler 已停止")

    def stop(self):
        self._running = False

    def _get_poll_interval(self) -> int:
        """根据当前时间返回轮询间隔"""
        now = datetime.now()
        mins = now.hour * 60 + now.minute
        if mins < 9 * 60 + 15:   # 盘前
            return self._config.poll_interval_pre_market
        elif mins < 11 * 60 + 30:  # 早盘
            return self._config.poll_interval_intra_day
        elif mins < 15 * 60:       # 午休
            return self._config.poll_interval_intra_day
        elif mins < 15 * 60 + 30: # 收盘后
            return self._config.poll_interval_post_market
        else:                      # 夜间
            return self._config.poll_interval_post_market

    async def _run_loop(self):
        while self._running:
            interval = self._get_poll_interval()
            self._poll_count += 1
            poll_start = time.monotonic()

            try:
                events = await self._poll_all()
                if events:
                    # 商品突发事件检测
                    events = self._process_commodity_events(events)
                    published = self._publisher.publish_batch(events)
                    self._event_count += published
                    if published > 0:
                        logger.info("[%d] 发布 %d/%d 条事件",
                                    self._poll_count, published, len(events))
                else:
                    # 无事件时不打日志, 避免刷屏
                    pass
            except Exception as e:
                logger.error("轮询异常: %s", e, exc_info=True)

            elapsed = time.monotonic() - poll_start
            sleep_time = max(1, interval - elapsed)
            await asyncio.sleep(sleep_time)

    async def _poll_all(self) -> List[FinancialEvent]:
        """并发轮询所有适配器"""
        tasks = [adapter.poll() for adapter in self._adapters]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        events: List[FinancialEvent] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning("[%s] 异常: %s",
                               self._adapters[i]._source.value, result)
            elif result:
                events.extend(result)
        return events

    def _process_commodity_events(self, events: List[FinancialEvent]) -> List[FinancialEvent]:
        """商品突发事件检测 (在发布前注入)"""
        try:
            if self._commodity_hook is None:
                from .commodity_hook import CommodityEventHook
                self._commodity_hook = CommodityEventHook()
            for event in events:
                self._commodity_hook.process(event)
            detected = self._commodity_hook.detection_count - self._commodity_event_count
            self._commodity_event_count = self._commodity_hook.detection_count
            if detected > 0:
                logger.info("[Commodity] 检测到 %d 条商品突发事件 (累计 %d)",
                            detected, self._commodity_event_count)
        except Exception as e:
            logger.warning("[Commodity] 商品事件检测异常: %s", e)
        return events

    def _cleanup(self):
        for adapter in self._adapters:
            try:
                asyncio.get_event_loop().run_until_complete(adapter.close())
            except Exception:
                pass
        logger.info("共 %d 轮轮询, %d 条事件发布, %d 条商品信号",
                    self._poll_count, self._event_count, self._commodity_event_count)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    # 降噪: akshare/aiohttp 的 DEBUG 太多
    for mod in ["aiohttp", "akshare", "urllib3", "asyncio"]:
        logging.getLogger(mod).setLevel(logging.WARNING)

    config = EventModuleConfig.defaults()
    scheduler = EventScheduler(config)

    def _sig_handler(sig, frame):
        logger.info("收到信号 %d, 停止...", sig)
        scheduler.stop()

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    scheduler.start()


if __name__ == "__main__":
    main()
