from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Optional
import pandas as pd

@dataclass
class Signal:
    """交易信号"""
    symbol: str
    direction: int  # 1: 买入, -1: 卖出, 0: 持有
    strength: float
    timestamp: str
    reason: str = ""
    
@dataclass
class Position:
    """持仓信息"""
    symbol: str
    quantity: float
    entry_price: float
    entry_time: str
    current_price: float = 0.0

class BaseStrategy(ABC):
    """策略基类"""
    
    def __init__(self, name: str, params: Dict = None):
        self.name = name
        self.params = params or {}
        self.initial_capital = 1000000
        self.positions: Dict[str, Position] = {}
        self.signals: List[Signal] = []
        
    @abstractmethod
    def generate_signals(self, data: pd.DataFrame, factors: Dict[str, pd.Series]) -> List[Signal]:
        """生成交易信号"""
        pass
    
    def update_positions(self, signals: List[Signal], prices: Dict[str, float]):
        """更新持仓"""
        for signal in signals:
            if signal.direction == 1:  # 买入
                self._open_position(signal, prices)
            elif signal.direction == -1:  # 卖出
                self._close_position(signal, prices)
    
    def _open_position(self, signal: Signal, prices: Dict[str, float]):
        """开仓"""
        # 实现开仓逻辑
        pass