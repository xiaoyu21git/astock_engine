import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional
from .portfolio import Portfolio
from .performance import PerformanceAnalyzer

class BacktestEngine:
    """回测引擎"""
    
    def __init__(self, initial_capital: float = 1000000):
        self.initial_capital = initial_capital
        self.portfolio = Portfolio(initial_capital)
        self.analyzer = PerformanceAnalyzer()
        self.results = {}
        
    def run(self, strategy, data: Dict[str, pd.DataFrame], 
           start_date: str, end_date: str) -> Dict:
        """
        运行回测
        
        Args:
            strategy: 策略实例
            data: 股票数据字典 {symbol: DataFrame}
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            回测结果字典
        """
        dates = pd.date_range(start_date, end_date, freq='B')
        
        for current_date in dates:
            date_str = current_date.strftime('%Y-%m-%d')
            
            # 获取当日数据
            daily_data = {}
            for symbol, df in data.items():
                if date_str in df.index:
                    daily_data[symbol] = df.loc[date_str]
            
            if not daily_data:
                continue
                
            # 生成信号
            signals = strategy.generate_signals(daily_data)
            
            # 更新持仓
            self.portfolio.update(signals, daily_data, date_str)
            
            # 记录净值
            self.portfolio.record_equity(date_str)
        
        # 计算绩效指标
        results = self.analyzer.analyze(self.portfolio.equity_curve)
        self.results = results
        
        return results
    
    def get_report(self) -> pd.DataFrame:
        """生成回测报告"""
        return self.analyzer.generate_report(self.results)