"""
高性能技术指标计算库 - 向量化Python版本
使用NumPy向量化操作，避免Python循环
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional
from numba import jit, prange
import warnings

warnings.filterwarnings('ignore')


class VectorizedIndicators:
    """向量化技术指标计算器"""
    
    @staticmethod
    @jit(nopython=True, cache=True)
    def _rolling_mean_numba(arr: np.ndarray, window: int) -> np.ndarray:
        """Numba加速的滚动均值"""
        n = len(arr)
        result = np.empty(n)
        result[:window-1] = np.nan
        
        for i in range(window-1, n):
            result[i] = np.mean(arr[i-window+1:i+1])
        
        return result
    
    @staticmethod
    @jit(nopython=True, cache=True)
    def _ema_numba(arr: np.ndarray, span: int) -> np.ndarray:
        """Numba加速的指数移动平均"""
        n = len(arr)
        result = np.empty(n)
        alpha = 2.0 / (span + 1.0)
        
        result[0] = arr[0]
        for i in range(1, n):
            result[i] = alpha * arr[i] + (1 - alpha) * result[i-1]
        
        return result
    
    @staticmethod
    def ma(close: np.ndarray, period: int, use_numba: bool = True) -> np.ndarray:
        """
        移动平均线
        
        Args:
            close: 收盘价数组
            period: 周期
            use_numba: 是否使用Numba加速
            
        Returns:
            MA值数组
        """
        if use_numba:
            return VectorizedIndicators._rolling_mean_numba(close, period)
        else:
            return pd.Series(close).rolling(window=period).mean().values
    
    @staticmethod
    def ema(close: np.ndarray, span: int, use_numba: bool = True) -> np.ndarray:
        """
        指数移动平均
        
        Args:
            close: 收盘价数组
            span: 跨度
            use_numba: 是否使用Numba加速
            
        Returns:
            EMA值数组
        """
        if use_numba:
            return VectorizedIndicators._ema_numba(close, span)
        else:
            return pd.Series(close).ewm(span=span, adjust=False).mean().values
    
    @staticmethod
    def kdj(high: np.ndarray, low: np.ndarray, close: np.ndarray,
            n: int = 9, m1: int = 3, m2: int = 3, use_numba: bool = False) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        KDJ指标（向量化）
        
        Args:
            high: 最高价数组
            low: 最低价数组
            close: 收盘价数组
            n: RSV周期
            m1: K周期
            m2: D周期
            use_numba: 是否使用Numba（大数据集推荐）
            
        Returns:
            (K, D, J)
        """
        if use_numba:
            # 使用Numba加速版本（适合大数据集）
            low_n, _ = VectorizedIndicators._rolling_min_max_numba(low, n)
            _, high_n = VectorizedIndicators._rolling_min_max_numba(high, n)
        else:
            # 使用Pandas版本（适合小数据集）
            low_n = pd.Series(low).rolling(window=n, min_periods=1).min().values
            high_n = pd.Series(high).rolling(window=n, min_periods=1).max().values
        
        # 避免除零
        range_hn_ln = high_n - low_n
        rsv = np.where(range_hn_ln == 0, 50.0, (close - low_n) / range_hn_ln * 100)
        
        # 填充初始NaN值
        rsv[np.isnan(rsv)] = 50.0
        
        # 计算K值（EMA）- 使用简单版本避免Numba开销
        span_k = m1 * 2 - 1
        alpha_k = 2.0 / (span_k + 1.0)
        k = np.zeros_like(rsv)
        k[0] = rsv[0]
        for i in range(1, len(rsv)):
            k[i] = alpha_k * rsv[i] + (1 - alpha_k) * k[i-1]
        
        # 计算D值（EMA）
        span_d = m2 * 2 - 1
        alpha_d = 2.0 / (span_d + 1.0)
        d = np.zeros_like(k)
        d[0] = k[0]
        for i in range(1, len(k)):
            d[i] = alpha_d * k[i] + (1 - alpha_d) * d[i-1]
        
        # 计算J值
        j = 3 * k - 2 * d
        
        return k, d, j
    
    @staticmethod
    def macd(close: np.ndarray, 
             fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        MACD指标（向量化）
        
        Args:
            close: 收盘价数组
            fast: 快线周期
            slow: 慢线周期
            signal: 信号线周期
            
        Returns:
            (DIF, DEA, MACD柱)
        """
        ema_fast = VectorizedIndicators._ema_numba(close, fast)
        ema_slow = VectorizedIndicators._ema_numba(close, slow)
        
        dif = ema_fast - ema_slow
        dea = VectorizedIndicators._ema_numba(dif, signal)
        macd_hist = 2 * (dif - dea)
        
        return dif, dea, macd_hist
    
    @staticmethod
    @jit(nopython=True, cache=True)
    def _rsi_numba(close: np.ndarray, period: int) -> np.ndarray:
        """Numba加速的RSI计算"""
        n = len(close)
        rsi = np.empty(n)
        rsi[:period] = np.nan
        
        # 计算价格变化
        deltas = np.diff(close)
        
        # 初始平均增益和损失
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[:period-1])
        avg_loss = np.mean(losses[:period-1])
        
        if avg_loss == 0:
            rsi[period] = 100
        else:
            rs = avg_gain / avg_loss
            rsi[period] = 100 - (100 / (1 + rs))
        
        # 后续使用EMA方式更新
        alpha = 1.0 / period
        for i in range(period + 1, n):
            gain = gains[i-1] if i-1 < len(gains) else 0
            loss = losses[i-1] if i-1 < len(losses) else 0
            
            avg_gain = alpha * gain + (1 - alpha) * avg_gain
            avg_loss = alpha * loss + (1 - alpha) * avg_loss
            
            if avg_loss == 0:
                rsi[i] = 100
            else:
                rs = avg_gain / avg_loss
                rsi[i] = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
        """
        RSI指标（向量化+Numba）
        
        Args:
            close: 收盘价数组
            period: 周期
            
        Returns:
            RSI值数组
        """
        return VectorizedIndicators._rsi_numba(close, period)
    
    @staticmethod
    def bollinger_bands(close: np.ndarray, period: int = 20, std_dev: float = 2.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        布林带（向量化）
        
        Args:
            close: 收盘价数组
            period: 周期
            std_dev: 标准差倍数
            
        Returns:
            (上轨, 中轨, 下轨)
        """
        middle = VectorizedIndicators.ma(close, period, use_numba=True)
        std = pd.Series(close).rolling(window=period).std().values
        
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        
        return upper, middle, lower
    
    @staticmethod
    def obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        """
        能量潮OBV（向量化）
        
        Args:
            close: 收盘价数组
            volume: 成交量数组
            
        Returns:
            OBV值数组
        """
        # 价格变化方向
        direction = np.sign(np.diff(close, prepend=close[0]))
        
        # OBV累计
        obv = np.cumsum(direction * volume)
        
        return obv
    
    @staticmethod
    def vwap(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        """
        成交量加权平均价VWAP（向量化）
        
        Args:
            close: 收盘价数组
            volume: 成交量数组
            
        Returns:
            VWAP值数组
        """
        cumulative_pv = np.cumsum(close * volume)
        cumulative_v = np.cumsum(volume)
        
        vwap = np.where(cumulative_v > 0, cumulative_pv / cumulative_v, close)
        
        return vwap
    
    @staticmethod
    def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """
        平均真实波幅ATR（向量化）
        
        Args:
            high: 最高价数组
            low: 最低价数组
            close: 收盘价数组
            period: 周期
            
        Returns:
            ATR值数组
        """
        # 真实波幅
        prev_close = np.roll(close, 1)
        prev_close[0] = close[0]
        
        tr1 = high - low
        tr2 = np.abs(high - prev_close)
        tr3 = np.abs(low - prev_close)
        
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        
        # ATR = EMA(TR)
        atr = VectorizedIndicators._ema_numba(tr, period)
        
        return atr


class IndicatorCache:
    """指标缓存器 - 避免重复计算"""
    
    def __init__(self):
        self.cache = {}
        self.cache_hits = 0
        self.cache_misses = 0
    
    def get_or_compute(self, key: str, compute_func, *args, **kwargs):
        """
        获取缓存或计算
        
        Args:
            key: 缓存键
            compute_func: 计算函数
            *args, **kwargs: 计算函数参数
            
        Returns:
            计算结果
        """
        if key in self.cache:
            self.cache_hits += 1
            return self.cache[key]
        
        self.cache_misses += 1
        result = compute_func(*args, **kwargs)
        self.cache[key] = result
        
        return result
    
    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0
    
    def stats(self):
        """缓存统计"""
        total = self.cache_hits + self.cache_misses
        hit_rate = self.cache_hits / total * 100 if total > 0 else 0
        
        return {
            'hits': self.cache_hits,
            'misses': self.cache_misses,
            'hit_rate': hit_rate,
            'size': len(self.cache)
        }


# 全局缓存实例
_global_cache = IndicatorCache()


def get_global_cache() -> IndicatorCache:
    """获取全局缓存"""
    return _global_cache


if __name__ == '__main__':
    import time
    
    print("=" * 70)
    print("      高性能技术指标库性能测试")
    print("=" * 70)
    print()
    
    # 生成测试数据
    n_days = 1000
    np.random.seed(42)
    
    close = 100 * (1 + np.random.randn(n_days).cumsum() * 0.01)
    high = close * (1 + np.random.uniform(0, 0.02, n_days))
    low = close * (1 - np.random.uniform(0, 0.02, n_days))
    volume = np.random.randint(1000000, 10000000, n_days)
    
    print(f"测试数据：{n_days}天")
    print()
    
    # 测试KDJ
    print("【KDJ指标】")
    start = time.time()
    for _ in range(100):
        k, d, j = VectorizedIndicators.kdj(high, low, close)
    kdj_time = time.time() - start
    print(f"   100次计算耗时：{kdj_time:.3f}秒")
    print(f"   单次耗时：{kdj_time*10:.1f}ms")
    print(f"   最新值：K={k[-1]:.2f}, D={d[-1]:.2f}, J={j[-1]:.2f}")
    print()
    
    # 测试MACD
    print("【MACD指标】")
    start = time.time()
    for _ in range(100):
        dif, dea, macd = VectorizedIndicators.macd(close)
    macd_time = time.time() - start
    print(f"   100次计算耗时：{macd_time:.3f}秒")
    print(f"   单次耗时：{macd_time*10:.1f}ms")
    print(f"   最新值：DIF={dif[-1]:.2f}, DEA={dea[-1]:.2f}, MACD={macd[-1]:.2f}")
    print()
    
    # 测试RSI
    print("【RSI指标】")
    start = time.time()
    for _ in range(100):
        rsi = VectorizedIndicators.rsi(close)
    rsi_time = time.time() - start
    print(f"   100次计算耗时：{rsi_time:.3f}秒")
    print(f"   单次耗时：{rsi_time*10:.1f}ms")
    print(f"   最新值：RSI={rsi[-1]:.2f}")
    print()
    
    # 测试OBV
    print("【OBV指标】")
    start = time.time()
    for _ in range(100):
        obv = VectorizedIndicators.obv(close, volume)
    obv_time = time.time() - start
    print(f"   100次计算耗时：{obv_time:.3f}秒")
    print(f"   单次耗时：{obv_time*10:.1f}ms")
    print(f"   最新值：OBV={obv[-1]:.0f}")
    print()
    
    print("=" * 70)
    print("✅ 所有指标计算成功！")
    print()
    print("💡 使用建议：")
    print("   1. 替换策略中的Pandas rolling操作")
    print("   2. 使用IndicatorCache避免重复计算")
    print("   3. 大数据集优先使用Numba加速版本")
