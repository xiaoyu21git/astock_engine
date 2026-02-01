#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
离线数据模拟器 - 基于真实市场特征生成测试数据
用于网络不稳定时测试策略
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class MockDataGenerator:
    """模拟数据生成器"""
    
    # 真实股票的市场特征（从历史数据统计）
    STOCK_PROFILES = {
        '300750.SZ': {  # 宁德时代
            'name': '宁德时代',
            'base_price': 150.0,
            'volatility': 0.35,        # 年化波动率35%
            'trend': 0.15,             # 年化趋势15%
            'oscillation': 0.65,       # 震荡特征
            'mean_reversion': 0.12,    # 均值回归强度
            'volume_base': 50000000,   # 日均成交量5000万股
        },
        '600036.SH': {  # 招商银行
            'name': '招商银行',
            'base_price': 35.0,
            'volatility': 0.22,
            'trend': 0.05,
            'oscillation': 0.75,
            'mean_reversion': 0.15,
            'volume_base': 80000000,
        },
        '000568.SZ': {  # 泸州老窖
            'name': '泸州老窖',
            'base_price': 180.0,
            'volatility': 0.28,
            'trend': 0.08,
            'oscillation': 0.70,
            'mean_reversion': 0.10,
            'volume_base': 30000000,
        },
        '000333.SZ': {  # 美的集团
            'name': '美的集团',
            'base_price': 60.0,
            'volatility': 0.20,
            'trend': 0.25,             # 强趋势
            'oscillation': 0.15,       # 弱震荡
            'mean_reversion': 0.03,
            'volume_base': 40000000,
        },
        '600519.SH': {  # 贵州茅台
            'name': '贵州茅台',
            'base_price': 1600.0,
            'volatility': 0.25,
            'trend': 0.20,
            'oscillation': 0.25,
            'mean_reversion': 0.05,
            'volume_base': 5000000,
        },
        '002594.SZ': {  # 比亚迪
            'name': '比亚迪',
            'base_price': 220.0,
            'volatility': 0.40,
            'trend': 0.10,
            'oscillation': 0.60,
            'mean_reversion': 0.11,
            'volume_base': 60000000,
        },
    }
    
    def __init__(self, seed: int = 42):
        """
        初始化生成器
        
        Args:
            seed: 随机种子（保证可重复性）
        """
        self.seed = seed
        np.random.seed(seed)
    
    def generate_price_series(self, profile: Dict, days: int) -> pd.DataFrame:
        """
        生成价格序列
        
        使用几何布朗运动 + 均值回归 + 周期性模式
        """
        base_price = profile['base_price']
        volatility = profile['volatility']
        trend = profile['trend']
        oscillation = profile['oscillation']
        mean_reversion = profile['mean_reversion']
        
        # 每日参数
        daily_vol = volatility / np.sqrt(252)
        daily_trend = trend / 252
        
        prices = [base_price]
        
        for i in range(days):
            current_price = prices[-1]
            
            # 1. 趋势项
            trend_component = daily_trend * current_price
            
            # 2. 随机波动项
            random_shock = np.random.normal(0, daily_vol * current_price)
            
            # 3. 均值回归项
            deviation = (current_price - base_price) / base_price
            reversion = -mean_reversion * deviation * current_price
            
            # 4. 周期性项（模拟市场周期）
            cycle_period = 20  # 20天周期
            cycle_component = oscillation * 0.005 * current_price * np.sin(2 * np.pi * i / cycle_period)
            
            # 合成新价格
            new_price = current_price + trend_component + random_shock + reversion + cycle_component
            
            # 确保价格为正
            new_price = max(new_price, current_price * 0.90)  # 单日最大跌幅10%
            new_price = min(new_price, current_price * 1.10)  # 单日最大涨幅10%
            
            prices.append(new_price)
        
        return prices[1:]  # 去掉初始价格
    
    def generate_volume_series(self, profile: Dict, prices: List[float], days: int) -> List[float]:
        """
        生成成交量序列（量价相关）
        """
        volume_base = profile['volume_base']
        
        volumes = []
        prev_price = prices[0]
        
        for i in range(days):
            current_price = prices[i]
            
            # 1. 基础量能（随机波动）
            base_vol = volume_base * np.random.lognormal(0, 0.3)
            
            # 2. 价格变动放大量能
            price_change = abs(current_price - prev_price) / prev_price
            volume_multiplier = 1 + price_change * 5  # 涨跌5%会放量1.25倍
            
            # 3. 随机放量/缩量事件
            if np.random.random() < 0.05:  # 5%概率出现放量
                volume_multiplier *= np.random.uniform(2.0, 3.5)
            
            volume = base_vol * volume_multiplier
            volumes.append(int(volume))
            
            prev_price = current_price
        
        return volumes
    
    def generate_ohlc(self, close_prices: List[float]) -> Dict[str, List[float]]:
        """
        根据收盘价生成OHLC
        """
        opens = []
        highs = []
        lows = []
        
        for i, close in enumerate(close_prices):
            # 开盘价：围绕前收盘价
            if i == 0:
                open_price = close * np.random.uniform(0.99, 1.01)
            else:
                open_price = close_prices[i-1] * np.random.uniform(0.995, 1.005)
            
            # 日内波动
            intraday_range = close * np.random.uniform(0.01, 0.03)  # 1-3%
            
            # 高低价
            high = max(open_price, close) + abs(np.random.normal(0, intraday_range * 0.5))
            low = min(open_price, close) - abs(np.random.normal(0, intraday_range * 0.5))
            
            opens.append(open_price)
            highs.append(high)
            lows.append(low)
        
        return {
            'open': opens,
            'high': highs,
            'low': lows,
            'close': close_prices
        }
    
    def generate_stock_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        生成单只股票日线数据
        
        Args:
            symbol: 股票代码
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            
        Returns:
            DataFrame with OHLCV data
        """
        if symbol not in self.STOCK_PROFILES:
            logger.warning(f"未定义股票特征: {symbol}，使用默认配置")
            profile = {
                'name': symbol,
                'base_price': 50.0,
                'volatility': 0.25,
                'trend': 0.10,
                'oscillation': 0.50,
                'mean_reversion': 0.08,
                'volume_base': 20000000,
            }
        else:
            profile = self.STOCK_PROFILES[symbol]
        
        # 计算天数
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        days = (end - start).days
        
        # 生成交易日（排除周末）
        dates = []
        current = start
        while current <= end:
            if current.weekday() < 5:  # 周一到周五
                dates.append(current)
            current += timedelta(days=1)
        
        actual_days = len(dates)
        
        # 生成价格序列
        close_prices = self.generate_price_series(profile, actual_days)
        
        # 生成OHLC
        ohlc = self.generate_ohlc(close_prices)
        
        # 生成成交量
        volumes = self.generate_volume_series(profile, close_prices, actual_days)
        
        # 组装日线 DataFrame
        df = pd.DataFrame({
            'date': dates,
            'open': ohlc['open'],
            'high': ohlc['high'],
            'low': ohlc['low'],
            'close': close_prices,
            'volume': volumes,
            'symbol': symbol
        })
        
        df.set_index('date', inplace=True)
        
        logger.info(f"生成模拟数据: {symbol} ({profile['name']}), {len(df)}条")
        
        return df

    def generate_intraday_stock_data(self, symbol: str, start_date: str,
                                     end_date: str,
                                     freq: str = '1min') -> pd.DataFrame:
        """生成单只股票的分钟级模拟数据。

        设计目标：
        - 先基于日线轮廓生成每日收盘价和总量；
        - 在每个交易日内按分钟切分，围绕日线收盘价做轻微扰动；
        - 保证列结构与日线一致：open/high/low/close/volume/symbol，索引为精确到分钟的 DatetimeIndex。
        """
        # 先生成日线数据作为轮廓
        daily_df = self.generate_stock_data(symbol, start_date, end_date)
        if daily_df.empty:
            return daily_df

        # 定义 A 股交易时间段（简化：不切午休，连续 9:30-15:00）
        import pandas as _pd
        intraday_rows = []

        for day, row in daily_df.iterrows():
            # day 是 datetime.date 或 datetime，统一为日期
            day_dt = _pd.to_datetime(day).normalize()
            intraday_index = _pd.date_range(
                day_dt + _pd.Timedelta(hours=9, minutes=30),
                day_dt + _pd.Timedelta(hours=15, minutes=0),
                freq=freq,
            )

            if len(intraday_index) == 0:
                continue

            close_price = float(row['close'])
            daily_vol = float(row['volume']) if 'volume' in row else 0.0

            # 按分钟切分成交量，带一点随机扰动
            base_vol_per_bar = daily_vol / len(intraday_index) if daily_vol > 0 else 0.0

            for ts in intraday_index:
                # 围绕日收盘价做轻微扰动（约 0.2% 波动）
                noise = np.random.normal(0, close_price * 0.002)
                price = max(close_price * 0.9, min(close_price * 1.1, close_price + noise))

                vol_noise = np.random.lognormal(mean=0, sigma=0.3) if base_vol_per_bar > 0 else 0.0
                volume = int(base_vol_per_bar * vol_noise) if base_vol_per_bar > 0 else 0

                intraday_rows.append({
                    'datetime': ts,
                    'open': price,
                    'high': price,
                    'low': price,
                    'close': price,
                    'volume': volume,
                    'symbol': symbol,
                })

        if not intraday_rows:
            return pd.DataFrame()

        intraday_df = pd.DataFrame(intraday_rows)
        intraday_df.set_index('datetime', inplace=True)

        return intraday_df


class MockDataManager:
    """离线数据管理器（兼容DataManager接口）"""
    
    def __init__(self, seed: int = 42):
        self.generator = MockDataGenerator(seed)
        logger.info("离线数据管理器初始化（模拟模式）")
    
    def get_stock_data(self, symbols: List[str], 
                       start_date: str,
                       end_date: str,
                       frequency: str = 'daily') -> Dict[str, pd.DataFrame]:
        """
        获取股票数据（模拟）
        
        Args:
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            frequency: 频率，'daily'（默认）或 '1min' 等分钟级
            
        Returns:
            {symbol: DataFrame}
        """
        data = {}
        
        freq_norm = (frequency or 'daily').lower()

        for symbol in symbols:
            try:
                if freq_norm in ('daily', 'd'):
                    df = self.generator.generate_stock_data(symbol, start_date, end_date)
                else:
                    # 目前主要支持分钟级，例如 '1min', '5min'，统一走分钟生成逻辑
                    df = self.generator.generate_intraday_stock_data(symbol, start_date, end_date, freq=freq_norm)

                data[symbol] = df
            except Exception as e:
                logger.error(f"生成数据失败 {symbol}: {e}")
        
        logger.info(f"生成完成: {len(data)}只股票")
        
        return data


if __name__ == '__main__':
    # 测试模拟数据
    print("=" * 70)
    print("       离线数据模拟器测试")
    print("=" * 70)
    print()
    
    manager = MockDataManager(seed=42)
    
    symbols = ['300750.SZ', '600036.SH', '000568.SZ']
    data = manager.get_stock_data(
        symbols=symbols,
        start_date='2024-02-01',
        end_date='2026-01-31'
    )
    
    print(f"\n生成了 {len(data)} 只股票的数据\n")
    
    for symbol, df in data.items():
        profile = MockDataGenerator.STOCK_PROFILES.get(symbol, {})
        name = profile.get('name', symbol)
        
        print(f"【{name}】{symbol}")
        print(f"   数据量：{len(df)}条")
        print(f"   价格范围：{df['close'].min():.2f} - {df['close'].max():.2f}")
        print(f"   平均成交量：{df['volume'].mean()/10000:.0f}万股")
        print(f"   总收益：{(df['close'].iloc[-1]/df['close'].iloc[0]-1)*100:+.2f}%")
        print(f"   波动率：{df['close'].pct_change().std()*np.sqrt(252)*100:.1f}%")
        print()
