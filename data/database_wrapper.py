"""
C++数据库层的Python封装

提供Pythonic的接口，内部调用C++实现
"""

import os
from typing import List, Optional, Tuple
from datetime import datetime, date
from dataclasses import dataclass

try:
    from . import database_native as _native
except ImportError:
    _native = None
    print("Warning: C++ database_native module not available, database features disabled")


@dataclass
class DatabaseConfig:
    """数据库配置"""
    host: str = "localhost"
    port: int = 3306
    database: str = "astock_quant"
    username: str = "root"
    password: str = ""
    charset: str = "utf8mb4"
    pool_size: int = 10
    max_overflow: int = 20
    
    def to_native(self) -> '_native.DatabaseConfig':
        """转换为C++配置对象"""
        config = _native.DatabaseConfig()
        config.host = self.host
        config.port = self.port
        config.database = self.database
        config.username = self.username
        config.password = self.password
        config.charset = self.charset
        config.pool_size = self.pool_size
        config.max_overflow = self.max_overflow
        return config


class Database:
    """
    C++数据库访问的Python接口
    
    使用示例:
        # 初始化
        config = DatabaseConfig(
            host='localhost',
            database='astock_quant',
            username='root',
            password='your_password'
        )
        db = Database(config)
        db.initialize()
        
        # 保存标的信息
        db.save_symbol('600000.SH', '浦发银行', 'stock', 'SSE')
        
        # 获取标的
        symbol_info = db.get_symbol('600000.SH')
        
        # 保存日线数据
        bars = [
            {'symbol': '600000.SH', 'trade_date': '2024-01-01', 
             'open': 10.0, 'high': 10.5, 'low': 9.8, 'close': 10.2,
             'volume': 1000000, 'turnover': 10000000}
        ]
        db.save_daily_bars(bars)
        
        # 查询日线
        bars = db.get_daily_bars('600000.SH', '2024-01-01', '2024-01-31')
        
        # 关闭
        db.shutdown()
    """
    
    def __init__(self, config: DatabaseConfig):
        if _native is None:
            raise RuntimeError("C++ database module not available")
        
        self.config = config
        self._pool = _native.ConnectionPool(config.to_native())
        self._repo = _native.MarketDataRepository(self._pool)
        self._initialized = False
    
    def initialize(self) -> bool:
        """初始化数据库连接池"""
        if self._initialized:
            return True
        self._initialized = self._pool.initialize()
        return self._initialized
    
    def shutdown(self):
        """关闭数据库连接池"""
        if self._initialized:
            self._pool.shutdown()
            self._initialized = False
    
    def get_stats(self) -> dict:
        """获取连接池统计信息"""
        stats = self._pool.get_stats()
        return {
            'total_connections': stats.total_connections,
            'active_connections': stats.active_connections,
            'idle_connections': stats.idle_connections,
            'failed_acquisitions': stats.failed_acquisitions,
            'total_acquisitions': stats.total_acquisitions
        }
    
    # ========== Symbol Info 操作 ==========
    
    def save_symbol(self, symbol: str, name: str, symbol_type: str, 
                   exchange: str = '', list_date: Optional[date] = None) -> bool:
        """
        保存标的信息
        
        Args:
            symbol: 标的代码
            name: 标的名称
            symbol_type: 类型 (stock/future/etf/index)
            exchange: 交易所
            list_date: 上市日期
        """
        info = _native.SymbolInfo()
        info.symbol = symbol
        info.name = name
        info.symbol_type = self._parse_symbol_type(symbol_type)
        info.exchange = exchange
        
        if list_date:
            info.list_date = int(datetime.combine(list_date, datetime.min.time()).timestamp())
        
        return self._repo.save_symbol(info)
    
    def get_symbol(self, symbol: str) -> Optional[dict]:
        """获取标的信息"""
        result = self._repo.get_symbol(symbol)
        if not result:
            return None
        
        info = result  # result已经是SymbolInfo对象
        return {
            'symbol': info.symbol,
            'name': info.name,
            'symbol_type': self._symbol_type_to_str(info.symbol_type),
            'exchange': info.exchange,
            'list_date': datetime.fromtimestamp(info.list_date).date() if info.list_date else None,
            'status': info.status
        }
    
    def get_all_symbols(self, symbol_type: Optional[str] = None, 
                       status: str = 'active') -> List[dict]:
        """获取所有标的"""
        type_filter = self._parse_symbol_type(symbol_type) if symbol_type else None
        results = self._repo.get_all_symbols(type_filter, status)
        
        return [
            {
                'symbol': info.symbol,
                'name': info.name,
                'symbol_type': self._symbol_type_to_str(info.symbol_type),
                'exchange': info.exchange,
                'status': info.status
            }
            for info in results
        ]
    
    # ========== Daily Bar 操作 ==========
    
    def save_daily_bars(self, bars: List[dict]) -> int:
        """
        批量保存日线数据
        
        Args:
            bars: 日线数据列表，每个dict包含:
                  symbol, trade_date, open, high, low, close, volume等
        
        Returns:
            保存的记录数
        """
        native_bars = []
        for bar_dict in bars:
            bar = _native.DailyBar()
            bar.symbol = bar_dict['symbol']
            bar.trade_date = self._parse_date(bar_dict['trade_date'])
            bar.open = float(bar_dict.get('open', 0))
            bar.high = float(bar_dict.get('high', 0))
            bar.low = float(bar_dict.get('low', 0))
            bar.close = float(bar_dict.get('close', 0))
            bar.pre_close = float(bar_dict.get('pre_close', 0))
            bar.volume = float(bar_dict.get('volume', 0))
            bar.turnover = float(bar_dict.get('turnover', 0))
            bar.change_pct = float(bar_dict.get('change_pct', 0))
            bar.amplitude = float(bar_dict.get('amplitude', 0))
            bar.turnover_rate = float(bar_dict.get('turnover_rate', 0))
            bar.pe_ratio = float(bar_dict.get('pe_ratio', 0))
            bar.pb_ratio = float(bar_dict.get('pb_ratio', 0))
            bar.market_cap = float(bar_dict.get('market_cap', 0))
            native_bars.append(bar)
        
        return self._repo.save_daily_bars(native_bars)
    
    def get_daily_bars(self, symbol: str, start_date: str, end_date: str) -> List[dict]:
        """获取日线数据"""
        start_ts = self._parse_date(start_date)
        end_ts = self._parse_date(end_date)
        
        bars = self._repo.get_daily_bars(symbol, start_ts, end_ts)
        
        return [
            {
                'symbol': bar.symbol,
                'trade_date': datetime.fromtimestamp(bar.trade_date).strftime('%Y-%m-%d'),
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
            }
            for bar in bars
        ]
    
    def get_latest_bar(self, symbol: str) -> Optional[dict]:
        """获取最新日线"""
        result = self._repo.get_latest_bar(symbol)
        if not result:
            return None
        
        bar = result
        return {
            'symbol': bar.symbol,
            'trade_date': datetime.fromtimestamp(bar.trade_date).strftime('%Y-%m-%d'),
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'volume': bar.volume
        }
    
    # ========== Transaction 操作 ==========
    
    def begin_transaction(self) -> bool:
        """开始事务"""
        return self._repo.begin_transaction()
    
    def commit(self) -> bool:
        """提交事务"""
        return self._repo.commit()
    
    def rollback(self) -> bool:
        """回滚事务"""
        return self._repo.rollback()
    
    # ========== 辅助方法 ==========
    
    @staticmethod
    def _parse_symbol_type(symbol_type: str) -> '_native.SymbolType':
        """解析标的类型字符串"""
        type_map = {
            'stock': _native.SymbolType.STOCK,
            'future': _native.SymbolType.FUTURE,
            'etf': _native.SymbolType.ETF,
            'index': _native.SymbolType.INDEX
        }
        return type_map.get(symbol_type.lower(), _native.SymbolType.STOCK)
    
    @staticmethod
    def _symbol_type_to_str(symbol_type: '_native.SymbolType') -> str:
        """SymbolType枚举转字符串"""
        return _native.symbol_type_to_string(symbol_type)
    
    @staticmethod
    def _parse_date(date_str: str) -> int:
        """解析日期字符串为时间戳"""
        if isinstance(date_str, int):
            return date_str
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return int(dt.timestamp())
    
    def __enter__(self):
        """上下文管理器入口"""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.shutdown()
        return False


# 全局数据库实例（单例模式）
_global_db: Optional[Database] = None


def get_database() -> Database:
    """获取全局数据库实例"""
    global _global_db
    if _global_db is None:
        # 从环境变量读取配置
        config = DatabaseConfig(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', '3306')),
            database=os.getenv('DB_NAME', 'astock_quant'),
            username=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
        )
        _global_db = Database(config)
        _global_db.initialize()
    return _global_db


def close_database():
    """关闭全局数据库实例"""
    global _global_db
    if _global_db:
        _global_db.shutdown()
        _global_db = None
