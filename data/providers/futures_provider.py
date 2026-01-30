"""
期货数据提供者
获取股指期货和商品期货数据
"""

import akshare as ak
import pandas as pd
from typing import List, Dict, Optional, Any
from datetime import datetime, date
import logging
from .base_provider import (
    BaseDataProvider, DataQuery, DataResponse, DataType
)

logger = logging.getLogger(__name__)


class FuturesDataProvider(BaseDataProvider):
    """期货数据提供者"""
    
    # 股指期货代码映射
    INDEX_FUTURES_MAP = {
        'IF': '沪深300股指期货',
        'IH': '上证50股指期货',
        'IC': '中证500股指期货',
        'IM': '中证1000股指期货',
    }
    
    # 主力合约映射
    MAIN_CONTRACT_MAP = {
        'IF': 'IF0',  # 主力合约
        'IH': 'IH0',
        'IC': 'IC0',
        'IM': 'IM0',
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("FuturesDataProvider", config)
        self.cache = {}
        
    def initialize(self) -> bool:
        """初始化期货数据源"""
        try:
            # 测试连接 - 获取期货列表
            ak.futures_zh_spot()
            self._initialized = True
            logger.info("FuturesDataProvider initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize FuturesDataProvider: {e}")
            return False
    
    def get_data(self, query: DataQuery, data_type: DataType) -> DataResponse:
        """获取期货数据"""
        try:
            if data_type == DataType.FUTURES_DAILY:
                df = self._get_daily_data(query)
            elif data_type == DataType.FUTURES_MINUTE:
                df = self._get_minute_data(query)
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
            logger.error(f"Failed to get futures data: {e}")
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
        """获取期货日线数据"""
        all_data = []
        
        for symbol in query.symbols:
            try:
                # 判断是股指期货还是商品期货
                if any(symbol.startswith(prefix) for prefix in ['IF', 'IH', 'IC', 'IM']):
                    df = self._get_index_futures_daily(symbol, query)
                else:
                    df = self._get_commodity_futures_daily(symbol, query)
                
                if df is not None and not df.empty:
                    df['symbol'] = symbol
                    all_data.append(df)
                    
            except Exception as e:
                logger.warning(f"Failed to get daily data for {symbol}: {e}")
                continue
        
        if all_data:
            result = pd.concat(all_data, ignore_index=True)
            return result.sort_values(['symbol', 'date'])
        
        return pd.DataFrame()
    
    def _get_index_futures_daily(self, symbol: str, query: DataQuery) -> pd.DataFrame:
        """获取股指期货日线数据"""
        try:
            # 提取品种代码
            variety = symbol[:2]  # IF, IH, IC, IM
            
            # 获取股指期货数据
            df = ak.futures_zh_daily_sina(symbol=symbol)
            
            if df is not None and not df.empty:
                df = df.rename(columns={
                    'date': 'date',
                    'open': 'open',
                    'high': 'high',
                    'low': 'low',
                    'close': 'close',
                    'volume': 'volume',
                    'hold': 'open_interest'
                })
                
                df['date'] = pd.to_datetime(df['date'])
                
                # 过滤日期范围
                if query.start_date:
                    df = df[df['date'] >= pd.to_datetime(query.start_date)]
                if query.end_date:
                    df = df[df['date'] <= pd.to_datetime(query.end_date)]
                
                return df
                
        except Exception as e:
            logger.warning(f"Failed to get index futures data for {symbol}: {e}")
        
        return pd.DataFrame()
    
    def _get_commodity_futures_daily(self, symbol: str, query: DataQuery) -> pd.DataFrame:
        """获取商品期货日线数据"""
        try:
            # 获取商品期货数据
            df = ak.futures_zh_daily_sina(symbol=symbol)
            
            if df is not None and not df.empty:
                df = df.rename(columns={
                    'date': 'date',
                    'open': 'open',
                    'high': 'high',
                    'low': 'low',
                    'close': 'close',
                    'volume': 'volume',
                    'hold': 'open_interest'
                })
                
                df['date'] = pd.to_datetime(df['date'])
                
                # 过滤日期范围
                if query.start_date:
                    df = df[df['date'] >= pd.to_datetime(query.start_date)]
                if query.end_date:
                    df = df[df['date'] <= pd.to_datetime(query.end_date)]
                
                return df
                
        except Exception as e:
            logger.warning(f"Failed to get commodity futures data for {symbol}: {e}")
        
        return pd.DataFrame()
    
    def _get_minute_data(self, query: DataQuery) -> pd.DataFrame:
        """获取期货分钟线数据"""
        all_data = []
        
        for symbol in query.symbols:
            try:
                # 获取期货分钟数据
                df = ak.futures_zh_minute_sina(symbol=symbol, period=query.frequency)
                
                if df is not None and not df.empty:
                    df = df.rename(columns={
                        'datetime': 'datetime',
                        'open': 'open',
                        'high': 'high',
                        'low': 'low',
                        'close': 'close',
                        'volume': 'volume'
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
    
    def get_realtime_data(self, symbols: List[str]) -> DataResponse:
        """获取期货实时行情"""
        try:
            # 获取期货实时行情
            df = ak.futures_zh_spot()
            
            if df is not None and not df.empty:
                # 筛选指定合约
                df = df[df['symbol'].isin(symbols)]
                
                query = DataQuery(symbols=symbols)
                return DataResponse(
                    data=df,
                    data_type=DataType.FUTURES_MINUTE,
                    query=query,
                    timestamp=datetime.now(),
                    source=self.name,
                    success=True
                )
                
        except Exception as e:
            logger.error(f"Failed to get realtime futures data: {e}")
        
        return DataResponse(
            data=pd.DataFrame(),
            data_type=DataType.FUTURES_MINUTE,
            query=DataQuery(symbols=symbols),
            timestamp=datetime.now(),
            source=self.name,
            success=False
        )
    
    def subscribe(self, symbols: List[str], callback) -> bool:
        """订阅期货实时数据"""
        # TODO: 实现期货WebSocket订阅
        logger.info(f"Subscribed to {len(symbols)} futures symbols")
        return True
    
    def unsubscribe(self, symbols: List[str]) -> bool:
        """取消订阅期货数据"""
        logger.info(f"Unsubscribed from {len(symbols)} futures symbols")
        return True
    
    def get_main_contracts(self, varieties: List[str]) -> Dict[str, str]:
        """
        获取主力合约
        
        Args:
            varieties: 品种列表，如 ['IF', 'IH', 'IC']
            
        Returns:
            品种到主力合约的映射
        """
        result = {}
        
        try:
            # 获取所有期货合约
            df = ak.futures_zh_spot()
            
            for variety in varieties:
                # 筛选该品种的合约
                variety_df = df[df['symbol'].str.startswith(variety)]
                
                if not variety_df.empty:
                    # 按持仓量排序，取最大的作为主力合约
                    main_contract = variety_df.nlargest(1, 'open_interest')['symbol'].iloc[0]
                    result[variety] = main_contract
                    
        except Exception as e:
            logger.error(f"Failed to get main contracts: {e}")
        
        return result
    
    def get_basis_data(self, index_symbol: str, futures_symbol: str) -> pd.DataFrame:
        """
        获取基差数据（期货价格 - 现货价格）
        
        Args:
            index_symbol: 指数代码
            futures_symbol: 期货合约代码
            
        Returns:
            包含基差的DataFrame
        """
        try:
            # 获取指数数据
            from .stock_provider import StockDataProvider
            stock_provider = StockDataProvider()
            stock_provider.initialize()
            
            query = DataQuery(symbols=[index_symbol])
            index_response = stock_provider.get_data(query, DataType.INDEX_DAILY)
            index_df = index_response.data
            
            # 获取期货数据
            query = DataQuery(symbols=[futures_symbol])
            futures_response = self.get_data(query, DataType.FUTURES_DAILY)
            futures_df = futures_response.data
            
            # 合并数据计算基差
            if not index_df.empty and not futures_df.empty:
                merged = pd.merge(
                    index_df[['date', 'close']],
                    futures_df[['date', 'close']],
                    on='date',
                    suffixes=('_index', '_futures')
                )
                
                merged['basis'] = merged['close_futures'] - merged['close_index']
                merged['basis_rate'] = (merged['basis'] / merged['close_index']) * 100
                
                return merged
                
        except Exception as e:
            logger.error(f"Failed to calculate basis: {e}")
        
        return pd.DataFrame()
