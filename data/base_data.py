import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Union

class BaseDataProvider(ABC):
    """数据提供器基类"""
    
    def __init__(self, cache_size: int = 1000):
        self.cache = {}
        self.cache_size = cache_size
        
    @abstractmethod
    def get_price_data(self, symbol: str, start_date: str, end_date: str, 
                      frequency: str = 'daily') -> pd.DataFrame:
        """获取价格数据"""
        pass
    
    @abstractmethod
    def get_fundamental_data(self, symbol: str, date: str) -> Dict:
        """获取基本面数据"""
        pass
    
    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()