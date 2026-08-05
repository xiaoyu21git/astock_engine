"""
金融事件感知模块 — 配置管理
"""

import json
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class EventModuleConfig:
    """事件感知模块全局配置"""

    # ── NLP ──
    hanlp_model_tokenizer: str = "COARSE_ELECTRA_SMALL_ZH"
    hanlp_model_ner: str = "MSRA_NER_ELECTRA_SMALL_ZH"
    sentiment_lexicon_path: str = ""  # 空 = 默认路径

    # ── 信息源 ──
    # 经过实测验证可用的源 (2026-08-04):
    enabled_sources: List[str] = field(default_factory=lambda: [
        "eastmoney",    # 东方财富全球快讯 ✓
        "sina",         # 新浪财经滚动新闻 ✓
        "tonghuashun",  # 同花顺概念快讯 ✓
        "yahoo",        # Yahoo Finance RSS (原油/黄金/铜/天然气/农产品) ✓
        "cnbc",         # CNBC RSS (国际财经头条) ✓
        "marketwatch",  # MarketWatch RSS (美股市场) ✓
        "oilprice",     # OilPrice.com (能源商品深度报道) ✓
    ])

    # ── 轮询间隔 (秒) ──
    poll_interval_pre_market: int = 300    # 盘前 5 分钟
    poll_interval_intra_day: int = 60      # 盘中 1 分钟
    poll_interval_post_market: int = 600   # 盘后 10 分钟

    # ── 去重 ──
    fingerprint_max: int = 100_000
    fingerprint_trim_to: int = 50_000

    # ── 日志 ──
    log_level: str = "INFO"

    # ── 健康检查 ──
    health_check_interval: int = 30  # 秒

    @classmethod
    def defaults(cls) -> "EventModuleConfig":
        return cls()

    @classmethod
    def from_file(cls, path: str) -> "EventModuleConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_file(self, path: str):
        """保存配置到 JSON 文件"""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.__dict__, f, indent=2, ensure_ascii=False)
