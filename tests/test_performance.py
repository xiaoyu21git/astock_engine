#!/usr/bin/env python3
"""性能对比测试：纯Python vs C++扩展"""
import timeit
import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

def python_sma(prices, window):
    """纯Python实现的SMA"""
    result = np.full(len(prices), np.nan)
    for i in range(window - 1, len(prices)):
        result[i] = np.mean(prices[i-window+1:i+1])
    return result

def run_performance_comparison():
    """运行性能对比"""
    print("性能对比测试")
    print("=" * 60)
    
    # 生成测试数据
    data_sizes = [100, 1000, 10000, 50000]
    window = 20
    
    try:
        import fast_factors
        cpp_available = True
    except ImportError:
        cpp_available = False
        print("⚠️  C++扩展不可用，只测试Python版本")
    
    for size in data_sizes:
        data = np.random.randn(size) + 100
        
        # 测试Python版本
        py_time = timeit.timeit(
            lambda: python_sma(data, window),
            number=10 if size <= 10000 else 3
        )
        
        if cpp_available:
            # 测试C++版本
            cpp_time = timeit.timeit(
                lambda: fast_factors.fast_sma(data, window),
                number=10 if size <= 10000 else 3
            )
            
            speedup = py_time / cpp_time if cpp_time > 0 else float('inf')
            
            print(f"数据量: {size:6d} | Python: {py_time:.4f}s | "
                  f"C++: {cpp_time:.4f}s | 加速比: {speedup:.1f}x")
        else:
            print(f"数据量: {size:6d} | Python: {py_time:.4f}s | C++: N/A")
    
    print("=" * 60)

if __name__ == '__main__':
    run_performance_comparison()