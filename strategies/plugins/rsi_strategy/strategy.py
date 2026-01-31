"""
RSI超买超卖策略插件
"""
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np
import logging

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from astock_engine.strategies.base_strategy import BaseStrategy, Signal, Position
from astock_engine.core import EventBus, EventType, Event

logger = logging.getLogger(__name__)


class RSIStrategy(BaseStrategy):
    """
    RSI超买超卖策略
    
    原理：
    - RSI < 超卖线（默认30）：超卖，买入信号
    - RSI > 超买线（默认70）：超买，卖出信号
    
    适用场景：震荡市、均值回归
    """
    
    def __init__(self, params: Dict = None):
        super().__init__(name="RSI_Strategy", params=params)
        
        self.rsi_period = self.params.get('rsi_period', 14)
        self.oversold = self.params.get('oversold', 30)
        self.overbought = self.params.get('overbought', 70)
        self.position_size = self.params.get('position_size', 0.2)
        
        # 缓存价格历史
        self.price_history: Dict[str, List[float]] = {}
        self.rsi_values: Dict[str, float] = {}
        
        self.bus: Optional[EventBus] = None
        
        logger.info(f"[RSI策略] 初始化: period={self.rsi_period}, "
                   f"超卖={self.oversold}, 超买={self.overbought}")
    
    def initialize(self, bus: EventBus):
        """初始化策略，订阅事件"""
        self.bus = bus
        bus.subscribe(EventType.MARKET_DATA, self.on_market_data)
        bus.subscribe(EventType.ORDER_RESPONSE, self.on_order_response)
        logger.info(f"[RSI策略] 已订阅事件总线")
    
    def generate_signals(self, data: pd.DataFrame, context: Optional[Dict] = None) -> List[Signal]:
        """生成交易信号（批量回测模式）"""
        signals = []
        
        for symbol in data['symbol'].unique() if 'symbol' in data.columns else []:
            symbol_data = data[data['symbol'] == symbol]
            
            if len(symbol_data) < self.rsi_period + 1:
                continue
            
            # 计算RSI
            rsi_series = self._calculate_rsi(symbol_data['close'])
            
            if rsi_series is None or len(rsi_series) == 0:
                continue
            
            current_rsi = rsi_series.iloc[-1]
            current_price = symbol_data['close'].iloc[-1]
            timestamp = symbol_data.index[-1] if hasattr(symbol_data, 'index') else datetime.now()
            
            # 超卖买入
            if current_rsi < self.oversold and symbol not in self.positions:
                if len(self.positions) < self.max_positions:
                    signals.append(Signal(
                        symbol=symbol,
                        direction=1,
                        strength=min(1.0, (self.oversold - current_rsi) / self.oversold),
                        timestamp=timestamp,
                        price=current_price,
                        reason=f"RSI超卖({current_rsi:.1f} < {self.oversold})",
                        metadata={'rsi': current_rsi, 'strategy': 'rsi_plugin'}
                    ))
            
            # 超买卖出
            elif current_rsi > self.overbought and symbol in self.positions:
                signals.append(Signal(
                    symbol=symbol,
                    direction=-1,
                    strength=min(1.0, (current_rsi - self.overbought) / (100 - self.overbought)),
                    timestamp=timestamp,
                    price=current_price,
                    reason=f"RSI超买({current_rsi:.1f} > {self.overbought})",
                    metadata={'rsi': current_rsi, 'strategy': 'rsi_plugin'}
                ))
        
        return signals
    
    def _calculate_rsi(self, prices: pd.Series) -> Optional[pd.Series]:
        """
        计算RSI指标
        
        RSI = 100 - (100 / (1 + RS))
        RS = 平均涨幅 / 平均跌幅
        """
        try:
            delta = prices.diff()
            
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            avg_gain = gain.rolling(window=self.rsi_period).mean()
            avg_loss = loss.rolling(window=self.rsi_period).mean()
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi
        except Exception as e:
            logger.error(f"[RSI策略] 计算RSI失败: {e}")
            return None
    
    def on_market_data(self, event: Event):
        """处理市场数据事件（实时模式）"""
        try:
            data = event.data
            symbol = data['symbol']
            close = data['close']
            timestamp = data.get('timestamp', datetime.now())
            
            # 更新价格历史
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            self.price_history[symbol].append(close)
            
            # 保持历史数据窗口
            if len(self.price_history[symbol]) > self.rsi_period + 10:
                self.price_history[symbol] = self.price_history[symbol][-(self.rsi_period + 10):]
            
            # 需要足够数据计算RSI
            if len(self.price_history[symbol]) < self.rsi_period + 1:
                return
            
            # 计算RSI
            prices_series = pd.Series(self.price_history[symbol])
            rsi_series = self._calculate_rsi(prices_series)
            
            if rsi_series is None:
                return
            
            current_rsi = rsi_series.iloc[-1]
            self.rsi_values[symbol] = current_rsi
            
            # 检查信号
            signal = self._check_signal(symbol, close, current_rsi, timestamp)
            
            if signal:
                self._publish_signal(signal)
                
        except Exception as e:
            logger.error(f"[RSI策略] 处理市场数据失败: {e}", exc_info=True)
    
    def _check_signal(self, symbol: str, current_price: float, 
                     rsi: float, timestamp: datetime) -> Optional[Signal]:
        """检查是否产生信号"""
        
        # 超卖买入
        if rsi < self.oversold:
            if symbol not in self.positions and len(self.positions) < self.max_positions:
                logger.info(f"[RSI策略] 🔔 {symbol} 超卖信号: RSI={rsi:.1f}")
                
                return Signal(
                    symbol=symbol,
                    direction=1,
                    strength=min(1.0, (self.oversold - rsi) / self.oversold),
                    timestamp=timestamp,
                    price=current_price,
                    reason=f"RSI超卖({rsi:.1f} < {self.oversold})",
                    metadata={'rsi': rsi, 'strategy': 'rsi_plugin'}
                )
        
        # 超买卖出
        elif rsi > self.overbought:
            if symbol in self.positions:
                logger.info(f"[RSI策略] 🔔 {symbol} 超买信号: RSI={rsi:.1f}")
                
                return Signal(
                    symbol=symbol,
                    direction=-1,
                    strength=min(1.0, (rsi - self.overbought) / (100 - self.overbought)),
                    timestamp=timestamp,
                    price=current_price,
                    reason=f"RSI超买({rsi:.1f} > {self.overbought})",
                    metadata={'rsi': rsi, 'strategy': 'rsi_plugin'}
                )
        
        return None
    
    def _publish_signal(self, signal: Signal):
        """发布交易信号"""
        if not self.bus:
            return
        
        event = Event(
            type=EventType.SIGNAL,
            data={
                'symbol': signal.symbol,
                'direction': signal.direction,
                'strength': signal.strength,
                'price': signal.price,
                'reason': signal.reason,
                'metadata': signal.metadata,
                'timestamp': signal.timestamp
            },
            timestamp=signal.timestamp
        )
        
        self.bus.publish(event)
        logger.info(f"[RSI策略] 📡 发布信号: {signal.symbol} {signal.reason}")
    
    def on_order_response(self, event: Event):
        """处理订单响应"""
        try:
            data = event.data
            symbol = data['symbol']
            status = data['status']
            action = data.get('action', '')
            
            if status == 'FILLED':
                logger.info(f"[RSI策略] ✅ 订单成交: {symbol} {action}")
                
                if action == 'BUY':
                    position = Position(
                        symbol=symbol,
                        quantity=data['quantity'],
                        entry_price=data['price'],
                        entry_time=data['timestamp'],
                        current_price=data['price']
                    )
                    self.positions[symbol] = position
                    self.cash -= data['quantity'] * data['price'] * (1 + self.commission_rate)
                    
                elif action == 'SELL':
                    if symbol in self.positions:
                        position = self.positions[symbol]
                        self.cash += data['quantity'] * data['price'] * (1 - self.commission_rate)
                        del self.positions[symbol]
                        
                        pnl = (data['price'] - position.entry_price) * position.quantity
                        pnl_pct = (data['price'] - position.entry_price) / position.entry_price
                        logger.info(f"[RSI策略] 💰 平仓盈亏: {symbol} {pnl:.2f} ({pnl_pct:.2%})")
                
        except Exception as e:
            logger.error(f"[RSI策略] 处理订单响应失败: {e}", exc_info=True)
    
    def shutdown(self):
        """关闭策略"""
        if self.bus:
            self.bus.unsubscribe(EventType.MARKET_DATA, self.on_market_data)
            self.bus.unsubscribe(EventType.ORDER_RESPONSE, self.on_order_response)
        
        logger.info(f"[RSI策略] 已关闭")
