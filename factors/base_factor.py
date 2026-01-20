import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class FactorResult:
    """因子计算结果"""
    name: str
    values: pd.Series
    timestamp: str
    params: Dict = None

class BaseFactor(ABC):
    """因子计算基类"""
    
    def __init__(self, name: str, params: Dict = None):
        self.name = name
        self.params = params or {}
        self.description = ""
        
    @abstractmethod
    def calculate(self, data: pd.DataFrame) -> FactorResult:
        """计算因子值"""
        pass
    
    def validate(self, data: pd.DataFrame) -> bool:
        """验证输入数据"""
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        return all(col in data.columns for col in required_cols)