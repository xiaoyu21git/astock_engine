"""
A股数据提供者
使用 akshare 获取A股市场数据
"""

import akshare as ak
import json
import os
import pandas as pd
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime, date, timedelta
import logging
import threading
import time
from .base_provider import (
    BaseDataProvider, DataQuery, DataResponse, DataType
)

logger = logging.getLogger(__name__)


class StockDataProvider(BaseDataProvider):
    """A股数据提供者"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("StockDataProvider", config)
        self.cache: Dict[str, Any] = {}
        # 订阅相关：symbol -> callback
        self.subscribers: Dict[str, Callable[[str, Dict[str, Any], datetime], None]] = {}
        self._subscribe_thread: threading.Thread | None = None
        self._stop_subscribe: bool = False
        # 轮询间隔（秒），可通过 config['subscribe_interval'] 覆盖
        self._subscribe_interval: float = float(self.config.get("subscribe_interval", 2.0))
        
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
        """订阅实时数据

        当前实现为基于轮询的订阅：
        - 周期性调用 get_realtime_data
        - 对每个标的调用回调: callback(symbol, row_dict, timestamp)
        """
        valid_symbols = self.validate_symbols(symbols)
        if not valid_symbols or callback is None:
            return False

        for symbol in valid_symbols:
            self.subscribers[symbol] = callback

        logger.info("Subscribed to %d symbols (polling interval=%.2fs)", len(valid_symbols), self._subscribe_interval)

        # 启动后台轮询线程（若尚未启动）
        if self._subscribe_thread is None or not self._subscribe_thread.is_alive():
            self._stop_subscribe = False
            self._subscribe_thread = threading.Thread(
                target=self._subscribe_loop,
                name="StockDataProviderSubscribeLoop",
                daemon=True,
            )
            self._subscribe_thread.start()

        return True
    
    def unsubscribe(self, symbols: List[str]) -> bool:
        """取消订阅"""
        valid_symbols = self.validate_symbols(symbols)
        for symbol in valid_symbols:
            self.subscribers.pop(symbol, None)

        logger.info("Unsubscribed from %d symbols", len(valid_symbols))

        # 若无任何订阅，停止轮询线程
        if not self.subscribers:
            self._stop_subscribe = True

        return True

    def _subscribe_loop(self) -> None:
        """后台轮询实时行情并触发订阅回调。

        注意：这是一个简易实现，用轮询模拟 WebSocket 推送，
        主要用于开发与测试，生产可替换为真正的流式行情源。
        """
        while not self._stop_subscribe:
            try:
                symbols = list(self.subscribers.keys())
                if not symbols:
                    time.sleep(self._subscribe_interval)
                    continue

                resp = self.get_realtime_data(symbols)
                if not resp.success or resp.data is None or resp.data.empty:
                    time.sleep(self._subscribe_interval)
                    continue

                df = resp.data

                # 将无后缀代码映射回订阅时的标准代码（如 000001 -> 000001.SZ）
                code_to_full: Dict[str, str] = {}
                for full_symbol in symbols:
                    code = full_symbol.split(".")[0]
                    code_to_full[code] = full_symbol

                for _, row in df.iterrows():
                    raw_code = str(row.get("symbol", ""))
                    full_symbol = code_to_full.get(raw_code, raw_code)
                    cb = self.subscribers.get(full_symbol)
                    if cb is None:
                        continue
                    try:
                        cb(full_symbol, row.to_dict(), resp.timestamp)
                    except Exception as exc:  # pragma: no cover - 防御性
                        logger.warning("StockDataProvider callback failed for %s: %s", full_symbol, exc)

            except Exception as exc:  # pragma: no cover - 防御性
                logger.warning("StockDataProvider subscribe loop error: %s", exc)

            time.sleep(self._subscribe_interval)

    def close(self) -> None:
        """关闭数据源并停止订阅线程"""
        self._stop_subscribe = True
        super().close()
    
    def get_stock_list(self) -> pd.DataFrame:
        """获取A股股票列表，支持多数据源（eastmoney/ths/tencent）"""
        # 读取配置文件
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config', 'data_source.json')
        source = 'eastmoney'
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    conf = json.load(f)
                    source = conf.get('stock_list_source', 'eastmoney')
            except Exception as e:
                logger.warning(f"读取数据源配置失败，使用默认eastmoney: {e}")
        try:
            if source == 'eastmoney':
                df = ak.stock_zh_a_spot_em()
                return df[['代码', '名称']].rename(columns={'代码': 'symbol', '名称': 'name'})
            elif source == 'ths':
                df = ak.stock_info_a_code_name_ths()
                return df[['code', 'name']].rename(columns={'code': 'symbol'})
            elif source == 'tencent':
                df = ak.stock_zh_a_spot()
                return df[['代码', '名称']].rename(columns={'代码': 'symbol', '名称': 'name'})
            else:
                logger.error(f"未知股票列表数据源: {source}")
                return pd.DataFrame()
        except Exception as e:
            logger.error(f"Failed to get stock list from {source}: {e}")
            return pd.DataFrame()
