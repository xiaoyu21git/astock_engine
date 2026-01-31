"""
基础回测引擎
支持策略历史数据回测和性能评估
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
import logging

from ..strategies.base_strategy import BaseStrategy, Signal
from ..risk import RiskManager, RiskConfig

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """回测配置"""
    initial_capital: float = 1000000  # 初始资金
    commission_rate: float = 0.0003  # 手续费率（万3）
    slippage_rate: float = 0.001  # 滑点（0.1%）
    benchmark: str = "000300.SH"  # 基准指数
    
    # 风控参数
    max_position_size: float = 0.3  # 单股最大仓位30%
    max_positions: int = 10  # 最多持仓数
    stop_loss: float = -0.05  # 止损-5%
    take_profit: Optional[float] = None  # 止盈


@dataclass
class BacktestMetrics:
    """回测指标"""
    # 收益指标
    total_return: float = 0.0  # 总收益率
    annual_return: float = 0.0  # 年化收益率
    
    # 风险指标
    volatility: float = 0.0  # 波动率
    max_drawdown: float = 0.0  # 最大回撤
    sharpe_ratio: float = 0.0  # 夏普比率
    sortino_ratio: float = 0.0  # 索提诺比率
    calmar_ratio: float = 0.0  # 卡玛比率
    
    # 交易指标
    num_trades: int = 0  # 交易次数
    win_rate: float = 0.0  # 胜率
    profit_factor: float = 0.0  # 盈亏比
    avg_win: float = 0.0  # 平均盈利
    avg_loss: float = 0.0  # 平均亏损
    
    # 时间指标
    trading_days: int = 0  # 交易天数
    avg_holding_period: float = 0.0  # 平均持仓周期
    
    # 其他
    final_value: float = 0.0  # 最终资产
    benchmark_return: float = 0.0  # 基准收益率
    alpha: float = 0.0  # 超额收益


@dataclass
class Trade:
    """交易记录"""
    symbol: str
    action: str  # BUY/SELL
    price: float
    quantity: int
    timestamp: datetime
    commission: float = 0.0
    pnl: float = 0.0  # 本次交易盈亏


class BacktestEngine:
    """回测引擎"""
    
    def __init__(self, config: BacktestConfig = None, enable_risk_control: bool = True):
        self.config = config or BacktestConfig()
        self.enable_risk_control = enable_risk_control
        
        # 状态变量
        self.cash = self.config.initial_capital
        self.positions: Dict[str, Dict] = {}  # {symbol: {quantity, entry_price, entry_time}}
        self.trades: List[Trade] = []
        self.equity_curve: List[Tuple[datetime, float]] = []
        self.daily_returns: List[float] = []
        
        # 风控管理器
        if self.enable_risk_control:
            risk_config = RiskConfig(
                stop_loss=self.config.stop_loss,
                take_profit=self.config.take_profit,
                max_position_size=self.config.max_position_size,
                max_positions=self.config.max_positions
            )
            self.risk_manager = RiskManager(risk_config)
            self.risk_manager.initialize(self.config.initial_capital)
        else:
            self.risk_manager = None
        
        logger.info(f"回测引擎初始化: 初始资金={self.config.initial_capital:,.0f}, 风控={'开启' if enable_risk_control else '关闭'}")
    
    def run(self, 
            strategy: BaseStrategy,
            data: Dict[str, pd.DataFrame],
            start_date: str = None,
            end_date: str = None) -> BacktestMetrics:
        """
        运行回测
        
        Args:
            strategy: 策略实例
            data: 股票数据字典 {symbol: DataFrame(date, open, high, low, close, volume)}
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            
        Returns:
            BacktestMetrics: 回测指标
        """
        logger.info(f"开始回测: {strategy.name}")
        logger.info(f"回测区间: {start_date} 至 {end_date}")
        logger.info(f"标的数量: {len(data)}")
        
        # 重置状态
        self._reset()
        
        # 获取所有交易日
        all_dates = set()
        for symbol, df in data.items():
            df.index = pd.to_datetime(df.index)
            all_dates.update(df.index)
        
        trading_dates = sorted(all_dates)
        
        # 过滤日期范围
        if start_date:
            start_dt = pd.to_datetime(start_date)
            trading_dates = [d for d in trading_dates if d >= start_dt]
        if end_date:
            end_dt = pd.to_datetime(end_date)
            trading_dates = [d for d in trading_dates if d <= end_dt]
        
        logger.info(f"交易日数: {len(trading_dates)}")
        
        # 逐日回测
        for i, current_date in enumerate(trading_dates):
            if i % 50 == 0:
                logger.info(f"进度: {i}/{len(trading_dates)} ({i/len(trading_dates)*100:.1f}%)")
            
            # 获取当日数据
            daily_data = self._get_daily_data(data, current_date)
            
            if not daily_data:
                continue
            
            # 更新持仓市值
            self._update_positions_price(daily_data)
            
            # 风控检查：止损止盈
            if self.enable_risk_control:
                self._check_risk_control(daily_data, current_date)
            
            # 生成信号（传递截止当前日期的历史数据）
            historical_data = self._get_historical_data(data, current_date)
            signals = strategy.generate_signals(
                historical_data,
                context={'date': current_date}
            )
            
            # 执行信号
            self._execute_signals(signals, daily_data, current_date)
            
            # 记录净值
            total_value = self._calculate_total_value(daily_data)
            self.equity_curve.append((current_date, total_value))
            
            # 计算日收益率
            if len(self.equity_curve) > 1:
                prev_value = self.equity_curve[-2][1]
                daily_return = (total_value - prev_value) / prev_value
                self.daily_returns.append(daily_return)
        
        # 计算指标
        metrics = self._calculate_metrics()
        
        logger.info(f"回测完成: 总收益={metrics.total_return:.2%}, "
                   f"夏普={metrics.sharpe_ratio:.2f}, 最大回撤={metrics.max_drawdown:.2%}")
        
        return metrics
    
    def _reset(self):
        """重置回测状态"""
        self.cash = self.config.initial_capital
        self.positions = {}
        self.trades = []
        self.equity_curve = []
        self.daily_returns = []
    
    def _get_daily_data(self, data: Dict[str, pd.DataFrame], date: datetime) -> Dict[str, Dict]:
        """获取指定日期的数据"""
        daily_data = {}
        
        for symbol, df in data.items():
            if date in df.index:
                row = df.loc[date]
                daily_data[symbol] = {
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'volume': row['volume']
                }
        
        return daily_data
    
    def _get_historical_data(self, data: Dict[str, pd.DataFrame], 
                             current_date: datetime) -> pd.DataFrame:
        """获取截止当前日期的历史数据（供策略计算指标）"""
        all_data = []
        
        for symbol, df in data.items():
            # 获取截止当前日期的所有历史数据
            historical_df = df[df.index <= current_date].copy()
            
            if not historical_df.empty:
                historical_df['symbol'] = symbol
                all_data.append(historical_df)
        
        if not all_data:
            return pd.DataFrame()
        
        # 合并所有股票数据
        combined_df = pd.concat(all_data, ignore_index=False)
        return combined_df
    
    def _update_positions_price(self, daily_data: Dict[str, Dict]):
        """更新持仓当前价格"""
        for symbol in self.positions:
            if symbol in daily_data:
                self.positions[symbol]['current_price'] = daily_data[symbol]['close']
                
                # 同步更新风控管理器的持仓价格
                if self.enable_risk_control:
                    self.risk_manager.update_position_price(symbol, daily_data[symbol]['close'])
    
    def _check_risk_control(self, daily_data: Dict[str, Dict], timestamp: datetime):
        """检查风控规则（止损止盈）"""
        if not self.enable_risk_control:
            return
        
        symbols_to_close = []
        
        for symbol in list(self.positions.keys()):
            if symbol not in daily_data:
                continue
            
            price = daily_data[symbol]['close']
            
            # 检查止损
            should_stop, reason = self.risk_manager.check_stop_loss(symbol)
            if should_stop:
                logger.info(f"[风控止损] {symbol}: {reason}")
                symbols_to_close.append((symbol, price, reason))
                continue
            
            # 检查止盈
            should_profit, reason = self.risk_manager.check_take_profit(symbol)
            if should_profit:
                logger.info(f"[风控止盈] {symbol}: {reason}")
                symbols_to_close.append((symbol, price, reason))
        
        # 执行平仓
        for symbol, price, reason in symbols_to_close:
            self._execute_risk_close(symbol, price, timestamp, reason)
    
    def _execute_signals(self, signals: List[Signal], 
                        daily_data: Dict[str, Dict],
                        timestamp: datetime):
        """执行交易信号"""
        for signal in signals:
            symbol = signal.symbol
            
            if symbol not in daily_data:
                continue
            
            price = daily_data[symbol]['close']
            
            # 考虑滑点
            if signal.direction == 1:  # 买入，价格上浮
                price *= (1 + self.config.slippage_rate)
            else:  # 卖出，价格下浮
                price *= (1 - self.config.slippage_rate)
            
            if signal.direction == 1:  # 买入
                self._execute_buy(signal, price, timestamp)
            elif signal.direction == -1:  # 卖出
                self._execute_sell(signal, price, timestamp)
    
    def _execute_buy(self, signal: Signal, price: float, timestamp: datetime):
        """执行买入"""
        symbol = signal.symbol
        
        # 检查是否已持仓
        if symbol in self.positions:
            return
        
        # 检查持仓数量限制
        if len(self.positions) >= self.config.max_positions:
            return
        
        # 计算可买数量
        position_value = self.cash * signal.strength * self.config.max_position_size
        quantity = int(position_value / price / 100) * 100  # 100股整数倍
        
        if quantity < 100:
            return
        
        # 风控检查
        if self.enable_risk_control:
            can_open, reason = self.risk_manager.check_open_order(symbol, quantity, price)
            if not can_open:
                logger.debug(f"[风控拒绝] {symbol} 开仓: {reason}")
                return
        
        # 计算成本
        cost = quantity * price
        commission = max(cost * self.config.commission_rate, 5.0)
        total_cost = cost + commission
        
        if total_cost > self.cash:
            # 资金不足，调整数量
            quantity = int((self.cash / (price * (1 + self.config.commission_rate))) / 100) * 100
            if quantity < 100:
                return
            cost = quantity * price
            commission = max(cost * self.config.commission_rate, 5.0)
            total_cost = cost + commission
        
        # 执行买入
        self.cash -= total_cost
        self.positions[symbol] = {
            'quantity': quantity,
            'entry_price': price,
            'entry_time': timestamp,
            'current_price': price
        }
        
        # 同步到风控管理器
        if self.enable_risk_control:
            self.risk_manager.add_position(symbol, quantity, price, timestamp)
        
        # 记录交易
        trade = Trade(
            symbol=symbol,
            action='BUY',
            price=price,
            quantity=quantity,
            timestamp=timestamp,
            commission=commission
        )
        self.trades.append(trade)
        
        logger.debug(f"买入: {symbol} @ {price:.2f} × {quantity}, 手续费={commission:.2f}")
    
    def _execute_sell(self, signal: Signal, price: float, timestamp: datetime):
        """执行卖出"""
        symbol = signal.symbol
        
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        quantity = position['quantity']
        entry_price = position['entry_price']
        
        # 计算收入
        revenue = quantity * price
        commission = max(revenue * self.config.commission_rate, 5.0)
        total_revenue = revenue - commission
        
        # 执行卖出
        self.cash += total_revenue
        
        # 计算盈亏
        pnl = (price - entry_price) * quantity - commission
        pnl_pct = (price - entry_price) / entry_price
        
        # 记录交易
        trade = Trade(
            symbol=symbol,
            action='SELL',
            price=price,
            quantity=quantity,
            timestamp=timestamp,
            commission=commission,
            pnl=pnl
        )
        self.trades.append(trade)
        
        # 移除持仓
        del self.positions[symbol]
        
        # 同步到风控管理器
        if self.enable_risk_control:
            self.risk_manager.remove_position(symbol, price)
        
        logger.debug(f"卖出: {symbol} @ {price:.2f} × {quantity}, "
                    f"盈亏={pnl:.2f} ({pnl_pct:.2%}), 手续费={commission:.2f}")
    
    def _execute_risk_close(self, symbol: str, price: float, timestamp: datetime, reason: str):
        """执行风控平仓（止损/止盈）"""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        quantity = position['quantity']
        entry_price = position['entry_price']
        
        # 考虑滑点
        price *= (1 - self.config.slippage_rate)
        
        # 计算收入
        revenue = quantity * price
        commission = max(revenue * self.config.commission_rate, 5.0)
        total_revenue = revenue - commission
        
        # 执行平仓
        self.cash += total_revenue
        pnl = (price - entry_price) * quantity - commission
        pnl_pct = (price - entry_price) / entry_price
        
        # 记录交易
        trade = Trade(
            symbol=symbol,
            action='SELL',
            price=price,
            quantity=quantity,
            timestamp=timestamp,
            commission=commission,
            pnl=pnl
        )
        self.trades.append(trade)
        
        # 移除持仓
        del self.positions[symbol]
        
        # 同步到风控管理器
        if self.enable_risk_control:
            self.risk_manager.remove_position(symbol, price)
        
        logger.info(f"[风控平仓] {symbol} @ {price:.2f} × {quantity}, 盈亏={pnl:+.2f}({pnl_pct:+.2%}) - {reason}")
    
    def _calculate_total_value(self, daily_data: Dict[str, Dict]) -> float:
        """计算总资产"""
        total = self.cash
        
        for symbol, position in self.positions.items():
            if symbol in daily_data:
                total += position['quantity'] * daily_data[symbol]['close']
        
        return total
    
    def _calculate_metrics(self) -> BacktestMetrics:
        """计算回测指标"""
        metrics = BacktestMetrics()
        
        if not self.equity_curve:
            return metrics
        
        # 基础数据
        initial_value = self.config.initial_capital
        final_value = self.equity_curve[-1][1]
        trading_days = len(self.equity_curve)
        
        # 收益指标
        metrics.final_value = final_value
        metrics.total_return = (final_value - initial_value) / initial_value
        metrics.trading_days = trading_days
        
        # 年化收益率（假设一年250个交易日）
        years = trading_days / 250
        if years > 0:
            metrics.annual_return = (1 + metrics.total_return) ** (1 / years) - 1
        
        # 波动率和夏普比率
        if len(self.daily_returns) > 1:
            returns_array = np.array(self.daily_returns)
            metrics.volatility = np.std(returns_array) * np.sqrt(250)  # 年化波动率
            
            mean_return = np.mean(returns_array)
            annual_mean_return = mean_return * 250
            risk_free_rate = 0.03  # 假设无风险利率3%
            
            if metrics.volatility > 0:
                metrics.sharpe_ratio = (annual_mean_return - risk_free_rate) / metrics.volatility
        
        # 最大回撤
        equity_values = [val for _, val in self.equity_curve]
        peak = equity_values[0]
        max_dd = 0
        
        for value in equity_values:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
        
        metrics.max_drawdown = max_dd
        
        # 卡玛比率
        if max_dd > 0:
            metrics.calmar_ratio = metrics.annual_return / max_dd
        
        # 交易指标
        metrics.num_trades = len(self.trades)
        
        if metrics.num_trades > 0:
            wins = [t for t in self.trades if t.action == 'SELL' and t.pnl > 0]
            losses = [t for t in self.trades if t.action == 'SELL' and t.pnl < 0]
            
            metrics.win_rate = len(wins) / (len(wins) + len(losses)) if (len(wins) + len(losses)) > 0 else 0
            
            if wins:
                metrics.avg_win = np.mean([t.pnl for t in wins])
            if losses:
                metrics.avg_loss = abs(np.mean([t.pnl for t in losses]))
            
            if metrics.avg_loss > 0:
                metrics.profit_factor = metrics.avg_win / metrics.avg_loss
        
        return metrics
    
    def get_equity_curve(self) -> pd.DataFrame:
        """获取净值曲线"""
        df = pd.DataFrame(self.equity_curve, columns=['date', 'value'])
        df['return'] = df['value'].pct_change()
        df['cumulative_return'] = (df['value'] / self.config.initial_capital) - 1
        return df
    
    def get_trades_df(self) -> pd.DataFrame:
        """获取交易记录"""
        if not self.trades:
            return pd.DataFrame()
        
        trades_data = []
        for t in self.trades:
            trades_data.append({
                'timestamp': t.timestamp,
                'symbol': t.symbol,
                'action': t.action,
                'price': t.price,
                'quantity': t.quantity,
                'commission': t.commission,
                'pnl': t.pnl
            })
        
        return pd.DataFrame(trades_data)
