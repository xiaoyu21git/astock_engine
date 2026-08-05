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
        self._entity_recognizer = EntityRecognizer()
        self._pipeline = NLPPipeline(
            lexicon=self._lexicon,
            entity_recognizer=self._entity_recognizer,
        )
        self._publisher = EventPublisher()
        self._adapters: List[BaseAdapter] = []
        self._commodity_hook = None  # 延迟初始化
        self._pg_bridge = None      # 延迟初始化 (需 PG 连接)
        self._pg_conn = None        # 延迟初始化 (行业/商品→股票查询)
        self._market_monitor = None  # 延迟初始化 (盘中急跌监控)
        self._running = False
        self._poll_count = 0
        self._event_count = 0
        self._commodity_event_count = 0

    def start(self):
        self._adapters = create_adapters(self._pipeline, self._config.enabled_sources)
        if not self._adapters:
            logger.error("无可用适配器, 退出")
            return

        # 加载标的注册表
        try:
            self._entity_recognizer.load_from_db()
        except Exception as e:
            logger.warning("[Scheduler] 标的注册表加载失败: %s", e)

        # PG 桥接器
        try:
            from .pg_event_bridge import PgEventBridge
            from tools.db_config import pg_connect
            self._pg_conn = pg_connect()
            self._pg_bridge = PgEventBridge(pg_conn=self._pg_conn)
        except Exception as e:
            logger.warning("[Scheduler] PG桥接失败: %s", e)

        # 盘中市场监控
        try:
            from .market_monitor import MarketMonitor
            self._market_monitor = MarketMonitor()
        except Exception as e:
            logger.warning("[Scheduler] 市场监控失败: %s", e)

        logger.info("EventScheduler 启动: %d 源 %s 标的 桥接=%s 监控=%s",
                    len(self._adapters),
                    str(self._config.enabled_sources),
                    "Y" if self._pg_bridge else "N",
                    "Y" if self._market_monitor else "N")

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
                # 0. 盘中急跌监控 (新闻轮询前)
                if self._market_monitor:
                    alerts = self._market_monitor.check()
                    for alert in alerts:
                        logger.warning("[MarketMonitor] 预警: %s", alert["title"])
                        # 创建 FinancialEvent 走发布管线
                        from .event_types import FinancialEvent, FinancialEventType as FET
                        fe = FinancialEvent(
                            source="market_monitor",
                            title=alert["title"],
                            summary="",
                            symbols=[],
                            sentiment_score=-abs(alert.get("pct", 1)) / 5,
                            event_type=FET.QUOTE_ALERT,
                            confidence=0.9,
                        )
                        fe.tags["level"] = alert["level"]
                        fe.tags["action"] = alert["action"]
                        fe.tags["severity"] = alert["severity"]
                        fe.tags["severity_val"] = alert["severity_val"]
                        fe.tags["sentiment_direction"] = alert["sentiment_direction"]
                        # 写入桥接
                        if self._pg_bridge:
                            self._pg_bridge.write_one(fe)
                        self._publisher.publish_one(fe)

                # 1. 新闻轮询
                events = await self._poll_all()
                if events:
                    # 商品突发事件检测
                    events = self._process_commodity_events(events)
                    # 事件分级 (附加 level/severity/action 标签, 不决定过滤)
                    events = self._classify_events(events)
                    # 过滤: 有符号/有商品标签/有行业影响
                    publishable = [e for e in events
                                   if e.symbols
                                   or e.tags.get("commodity_event")
                                   or e.tags.get("sector_codes")]
                    if publishable:
                        published = self._publisher.publish_batch(publishable)
                        self._event_count += published
                        if self._pg_bridge:
                            self._pg_bridge.write_batch(publishable)
                        if published > 0:
                            logger.info("[%d] %d条 | %s",
                                self._poll_count, published,
                                " ".join(
                                    f"[{e.tags.get('sentiment_direction','?')}/{e.tags.get('level','?')}/{e.tags.get('action','?')}]"
                                    for e in publishable[:5]))
                    else:
                        pass
                else:
                    # 无事件时不打日志, 避免刷屏
                    pass
            except Exception as e:
                logger.error("轮询异常: %s", e, exc_info=True)

            elapsed = time.monotonic() - poll_start
            sleep_time = max(1, interval - elapsed)
            await asyncio.sleep(sleep_time)

    async def _poll_all(self) -> List[FinancialEvent]:
        """并发轮询所有适配器 (单适配器超时 120s 则跳过, 不阻塞其他)"""
        async def _poll_one(adapter):
            try:
                return await asyncio.wait_for(adapter.poll(), timeout=120)
            except asyncio.TimeoutError:
                logger.warning("[%s] 超时, 跳过本轮", adapter._source.value)
                return []
            except Exception as e:
                logger.warning("[%s] 异常: %s", adapter._source.value, e)
                return []

        tasks = [_poll_one(a) for a in self._adapters]
        results = await asyncio.gather(*tasks)

        events: List[FinancialEvent] = []
        for r in results:
            if r:
                events.extend(r)
        return events

    def _process_commodity_events(self, events: List[FinancialEvent]) -> List[FinancialEvent]:
        """商品突发事件检测 (在发布前注入)"""
        try:
            if self._commodity_hook is None:
                from .commodity_hook import CommodityEventHook
                self._commodity_hook = CommodityEventHook(pg_conn=self._pg_conn)
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

    def _classify_events(self, events: List[FinancialEvent]) -> List[FinancialEvent]:
        """事件分级 + 影响范围解析: 符号/行业代码/商品 → 受影响标的列表"""
        from .sector_keywords import match_sectors

        for event in events:
            text = f"{event.title} {event.summary}"
            sentiment = event.sentiment_score
            confidence = event.confidence

            # ── 情感方向 ──
            if sentiment > 0.05:
                direction = "利多"
            elif sentiment < -0.05:
                direction = "利空"
            else:
                direction = "中性"

            severity = min(1.0, abs(sentiment) * confidence)
            event.tags["sentiment_direction"] = direction

            # ── 商品事件: commodity hook 已写入 cm_0_dir (方向) 和 cm_0_urgency ──
            if event.tags.get("commodity_event") == "true":
                # 商品事件方向: +1=供给冲击(利多上游), -1=需求崩塌(利空)
                cm_dir = int(event.tags.get("cm_0_dir", "0"))
                cm_urgency = float(event.tags.get("cm_0_urgency", "0.5"))
                if cm_dir > 0:
                    event.tags["sentiment_direction"] = "利多"
                    event.tags["action"] = "alert"  # 供给冲击→利好, 不减持
                elif cm_dir < 0:
                    event.tags["sentiment_direction"] = "利空"
                    event.tags["action"] = "reduce_exposure" if cm_urgency >= 0.7 else "reduce_position"
                else:
                    event.tags["sentiment_direction"] = "中性"
                    event.tags["action"] = "alert"
                event.tags["level"] = "sector"
                event.tags["severity"] = "urgent" if cm_urgency >= 0.8 else "high" if cm_urgency >= 0.6 else "normal"
                event.tags["severity_val"] = str(cm_urgency)
                # 解析商品→受影响的A股
                product_ids = [v for k, v in event.tags.items() if k.endswith("_pid")]
                if product_ids:
                    affected = self._resolve_product_stocks(product_ids)
                    event.tags["affected_symbols"] = ",".join(affected[:50])
                    event.tags["affected_product_ids"] = ",".join(product_ids)
                continue

            # ── 分级: stock > sector > market ──
            sector_codes = match_sectors(text) if not event.symbols else []
            if event.symbols:
                level = "stock"
            elif sector_codes:
                level = "sector"
            else:
                level = "market"

            # 无风险信号
            if severity < 0.3 and not sector_codes and level != "stock":
                event.tags["level"] = "none"
                event.tags["action"] = "ignore"
                continue

            # 动作映射
            if level == "stock":
                action = "liquidate" if severity >= 0.7 else "reduce_position"
            elif level == "sector":
                action = "reduce_exposure" if severity >= 0.7 else "reduce_position"
            else:
                action = "reduce_exposure" if severity >= 0.5 else "alert"

            event.tags["level"] = level
            event.tags["severity"] = "urgent" if severity >= 0.7 else "high" if severity >= 0.4 else "normal"
            event.tags["severity_val"] = str(severity)
            event.tags["action"] = action

            if sector_codes:
                event.tags["sector_codes"] = ",".join(sector_codes)
                # 解析行业→受影响的A股
                affected = self._resolve_sector_stocks(sector_codes)
                if affected:
                    event.tags["affected_symbols"] = ",".join(affected[:100])
                    event.tags["affected_sectors"] = ",".join(sector_codes)

        return events

    def _resolve_product_stocks(self, product_ids: list) -> list:
        """商品 product_id → 关联 A 股标的 (缓存 PG 查询)"""
        if not self._pg_conn:
            return []
        try:
            cur = self._pg_conn.cursor()
            placeholders = ",".join(["%s"] * len(product_ids))
            cur.execute(
                f"SELECT DISTINCT symbol FROM ref.product_stock_mapping "
                f"WHERE product_id IN ({placeholders})",
                product_ids)
            return [r[0] for r in cur.fetchall()]
        except Exception as e:
            logger.warning("[Classify] 商品→股票查询失败: %s", e)
            try: self._pg_conn.rollback()
            except: pass
            return []

    def _resolve_sector_stocks(self, sector_codes: list) -> list:
        """行业代码 → 关联 A 股标的 (缓存 PG 查询)"""
        if not self._pg_conn:
            return []
        try:
            cur = self._pg_conn.cursor()
            codes_str = ",".join(["'" + c + "'" for c in sector_codes])
            cur.execute(
                f"SELECT DISTINCT si.symbol FROM ref.symbol_info si "
                f"JOIN ref.industry_classification ic ON si.id = ic.symbol_id "
                f"WHERE ic.industry_code IN ({codes_str}) AND si.status = 'ACTIVE'")
            return [r[0] for r in cur.fetchall()]
        except Exception as e:
            logger.warning("[Classify] 行业→股票查询失败: %s", e)
            try: self._pg_conn.rollback()
            except: pass
            return []

    def _cleanup(self):
        for adapter in self._adapters:
            try:
                asyncio.get_event_loop().run_until_complete(adapter.close())
            except Exception:
                pass
        logger.info("共 %d 轮轮询, %d 条事件发布, %d 条商品信号",
                    self._poll_count, self._event_count, self._commodity_event_count)


def main():
    # 禁止 akshare/tqdm 进度条刷屏
    import os as _os
    _os.environ.setdefault("TQDM_DISABLE", "1")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    # 降噪: 第三方库的 DEBUG / FutureWarning 太多
    for mod in ["aiohttp", "akshare", "urllib3", "asyncio",
                "transformers", "transformers.tokenization_utils_base"]:
        logging.getLogger(mod).setLevel(logging.WARNING)
    import warnings
    warnings.filterwarnings("ignore", category=FutureWarning, module="transformers")
    warnings.filterwarnings("ignore", category=FutureWarning, module="torch")

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
