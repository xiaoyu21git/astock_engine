"""
A股数据提供者
使用 akshare 获取A股市场数据
"""

import akshare as ak
import pandas as pd
from typing import List, Dict, Optional, Any
from datetime import datetime, date, timedelta
import logging
from .base_provider import (
    BaseDataProvider, DataQuery, DataResponse, DataType
)

logger = logging.getLogger(__name__)


class StockDataProvider(BaseDataProvider):
    """A股数据提供者"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("StockDataProvider", config)
        self.cache = {}
        self.subscribers = {}
        
    def initialize(self) -> bool:
        """初始化数据源"""
        try:
            # 测试连接 - 获取交易日历
            today = datetime.now().strftime("%Y%m%d")
            ak.tool_trade_date_hist_sina()
            self._initialized = True
            logger.info("StockDataProvider initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize StockDataProvider: {e}")
            return False
    
    def get_data(self, query: DataQuery, data_type: DataType) -> DataResponse:
        """
        获取股票数据
        
        Args:
            query: 查询参数
            data_type: 数据类型
            
        Returns:
            数据响应
        """
        try:
            if data_type == DataType.STOCK_DAILY:
                df = self._get_daily_data(query)
            elif data_type == DataType.STOCK_MINUTE:
                df = self._get_minute_data(query)
            elif data_type == DataType.INDEX_DAILY:
                df = self._get_index_data(query)
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
            logger.error(f"Failed to get data: {e}")
            return DataResponse(
                data=pd.DataFrame(),
                data_type=data_type,
                query=query,
                timestamp=datetime.now(),
                source=self.name,
                success=False,
                error_msg=str(e)
            )
    
    def _get_daily_data(self, query: DataQuery) -> pd.DataFrame:
        """获取日线数据"""
        all_data = []
        
        for symbol in query.symbols:
            try:
                # akshare 获取股票历史数据
                # 格式: 000001 需要转换为标准格式
                symbol_code = symbol.split('.')[0]
                
                # 获取历史数据
                df = ak.stock_zh_a_hist(
                    symbol=symbol_code,
                    period="daily",
                    start_date=query.start_date.strftime("%Y%m%d") if query.start_date else "20200101",
                    end_date=query.end_date.strftime("%Y%m%d") if query.end_date else datetime.now().strftime("%Y%m%d"),
                    adjust=query.adjust
                )
                
                if df is not None and not df.empty:
                    # 重命名列
                    df = df.rename(columns={
                        '日期': 'date',
                        '开盘': 'open',
                        '收盘': 'close',
                        '最高': 'high',
                        '最低': 'low',
                        '成交量': 'volume',
                        '成交额': 'amount',
                        '振幅': 'amplitude',
                        '涨跌幅': 'pct_change',
                        '涨跌额': 'change',
                        '换手率': 'turnover'
                    })
                    
                    df['symbol'] = symbol
                    df['date'] = pd.to_datetime(df['date'])
                    all_data.append(df)
                    
            except Exception as e:
                logger.warning(f"Failed to get data for {symbol}: {e}")
                continue
        
        if all_data:
            result = pd.concat(all_data, ignore_index=True)
            return result.sort_values(['symbol', 'date'])
        
        return pd.DataFrame()
    
    def _get_minute_data(self, query: DataQuery) -> pd.DataFrame:
        """获取分钟线数据"""
        all_data = []
        
        # 解析频率
        period_map = {
            '1m': '1',
            '5m': '5',
            '15m': '15',
            '30m': '30',
            '60m': '60'
        }
        period = period_map.get(query.frequency, '1')
        
        for symbol in query.symbols:
            try:
                symbol_code = symbol.split('.')[0]
                
                # akshare 分钟数据
                df = ak.stock_zh_a_hist_min_em(
                    symbol=symbol_code,
                    period=period,
                    adjust=query.adjust
                )
                
                if df is not None and not df.empty:
                    df = df.rename(columns={
                        '时间': 'datetime',
                        '开盘': 'open',
                        '收盘': 'close',
                        '最高': 'high',
                        '最低': 'low',
                        '成交量': 'volume',
                        '成交额': 'amount'
                    })
                    
                    df['symbol'] = symbol
                    df['datetime'] = pd.to_datetime(df['datetime'])
                    all_data.append(df)
                    
            except Exception as e:
                logger.warning(f"Failed to get minute data for {symbol}: {e}")
                continue
        
        if all_data:
            result = pd.concat(all_data, ignore_index=True)
            return result.sort_values(['symbol', 'datetime'])
        
        return pd.DataFrame()
    
    def _get_index_data(self, query: DataQuery) -> pd.DataFrame:
        """获取指数数据"""
        all_data = []
        
        # 指数代码映射
        index_map = {
            '000001.SH': 'sh000001',  # 上证指数
            '399001.SZ': 'sz399001',  # 深证成指
            '399006.SZ': 'sz399006',  # 创业板指
            '000300.SH': 'sh000300',  # 沪深300
            '000905.SH': 'sh000905',  # 中证500
        }
        
        for symbol in query.symbols:
            try:
                index_code = index_map.get(symbol, symbol)
                
                df = ak.stock_zh_index_daily(symbol=index_code)
                
                if df is not None and not df.empty:
                    df = df.rename(columns={
                        'date': 'date',
                        'open': 'open',
                        'close': 'close',
                        'high': 'high',
                        'low': 'low',
                        'volume': 'volume'
                    })
                    
                    df['symbol'] = symbol
                    df['date'] = pd.to_datetime(df['date'])
                    
                    # 过滤日期范围
                    if query.start_date:
                        df = df[df['date'] >= pd.to_datetime(query.start_date)]
                    if query.end_date:
                        df = df[df['date'] <= pd.to_datetime(query.end_date)]
                    
                    all_data.append(df)
                    
            except Exception as e:
                logger.warning(f"Failed to get index data for {symbol}: {e}")
                continue
        
        if all_data:
            result = pd.concat(all_data, ignore_index=True)
            return result.sort_values(['symbol', 'date'])
        
        return pd.DataFrame()
    
    def get_realtime_data(self, symbols: List[str]) -> DataResponse:
        """获取实时行情数据"""
        try:
            # 获取实时行情
            df = ak.stock_zh_a_spot_em()
            
            if df is not None and not df.empty:
                # 提取需要的股票
                symbol_codes = [s.split('.')[0] for s in symbols]
                df = df[df['代码'].isin(symbol_codes)]
                
                # 重命名列
                df = df.rename(columns={
                    '代码': 'symbol',
                    '名称': 'name',
                    '最新价': 'price',
                    '涨跌幅': 'pct_change',
                    '涨跌额': 'change',
                    '成交量': 'volume',
                    '成交额': 'amount',
                    '振幅': 'amplitude',
                    '最高': 'high',
                    '最低': 'low',
                    '今开': 'open',
                    '昨收': 'pre_close',
                    '换手率': 'turnover',
                    '市盈率': 'pe',
                    '市净率': 'pb'
                })
                
                query = DataQuery(symbols=symbols)
                return DataResponse(
                    data=df,
                    data_type=DataType.STOCK_TICK,
                    query=query,
                    timestamp=datetime.now(),
                    source=self.name,
                    success=True
                )
                
        except Exception as e:
            logger.error(f"Failed to get realtime data: {e}")
        
        return DataResponse(
            data=pd.DataFrame(),
            data_type=DataType.STOCK_TICK,
            query=DataQuery(symbols=symbols),
            timestamp=datetime.now(),
            source=self.name,
            success=False
        )
    
    def subscribe(self, symbols: List[str], callback) -> bool:
        """订阅实时数据（需要实现WebSocket）"""
        # TODO: 实现WebSocket订阅
        for symbol in symbols:
            self.subscribers[symbol] = callback
        logger.info(f"Subscribed to {len(symbols)} symbols")
        return True
    
    def unsubscribe(self, symbols: List[str]) -> bool:
        """取消订阅"""
        for symbol in symbols:
            self.subscribers.pop(symbol, None)
        logger.info(f"Unsubscribed from {len(symbols)} symbols")
        return True
    
    def get_stock_list(self) -> pd.DataFrame:
        """获取A股股票列表"""
        try:
            df = ak.stock_zh_a_spot_em()
            return df[['代码', '名称']].rename(columns={'代码': 'symbol', '名称': 'name'})
        except Exception as e:
            logger.error(f"Failed to get stock list: {e}")
            return pd.DataFrame()
