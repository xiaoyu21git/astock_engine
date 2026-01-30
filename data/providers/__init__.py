"""
数据提供者模块
提供统一的数据接口，支持多种数据源
"""

from .base_provider import BaseDataProvider, DataType, DataQuery, DataResponse
from .stock_provider import StockDataProvider
from .futures_provider import FuturesDataProvider
from .news_provider import NewsDataProvider

__all__ = [
    'BaseDataProvider',
    'DataType',
    'DataQuery',
    'DataResponse',
    'StockDataProvider',
    'FuturesDataProvider',
    'NewsDataProvider',
]
