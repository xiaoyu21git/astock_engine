"""
数据提供者基类
定义统一的数据接口规范
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict, Optional, Any
from datetime import datetime, date
import pandas as pd
from dataclasses import dataclass


class DataType(Enum):
    """数据类型枚举"""
    STOCK_DAILY = "stock_daily"           # 股票日线
    STOCK_MINUTE = "stock_minute"         # 股票分钟线
    STOCK_TICK = "stock_tick"             # 股票tick
    FUTURES_DAILY = "futures_daily"       # 期货日线
    FUTURES_MINUTE = "futures_minute"     # 期货分钟线
    INDEX_DAILY = "index_daily"           # 指数日线
    NEWS = "news"                         # 新闻
    ANNOUNCEMENT = "announcement"         # 公告
    FINANCIAL = "financial"               # 财务数据


@dataclass
class DataQuery:
    """数据查询参数"""
    symbols: List[str]                    # 标的代码列表
    start_date: Optional[date] = None     # 开始日期
    end_date: Optional[date] = None       # 结束日期
    frequency: str = "1d"                 # 频率: 1m, 5m, 15m, 30m, 1h, 1d
    fields: Optional[List[str]] = None    # 需要的字段
    limit: int = 1000                     # 数据条数限制
    adjust: str = "qfq"                   # 复权类型: qfq(前复权), hfq(后复权), none
    extra_params: Optional[Dict[str, Any]] = None  # 额外参数


@dataclass
class DataResponse:
    """数据响应"""
    data: pd.DataFrame                    # 数据内容
    data_type: DataType                   # 数据类型
    query: DataQuery                      # 查询参数
    timestamp: datetime                   # 响应时间戳
    source: str                           # 数据源
    success: bool = True                  # 是否成功
    error_msg: Optional[str] = None       # 错误信息


class BaseDataProvider(ABC):
    """数据提供者基类"""
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        """
        初始化数据提供者
        
        Args:
            name: 提供者名称
            config: 配置参数
        """
        self.name = name
        self.config = config or {}
        self._initialized = False
        
    @abstractmethod
    def initialize(self) -> bool:
        """
        初始化数据源连接
        
        Returns:
            是否初始化成功
        """
        pass
    
    @abstractmethod
    def get_data(self, query: DataQuery, data_type: DataType) -> DataResponse:
        """
        获取数据
        
        Args:
            query: 查询参数
            data_type: 数据类型
            
        Returns:
            数据响应
        """
        pass
    
    @abstractmethod
    def get_realtime_data(self, symbols: List[str]) -> DataResponse:
        """
        获取实时数据
        
        Args:
            symbols: 标的代码列表
            
        Returns:
            实时数据响应
        """
        pass
    
    @abstractmethod
    def subscribe(self, symbols: List[str], callback) -> bool:
        """
        订阅实时数据
        
        Args:
            symbols: 标的代码列表
            callback: 回调函数
            
        Returns:
            是否订阅成功
        """
        pass
    
    @abstractmethod
    def unsubscribe(self, symbols: List[str]) -> bool:
        """
        取消订阅
        
        Args:
            symbols: 标的代码列表
            
        Returns:
            是否取消成功
        """
        pass
    
    def validate_symbols(self, symbols: List[str]) -> List[str]:
        """
        验证标的代码有效性
        
        Args:
            symbols: 标的代码列表
            
        Returns:
            有效的标的代码列表
        """
        return [s for s in symbols if s and isinstance(s, str)]
    
    def close(self):
        """关闭连接"""
        self._initialized = False
    
    def __enter__(self):
        """上下文管理器入口"""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()
