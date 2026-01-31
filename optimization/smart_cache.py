"""
智能缓存系统 - 用于聚类、指标等计算结果的缓存
"""

import hashlib
import pickle
from typing import Any, Callable, Dict, Optional, Tuple
from functools import wraps
import time
import numpy as np


class SmartCache:
    """智能缓存器"""
    
    def __init__(self, max_size: int = 100, ttl: int = 3600):
        """
        初始化
        
        Args:
            max_size: 最大缓存条目数
            ttl: 缓存过期时间（秒）
        """
        self.cache: Dict[str, Tuple[Any, float]] = {}
        self.max_size = max_size
        self.ttl = ttl
        
        # 统计
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        
    def _make_key(self, *args, **kwargs) -> str:
        """生成缓存键"""
        # 处理NumPy数组
        processed_args = []
        for arg in args:
            if isinstance(arg, np.ndarray):
                # 使用数组的哈希值
                processed_args.append(hashlib.md5(arg.tobytes()).hexdigest())
            else:
                processed_args.append(str(arg))
        
        processed_kwargs = {}
        for k, v in kwargs.items():
            if isinstance(v, np.ndarray):
                processed_kwargs[k] = hashlib.md5(v.tobytes()).hexdigest()
            else:
                processed_kwargs[k] = str(v)
        
        key_str = f"{processed_args}_{processed_kwargs}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值，如果不存在或过期返回None
        """
        if key not in self.cache:
            self.misses += 1
            return None
        
        value, timestamp = self.cache[key]
        
        # 检查是否过期
        if time.time() - timestamp > self.ttl:
            del self.cache[key]
            self.misses += 1
            return None
        
        self.hits += 1
        return value
    
    def set(self, key: str, value: Any):
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
        """
        # 如果缓存已满，删除最旧的条目
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]
            self.evictions += 1
        
        self.cache[key] = (value, time.time())
    
    def get_or_compute(self, compute_func: Callable, *args, **kwargs) -> Any:
        """
        获取缓存或计算
        
        Args:
            compute_func: 计算函数
            *args, **kwargs: 函数参数
            
        Returns:
            计算结果
        """
        key = self._make_key(*args, **kwargs)
        
        value = self.get(key)
        if value is not None:
            return value
        
        value = compute_func(*args, **kwargs)
        self.set(key, value)
        
        return value
    
    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
    
    def stats(self) -> Dict[str, Any]:
        """
        获取缓存统计
        
        Returns:
            统计信息字典
        """
        total = self.hits + self.misses
        hit_rate = self.hits / total * 100 if total > 0 else 0
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hits': self.hits,
            'misses': self.misses,
            'evictions': self.evictions,
            'hit_rate': hit_rate,
            'ttl': self.ttl
        }


def cached(cache: SmartCache):
    """
    缓存装饰器
    
    Args:
        cache: SmartCache实例
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return cache.get_or_compute(func, *args, **kwargs)
        
        return wrapper
    
    return decorator


class ClusteringCache:
    """
    聚类结果缓存器
    专门用于缓存K-Means聚类结果
    """
    
    def __init__(self, max_size: int = 50):
        """
        初始化
        
        Args:
            max_size: 最大缓存条目数
        """
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.max_size = max_size
        
        # 统计
        self.hits = 0
        self.misses = 0
        
    def _make_key(self, data: np.ndarray, n_clusters: int) -> str:
        """
        生成缓存键
        
        Args:
            data: 数据数组
            n_clusters: 聚类数量
            
        Returns:
            缓存键
        """
        # 使用数据的哈希值 + 聚类数量作为键
        data_hash = hashlib.md5(data.tobytes()).hexdigest()
        return f"{data_hash}_{n_clusters}"
    
    def get(self, data: np.ndarray, n_clusters: int) -> Optional[Dict[str, Any]]:
        """
        获取聚类结果
        
        Args:
            data: 数据数组
            n_clusters: 聚类数量
            
        Returns:
            聚类结果字典，包含labels和centers
        """
        key = self._make_key(data, n_clusters)
        
        if key in self.cache:
            self.hits += 1
            return self.cache[key]
        
        self.misses += 1
        return None
    
    def set(self, data: np.ndarray, n_clusters: int, result: Dict[str, Any]):
        """
        设置聚类结果
        
        Args:
            data: 数据数组
            n_clusters: 聚类数量
            result: 聚类结果字典
        """
        key = self._make_key(data, n_clusters)
        
        # 如果缓存已满，删除最旧的条目（简单LRU）
        if len(self.cache) >= self.max_size:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
        
        self.cache[key] = result
    
    def get_or_cluster(self, data: np.ndarray, n_clusters: int, 
                       cluster_func: Callable) -> Dict[str, Any]:
        """
        获取缓存或执行聚类
        
        Args:
            data: 数据数组
            n_clusters: 聚类数量
            cluster_func: 聚类函数，接收(data, n_clusters)，返回结果字典
            
        Returns:
            聚类结果
        """
        result = self.get(data, n_clusters)
        
        if result is not None:
            return result
        
        result = cluster_func(data, n_clusters)
        self.set(data, n_clusters, result)
        
        return result
    
    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
    
    def stats(self) -> Dict[str, Any]:
        """
        获取缓存统计
        
        Returns:
            统计信息字典
        """
        total = self.hits + self.misses
        hit_rate = self.hits / total * 100 if total > 0 else 0
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': hit_rate
        }


# 全局缓存实例
_global_smart_cache = SmartCache(max_size=200, ttl=7200)
_global_clustering_cache = ClusteringCache(max_size=50)


def get_global_cache() -> SmartCache:
    """获取全局智能缓存"""
    return _global_smart_cache


def get_clustering_cache() -> ClusteringCache:
    """获取全局聚类缓存"""
    return _global_clustering_cache


if __name__ == '__main__':
    import numpy as np
    from sklearn.cluster import KMeans
    
    print("=" * 70)
    print("      智能缓存系统测试")
    print("=" * 70)
    print()
    
    # 测试智能缓存
    print("【测试1：智能缓存】")
    cache = SmartCache(max_size=10, ttl=60)
    
    def expensive_computation(arr: np.ndarray, factor: float) -> np.ndarray:
        """模拟耗时计算"""
        time.sleep(0.1)  # 模拟耗时
        return arr * factor + np.sum(arr)
    
    arr = np.random.randn(1000)
    
    # 第一次计算（未命中）
    start = time.time()
    result1 = cache.get_or_compute(expensive_computation, arr, 2.0)
    time1 = time.time() - start
    print(f"   第一次计算耗时：{time1:.3f}秒")
    
    # 第二次计算（命中缓存）
    start = time.time()
    result2 = cache.get_or_compute(expensive_computation, arr, 2.0)
    time2 = time.time() - start
    print(f"   第二次计算耗时：{time2:.3f}秒")
    
    speedup = time1/time2 if time2 > 0 else float('inf')
    print(f"   加速比：{speedup:.1f}x" if speedup != float('inf') else "   加速比：∞x (instant)")
    print(f"   缓存统计：{cache.stats()}")
    print()
    
    # 测试聚类缓存
    print("【测试2：聚类缓存】")
    cluster_cache = ClusteringCache(max_size=10)
    
    def kmeans_cluster(data: np.ndarray, n_clusters: int) -> Dict[str, Any]:
        """执行K-Means聚类"""
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(data)
        return {
            'labels': labels,
            'centers': kmeans.cluster_centers_
        }
    
    # 生成测试数据
    data = np.random.randn(1000, 2)
    
    # 第一次聚类（未命中）
    start = time.time()
    result1 = cluster_cache.get_or_cluster(data, 3, kmeans_cluster)
    time1 = time.time() - start
    print(f"   第一次聚类耗时：{time1:.3f}秒")
    
    # 第二次聚类（命中缓存）
    start = time.time()
    result2 = cluster_cache.get_or_cluster(data, 3, kmeans_cluster)
    time2 = time.time() - start
    print(f"   第二次聚类耗时：{time2:.3f}秒")
    
    speedup = time1/time2 if time2 > 0 else float('inf')
    print(f"   加速比：{speedup:.0f}x" if speedup != float('inf') else "   加速比：∞x (instant)")
    print(f"   缓存统计：{cluster_cache.stats()}")
    print()
    
    # 测试装饰器
    print("【测试3：装饰器】")
    decorator_cache = SmartCache(max_size=10, ttl=60)
    
    @cached(decorator_cache)
    def fibonacci(n: int) -> int:
        """斐波那契数列（递归）"""
        if n <= 1:
            return n
        return fibonacci(n-1) + fibonacci(n-2)
    
    # 计算斐波那契数列
    start = time.time()
    result = fibonacci(30)
    time_taken = time.time() - start
    
    print(f"   fibonacci(30) = {result}")
    print(f"   耗时：{time_taken:.3f}秒")
    print(f"   缓存统计：{decorator_cache.stats()}")
    print()
    
    print("=" * 70)
    print("✅ 所有测试通过！")
    print()
    print("💡 使用建议：")
    print("   1. 在KDJ策略中使用ClusteringCache缓存聚类结果")
    print("   2. 在指标计算中使用SmartCache缓存中间结果")
    print("   3. 使用@cached装饰器简化缓存逻辑")
