#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
量价关系策略 - Volume-Price Strategy
基于经典量价理论的交易策略

核心理论：
1. 量价齐升 - 上涨确认（买入）
2. 量价背离 - 趋势反转（卖出）
3. 缩量下跌后放量上涨 - 底部反转（买入）
4. 巨量滞涨 - 顶部信号（卖出）
5. 温和放量 - 健康上涨（持有）
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
import logging

from astock_engine.strategies.base_strategy import Signal
from astock_engine.factors.sector_factors import apply_sector_factors
from astock_engine.factors.sentiment_policy_factors import (
    apply_simple_sentiment,
    apply_policy_factor,
)
from astock_engine.factors.auction_factors import apply_auction_factors
from astock_engine.factors.industry_sentiment import get_sector_sentiment_for_symbol

logger = logging.getLogger(__name__)

# 控制板块因子相关异常的日志噪音：
# - 仅在首次失败时告警一次；
# - 之后直接跳过板块因子计算，不再刷屏日志。
_SECTOR_FACTOR_DIM_WARNING_SUPPRESSED = False


class VolumePriceStrategy:
    """量价关系策略"""
    
    def __init__(self, params: Optional[Dict] = None):
        """
        初始化策略
        
        Args:
            params: 策略参数
                - volume_ma_period: 成交量均线周期（默认20）
                - volume_surge_ratio: 放量倍数（默认1.5倍）
                - volume_shrink_ratio: 缩量倍数（默认0.7倍）
                - price_ma_short: 短期均线（默认5）
                - price_ma_long: 长期均线（默认20）
                - obv_signal_period: OBV信号线周期（默认10）
                - min_price_change: 最小价格变动阈值（默认1%）
                - mode: 模式 conservative/balanced/aggressive
        """
        self.name = '量价关系策略'
        self.params = params or {}
        
        # 量能参数
        self.volume_ma_period = self.params.get('volume_ma_period', 20)
        self.volume_surge_ratio = self.params.get('volume_surge_ratio', 1.5)  # 放量1.5倍
        self.volume_shrink_ratio = self.params.get('volume_shrink_ratio', 0.7)  # 缩量0.7倍
        
        # 价格参数
        self.price_ma_short = self.params.get('price_ma_short', 5)
        self.price_ma_long = self.params.get('price_ma_long', 20)
        self.min_price_change = self.params.get('min_price_change', 0.01)  # 1%
        
        # OBV参数
        self.obv_signal_period = self.params.get('obv_signal_period', 10)
        
        # 5分钟周期线参数（用于压力位/支撑位与短期趋势识别）
        # 窗口按5分钟K线根数计，例如12≈1小时，24≈2小时
        self.cycle_5m_window = self.params.get('cycle_5m_window', 12)
        self.cycle_5m_trend_window = self.params.get('cycle_5m_trend_window', 20)
        # 当前价距 5 分钟压力/支撑的相对距离阈值（例如 0.003 ≈ 0.3%）
        self.cycle_5m_near_threshold = self.params.get('cycle_5m_near_threshold', 0.003)

        # 策略模式
        self.mode = self.params.get('mode', 'balanced')
        
        # 根据模式调整参数
        if self.mode == 'conservative':
            self.volume_surge_ratio = 2.0  # 更大的放量才买入
            self.min_price_change = 0.02   # 更大的涨幅要求
        elif self.mode == 'aggressive':
            self.volume_surge_ratio = 1.2  # 较小的放量就买入
            self.min_price_change = 0.005  # 较小的涨幅要求
        
        logger.info(f"量价策略初始化 - 模式:{self.mode}")
    
    def calculate_indicators(self, data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """
        计算技术指标
        
        Args:
            data: 股票数据字典 {symbol: DataFrame}
        
        Returns:
            添加了指标的数据字典
        """
        for symbol, df in data.items():
            # 检查指标是否已存在，避免重复计算
            if f'volume_ma{self.volume_ma_period}' in df.columns:
                continue
            
            # 确保必要列存在
            required_cols = ['close', 'volume', 'open', 'high', 'low']
            if not all(col in df.columns for col in required_cols):
                logger.warning(f"{symbol}: 缺少必要列，跳过指标计算")
                continue
            # 成交量均线
            df[f'volume_ma{self.volume_ma_period}'] = df['volume'].rolling(
                window=self.volume_ma_period
            ).mean()
            
            # 成交量比率
            df['volume_ratio'] = df['volume'] / df[f'volume_ma{self.volume_ma_period}']
            
            # 价格均线
            df[f'ma{self.price_ma_short}'] = df['close'].rolling(
                window=self.price_ma_short
            ).mean()
            df[f'ma{self.price_ma_long}'] = df['close'].rolling(
                window=self.price_ma_long
            ).mean()
            
            # 价格变化
            df['price_change'] = df['close'].pct_change()
            df['price_change_3d'] = df['close'].pct_change(periods=3)
            
            # OBV（能量潮）
            df['obv'] = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
            df['obv_ma'] = df['obv'].rolling(window=self.obv_signal_period).mean()
            df['obv_signal'] = df['obv'] - df['obv_ma']
            
            # VWAP（成交量加权平均价）
            df['vwap'] = (df['close'] * df['volume']).cumsum() / df['volume'].cumsum()
            
            # 价量背离检测
            df['price_trend'] = df['close'].rolling(window=5).apply(
                lambda x: 1 if x.iloc[-1] > x.iloc[0] else -1, raw=False
            )
            df['volume_trend'] = df['volume'].rolling(window=5).apply(
                lambda x: 1 if x.iloc[-1] > x.iloc[0] else -1, raw=False
            )
            df['divergence'] = df['price_trend'] != df['volume_trend']
            
            # 缩量天数统计（连续低于均量）
            df['low_volume_days'] = (df['volume_ratio'] < self.volume_shrink_ratio).astype(int)
            df['consecutive_low_volume'] = df['low_volume_days'].groupby(
                (df['low_volume_days'] != df['low_volume_days'].shift()).cumsum()
            ).cumsum()

            # 若为日内分钟级数据，额外计算 5 分钟周期线相关指标
            # 用于识别短周期压力位/支撑位与反弹趋势
            if isinstance(df.index, pd.DatetimeIndex):
                # 判断是否明显为日内数据（存在非 00:00 的时间部分）
                if ((df.index.hour != 0) | (df.index.minute != 0)).any():
                    data[symbol] = self._calculate_5min_cycle_indicators(df)
        
        # 叠加板块 / 行业 / 题材加权指标
        # 如果板块因子在当前环境下因维度等问题反复报错，会严重干扰日志阅读。
        # 这里采用“失败一次就整体关闭板块因子”的策略：
        # - 首次失败时告警一次；
        # - 之后不再尝试 apply_sector_factors，也不再输出相关告警。
        global _SECTOR_FACTOR_DIM_WARNING_SUPPRESSED
        if not _SECTOR_FACTOR_DIM_WARNING_SUPPRESSED:
            try:
                data = apply_sector_factors(data)
            except Exception as e:
                logger.warning(
                    "计算板块因子失败，将关闭板块加权因子后续计算: %s",
                    e,
                )
                _SECTOR_FACTOR_DIM_WARNING_SUPPRESSED = True

        # 叠加简化市场情绪因子
        try:
            data = apply_simple_sentiment(data)
        except Exception as e:
            logger.warning(f"计算市场情绪因子失败，忽略 sentiment: {e}")

        # 叠加简化政策因子
        try:
            data = apply_policy_factor(data)
        except Exception as e:
            logger.warning(f"计算政策因子失败，忽略 policy_score: {e}")

        # 叠加行业 / 板块舆情因子（基于 NEWS 聚合得到的 sector_sentiment）
        try:
            for symbol, df in data.items():
                if df is None or df.empty:
                    continue
                # 若上游已写入 sector_sentiment，则不重复覆盖
                if "sector_sentiment" in df.columns:
                    continue
                try:
                    val = float(get_sector_sentiment_for_symbol(str(symbol)))
                except Exception:
                    val = 0.0
                df["sector_sentiment"] = float(val)
        except Exception as e:  # pragma: no cover - 防御性
            logger.warning("计算行业舆情因子失败，忽略 sector_sentiment: %s", e)

        # 叠加竞价因子（基于前一日收盘与当日首个 bar 的 open/volume）
        try:
            data = apply_auction_factors(data)
        except Exception as e:
            logger.warning(f"计算竞价因子失败，忽略 auction_*: {e}")
            
        return data

    def _calculate_5min_cycle_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """在分钟级数据上计算 5 分钟周期线相关指标。

        目标：
        - 基于 5 分钟聚合的高低点，构造近期压力位/支撑位；
        - 计算 5 分钟级别的短期趋势；
        - 标注是否处于压力区/支撑区，以及是否出现自支撑位的反弹迹象。
        """
        # 必要列检查
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required_cols):
            return df

        if not isinstance(df.index, pd.DatetimeIndex):
            return df

        # 使用 5 分钟重采样构造更平滑的周期线
        ohlcv = df[required_cols]
        # 在当前 pandas 版本中使用 '5min' 作为 5 分钟频率
        resampled = ohlcv.resample('5min').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
        }).dropna()

        if resampled.empty:
            return df

        win = max(int(self.cycle_5m_window), 1)
        trend_win = max(int(self.cycle_5m_trend_window), 1)

        # 5 分钟滚动高低点 -> 近端压力/支撑
        resampled['cycle_5m_resistance'] = resampled['high'].rolling(window=win).max()
        resampled['cycle_5m_support'] = resampled['low'].rolling(window=win).min()

        # 5 分钟短期趋势（相对均线的偏离度）
        resampled['cycle_5m_ma'] = resampled['close'].rolling(window=trend_win).mean()
        resampled['cycle_5m_trend'] = resampled['close'] / resampled['cycle_5m_ma'] - 1

        cycle_cols = ['cycle_5m_resistance', 'cycle_5m_support', 'cycle_5m_trend']

        # 将 5 分钟周期指标对齐回原始分钟级索引
        aligned = resampled[cycle_cols].reindex(df.index, method='ffill')
        for col in cycle_cols:
            df[col] = aligned[col]

        thr = float(self.cycle_5m_near_threshold)

        # 靠近 5 分钟压力位/支撑位的标记（用于压力/支撑识别）
        df['is_near_5m_resistance'] = (
            df['cycle_5m_resistance'].notna()
            & (df['close'] >= df['cycle_5m_resistance'] * (1 - thr))
            & (df['close'] <= df['cycle_5m_resistance'] * (1 + thr))
        )

        df['is_near_5m_support'] = (
            df['cycle_5m_support'].notna()
            & (df['close'] >= df['cycle_5m_support'] * (1 - thr))
            & (df['close'] <= df['cycle_5m_support'] * (1 + thr))
        )

        # 自 5 分钟支撑位的反弹：
        # - 当前处于支撑区域附近；
        # - 5 分钟趋势向上；
        # - 当前 bar 为上涨 bar
        if 'price_change' in df.columns:
            df['is_rebound_from_5m_support'] = (
                df['is_near_5m_support']
                & (df['cycle_5m_trend'] > 0)
                & (df['price_change'] > 0)
            )
        else:
            df['is_rebound_from_5m_support'] = False

        return df
    
    def generate_signals(self, data: Dict[str, pd.DataFrame], context: Dict = None) -> List[Dict]:
        """
        生成交易信号
        
        Args:
            data: 股票数据（可能是DataFrame或Dict）
            context: 上下文信息（包含当前日期等）
        
        Returns:
            信号列表
        """
        # 处理回测引擎传入的合并DataFrame格式
        if isinstance(data, pd.DataFrame):
            # 转换为字典格式
            if 'symbol' in data.columns:
                symbols = data['symbol'].unique()
                data_dict = {}
                for symbol in symbols:
                    symbol_data = data[data['symbol'] == symbol].copy()
                    # 移除symbol列以便后续处理
                    if 'symbol' in symbol_data.columns:
                        symbol_data = symbol_data.drop('symbol', axis=1)
                    data_dict[symbol] = symbol_data
                data = data_dict
            else:
                # 单个股票数据
                return []
        
        # 先计算指标
        data = self.calculate_indicators(data)
        
        signals = []
        
        # 获取当前日期（用于Signal对象）
        current_date = context.get('date', datetime.now()) if context else datetime.now()
        
        for symbol, df in data.items():
            if len(df) < max(self.volume_ma_period, self.price_ma_long) + 5:
                continue
            
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            recent_5d = df.iloc[-5:]
            recent_10d = df.iloc[-10:]
            
            # 跳过指标不完整的数据
            required_cols = ['volume_ratio', 'price_change', f'ma{self.price_ma_short}']
            if any(pd.isna(latest.get(col)) for col in required_cols):
                continue

            # 5 分钟周期线相关的最新状态（若存在）
            cycle_5m_info = {
                'cycle_5m_resistance': float(latest['cycle_5m_resistance']) if 'cycle_5m_resistance' in latest and pd.notna(latest['cycle_5m_resistance']) else None,
                'cycle_5m_support': float(latest['cycle_5m_support']) if 'cycle_5m_support' in latest and pd.notna(latest['cycle_5m_support']) else None,
                'cycle_5m_trend': float(latest['cycle_5m_trend']) if 'cycle_5m_trend' in latest and pd.notna(latest['cycle_5m_trend']) else None,
                'is_near_5m_resistance': bool(latest['is_near_5m_resistance']) if 'is_near_5m_resistance' in latest and not pd.isna(latest['is_near_5m_resistance']) else False,
                'is_near_5m_support': bool(latest['is_near_5m_support']) if 'is_near_5m_support' in latest and not pd.isna(latest['is_near_5m_support']) else False,
                'is_rebound_from_5m_support': bool(latest['is_rebound_from_5m_support']) if 'is_rebound_from_5m_support' in latest and not pd.isna(latest['is_rebound_from_5m_support']) else False,
            }
            
            # === 买入信号检测 ===
            
            # 信号1: 量价齐升（最经典）
            price_rising = latest['close'] > prev['close'] and latest['price_change'] > self.min_price_change
            volume_surge = latest['volume_ratio'] > self.volume_surge_ratio
            above_ma = latest['close'] > latest[f'ma{self.price_ma_short}']
            
            if price_rising and volume_surge and above_ma:
                strength = min(latest['volume_ratio'] / 2, 1.0)  # 量能越大强度越高
                signals.append(Signal(
                    symbol=symbol,
                    direction=1,  # 买入
                    strength=strength,
                    timestamp=current_date,
                    price=latest['close'],
                    reason=f"量价齐升(放量{latest['volume_ratio']:.1f}倍,涨{latest['price_change']*100:.1f}%)",
                    metadata={
                        'pattern': 'volume_price_surge',
                        'volume_ratio': latest['volume_ratio'],
                        'price_change': latest['price_change'],
                        'obv_signal': latest['obv_signal'],
                        **cycle_5m_info,
                    }
                ))
                continue
            
            # 信号2: 缩量下跌后放量反弹（底部反转）
            recent_low_volume = (recent_5d['consecutive_low_volume'] >= 3).any()
            price_was_falling = (recent_5d['price_change'] < 0).sum() >= 3
            now_surge = latest['volume_ratio'] > self.volume_surge_ratio
            now_rising = latest['price_change'] > self.min_price_change
            
            if recent_low_volume and price_was_falling and now_surge and now_rising:
                strength = 0.8  # 较高强度
                signals.append(Signal(
                    symbol=symbol,
                    direction=1,
                    strength=strength,
                    timestamp=current_date,
                    price=latest['close'],
                    reason=f"缩量下跌后放量反弹(量能{latest['volume_ratio']:.1f}倍)",
                    metadata={
                        'pattern': 'bottom_reversal',
                        'consecutive_low_volume_days': recent_5d['consecutive_low_volume'].max(),
                        'volume_ratio': latest['volume_ratio'],
                        **cycle_5m_info,
                    }
                ))
                continue
            
            # 信号3: OBV金叉（资金流入）
            obv_cross = prev['obv'] <= prev['obv_ma'] and latest['obv'] > latest['obv_ma']
            price_stable = latest['close'] > latest[f'ma{self.price_ma_long}']
            volume_normal = latest['volume_ratio'] > 1.0
            
            if obv_cross and price_stable and volume_normal:
                strength = 0.6
                signals.append(Signal(
                    symbol=symbol,
                    direction=1,
                    strength=strength,
                    timestamp=current_date,
                    price=latest['close'],
                    reason=f"OBV金叉(资金流入,量能{latest['volume_ratio']:.1f}倍)",
                    metadata={
                        'pattern': 'obv_golden_cross',
                        'obv': latest['obv'],
                        'obv_ma': latest['obv_ma'],
                        'volume_ratio': latest['volume_ratio'],
                        **cycle_5m_info,
                    }
                ))
                continue
            
            # 信号4: 突破平台+放量
            price_breakout = latest['close'] > recent_10d['high'].max() * 1.01  # 突破近10日高点
            volume_confirm = latest['volume_ratio'] > 1.5
            
            if price_breakout and volume_confirm:
                strength = 0.9
                signals.append(Signal(
                    symbol=symbol,
                    direction=1,
                    strength=strength,
                    timestamp=current_date,
                    price=latest['close'],
                    reason=f"突破平台+放量(量能{latest['volume_ratio']:.1f}倍)",
                    metadata={
                        'pattern': 'breakout_surge',
                        'breakout_level': recent_10d['high'].max(),
                        'volume_ratio': latest['volume_ratio'],
                        **cycle_5m_info,
                    }
                ))
                continue
            
            # === 卖出信号检测 ===
            
            # 信号5: 巨量滞涨（顶部信号）
            huge_volume = latest['volume_ratio'] > 2.5
            price_stagnant = abs(latest['price_change']) < 0.01  # 涨幅小于1%
            high_position = latest['close'] > latest[f'ma{self.price_ma_long}'] * 1.1  # 价格高位
            
            if huge_volume and price_stagnant and high_position:
                signals.append(Signal(
                    symbol=symbol,
                    direction=-1,  # 卖出
                    strength=1.0,
                    timestamp=current_date,
                    price=latest['close'],
                    reason=f"巨量滞涨(量能{latest['volume_ratio']:.1f}倍,涨幅仅{latest['price_change']*100:.1f}%)",
                    metadata={
                        'pattern': 'volume_stagnation',
                        'volume_ratio': latest['volume_ratio'],
                        'price_change': latest['price_change'],
                        **cycle_5m_info,
                    }
                ))
                continue
            
            # 信号6: 量价背离（价涨量缩）
            price_rising_3d = latest['price_change_3d'] > 0.02  # 3日上涨>2%
            volume_shrinking = recent_5d['volume_ratio'].iloc[-1] < recent_5d['volume_ratio'].iloc[0]
            divergence_detected = latest['divergence'] and latest['price_trend'] == 1
            
            if price_rising_3d and volume_shrinking and divergence_detected:
                signals.append(Signal(
                    symbol=symbol,
                    direction=-1,
                    strength=0.8,
                    timestamp=current_date,
                    price=latest['close'],
                    reason=f"量价背离(价涨{latest['price_change_3d']*100:.1f}%但量缩)",
                    metadata={
                        'pattern': 'price_volume_divergence',
                        'price_change_3d': latest['price_change_3d'],
                        'volume_ratio': latest['volume_ratio'],
                        **cycle_5m_info,
                    }
                ))
                continue
            
            # 信号7: OBV死叉（资金流出）
            obv_death_cross = prev['obv'] >= prev['obv_ma'] and latest['obv'] < latest['obv_ma']
            price_weak = latest['close'] < latest[f'ma{self.price_ma_short}']
            
            if obv_death_cross and price_weak:
                signals.append(Signal(
                    symbol=symbol,
                    direction=-1,
                    strength=0.7,
                    timestamp=current_date,
                    price=latest['close'],
                    reason="OBV死叉(资金流出)",
                    metadata={
                        'pattern': 'obv_death_cross',
                        'obv': latest['obv'],
                        'obv_ma': latest['obv_ma'],
                        **cycle_5m_info,
                    }
                ))
                continue
        
        return signals
    
    def on_bar(self, data: Dict[str, pd.DataFrame]) -> List[Dict]:
        """
        K线数据回调
        
        Args:
            data: 股票数据
        
        Returns:
            交易信号列表
        """
        # 计算指标
        data = self.calculate_indicators(data)
        
        # 生成信号
        signals = self.generate_signals(data)
        
        return signals


# 策略工厂函数
def create_strategy(params: Optional[Dict] = None):
    """创建量价策略实例"""
    return VolumePriceStrategy(params)


# 策略元数据（供插件管理器使用）
STRATEGY_METADATA = {
    'name': 'volume_price_strategy',
    'display_name': '量价关系策略',
    'version': '1.0.0',
    'description': '基于经典量价理论的交易策略，识别量价齐升、量价背离、底部反转等形态',
    'author': 'AStock Quant Team',
    'tags': ['量价', 'OBV', '技术分析'],
    'parameters': {
        'volume_ma_period': {
            'type': 'int',
            'default': 20,
            'range': [5, 60],
            'description': '成交量均线周期'
        },
        'volume_surge_ratio': {
            'type': 'float',
            'default': 1.5,
            'range': [1.2, 3.0],
            'description': '放量倍数'
        },
        'mode': {
            'type': 'str',
            'default': 'balanced',
            'options': ['conservative', 'balanced', 'aggressive'],
            'description': '策略模式'
        }
    }
}
