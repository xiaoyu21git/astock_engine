#!/usr/bin/env python3
"""综合测试套件"""
import pytest
import numpy as np
import pandas as pd
import tempfile
import shutil
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

class TestQuantEngine:
    """量化引擎综合测试"""
    
    @pytest.fixture
    def sample_data(self):
        """生成测试数据"""
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        return pd.DataFrame({
            'open': np.random.randn(100).cumsum() + 100,
            'high': np.random.randn(100).cumsum() + 105,
            'low': np.random.randn(100).cumsum() + 95,
            'close': np.random.randn(100).cumsum() + 100,
            'volume': np.random.randint(1000, 10000, 100)
        }, index=dates)
    
    @pytest.mark.cpp
    def test_factors_performance(self):
        """测试因子计算性能"""
        pytest.importorskip("fast_factors")
        import fast_factors
        
        # 生成大数据测试性能
        large_data = np.random.randn(10000) + 100
        
        import time
        start = time.time()
        result = fast_factors.fast_sma(large_data, 20)
        elapsed = time.time() - start
        
        print(f"C++ SMA计算耗时: {elapsed:.4f}秒")
        assert elapsed < 0.1  # 应该很快
    
    @pytest.mark.integration
    def test_backtest_integration(self):
        """测试回测集成"""
        # 这里可以测试Python与C++的集成
        pass
    
    @pytest.mark.slow
    def test_strategy_workflow(self):
        """测试完整策略工作流"""
        from base_strategy import BaseStrategy
        
        class DummyStrategy(BaseStrategy):
            def generate_signals(self, data):
                # 简单策略：价格上涨时买入
                signals = []
                for symbol in data['symbol'].unique():
                    symbol_data = data[data['symbol'] == symbol]
                    if len(symbol_data) > 1:
                        if symbol_data['close'].iloc[-1] > symbol_data['close'].iloc[-2]:
                            signals.append({
                                'symbol': symbol,
                                'action': 'buy',
                                'strength': 1.0
                            })
                return signals
        
        strategy = DummyStrategy("Dummy")
        assert strategy.name == "Dummy"

if __name__ == '__main__':
    pytest.main([__file__, '-v'])