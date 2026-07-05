"""
数据库会话管理
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
from typing import Generator
import os

from .models import Base

# 数据库配置
DATABASE_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'database': os.getenv('DB_NAME', 'astock_quant'),
    'username': os.getenv('DB_USER', 'astock'),
    'password': os.getenv('DB_PASSWORD', 'astock123'),
}

# 连接池配置
POOL_CONFIG = {
    'poolclass': QueuePool,
    'pool_size': 10,  # 连接池大小
    'max_overflow': 20,  # 超过pool_size后最多创建的连接数
    'pool_timeout': 30,  # 获取连接超时时间
    'pool_recycle': 3600,  # 连接回收时间(秒)
    'pool_pre_ping': True,  # 连接前检查有效性
}

# 全局引擎和会话工厂
_engine = None
_SessionFactory = None


def init_database(echo: bool = False) -> None:
    """
    初始化数据库连接
    
    Args:
        echo: 是否打印SQL语句
    """
    global _engine, _SessionFactory
    
    if _engine is not None:
        return
    
    # 构建连接URL
    url = (
        f"postgresql://{DATABASE_CONFIG['username']}:{DATABASE_CONFIG['password']}"
        f"@{DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}"
        f"/{DATABASE_CONFIG['database']}"
    )
    
    # 创建引擎
    _engine = create_engine(url, echo=echo, **POOL_CONFIG)
    
    # 创建会话工厂
    _SessionFactory = sessionmaker(bind=_engine)
    
    # 创建所有表（如果不存在）
    Base.metadata.create_all(_engine)


def get_session() -> Session:
    """
    获取数据库会话
    
    Returns:
        Session对象
    """
    if _SessionFactory is None:
        init_database()
    
    return _SessionFactory()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    提供会话上下文管理器，自动处理提交和回滚
    
    Usage:
        with session_scope() as session:
            session.add(obj)
            # 自动提交
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def close_database():
    """关闭数据库连接"""
    global _engine, _SessionFactory
    
    if _engine is not None:
        _engine.dispose()
        _engine = None
        _SessionFactory = None
