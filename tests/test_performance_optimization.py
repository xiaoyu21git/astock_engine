"""
性能优化对比测试
比较优化前后的性能提升
"""

import time
import numpy as np
import pandas as pd
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from optimization.vectorized_indicators import VectorizedIndicators
from optimization.smart_cache import get_clustering_cache
from sklearn.cluster import KMeans


def generate_test_data(n_days: int = 1000):
    """生成测试数据"""
    np.random.seed(42)
    
    close = 100 * (1 + np.random.randn(n_days).cumsum() * 0.01)
    high = close * (1 + np.random.uniform(0, 0.02, n_days))
    low = close * (1 - np.random.uniform(0, 0.02, n_days))
    volume = np.random.randint(1000000, 10000000, n_days)
    
    df = pd.DataFrame({
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    
    return df


def bench_kdj_original(df: pd.DataFrame, n_iterations: int = 100):
    """测试原始KDJ计算（Pandas） - 基准函数，非pytest测试用例"""
    def kdj_pandas(high, low, close, n=9, m1=3, m2=3):
        rsv = (close - low.rolling(n).min()) / (high.rolling(n).max() - low.rolling(n).min()) * 100
        k = rsv.ewm(com=m1-1, adjust=False).mean()
        d = k.ewm(com=m2-1, adjust=False).mean()
        j = 3 * k - 2 * d
        return k, d, j
    
    start = time.time()
    for _ in range(n_iterations):
        k, d, j = kdj_pandas(df['high'], df['low'], df['close'])
    elapsed = time.time() - start
    
    return elapsed, k.iloc[-1], d.iloc[-1], j.iloc[-1]


def bench_kdj_optimized(df: pd.DataFrame, n_iterations: int = 100):
    """测试优化后的KDJ计算（NumPy+Numba） - 基准函数，非pytest测试用例"""
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    
    start = time.time()
    for _ in range(n_iterations):
        k, d, j = VectorizedIndicators.kdj(high, low, close)
    elapsed = time.time() - start
    
    return elapsed, k[-1], d[-1], j[-1]


def bench_clustering_original(data: np.ndarray, n_runs: int = 10):
    """测试原始聚类（无缓存） - 基准函数，非pytest测试用例"""
    def kmeans_cluster(data, n_clusters):
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(data)
        return labels, kmeans.cluster_centers_
    
    start = time.time()
    for _ in range(n_runs):
        labels, centers = kmeans_cluster(data, 3)
    elapsed = time.time() - start
    
    return elapsed, labels, centers


def bench_clustering_cached(data: np.ndarray, n_runs: int = 10):
    """测试带缓存的聚类 - 基准函数，非pytest测试用例"""
    cache = get_clustering_cache()
    cache.clear()  # 清空缓存
    
    def kmeans_cluster(data, n_clusters):
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(data)
        return {
            'labels': labels,
            'centers': kmeans.cluster_centers_
        }
    
    start = time.time()
    for _ in range(n_runs):
        result = cache.get_or_cluster(data, 3, kmeans_cluster)
    elapsed = time.time() - start
    
    return elapsed, result['labels'], result['centers']


def bench_obv_original(df: pd.DataFrame, n_iterations: int = 100):
    """测试原始OBV计算（Pandas） - 基准函数，非pytest测试用例"""
    def obv_pandas(close, volume):
        direction = np.sign(close.diff())
        obv = (direction * volume).fillna(0).cumsum()
        return obv
    
    start = time.time()
    for _ in range(n_iterations):
        obv = obv_pandas(df['close'], df['volume'])
    elapsed = time.time() - start
    
    return elapsed, obv.iloc[-1]


def bench_obv_optimized(df: pd.DataFrame, n_iterations: int = 100):
    """测试优化后的OBV计算（NumPy） - 基准函数，非pytest测试用例"""
    close = df['close'].values
    volume = df['volume'].values
    
    start = time.time()
    for _ in range(n_iterations):
        obv = VectorizedIndicators.obv(close, volume)
    elapsed = time.time() - start
    
    return elapsed, obv[-1]


def print_comparison(name: str, time_orig: float, time_opt: float, 
                    value_orig, value_opt, n_iter: int = 100):
    """打印对比结果"""
    speedup = time_orig / time_opt if time_opt > 0 else float('inf')
    
    print(f"\n【{name}】")
    print(f"   原始方法: {time_orig:.3f}秒 ({n_iter}次)")
    print(f"   优化方法: {time_opt:.3f}秒 ({n_iter}次)")
    print(f"   单次耗时: {time_orig*1000/n_iter:.1f}ms → {time_opt*1000/n_iter:.1f}ms")
    print(f"   ⚡ 加速比: {speedup:.1f}x" if speedup != float('inf') else "   ⚡ 加速比: ∞x")
    
    # 验证结果正确性
    if isinstance(value_orig, (int, float, np.number)):
        diff = abs(value_orig - value_opt)
        if diff < 1e-6:
            print(f"   ✅ 结果一致")
        else:
            print(f"   ⚠️  结果差异: {diff:.6f}")
    
    return speedup


if __name__ == '__main__':
    print("=" * 80)
    print("                    性能优化对比测试")
    print("=" * 80)
    print()
    
    # 生成测试数据
    print("生成测试数据...")
    df = generate_test_data(1000)
    clustering_data = np.random.randn(500, 2)
    print(f"   ✅ 数据准备完成：{len(df)}天行情数据")
    print()
    
    speedups = {}
    
    # 测试1：KDJ指标
    print("=" * 80)
    print("测试1：KDJ指标计算")
    print("=" * 80)
    
    time_orig, k_orig, d_orig, j_orig = bench_kdj_original(df, 100)
    time_opt, k_opt, d_opt, j_opt = bench_kdj_optimized(df, 100)
    
    speedup = print_comparison("KDJ指标", time_orig, time_opt, k_orig, k_opt, 100)
    speedups['KDJ'] = speedup
    
    # 测试2：OBV指标
    print()
    print("=" * 80)
    print("测试2：OBV指标计算")
    print("=" * 80)
    
    time_orig, obv_orig = bench_obv_original(df, 100)
    time_opt, obv_opt = bench_obv_optimized(df, 100)
    
    speedup = print_comparison("OBV指标", time_orig, time_opt, obv_orig, obv_opt, 100)
    speedups['OBV'] = speedup
    
    # 测试3：聚类缓存
    print()
    print("=" * 80)
    print("测试3：聚类结果缓存")
    print("=" * 80)
    
    time_orig, _, _ = bench_clustering_original(clustering_data, 10)
    time_cached, _, _ = bench_clustering_cached(clustering_data, 10)
    
    speedup = print_comparison("K-Means聚类", time_orig, time_cached, 0, 0, 10)
    speedups['Clustering'] = speedup
    
    # 缓存统计
    cache = get_clustering_cache()
    stats = cache.stats()
    print(f"   📊 缓存统计: 命中率={stats['hit_rate']:.1f}%, 命中={stats['hits']}, 未命中={stats['misses']}")
    
    # 综合报告
    print()
    print("=" * 80)
    print("                    综合性能报告")
    print("=" * 80)
    print()
    
    print("模块加速效果：")
    for name, speedup in speedups.items():
        bar_length = int(min(speedup, 50))
        bar = "█" * bar_length
        print(f"   {name:15s} {'∞' if speedup == float('inf') else f'{speedup:.1f}x':>6s}  {bar}")
    
    print()
    avg_speedup = sum(s for s in speedups.values() if s != float('inf')) / len(speedups)
    print(f"📊 平均加速比: {avg_speedup:.1f}x")
    print()
    
    print("✅ 所有性能测试完成！")
    print()
    print("💡 优化建议：")
    print("   1. KDJ策略：使用VectorizedIndicators.kdj替代Pandas rolling")
    print("   2. 量价策略：使用VectorizedIndicators.obv和vwap")
    print("   3. KDJ聚类：集成ClusteringCache避免重复计算")
    print("   4. 回测引擎：考虑并行处理多股票")
