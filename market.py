# astock_engine/market.py
import json
from datetime import datetime
from typing import List, Optional, Union, Dict, Callable
from dataclasses import dataclass
import pandas as pd
import numpy as np

from ._native import market as _native

@dataclass
class KLine:
    """K线数据Python包装"""
    symbol: str
    period: str
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    turnover: float
    
    @classmethod
    def from_native(cls, native_kline):
        """从C++对象转换"""
        return cls(
            symbol=native_kline.symbol,
            period=native_kline.period,
            timestamp=native_kline.timestamp,
            open=native_kline.open,
            high=native_kline.high,
            low=native_kline.low,
            close=native_kline.close,
            volume=native_kline.volume,
            amount=native_kline.amount,
            turnover=native_kline.turnover
        )
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'period': self.period,
            'timestamp': self.timestamp,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'amount': self.amount,
            'turnover': self.turnover,
            'change_rate': self.change_rate,
            'is_yang': self.is_yang
        }
    
    @property
    def change_rate(self) -> float:
        """涨跌幅(%)"""
        return (self.close - self.open) / self.open * 100.0
    
    @property
    def is_yang(self) -> bool:
        """是否为阳线"""
        return self.close > self.open
    
    def to_pandas(self) -> pd.Series:
        """转换为pandas Series"""
        return pd.Series(self.to_dict())
    
    @property
    def datetime(self) -> datetime:
        """转换为datetime对象"""
        return datetime.fromtimestamp(self.timestamp / 1000)

class MarketData:
    """市场数据管理器Python接口"""
    
    def __init__(self):
        self._impl = _native.MarketDataManager.get_instance()
        self._callbacks = {}
    
    def subscribe(self, symbol: str, period: str = "1m") -> bool:
        """订阅市场数据"""
        return self._impl.subscribe(symbol, period)
    
    def unsubscribe(self, symbol: str) -> bool:
        """取消订阅"""
        return self._impl.unsubscribe(symbol)
    
    def get_history(self, 
                   symbol: str, 
                   period: str = "1m",
                   start_time: Optional[Union[int, datetime]] = None,
                   end_time: Optional[Union[int, datetime]] = None,
                   limit: int = 1000) -> List[KLine]:
        """获取历史K线数据
        
        Args:
            symbol: 标的代码
            period: K线周期
            start_time: 开始时间（时间戳或datetime）
            end_time: 结束时间（时间戳或datetime）
            limit: 最大数据条数
        """
        # 时间转换
        if isinstance(start_time, datetime):
            start_time = int(start_time.timestamp() * 1000)
        if isinstance(end_time, datetime):
            end_time = int(end_time.timestamp() * 1000)
        
        # 默认时间范围（最近7天）
        if start_time is None:
            end_time = end_time or int(datetime.now().timestamp() * 1000)
            start_time = end_time - 7 * 24 * 3600 * 1000
        
        if end_time is None:
            end_time = int(datetime.now().timestamp() * 1000)
        
        # 调用C++接口
        native_klines = self._impl.get_history_klines(
            symbol, period, start_time, end_time, limit
        )
        
        # 转换为Python对象
        return [KLine.from_native(k) for k in native_klines]
    
    def get_history_dataframe(self, 
                             symbol: str, 
                             period: str = "1m",
                             start_time: Optional[Union[int, datetime]] = None,
                             end_time: Optional[Union[int, datetime]] = None,
                             limit: int = 1000) -> pd.DataFrame:
        """获取历史数据并转换为pandas DataFrame"""
        klines = self.get_history(symbol, period, start_time, end_time, limit)
        
        # 转换为DataFrame
        if not klines:
            return pd.DataFrame()
        
        data = [k.to_dict() for k in klines]
        df = pd.DataFrame(data)
        
        # 设置时间为索引
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('datetime', inplace=True)
        df.sort_index(inplace=True)
        
        return df
    
    def get_latest(self, symbol: str, period: str = "1m") -> Optional[KLine]:
        """获取最新K线数据"""
        native_kline = self._impl.get_latest_kline(symbol, period)
        if native_kline.symbol.empty():
            return None
        return KLine.from_native(native_kline)
    
    def register_callback(self, 
                         event_type: str, 
                         callback: Callable):
        """注册数据回调
        
        Args:
            event_type: 事件类型 'kline' 或 'tick'
            callback: 回调函数
        """
        self._callbacks[event_type] = callback
        
        # TODO: 将回调转发给C++层
        # 需要C++支持回调注册
    
    def download_data(self, 
                     symbol: str,
                     period: str = "1d",
                     start_date: Union[str, datetime] = "2020-01-01",
                     end_date: Union[str, datetime] = None) -> pd.DataFrame:
        """从网络下载数据（示例实现）
        
        实际项目中可以对接各种数据源：
        1. 聚宽/JQData
        2. Tushare
        3. Baostock
        4. 券商API
        """
        # 这里是一个示例实现
        # 实际使用时需要对接具体的数据源
        
        print(f"下载数据: {symbol} {period} {start_date} - {end_date}")
        
        # 示例：生成模拟数据
        if end_date is None:
            end_date = datetime.now()
        
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%Y-%m-%d")
        
        # 生成模拟K线数据
        dates = pd.date_range(start_date, end_date, freq='D')
        n_days = len(dates)
        
        # 随机生成价格数据
        np.random.seed(hash(symbol) % 10000)
        base_price = 100.0
        returns = np.random.randn(n_days) * 0.02
        prices = base_price * np.exp(np.cumsum(returns))
        
        df = pd.DataFrame({
            'symbol': symbol,
            'period': period,
            'timestamp': [int(d.timestamp() * 1000) for d in dates],
            'open': prices * (1 - np.random.rand(n_days) * 0.01),
            'high': prices * (1 + np.random.rand(n_days) * 0.02),
            'low': prices * (1 - np.random.rand(n_days) * 0.02),
            'close': prices,
            'volume': np.random.rand(n_days) * 1000000,
            'amount': prices * np.random.rand(n_days) * 1000000,
            'turnover': np.random.rand(n_days) * 5.0
        })
        
        df.set_index(pd.DatetimeIndex(dates), inplace=True)
        
        # 保存到本地缓存
        self._save_to_cache(symbol, period, df)
        
        return df
    
    def _save_to_cache(self, symbol: str, period: str, df: pd.DataFrame):
        """保存数据到本地缓存"""
        cache_dir = "data/cache"
        os.makedirs(cache_dir, exist_ok=True)
        
        cache_file = f"{cache_dir}/{symbol}_{period}.parquet"
        df.to_parquet(cache_file)
        print(f"数据已保存到: {cache_file}")

# 创建全局实例
market_data = MarketData()

__all__ = ['KLine', 'MarketData', 'market_data']