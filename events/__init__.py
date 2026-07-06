"""
金融事件感知模块 — astock_engine.events

组件:
  event_types.py      — FinancialEventType 枚举 + FinancialEvent dataclass
  financial_lexicon.py — FinancialLexicon 词典引擎 + SentimentAnalyzer
  nlp_pipeline.py     — NLPPipeline (Phase 2)
  adapter.py          — 多源信息适配器 (Phase 2)
  publisher.py        — EventPublisher → C++ EventBus
  config.py           — 配置管理 (Phase 2)
"""

from .event_types import (
    FinancialEvent,
    FinancialEventType,
    InfoSource,
)
from .financial_lexicon import (
    FinancialLexicon,
    SentimentAnalyzer,
)
from .nlp_pipeline import (
    EntityRecognizer,
    EventClassifier,
    TagExtractor,
    NLPPipeline,
)
from .publisher import EventPublisher
from .config import EventModuleConfig

__all__ = [
    "EntityRecognizer",
    "EventClassifier",
    "EventModuleConfig",
    "FinancialEvent",
    "FinancialEventType",
    "FinancialLexicon",
    "InfoSource",
    "NLPPipeline",
    "EventPublisher",
    "SentimentAnalyzer",
    "TagExtractor",
]
