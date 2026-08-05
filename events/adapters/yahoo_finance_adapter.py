"""
Yahoo Finance RSS 适配器 — 商品+市场新闻
===========================================
免费、快速，覆盖原油/黄金/铜/天然气/农产品等主要商品
"""

import logging
import xml.etree.ElementTree as ET
from typing import List, Optional
from datetime import datetime

from ..adapter import BaseAdapter
from ..event_types import FinancialEvent, InfoSource
from ..nlp_pipeline import NLPPipeline

logger = logging.getLogger("YahooFinance")


class YahooFinanceAdapter(BaseAdapter):
    """Yahoo Finance RSS — 国际财经头条 (限流严格, 低频轮询)"""

    DEFAULT_RATE_LIMIT = (4, 60.0)   # Yahoo 严格限流, 每分钟最多 4 次
    DEFAULT_RETRIES = 1               # 不重试, 等下一轮
    FEED_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=CL=F&region=US&lang=en-US"

    def __init__(self, pipeline: NLPPipeline):
        super().__init__(InfoSource.YAHOO, pipeline)

    async def _fetch_with_retry(self, url, **kwargs):
        """覆盖重试逻辑: Yahoo 限流时不重试"""
        kwargs.setdefault('headers', {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/xml,text/xml,*/*',
        })
        return await super()._fetch_with_retry(url, **kwargs)

    async def poll(self) -> List[FinancialEvent]:
        await self._ensure_session()
        events: List[FinancialEvent] = []
        raw = await self._fetch_rss()
        if raw:
            for item in raw:
                title = item.get("title", "")
                content = item.get("description", item.get("summary", ""))
                if not title:
                    continue
                event = self._process_item(title, content)
                if event:
                    event.source = "yahoo"  # 标记来源
                    events.append(event)
        if events:
            logger.info("[%s] poll 完成: %d 条事件", "yahoo", len(events))
        return events

    async def _fetch_rss(self) -> Optional[List[dict]]:
        try:
            text = await self._fetch_with_retry(self.FEED_URL)
            if not text:
                return None
            root = ET.fromstring(text)
            items = []
            for item in root.findall(".//item"):
                title_el = item.find("title")
                desc_el = item.find("description")
                pub_el = item.find("pubDate")
                items.append({
                    "title": title_el.text.strip() if title_el is not None and title_el.text else "",
                    "description": desc_el.text.strip()[:500] if desc_el is not None and desc_el.text else "",
                    "published": pub_el.text if pub_el is not None else "",
                })
            return items
        except Exception as e:
            logger.warning("[yahoo] RSS 失败: %s", e)
            return None
