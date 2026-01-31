"""
KDJ随机指标策略

KDJ指标特点：
- K值：快速指标,对价格变化敏感
- D值：K值的平滑,提供趋势确认
- J值：更敏感的指标,3K-2D,提前预警

交易逻辑:
买入：K线从下方上穿D线(金叉) 且 K值 < 20(超卖)
卖出：K线从上方下穿D线(死叉) 且 K值 > 80(超买)
"""

from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np
import logging

from astock_engine.strategies.base_strategy import BaseStrategy, Signal

logger = logging.getLogger(__name__)


class KDJStrategy(BaseStrategy):
    """KDJ随机指标策略"""
    
    def __init__(self, params: Optional[Dict] = None):
        """
        初始化KDJ策略
        
        Args:
            params: 策略参数
                - n: KDJ周期（默认9）
                - m1: K值平滑周期（默认3）
                - m2: D值平滑周期（默认3）
                - oversold: 超卖阈值（默认20）
                - overbought: 超买阈值（默认80）
                - max_positions: 最大持仓数（默认5）
        """
        super().__init__(params)
        
        # KDJ参数
        self.n = self.params.get('n', 9)  # KDJ周期
        self.m1 = self.params.get('m1', 3)  # K值平滑
        self.m2 = self.params.get('m2', 3)  # D值平滑
        self.oversold = self.params.get('oversold', 20)  # 超卖线
        self.overbought = self.params.get('overbought', 80)  # 超买线
        self.max_positions = self.params.get('max_positions', 5)
        
        # 策略模式: 'swing'=短线波段, 'trend'=趋势跟踪
        self.mode = self.params.get('mode', 'swing')  # 默认短线模式
        
        # 市场环境过滤
        self.market_filter = self.params.get('market_filter', True)  # 是否启用市场环境过滤
        self.market_index = self.params.get('market_index', '000300.SH')  # 大盘指数(沪深300)
        
        # 信号质量过滤阈值
        self.signal_threshold = self.params.get('signal_threshold', 50)  # 最低接受分数(默认过滤D级<50分)
        
        # 压力位配置
        self.resistance_period = self.params.get('resistance_period', 20)  # 计算前N日高点
        self.resistance_buffer = self.params.get('resistance_buffer', 0.02)  # 压力位缓冲2%
        
        # 状态管理
        self.positions = {}  # 持仓股票
        self.last_kdj = {}  # 上一周期的KDJ值
        
        # 历史数据缓存(用于计算技术指标)
        self.history_data = {}  # {symbol: DataFrame}
        self.max_history_len = max(self.n * 3, 50)  # 保留足够的历史数据
        
        logger.info(f"[KDJ策略] 初始化: period={self.n}, K平滑={self.m1}, "
                   f"D平滑={self.m2}, 超卖={self.oversold}, 超买={self.overbought}")
    
    def calculate_kdj(self, data: pd.DataFrame) -> tuple:
        """
        计算KDJ指标
        
        Args:
            data: 包含high, low, close的DataFrame
        
        Returns:
            (K值, D值, J值) 的Series
        """
        # 支持中英文列名
        if 'high' in data.columns:
            high, low, close = data['high'], data['low'], data['close']
        elif '最高' in data.columns:
            high, low, close = data['最高'], data['最低'], data['收盘']
        else:
            raise ValueError(f"数据缺少必需的列,现有列: {list(data.columns)}")
        
        # 计算RSV (Raw Stochastic Value)
        low_n = low.rolling(window=self.n, min_periods=self.n).min()
        high_n = high.rolling(window=self.n, min_periods=self.n).max()
        
        rsv = ((close - low_n) / (high_n - low_n)) * 100
        rsv = rsv.fillna(50)  # 初始值设为50
        
        # 计算K值（使用指数移动平均，相当于加权）
        # K = (2/3) * 前K + (1/3) * RSV
        # 使用EWM实现：alpha = 1/m1
        k = rsv.ewm(alpha=1/self.m1, adjust=False).mean()
        
        # 计算D值
        # D = (2/3) * 前D + (1/3) * K
        d = k.ewm(alpha=1/self.m2, adjust=False).mean()
        
        # 计算J值（更敏感）
        j = 3 * k - 2 * d
        
        return k, d, j
    
    def detect_golden_cross(self, k: pd.Series, d: pd.Series) -> bool:
        """
        检测金叉：K线从下方上穿D线
        
        Args:
            k: K值序列
            d: D值序列
        
        Returns:
            是否发生金叉
        """
        if len(k) < 2 or len(d) < 2:
            return False
        
        # 前一日K < D，当日K >= D
        prev_k, curr_k = k.iloc[-2], k.iloc[-1]
        prev_d, curr_d = d.iloc[-2], d.iloc[-1]
        
        return prev_k < prev_d and curr_k >= curr_d
    
    def detect_death_cross(self, k: pd.Series, d: pd.Series) -> bool:
        """
        检测死叉：K线从上方下穿D线
        
        Args:
            k: K值序列
            d: D值序列
        
        Returns:
            是否发生死叉
        """
        if len(k) < 2 or len(d) < 2:
            return False
        
        # 前一日K > D，当日K <= D
        prev_k, curr_k = k.iloc[-2], k.iloc[-1]
        prev_d, curr_d = d.iloc[-2], d.iloc[-1]
        
        return prev_k > prev_d and curr_k <= curr_d
    
    def calculate_volume_ma(self, data: pd.DataFrame, period: int = 20) -> float:
        """
        计算成交量均值
        
        Args:
            data: 历史数据
            period: 均线周期
            
        Returns:
            成交量均值
        """
        if len(data) < period:
            return 0
        
        # 支持中英文列名
        if 'volume' in data.columns:
            volume = data['volume']
        elif '成交量' in data.columns:
            volume = data['成交量']
        else:
            return 0
        
        return volume.iloc[-period:].mean()
    
    def calculate_ma(self, data: pd.DataFrame, period: int) -> float:
        """
        计算移动平均线
        
        Args:
            data: 历史数据
            period: 均线周期
            
        Returns:
            均线值
        """
        if len(data) < period:
            return 0
        
        # 支持中英文列名
        if 'close' in data.columns:
            close = data['close']
        elif '收盘' in data.columns:
            close = data['收盘']
        else:
            return 0
        
        return close.iloc[-period:].mean()
    
    def check_trend(self, data: pd.DataFrame) -> dict:
        """
        检查趋势状态（均线多空）
        
        Args:
            data: 历史数据
            
        Returns:
            趋势信息字典
        """
        ma20 = self.calculate_ma(data, 20)
        ma60 = self.calculate_ma(data, 60)
        
        if 'close' in data.columns:
            current_price = data['close'].iloc[-1]
        elif '收盘' in data.columns:
            current_price = data['收盘'].iloc[-1]
        else:
            return {'is_bullish': False, 'ma20': 0, 'ma60': 0}
        
        # 多头趋势：价格>MA20（简化条件，提高入场机会）
        is_bullish = current_price > ma20 and ma20 > 0
        # 空头趋势：价格<MA20
        is_bearish = current_price < ma20
        
        return {
            'is_bullish': is_bullish,
            'is_bearish': is_bearish,
            'price': current_price,
            'ma20': ma20,
            'ma60': ma60
        }
    
    def check_market_environment(self, market_data: pd.DataFrame = None) -> dict:
        """
        判断市场环境（牛市/熊市/震荡市）
        
        Args:
            market_data: 大盘指数数据（可选）
            
        Returns:
            市场环境信息
        """
        if not self.market_filter or market_data is None or market_data.empty:
            # 不启用过滤或无数据时，默认允许交易
            return {
                'environment': 'neutral',
                'strength': 0,
                'allow_long': True,
                'position_ratio': 1.0  # 仓位系数
            }
        
        try:
            # 计算大盘均线
            if 'close' in market_data.columns:
                close = market_data['close']
            elif '收盘' in market_data.columns:
                close = market_data['收盘']
            else:
                return {'environment': 'neutral', 'strength': 0, 'allow_long': True, 'position_ratio': 1.0}
            
            if len(close) < 60:
                return {'environment': 'neutral', 'strength': 0, 'allow_long': True, 'position_ratio': 1.0}
            
            ma20 = close.iloc[-20:].mean()
            ma60 = close.iloc[-60:].mean()
            current_price = close.iloc[-1]
            
            # 判断市场环境
            # 牛市：价格>MA20>MA60，且MA20向上
            ma20_slope = (close.iloc[-20:].mean() - close.iloc[-40:-20].mean()) / close.iloc[-40:-20].mean()
            
            if current_price > ma20 > ma60 and ma20_slope > 0.02:  # MA20上涨>2%
                return {
                    'environment': 'bull',  # 牛市
                    'strength': min(ma20_slope * 50, 1.0),
                    'allow_long': True,
                    'position_ratio': 1.2  # 牛市可加仓
                }
            # 熊市：价格<MA20<MA60，且MA20向下
            elif current_price < ma20 < ma60 and ma20_slope < -0.02:  # MA20下跌>2%
                return {
                    'environment': 'bear',  # 熊市
                    'strength': min(abs(ma20_slope) * 50, 1.0),
                    'allow_long': False,  # 熊市不开多仓
                    'position_ratio': 0.5  # 熊市减仓
                }
            else:
                # 震荡市
                return {
                    'environment': 'sideways',
                    'strength': 0.5,
                    'allow_long': True,
                    'position_ratio': 0.8  # 震荡市减仓20%
                }
        except Exception as e:
            logger.warning(f"[KDJ策略] 市场环境判断失败: {e}")
            return {'environment': 'neutral', 'strength': 0, 'allow_long': True, 'position_ratio': 1.0}
    
    def calculate_resistance_support(self, data: pd.DataFrame, lookback: int = 60) -> dict:
        """
        识别历史压力位和支撑位（多次触及的价格区域）
        
        Args:
            data: 历史数据
            lookback: 回溯期数（默认60日）
            
        Returns:
            压力支撑信息字典
        """
        if len(data) < 20:
            return {'resistance': 0, 'support': 0, 'resistance_strength': 0, 'support_strength': 0}
        
        # 获取价格列
        if 'high' in data.columns and 'low' in data.columns and 'close' in data.columns:
            high = data['high']
            low = data['low']
            close = data['close']
        elif '最高' in data.columns and '最低' in data.columns and '收盘' in data.columns:
            high = data['最高']
            low = data['最低']
            close = data['收盘']
        else:
            return {'resistance': 0, 'support': 0, 'resistance_strength': 0, 'support_strength': 0}
        
        # 限制回溯期
        lookback = min(lookback, len(data))
        recent_high = high.iloc[-lookback:]
        recent_low = low.iloc[-lookback:]
        recent_close = close.iloc[-lookback:]
        
        # 找历史高点（局部极大值）
        highs = []
        for i in range(2, len(recent_high) - 2):
            if (recent_high.iloc[i] >= recent_high.iloc[i-1] and 
                recent_high.iloc[i] >= recent_high.iloc[i-2] and
                recent_high.iloc[i] >= recent_high.iloc[i+1] and 
                recent_high.iloc[i] >= recent_high.iloc[i+2]):
                highs.append(recent_high.iloc[i])
        
        # 找历史低点（局部极小值）
        lows = []
        for i in range(2, len(recent_low) - 2):
            if (recent_low.iloc[i] <= recent_low.iloc[i-1] and 
                recent_low.iloc[i] <= recent_low.iloc[i-2] and
                recent_low.iloc[i] <= recent_low.iloc[i+1] and 
                recent_low.iloc[i] <= recent_low.iloc[i+2]):
                lows.append(recent_low.iloc[i])
        
        current_price = close.iloc[-1]
        
        # 找最近的压力位（当前价格上方，且多次触及的价位）
        resistance = 0
        resistance_strength = 0
        if highs:
            # 按价格分组（容差2%）
            from collections import defaultdict
            price_clusters = defaultdict(list)
            for price in highs:
                if price > current_price:  # 只看上方压力
                    # 找到接近的簇
                    found_cluster = False
                    for cluster_price in list(price_clusters.keys()):
                        if abs(price - cluster_price) / cluster_price < 0.02:  # 2%容差
                            price_clusters[cluster_price].append(price)
                            found_cluster = True
                            break
                    if not found_cluster:
                        price_clusters[price] = [price]
            
            # 找触及次数最多的簇作为主压力位
            if price_clusters:
                best_cluster = max(price_clusters.items(), key=lambda x: len(x[1]))
                resistance = sum(best_cluster[1]) / len(best_cluster[1])  # 平均价格
                resistance_strength = len(best_cluster[1])  # 触及次数
        
        # 找最近的支撑位（当前价格下方，且多次触及的价位）
        support = 0
        support_strength = 0
        if lows:
            from collections import defaultdict
            price_clusters = defaultdict(list)
            for price in lows:
                if price < current_price:  # 只看下方支撑
                    found_cluster = False
                    for cluster_price in list(price_clusters.keys()):
                        if abs(price - cluster_price) / cluster_price < 0.02:
                            price_clusters[cluster_price].append(price)
                            found_cluster = True
                            break
                    if not found_cluster:
                        price_clusters[price] = [price]
            
            if price_clusters:
                best_cluster = max(price_clusters.items(), key=lambda x: len(x[1]))
                support = sum(best_cluster[1]) / len(best_cluster[1])
                support_strength = len(best_cluster[1])
        
        # 如果没找到历史压力位，用近期高低点
        if resistance == 0:
            resistance = recent_high.max()
            resistance_strength = 1
        if support == 0:
            support = recent_low.min()
            support_strength = 1
        
        return {
            'resistance': resistance,
            'support': support,
            'resistance_strength': resistance_strength,  # 触及次数
            'support_strength': support_strength
        }
    
    def detect_candlestick_pattern(self, data: pd.DataFrame) -> dict:
        """
        识别K线形态
        
        Args:
            data: 历史数据（至少需要3根K线）
            
        Returns:
            形态信息字典
        """
        if len(data) < 3:
            return {'pattern': None, 'signal': 0}
        
        # 获取价格列
        if 'open' in data.columns:
            opens = data['open']
            highs = data['high']
            lows = data['low']
            closes = data['close']
        elif '开盘' in data.columns:
            opens = data['开盘']
            highs = data['最高']
            lows = data['最低']
            closes = data['收盘']
        else:
            return {'pattern': None, 'signal': 0}
        
        # 最近3根K线
        o1, h1, l1, c1 = opens.iloc[-3], highs.iloc[-3], lows.iloc[-3], closes.iloc[-3]
        o2, h2, l2, c2 = opens.iloc[-2], highs.iloc[-2], lows.iloc[-2], closes.iloc[-2]
        o3, h3, l3, c3 = opens.iloc[-1], highs.iloc[-1], lows.iloc[-1], closes.iloc[-1]
        
        # 计算实体和影线
        body3 = abs(c3 - o3)
        upper_shadow3 = h3 - max(c3, o3)
        lower_shadow3 = min(c3, o3) - l3
        total_range3 = h3 - l3
        
        # 避免除零
        if total_range3 == 0:
            return {'pattern': None, 'signal': 0}
        
        # 1. 锤子线（看涨）：下影线长，实体小，出现在底部
        if (lower_shadow3 > body3 * 2 and 
            upper_shadow3 < body3 * 0.5 and
            c3 < closes.iloc[-10:-1].mean()):  # 在低位
            return {'pattern': '锤子线', 'signal': 1.0}
        
        # 2. 射击之星（看跌）：上影线长，实体小，出现在顶部
        if (upper_shadow3 > body3 * 2 and 
            lower_shadow3 < body3 * 0.5 and
            c3 > closes.iloc[-10:-1].mean()):  # 在高位
            return {'pattern': '射击之星', 'signal': -1.0}
        
        # 3. 多头吞没（看涨）：阳线吞没前一根阴线
        if (c2 < o2 and  # 前一根是阴线
            c3 > o3 and  # 当前是阳线
            o3 < c2 and  # 开盘低于前收盘
            c3 > o2):    # 收盘高于前开盘
            return {'pattern': '多头吞没', 'signal': 1.2}
        
        # 4. 空头吞没（看跌）：阴线吞没前一根阳线
        if (c2 > o2 and  # 前一根是阳线
            c3 < o3 and  # 当前是阴线
            o3 > c2 and  # 开盘高于前收盘
            c3 < o2):    # 收盘低于前开盘
            return {'pattern': '空头吞没', 'signal': -1.2}
        
        # 5. 早晨之星（看涨三K组合）
        if (c1 < o1 and  # 第一根阴线
            abs(c2 - o2) < body3 * 0.5 and  # 第二根十字星
            c3 > o3 and  # 第三根阳线
            c3 > (o1 + c1) / 2):  # 突破第一根中点
            return {'pattern': '早晨之星', 'signal': 1.5}
        
        # 6. 黄昏之星（看跌三K组合）
        if (c1 > o1 and  # 第一根阳线
            abs(c2 - o2) < body3 * 0.5 and  # 第二根十字星
            c3 < o3 and  # 第三根阴线
            c3 < (o1 + c1) / 2):  # 跌破第一根中点
            return {'pattern': '黄昏之星', 'signal': -1.5}
        
        # 7. 十字星（变盘信号）
        if body3 < total_range3 * 0.1:  # 实体很小
            return {'pattern': '十字星', 'signal': 0}
        
        return {'pattern': None, 'signal': 0}
    
    def evaluate_signal_quality(self, symbol_data: pd.DataFrame, k: float, d: float, j: float,
                                 volume_ratio: float, pattern_info: dict, 
                                 resistance_info: dict, market_env: dict) -> dict:
        """
        多维度评估信号质量
        
        评分维度：
        1. 趋势(Trend): 市场和个股趋势强度 (0-30分)
        2. 方向(Direction): KDJ指标方向性 (0-25分)
        3. 位置(Position): 超买超卖位置 (0-20分)
        4. 形态(Pattern): K线形态强度 (0-15分)
        5. 量能(Volume): 成交量配合度 (0-10分)
        
        Returns:
            评分详情字典
        """
        scores = {}
        
        # 1. 趋势评分 (0-30分)
        trend_score = 0
        if market_env.get('environment') == 'bull':
            trend_score += 15  # 牛市加分
        elif market_env.get('environment') == 'bear':
            trend_score -= 10  # 熊市扣分
        elif market_env.get('environment') == 'sideways':
            trend_score += 5   # 震荡市小加分(适合KDJ)
        
        # 个股趋势：看MA排列
        if 'close' in symbol_data.columns:
            close = symbol_data['close']
        elif '收盘' in symbol_data.columns:
            close = symbol_data['收盘']
        else:
            close = None
        
        if close is not None and len(close) >= 60:
            current_price = close.iloc[-1]
            ma20 = close.iloc[-20:].mean()
            ma60 = close.iloc[-60:].mean()
            
            if current_price > ma20 > ma60:
                trend_score += 15  # 多头排列
            elif current_price < ma20 < ma60:
                trend_score -= 5   # 空头排列
            else:
                trend_score += 5   # 震荡
        
        scores['trend'] = max(0, min(30, trend_score))
        
        # 2. 方向评分 (0-25分)
        direction_score = 0
        
        # KDJ金叉强度
        cross_strength = abs(k - d)
        if cross_strength > 10:
            direction_score += 15  # 强金叉
        elif cross_strength > 5:
            direction_score += 10  # 中等金叉
        else:
            direction_score += 5   # 弱金叉
        
        # J值方向
        if len(symbol_data) >= 3:
            j_values = self.calculate_kdj(symbol_data)[2]
            if len(j_values) >= 2:
                if j_values.iloc[-1] > j_values.iloc[-2]:
                    direction_score += 10  # J值向上
                else:
                    direction_score -= 5   # J值向下
        
        scores['direction'] = max(0, min(25, direction_score))
        
        # 3. 位置评分 (0-20分)
        position_score = 0
        
        # 超卖区位置（K值越低越好）
        if k < 15:
            position_score += 20  # 深度超卖
        elif k < 20:
            position_score += 15  # 超卖
        elif k < 30:
            position_score += 10  # 接近超卖
        else:
            position_score += 5   # 位置一般
        
        # 相对压力支撑位置
        if resistance_info.get('support', 0) > 0 and close is not None and len(close) > 0:
            support = resistance_info['support']
            current_price = close.iloc[-1]
            distance_to_support = (current_price - support) / support
            if distance_to_support < 0.05:  # 接近支撑5%以内
                position_score += 5
        
        scores['position'] = max(0, min(20, position_score))
        
        # 4. 形态评分 (0-15分)
        pattern_score = 0
        pattern_signal = pattern_info.get('signal', 0)
        
        if pattern_signal >= 1.5:  # 早晨之星
            pattern_score = 15
        elif pattern_signal >= 1.2:  # 多头吞没
            pattern_score = 12
        elif pattern_signal >= 1.0:  # 锤子线
            pattern_score = 10
        elif pattern_signal > 0:  # 其他看涨形态
            pattern_score = 5
        
        # 历史压力强度
        if resistance_info.get('resistance_strength', 0) >= 3:
            pattern_score += 3  # 突破强压力加分
        
        scores['pattern'] = max(0, min(15, pattern_score))
        
        # 5. 量能评分 (0-10分)
        volume_score = 0
        
        if volume_ratio >= 2.0:
            volume_score = 10  # 放量2倍以上
        elif volume_ratio >= 1.5:
            volume_score = 8   # 放量1.5倍
        elif volume_ratio >= 1.2:
            volume_score = 6   # 放量1.2倍
        elif volume_ratio >= 1.0:
            volume_score = 4   # 持平
        else:
            volume_score = 2   # 缩量
        
        scores['volume'] = max(0, min(10, volume_score))
        
        # 计算总分和级别
        total_score = sum(scores.values())
        
        # 信号级别分类
        if total_score >= 80:
            level = 'A'  # 优质信号
            priority = 1
        elif total_score >= 65:
            level = 'B'  # 良好信号
            priority = 2
        elif total_score >= 50:
            level = 'C'  # 一般信号
            priority = 3
        else:
            level = 'D'  # 弱信号
            priority = 4
        
        return {
            'scores': scores,
            'total_score': total_score,
            'level': level,
            'priority': priority,
            'details': f"趋势{scores['trend']}/方向{scores['direction']}/位置{scores['position']}/形态{scores['pattern']}/量能{scores['volume']}"
        }
    
    def generate_signals(self, data: pd.DataFrame, 
                        context: Optional[Dict] = None) -> List[Signal]:
        """
        生成交易信号
        
        Args:
            data: 历史数据DataFrame (包含symbol列,index是日期)
            context: 额外上下文信息
        
        Returns:
            信号列表
        """
        signals = []
        
        # 检查数据
        if data.empty or 'symbol' not in data.columns:
            return signals
        
        # 按symbol分组处理
        for symbol in data['symbol'].unique():
            try:
                # 获取该symbol的所有历史数据
                symbol_data = data[data['symbol'] == symbol].copy()
                
                # 更新历史缓存
                self.history_data[symbol] = symbol_data
                
                # 检查数据是否足够
                if len(self.history_data[symbol]) < self.n + 5:
                    continue
                
                # 计算KDJ指标
                k, d, j = self.calculate_kdj(self.history_data[symbol])
                
                # 获取最新值
                current_k = k.iloc[-1]
                current_d = d.iloc[-1]
                current_j = j.iloc[-1]
                
                # 获取最新行的价格和时间
                latest_row = symbol_data.iloc[-1]
                
                # 尝试获取收盘价(英文或中文)
                if 'close' in latest_row:
                    current_price = latest_row['close']
                elif '收盘' in latest_row:
                    current_price = latest_row['收盘']
                else:
                    continue  # 无法获取价格,跳过
                
                # 时间戳用DataFrame index
                timestamp = symbol_data.index[-1]
                
                # 检测金叉/死叉
                has_golden_cross = self.detect_golden_cross(k, d)
                has_death_cross = self.detect_death_cross(k, d)
                
                # 买入信号
                if symbol not in self.positions:
                    # 市场环境检查
                    market_env = {'allow_long': True, 'position_ratio': 1.0, 'environment': 'neutral'}
                    if self.market_filter and context and 'market_data' in context:
                        market_env = self.check_market_environment(context['market_data'])
                        if not market_env['allow_long']:
                            logger.debug(f"[KDJ跳过] {symbol}: 市场环境不佳({market_env['environment']})")
                            continue
                    
                    # 优化后的条件:
                    # 1. 发生金叉(K上穿D)
                    # 2. K值在超卖区或刚离开超卖区(K<30)
                    # 3. 成交量放大（>1.2倍均量）
                    # 注：不再要求价格>MA20,允许在均线下抄底
                    in_oversold_zone = current_k < 30  # 放宽到30
                    
                    if has_golden_cross and in_oversold_zone:
                        # 检查是否达到最大持仓数
                        if len(self.positions) >= self.max_positions:
                            continue
                        
                        # K线形态分析
                        pattern_info = self.detect_candlestick_pattern(symbol_data)
                        
                        # 提前计算压力位支撑位（评分系统需要）
                        resistance_info = self.calculate_resistance_support(symbol_data)
                        
                        # 成交量过滤：要求放量
                        volume_ma = self.calculate_volume_ma(symbol_data)
                        if 'volume' in symbol_data.columns:
                            current_volume = symbol_data['volume'].iloc[-1]
                        elif '成交量' in symbol_data.columns:
                            current_volume = symbol_data['成交量'].iloc[-1]
                        else:
                            current_volume = 0
                        
                        volume_ratio = current_volume / volume_ma if volume_ma > 0 else 0
                        
                        # 成交量需大于20日均量的1.2倍（确认资金流入）
                        # 但如果有强烈看涨K线形态（如早晨之星），可以放宽要求
                        volume_threshold = 1.2
                        if pattern_info['signal'] >= 1.2:  # 强烈看涨形态
                            volume_threshold = 1.0  # 放宽到只需超过均量
                        
                        if volume_ratio < volume_threshold:
                            logger.debug(f"[KDJ跳过] {symbol}: 量能不足({volume_ratio:.2f}倍<{volume_threshold})")
                            continue
                        
                        # 信号强度：越接近超卖区底部越强，量价配合加权
                        strength = max(0.5, min(1.0, 1.0 - (current_k / self.oversold)))
                        strength = min(1.0, strength * (volume_ratio / 1.5))  # 量能加权
                        
                        # K线形态加权
                        if pattern_info['signal'] > 0:
                            strength = min(1.0, strength * (1 + pattern_info['signal'] * 0.2))
                        
                        # 如果J值回升，增强信号
                        j_rising = len(j) >= 2 and j.iloc[-1] > j.iloc[-2]
                        if j_rising:
                            strength = min(1.0, strength * 1.2)
                        
                        # 多维度评估信号质量
                        signal_quality = self.evaluate_signal_quality(
                            symbol_data=symbol_data,
                            k=current_k,
                            d=current_d,
                            j=current_j,
                            volume_ratio=volume_ratio,
                            pattern_info=pattern_info,
                            resistance_info=resistance_info,
                            market_env=market_env
                        )
                        
                        # 过滤低质量信号（使用可配置阈值）
                        if signal_quality['total_score'] < self.signal_threshold:
                            logger.debug(f"[KDJ跳过] {symbol}: 信号质量不足({signal_quality['total_score']:.0f}分<{self.signal_threshold}分/{signal_quality['level']}级)")
                            continue
                        
                        # 市场环境调整信号强度
                        strength = strength * market_env['position_ratio']
                        
                        # 根据信号级别调整强度
                        if signal_quality['level'] == 'A':
                            strength = min(1.0, strength * 1.2)  # A级信号加权20%
                        elif signal_quality['level'] == 'C':
                            strength = strength * 0.8  # C级信号降权20%
                        
                        # 计算MA20用于后续卖出判断（resistance_info已在前面计算）
                        ma20 = self.calculate_ma(symbol_data, 20)
                        
                        # 构建原因说明
                        reason_parts = [
                            f"【{signal_quality['level']}级{signal_quality['total_score']}分】",
                            f"KDJ金叉(K={current_k:.1f})",
                            f"放量{volume_ratio:.1f}倍"
                        ]
                        if pattern_info['pattern']:
                            reason_parts.append(f"{pattern_info['pattern']}")
                        if resistance_info['resistance_strength'] >= 3:
                            reason_parts.append(f"突破{resistance_info['resistance_strength']}次压力")
                        if market_env['environment'] != 'neutral':
                            env_label = {'bull': '牛市', 'bear': '熊市', 'sideways': '震荡'}[market_env['environment']]
                            reason_parts.append(f"{env_label}环境")
                        reason_parts.append(f"[{self.mode}模式]")
                        reason_parts.append(f"({signal_quality['details']})")  # 详细评分
                        
                        signals.append(Signal(
                            symbol=symbol,
                            direction=1,  # 买入
                            strength=strength,
                            timestamp=timestamp,
                            price=current_price,
                            reason="+".join(reason_parts),
                            metadata={
                                'k': current_k,
                                'd': current_d,
                                'j': current_j,
                                'volume_ratio': volume_ratio,
                                'ma20': ma20,
                                'resistance': resistance_info['resistance'],
                                'resistance_strength': resistance_info['resistance_strength'],
                                'support': resistance_info['support'],
                                'support_strength': resistance_info['support_strength'],
                                'candlestick_pattern': pattern_info['pattern'],
                                'pattern_signal': pattern_info['signal'],
                                'signal_level': signal_quality['level'],  # 新增：信号级别
                                'signal_score': signal_quality['total_score'],  # 新增：总评分
                                'signal_priority': signal_quality['priority'],  # 新增：优先级
                                'score_breakdown': signal_quality['scores'],  # 新增：评分明细
                                'market_environment': market_env['environment'],  # 新增：市场环境
                                'mode': self.mode,
                                'golden_cross': True,
                                'oversold_zone': in_oversold_zone,
                                'bullish_trend': False,
                                'strategy': 'kdj_plugin'
                            }
                        ))
                        
                        logger.debug(f"[KDJ买入] {symbol}: K={current_k:.1f}, D={current_d:.1f}, "
                                   f"J={current_j:.1f}, 金叉+超卖+放量{volume_ratio:.1f}倍")
                
                # 卖出信号
                elif symbol in self.positions:
                    # 计算压力位支撑位
                    resistance_info = self.calculate_resistance_support(symbol_data)
                    
                    # K线形态分析
                    pattern_info = self.detect_candlestick_pattern(symbol_data)
                    
                    # 支撑位止损：跌破前N日低点（箱体下沿）
                    if resistance_info['support'] > 0:
                        support_stop = resistance_info['support'] * (1 + self.resistance_buffer)
                        # 如果出现强烈看跌K线形态（如射击之星），提前止损
                        if pattern_info['signal'] < -1.0:
                            support_stop = resistance_info['support'] * (1 + self.resistance_buffer * 2)  # 放宽止损位
                        
                        if current_price <= support_stop:
                            reason = f"跌破支撑位止损(价格={current_price:.2f}, 支撑={resistance_info['support']:.2f}"
                            if pattern_info['pattern']:
                                reason += f", {pattern_info['pattern']}"
                            reason += ")"
                            
                            signals.append(Signal(
                                symbol=symbol,
                                direction=-1,
                                strength=1.0,  # 强制止损
                                timestamp=timestamp,
                                price=current_price,
                                reason=reason,
                                metadata={
                                    'k': current_k,
                                    'd': current_d,
                                    'j': current_j,
                                    'support': resistance_info['support'],
                                    'candlestick_pattern': pattern_info['pattern'],
                                    'support_stop_loss': True,
                                    'strategy': 'kdj_plugin'
                                }
                            ))
                            logger.debug(f"[KDJ卖出] {symbol}: 跌破支撑位{resistance_info['support']:.2f}")
                            continue
                    
                    # 短线模式：接近压力位主动止盈
                    if self.mode == 'swing' and resistance_info['resistance'] > 0:
                        resistance_target = resistance_info['resistance'] * (1 - self.resistance_buffer)
                        
                        # 如果压力位被多次触及（强压力），更积极止盈
                        if resistance_info['resistance_strength'] >= 3:
                            resistance_target = resistance_info['resistance'] * (1 - self.resistance_buffer * 1.5)
                        
                        # 如果出现看跌K线形态，提前止盈
                        if pattern_info['signal'] < -0.5:
                            resistance_target = current_price * 0.98  # 当前价-2%就止盈
                        
                        if current_price >= resistance_target:
                            reason = f"接近压力位止盈(价格={current_price:.2f}, 压力={resistance_info['resistance']:.2f}"
                            if resistance_info['resistance_strength'] >= 3:
                                reason += f", {resistance_info['resistance_strength']}次触及"
                            if pattern_info['pattern']:
                                reason += f", {pattern_info['pattern']}"
                            reason += ")"
                            
                            signals.append(Signal(
                                symbol=symbol,
                                direction=-1,
                                strength=0.9,
                                timestamp=timestamp,
                                price=current_price,
                                reason=reason,
                                metadata={
                                    'k': current_k,
                                    'd': current_d,
                                    'j': current_j,
                                    'resistance': resistance_info['resistance'],
                                    'resistance_strength': resistance_info['resistance_strength'],
                                    'candlestick_pattern': pattern_info['pattern'],
                                    'resistance_take_profit': True,
                                    'strategy': 'kdj_plugin'
                                }
                            ))
                            logger.debug(f"[KDJ卖出] {symbol}: 短线模式压力位止盈")
                            continue
                    
                    # 检查趋势：价格跌破MA20立即卖出（趋势转弱）
                    trend = self.check_trend(symbol_data)
                    if trend['is_bearish']:
                        signals.append(Signal(
                            symbol=symbol,
                            direction=-1,  # 卖出
                            strength=0.8,
                            timestamp=timestamp,
                            price=current_price,
                            reason=f"跌破MA20(价格={current_price:.2f}, MA20={trend['ma20']:.2f})",
                            metadata={
                                'k': current_k,
                                'd': current_d,
                                'j': current_j,
                                'ma20': trend['ma20'],
                                'trend_break': True,
                                'strategy': 'kdj_plugin'
                            }
                        ))
                        logger.debug(f"[KDJ卖出] {symbol}: 跌破MA20，趋势转弱")
                        continue
                    
                    # 优化后的条件:
                    # 1. 发生死叉(K下穿D)
                    # 2. K值在超买区或刚进入超买区(K>70)
                    in_overbought_zone = current_k > 70  # 放宽到70
                    
                    if has_death_cross and in_overbought_zone:
                        # 成交量过滤：放量下跌更危险，或K值极高不管量能
                        volume_ma = self.calculate_volume_ma(symbol_data)
                        if 'volume' in symbol_data.columns:
                            current_volume = symbol_data['volume'].iloc[-1]
                        elif '成交量' in symbol_data.columns:
                            current_volume = symbol_data['成交量'].iloc[-1]
                        else:
                            current_volume = volume_ma  # 无数据默认通过
                        
                        volume_ratio = current_volume / volume_ma if volume_ma > 0 else 1.5
                        
                        # 成交量放大(>均量)或K值极高(>85)才卖出
                        if volume_ratio < 1.0 and current_k <= 85:
                            logger.debug(f"[KDJ持有] {symbol}: 量能萎缩({volume_ratio:.2f}倍),继续持有")
                            continue
                        
                        # 信号强度：越接近超买区顶部越强
                        strength = max(0.5, min(1.0, (current_k - self.overbought) / (100 - self.overbought)))
                        
                        volume_tag = "放量" if volume_ratio >= 1.0 else "极度超买"
                        signals.append(Signal(
                            symbol=symbol,
                            direction=-1,  # 卖出
                            strength=strength,
                            timestamp=timestamp,
                            price=current_price,
                            reason=f"KDJ死叉(K={current_k:.1f}, D={current_d:.1f}, J={current_j:.1f})+{volume_tag}",
                            metadata={
                                'k': current_k,
                                'd': current_d,
                                'j': current_j,
                                'volume_ratio': volume_ratio,
                                'death_cross': True,
                                'overbought_zone': in_overbought_zone,
                                'strategy': 'kdj_plugin'
                            }
                        ))
                        
                        logger.debug(f"[KDJ卖出] {symbol}: K={current_k:.1f}, D={current_d:.1f}, "
                                   f"J={current_j:.1f}, 死叉+超买+{volume_tag}(量能{volume_ratio:.1f}倍)")
                
                # 保存当前KDJ值
                self.last_kdj[symbol] = {
                    'k': current_k,
                    'd': current_d,
                    'j': current_j
                }
                
            except Exception as e:
                logger.warning(f"[KDJ策略] 处理{symbol}时出错: {e}")
                continue
        
        return signals
    
    def on_order_filled(self, symbol: str, direction: int, price: float, 
                       quantity: int, timestamp):
        """
        订单成交回调
        
        Args:
            symbol: 股票代码
            direction: 方向（1=买入，-1=卖出）
            price: 成交价格
            quantity: 成交数量
            timestamp: 成交时间
        """
        if direction == 1:
            # 买入成交
            self.positions[symbol] = {
                'entry_price': price,
                'entry_time': timestamp,
                'quantity': quantity
            }
            logger.info(f"[KDJ策略] 开仓: {symbol} @ {price:.2f} × {quantity}")
        
        elif direction == -1 and symbol in self.positions:
            # 卖出成交
            entry_price = self.positions[symbol]['entry_price']
            pnl_pct = (price / entry_price - 1) * 100
            
            logger.info(f"[KDJ策略] 平仓: {symbol} @ {price:.2f} × {quantity}, "
                       f"盈亏={pnl_pct:+.2f}%")
            
            del self.positions[symbol]
    
    def get_name(self) -> str:
        """获取策略名称"""
        return "KDJ_Strategy"
    
    def get_version(self) -> str:
        """获取策略版本"""
        return "1.0.0"
    
    def get_description(self) -> str:
        """获取策略描述"""
        return (f"KDJ随机指标策略 (周期={self.n}, 超卖={self.oversold}, "
                f"超买={self.overbought})")
