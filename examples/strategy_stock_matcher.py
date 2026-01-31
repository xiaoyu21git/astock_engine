#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
策略-股票智能匹配系统
根据股票特征自动推荐最合适的策略
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from astock_engine.data.data_provider import DataManager
import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.WARNING)

print("=" * 70)
print("            策略-股票智能匹配系统")
print("=" * 70)
print()

class StockCharacterizer:
    """股票特征分析器"""
    
    @staticmethod
    def analyze(df: pd.DataFrame) -> dict:
        """
        分析股票特征
        
        Returns:
            {
                'volatility': 波动率,
                'trend_strength': 趋势强度,
                'oscillation': 震荡性,
                'amplitude': 振幅,
                'momentum': 动量,
                'mean_reversion': 均值回归性,
            }
        """
        close = df['close']
        high = df['high']
        low = df['low']
        
        # 1. 波动率（年化标准差）
        volatility = close.pct_change().std() * np.sqrt(252)
        
        # 2. 趋势强度（线性回归R²）
        x = np.arange(len(close))
        y = close.values
        coeffs = np.polyfit(x, y, 1)
        y_pred = coeffs[0] * x + coeffs[1]
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
        trend_strength = abs(r_squared)  # 0-1，越大越有趋势
        
        # 3. 震荡性（趋势强度的反面）
        oscillation = 1 - trend_strength
        
        # 4. 振幅（最大最小差/均值）
        amplitude = (high.max() - low.min()) / close.mean()
        
        # 5. 动量（近期涨跌幅）
        momentum = (close.iloc[-20:].mean() - close.iloc[-60:-20].mean()) / close.iloc[-60:-20].mean()
        
        # 6. 均值回归性（价格偏离均线后回归的频率）
        ma20 = close.rolling(20).mean()
        deviations = (close - ma20) / ma20
        # 计算穿越均线的次数
        crossings = (deviations.shift(1) * deviations < 0).sum()
        mean_reversion = crossings / len(close)  # 回归频率
        
        return {
            'volatility': volatility,
            'trend_strength': trend_strength,
            'oscillation': oscillation,
            'amplitude': amplitude,
            'momentum': momentum,
            'mean_reversion': mean_reversion,
        }


class StrategyMatcher:
    """策略匹配器"""
    
    # 策略适用条件定义
    STRATEGY_PROFILES = {
        'KDJ': {
            'name': 'KDJ随机指标',
            'type': '均值回归',
            'conditions': {
                'oscillation': (0.6, 1.0),      # 震荡性 > 0.6
                'mean_reversion': (0.08, 1.0),  # 回归频率 > 8%
                'volatility': (0.2, 0.5),       # 波动率适中
            },
            'score_weights': {
                'oscillation': 0.4,
                'mean_reversion': 0.3,
                'volatility': 0.3,
            }
        },
        'MACD': {
            'name': 'MACD趋势策略',
            'type': '趋势跟随',
            'conditions': {
                'trend_strength': (0.5, 1.0),   # 趋势强度 > 0.5
                'momentum': (0.0, 1.0),          # 正向动量
                'volatility': (0.1, 0.4),       # 波动率不太高
            },
            'score_weights': {
                'trend_strength': 0.5,
                'momentum': 0.3,
                'volatility': 0.2,
            }
        },
        'RSI': {
            'name': 'RSI超买超卖',
            'type': '均值回归',
            'conditions': {
                'oscillation': (0.5, 1.0),
                'volatility': (0.25, 0.6),      # 高波动
                'mean_reversion': (0.06, 1.0),
            },
            'score_weights': {
                'oscillation': 0.3,
                'volatility': 0.4,
                'mean_reversion': 0.3,
            }
        },
        'BollingerBands': {
            'name': '布林带均值回归',
            'type': '均值回归',
            'conditions': {
                'mean_reversion': (0.08, 1.0),
                'volatility': (0.2, 0.5),
                'oscillation': (0.4, 1.0),
            },
            'score_weights': {
                'mean_reversion': 0.4,
                'volatility': 0.3,
                'oscillation': 0.3,
            }
        },
        'MA': {
            'name': '均线交叉',
            'type': '趋势跟随',
            'conditions': {
                'trend_strength': (0.4, 1.0),
                'volatility': (0.1, 0.35),      # 低波动
            },
            'score_weights': {
                'trend_strength': 0.6,
                'volatility': 0.4,
            }
        }
    }
    
    @classmethod
    def match(cls, features: dict, top_n: int = 3) -> list:
        """
        为股票特征匹配最合适的策略
        
        Args:
            features: 股票特征字典
            top_n: 返回前N个最匹配的策略
            
        Returns:
            [(strategy_name, score, reason), ...]
        """
        results = []
        
        for strategy_name, profile in cls.STRATEGY_PROFILES.items():
            score = 0
            reasons = []
            max_score = 0
            
            # 计算匹配分数
            for feature_name, weight in profile['score_weights'].items():
                feature_value = features.get(feature_name, 0)
                
                # 检查是否在条件范围内
                if feature_name in profile['conditions']:
                    min_val, max_val = profile['conditions'][feature_name]
                    if min_val <= feature_value <= max_val:
                        # 在范围内，加分
                        # 归一化到0-1
                        normalized = (feature_value - min_val) / (max_val - min_val) if max_val > min_val else 1.0
                        feature_score = normalized * weight * 100
                        score += feature_score
                        
                        if normalized > 0.7:  # 非常匹配
                            reasons.append(f"{feature_name}非常适合")
                    else:
                        # 不在范围内，扣分
                        reasons.append(f"{feature_name}不符合")
                
                max_score += weight * 100
            
            # 计算匹配度百分比
            match_pct = (score / max_score * 100) if max_score > 0 else 0
            
            results.append({
                'strategy': strategy_name,
                'name': profile['name'],
                'type': profile['type'],
                'score': match_pct,
                'reasons': reasons
            })
        
        # 按分数排序
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_n]


def main():
    # 测试股票列表
    test_stocks = {
        '300750.SZ': '宁德时代',
        '000333.SZ': '美的集团',
        '600519.SH': '贵州茅台',
        '601398.SH': '工商银行',
    }
    
    print("📊 分析股票特征并推荐策略...\n")
    
    data_manager = DataManager()
    
    for symbol, name in test_stocks.items():
        try:
            print("=" * 70)
            print(f"【{name}】({symbol})")
            print("=" * 70)
            
            # 获取数据
            data = data_manager.get_stock_data(
                symbols=[symbol],
                start_date='2024-02-01',
                end_date='2026-01-31'
            )
            
            if symbol not in data or data[symbol].empty:
                print("⚠️ 数据获取失败\n")
                continue
            
            df = data[symbol]
            
            # 分析特征
            features = StockCharacterizer.analyze(df)
            
            print("\n📈 股票特征:")
            print(f"   波动率:       {features['volatility']:.2%}")
            print(f"   趋势强度:     {features['trend_strength']:.2f} (0-1)")
            print(f"   震荡性:       {features['oscillation']:.2f} (0-1)")
            print(f"   振幅:         {features['amplitude']:.2%}")
            print(f"   动量:         {features['momentum']:.2%}")
            print(f"   均值回归性:   {features['mean_reversion']:.2%}")
            
            # 匹配策略
            matches = StrategyMatcher.match(features, top_n=3)
            
            print("\n🎯 推荐策略（按匹配度排序）:")
            for i, match in enumerate(matches, 1):
                emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
                print(f"\n   {emoji} {match['name']} ({match['type']})")
                print(f"      匹配度: {match['score']:.1f}%")
                if match['reasons']:
                    print(f"      原因: {', '.join(match['reasons'][:3])}")
            
            # 判断类型
            print("\n💡 建议:")
            if features['trend_strength'] > 0.6:
                print("   ✅ 强趋势股，优先使用趋势跟随策略（MACD/MA）")
            elif features['oscillation'] > 0.6:
                print("   ✅ 震荡股，优先使用均值回归策略（KDJ/RSI/布林带）")
            else:
                print("   ⚠️ 特征不明显，建议观望或使用组合策略")
            
            print()
            
        except Exception as e:
            print(f"❌ 分析失败: {e}\n")
            continue
    
    print("=" * 70)
    print("💡 使用建议")
    print("=" * 70)
    print("""
1. 选股流程:
   ① 分析股票特征（震荡性/趋势性）
   ② 根据特征选择策略类型
   ③ 只对匹配的股票应用对应策略

2. 策略分类:
   • 均值回归策略（KDJ/RSI/布林带）→ 震荡股
   • 趋势跟随策略（MACD/MA）→ 趋势股

3. 避免错误:
   ❌ 不要在趋势股上用KDJ
   ❌ 不要在震荡股上用MACD
   ✅ 策略-股票特征匹配是关键

4. 实战应用:
   • 先用本工具分析待选股票
   • 根据推荐结果选择策略
   • 在匹配度>70%的股票上应用策略
    """)


if __name__ == '__main__':
    main()
