from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """交易信号"""
    symbol: str
    direction: int  # 1: 买入, -1: 卖出, 0: 持有
    strength: float  # 信号强度 0-1
    timestamp: datetime
    price: float  # 信号价格
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not -1 <= self.direction <= 1:
            raise ValueError("direction must be -1, 0, or 1")
        if not 0 <= self.strength <= 1:
            raise ValueError("strength must be between 0 and 1")


@dataclass
class Position:
    """持仓信息"""
    symbol: str
    quantity: int  # 持仓数量
    entry_price: float  # 开仓价格
    entry_time: datetime  # 开仓时间
    current_price: float = 0.0  # 当前价格
    stop_loss: Optional[float] = None  # 止损价
    take_profit: Optional[float] = None  # 止盈价
    
    @property
    def market_value(self) -> float:
        """市值"""
        return self.quantity * self.current_price
    
    @property
    def cost_basis(self) -> float:
        """成本"""
        return self.quantity * self.entry_price
    
    @property
    def unrealized_pnl(self) -> float:
        """未实现盈亏"""
        return (self.current_price - self.entry_price) * self.quantity
    
    @property
    def unrealized_pnl_pct(self) -> float:
        """未实现盈亏率"""
        if self.entry_price == 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price


@dataclass
class Trade:
    """交易记录"""
    symbol: str
    action: str  # 'BUY' or 'SELL'
    quantity: int
    price: float
    timestamp: datetime
    commission: float = 0.0
    reason: str = ""


class BaseStrategy(ABC):
    """策略基类"""
    
    def __init__(self, name: str, params: Dict = None):
        """
        初始化策略
        
        Args:
            name: 策略名称
            params: 策略参数
        """
        self.name = name
        self.params = params or {}
        
        # 资金管理
        self.initial_capital = self.params.get('initial_capital', 1000000)
        self.cash = self.initial_capital
        self.commission_rate = self.params.get('commission_rate', 0.0003)  # 万3
        self.min_commission = self.params.get('min_commission', 5.0)  # 最低5元
        
        # 持仓管理
        self.positions: Dict[str, Position] = {}
        self.max_position_size = self.params.get('max_position_size', 0.2)  # 单股最多20%
        self.max_positions = self.params.get('max_positions', 10)  # 最多持有10只
        
        # 信号和交易记录
        self.signals: List[Signal] = []
        self.trades: List[Trade] = []
        
        # 绩效追踪
        self.equity_curve = []
        self.daily_returns = []
        
    @abstractmethod
    def generate_signals(self, data: pd.DataFrame, 
                        context: Optional[Dict] = None) -> List[Signal]:
        """
        生成交易信号（子类必须实现）
        
        Args:
            data: 市场数据
            context: 额外上下文信息（因子、新闻等）
            
        Returns:
            信号列表
        """
        pass
    
    def on_bar(self, bar: pd.Series, context: Optional[Dict] = None) -> Optional[Signal]:
        """
        处理单根K线（可选实现）
        
        Args:
            bar: K线数据
            context: 上下文信息
            
        Returns:
            可选的信号
        """
        return None
    
    def execute_signals(self, signals: List[Signal], current_prices: Dict[str, float]):
        """
        执行交易信号
        
        Args:
            signals: 信号列表
            current_prices: 当前价格字典
        """
        for signal in signals:
            if signal.direction == 1:  # 买入
                self._execute_buy(signal, current_prices)
            elif signal.direction == -1:  # 卖出
                self._execute_sell(signal, current_prices)
        
        # 保存信号
        self.signals.extend(signals)
    
    def _execute_buy(self, signal: Signal, current_prices: Dict[str, float]):
        """
        执行买入
        
        Args:
            signal: 买入信号
            current_prices: 当前价格
        """
        symbol = signal.symbol
        price = current_prices.get(symbol, signal.price)
        
        # 检查是否已持有
        if symbol in self.positions:
            logger.warning(f"Already holding {symbol}, skip buy signal")
            return
        
        # 检查持仓数量限制
        if len(self.positions) >= self.max_positions:
            logger.warning(f"Max positions {self.max_positions} reached, skip buy")
            return
        
        # 计算可买数量
        portfolio_value = self.get_portfolio_value(current_prices)
        max_position_value = portfolio_value * self.max_position_size
        
        # 根据信号强度调整仓位
        position_value = max_position_value * signal.strength
        quantity = int(position_value / price / 100) * 100  # 100股整数倍
        
        if quantity < 100:
            logger.warning(f"Quantity {quantity} < 100, skip buy")
            return
        
        # 计算所需资金
        cost = quantity * price
        commission = max(cost * self.commission_rate, self.min_commission)
        total_cost = cost + commission
        
        # 检查资金是否足够
        if total_cost > self.cash:
            logger.warning(f"Insufficient cash: need {total_cost:.2f}, have {self.cash:.2f}")
            # 调整数量
            quantity = int((self.cash / (price * (1 + self.commission_rate))) / 100) * 100
            if quantity < 100:
                return
            cost = quantity * price
            commission = max(cost * self.commission_rate, self.min_commission)
            total_cost = cost + commission
        
        # 开仓
        self.positions[symbol] = Position(
            symbol=symbol,
            quantity=quantity,
            entry_price=price,
            entry_time=signal.timestamp,
            current_price=price
        )
        
        # 扣除资金
        self.cash -= total_cost
        
        # 记录交易
        trade = Trade(
            symbol=symbol,
            action='BUY',
            quantity=quantity,
            price=price,
            timestamp=signal.timestamp,
            commission=commission,
            reason=signal.reason
        )
        self.trades.append(trade)
        
        logger.info(f"BUY {symbol}: {quantity} shares @ {price:.2f}, cost {total_cost:.2f}")
    
    def _execute_sell(self, signal: Signal, current_prices: Dict[str, float]):
        """
        执行卖出
        
        Args:
            signal: 卖出信号
            current_prices: 当前价格
        """
        symbol = signal.symbol
        
        # 检查是否持有
        if symbol not in self.positions:
            logger.warning(f"Not holding {symbol}, skip sell signal")
            return
        
        position = self.positions[symbol]
        price = current_prices.get(symbol, signal.price)
        quantity = position.quantity
        
        # 计算收入
        proceeds = quantity * price
        commission = max(proceeds * self.commission_rate, self.min_commission)
        stamp_tax = proceeds * 0.001  # 印花税 0.1%
        total_proceeds = proceeds - commission - stamp_tax
        
        # 增加资金
        self.cash += total_proceeds
        
        # 平仓
        del self.positions[symbol]
        
        # 记录交易
        trade = Trade(
            symbol=symbol,
            action='SELL',
            quantity=quantity,
            price=price,
            timestamp=signal.timestamp,
            commission=commission + stamp_tax,
            reason=signal.reason
        )
        self.trades.append(trade)
        
        pnl = total_proceeds - position.cost_basis
        pnl_pct = pnl / position.cost_basis
        
        logger.info(f"SELL {symbol}: {quantity} shares @ {price:.2f}, "
                   f"proceeds {total_proceeds:.2f}, PnL {pnl:.2f} ({pnl_pct:.2%})")
    
    def update_positions(self, current_prices: Dict[str, float]):
        """
        更新持仓当前价格
        
        Args:
            current_prices: 当前价格字典
        """
        for symbol, position in self.positions.items():
            if symbol in current_prices:
                position.current_price = current_prices[symbol]
    
    def get_portfolio_value(self, current_prices: Dict[str, float]) -> float:
        """
        计算组合总价值
        
        Args:
            current_prices: 当前价格
            
        Returns:
            组合总价值
        """
        self.update_positions(current_prices)
        positions_value = sum(pos.market_value for pos in self.positions.values())
        return self.cash + positions_value
    
    def get_positions_summary(self) -> pd.DataFrame:
        """获取持仓汇总"""
        if not self.positions:
            return pd.DataFrame()
        
        data = []
        for symbol, pos in self.positions.items():
            data.append({
                'symbol': symbol,
                'quantity': pos.quantity,
                'entry_price': pos.entry_price,
                'current_price': pos.current_price,
                'market_value': pos.market_value,
                'cost_basis': pos.cost_basis,
                'unrealized_pnl': pos.unrealized_pnl,
                'unrealized_pnl_pct': pos.unrealized_pnl_pct,
                'holding_period': (datetime.now() - pos.entry_time).days
            })
        
        return pd.DataFrame(data)
    
    def get_trades_summary(self) -> pd.DataFrame:
        """获取交易记录汇总"""
        if not self.trades:
            return pd.DataFrame()
        
        data = []
        for trade in self.trades:
            data.append({
                'timestamp': trade.timestamp,
                'symbol': trade.symbol,
                'action': trade.action,
                'quantity': trade.quantity,
                'price': trade.price,
                'amount': trade.quantity * trade.price,
                'commission': trade.commission,
                'reason': trade.reason
            })
        
        return pd.DataFrame(data)
    
    def get_performance_metrics(self, current_prices: Dict[str, float]) -> Dict[str, float]:
        """
        计算策略绩效指标
        
        Args:
            current_prices: 当前价格
            
        Returns:
            绩效指标字典
        """
        portfolio_value = self.get_portfolio_value(current_prices)
        total_return = (portfolio_value - self.initial_capital) / self.initial_capital
        
        metrics = {
            'initial_capital': self.initial_capital,
            'current_value': portfolio_value,
            'cash': self.cash,
            'positions_value': portfolio_value - self.cash,
            'total_return': total_return,
            'total_trades': len(self.trades),
            'current_positions': len(self.positions)
        }
        
        # 计算已实现盈亏
        realized_pnl = 0
        buy_trades = {}
        for trade in self.trades:
            if trade.action == 'BUY':
                buy_trades[trade.symbol] = trade
            elif trade.action == 'SELL' and trade.symbol in buy_trades:
                buy_trade = buy_trades[trade.symbol]
                pnl = (trade.price - buy_trade.price) * trade.quantity - trade.commission - buy_trade.commission
                realized_pnl += pnl
        
        metrics['realized_pnl'] = realized_pnl
        
        return metrics