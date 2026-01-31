"""
数据接入模块
支持从多个数据源获取股票历史数据
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class DataProvider:
    """数据提供者基类"""
    
    def get_daily_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取日线数据
        
        Args:
            symbol: 股票代码
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            
        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        raise NotImplementedError
    
    def get_multiple_stocks(self, symbols: List[str], 
                           start_date: str, 
                           end_date: str) -> Dict[str, pd.DataFrame]:
        """
        批量获取多只股票数据
        
        Args:
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            {symbol: DataFrame}
        """
        data = {}
        
        for symbol in symbols:
            try:
                logger.info(f"获取数据: {symbol}")
                df = self.get_daily_data(symbol, start_date, end_date)
                if not df.empty:
                    data[symbol] = df
                else:
                    logger.warning(f"数据为空: {symbol}")
            except Exception as e:
                logger.error(f"获取数据失败 {symbol}: {e}")
        
        return data


class AkShareProvider(DataProvider):
    """AkShare数据提供者（免费，无需token）"""
    
    def __init__(self):
        try:
            import akshare as ak
            self.ak = ak
            logger.info("AkShare初始化成功")
        except ImportError:
            raise ImportError("请先安装akshare: pip install akshare")
    
    def get_daily_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取日线数据
        
        symbol格式转换：
        - 输入: 600519.SH, 000858.SZ
        - AkShare: 600519, 000858
        """
        # 转换代码格式
        symbol_code = symbol.split('.')[0]
        
        try:
            # 获取A股历史数据
            df = self.ak.stock_zh_a_hist(
                symbol=symbol_code,
                period="daily",
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"  # 前复权
            )
            
            if df.empty:
                logger.warning(f"获取数据为空: {symbol}")
                return pd.DataFrame()
            
            # 标准化列名
            df = df.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '最高': 'high',
                '最低': 'low',
                '收盘': 'close',
                '成交量': 'volume'
            })
            
            # 选择需要的列
            df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
            
            # 设置日期为索引
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            # 添加symbol列
            df['symbol'] = symbol
            
            logger.info(f"获取成功: {symbol}, {len(df)}条数据")
            
            return df
            
        except Exception as e:
            logger.error(f"获取数据失败 {symbol}: {e}")
            return pd.DataFrame()
    
    def search_stock(self, keyword: str) -> pd.DataFrame:
        """搜索股票"""
        try:
            df = self.ak.stock_info_a_code_name()
            result = df[df['name'].str.contains(keyword) | df['code'].str.contains(keyword)]
            return result
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return pd.DataFrame()
    
    def get_index_list(self) -> List[str]:
        """获取常用指数列表"""
        return [
            'sh000001',  # 上证指数
            'sz399001',  # 深证成指
            'sz399006',  # 创业板指
            'sh000300',  # 沪深300
            'sh000016',  # 上证50
            'sz399905',  # 中证500
        ]


class TushareProvider(DataProvider):
    """Tushare数据提供者（需要token）"""
    
    def __init__(self, token: str):
        try:
            import tushare as ts
            ts.set_token(token)
            self.pro = ts.pro_api()
            logger.info("Tushare初始化成功")
        except ImportError:
            raise ImportError("请先安装tushare: pip install tushare")
    
    def get_daily_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取日线数据
        
        symbol格式：600519.SH, 000858.SZ（已是Tushare格式）
        """
        try:
            # Tushare日期格式：YYYYMMDD
            start = start_date.replace('-', '')
            end = end_date.replace('-', '')
            
            df = self.pro.daily(
                ts_code=symbol,
                start_date=start,
                end_date=end
            )
            
            if df.empty:
                return pd.DataFrame()
            
            # 标准化列名
            df = df.rename(columns={
                'trade_date': 'date',
                'vol': 'volume'
            })
            
            # 选择需要的列
            df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
            
            # 设置日期为索引
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            df.sort_index(inplace=True)  # 按日期升序
            
            # 添加symbol列
            df['symbol'] = symbol
            
            logger.info(f"获取成功: {symbol}, {len(df)}条数据")
            
            return df
            
        except Exception as e:
            logger.error(f"获取数据失败 {symbol}: {e}")
            return pd.DataFrame()


class DataManager:
    """数据管理器"""
    
    def __init__(self, provider: DataProvider = None):
        """
        初始化数据管理器
        
        Args:
            provider: 数据提供者，默认使用AkShare
        """
        if provider is None:
            try:
                provider = AkShareProvider()
            except ImportError:
                logger.error("AkShare未安装，请运行: pip install akshare")
                raise
        
        self.provider = provider
        logger.info(f"数据管理器初始化: {type(provider).__name__}")
    
    def get_stock_data(self, symbols: List[str], 
                       start_date: str = None,
                       end_date: str = None,
                       days: int = 365) -> Dict[str, pd.DataFrame]:
        """
        获取股票数据
        
        Args:
            symbols: 股票代码列表 ['600519.SH', '000858.SZ']
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            days: 天数（如果未指定日期）
            
        Returns:
            {symbol: DataFrame}
        """
        # 计算日期范围
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        if start_date is None:
            start = datetime.now() - timedelta(days=days)
            start_date = start.strftime('%Y-%m-%d')
        
        logger.info(f"获取数据: {len(symbols)}只股票, {start_date} 至 {end_date}")
        
        data = self.provider.get_multiple_stocks(symbols, start_date, end_date)
        
        logger.info(f"获取完成: {len(data)}只股票成功")
        
        return data
    
    def get_popular_stocks(self, count: int = 10) -> List[str]:
        """获取热门股票代码"""
        # 常见热门股票
        popular = [
            '600519.SH',  # 贵州茅台
            '000858.SZ',  # 五粮液
            '000001.SZ',  # 平安银行
            '600036.SH',  # 招商银行
            '601318.SH',  # 中国平安
            '000002.SZ',  # 万科A
            '600000.SH',  # 浦发银行
            '601166.SH',  # 兴业银行
            '000333.SZ',  # 美的集团
            '002475.SZ',  # 立讯精密
            '300059.SZ',  # 东方财富
            '600276.SH',  # 恒瑞医药
        ]
        
        return popular[:count]
    
    def validate_data(self, data: Dict[str, pd.DataFrame]) -> bool:
        """验证数据质量"""
        if not data:
            logger.error("数据为空")
            return False
        
        for symbol, df in data.items():
            if df.empty:
                logger.warning(f"数据为空: {symbol}")
                continue
            
            # 检查必需列
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                logger.error(f"{symbol} 缺失列: {missing_cols}")
                return False
            
            # 检查数据完整性
            if df[required_cols].isnull().any().any():
                logger.warning(f"{symbol} 存在空值")
        
        return True
