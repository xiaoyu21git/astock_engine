"""
策略模块
包含各种量化交易策略
"""

from .base_strategy import BaseStrategy, Signal, Position, Trade
from .multi_factor_strategy import MultiFactorStrategy
from .futures_arbitrage_strategy import IndexFuturesArbitrageStrategy
from .commodity_strategy import CommodityDrivenStrategy
from .sentiment_strategy import SentimentDrivenStrategy

__all__ = [
    'BaseStrategy',
    'Signal',
    'Position',
    'Trade',
    'MultiFactorStrategy',
    'IndexFuturesArbitrageStrategy',
    'CommodityDrivenStrategy',
    'SentimentDrivenStrategy',
]
