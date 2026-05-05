"""
SQLAlchemy ORM模型
映射astock_init.sql中的表结构
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Enum, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()


class SymbolType(enum.Enum):
    """标的类型枚举"""
    STOCK = 'stock'
    FUTURE = 'future'
    ETF = 'etf'
    INDEX = 'index'


class SymbolInfo(Base):
    """标的信息表"""
    __tablename__ = 'symbol_info'
    
    symbol = Column(String(20), primary_key=True, comment='标的代码')
    name = Column(String(50), nullable=False, comment='标的名称')
    symbol_type = Column(Enum(SymbolType), nullable=False, comment='标的类型')
    exchange = Column(String(10), comment='交易所')
    list_date = Column(Date, comment='上市日期')
    delist_date = Column(Date, comment='退市日期')
    status = Column(String(10), default='active', comment='状态: active/delisted')
    created_at = Column(DateTime, default=lambda: datetime.now(), comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now(), comment='更新时间')


class DailyBar(Base):
    """日线数据表（按年分区）"""
    __tablename__ = 'daily_bar'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), ForeignKey('symbol_info.symbol'), nullable=False, comment='标的代码')
    trade_date = Column(Date, nullable=False, comment='交易日期')
    open = Column(Float, comment='开盘价')
    high = Column(Float, comment='最高价')
    low = Column(Float, comment='最低价')
    close = Column(Float, comment='收盘价')
    pre_close = Column(Float, comment='前收盘价')
    volume = Column(Float, comment='成交量')
    turnover = Column(Float, comment='成交额')
    change_pct = Column(Float, comment='涨跌幅%')
    change_amt = Column(Float, comment='涨跌额')
    amplitude = Column(Float, comment='振幅%')
    turnover_rate = Column(Float, comment='换手率%')
    pe_ratio = Column(Float, comment='市盈率')
    pb_ratio = Column(Float, comment='市净率')
    market_cap = Column(Float, comment='总市值')
    circulating_market_cap = Column(Float, comment='流通市值')
    pre_adjust_factor = Column(Float, comment='前复权因子')
    post_adjust_factor = Column(Float, comment='后复权因子')
    data_source = Column(String(50), default='UNKNOWN', comment='数据源')
    created_at = Column(DateTime, default=lambda: datetime.now(), comment='创建时间')
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now(), comment='更新时间')
    
    __table_args__ = (
        Index('idx_daily_bar_symbol_date', 'symbol', 'trade_date'),
        Index('idx_daily_bar_date', 'trade_date'),
    )


class MinuteBar(Base):
    """分钟线数据表"""
    __tablename__ = 'minute_bar'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), ForeignKey('symbol_info.symbol'), nullable=False, comment='标的代码')
    datetime = Column(DateTime, nullable=False, comment='时间')
    frequency = Column(Integer, nullable=False, comment='频率: 1/5/15/30/60分钟')
    open = Column(Float, comment='开盘价')
    high = Column(Float, comment='最高价')
    low = Column(Float, comment='最低价')
    close = Column(Float, comment='收盘价')
    volume = Column(Float, comment='成交量')
    turnover = Column(Float, comment='成交额')
    created_at = Column(DateTime, default=lambda: datetime.now(), comment='创建时间')
    
    __table_args__ = (
        Index('idx_minute_bar_symbol_datetime', 'symbol', 'datetime'),
        Index('idx_minute_bar_datetime', 'datetime'),
    )


class TickData(Base):
    """Tick数据表"""
    __tablename__ = 'tick_data'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), ForeignKey('symbol_info.symbol'), nullable=False, comment='标的代码')
    datetime = Column(DateTime, nullable=False, comment='时间(精确到毫秒)')
    last_price = Column(Float, comment='最新价')
    volume = Column(Float, comment='成交量')
    turnover = Column(Float, comment='成交额')
    bid_price = Column(Float, comment='买一价')
    bid_volume = Column(Float, comment='买一量')
    ask_price = Column(Float, comment='卖一价')
    ask_volume = Column(Float, comment='卖一量')
    created_at = Column(DateTime, default=lambda: datetime.now(), comment='创建时间')
    
    __table_args__ = (
        Index('idx_tick_data_symbol_datetime', 'symbol', 'datetime'),
    )
