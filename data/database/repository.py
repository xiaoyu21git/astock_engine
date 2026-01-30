"""
数据仓储（Repository模式）
提供统一的数据访问接口
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, date
import pandas as pd

from .models import SymbolInfo, DailyBar, MinuteBar, TickData, SymbolType
from .session import session_scope


class DatabaseRepository:
    """数据库仓储类"""
    
    # ============ Symbol Info 操作 ============
    
    @staticmethod
    def save_symbol(symbol: str, name: str, symbol_type: SymbolType, 
                   exchange: str = None, list_date: date = None) -> SymbolInfo:
        """保存或更新标的信息"""
        with session_scope() as session:
            # 查找已存在的记录
            symbol_info = session.query(SymbolInfo).filter(
                SymbolInfo.symbol == symbol
            ).first()
            
            if symbol_info:
                # 更新
                symbol_info.name = name
                symbol_info.symbol_type = symbol_type
                symbol_info.exchange = exchange
                symbol_info.list_date = list_date
                symbol_info.updated_at = datetime.now()
            else:
                # 新增
                symbol_info = SymbolInfo(
                    symbol=symbol,
                    name=name,
                    symbol_type=symbol_type,
                    exchange=exchange,
                    list_date=list_date
                )
                session.add(symbol_info)
            
            return symbol_info
    
    @staticmethod
    def get_symbol(symbol: str) -> Optional[SymbolInfo]:
        """获取标的信息"""
        with session_scope() as session:
            return session.query(SymbolInfo).filter(
                SymbolInfo.symbol == symbol
            ).first()
    
    @staticmethod
    def get_all_symbols(symbol_type: SymbolType = None, 
                       status: str = 'active') -> List[SymbolInfo]:
        """获取所有标的"""
        with session_scope() as session:
            query = session.query(SymbolInfo).filter(
                SymbolInfo.status == status
            )
            
            if symbol_type:
                query = query.filter(SymbolInfo.symbol_type == symbol_type)
            
            return query.all()
    
    # ============ Daily Bar 操作 ============
    
    @staticmethod
    def save_daily_bars(df: pd.DataFrame) -> int:
        """
        批量保存日线数据
        
        Args:
            df: DataFrame with columns [symbol, trade_date, open, high, low, close, 
                                       volume, turnover, change_pct, etc.]
        
        Returns:
            保存的记录数
        """
        if df.empty:
            return 0
        
        with session_scope() as session:
            records = []
            for _, row in df.iterrows():
                # 检查是否已存在
                existing = session.query(DailyBar).filter(
                    and_(
                        DailyBar.symbol == row['symbol'],
                        DailyBar.trade_date == row['trade_date']
                    )
                ).first()
                
                if existing:
                    # 更新现有记录
                    for col in df.columns:
                        if col not in ['symbol', 'trade_date', 'id', 'created_at']:
                            setattr(existing, col, row.get(col))
                else:
                    # 创建新记录
                    record = DailyBar(
                        symbol=row['symbol'],
                        trade_date=row['trade_date'],
                        open=row.get('open'),
                        high=row.get('high'),
                        low=row.get('low'),
                        close=row.get('close'),
                        pre_close=row.get('pre_close'),
                        volume=row.get('volume'),
                        turnover=row.get('turnover'),
                        change_pct=row.get('change_pct'),
                        amplitude=row.get('amplitude'),
                        turnover_rate=row.get('turnover_rate'),
                        pe_ratio=row.get('pe_ratio'),
                        pb_ratio=row.get('pb_ratio'),
                        market_cap=row.get('market_cap')
                    )
                    records.append(record)
            
            if records:
                session.bulk_save_objects(records)
            
            return len(records)
    
    @staticmethod
    def get_daily_bars(symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        """
        获取日线数据
        
        Returns:
            DataFrame格式的日线数据
        """
        with session_scope() as session:
            query = session.query(DailyBar).filter(
                and_(
                    DailyBar.symbol == symbol,
                    DailyBar.trade_date >= start_date,
                    DailyBar.trade_date <= end_date
                )
            ).order_by(DailyBar.trade_date)
            
            bars = query.all()
            
            if not bars:
                return pd.DataFrame()
            
            # 转换为DataFrame
            data = []
            for bar in bars:
                data.append({
                    'symbol': bar.symbol,
                    'trade_date': bar.trade_date,
                    'open': bar.open,
                    'high': bar.high,
                    'low': bar.low,
                    'close': bar.close,
                    'pre_close': bar.pre_close,
                    'volume': bar.volume,
                    'turnover': bar.turnover,
                    'change_pct': bar.change_pct,
                    'amplitude': bar.amplitude,
                    'turnover_rate': bar.turnover_rate,
                    'pe_ratio': bar.pe_ratio,
                    'pb_ratio': bar.pb_ratio,
                    'market_cap': bar.market_cap
                })
            
            return pd.DataFrame(data)
    
    @staticmethod
    def get_latest_bar(symbol: str) -> Optional[DailyBar]:
        """获取最新日线数据"""
        with session_scope() as session:
            return session.query(DailyBar).filter(
                DailyBar.symbol == symbol
            ).order_by(desc(DailyBar.trade_date)).first()
    
    # ============ Minute Bar 操作 ============
    
    @staticmethod
    def save_minute_bars(df: pd.DataFrame, frequency: int = 1) -> int:
        """
        批量保存分钟线数据
        
        Args:
            df: DataFrame with columns [symbol, datetime, open, high, low, close, volume, turnover]
            frequency: 频率（1/5/15/30/60分钟）
        
        Returns:
            保存的记录数
        """
        if df.empty:
            return 0
        
        with session_scope() as session:
            records = []
            for _, row in df.iterrows():
                # 检查是否已存在
                existing = session.query(MinuteBar).filter(
                    and_(
                        MinuteBar.symbol == row['symbol'],
                        MinuteBar.datetime == row['datetime'],
                        MinuteBar.frequency == frequency
                    )
                ).first()
                
                if not existing:
                    record = MinuteBar(
                        symbol=row['symbol'],
                        datetime=row['datetime'],
                        frequency=frequency,
                        open=row.get('open'),
                        high=row.get('high'),
                        low=row.get('low'),
                        close=row.get('close'),
                        volume=row.get('volume'),
                        turnover=row.get('turnover')
                    )
                    records.append(record)
            
            if records:
                session.bulk_save_objects(records)
            
            return len(records)
    
    @staticmethod
    def get_minute_bars(symbol: str, start_datetime: datetime, 
                       end_datetime: datetime, frequency: int = 1) -> pd.DataFrame:
        """获取分钟线数据"""
        with session_scope() as session:
            query = session.query(MinuteBar).filter(
                and_(
                    MinuteBar.symbol == symbol,
                    MinuteBar.frequency == frequency,
                    MinuteBar.datetime >= start_datetime,
                    MinuteBar.datetime <= end_datetime
                )
            ).order_by(MinuteBar.datetime)
            
            bars = query.all()
            
            if not bars:
                return pd.DataFrame()
            
            data = []
            for bar in bars:
                data.append({
                    'symbol': bar.symbol,
                    'datetime': bar.datetime,
                    'frequency': bar.frequency,
                    'open': bar.open,
                    'high': bar.high,
                    'low': bar.low,
                    'close': bar.close,
                    'volume': bar.volume,
                    'turnover': bar.turnover
                })
            
            return pd.DataFrame(data)
    
    # ============ Tick Data 操作 ============
    
    @staticmethod
    def save_tick_data(df: pd.DataFrame) -> int:
        """批量保存Tick数据"""
        if df.empty:
            return 0
        
        with session_scope() as session:
            records = []
            for _, row in df.iterrows():
                record = TickData(
                    symbol=row['symbol'],
                    datetime=row['datetime'],
                    last_price=row.get('last_price'),
                    volume=row.get('volume'),
                    turnover=row.get('turnover'),
                    bid_price=row.get('bid_price'),
                    bid_volume=row.get('bid_volume'),
                    ask_price=row.get('ask_price'),
                    ask_volume=row.get('ask_volume')
                )
                records.append(record)
            
            session.bulk_save_objects(records)
            return len(records)
    
    @staticmethod
    def get_tick_data(symbol: str, start_datetime: datetime, 
                     end_datetime: datetime) -> pd.DataFrame:
        """获取Tick数据"""
        with session_scope() as session:
            query = session.query(TickData).filter(
                and_(
                    TickData.symbol == symbol,
                    TickData.datetime >= start_datetime,
                    TickData.datetime <= end_datetime
                )
            ).order_by(TickData.datetime)
            
            ticks = query.all()
            
            if not ticks:
                return pd.DataFrame()
            
            data = []
            for tick in ticks:
                data.append({
                    'symbol': tick.symbol,
                    'datetime': tick.datetime,
                    'last_price': tick.last_price,
                    'volume': tick.volume,
                    'turnover': tick.turnover,
                    'bid_price': tick.bid_price,
                    'bid_volume': tick.bid_volume,
                    'ask_price': tick.ask_price,
                    'ask_volume': tick.ask_volume
                })
            
            return pd.DataFrame(data)
