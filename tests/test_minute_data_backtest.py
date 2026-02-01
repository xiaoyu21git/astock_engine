import pandas as pd

from astock_engine.data.mock_data import MockDataManager
from astock_engine.backtest.backtest_engine import BacktestEngine, BacktestConfig
from astock_engine.strategies.base_strategy import BaseStrategy, Signal


class DummyIntradayStrategy(BaseStrategy):
    """一个用于验证分钟级数据管线的极简策略。

    逻辑：
    - 在每个时间点，对每个 symbol 取最新一条 K 线；
    - 若仍有现金，则按市价买入少量仓位，用于验证回测引擎在分钟级数据下能正常运行。
    """

    def __init__(self):
        super().__init__(name="DummyIntradayStrategy", params={"initial_capital": 100000})

    def generate_signals(self, data: pd.DataFrame, context=None):
        if data is None or data.empty:
            return []

        # 取每个 symbol 最新一条记录
        last_rows = data.groupby("symbol").tail(1)
        current_time = context.get("date") if context else None

        signals = []
        for symbol, group in last_rows.groupby("symbol"):
            row = group.iloc[0]
            price = float(row["close"])

            # 如果还有现金，就简单下一个买入信号
            if self.cash > 0 and price > 0:
                signals.append(
                    Signal(
                        symbol=symbol,
                        direction=1,
                        strength=0.5,
                        timestamp=current_time,
                        price=price,
                        reason="dummy_intraday_buy",
                    )
                )

        return signals


def test_minute_mock_data_and_backtest_runs():
    """验证：
    1. MockDataManager 能生成分钟级 K 线数据；
    2. BacktestEngine 能在分钟级数据上完整跑完一段回测。
    """

    manager = MockDataManager(seed=123)
    symbols = ["600519.SH"]

    data = manager.get_stock_data(
        symbols=symbols,
        start_date="2024-01-01",
        end_date="2024-01-05",
        frequency="1min",
    )

    assert symbols[0] in data
    df = data[symbols[0]]

    # 分钟级数据应为 DatetimeIndex，且包含非零时间部分
    assert isinstance(df.index, pd.DatetimeIndex)
    assert not df.empty
    assert any((df.index.hour != 0) | (df.index.minute != 0))

    # 使用极简策略和 BacktestEngine 在分钟级数据上跑一遍
    engine = BacktestEngine(config=BacktestConfig(initial_capital=100000), enable_risk_control=False)
    strategy = DummyIntradayStrategy()

    metrics = engine.run(
        strategy=strategy,
        data=data,
        start_date="2024-01-01",
        end_date="2024-01-05",
    )

    # 至少应该有若干交易时间点，并产生非零最终权益
    assert metrics.trading_days > 0
    assert metrics.final_value > 0
