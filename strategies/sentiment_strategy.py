"""
舆情事件驱动策略
基于新闻情感和热度的事件驱动交易
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging
from .base_strategy import BaseStrategy, Signal

logger = logging.getLogger(__name__)


class SentimentDrivenStrategy(BaseStrategy):
    """舆情驱动策略"""
    
    def __init__(self, params: Dict = None):
        """
        初始化舆情驱动策略
        
        Args:
            params: 策略参数
                - sentiment_threshold: 情感阈值 (默认0.6)
                - hot_threshold: 热度阈值 (默认1000)
                - holding_period: 持有周期天数 (默认5)
                - event_types: 关注的事件类型列表
        """
        super().__init__("SentimentDrivenStrategy", params)
        
        self.sentiment_threshold = self.params.get('sentiment_threshold', 0.6)
        self.hot_threshold = self.params.get('hot_threshold', 1000)
        self.holding_period = self.params.get('holding_period', 5)
        self.event_types = self.params.get('event_types', [
            '业绩预增', '重组并购', '新产品发布', '政策利好', '行业景气'
        ])
        
        # 事件追踪
        self.event_positions = {}  # {symbol: entry_date}
        
    def generate_signals(self, data: pd.DataFrame, 
                        context: Optional[Dict] = None) -> List[Signal]:
        """
        生成交易信号
        
        Args:
            data: 市场数据
            context: 上下文信息
                - news_data: 新闻数据DataFrame
                    columns: ['symbol', 'title', 'publish_time', 'sentiment', 'score']
                - hot_stocks: 热门股票DataFrame
                
        Returns:
            信号列表
        """
        signals = []
        
        if context is None:
            return signals
        
        current_time = datetime.now()
        
        # 处理新闻事件
        if 'news_data' in context:
            news_df = context['news_data']
            event_signals = self._analyze_news_events(news_df, data, current_time)
            signals.extend(event_signals)
        
        # 处理热门股票
        if 'hot_stocks' in context:
            hot_df = context['hot_stocks']
            hot_signals = self._analyze_hot_stocks(hot_df, data, current_time)
            signals.extend(hot_signals)
        
        # 检查持有期限，生成卖出信号
        exit_signals = self._check_holding_period(data, current_time)
        signals.extend(exit_signals)
        
        return signals
    
    def _analyze_news_events(self, news_df: pd.DataFrame, 
                            data: pd.DataFrame,
                            current_time: datetime) -> List[Signal]:
        """
        分析新闻事件
        
        Args:
            news_df: 新闻数据
            data: 市场数据
            current_time: 当前时间
            
        Returns:
            信号列表
        """
        signals = []
        
        # 筛选正面新闻
        positive_news = news_df[
            (news_df['sentiment'] == 'positive') &
            (news_df['score'] >= self.sentiment_threshold)
        ]
        
        # 按股票分组
        for symbol in positive_news['symbol'].unique():
            # 已持有，跳过
            if symbol in self.positions:
                continue
            
            symbol_news = positive_news[positive_news['symbol'] == symbol]
            
            # 检查是否有关键事件
            has_key_event = False
            event_description = ""
            
            for _, news in symbol_news.iterrows():
                title = news['title']
                for event_type in self.event_types:
                    if event_type in title:
                        has_key_event = True
                        event_description = event_type
                        break
                if has_key_event:
                    break
            
            if not has_key_event:
                continue
            
            # 获取价格
            stock_data = data[data['symbol'] == symbol]
            if stock_data.empty:
                continue
            
            price = stock_data['close'].iloc[-1]
            
            # 计算新闻情感平均分
            avg_sentiment = symbol_news['score'].mean()
            
            signals.append(Signal(
                symbol=symbol,
                direction=1,
                strength=avg_sentiment,
                timestamp=current_time,
                price=price,
                reason=f"正面事件: {event_description}, 情感得分 {avg_sentiment:.2f}",
                metadata={
                    'event_type': event_description,
                    'news_count': len(symbol_news),
                    'sentiment_score': avg_sentiment
                }
            ))
            
            # 记录事件入场时间
            self.event_positions[symbol] = current_time
            
            logger.info(f"{symbol}: Detected event '{event_description}', "
                       f"sentiment {avg_sentiment:.2f}")
        
        return signals
    
    def _analyze_hot_stocks(self, hot_df: pd.DataFrame, 
                           data: pd.DataFrame,
                           current_time: datetime) -> List[Signal]:
        """
        分析热门股票
        
        Args:
            hot_df: 热门股票数据
            data: 市场数据
            current_time: 当前时间
            
        Returns:
            信号列表
        """
        signals = []
        
        # 筛选热度高的股票
        hot_stocks = hot_df[hot_df['热度'] >= self.hot_threshold]
        
        for _, row in hot_stocks.head(5).iterrows():  # 取前5只
            symbol = row['代码']
            
            # 已持有，跳过
            if symbol in self.positions:
                continue
            
            # 获取价格
            stock_data = data[data['symbol'] == symbol]
            if stock_data.empty:
                continue
            
            price = stock_data['close'].iloc[-1]
            pct_change = stock_data['pct_change'].iloc[-1] if 'pct_change' in stock_data else 0
            
            # 热度高且价格上涨
            if pct_change > 0:
                signals.append(Signal(
                    symbol=symbol,
                    direction=1,
                    strength=0.7,
                    timestamp=current_time,
                    price=price,
                    reason=f"热门股票: 热度 {row['热度']}, 涨幅 {pct_change:.2%}",
                    metadata={
                        'hot_rank': row.name + 1,
                        'hot_score': row['热度']
                    }
                ))
                
                self.event_positions[symbol] = current_time
        
        return signals
    
    def _check_holding_period(self, data: pd.DataFrame, 
                             current_time: datetime) -> List[Signal]:
        """
        检查持有期限
        
        Args:
            data: 市场数据
            current_time: 当前时间
            
        Returns:
            卖出信号列表
        """
        signals = []
        
        for symbol, entry_time in list(self.event_positions.items()):
            # 检查是否仍持有
            if symbol not in self.positions:
                del self.event_positions[symbol]
                continue
            
            # 检查持有时间
            holding_days = (current_time - entry_time).days
            
            if holding_days >= self.holding_period:
                # 获取价格
                stock_data = data[data['symbol'] == symbol]
                if stock_data.empty:
                    continue
                
                price = stock_data['close'].iloc[-1]
                position = self.positions[symbol]
                pnl_pct = position.unrealized_pnl_pct
                
                signals.append(Signal(
                    symbol=symbol,
                    direction=-1,
                    strength=1.0,
                    timestamp=current_time,
                    price=price,
                    reason=f"持有期满 {holding_days}天, 收益 {pnl_pct:.2%}"
                ))
                
                del self.event_positions[symbol]
                
                logger.info(f"{symbol}: Exit after {holding_days} days, "
                          f"return {pnl_pct:.2%}")
        
        return signals
    
    def analyze_event_performance(self) -> pd.DataFrame:
        """
        分析事件交易绩效
        
        Returns:
            事件绩效DataFrame
        """
        if not self.trades:
            return pd.DataFrame()
        
        events = []
        buy_trades = {}
        
        for trade in self.trades:
            if trade.action == 'BUY':
                buy_trades[trade.symbol] = trade
            elif trade.action == 'SELL' and trade.symbol in buy_trades:
                buy_trade = buy_trades[trade.symbol]
                holding_days = (trade.timestamp - buy_trade.timestamp).days
                pnl = (trade.price - buy_trade.price) * trade.quantity
                pnl_pct = pnl / (buy_trade.price * buy_trade.quantity)
                
                events.append({
                    'symbol': trade.symbol,
                    'entry_date': buy_trade.timestamp,
                    'exit_date': trade.timestamp,
                    'holding_days': holding_days,
                    'entry_price': buy_trade.price,
                    'exit_price': trade.price,
                    'return_pct': pnl_pct,
                    'pnl': pnl,
                    'reason': buy_trade.reason
                })
                
                del buy_trades[trade.symbol]
        
        return pd.DataFrame(events)
