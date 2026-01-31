"""
自定义策略示例
演示如何快速创建自己的策略
"""
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np
import logging

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from astock_engine.strategies.base_strategy import BaseStrategy, Signal
from astock_engine.core import EventBus, EventType, Event

logger = logging.getLogger(__name__)


class MyCustomStrategy(BaseStrategy):
    """
    我的自定义策略
    
    这是一个模板，展示如何快速创建自己的策略
    只需实现 generate_signals() 方法即可！
    """
    
    def __init__(self, params: Dict = None):
        super().__init__(name="MyCustomStrategy", params=params)
        
        # 🎯 第1步：定义你的策略参数
        self.my_param_1 = self.params.get('my_param_1', 10)
        self.my_param_2 = self.params.get('my_param_2', 0.5)
        
        # 你的私有变量
        self.data_cache = {}
        
        logger.info(f"自定义策略初始化: {self.name}")
    
    def generate_signals(self, data: pd.DataFrame, context: Optional[Dict] = None) -> List[Signal]:
        """
        🎯 第2步：实现核心逻辑
        
        这是唯一必须实现的方法！
        
        Args:
            data: 市场数据DataFrame，包含 symbol, close, volume 等列
            context: 可选的上下文信息
            
        Returns:
            Signal对象列表
        """
        signals = []
        
        # 🎯 你的策略逻辑写在这里
        
        # 示例：简单的价格突破策略
        for symbol in data['symbol'].unique() if 'symbol' in data.columns else []:
            symbol_data = data[data['symbol'] == symbol]
            
            if len(symbol_data) < 20:
                continue
            
            # 计算20日最高价
            high_20 = symbol_data['close'].rolling(20).max().iloc[-1]
            current_price = symbol_data['close'].iloc[-1]
            
            # 突破买入
            if current_price > high_20 * 1.02:  # 突破2%
                if symbol not in self.positions:
                    signals.append(Signal(
                        symbol=symbol,
                        direction=1,  # 买入
                        strength=0.8,
                        timestamp=datetime.now(),
                        price=current_price,
                        reason="价格突破20日高点"
                    ))
            
            # 跌破卖出
            elif symbol in self.positions:
                entry_price = self.positions[symbol].entry_price
                if current_price < entry_price * 0.95:  # 止损5%
                    signals.append(Signal(
                        symbol=symbol,
                        direction=-1,  # 卖出
                        strength=1.0,
                        timestamp=datetime.now(),
                        price=current_price,
                        reason="止损"
                    ))
        
        return signals


# ============================================================================
# 🎯 更多策略示例
# ============================================================================

class RSIStrategy(BaseStrategy):
    """RSI超买超卖策略（60行实现）"""
    
    def __init__(self, params: Dict = None):
        super().__init__(name="RSI_Strategy", params=params)
        self.rsi_period = self.params.get('rsi_period', 14)
        self.oversold = self.params.get('oversold', 30)
        self.overbought = self.params.get('overbought', 70)
    
    def generate_signals(self, data: pd.DataFrame, context: Optional[Dict] = None) -> List[Signal]:
        signals = []
        
        for symbol in data['symbol'].unique() if 'symbol' in data.columns else []:
            symbol_data = data[data['symbol'] == symbol]
            
            if len(symbol_data) < self.rsi_period + 1:
                continue
            
            # 计算RSI
            delta = symbol_data['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            current_rsi = rsi.iloc[-1]
            current_price = symbol_data['close'].iloc[-1]
            
            # 超卖买入
            if current_rsi < self.oversold and symbol not in self.positions:
                signals.append(Signal(
                    symbol=symbol,
                    direction=1,
                    strength=1.0,
                    timestamp=datetime.now(),
                    price=current_price,
                    reason=f"RSI超卖({current_rsi:.1f})"
                ))
            
            # 超买卖出
            elif current_rsi > self.overbought and symbol in self.positions:
                signals.append(Signal(
                    symbol=symbol,
                    direction=-1,
                    strength=1.0,
                    timestamp=datetime.now(),
                    price=current_price,
                    reason=f"RSI超买({current_rsi:.1f})"
                ))
        
        return signals


class GridTradingStrategy(BaseStrategy):
    """网格交易策略（80行实现）"""
    
    def __init__(self, params: Dict = None):
        super().__init__(name="GridTrading", params=params)
        self.grid_size = self.params.get('grid_size', 0.02)  # 2%网格
        self.num_grids = self.params.get('num_grids', 10)
        self.base_price = {}
        self.grid_levels = {}
    
    def generate_signals(self, data: pd.DataFrame, context: Optional[Dict] = None) -> List[Signal]:
        signals = []
        
        for symbol in data['symbol'].unique() if 'symbol' in data.columns else []:
            symbol_data = data[data['symbol'] == symbol]
            current_price = symbol_data['close'].iloc[-1]
            
            # 初始化基准价格
            if symbol not in self.base_price:
                self.base_price[symbol] = current_price
                self.grid_levels[symbol] = [
                    current_price * (1 + self.grid_size * i) 
                    for i in range(-self.num_grids, self.num_grids + 1)
                ]
            
            # 找到当前所在网格
            base = self.base_price[symbol]
            grid_levels = self.grid_levels[symbol]
            
            # 价格下跌到下一网格：买入
            if current_price < base * (1 - self.grid_size):
                if len(self.positions) < self.max_positions:
                    signals.append(Signal(
                        symbol=symbol,
                        direction=1,
                        strength=0.3,  # 网格交易用小仓位
                        timestamp=datetime.now(),
                        price=current_price,
                        reason=f"触发买入网格 @ {current_price:.2f}"
                    ))
                    self.base_price[symbol] = current_price
            
            # 价格上涨到上一网格：卖出
            elif symbol in self.positions and current_price > base * (1 + self.grid_size):
                signals.append(Signal(
                    symbol=symbol,
                    direction=-1,
                    strength=0.5,
                    timestamp=datetime.now(),
                    price=current_price,
                    reason=f"触发卖出网格 @ {current_price:.2f}"
                ))
                self.base_price[symbol] = current_price
        
        return signals


# ============================================================================
# 🎯 策略组合器
# ============================================================================

class StrategyComposer(BaseStrategy):
    """
    策略组合器 - 多策略信号融合
    
    可以组合多个策略的信号，通过投票或加权决策
    """
    
    def __init__(self, strategies: List[BaseStrategy], params: Dict = None):
        super().__init__(name="StrategyComposer", params=params)
        
        self.strategies = strategies
        self.voting_method = self.params.get('voting_method', 'majority')  # majority, weighted, unanimous
        self.weights = self.params.get('weights', [1.0] * len(strategies))
        
        logger.info(f"组合策略初始化: {len(strategies)} 个子策略, 投票方式={self.voting_method}")
    
    def generate_signals(self, data: pd.DataFrame, context: Optional[Dict] = None) -> List[Signal]:
        """融合多个策略的信号"""
        
        # 收集所有子策略的信号
        all_signals = {}  # {symbol: [signals]}
        
        for i, strategy in enumerate(self.strategies):
            signals = strategy.generate_signals(data, context)
            
            for signal in signals:
                if signal.symbol not in all_signals:
                    all_signals[signal.symbol] = []
                all_signals[signal.symbol].append((signal, self.weights[i]))
        
        # 融合信号
        final_signals = []
        
        for symbol, signal_list in all_signals.items():
            if self.voting_method == 'majority':
                # 多数投票
                buy_votes = sum(1 for sig, _ in signal_list if sig.direction == 1)
                sell_votes = sum(1 for sig, _ in signal_list if sig.direction == -1)
                
                if buy_votes > len(self.strategies) / 2:
                    final_signals.append(self._create_consensus_signal(symbol, 1, signal_list))
                elif sell_votes > len(self.strategies) / 2:
                    final_signals.append(self._create_consensus_signal(symbol, -1, signal_list))
            
            elif self.voting_method == 'weighted':
                # 加权投票
                weighted_score = sum(sig.direction * sig.strength * weight 
                                   for sig, weight in signal_list)
                
                if weighted_score > 0.5:
                    final_signals.append(self._create_consensus_signal(symbol, 1, signal_list))
                elif weighted_score < -0.5:
                    final_signals.append(self._create_consensus_signal(symbol, -1, signal_list))
            
            elif self.voting_method == 'unanimous':
                # 一致同意
                if all(sig.direction == 1 for sig, _ in signal_list):
                    final_signals.append(self._create_consensus_signal(symbol, 1, signal_list))
                elif all(sig.direction == -1 for sig, _ in signal_list):
                    final_signals.append(self._create_consensus_signal(symbol, -1, signal_list))
        
        return final_signals
    
    def _create_consensus_signal(self, symbol: str, direction: int, signal_list: List) -> Signal:
        """创建共识信号"""
        avg_price = np.mean([sig.price for sig, _ in signal_list])
        avg_strength = np.mean([sig.strength for sig, _ in signal_list])
        reasons = [sig.reason for sig, _ in signal_list]
        
        return Signal(
            symbol=symbol,
            direction=direction,
            strength=avg_strength,
            timestamp=datetime.now(),
            price=avg_price,
            reason=f"组合信号: {', '.join(reasons)}"
        )


if __name__ == "__main__":
    """演示如何使用"""
    
    # 示例1: 使用单个策略
    print("="*60)
    print("示例1: 创建自定义策略")
    print("="*60)
    
    my_strategy = MyCustomStrategy(params={
        'my_param_1': 20,
        'my_param_2': 0.8
    })
    print(f"✅ 策略名称: {my_strategy.name}")
    print(f"   参数: my_param_1={my_strategy.my_param_1}, my_param_2={my_strategy.my_param_2}")
    
    # 示例2: 组合多个策略
    print("\n" + "="*60)
    print("示例2: 组合多个策略")
    print("="*60)
    
    strategy1 = RSIStrategy(params={'rsi_period': 14})
    strategy2 = GridTradingStrategy(params={'grid_size': 0.03})
    strategy3 = MyCustomStrategy()
    
    composer = StrategyComposer(
        strategies=[strategy1, strategy2, strategy3],
        params={
            'voting_method': 'weighted',
            'weights': [0.4, 0.3, 0.3]  # RSI权重40%, Grid 30%, Custom 30%
        }
    )
    
    print(f"✅ 组合策略包含 {len(composer.strategies)} 个子策略")
    print(f"   投票方式: {composer.voting_method}")
    print(f"   权重分配: {composer.weights}")
    
    print("\n" + "="*60)
    print("🎉 你可以：")
    print("  1. 修改 MyCustomStrategy 实现自己的逻辑")
    print("  2. 复制模板创建新策略")
    print("  3. 使用 StrategyComposer 组合多个策略")
    print("  4. 只需实现 generate_signals() 方法！")
    print("="*60)
