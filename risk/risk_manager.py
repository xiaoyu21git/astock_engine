"""
风控管理模块
提供止损、止盈、仓位控制、风险监控等功能
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class RiskConfig:
    """风控配置"""
    # 止损止盈
    stop_loss: float = -0.05  # 止损线-5%
    take_profit: Optional[float] = 0.20  # 止盈线+20%
    trailing_stop: Optional[float] = None  # 移动止损（从最高点回撤）
    
    # 仓位控制
    max_position_size: float = 0.30  # 单股最大仓位30%
    max_positions: int = 10  # 最大持仓数
    max_total_exposure: float = 0.95  # 最大总仓位95%
    
    # 账户风险
    max_daily_loss: float = -0.03  # 单日最大亏损-3%
    max_drawdown: float = -0.15  # 最大回撤-15%
    
    # 其他
    min_holding_period: int = 1  # 最小持仓天数
    max_correlation: float = 0.7  # 持仓最大相关性


@dataclass
class Position:
    """持仓信息"""
    symbol: str
    quantity: int
    entry_price: float
    entry_time: datetime
    current_price: float
    highest_price: float = 0.0  # 持仓期间最高价
    lowest_price: float = 0.0  # 持仓期间最低价
    
    def __post_init__(self):
        if self.highest_price == 0.0:
            self.highest_price = self.entry_price
        if self.lowest_price == 0.0:
            self.lowest_price = self.entry_price
    
    @property
    def pnl(self) -> float:
        """浮动盈亏"""
        return (self.current_price - self.entry_price) * self.quantity
    
    @property
    def pnl_pct(self) -> float:
        """浮动盈亏百分比"""
        return (self.current_price - self.entry_price) / self.entry_price
    
    @property
    def value(self) -> float:
        """当前市值"""
        return self.current_price * self.quantity
    
    @property
    def trailing_loss(self) -> float:
        """从最高点的回撤"""
        if self.highest_price > 0:
            return (self.current_price - self.highest_price) / self.highest_price
        return 0.0


class RiskManager:
    """风控管理器"""
    
    def __init__(self, config: RiskConfig = None):
        self.config = config or RiskConfig()
        
        # 账户信息
        self.initial_capital = 0.0
        self.cash = 0.0
        self.positions: Dict[str, Position] = {}
        
        # 风险指标
        self.highest_equity = 0.0  # 历史最高净值
        self.daily_start_equity = 0.0  # 当日起始净值
        self.peak_equity = 0.0  # 峰值净值
        
        logger.info(f"[风控] 初始化: 止损={self.config.stop_loss:.2%}, "
                   f"最大仓位={self.config.max_position_size:.2%}")
    
    def initialize(self, initial_capital: float):
        """初始化资金"""
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.highest_equity = initial_capital
        self.daily_start_equity = initial_capital
        self.peak_equity = initial_capital
        
        logger.info(f"[风控] 初始化资金: ¥{initial_capital:,.2f}")
    
    def update_position_price(self, symbol: str, current_price: float):
        """更新持仓价格"""
        if symbol in self.positions:
            position = self.positions[symbol]
            position.current_price = current_price
            
            # 更新最高价和最低价
            if current_price > position.highest_price:
                position.highest_price = current_price
            if current_price < position.lowest_price:
                position.lowest_price = current_price
    
    def check_open_order(self, symbol: str, quantity: int, price: float) -> Tuple[bool, str]:
        """
        检查开仓订单是否符合风控
        
        Returns:
            (是否允许, 原因)
        """
        # 1. 检查持仓数量
        if symbol in self.positions:
            return False, "已持有该股票"
        
        if len(self.positions) >= self.config.max_positions:
            return False, f"超过最大持仓数({self.config.max_positions})"
        
        # 2. 检查单股仓位
        order_value = quantity * price
        total_equity = self.get_total_equity()
        
        position_ratio = order_value / total_equity if total_equity > 0 else 1.0
        
        if position_ratio > self.config.max_position_size:
            return False, f"单股仓位过大({position_ratio:.2%} > {self.config.max_position_size:.2%})"
        
        # 3. 检查总仓位
        current_exposure = self.get_position_exposure()
        new_exposure = current_exposure + position_ratio
        
        if new_exposure > self.config.max_total_exposure:
            return False, f"总仓位过大({new_exposure:.2%} > {self.config.max_total_exposure:.2%})"
        
        # 4. 检查资金充足
        if order_value > self.cash:
            return False, f"资金不足(需要¥{order_value:,.2f}, 可用¥{self.cash:,.2f})"
        
        # 5. 检查单日亏损
        daily_return = self.get_daily_return()
        if daily_return < self.config.max_daily_loss:
            return False, f"单日亏损超限({daily_return:.2%} < {self.config.max_daily_loss:.2%})"
        
        # 6. 检查最大回撤
        drawdown = self.get_current_drawdown()
        if drawdown < self.config.max_drawdown:
            return False, f"回撤超限({drawdown:.2%} < {self.config.max_drawdown:.2%})"
        
        return True, "OK"
    
    def check_close_order(self, symbol: str) -> Tuple[bool, str]:
        """
        检查平仓订单是否符合风控
        
        Returns:
            (是否允许, 原因)
        """
        if symbol not in self.positions:
            return False, "未持有该股票"
        
        # 检查最小持仓期
        position = self.positions[symbol]
        holding_days = (datetime.now() - position.entry_time).days
        
        if holding_days < self.config.min_holding_period:
            # 但如果触发止损，允许提前平仓
            if position.pnl_pct <= self.config.stop_loss:
                return True, "止损优先"
            return False, f"未达最小持仓期({holding_days}天 < {self.config.min_holding_period}天)"
        
        return True, "OK"
    
    def check_stop_loss(self, symbol: str) -> Tuple[bool, str]:
        """
        检查是否触发止损
        
        Returns:
            (是否止损, 原因)
        """
        if symbol not in self.positions:
            return False, ""
        
        position = self.positions[symbol]
        
        # 1. 固定止损
        if position.pnl_pct <= self.config.stop_loss:
            return True, f"触发止损({position.pnl_pct:.2%} <= {self.config.stop_loss:.2%})"
        
        # 2. 移动止损
        if self.config.trailing_stop is not None:
            if position.trailing_loss <= -self.config.trailing_stop:
                return True, f"触发移动止损(从最高点回撤{position.trailing_loss:.2%})"
        
        return False, ""
    
    def check_take_profit(self, symbol: str) -> Tuple[bool, str]:
        """
        检查是否触发止盈
        
        Returns:
            (是否止盈, 原因)
        """
        if symbol not in self.positions:
            return False, ""
        
        if self.config.take_profit is None:
            return False, ""
        
        position = self.positions[symbol]
        
        if position.pnl_pct >= self.config.take_profit:
            return True, f"触发止盈({position.pnl_pct:.2%} >= {self.config.take_profit:.2%})"
        
        return False, ""
    
    def add_position(self, symbol: str, quantity: int, price: float, timestamp: datetime):
        """添加持仓"""
        if symbol in self.positions:
            logger.warning(f"[风控] 重复持仓: {symbol}")
            return
        
        self.positions[symbol] = Position(
            symbol=symbol,
            quantity=quantity,
            entry_price=price,
            entry_time=timestamp,
            current_price=price
        )
        
        self.cash -= quantity * price
        
        logger.info(f"[风控] ✅ 开仓: {symbol} × {quantity} @ {price:.2f}, "
                   f"仓位={self.get_position_ratio(symbol):.2%}")
    
    def remove_position(self, symbol: str, price: float) -> float:
        """移除持仓，返回盈亏"""
        if symbol not in self.positions:
            logger.warning(f"[风控] 持仓不存在: {symbol}")
            return 0.0
        
        position = self.positions[symbol]
        pnl = position.pnl
        
        self.cash += position.quantity * price
        del self.positions[symbol]
        
        logger.info(f"[风控] ✅ 平仓: {symbol}, 盈亏={pnl:+,.2f} ({position.pnl_pct:+.2%})")
        
        return pnl
    
    def get_total_equity(self) -> float:
        """获取总资产"""
        position_value = sum(pos.value for pos in self.positions.values())
        return self.cash + position_value
    
    def get_position_exposure(self) -> float:
        """获取当前总仓位比例"""
        total_equity = self.get_total_equity()
        if total_equity <= 0:
            return 0.0
        
        position_value = sum(pos.value for pos in self.positions.values())
        return position_value / total_equity
    
    def get_position_ratio(self, symbol: str) -> float:
        """获取单股仓位比例"""
        if symbol not in self.positions:
            return 0.0
        
        total_equity = self.get_total_equity()
        if total_equity <= 0:
            return 0.0
        
        return self.positions[symbol].value / total_equity
    
    def get_current_drawdown(self) -> float:
        """获取当前回撤"""
        current_equity = self.get_total_equity()
        
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
        
        if self.peak_equity <= 0:
            return 0.0
        
        return (current_equity - self.peak_equity) / self.peak_equity
    
    def get_daily_return(self) -> float:
        """获取当日收益率"""
        if self.daily_start_equity <= 0:
            return 0.0
        
        current_equity = self.get_total_equity()
        return (current_equity - self.daily_start_equity) / self.daily_start_equity
    
    def start_new_day(self):
        """开始新的一天（重置单日指标）"""
        self.daily_start_equity = self.get_total_equity()
    
    def get_risk_report(self) -> Dict:
        """获取风控报告"""
        total_equity = self.get_total_equity()
        
        return {
            'total_equity': total_equity,
            'cash': self.cash,
            'position_count': len(self.positions),
            'position_exposure': self.get_position_exposure(),
            'current_drawdown': self.get_current_drawdown(),
            'daily_return': self.get_daily_return(),
            'total_return': (total_equity - self.initial_capital) / self.initial_capital if self.initial_capital > 0 else 0,
            'positions': {
                symbol: {
                    'quantity': pos.quantity,
                    'entry_price': pos.entry_price,
                    'current_price': pos.current_price,
                    'pnl': pos.pnl,
                    'pnl_pct': pos.pnl_pct,
                    'value': pos.value,
                    'ratio': self.get_position_ratio(symbol)
                }
                for symbol, pos in self.positions.items()
            }
        }
    
    def log_status(self):
        """输出当前状态"""
        report = self.get_risk_report()
        
        logger.info(f"[风控状态] 总资产=¥{report['total_equity']:,.2f}, "
                   f"持仓数={report['position_count']}, "
                   f"仓位={report['position_exposure']:.2%}, "
                   f"回撤={report['current_drawdown']:.2%}")
