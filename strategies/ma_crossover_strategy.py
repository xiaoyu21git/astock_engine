"""
双均线交叉策略
基于EventBus的实时策略实现
"""
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np
import logging

from .base_strategy import BaseStrategy, Signal, Position
from ..core import EventBus, EventType, Event

logger = logging.getLogger(__name__)


class MovingAverageCrossoverStrategy(BaseStrategy):
    """
    双均线交叉策略
    
    策略逻辑：
    - 金叉（短期均线上穿长期均线）：买入信号
    - 死叉（短期均线下穿长期均线）：卖出信号
    
    参数：
    - short_window: 短期均线窗口（默认10）
    - long_window: 长期均线窗口（默认30）
    - position_size: 单次交易仓位（默认0.2，即20%）
    """
    
    def __init__(self, params: Dict = None):
        super().__init__(name="MA_Crossover", params=params)
        
        # 策略参数
        self.short_window = self.params.get('short_window', 10)
        self.long_window = self.params.get('long_window', 30)
        self.position_size = self.params.get('position_size', 0.2)
        
        # 数据缓存
        self.price_history: Dict[str, List[float]] = {}
        self.ma_short: Dict[str, float] = {}
        self.ma_long: Dict[str, float] = {}
        self.last_ma_short: Dict[str, float] = {}
        self.last_ma_long: Dict[str, float] = {}
        
        # EventBus
        self.bus: Optional[EventBus] = None
        
        logger.info(f"策略初始化: {self.name}, 参数: short={self.short_window}, long={self.long_window}")
    
    def initialize(self, bus: EventBus):
        """
        初始化策略，订阅事件
        
        Args:
            bus: EventBus实例
        """
        self.bus = bus
        
        # 订阅市场数据事件
        bus.subscribe(EventType.MARKET_DATA, self.on_market_data)
        
        # 订阅订单响应事件
        bus.subscribe(EventType.ORDER_RESPONSE, self.on_order_response)
        
        logger.info(f"策略 {self.name} 已订阅事件总线")
    
    def generate_signals(self, data: pd.DataFrame, context: Optional[Dict] = None) -> List[Signal]:
        """
        生成交易信号（批量模式，用于回测）
        
        Args:
            data: 市场数据DataFrame
            context: 额外上下文
            
        Returns:
            信号列表
        """
        signals = []
        
        for symbol in data['symbol'].unique() if 'symbol' in data.columns else []:
            symbol_data = data[data['symbol'] == symbol]
            
            # 确保有足够数据
            if len(symbol_data) < self.long_window:
                continue
            
            # 计算均线
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
        """
        处理市场数据事件
        
        Args:
            event: 市场数据事件
        """
        try:
            data = event.data
            symbol = data['symbol']
            close = data['close']
            timestamp = data.get('timestamp', datetime.now())
            
            # 更新价格历史
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            self.price_history[symbol].append(close)
            
            # 保持历史数据在长期窗口大小
            if len(self.price_history[symbol]) > self.long_window:
                self.price_history[symbol] = self.price_history[symbol][-self.long_window:]
            
            # 需要足够的数据才能计算均线
            if len(self.price_history[symbol]) < self.long_window:
                logger.debug(f"{symbol} 数据不足，当前 {len(self.price_history[symbol])}/{self.long_window}")
                return
            
            # 保存上一次的均线值
            if symbol in self.ma_short:
                self.last_ma_short[symbol] = self.ma_short[symbol]
            if symbol in self.ma_long:
                self.last_ma_long[symbol] = self.ma_long[symbol]
            
            # 计算均线
            prices = np.array(self.price_history[symbol])
            self.ma_short[symbol] = np.mean(prices[-self.short_window:])
            self.ma_long[symbol] = np.mean(prices[-self.long_window:])
            
            # 检查是否有交叉信号
            signal = self._check_crossover(symbol, close, timestamp)
            
            if signal:
                # 发布信号事件
                self._publish_signal(signal)
                
        except Exception as e:
            logger.error(f"处理市场数据失败: {e}", exc_info=True)
    
    def _check_crossover(self, symbol: str, current_price: float, 
                        timestamp: datetime) -> Optional[Signal]:
        """
        检查均线交叉信号
        
        Returns:
            Signal对象，如果没有信号则返回None
        """
        # 需要至少有上一次的均线值
        if symbol not in self.last_ma_short or symbol not in self.last_ma_long:
            return None
        
        ma_short_curr = self.ma_short[symbol]
        ma_long_curr = self.ma_long[symbol]
        ma_short_last = self.last_ma_short[symbol]
        ma_long_last = self.last_ma_long[symbol]
        
        # 金叉：短期均线上穿长期均线
        if ma_short_last <= ma_long_last and ma_short_curr > ma_long_curr:
            # 检查是否已持仓
            if symbol in self.positions:
                logger.info(f"{symbol} 金叉信号，但已持仓，忽略")
                return None
            
            # 检查持仓数量限制
            if len(self.positions) >= self.max_positions:
                logger.info(f"{symbol} 金叉信号，但持仓已满({self.max_positions})，忽略")
                return None
            
            logger.info(f"🔔 {symbol} 金叉信号: MA{self.short_window}={ma_short_curr:.2f} > MA{self.long_window}={ma_long_curr:.2f}")
            
            return Signal(
                symbol=symbol,
                direction=1,  # 买入
                strength=1.0,
                timestamp=timestamp,
                price=current_price,
                reason=f"金叉: MA{self.short_window}上穿MA{self.long_window}",
                metadata={
                    'ma_short': ma_short_curr,
                    'ma_long': ma_long_curr,
                    'strategy': self.name
                }
            )
        
        # 死叉：短期均线下穿长期均线
        elif ma_short_last >= ma_long_last and ma_short_curr < ma_long_curr:
            # 检查是否持仓
            if symbol not in self.positions:
                logger.info(f"{symbol} 死叉信号，但未持仓，忽略")
                return None
            
            logger.info(f"🔔 {symbol} 死叉信号: MA{self.short_window}={ma_short_curr:.2f} < MA{self.long_window}={ma_long_curr:.2f}")
            
            return Signal(
                symbol=symbol,
                direction=-1,  # 卖出
                strength=1.0,
                timestamp=timestamp,
                price=current_price,
                reason=f"死叉: MA{self.short_window}下穿MA{self.long_window}",
                metadata={
                    'ma_short': ma_short_curr,
                    'ma_long': ma_long_curr,
                    'strategy': self.name
                }
            )
        
        return None
    
    def _publish_signal(self, signal: Signal):
        """发布交易信号事件"""
        if not self.bus:
            logger.warning("EventBus未初始化，无法发布信号")
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
        logger.info(f"📡 发布信号: {signal.symbol} {signal.reason}")
    
    def on_order_response(self, event: Event):
        """
        处理订单响应事件
        
        Args:
            event: 订单响应事件
        """
        try:
            data = event.data
            symbol = data['symbol']
            status = data['status']
            action = data.get('action', '')
            
            if status == 'FILLED':
                logger.info(f"✅ 订单成交: {symbol} {action}")
                
                # 更新持仓
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
                        
                        # 计算盈亏
                        pnl = (data['price'] - position.entry_price) * position.quantity
                        pnl_pct = (data['price'] - position.entry_price) / position.entry_price
                        logger.info(f"💰 平仓盈亏: {symbol} {pnl:.2f} ({pnl_pct:.2%})")
                
            elif status == 'REJECTED':
                logger.warning(f"❌ 订单被拒绝: {symbol} {data.get('reason', '')}")
                
        except Exception as e:
            logger.error(f"处理订单响应失败: {e}", exc_info=True)
    
    def get_portfolio_value(self) -> float:
        """计算组合总市值"""
        total = self.cash
        for position in self.positions.values():
            total += position.market_value
        return total
    
    def get_positions_summary(self) -> Dict:
        """获取持仓摘要"""
        return {
            'cash': self.cash,
            'positions': [
                {
                    'symbol': pos.symbol,
                    'quantity': pos.quantity,
                    'entry_price': pos.entry_price,
                    'current_price': pos.current_price,
                    'pnl': pos.unrealized_pnl,
                    'pnl_pct': pos.unrealized_pnl_pct
                }
                for pos in self.positions.values()
            ],
            'total_value': self.get_portfolio_value()
        }
    
    def shutdown(self):
        """关闭策略"""
        if self.bus:
            self.bus.unsubscribe(EventType.MARKET_DATA, self.on_market_data)
            self.bus.unsubscribe(EventType.ORDER_RESPONSE, self.on_order_response)
        
        logger.info(f"策略 {self.name} 已关闭")
