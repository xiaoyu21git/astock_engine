"""
商品期货选股策略
根据商品期货价格变化选择相关股票
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime
import logging
from .base_strategy import BaseStrategy, Signal

logger = logging.getLogger(__name__)


class CommodityDrivenStrategy(BaseStrategy):
    """商品期货驱动选股策略"""
    
    # 商品期货与股票映射关系
    COMMODITY_STOCK_MAP = {
        # 黑色系
        'RB': {  # 螺纹钢
            'name': '钢铁',
            'stocks': ['600019.SH', '000709.SZ', '000708.SZ', '600005.SH'],  # 宝钢、河钢、首钢、武钢
            'correlation': 'positive'  # 正相关
        },
        'I': {  # 铁矿石
            'name': '铁矿石',
            'stocks': ['600808.SH', '600117.SH'],
            'correlation': 'negative'  # 负相关（成本）
        },
        # 能源化工
        'SC': {  # 原油
            'name': '石油化工',
            'stocks': ['600028.SH', '600688.SH', '600971.SH'],  # 中石化、上海石化、恒源煤电
            'correlation': 'positive'
        },
        'TA': {  # PTA
            'name': '化纤',
            'stocks': ['000301.SZ', '601233.SH'],  # 东方盛虹、桐昆股份
            'correlation': 'positive'
        },
        # 有色金属
        'CU': {  # 铜
            'name': '有色金属',
            'stocks': ['601600.SH', '000630.SZ', '002378.SZ'],  # 中国铝业、铜陵有色、章源钨业
            'correlation': 'positive'
        },
        'AL': {  # 铝
            'name': '铝业',
            'stocks': ['601600.SH', '000933.SZ'],
            'correlation': 'positive'
        },
        # 农产品
        'M': {  # 豆粕
            'name': '饲料养殖',
            'stocks': ['000876.SZ', '002311.SZ', '300498.SZ'],  # 新希望、海大集团、温氏股份
            'correlation': 'negative'  # 成本负相关
        }
    }
    
    def __init__(self, params: Dict = None):
        """
        初始化商品期货选股策略
        
        Args:
            params: 策略参数
                - price_change_threshold: 价格变动阈值 (默认5%)
                - lookback_period: 回看周期 (默认20天)
                - correlation_weight: 相关性权重 (默认0.7)
        """
        super().__init__("CommodityDrivenStrategy", params)
        
        self.price_change_threshold = self.params.get('price_change_threshold', 0.05)
        self.lookback_period = self.params.get('lookback_period', 20)
        self.correlation_weight = self.params.get('correlation_weight', 0.7)
        
    def generate_signals(self, data: pd.DataFrame, 
                        context: Optional[Dict] = None) -> List[Signal]:
        """
        生成交易信号
        
        Args:
            data: 市场数据
            context: 上下文信息
                - commodity_prices: 商品期货价格DataFrame
                    columns: ['commodity', 'price', 'pct_change']
                
        Returns:
            信号列表
        """
        signals = []
        
        if context is None or 'commodity_prices' not in context:
            logger.warning("No commodity prices provided")
            return signals
        
        commodity_df = context['commodity_prices']
        current_time = datetime.now()
        
        # 分析每个商品期货的价格变动
        for _, row in commodity_df.iterrows():
            commodity = row['commodity']
            pct_change = row['pct_change']
            
            if commodity not in self.COMMODITY_STOCK_MAP:
                continue
            
            # 价格显著变动
            if abs(pct_change) < self.price_change_threshold:
                continue
            
            mapping = self.COMMODITY_STOCK_MAP[commodity]
            stocks = mapping['stocks']
            correlation = mapping['correlation']
            
            # 确定交易方向
            if correlation == 'positive':
                # 正相关：商品涨，股票涨
                direction = 1 if pct_change > 0 else -1
            else:
                # 负相关：商品涨（成本上升），股票跌
                direction = -1 if pct_change > 0 else 1
            
            # 生成信号
            for symbol in stocks:
                # 检查是否在数据中
                stock_data = data[data['symbol'] == symbol]
                if stock_data.empty:
                    continue
                
                price = stock_data['close'].iloc[-1]
                
                # 如果是买入信号且已持有，跳过
                if direction == 1 and symbol in self.positions:
                    continue
                
                # 如果是卖出信号但未持有，跳过
                if direction == -1 and symbol not in self.positions:
                    continue
                
                strength = min(abs(pct_change) / self.price_change_threshold, 1.0)
                
                signals.append(Signal(
                    symbol=symbol,
                    direction=direction,
                    strength=strength,
                    timestamp=current_time,
                    price=price,
                    reason=f"{mapping['name']}期货{'上涨' if pct_change > 0 else '下跌'} {abs(pct_change):.1%}",
                    metadata={
                        'commodity': commodity,
                        'commodity_change': pct_change,
                        'correlation': correlation
                    }
                ))
                
                logger.info(f"{symbol}: {mapping['name']} commodity {commodity} "
                          f"changed {pct_change:.2%}, signal: {direction}")
        
        return signals
    
    def analyze_correlation(self, stock_data: pd.DataFrame, 
                          commodity_data: pd.DataFrame) -> float:
        """
        分析股票与商品期货的相关性
        
        Args:
            stock_data: 股票价格数据
            commodity_data: 商品期货价格数据
            
        Returns:
            相关系数
        """
        if len(stock_data) < 2 or len(commodity_data) < 2:
            return 0.0
        
        # 计算收益率
        stock_returns = stock_data['close'].pct_change().dropna()
        commodity_returns = commodity_data['close'].pct_change().dropna()
        
        # 对齐数据
        min_len = min(len(stock_returns), len(commodity_returns))
        stock_returns = stock_returns.tail(min_len)
        commodity_returns = commodity_returns.tail(min_len)
        
        # 计算相关系数
        correlation = stock_returns.corr(commodity_returns)
        
        return correlation
    
    def get_industry_exposure(self) -> Dict[str, float]:
        """
        获取行业敞口
        
        Returns:
            行业敞口字典
        """
        exposure = {}
        
        for symbol, position in self.positions.items():
            # 找到股票对应的商品
            for commodity, mapping in self.COMMODITY_STOCK_MAP.items():
                if symbol in mapping['stocks']:
                    industry = mapping['name']
                    exposure[industry] = exposure.get(industry, 0) + position.market_value
        
        return exposure
