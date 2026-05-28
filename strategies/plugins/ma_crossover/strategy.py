"""
双均线交叉策略插件
"""
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np
import logging

import sys
from pathlib import Path
# 添加父路径以导入基类
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from astock_engine.strategies.base_strategy import BaseStrategy, Signal, Position
from astock_engine.core import EventBus, EventType, Event

logger = logging.getLogger(__name__)


class MACrossoverStrategy(BaseStrategy):
    """双均线交叉策略（插件版本）"""
    
    def __init__(self, params: Dict = None):
        super().__init__(name="MA_Crossover_Plugin", params=params)
        
        self.short_window = self.params.get('short_window', 10)
        self.long_window = self.params.get('long_window', 30)
        self.position_ratio = self.params.get('positionSize', 0.2)
        
        self.price_history: Dict[str, List[float]] = {}
        self.ma_short: Dict[str, float] = {}
        self.ma_long: Dict[str, float] = {}
        self.last_ma_short: Dict[str, float] = {}
        self.last_ma_long: Dict[str, float] = {}
        
        self.bus: Optional[EventBus] = None
        
        logger.info(f"[插件] 策略初始化: {self.name}, 参数: short={self.short_window}, long={self.long_window}")
    
    def initialize(self, bus: EventBus):
        """初始化策略"""
        self.bus = bus
        bus.subscribe(EventType.MARKET_DATA, self.on_market_data)
        bus.subscribe(EventType.ORDER_RESPONSE, self.on_order_response)
        logger.info(f"[插件] 策略 {self.name} 已订阅事件总线")
    
    def generate_signals(self, data: pd.DataFrame, context: Optional[Dict] = None) -> List[Signal]:
        """生成交易信号（批量模式）"""
        signals = []
        
        for symbol in data['symbol'].unique() if 'symbol' in data.columns else []:
            symbol_data = data[data['symbol'] == symbol]
            
            if len(symbol_data) < self.long_window:
                continue
            
            prices = symbol_data['close'].values
            ma_short = np.mean(prices[-self.short_window:])
            ma_long = np.mean(prices[-self.long_window:])
            
            last_ma_short = np.mean(prices[-(self.short_window+1):-1])
            last_ma_long = np.mean(prices[-(self.long_window+1):-1])
            
            current_price = prices[-1]
            timestamp = symbol_data.index[-1] if hasattr(symbol_data, 'index') else datetime.now()
            
            # 金叉
            if last_ma_short <= last_ma_long and ma_short > ma_long:
                if symbol not in self.positions:
                    signals.append(Signal(
                        symbol=symbol,
                        direction=1,
                        strength=1.0,
                        timestamp=timestamp,
                        price=current_price,
                        reason=f"金叉: MA{self.short_window}上穿MA{self.long_window}"
                    ))
            
            # 死叉
            elif last_ma_short >= last_ma_long and ma_short < ma_long:
                if symbol in self.positions:
                    signals.append(Signal(
                        symbol=symbol,
                        direction=-1,
                        strength=1.0,
                        timestamp=timestamp,
                        price=current_price,
                        reason=f"死叉: MA{self.short_window}下穿MA{self.long_window}"
                    ))
        
        return signals
    
    def on_market_data(self, event: Event):
        """处理市场数据事件（实时模式）"""
        try:
            data = event.data
            symbol = data['symbol']
            close = data['close']
            timestamp = data.get('timestamp', datetime.now())
            
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            self.price_history[symbol].append(close)
            
            if len(self.price_history[symbol]) > self.long_window:
                self.price_history[symbol] = self.price_history[symbol][-self.long_window:]
            
            if len(self.price_history[symbol]) < self.long_window:
                return
            
            if symbol in self.ma_short:
                self.last_ma_short[symbol] = self.ma_short[symbol]
            if symbol in self.ma_long:
                self.last_ma_long[symbol] = self.ma_long[symbol]
            
            prices = np.array(self.price_history[symbol])
            self.ma_short[symbol] = np.mean(prices[-self.short_window:])
            self.ma_long[symbol] = np.mean(prices[-self.long_window:])
            
            signal = self._check_crossover(symbol, close, timestamp)
            
            if signal:
                self._publish_signal(signal)
                
        except Exception as e:
            logger.error(f"[插件] 处理市场数据失败: {e}", exc_info=True)
    
    def _check_crossover(self, symbol: str, current_price: float, timestamp: datetime) -> Optional[Signal]:
        """检查均线交叉"""
        if symbol not in self.last_ma_short or symbol not in self.last_ma_long:
            return None
        
        ma_short_curr = self.ma_short[symbol]
        ma_long_curr = self.ma_long[symbol]
        ma_short_last = self.last_ma_short[symbol]
        ma_long_last = self.last_ma_long[symbol]
        
        # 金叉
        if ma_short_last <= ma_long_last and ma_short_curr > ma_long_curr:
            if symbol in self.positions:
                return None
            if len(self.positions) >= self.max_positions:
                return None
            
            logger.info(f"[插件] 🔔 {symbol} 金叉信号")
            
            return Signal(
                symbol=symbol,
                direction=1,
                strength=1.0,
                timestamp=timestamp,
                price=current_price,
                reason=f"金叉: MA{self.short_window}上穿MA{self.long_window}",
                metadata={'strategy': 'plugin:ma_crossover'}
            )
        
        # 死叉
        elif ma_short_last >= ma_long_last and ma_short_curr < ma_long_curr:
            if symbol not in self.positions:
                return None
            
            logger.info(f"[插件] 🔔 {symbol} 死叉信号")
            
            return Signal(
                symbol=symbol,
                direction=-1,
                strength=1.0,
                timestamp=timestamp,
                price=current_price,
                reason=f"死叉: MA{self.short_window}下穿MA{self.long_window}",
                metadata={'strategy': 'plugin:ma_crossover'}
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
        logger.info(f"[插件] 📡 发布信号: {signal.symbol} {signal.reason}")
    
    def on_order_response(self, event: Event):
        """处理订单响应"""
        try:
            data = event.data
            symbol = data['symbol']
            status = data['status']
            action = data.get('action', '')
            
            if status == 'FILLED':
                logger.info(f"[插件] ✅ 订单成交: {symbol} {action}")
                
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
                        logger.info(f"[插件] 💰 平仓盈亏: {symbol} {pnl:.2f} ({pnl_pct:.2%})")
                
        except Exception as e:
            logger.error(f"[插件] 处理订单响应失败: {e}", exc_info=True)
    
    def shutdown(self):
        """关闭策略"""
        if self.bus:
            self.bus.unsubscribe(EventType.MARKET_DATA, self.on_market_data)
            self.bus.unsubscribe(EventType.ORDER_RESPONSE, self.on_order_response)
        
        logger.info(f"[插件] 策略 {self.name} 已关闭")
