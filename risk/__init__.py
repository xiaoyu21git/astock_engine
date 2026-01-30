"""
风险管理系统
提供多维度风险监控、预警和控制
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险等级"""
    LOW = "低风险"
    MEDIUM = "中等风险"
    HIGH = "高风险"
    CRITICAL = "极高风险"


@dataclass
class RiskMetrics:
    """风险指标"""
    timestamp: datetime
    portfolio_value: float          # 组合净值
    total_return: float             # 总收益率
    daily_return: float             # 日收益率
    volatility: float               # 波动率
    sharpe_ratio: float             # 夏普比率
    max_drawdown: float             # 最大回撤
    current_drawdown: float         # 当前回撤
    var_95: float                   # 95% VaR
    cvar_95: float                  # 95% CVaR
    position_concentration: float   # 持仓集中度
    leverage_ratio: float           # 杠杆率
    risk_level: RiskLevel           # 风险等级


@dataclass
class RiskAlert:
    """风险预警"""
    alert_type: str                 # 预警类型
    level: RiskLevel                # 风险等级
    timestamp: datetime             # 时间
    message: str                    # 预警信息
    metrics: Dict[str, float]       # 相关指标
    recommended_action: str         # 建议操作


class RiskManager:
    """风险管理器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化风险管理器
        
        Args:
            config: 配置参数
        """
        self.config = config or {}
        
        # 风险限制阈值
        self.limits = {
            'max_position_ratio': 0.30,      # 单股持仓上限 30%
            'max_drawdown': 0.15,            # 最大回撤限制 15%
            'max_leverage': 1.0,             # 最大杠杆倍数
            'min_cash_ratio': 0.10,          # 最低现金比例 10%
            'max_sector_concentration': 0.40, # 行业集中度上限 40%
            'stop_loss_ratio': -0.05,        # 止损线 -5%
            'stop_profit_ratio': 0.20,       # 止盈线 +20%
            'var_limit': 0.02,               # VaR限制 2%
        }
        self.limits.update(self.config.get('limits', {}))
        
        # 风险指标历史
        self.metrics_history = []
        
        # 预警记录
        self.alerts = []
        
        # 订阅者
        self.subscribers = []
        
    def calculate_metrics(self, 
                         portfolio_value: float,
                         positions: Dict[str, Dict],
                         equity_curve: pd.Series) -> RiskMetrics:
        """
        计算风险指标
        
        Args:
            portfolio_value: 组合总价值
            positions: 持仓信息
            equity_curve: 净值曲线
            
        Returns:
            风险指标
        """
        # 计算收益率
        returns = equity_curve.pct_change().dropna()
        total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1
        daily_return = returns.iloc[-1] if len(returns) > 0 else 0
        
        # 计算波动率（年化）
        volatility = returns.std() * np.sqrt(252) if len(returns) > 1 else 0
        
        # 计算夏普比率
        risk_free_rate = 0.03  # 假设无风险利率3%
        sharpe_ratio = (total_return - risk_free_rate) / volatility if volatility > 0 else 0
        
        # 计算最大回撤
        cummax = equity_curve.cummax()
        drawdown = (equity_curve - cummax) / cummax
        max_drawdown = drawdown.min()
        current_drawdown = drawdown.iloc[-1]
        
        # 计算VaR和CVaR (95%置信水平)
        var_95 = returns.quantile(0.05) if len(returns) > 0 else 0
        cvar_95 = returns[returns <= var_95].mean() if len(returns) > 0 else 0
        
        # 计算持仓集中度
        total_position_value = sum(pos['market_value'] for pos in positions.values())
        if total_position_value > 0:
            position_concentration = max(
                pos['market_value'] / total_position_value 
                for pos in positions.values()
            )
        else:
            position_concentration = 0
        
        # 计算杠杆率
        leverage_ratio = total_position_value / portfolio_value if portfolio_value > 0 else 0
        
        # 评估风险等级
        risk_level = self._assess_risk_level(
            max_drawdown, volatility, position_concentration, leverage_ratio
        )
        
        metrics = RiskMetrics(
            timestamp=datetime.now(),
            portfolio_value=portfolio_value,
            total_return=total_return,
            daily_return=daily_return,
            volatility=volatility,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            current_drawdown=current_drawdown,
            var_95=var_95,
            cvar_95=cvar_95,
            position_concentration=position_concentration,
            leverage_ratio=leverage_ratio,
            risk_level=risk_level
        )
        
        self.metrics_history.append(metrics)
        return metrics
    
    def _assess_risk_level(self, drawdown: float, volatility: float,
                          concentration: float, leverage: float) -> RiskLevel:
        """评估风险等级"""
        risk_score = 0
        
        # 回撤评分
        if abs(drawdown) > 0.15:
            risk_score += 3
        elif abs(drawdown) > 0.10:
            risk_score += 2
        elif abs(drawdown) > 0.05:
            risk_score += 1
        
        # 波动率评分
        if volatility > 0.40:
            risk_score += 3
        elif volatility > 0.30:
            risk_score += 2
        elif volatility > 0.20:
            risk_score += 1
        
        # 集中度评分
        if concentration > 0.40:
            risk_score += 2
        elif concentration > 0.30:
            risk_score += 1
        
        # 杠杆评分
        if leverage > 2.0:
            risk_score += 3
        elif leverage > 1.5:
            risk_score += 2
        elif leverage > 1.0:
            risk_score += 1
        
        # 确定风险等级
        if risk_score >= 6:
            return RiskLevel.CRITICAL
        elif risk_score >= 4:
            return RiskLevel.HIGH
        elif risk_score >= 2:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def check_limits(self, metrics: RiskMetrics, 
                    positions: Dict[str, Dict]) -> List[RiskAlert]:
        """
        检查风险限制
        
        Args:
            metrics: 风险指标
            positions: 持仓信息
            
        Returns:
            风险预警列表
        """
        alerts = []
        
        # 检查回撤限制
        if abs(metrics.max_drawdown) > self.limits['max_drawdown']:
            alerts.append(RiskAlert(
                alert_type="最大回撤超限",
                level=RiskLevel.CRITICAL,
                timestamp=datetime.now(),
                message=f"最大回撤 {metrics.max_drawdown:.2%} 超过限制 {self.limits['max_drawdown']:.2%}",
                metrics={'max_drawdown': metrics.max_drawdown},
                recommended_action="建议减仓或停止交易"
            ))
        
        # 检查持仓集中度
        if metrics.position_concentration > self.limits['max_position_ratio']:
            alerts.append(RiskAlert(
                alert_type="持仓集中度过高",
                level=RiskLevel.HIGH,
                timestamp=datetime.now(),
                message=f"单股持仓比例 {metrics.position_concentration:.2%} 超过限制 {self.limits['max_position_ratio']:.2%}",
                metrics={'concentration': metrics.position_concentration},
                recommended_action="建议分散投资"
            ))
        
        # 检查杠杆率
        if metrics.leverage_ratio > self.limits['max_leverage']:
            alerts.append(RiskAlert(
                alert_type="杠杆率过高",
                level=RiskLevel.HIGH,
                timestamp=datetime.now(),
                message=f"杠杆率 {metrics.leverage_ratio:.2f} 超过限制 {self.limits['max_leverage']:.2f}",
                metrics={'leverage': metrics.leverage_ratio},
                recommended_action="建议降低杠杆"
            ))
        
        # 检查VaR
        if abs(metrics.var_95) > self.limits['var_limit']:
            alerts.append(RiskAlert(
                alert_type="VaR超限",
                level=RiskLevel.MEDIUM,
                timestamp=datetime.now(),
                message=f"95% VaR {metrics.var_95:.2%} 超过限制 {self.limits['var_limit']:.2%}",
                metrics={'var_95': metrics.var_95},
                recommended_action="建议控制风险敞口"
            ))
        
        # 保存预警
        self.alerts.extend(alerts)
        
        # 通知订阅者
        for alert in alerts:
            self.notify_subscribers(alert)
        
        return alerts
    
    def should_stop_loss(self, position: Dict, current_price: float) -> bool:
        """
        判断是否应该止损
        
        Args:
            position: 持仓信息
            current_price: 当前价格
            
        Returns:
            是否应该止损
        """
        entry_price = position['entry_price']
        pnl_ratio = (current_price - entry_price) / entry_price
        
        return pnl_ratio <= self.limits['stop_loss_ratio']
    
    def should_stop_profit(self, position: Dict, current_price: float) -> bool:
        """
        判断是否应该止盈
        
        Args:
            position: 持仓信息
            current_price: 当前价格
            
        Returns:
            是否应该止盈
        """
        entry_price = position['entry_price']
        pnl_ratio = (current_price - entry_price) / entry_price
        
        return pnl_ratio >= self.limits['stop_profit_ratio']
    
    def calculate_position_size(self, 
                               portfolio_value: float,
                               price: float,
                               volatility: float,
                               risk_per_trade: float = 0.02) -> int:
        """
        计算合理的持仓规模（凯利公式变体）
        
        Args:
            portfolio_value: 组合总价值
            price: 股票价格
            volatility: 股票波动率
            risk_per_trade: 单笔交易风险比例
            
        Returns:
            建议持仓数量
        """
        # 风险金额
        risk_amount = portfolio_value * risk_per_trade
        
        # 根据波动率调整持仓
        if volatility > 0:
            position_value = risk_amount / volatility
        else:
            position_value = portfolio_value * self.limits['max_position_ratio']
        
        # 不超过持仓上限
        max_position_value = portfolio_value * self.limits['max_position_ratio']
        position_value = min(position_value, max_position_value)
        
        # 计算股数
        shares = int(position_value / price / 100) * 100  # 取整到100股
        
        return max(shares, 100)  # 至少100股
    
    def generate_risk_report(self, metrics: RiskMetrics) -> Dict[str, Any]:
        """生成风险报告"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'risk_level': metrics.risk_level.value,
            'summary': {
                '组合净值': f"{metrics.portfolio_value:.2f}",
                '总收益率': f"{metrics.total_return:.2%}",
                '夏普比率': f"{metrics.sharpe_ratio:.2f}",
                '最大回撤': f"{metrics.max_drawdown:.2%}",
                '当前回撤': f"{metrics.current_drawdown:.2%}",
                '波动率': f"{metrics.volatility:.2%}",
                '持仓集中度': f"{metrics.position_concentration:.2%}",
                '杠杆率': f"{metrics.leverage_ratio:.2f}",
            },
            'risk_indicators': {
                'VaR_95': f"{metrics.var_95:.2%}",
                'CVaR_95': f"{metrics.cvar_95:.2%}",
            },
            'recent_alerts': [
                {
                    'type': alert.alert_type,
                    'level': alert.level.value,
                    'message': alert.message,
                    'action': alert.recommended_action
                }
                for alert in self.alerts[-5:]  # 最近5条预警
            ]
        }
        
        return report
    
    def subscribe(self, callback: Callable[[RiskAlert], None]):
        """订阅风险预警"""
        self.subscribers.append(callback)
        logger.info(f"Added risk alert subscriber, total: {len(self.subscribers)}")
    
    def notify_subscribers(self, alert: RiskAlert):
        """通知所有订阅者"""
        for callback in self.subscribers:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Failed to notify risk subscriber: {e}")
