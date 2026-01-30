"""
异动监控系统
实时监控股票价格、成交量等异常变化
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class AnomalyType(Enum):
    """异动类型"""
    LIMIT_UP = "涨停"              # 涨停
    LIMIT_DOWN = "跌停"            # 跌停
    RAPID_RISE = "急涨"            # 快速上涨
    RAPID_FALL = "急跌"            # 快速下跌
    VOLUME_SURGE = "放量"          # 成交量暴增
    VOLUME_SHRINK = "缩量"         # 成交量萎缩
    BIG_BUY_ORDER = "大买单"       # 大额买单
    BIG_SELL_ORDER = "大卖单"      # 大额卖单
    CONTINUOUS_BUY = "连续买入"     # 连续买入
    CONTINUOUS_SELL = "连续卖出"    # 连续卖出
    VOLATILITY_SURGE = "波动率突增"  # 波动率异常
    FLASH_CRASH = "闪崩"           # 闪崩
    TURNOVER_SURGE = "换手率异常"   # 换手率过高


@dataclass
class AnomalyEvent:
    """异动事件"""
    symbol: str                    # 股票代码
    name: str                      # 股票名称
    anomaly_type: AnomalyType      # 异动类型
    timestamp: datetime            # 发生时间
    current_price: float           # 当前价格
    change_rate: float             # 涨跌幅
    volume: float                  # 成交量
    amount: float                  # 成交额
    turnover: float                # 换手率
    description: str               # 异动描述
    severity: int                  # 严重程度 (1-5)
    extra_data: Dict[str, Any]     # 额外数据
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'name': self.name,
            'anomaly_type': self.anomaly_type.value,
            'timestamp': self.timestamp.isoformat(),
            'current_price': self.current_price,
            'change_rate': self.change_rate,
            'volume': self.volume,
            'amount': self.amount,
            'turnover': self.turnover,
            'description': self.description,
            'severity': self.severity,
            'extra_data': self.extra_data
        }


class AnomalyDetector:
    """异动检测器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化异动检测器
        
        Args:
            config: 配置参数
        """
        self.config = config or {}
        
        # 默认阈值
        self.thresholds = {
            'limit_up_rate': 9.9,          # 涨停阈值
            'limit_down_rate': -9.9,       # 跌停阈值
            'rapid_rise_rate': 3.0,        # 急涨阈值（1分钟）
            'rapid_fall_rate': -3.0,       # 急跌阈值（1分钟）
            'volume_surge_ratio': 2.0,     # 放量倍数
            'volume_shrink_ratio': 0.3,    # 缩量比例
            'big_order_amount': 1000000,   # 大单金额（元）
            'turnover_high': 20.0,         # 高换手率
            'volatility_surge': 3.0,       # 波动率倍数
        }
        self.thresholds.update(self.config.get('thresholds', {}))
        
        # 历史数据缓存
        self.history_cache = {}
        
        # 异动事件缓存
        self.anomaly_events = []
        
        # 订阅者回调
        self.subscribers = []
        
    def detect(self, current_data: pd.DataFrame, 
              historical_data: Optional[pd.DataFrame] = None) -> List[AnomalyEvent]:
        """
        检测异动
        
        Args:
            current_data: 当前实时数据
            historical_data: 历史数据用于对比
            
        Returns:
            异动事件列表
        """
        anomalies = []
        
        for _, row in current_data.iterrows():
            symbol = row['symbol']
            
            # 检测各类异动
            anomalies.extend(self._detect_price_anomaly(row))
            anomalies.extend(self._detect_volume_anomaly(row, historical_data))
            anomalies.extend(self._detect_turnover_anomaly(row))
            
        return anomalies
    
    def _detect_price_anomaly(self, data: pd.Series) -> List[AnomalyEvent]:
        """检测价格异动"""
        anomalies = []
        
        symbol = data['symbol']
        name = data.get('name', symbol)
        change_rate = data.get('pct_change', 0)
        price = data.get('price', 0)
        volume = data.get('volume', 0)
        amount = data.get('amount', 0)
        turnover = data.get('turnover', 0)
        
        # 涨停检测
        if change_rate >= self.thresholds['limit_up_rate']:
            anomalies.append(AnomalyEvent(
                symbol=symbol,
                name=name,
                anomaly_type=AnomalyType.LIMIT_UP,
                timestamp=datetime.now(),
                current_price=price,
                change_rate=change_rate,
                volume=volume,
                amount=amount,
                turnover=turnover,
                description=f"{name} 涨停，涨幅 {change_rate:.2f}%",
                severity=5,
                extra_data={}
            ))
        
        # 跌停检测
        elif change_rate <= self.thresholds['limit_down_rate']:
            anomalies.append(AnomalyEvent(
                symbol=symbol,
                name=name,
                anomaly_type=AnomalyType.LIMIT_DOWN,
                timestamp=datetime.now(),
                current_price=price,
                change_rate=change_rate,
                volume=volume,
                amount=amount,
                turnover=turnover,
                description=f"{name} 跌停，跌幅 {change_rate:.2f}%",
                severity=5,
                extra_data={}
            ))
        
        # 急涨检测
        elif change_rate >= self.thresholds['rapid_rise_rate']:
            anomalies.append(AnomalyEvent(
                symbol=symbol,
                name=name,
                anomaly_type=AnomalyType.RAPID_RISE,
                timestamp=datetime.now(),
                current_price=price,
                change_rate=change_rate,
                volume=volume,
                amount=amount,
                turnover=turnover,
                description=f"{name} 快速上涨，涨幅 {change_rate:.2f}%",
                severity=3,
                extra_data={}
            ))
        
        # 急跌检测
        elif change_rate <= self.thresholds['rapid_fall_rate']:
            anomalies.append(AnomalyEvent(
                symbol=symbol,
                name=name,
                anomaly_type=AnomalyType.RAPID_FALL,
                timestamp=datetime.now(),
                current_price=price,
                change_rate=change_rate,
                volume=volume,
                amount=amount,
                turnover=turnover,
                description=f"{name} 快速下跌，跌幅 {change_rate:.2f}%",
                severity=3,
                extra_data={}
            ))
        
        return anomalies
    
    def _detect_volume_anomaly(self, data: pd.Series, 
                               historical_data: Optional[pd.DataFrame]) -> List[AnomalyEvent]:
        """检测成交量异动"""
        anomalies = []
        
        if historical_data is None or historical_data.empty:
            return anomalies
        
        symbol = data['symbol']
        name = data.get('name', symbol)
        current_volume = data.get('volume', 0)
        
        # 获取历史平均成交量
        symbol_history = historical_data[historical_data['symbol'] == symbol]
        if symbol_history.empty:
            return anomalies
        
        avg_volume = symbol_history['volume'].tail(5).mean()
        
        if avg_volume > 0:
            volume_ratio = current_volume / avg_volume
            
            # 放量检测
            if volume_ratio >= self.thresholds['volume_surge_ratio']:
                anomalies.append(AnomalyEvent(
                    symbol=symbol,
                    name=name,
                    anomaly_type=AnomalyType.VOLUME_SURGE,
                    timestamp=datetime.now(),
                    current_price=data.get('price', 0),
                    change_rate=data.get('pct_change', 0),
                    volume=current_volume,
                    amount=data.get('amount', 0),
                    turnover=data.get('turnover', 0),
                    description=f"{name} 成交量放大 {volume_ratio:.1f}倍",
                    severity=4,
                    extra_data={'volume_ratio': volume_ratio, 'avg_volume': avg_volume}
                ))
            
            # 缩量检测
            elif volume_ratio <= self.thresholds['volume_shrink_ratio']:
                anomalies.append(AnomalyEvent(
                    symbol=symbol,
                    name=name,
                    anomaly_type=AnomalyType.VOLUME_SHRINK,
                    timestamp=datetime.now(),
                    current_price=data.get('price', 0),
                    change_rate=data.get('pct_change', 0),
                    volume=current_volume,
                    amount=data.get('amount', 0),
                    turnover=data.get('turnover', 0),
                    description=f"{name} 成交量萎缩至 {volume_ratio:.1%}",
                    severity=2,
                    extra_data={'volume_ratio': volume_ratio, 'avg_volume': avg_volume}
                ))
        
        return anomalies
    
    def _detect_turnover_anomaly(self, data: pd.Series) -> List[AnomalyEvent]:
        """检测换手率异动"""
        anomalies = []
        
        symbol = data['symbol']
        name = data.get('name', symbol)
        turnover = data.get('turnover', 0)
        
        # 高换手率检测
        if turnover >= self.thresholds['turnover_high']:
            anomalies.append(AnomalyEvent(
                symbol=symbol,
                name=name,
                anomaly_type=AnomalyType.TURNOVER_SURGE,
                timestamp=datetime.now(),
                current_price=data.get('price', 0),
                change_rate=data.get('pct_change', 0),
                volume=data.get('volume', 0),
                amount=data.get('amount', 0),
                turnover=turnover,
                description=f"{name} 换手率异常，达到 {turnover:.2f}%",
                severity=3,
                extra_data={'turnover': turnover}
            ))
        
        return anomalies
    
    def subscribe(self, callback: Callable[[AnomalyEvent], None]):
        """
        订阅异动事件
        
        Args:
            callback: 回调函数
        """
        self.subscribers.append(callback)
        logger.info(f"Added anomaly subscriber, total: {len(self.subscribers)}")
    
    def notify_subscribers(self, anomaly: AnomalyEvent):
        """通知所有订阅者"""
        for callback in self.subscribers:
            try:
                callback(anomaly)
            except Exception as e:
                logger.error(f"Failed to notify subscriber: {e}")
    
    def get_recent_anomalies(self, hours: int = 24) -> List[AnomalyEvent]:
        """
        获取最近的异动事件
        
        Args:
            hours: 小时数
            
        Returns:
            异动事件列表
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [a for a in self.anomaly_events if a.timestamp >= cutoff_time]
    
    def get_anomaly_statistics(self) -> Dict[str, Any]:
        """获取异动统计信息"""
        recent_anomalies = self.get_recent_anomalies(24)
        
        # 按类型统计
        type_counts = {}
        for anomaly in recent_anomalies:
            type_name = anomaly.anomaly_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        
        return {
            'total_count': len(recent_anomalies),
            'type_distribution': type_counts,
            'high_severity_count': sum(1 for a in recent_anomalies if a.severity >= 4),
            'symbols_affected': len(set(a.symbol for a in recent_anomalies))
        }
