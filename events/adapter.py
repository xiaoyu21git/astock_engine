"""
多源信息适配器
==============
每个信息源一个 Adapter 子类, 负责: 拉取/接收 → 去重 → 清洗 → 送入 NLP Pipeline

内置能力:
  - RateLimiter: 令牌桶限流 (防止 API 封禁)
  - 指数退避重试: 429/网络异常自动重试
  - SHA256 内容指纹去重: 内存 10 万条自动清理
  - 并发拉取: asyncio.gather 多源并行
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
                    "[%s] 无关联标的: %s", self._source.value, title[:40])
                return None
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


# ═══════════════════════════════════════════════════════════════
# AKShareNewsAdapter — 东方财富 + 巨潮资讯
# ═══════════════════════════════════════════════════════════════

class AKShareNewsAdapter(BaseAdapter):
    """AKShare 新闻适配器

    信息源:
      - 东方财富 7x24 快讯 (stock_zh_a_alerts_cls)
      - 巨潮资讯公告 (stock_notice_report)

    限流: 保守 30次/分钟 (akshare 不公开 rate limit)
    """

    DEFAULT_RATE_LIMIT = (30, 60.0)

    def __init__(self, pipeline: NLPPipeline):
        super().__init__(InfoSource.EASTMONEY, pipeline)

    async def poll(self) -> List[FinancialEvent]:
        await self._ensure_session()
        events: List[FinancialEvent] = []

        # 并发拉取多源
        results = await asyncio.gather(
            self._fetch_eastmoney_news(),
            self._fetch_cninfo_announcements(),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logging.error("[%s] 拉取异常: %s", self._source.value, result)
                continue
            if not result:
                continue
            for item in result:
                event = self._process_item(
                    str(item.get("title", "")),
                    str(item.get("content", "")),
                )
                if event:
                    events.append(event)

        if events:
            logging.info(
                "[%s] poll 完成: %d 条新闻 → %d 条事件",
                self._source.value,
                sum(len(r) if r else 0 for r in results if not isinstance(r, Exception)),
                len(events),
            )

        return events

    async def _fetch_eastmoney_news(self) -> Optional[List[dict]]:
        """东方财富 7x24 快讯"""
        try:
            import akshare as ak
            df = ak.stock_zh_a_alerts_cls()
            if df is None or df.empty:
                return []
            return df.tail(self.DEFAULT_BATCH_SIZE).to_dict("records")
        except ImportError:
            logging.warning("[%s] akshare 不可用", self._source.value)
            return None
        except Exception as e:
            logging.error("[%s] 东方财富快讯异常: %s", self._source.value, e)
            return None

    async def _fetch_cninfo_announcements(self) -> Optional[List[dict]]:
        """巨潮资讯公告"""
        try:
            import akshare as ak
            df = ak.stock_notice_report()
            if df is None or df.empty:
                return []
            return df.tail(self.DEFAULT_BATCH_SIZE).to_dict("records")
        except ImportError:
            return None
        except Exception as e:
            logging.error("[%s] 巨潮公告异常: %s", self._source.value, e)
            return None
