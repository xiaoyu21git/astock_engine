"""
布林带均值回归策略插件
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


class BollingerBandsStrategy(BaseStrategy):
    """
    布林带均值回归策略
    
    原理：
    - 中轨 = MA(n)
    - 上轨 = MA(n) + k * STD(n)
    - 下轨 = MA(n) - k * STD(n)
    
    信号：
    - 价格触及或跌破下轨 → 超卖买入（预期回归）
    - 价格触及或突破上轨 → 超买卖出（预期回调）
    - 价格回归中轨附近 → 平仓
    
    适用场景：
    - 震荡行情（横盘整理）
    - 强势股回调
    - 不适合单边趋势
    """
    
    def __init__(self, params: Dict = None):
        super().__init__(name="BollingerBands_Strategy", params=params)
        
        self.period = self.params.get('period', 20)
        self.std_dev = self.params.get('std_dev', 2.0)
        self.lower_trigger = self.params.get('lower_band_trigger', 0.95)
        self.upper_trigger = self.params.get('upper_band_trigger', 1.05)
        self.position_size = self.params.get('position_size', 0.3)
        
        # 缓存数据
        self.price_history: Dict[str, List[float]] = {}
        self.bb_values: Dict[str, Dict] = {}  # {symbol: {upper, middle, lower}}
        
        self.bus: Optional[EventBus] = None
        
        logger.info(f"[布林带策略] 初始化: period={self.period}, "
                   f"std_dev={self.std_dev}, lower_trigger={self.lower_trigger:.2%}")
    
    def initialize(self, bus: EventBus):
        """初始化策略，订阅事件"""
        self.bus = bus
        bus.subscribe(EventType.MARKET_DATA, self.on_market_data)
        bus.subscribe(EventType.ORDER_RESPONSE, self.on_order_response)
        logger.info(f"[布林带策略] 已订阅事件总线")
    
    def generate_signals(self, data: pd.DataFrame, context: Optional[Dict] = None) -> List[Signal]:
        """生成交易信号（批量回测模式）"""
        signals = []
        
        for symbol in data['symbol'].unique() if 'symbol' in data.columns else []:
            symbol_data = data[data['symbol'] == symbol]
            
            # 需要足够数据计算布林带
            min_required = self.period + 10
            if len(symbol_data) < min_required:
                continue
            
            # 计算布林带
            bb_data = self._calculate_bollinger_bands(symbol_data['close'])
            
            if bb_data is None or len(bb_data) < 2:
                continue
            
            # 当前值
            current_price = symbol_data['close'].iloc[-1]
            upper_band = bb_data['upper'].iloc[-1]
            middle_band = bb_data['middle'].iloc[-1]
            lower_band = bb_data['lower'].iloc[-1]
            
            timestamp = symbol_data.index[-1] if hasattr(symbol_data, 'index') else datetime.now()
            
            # 计算价格相对位置
            price_to_lower = current_price / lower_band if lower_band > 0 else 1.0
            price_to_upper = current_price / upper_band if upper_band > 0 else 1.0
            
            # 买入信号：价格触及下轨（超卖）
            if price_to_lower <= self.lower_trigger:
                if symbol not in self.positions and len(self.positions) < self.max_positions:
                    
                    # 信号强度：越接近下轨越强 (限制在0.5-1.0之间)
                    strength = max(0.5, min(1.0, 1.0 - (price_to_lower - 0.9) * 2))
                    
                    signals.append(Signal(
                        symbol=symbol,
                        direction=1,
                        strength=strength,
                        timestamp=timestamp,
                        price=current_price,
                        reason=f"价格触及下轨(价格={current_price:.2f}, 下轨={lower_band:.2f}, 比例={price_to_lower:.2%})",
                        metadata={
                            'upper_band': upper_band,
                            'middle_band': middle_band,
                            'lower_band': lower_band,
                            'price_position': (current_price - lower_band) / (upper_band - lower_band),
                            'strategy': 'bollinger_bands_plugin'
                        }
                    ))
            
            # 卖出信号：价格触及上轨（超买）或回归中轨
            elif symbol in self.positions:
                position = self.positions[symbol]
                
                # 条件1：触及上轨
                if price_to_upper >= self.upper_trigger:
                    strength = max(0.5, (price_to_upper - 1.0) * 2)
                    
                    signals.append(Signal(
                        symbol=symbol,
                        direction=-1,
                        strength=strength,
                        timestamp=timestamp,
                        price=current_price,
                        reason=f"价格触及上轨(价格={current_price:.2f}, 上轨={upper_band:.2f}, 比例={price_to_upper:.2%})",
                        metadata={
                            'upper_band': upper_band,
                            'middle_band': middle_band,
                            'lower_band': lower_band,
                            'entry_price': position.entry_price,
                            'pnl_pct': (current_price - position.entry_price) / position.entry_price,
                            'strategy': 'bollinger_bands_plugin'
                        }
                    ))
                
                # 条件2：回归中轨且有盈利
                elif abs(current_price - middle_band) / middle_band < 0.02:  # 距中轨2%以内
                    pnl_pct = (current_price - position.entry_price) / position.entry_price
                    if pnl_pct > 0.03:  # 盈利超过3%
                        signals.append(Signal(
                            symbol=symbol,
                            direction=-1,
                            strength=0.6,
                            timestamp=timestamp,
                            price=current_price,
                            reason=f"回归中轨止盈(盈利={pnl_pct:.2%})",
                            metadata={
                                'upper_band': upper_band,
                                'middle_band': middle_band,
                                'lower_band': lower_band,
                                'entry_price': position.entry_price,
                                'pnl_pct': pnl_pct,
                                'strategy': 'bollinger_bands_plugin'
                            }
                        ))
        
        return signals
    
    def _calculate_bollinger_bands(self, prices: pd.Series) -> Optional[pd.DataFrame]:
        """
        计算布林带指标
        
        Returns:
            DataFrame with columns: upper, middle, lower
        """
        try:
            # 中轨：简单移动平均
            middle_band = prices.rolling(window=self.period).mean()
            
            # 标准差
            std = prices.rolling(window=self.period).std()
            
            # 上轨和下轨
            upper_band = middle_band + (std * self.std_dev)
            lower_band = middle_band - (std * self.std_dev)
            
            return pd.DataFrame({
                'upper': upper_band,
                'middle': middle_band,
                'lower': lower_band
            })
        except Exception as e:
            logger.error(f"[布林带策略] 计算布林带失败: {e}")
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
            max_window = self.period + 20
            if len(self.price_history[symbol]) > max_window:
                self.price_history[symbol] = self.price_history[symbol][-max_window:]
            
            # 需要足够数据计算布林带
            min_required = self.period + 2
            if len(self.price_history[symbol]) < min_required:
                return
            
            # 计算布林带
            prices_series = pd.Series(self.price_history[symbol])
            bb_data = self._calculate_bollinger_bands(prices_series)
            
            if bb_data is None:
                return
            
            upper_band = bb_data['upper'].iloc[-1]
            middle_band = bb_data['middle'].iloc[-1]
            lower_band = bb_data['lower'].iloc[-1]
            
            self.bb_values[symbol] = {
                'upper': upper_band,
                'middle': middle_band,
                'lower': lower_band
            }
            
            # 检查信号
            signal = self._check_signal(symbol, close, timestamp)
            
            if signal:
                self._publish_signal(signal)
                
        except Exception as e:
            logger.error(f"[布林带策略] 处理市场数据失败: {e}", exc_info=True)
    
    def _check_signal(self, symbol: str, current_price: float, 
                     timestamp: datetime) -> Optional[Signal]:
        """检查是否产生信号"""
        
        if symbol not in self.bb_values:
            return None
        
        bb = self.bb_values[symbol]
        upper_band = bb['upper']
        middle_band = bb['middle']
        lower_band = bb['lower']
        
        if np.isnan(upper_band) or np.isnan(lower_band):
            return None
        
        price_to_lower = current_price / lower_band
        price_to_upper = current_price / upper_band
        
        # 买入信号
        if price_to_lower <= self.lower_trigger:
            if symbol not in self.positions and len(self.positions) < self.max_positions:
                
                strength = max(0.5, 1.0 - (price_to_lower - 0.9) * 2)
                
                logger.info(f"[布林带策略] 🔔 {symbol} 超卖信号: "
                           f"价格={current_price:.2f}, 下轨={lower_band:.2f}")
                
                return Signal(
                    symbol=symbol,
                    direction=1,
                    strength=strength,
                    timestamp=timestamp,
                    price=current_price,
                    reason=f"价格触及下轨(比例={price_to_lower:.2%})",
                    metadata={**bb, 'strategy': 'bollinger_bands_plugin'}
                )
        
        # 卖出信号
        elif symbol in self.positions:
            position = self.positions[symbol]
            
            # 触及上轨
            if price_to_upper >= self.upper_trigger:
                strength = max(0.5, (price_to_upper - 1.0) * 2)
                
                logger.info(f"[布林带策略] 🔔 {symbol} 超买信号: "
                           f"价格={current_price:.2f}, 上轨={upper_band:.2f}")
                
                return Signal(
                    symbol=symbol,
                    direction=-1,
                    strength=strength,
                    timestamp=timestamp,
                    price=current_price,
                    reason=f"价格触及上轨(比例={price_to_upper:.2%})",
                    metadata={**bb, 'entry_price': position.entry_price, 'strategy': 'bollinger_bands_plugin'}
                )
            
            # 回归中轨止盈
            elif abs(current_price - middle_band) / middle_band < 0.02:
                pnl_pct = (current_price - position.entry_price) / position.entry_price
                if pnl_pct > 0.03:
                    logger.info(f"[布林带策略] 🔔 {symbol} 回归中轨: "
                               f"盈利={pnl_pct:.2%}")
                    
                    return Signal(
                        symbol=symbol,
                        direction=-1,
                        strength=0.6,
                        timestamp=timestamp,
                        price=current_price,
                        reason=f"回归中轨止盈(盈利={pnl_pct:.2%})",
                        metadata={**bb, 'entry_price': position.entry_price, 'pnl_pct': pnl_pct, 'strategy': 'bollinger_bands_plugin'}
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
        logger.info(f"[布林带策略] 📡 发布信号: {signal.symbol} {signal.reason}")
    
    def on_order_response(self, event: Event):
        """处理订单响应"""
        try:
            data = event.data
            symbol = data['symbol']
            status = data['status']
            action = data.get('action', '')
            
            if status == 'FILLED':
                logger.info(f"[布林带策略] ✅ 订单成交: {symbol} {action}")
                
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
                        logger.info(f"[布林带策略] 💰 平仓盈亏: {symbol} {pnl:.2f} ({pnl_pct:.2%})")
                
        except Exception as e:
            logger.error(f"[布林带策略] 处理订单响应失败: {e}", exc_info=True)
    
    def shutdown(self):
        """关闭策略"""
        if self.bus:
            self.bus.unsubscribe(EventType.MARKET_DATA, self.on_market_data)
            self.bus.unsubscribe(EventType.ORDER_RESPONSE, self.on_order_response)
        
        logger.info(f"[布林带策略] 已关闭")
