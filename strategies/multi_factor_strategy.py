"""
多因子选股策略
综合技术、量价、舆情等多个因子进行选股
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime
import logging
from .base_strategy import BaseStrategy, Signal

logger = logging.getLogger(__name__)


class MultiFactorStrategy(BaseStrategy):
    """多因子选股策略"""
    
    def __init__(self, params: Dict = None):
        """
        初始化多因子策略
        
        Args:
            params: 策略参数
                - technical_weight: 技术因子权重 (默认0.4)
                - volume_weight: 量价因子权重 (默认0.3)
                - sentiment_weight: 舆情因子权重 (默认0.3)
                - buy_threshold: 买入阈值 (默认0.6)
                - sell_threshold: 卖出阈值 (默认0.4)
                - top_n: 选择前N只股票 (默认10)
        """
        super().__init__("MultiFactorStrategy", params)
        
        # 因子权重
        self.technical_weight = self.params.get('technical_weight', 0.4)
        self.volume_weight = self.params.get('volume_weight', 0.3)
        self.sentiment_weight = self.params.get('sentiment_weight', 0.3)
        
        # 交易阈值
        self.buy_threshold = self.params.get('buy_threshold', 0.6)
        self.sell_threshold = self.params.get('sell_threshold', 0.4)
        self.top_n = self.params.get('top_n', 10)
        
    def generate_signals(self, data: pd.DataFrame, 
                        context: Optional[Dict] = None) -> List[Signal]:
        """
        生成交易信号
        
        Args:
            data: 市场数据
            context: 上下文信息
                - technical_factors: 技术因子DataFrame
                - volume_factors: 量价因子DataFrame
                - sentiment_factors: 舆情因子DataFrame
                
        Returns:
            信号列表
        """
        signals = []
        
        if context is None:
            context = {}
        
        # 计算各类因子
        technical_scores = self._calculate_technical_factors(data, context.get('technical_factors'))
        volume_scores = self._calculate_volume_factors(data, context.get('volume_factors'))
        sentiment_scores = self._calculate_sentiment_factors(data, context.get('sentiment_factors'))
        
        # 合并因子得分
        combined_scores = self._combine_factors(
            technical_scores, volume_scores, sentiment_scores
        )
        
        if combined_scores.empty:
            return signals
        
        # 生成买入信号
        buy_candidates = combined_scores[combined_scores['score'] >= self.buy_threshold]
        buy_candidates = buy_candidates.nlargest(self.top_n, 'score')
        
        current_time = datetime.now()
        
        for symbol, row in buy_candidates.iterrows():
            # 如果已经持有，跳过
            if symbol in self.positions:
                continue
            
            price = data[data['symbol'] == symbol]['close'].iloc[-1] if len(data) > 0 else 0
            
            signals.append(Signal(
                symbol=symbol,
                direction=1,
                strength=row['score'],
                timestamp=current_time,
                price=price,
                reason=f"多因子选股: 综合得分 {row['score']:.2f}",
                metadata={
                    'technical_score': row['technical_score'],
                    'volume_score': row['volume_score'],
                    'sentiment_score': row['sentiment_score']
                }
            ))
        
        # 生成卖出信号
        for symbol, position in self.positions.items():
            if symbol in combined_scores.index:
                score = combined_scores.loc[symbol, 'score']
                
                # 得分低于阈值，卖出
                if score < self.sell_threshold:
                    price = data[data['symbol'] == symbol]['close'].iloc[-1] if len(data) > 0 else position.current_price
                    
                    signals.append(Signal(
                        symbol=symbol,
                        direction=-1,
                        strength=1.0,
                        timestamp=current_time,
                        price=price,
                        reason=f"因子得分下降: {score:.2f}"
                    ))
        
        return signals
    
    def _calculate_technical_factors(self, data: pd.DataFrame, 
                                    factors: Optional[pd.DataFrame]) -> pd.DataFrame:
        """
        计算技术因子得分
        
        Args:
            data: 市场数据
            factors: 预计算的技术因子
            
        Returns:
            技术因子得分
        """
        if factors is not None:
            return factors
        
        # 如果没有提供因子，自己计算基础技术指标
        scores = {}
        
        for symbol in data['symbol'].unique():
            symbol_data = data[data['symbol'] == symbol].copy()
            
            if len(symbol_data) < 20:
                continue
            
            # 计算技术指标
            symbol_data['ma5'] = symbol_data['close'].rolling(5).mean()
            symbol_data['ma20'] = symbol_data['close'].rolling(20).mean()
            symbol_data['rsi'] = self._calculate_rsi(symbol_data['close'], 14)
            
            # 评分逻辑
            score = 0.5  # 基础分
            
            # 均线多头排列
            if symbol_data['ma5'].iloc[-1] > symbol_data['ma20'].iloc[-1]:
                score += 0.2
            
            # RSI在合理区间
            rsi = symbol_data['rsi'].iloc[-1]
            if 30 <= rsi <= 70:
                score += 0.2
            elif rsi < 30:  # 超卖
                score += 0.3
            
            # 价格突破均线
            if symbol_data['close'].iloc[-1] > symbol_data['ma20'].iloc[-1]:
                score += 0.1
            
            scores[symbol] = max(0, min(1, score))
        
        return pd.DataFrame.from_dict(scores, orient='index', columns=['technical_score'])
    
    def _calculate_volume_factors(self, data: pd.DataFrame, 
                                  factors: Optional[pd.DataFrame]) -> pd.DataFrame:
        """
        计算量价因子得分
        
        Args:
            data: 市场数据
            factors: 预计算的量价因子
            
        Returns:
            量价因子得分
        """
        if factors is not None:
            return factors
        
        scores = {}
        
        for symbol in data['symbol'].unique():
            symbol_data = data[data['symbol'] == symbol].copy()
            
            if len(symbol_data) < 5:
                continue
            
            # 计算量比
            avg_volume = symbol_data['volume'].tail(5).mean()
            current_volume = symbol_data['volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
            
            # 计算涨幅
            pct_change = symbol_data['pct_change'].iloc[-1] if 'pct_change' in symbol_data else 0
            
            # 评分
            score = 0.5
            
            # 放量上涨
            if volume_ratio > 1.5 and pct_change > 2:
                score += 0.3
            elif volume_ratio > 1.2 and pct_change > 0:
                score += 0.2
            
            # 缩量下跌（潜在止跌）
            if volume_ratio < 0.8 and -2 < pct_change < 0:
                score += 0.1
            
            # 换手率
            if 'turnover' in symbol_data:
                turnover = symbol_data['turnover'].iloc[-1]
                if 5 < turnover < 15:  # 合理换手率
                    score += 0.2
            
            scores[symbol] = max(0, min(1, score))
        
        return pd.DataFrame.from_dict(scores, orient='index', columns=['volume_score'])
    
    def _calculate_sentiment_factors(self, data: pd.DataFrame, 
                                    factors: Optional[pd.DataFrame]) -> pd.DataFrame:
        """
        计算舆情因子得分
        
        Args:
            data: 市场数据
            factors: 预计算的舆情因子
            
        Returns:
            舆情因子得分
        """
        if factors is not None:
            return factors
        
        # 默认中性得分
        symbols = data['symbol'].unique()
        scores = {symbol: 0.5 for symbol in symbols}
        
        return pd.DataFrame.from_dict(scores, orient='index', columns=['sentiment_score'])
    
    def _combine_factors(self, technical: pd.DataFrame, 
                        volume: pd.DataFrame, 
                        sentiment: pd.DataFrame) -> pd.DataFrame:
        """
        合并多个因子得分
        
        Args:
            technical: 技术因子
            volume: 量价因子
            sentiment: 舆情因子
            
        Returns:
            综合得分DataFrame
        """
        # 合并所有因子
        combined = pd.DataFrame()
        
        if not technical.empty:
            combined = technical
        
        if not volume.empty:
            if combined.empty:
                combined = volume
            else:
                combined = combined.join(volume, how='outer')
        
        if not sentiment.empty:
            if combined.empty:
                combined = sentiment
            else:
                combined = combined.join(sentiment, how='outer')
        
        # 填充缺失值
        combined = combined.fillna(0.5)
        
        # 计算加权得分
        combined['score'] = (
            combined.get('technical_score', 0.5) * self.technical_weight +
            combined.get('volume_score', 0.5) * self.volume_weight +
            combined.get('sentiment_score', 0.5) * self.sentiment_weight
        )
        
        return combined
    
    @staticmethod
    def _calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        """计算RSI指标"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
