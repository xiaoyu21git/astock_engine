"""
MACD趋势策略插件
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


class MACDStrategy(BaseStrategy):
    """
    MACD趋势策略
    
    原理：
    - MACD = EMA(12) - EMA(26)
    - Signal = EMA(MACD, 9)
    - Histogram = MACD - Signal
    
    信号：
    - 金叉：MACD上穿Signal → 买入
    - 死叉：MACD下穿Signal → 卖出
    - 辅助：柱状图由负转正加强买入，由正转负加强卖出
    """
    
    def __init__(self, params: Dict = None):
        super().__init__(name="MACD_Strategy", params=params)
        
        self.fast_period = self.params.get('fast_period', 12)
        self.slow_period = self.params.get('slow_period', 26)
        self.signal_period = self.params.get('signal_period', 9)
        self.use_histogram = self.params.get('use_histogram', True)
        self.position_size = self.params.get('position_size', 0.3)
        
        # 缓存价格历史
        self.price_history: Dict[str, List[float]] = {}
        self.macd_values: Dict[str, Dict] = {}  # {symbol: {macd, signal, histogram}}
        self.last_macd_values: Dict[str, Dict] = {}
        
        self.bus: Optional[EventBus] = None
        
        logger.info(f"[MACD策略] 初始化: fast={self.fast_period}, "
                   f"slow={self.slow_period}, signal={self.signal_period}")
    
    def initialize(self, bus: EventBus):
        """初始化策略，订阅事件"""
        self.bus = bus
        bus.subscribe(EventType.MARKET_DATA, self.on_market_data)
        bus.subscribe(EventType.ORDER_RESPONSE, self.on_order_response)
        logger.info(f"[MACD策略] 已订阅事件总线")
    
    def generate_signals(self, data: pd.DataFrame, context: Optional[Dict] = None) -> List[Signal]:
        """生成交易信号（批量回测模式）"""
        signals = []
        
        for symbol in data['symbol'].unique() if 'symbol' in data.columns else []:
            symbol_data = data[data['symbol'] == symbol]
            
            # 需要足够数据计算MACD
            min_required = self.slow_period + self.signal_period + 10
            if len(symbol_data) < min_required:
                continue
            
            # 计算MACD指标
            macd_data = self._calculate_macd(symbol_data['close'])
            
            if macd_data is None or len(macd_data) < 2:
                continue
            
            # 当前值和上一个值
            current_macd = macd_data['macd'].iloc[-1]
            current_signal = macd_data['signal'].iloc[-1]
            current_hist = macd_data['histogram'].iloc[-1]
            
            last_macd = macd_data['macd'].iloc[-2]
            last_signal = macd_data['signal'].iloc[-2]
            last_hist = macd_data['histogram'].iloc[-2]
            
            current_price = symbol_data['close'].iloc[-1]
            timestamp = symbol_data.index[-1] if hasattr(symbol_data, 'index') else datetime.now()
            
            # 金叉：MACD上穿Signal
            if last_macd <= last_signal and current_macd > current_signal:
                if symbol not in self.positions and len(self.positions) < self.max_positions:
                    
                    # 计算信号强度
                    strength = 0.8
                    if self.use_histogram and current_hist > 0 and last_hist <= 0:
                        strength = 1.0  # 柱状图同时转正，强信号
                    
                    signals.append(Signal(
                        symbol=symbol,
                        direction=1,
                        strength=strength,
                        timestamp=timestamp,
                        price=current_price,
                        reason=f"MACD金叉(MACD={current_macd:.4f} > Signal={current_signal:.4f})",
                        metadata={
                            'macd': current_macd,
                            'signal': current_signal,
                            'histogram': current_hist,
                            'strategy': 'macd_plugin'
                        }
                    ))
            
            # 死叉：MACD下穿Signal
            elif last_macd >= last_signal and current_macd < current_signal:
                if symbol in self.positions:
                    
                    # 计算信号强度
                    strength = 0.8
                    if self.use_histogram and current_hist < 0 and last_hist >= 0:
                        strength = 1.0  # 柱状图同时转负，强信号
                    
                    signals.append(Signal(
                        symbol=symbol,
                        direction=-1,
                        strength=strength,
                        timestamp=timestamp,
                        price=current_price,
                        reason=f"MACD死叉(MACD={current_macd:.4f} < Signal={current_signal:.4f})",
                        metadata={
                            'macd': current_macd,
                            'signal': current_signal,
                            'histogram': current_hist,
                            'strategy': 'macd_plugin'
                        }
                    ))
        
        return signals
    
    def _calculate_macd(self, prices: pd.Series) -> Optional[pd.DataFrame]:
        """
        计算MACD指标
        
        Returns:
            DataFrame with columns: macd, signal, histogram
        """
        try:
            # 计算快慢EMA
            ema_fast = prices.ewm(span=self.fast_period, adjust=False).mean()
            ema_slow = prices.ewm(span=self.slow_period, adjust=False).mean()
            
            # MACD线 = 快线 - 慢线
            macd = ema_fast - ema_slow
            
            # Signal线 = MACD的EMA
            signal = macd.ewm(span=self.signal_period, adjust=False).mean()
            
            # 柱状图 = MACD - Signal
            histogram = macd - signal
            
            return pd.DataFrame({
                'macd': macd,
                'signal': signal,
                'histogram': histogram
            })
        except Exception as e:
            logger.error(f"[MACD策略] 计算MACD失败: {e}")
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
            max_window = self.slow_period + self.signal_period + 20
            if len(self.price_history[symbol]) > max_window:
                self.price_history[symbol] = self.price_history[symbol][-max_window:]
            
            # 需要足够数据计算MACD
            min_required = self.slow_period + self.signal_period + 2
            if len(self.price_history[symbol]) < min_required:
                return
            
            # 保存上一次的值
            if symbol in self.macd_values:
                self.last_macd_values[symbol] = self.macd_values[symbol].copy()
            
            # 计算MACD
            prices_series = pd.Series(self.price_history[symbol])
            macd_data = self._calculate_macd(prices_series)
            
            if macd_data is None:
                return
            
            current_macd = macd_data['macd'].iloc[-1]
            current_signal = macd_data['signal'].iloc[-1]
            current_hist = macd_data['histogram'].iloc[-1]
            
            self.macd_values[symbol] = {
                'macd': current_macd,
                'signal': current_signal,
                'histogram': current_hist
            }
            
            # 检查信号
            signal = self._check_signal(symbol, close, timestamp)
            
            if signal:
                self._publish_signal(signal)
                
        except Exception as e:
            logger.error(f"[MACD策略] 处理市场数据失败: {e}", exc_info=True)
    
    def _check_signal(self, symbol: str, current_price: float, 
                     timestamp: datetime) -> Optional[Signal]:
        """检查是否产生信号"""
        
        if symbol not in self.last_macd_values or symbol not in self.macd_values:
            return None
        
        last = self.last_macd_values[symbol]
        current = self.macd_values[symbol]
        
        # 金叉
        if last['macd'] <= last['signal'] and current['macd'] > current['signal']:
            if symbol not in self.positions and len(self.positions) < self.max_positions:
                
                strength = 0.8
                if self.use_histogram and current['histogram'] > 0 and last['histogram'] <= 0:
                    strength = 1.0
                
                logger.info(f"[MACD策略] 🔔 {symbol} 金叉信号: "
                           f"MACD={current['macd']:.4f} > Signal={current['signal']:.4f}")
                
                return Signal(
                    symbol=symbol,
                    direction=1,
                    strength=strength,
                    timestamp=timestamp,
                    price=current_price,
                    reason=f"MACD金叉(MACD={current['macd']:.4f} > Signal={current['signal']:.4f})",
                    metadata={**current, 'strategy': 'macd_plugin'}
                )
        
        # 死叉
        elif last['macd'] >= last['signal'] and current['macd'] < current['signal']:
            if symbol in self.positions:
                
                strength = 0.8
                if self.use_histogram and current['histogram'] < 0 and last['histogram'] >= 0:
                    strength = 1.0
                
                logger.info(f"[MACD策略] 🔔 {symbol} 死叉信号: "
                           f"MACD={current['macd']:.4f} < Signal={current['signal']:.4f}")
                
                return Signal(
                    symbol=symbol,
                    direction=-1,
                    strength=strength,
                    timestamp=timestamp,
                    price=current_price,
                    reason=f"MACD死叉(MACD={current['macd']:.4f} < Signal={current['signal']:.4f})",
                    metadata={**current, 'strategy': 'macd_plugin'}
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
        logger.info(f"[MACD策略] 📡 发布信号: {signal.symbol} {signal.reason}")
    
    def on_order_response(self, event: Event):
        """处理订单响应"""
        try:
            data = event.data
            symbol = data['symbol']
            status = data['status']
            action = data.get('action', '')
            
            if status == 'FILLED':
                logger.info(f"[MACD策略] ✅ 订单成交: {symbol} {action}")
                
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
                        logger.info(f"[MACD策略] 💰 平仓盈亏: {symbol} {pnl:.2f} ({pnl_pct:.2%})")
                
        except Exception as e:
            logger.error(f"[MACD策略] 处理订单响应失败: {e}", exc_info=True)
    
    def shutdown(self):
        """关闭策略"""
        if self.bus:
            self.bus.unsubscribe(EventType.MARKET_DATA, self.on_market_data)
            self.bus.unsubscribe(EventType.ORDER_RESPONSE, self.on_order_response)
        
        logger.info(f"[MACD策略] 已关闭")
