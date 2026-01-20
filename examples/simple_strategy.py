import pandas as pd
import numpy as np
from quant_engine import BacktestEngine
from quant_engine.strategies import BaseStrategy
from quant_engine.factors import TechnicalFactors

class MovingAverageCrossover(BaseStrategy):
    """双均线策略"""
    
    def __init__(self, short_window=20, long_window=50):
        super().__init__("MovingAverageCrossover")
        self.short_window = short_window
        self.long_window = long_window
        self.factors = TechnicalFactors()
        
    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        signals = []
        
        for symbol in data['symbol'].unique():
            symbol_data = data[data['symbol'] == symbol]
            
            # 计算技术指标
            sma_short = self.factors.sma(symbol_data['close'], self.short_window)
            sma_long = self.factors.sma(symbol_data['close'], self.long_window)
            
            # 生成交易信号
            if sma_short.iloc[-1] > sma_long.iloc[-1] and sma_short.iloc[-2] <= sma_long.iloc[-2]:
                signals.append(Signal(
                    symbol=symbol,
                    direction=1,
                    strength=1.0,
                    timestamp=data.index[-1],
                    reason="金叉买入"
                ))
            elif sma_short.iloc[-1] < sma_long.iloc[-1] and sma_short.iloc[-2] >= sma_long.iloc[-2]:
                signals.append(Signal(
                    symbol=symbol,
                    direction=-1,
                    strength=1.0,
                    timestamp=data.index[-1],
                    reason="死叉卖出"
                ))
        
        return signals

def main():
    # 加载数据
    data = pd.read_csv('stock_data.csv', index_col='date', parse_dates=True)
    
    # 创建策略实例
    strategy = MovingAverageCrossover(short_window=10, long_window=30)
    
    # 创建回测引擎
    engine = BacktestEngine(initial_capital=1000000)
    
    # 运行回测
    results = engine.run(
        strategy=strategy,
        data={'000001.SZ': data},
        start_date='2020-01-01',
        end_date='2023-12-31'
    )
    
    # 输出结果
    print("回测结果:")
    print(f"年化收益率: {results['annual_return']:.2%}")
    print(f"夏普比率: {results['sharpe_ratio']:.2f}")
    print(f"最大回撤: {results['max_drawdown']:.2%}")
    
    # 生成报告
    report = engine.get_report()
    report.to_csv('backtest_report.csv')

if __name__ == "__main__":
    main()