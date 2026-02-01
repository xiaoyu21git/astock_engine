"""
新闻舆情数据提供者
采集和处理新闻、公告、社交媒体数据
"""

import akshare as ak
import pandas as pd
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime, date, timedelta
import logging
import threading
import time
import requests
from bs4 import BeautifulSoup
from .base_provider import (
    BaseDataProvider, DataQuery, DataResponse, DataType
)

logger = logging.getLogger(__name__)


class NewsDataProvider(BaseDataProvider):
    """新闻数据提供者"""
    
    NEWS_SOURCES = {
        'eastmoney': '东方财富',
        'sina': '新浪财经',
        'cninfo': '巨潮资讯',
        'xueqiu': '雪球',
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("NewsDataProvider", config)
        self.cache: Dict[str, Any] = {}
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        # 订阅相关：当前实现为单回调轮询推送
        self._callback: Optional[Callable[[str, Dict[str, Any], datetime], None]] = None
        self._subscribe_thread: threading.Thread | None = None
        self._stop_subscribe: bool = False
        self._subscribe_interval: float = float(self.config.get("subscribe_interval", 5.0))
        self._last_publish_time: Optional[datetime] = None
        
    def initialize(self) -> bool:
        """初始化新闻数据源"""
        try:
            # 测试连接
            self._initialized = True
            logger.info("NewsDataProvider initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize NewsDataProvider: {e}")
            return False
    
    def get_data(self, query: DataQuery, data_type: DataType) -> DataResponse:
        """获取新闻数据"""
        try:
            if data_type == DataType.NEWS:
                df = self._get_news_data(query)
            elif data_type == DataType.ANNOUNCEMENT:
                df = self._get_announcement_data(query)
            else:
                raise ValueError(f"Unsupported data type: {data_type}")
            
            return DataResponse(
                data=df,
                data_type=data_type,
                query=query,
                timestamp=datetime.now(),
                source=self.name,
                success=True
            )
        except Exception as e:
            logger.error(f"Failed to get news data: {e}")
            return DataResponse(
                data=pd.DataFrame(),
                data_type=data_type,
                query=query,
                timestamp=datetime.now(),
                source=self.name,
                success=False,
                error_msg=str(e)
            )
    
    def _get_news_data(self, query: DataQuery) -> pd.DataFrame:
        """获取财经新闻"""
        all_news = []
        
        try:
            # 使用akshare获取财经新闻
            # 东方财富财经新闻
            df = ak.stock_news_em()
            
            if df is not None and not df.empty:
                df = df.rename(columns={
                    '标题': 'title',
                    '内容': 'content',
                    '发布时间': 'publish_time',
                    '文章来源': 'source',
                    '网址': 'url'
                })
                
                df['publish_time'] = pd.to_datetime(df['publish_time'])
                df['data_type'] = 'market_news'
                
                # 过滤日期范围
                if query.start_date:
                    df = df[df['publish_time'].dt.date >= query.start_date]
                if query.end_date:
                    df = df[df['publish_time'].dt.date <= query.end_date]
                
                all_news.append(df)
            
            # 如果指定了股票代码，获取个股新闻
            if query.symbols:
                for symbol in query.symbols:
                    symbol_news = self._get_stock_news(symbol)
                    if not symbol_news.empty:
                        all_news.append(symbol_news)
                        
        except Exception as e:
            logger.warning(f"Failed to get news data: {e}")
        
        if all_news:
            result = pd.concat(all_news, ignore_index=True)
            return result.sort_values('publish_time', ascending=False)
        
        return pd.DataFrame()
    
    def _get_stock_news(self, symbol: str) -> pd.DataFrame:
        """获取个股新闻"""
        try:
            symbol_code = symbol.split('.')[0]
            
            # 使用akshare获取个股新闻
            df = ak.stock_individual_info_em(symbol=symbol_code)
            
            if df is not None and not df.empty:
                # 处理新闻数据
                df['symbol'] = symbol
                df['data_type'] = 'stock_news'
                return df
                
        except Exception as e:
            logger.warning(f"Failed to get news for {symbol}: {e}")
        
        return pd.DataFrame()
    
    def _get_announcement_data(self, query: DataQuery) -> pd.DataFrame:
        """获取上市公司公告"""
        all_announcements = []
        
        for symbol in query.symbols:
            try:
                symbol_code = symbol.split('.')[0]
                
                # 获取公司公告
                df = ak.stock_notice_report(symbol=symbol_code)
                
                if df is not None and not df.empty:
                    df = df.rename(columns={
                        '公告日期': 'announce_date',
                        '公告标题': 'title',
                        '公告类型': 'announcement_type',
                        '公告内容': 'content'
                    })
                    
                    df['symbol'] = symbol
                    df['announce_date'] = pd.to_datetime(df['announce_date'])
                    
                    # 过滤日期范围
                    if query.start_date:
                        df = df[df['announce_date'].dt.date >= query.start_date]
                    if query.end_date:
                        df = df[df['announce_date'].dt.date <= query.end_date]
                    
                    all_announcements.append(df)
                    
            except Exception as e:
                logger.warning(f"Failed to get announcements for {symbol}: {e}")
                continue
        
        if all_announcements:
            result = pd.concat(all_announcements, ignore_index=True)
            return result.sort_values(['symbol', 'announce_date'], ascending=False)
        
        return pd.DataFrame()
    
    def get_realtime_data(self, symbols: List[str]) -> DataResponse:
        """获取实时新闻快讯"""
        try:
            # 获取实时财经快讯
            df = ak.stock_zh_a_alerts_cls()
            
            if df is not None and not df.empty:
                query = DataQuery(symbols=symbols)
                return DataResponse(
                    data=df,
                    data_type=DataType.NEWS,
                    query=query,
                    timestamp=datetime.now(),
                    source=self.name,
                    success=True
                )
                
        except Exception as e:
            logger.error(f"Failed to get realtime news: {e}")
        
        return DataResponse(
            data=pd.DataFrame(),
            data_type=DataType.NEWS,
            query=DataQuery(symbols=symbols),
            timestamp=datetime.now(),
            source=self.name,
            success=False
        )
    
    def subscribe(self, symbols: List[str], callback) -> bool:
        """订阅新闻推送"""
        if callback is None:
            return False

        # 当前实现：忽略 symbols 过滤，统一推送所有快讯，
        # 上层可在 callback 内自行按 symbol/title 过滤。
        self._callback = callback
        logger.info(
            "Subscribed to news stream (symbol filter=%d symbols, interval=%.2fs)",
            len(self.validate_symbols(symbols)),
            self._subscribe_interval,
        )

        if self._subscribe_thread is None or not self._subscribe_thread.is_alive():
            self._stop_subscribe = False
            self._subscribe_thread = threading.Thread(
                target=self._subscribe_loop,
                name="NewsDataProviderSubscribeLoop",
                daemon=True,
            )
            self._subscribe_thread.start()

        return True
    
    def unsubscribe(self, symbols: List[str]) -> bool:
        """取消新闻订阅"""
        # 目前实现为单回调，全局取消
        self._callback = None
        self._stop_subscribe = True
        logger.info("Unsubscribed from news stream")
        return True

    def _subscribe_loop(self) -> None:
        """后台轮询实时财经快讯并推送给回调。

        使用 ak.stock_zh_a_alerts_cls() 获取实时快讯，
        按发布时间去重，仅对新的消息触发回调。
        """
        while not self._stop_subscribe:
            try:
                if self._callback is None:
                    time.sleep(self._subscribe_interval)
                    continue

                resp = self.get_realtime_data(symbols=[])
                df = resp.data
                if df is None or df.empty:
                    time.sleep(self._subscribe_interval)
                    continue

                ts_col = None
                for cand in ("发布时间", "time", "时间", "publish_time"):
                    if cand in df.columns:
                        ts_col = cand
                        break

                if ts_col is not None:
                    df = df.copy()
                    df["_ts"] = pd.to_datetime(df[ts_col], errors="coerce")
                    df = df.dropna(subset=["_ts"])
                    df = df.sort_values("_ts")

                    for _, row in df.iterrows():
                        row_ts = row["_ts"]
                        if not isinstance(row_ts, pd.Timestamp):
                            continue
                        row_dt = row_ts.to_pydatetime()
                        if self._last_publish_time is not None and row_dt <= self._last_publish_time:
                            continue

                        self._last_publish_time = row_dt

                        # 尝试从列中推断相关股票代码，若没有则传空字符串
                        raw_symbol = (
                            row.get("代码")
                            or row.get("symbol")
                            or row.get("相关股票")
                            or ""
                        )
                        symbol_str = str(raw_symbol) if raw_symbol is not None else ""

                        try:
                            self._callback(symbol_str, row.to_dict(), resp.timestamp)
                        except Exception as exc:  # pragma: no cover - 防御性
                            logger.warning("NewsDataProvider callback failed: %s", exc)
                else:
                    # 无明显时间列时，直接将整表推给回调，由上层自行去重
                    now_ts = resp.timestamp
                    for _, row in df.iterrows():
                        raw_symbol = row.get("代码") or row.get("symbol") or ""
                        symbol_str = str(raw_symbol) if raw_symbol is not None else ""
                        try:
                            self._callback(symbol_str, row.to_dict(), now_ts)
                        except Exception as exc:  # pragma: no cover - 防御性
                            logger.warning("NewsDataProvider callback failed: %s", exc)

            except Exception as exc:  # pragma: no cover - 防御性
                logger.warning("NewsDataProvider subscribe loop error: %s", exc)

            time.sleep(self._subscribe_interval)

    def close(self) -> None:
        """关闭数据源并停止订阅线程"""
        self._stop_subscribe = True
        super().close()
    
    def get_hot_stocks(self, limit: int = 20) -> pd.DataFrame:
        """获取热门股票"""
        try:
            # 获取东方财富人气榜
            df = ak.stock_hot_rank_em()
            
            if df is not None and not df.empty:
                return df.head(limit)
                
        except Exception as e:
            logger.error(f"Failed to get hot stocks: {e}")
        
        return pd.DataFrame()
    
    def get_stock_comments(self, symbol: str) -> pd.DataFrame:
        """获取股票评论数据（雪球等）"""
        try:
            symbol_code = symbol.split('.')[0]
            
            # 获取股吧评论
            df = ak.stock_guba_em(symbol=symbol_code)
            
            if df is not None and not df.empty:
                df['symbol'] = symbol
                return df
                
        except Exception as e:
            logger.warning(f"Failed to get comments for {symbol}: {e}")
        
        return pd.DataFrame()
    
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """
        情感分析（简单实现）
        
        Args:
            text: 文本内容
            
        Returns:
            情感分析结果
        """
        # 简单的情感词典
        positive_words = ['利好', '上涨', '增长', '突破', '创新高', '盈利', '增持', '买入']
        negative_words = ['利空', '下跌', '下降', '跌破', '亏损', '减持', '卖出', '风险']
        
        positive_count = sum(1 for word in positive_words if word in text)
        negative_count = sum(1 for word in negative_words if word in text)
        
        # 计算情感得分 (-1到1)
        total = positive_count + negative_count
        if total == 0:
            sentiment_score = 0.0
        else:
            sentiment_score = (positive_count - negative_count) / total
        
        # 情感分类
        if sentiment_score > 0.3:
            sentiment = 'positive'
        elif sentiment_score < -0.3:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        
        return {
            'sentiment': sentiment,
            'score': sentiment_score,
            'positive_count': positive_count,
            'negative_count': negative_count
        }
