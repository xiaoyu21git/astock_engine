"""
股指期货联动套利策略
监控股指期货基差，执行期现套利
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime
import logging
from .base_strategy import BaseStrategy, Signal

logger = logging.getLogger(__name__)


class IndexFuturesArbitrageStrategy(BaseStrategy):
    """股指期货套利策略"""
    
    def __init__(self, params: Dict = None):
        """
        初始化套利策略
        
        Args:
            params: 策略参数
                - basis_threshold: 基差率阈值 (默认2%)
                - index_symbol: 指数代码 (默认'000300.SH')
                - futures_symbol: 期货合约代码
                - hedge_ratio: 对冲比例 (默认1.0)
        """
        super().__init__("IndexFuturesArbitrageStrategy", params)
        
        self.basis_threshold = self.params.get('basis_threshold', 0.02)  # 2%
        self.index_symbol = self.params.get('index_symbol', '000300.SH')
        self.futures_symbol = self.params.get('futures_symbol')
        self.hedge_ratio = self.params.get('hedge_ratio', 1.0)
        
        # 套利状态
        self.arbitrage_position = None  # 'long_basis' or 'short_basis'
        
    def generate_signals(self, data: pd.DataFrame, 
                        context: Optional[Dict] = None) -> List[Signal]:
        """
        生成套利信号
        
        Args:
            data: 市场数据
            context: 上下文信息
                - index_price: 指数价格
                - futures_price: 期货价格
                - basis_data: 基差数据DataFrame
                
        Returns:
            信号列表
        """
        signals = []
        
        if context is None or 'basis_data' not in context:
            logger.warning("No basis data provided")
            return signals
        
        basis_df = context['basis_data']
        
        if basis_df.empty:
            return signals
        
        # 获取最新基差
        latest_basis = basis_df.iloc[-1]
        basis_rate = latest_basis['basis_rate']
        index_price = latest_basis['close_index']
        futures_price = latest_basis['close_futures']
        
        current_time = datetime.now()
        
        # 基差过大，做多现货做空期货
        if basis_rate > self.basis_threshold and self.arbitrage_position != 'long_basis':
            # 构建指数成分股组合
            basket_symbols = self._get_index_basket(self.index_symbol)
            
            for symbol in basket_symbols[:10]:  # 选前10只权重股
                signals.append(Signal(
                    symbol=symbol,
                    direction=1,
                    strength=0.8,
                    timestamp=current_time,
                    price=data[data['symbol'] == symbol]['close'].iloc[-1] if len(data) > 0 else 0,
                    reason=f"正基差套利: 基差率 {basis_rate:.2%}",
                    metadata={
                        'arbitrage_type': 'long_basis',
                        'basis_rate': basis_rate
                    }
                ))
            
            self.arbitrage_position = 'long_basis'
            logger.info(f"Opening long basis arbitrage, basis rate: {basis_rate:.2%}")
        
        # 基差过小，做空现货做多期货
        elif basis_rate < -self.basis_threshold and self.arbitrage_position != 'short_basis':
            # 平掉现有多头持仓
            for symbol in list(self.positions.keys()):
                signals.append(Signal(
                    symbol=symbol,
                    direction=-1,
                    strength=1.0,
                    timestamp=current_time,
                    price=data[data['symbol'] == symbol]['close'].iloc[-1] if len(data) > 0 else 0,
                    reason=f"负基差套利: 基差率 {basis_rate:.2%}"
                ))
            
            self.arbitrage_position = 'short_basis'
            logger.info(f"Opening short basis arbitrage, basis rate: {basis_rate:.2%}")
        
        # 基差回归，平仓
        elif abs(basis_rate) < self.basis_threshold * 0.5 and self.arbitrage_position is not None:
            for symbol in list(self.positions.keys()):
                signals.append(Signal(
                    symbol=symbol,
                    direction=-1,
                    strength=1.0,
                    timestamp=current_time,
                    price=data[data['symbol'] == symbol]['close'].iloc[-1] if len(data) > 0 else 0,
                    reason=f"基差回归平仓: 基差率 {basis_rate:.2%}"
                ))
            
            self.arbitrage_position = None
            logger.info(f"Closing arbitrage position, basis normalized: {basis_rate:.2%}")
        
        return signals
    
    def _get_index_basket(self, index_symbol: str) -> List[str]:
        """
        获取指数成分股
        
        Args:
            index_symbol: 指数代码
            
        Returns:
            成分股列表
        """
        # 沪深300前10大权重股（示例）
        if '000300' in index_symbol:
            return [
                '600519.SH',  # 贵州茅台
                '600036.SH',  # 招商银行
                '601318.SH',  # 中国平安
                '000858.SZ',  # 五粮液
                '600276.SH',  # 恒瑞医药
                '601166.SH',  # 兴业银行
                '000333.SZ',  # 美的集团
                '600030.SH',  # 中信证券
                '000002.SZ',  # 万科A
                '601328.SH',  # 交通银行
            ]
        # 上证50
        elif '000016' in index_symbol:
            return [
                '600519.SH',
                '600036.SH',
                '601318.SH',
                '600276.SH',
                '600030.SH',
            ]
        # 中证500
        elif '000905' in index_symbol:
            return [
                '002594.SZ',
                '002415.SZ',
                '000333.SZ',
            ]
        else:
            return []
    
    def calculate_hedge_quantity(self, index_value: float, 
                                 futures_price: float,
                                 portfolio_value: float) -> int:
        """
        计算期货对冲手数
        
        Args:
            index_value: 指数点位
            futures_price: 期货价格
            portfolio_value: 组合价值
            
        Returns:
            期货手数
        """
        # 期货合约乘数（沪深300为300）
        multiplier = 300
        
        # 计算所需手数
        hedge_quantity = int(portfolio_value / (futures_price * multiplier) * self.hedge_ratio)
        
        return max(1, hedge_quantity)
