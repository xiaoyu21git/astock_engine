"""
多源信息适配器
==============
每个信息源一个 Adapter 子类, 负责: 拉取/接收 → 去重 → 清洗 → 送入 NLP Pipeline

内置能力:
  - RateLimiter: 令牌桶限流 (防止 API 封禁)
  - 指数退避重试: 429/网络异常自动重试
  - SHA256 内容指纹去重: 内存 10 万条自动清理
  - 并发拉取: asyncio.gather 多源并行

支持信息源:
  - eastmoney   : 东方财富全球快讯
  - cninfo      : 巨潮资讯公告
  - cls         : 财联社电报
  - xueqiu      : 雪球热帖
  - sina        : 新浪财经
  - tonghuashun : 同花顺热榜/快讯
  - gm_sdk      : 掘金SDK 行情异动 (C++ 侧直发, 不走 Python)
"""

import asyncio
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from typing import List, Optional

import aiohttp

from .event_types import FinancialEvent, InfoSource
from .nlp_pipeline import NLPPipeline


# ═══════════════════════════════════════════════════════════════
# RateLimiter — 令牌桶限流器
# ═══════════════════════════════════════════════════════════════

class RateLimiter:
    """令牌桶限流器 — 控制 API 调用频率"""

    def __init__(self, max_calls: int, period_seconds: float):
        self._max_calls = max_calls
        self._period = period_seconds
        self._tokens = float(max_calls)
        self._last_refill = time.monotonic()

    async def acquire(self) -> bool:
        """获取令牌 (阻塞直到可用)"""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            float(self._max_calls),
            self._tokens + elapsed / self._period * self._max_calls)
        self._last_refill = now

        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True

        wait = (1.0 - self._tokens) * self._period / self._max_calls
        await asyncio.sleep(wait)
        self._tokens = 0.0
        self._last_refill = time.monotonic()
        return True


# ═══════════════════════════════════════════════════════════════
# BaseAdapter — 适配器基类
# ═══════════════════════════════════════════════════════════════

class BaseAdapter(ABC):
    """信息源适配器基类

    子类只需实现 poll() 方法, 去重/NLP/限流/重试由基类处理。
    """

    DEFAULT_RATE_LIMIT = (60, 60.0)     # 默认: 60次/分钟
    DEFAULT_RETRIES = 3                  # 最大重试次数
    DEFAULT_RETRY_BACKOFF = 1.0          # 退避基数(秒)
    DEFAULT_BATCH_SIZE = 200             # 每批最大条数
    MAX_FINGERPRINTS = 100_000           # 内存去重上限
    FINGERPRINT_TRIM = 50_000            # 清理后保留数

    def __init__(self, source: InfoSource, pipeline: NLPPipeline):
        self._source = source
        self._pipeline = pipeline
        self._rate_limiter = RateLimiter(*self.DEFAULT_RATE_LIMIT)
        self._seen_fingerprints: set = set()
        self._session: Optional[aiohttp.ClientSession] = None

    # ── HTTP Session ──

    async def _ensure_session(self):
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    # ── HTTP 请求 (带重试) ──

    async def _fetch_with_retry(self, url: str, **kwargs) -> Optional[str]:
        """GET 请求 — 指数退避重试"""
        for attempt in range(self.DEFAULT_RETRIES):
            try:
                await self._rate_limiter.acquire()
                async with self._session.get(url, **kwargs) as resp:
                    if resp.status == 200:
                        return await resp.text()
                    elif resp.status == 429:
                        wait = (2 ** attempt) * self.DEFAULT_RETRY_BACKOFF
                        logging.warning(
                            "[%s] HTTP 429 限流, %.1fs 后重试 (attempt %d)",
                            self._source.value, wait, attempt + 1)
                        await asyncio.sleep(wait)
                        continue
                    else:
                        logging.warning(
                            "[%s] HTTP %d: %s",
                            self._source.value, resp.status, url[:80])
                        return None
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                wait = (2 ** attempt) * self.DEFAULT_RETRY_BACKOFF
                logging.warning(
                    "[%s] 网络异常 (attempt %d/%d): %s",
                    self._source.value, attempt + 1, self.DEFAULT_RETRIES, e)
                if attempt < self.DEFAULT_RETRIES - 1:
                    await asyncio.sleep(wait)
        return None

    # ── 去重 ──

    @staticmethod
    def _fingerprint(title: str, content: str) -> str:
        """SHA256 内容指纹 (前 16 位十六进制)"""
        return hashlib.sha256(
            f"{title}|{content[:200]}".encode("utf-8")
        ).hexdigest()[:16]

    def _is_duplicate(self, fp: str) -> bool:
        """内存去重 — 超过上限自动清理旧指纹"""
        if fp in self._seen_fingerprints:
            return True
        self._seen_fingerprints.add(fp)
        if len(self._seen_fingerprints) > self.MAX_FINGERPRINTS:
            self._seen_fingerprints = set(
                list(self._seen_fingerprints)[-self.FINGERPRINT_TRIM:])
        return False

    # ── 单条处理 ──

    def _process_item(
        self, title: str, content: str
    ) -> Optional[FinancialEvent]:
        """单条信息: 去重 → NLP → FinancialEvent"""
        fp = self._fingerprint(title, content)
        if self._is_duplicate(fp):
            return None
        try:
            event = self._pipeline.process(title, content, self._source)
            if not event.symbols:
                logging.debug(
                    "[%s] 无关联标的 (保留给商品事件检测): %s",
                    self._source.value, title[:40])
            # 始终返回event, 是否发布由scheduler层统一决策
            return event
        except Exception as e:
            logging.error(
                "[%s] NLP 异常: %s | %s", self._source.value, title[:40], e)
            return None

    # ── 子类接口 ──

    @abstractmethod
    async def poll(self) -> List[FinancialEvent]:
        """拉取一批新闻 → NLP → FinancialEvent 列表"""
        ...

    @staticmethod
    def _ak_dataframe_to_records(df) -> List[dict]:
        """AKShare DataFrame → records, 兼容空值"""
        if df is None or (hasattr(df, 'empty') and df.empty):
            return []
        return df.tail(BaseAdapter.DEFAULT_BATCH_SIZE).to_dict("records")


# ═══════════════════════════════════════════════════════════════
# EastmoneyNewsAdapter — 东方财富全球快讯
# ═══════════════════════════════════════════════════════════════

class EastmoneyNewsAdapter(BaseAdapter):
    """东方财富新闻适配器 — 全球财经快讯"""

    DEFAULT_RATE_LIMIT = (20, 60.0)

    def __init__(self, pipeline: NLPPipeline):
        super().__init__(InfoSource.EASTMONEY, pipeline)

    async def poll(self) -> List[FinancialEvent]:
        await self._ensure_session()
        events: List[FinancialEvent] = []
        raw = await self._fetch_em_news()
        if raw:
            for item in raw:
                event = self._process_item(
                    str(item.get("title", item.get("content", ""))),
                    str(item.get("content", item.get("summary", item.get("title", "")))),
                )
                if event:
                    events.append(event)
        # 仅非空时报, 复用 scheduler 汇总
        return events

    async def _fetch_em_news(self) -> Optional[List[dict]]:
        try:
            import akshare as ak
            df = ak.stock_info_global_em()
            return self._ak_dataframe_to_records(df)
        except ImportError:
            logging.warning("[%s] akshare 不可用, 尝试 HTTP fallback", self._source.value)
            return await self._fetch_em_http()
        except Exception as e:
            logging.error("[%s] 东方财富异常: %s", self._source.value, e)
            return await self._fetch_em_http()

    async def _fetch_em_http(self) -> Optional[List[dict]]:
        """东方财富 HTTP fallback — 7x24 快讯 API"""
        try:
            url = (
                "https://push2ex.eastmoney.com/getQuickNews?"
                "pagesize=200&pageindex=1&type=1"
            )
            text = await self._fetch_with_retry(url)
            if not text:
                return None
            import json
            data = json.loads(text)
            items = data.get("Data", {}).get("List", [])
            return [{"title": i.get("Title", ""), "content": i.get("Content", "")}
                    for i in items]
        except Exception as e:
            logging.error("[%s] HTTP fallback 失败: %s", self._source.value, e)
            return None


# ═══════════════════════════════════════════════════════════════
# CninfoAdapter — 巨潮资讯公告
# ═══════════════════════════════════════════════════════════════

class CninfoAdapter(BaseAdapter):
    """巨潮资讯公告适配器"""

    DEFAULT_RATE_LIMIT = (20, 60.0)

    def __init__(self, pipeline: NLPPipeline):
        super().__init__(InfoSource.CNINFO, pipeline)

    async def poll(self) -> List[FinancialEvent]:
        await self._ensure_session()
        events: List[FinancialEvent] = []
        raw = await self._fetch_cninfo()
        if raw:
            for item in raw:
                title = str(item.get("title", item.get("name", "")))
                content = str(item.get("content", item.get("summary", "")))
                if not title:
                    continue
                event = self._process_item(title, content)
                if event:
                    events.append(event)
        # 仅非空时报, 复用 scheduler 汇总
        return events

    async def _fetch_cninfo(self) -> Optional[List[dict]]:
        try:
            import akshare as ak
            df = ak.stock_notice_report()
            return self._ak_dataframe_to_records(df)
        except ImportError:
            logging.warning("[%s] akshare 不可用", self._source.value)
            return None
        except Exception as e:
            logging.error("[%s] 巨潮公告异常: %s", self._source.value, e)
            return None


# ═══════════════════════════════════════════════════════════════
# ClsNewsAdapter — 财联社电报
# ═══════════════════════════════════════════════════════════════

class ClsNewsAdapter(BaseAdapter):
    """财联社电报适配器 — 7x24 实时电报"""

    DEFAULT_RATE_LIMIT = (30, 60.0)

    def __init__(self, pipeline: NLPPipeline):
        super().__init__(InfoSource.CLS, pipeline)

    async def poll(self) -> List[FinancialEvent]:
        await self._ensure_session()
        events: List[FinancialEvent] = []

        results = await asyncio.gather(
            self._fetch_cls_telegraph(),
            self._fetch_cls_hot(),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logging.error("[%s] 拉取异常: %s", self._source.value, result)
                continue
            if not result:
                continue
            for item in result:
                title = str(item.get("title", ""))
                content = str(item.get("content", item.get("summary", "")))
                if not title:
                    continue
                event = self._process_item(title, content)
                if event:
                    events.append(event)

        # 仅非空时报, 复用 scheduler 汇总
        return events

    async def _fetch_cls_telegraph(self) -> Optional[List[dict]]:
        """财联社电报"""
        try:
            import akshare as ak
            df = ak.stock_telegraph_cls()
            return self._ak_dataframe_to_records(df)
        except ImportError:
            return None
        except Exception as e:
            logging.warning("[%s] 财联社电报异常: %s", self._source.value, e)
            return None

    async def _fetch_cls_hot(self) -> Optional[List[dict]]:
        """财联社热门文章"""
        try:
            url = (
                "https://www.cls.cn/api/sw?app=CailianpressWeb"
                "&os=web&sv=8.5.5&sign="
            )
            text = await self._fetch_with_retry(url)
            if not text:
                return None
            import json
            data = json.loads(text)
            items = data.get("data", {}).get("roll_data", [])
            return [{"title": i.get("title", ""),
                     "content": i.get("brief", i.get("content", ""))}
                    for i in items]
        except Exception as e:
            logging.warning("[%s] 财联社热门异常: %s", self._source.value, e)
            return None


# ═══════════════════════════════════════════════════════════════
# XueqiuAdapter — 雪球热帖
# ═══════════════════════════════════════════════════════════════

class XueqiuAdapter(BaseAdapter):
    """雪球热帖适配器"""

    DEFAULT_RATE_LIMIT = (15, 60.0)

    def __init__(self, pipeline: NLPPipeline):
        super().__init__(InfoSource.XUEQIU, pipeline)

    async def poll(self) -> List[FinancialEvent]:
        await self._ensure_session()
        events: List[FinancialEvent] = []

        results = await asyncio.gather(
            self._fetch_xueqiu_hot(),
            self._fetch_xueqiu_status(),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logging.error("[%s] 拉取异常: %s", self._source.value, result)
                continue
            if not result:
                continue
            for item in result:
                title = str(item.get("title", item.get("text", item.get("description", ""))))
                content = str(item.get("text", item.get("description", item.get("content", ""))))
                if not title:
                    continue
                event = self._process_item(title, content)
                if event:
                    events.append(event)

        # 仅非空时报, 复用 scheduler 汇总
        return events

    async def _fetch_xueqiu_hot(self) -> Optional[List[dict]]:
        """雪球热门讨论"""
        try:
            import akshare as ak
            df = ak.stock_hot_discuss_xq(symbol="最热")
            return self._ak_dataframe_to_records(df)
        except ImportError:
            return None
        except Exception as e:
            logging.warning("[%s] 雪球热帖 AKShare 异常: %s", self._source.value, e)
            return await self._fetch_xueqiu_http()

    async def _fetch_xueqiu_status(self) -> Optional[List[dict]]:
        """雪球关注动态"""
        try:
            import akshare as ak
            df = ak.stock_hot_follow_xq(symbol="最热")
            return self._ak_dataframe_to_records(df)
        except ImportError:
            return None
        except Exception as e:
            logging.debug("[%s] 雪球动态异常 (可忽略): %s", self._source.value, e)
            return None

    async def _fetch_xueqiu_http(self) -> Optional[List[dict]]:
        """雪球 HTTP fallback — 热帖 API"""
        try:
            url = (
                "https://xueqiu.com/statuses/hot/listV2.json?"
                "since_id=-1&size=50"
            )
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36",
                "Referer": "https://xueqiu.com/",
            }
            text = await self._fetch_with_retry(url, headers=headers)
            if not text:
                return None
            import json
            data = json.loads(text)
            items = data.get("items", [])
            return [{"title": i.get("title", i.get("description", "")),
                     "content": i.get("description", i.get("text", ""))}
                    for i in items]
        except Exception as e:
            logging.error("[%s] HTTP fallback 失败: %s", self._source.value, e)
            return None


# ═══════════════════════════════════════════════════════════════
# SinaNewsAdapter — 新浪财经
# ═══════════════════════════════════════════════════════════════

class SinaNewsAdapter(BaseAdapter):
    """新浪财经适配器"""

    DEFAULT_RATE_LIMIT = (20, 60.0)

    def __init__(self, pipeline: NLPPipeline):
        super().__init__(InfoSource.SINA, pipeline)

    async def poll(self) -> List[FinancialEvent]:
        await self._ensure_session()
        events: List[FinancialEvent] = []

        results = await asyncio.gather(
            self._fetch_sina_finance(),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logging.error("[%s] 拉取异常: %s", self._source.value, result)
                continue
            if not result:
                continue
            for item in result:
                title = str(item.get("title", ""))
                content = str(item.get("content", item.get("summary", "")))
                if not title:
                    continue
                event = self._process_item(title, content)
                if event:
                    events.append(event)

        # 仅非空时报, 复用 scheduler 汇总
        return events

    async def _fetch_sina_finance(self) -> Optional[List[dict]]:
        """新浪财经 — HTTP 直连 (akshare API 已失效, 跳过)"""
        return await self._fetch_sina_http()

    async def _fetch_sina_http(self) -> Optional[List[dict]]:
        """新浪财经滚动新闻 API"""
        try:
            url = (
                "https://feed.mix.sina.com.cn/api/roll/get?"
                "pageid=153&lid=2509&k=&num=50&page=1"
            )
            text = await self._fetch_with_retry(url)
            if not text:
                return None
            import json
            data = json.loads(text)
            items = data.get("result", {}).get("data", [])
            return [{"title": i.get("title", ""),
                     "content": i.get("intro", i.get("ctime", ""))}
                    for i in items]
        except Exception as e:
            logging.warning("[%s] HTTP 失败: %s", self._source.value, e)
            return None


# ═══════════════════════════════════════════════════════════════
# TonghuashunAdapter — 同花顺
# ═══════════════════════════════════════════════════════════════

class TonghuashunAdapter(BaseAdapter):
    """同花顺适配器 — 热榜 + 快讯"""

    DEFAULT_RATE_LIMIT = (20, 60.0)

    def __init__(self, pipeline: NLPPipeline):
        super().__init__(InfoSource.TONGHUASHUN, pipeline)

    async def poll(self) -> List[FinancialEvent]:
        await self._ensure_session()
        events: List[FinancialEvent] = []

        results = await asyncio.gather(
            self._fetch_ths_hot_rank(),
            self._fetch_ths_news(),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logging.error("[%s] 拉取异常: %s", self._source.value, result)
                continue
            if not result:
                continue
            for item in result:
                title = str(item.get("title", item.get("name", item.get("概念名称", ""))))
                content = str(item.get("content", item.get("reason", item.get("描述", ""))))
                if not title:
                    continue
                event = self._process_item(title, content)
                if event:
                    events.append(event)

        # 仅非空时报, 复用 scheduler 汇总
        return events

    async def _fetch_ths_hot_rank(self) -> Optional[List[dict]]:
        """同花顺热门概念/板块排行 (akshare 已失效, 尝试 HTTP)"""
        try:
            import akshare as ak
            df = ak.stock_hot_rank_ths()
            return self._ak_dataframe_to_records(df)
        except Exception:
            return None  # 已知失效, 静默跳过, 不浪费时间重试 HTTP

    async def _fetch_ths_news(self) -> Optional[List[dict]]:
        """同花顺概念新闻 — 过滤掉纯行情描述(涨跌%无语义价值)"""
        try:
            import akshare as ak
            import re
            df = ak.stock_board_concept_name_ths()
            if df is None or (hasattr(df, 'empty') and df.empty):
                return None
            records = df.tail(50).to_dict("records")
            items = []
            for r in records:
                reason = str(r.get("reason", r.get("描述", "")))
                # 过滤: 纯行情描述(无实质内容)
                if not reason or len(reason) < 10:
                    continue
                # 过滤: 仅包含涨跌百分比 (如 "板块涨2.5%")
                if re.match(r'^[板块概念].{0,5}[涨跌][\d.]+%', reason):
                    continue
                items.append({
                    "title": str(r.get("name", r.get("概念名称", ""))),
                    "content": reason,
                    "_ths_concept": True,
                })
            return items
        except ImportError:
            return None
        except Exception as e:
            logging.debug("[%s] 同花顺概念异常: %s", self._source.value, e)
            return None

    async def _fetch_ths_http(self) -> Optional[List[dict]]:
        """同花顺 HTTP fallback — 热榜 API"""
        try:
            url = (
                "https://eq.10jqka.com.cn/open/api/users/hot/v1/hot_plate.json?"
                "appName=ths&client=pc"
            )
            text = await self._fetch_with_retry(url)
            if not text:
                return None
            import json
            data = json.loads(text)
            items = data.get("data", [])
            return [{"title": i.get("plate_name", i.get("name", "")),
                     "content": i.get("reason", i.get("desc", ""))}
                    for i in items]
        except Exception as e:
            logging.error("[%s] HTTP fallback 失败: %s", self._source.value, e)
            return None


# ═══════════════════════════════════════════════════════════════
# AdapterRegistry — 适配器注册表
# ═══════════════════════════════════════════════════════════════

_ADAPTER_REGISTRY = {
    InfoSource.EASTMONEY:   EastmoneyNewsAdapter,
    InfoSource.CNINFO:      CninfoAdapter,
    InfoSource.CLS:         ClsNewsAdapter,
    InfoSource.XUEQIU:      XueqiuAdapter,
    InfoSource.SINA:        SinaNewsAdapter,
    InfoSource.TONGHUASHUN: TonghuashunAdapter,
    InfoSource.YAHOO:       (lambda p: __import__('astock_engine.events.adapters.yahoo_finance_adapter', fromlist=['YahooFinanceAdapter']).YahooFinanceAdapter(p)),
    InfoSource.CNBC:        (lambda p: __import__('astock_engine.events.adapters.rss_adapter', fromlist=['RssNewsAdapter']).RssNewsAdapter(p, "cnbc")),
    InfoSource.MARKETWATCH: (lambda p: __import__('astock_engine.events.adapters.rss_adapter', fromlist=['RssNewsAdapter']).RssNewsAdapter(p, "marketwatch")),
    InfoSource.OILPRICE:    (lambda p: __import__('astock_engine.events.adapters.rss_adapter', fromlist=['RssNewsAdapter']).RssNewsAdapter(p, "oilprice")),
    # gm_sdk 由 C++ GmSessionEngine 直发 news.quote_alert，不走 Python
}


def create_adapters(
    pipeline: NLPPipeline,
    enabled_sources: List[str],
) -> List[BaseAdapter]:
    """根据配置创建适配器实例列表

    Args:
        pipeline: NLP 处理管线
        enabled_sources: 启用的信息源标识列表 (如 ["eastmoney", "cls", ...])

    Returns:
        适配器实例列表
    """
    adapters: List[BaseAdapter] = []
    for source_name in enabled_sources:
        source_name = source_name.lower().strip()
        # 找匹配的 InfoSource
        matching = None
        for src, cls in _ADAPTER_REGISTRY.items():
            if src.value == source_name:
                matching = cls
                break
        if matching:
            adapters.append(matching(pipeline))
        else:
            logging.warning("[Adapter] 未知信息源: %s", source_name)
    return adapters
