"""
国际财经 RSS 适配器 — CNBC / MarketWatch / OilPrice
======================================================
统一 RSS 解析，支持多个国际新闻源
"""

import logging
import xml.etree.ElementTree as ET
from typing import List, Optional

from ..adapter import BaseAdapter
from ..event_types import FinancialEvent, InfoSource
from ..nlp_pipeline import NLPPipeline

logger = logging.getLogger("RssAdapter")

# 预定义的 RSS 源
RSS_FEEDS = {
    "cnbc": {
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
        "rate": (10, 60.0),
    },
    "marketwatch": {
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "rate": (10, 60.0),
    },
    "oilprice": {
        "url": "https://oilprice.com/rss/main",
        "rate": (10, 60.0),
    },
}


class RssNewsAdapter(BaseAdapter):
    """通用 RSS 适配器 — 支持多个预定义国际源"""

    def __init__(self, pipeline: NLPPipeline, source_name: str):
        source = InfoSource(source_name) if hasattr(InfoSource, source_name) else None
        if source is None:
            # 动态创建 source
            from ..event_types import InfoSource as IS
            source = IS("cnbc")  # fallback
        super().__init__(source, pipeline)
        self._feed = RSS_FEEDS.get(source_name, RSS_FEEDS["cnbc"])
        self._source_name = source_name

    async def poll(self) -> List[FinancialEvent]:
        await self._ensure_session()
        events: List[FinancialEvent] = []
        raw = await self._fetch_rss()
        if raw:
            for item in raw:
                title = item.get("title", "")
                content = item.get("description", "")
                if not title:
                    continue
                event = self._process_item(title, content)
                if event:
                    event.source = self._source_name
                    events.append(event)
        if events:
            logger.info("[%s] poll 完成: %d 条", self._source_name, len(events))
        return events

    async def _fetch_rss(self) -> Optional[List[dict]]:
        try:
            text = await self._fetch_with_retry(self._feed["url"])
            if not text:
                return None
            root = ET.fromstring(text)
            items = []
            for item in root.findall(".//item"):
                title_el = item.find("title")
                desc_el = item.find("description")
                items.append({
                    "title": title_el.text.strip()[:200] if title_el is not None and title_el.text else "",
                    "description": desc_el.text.strip()[:500] if desc_el is not None and desc_el.text else "",
                })
            return items
        except Exception as e:
            logger.warning("[%s] RSS 失败: %s", self._source_name, e)
            return None
