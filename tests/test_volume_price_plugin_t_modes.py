from datetime import datetime, timedelta

import pandas as pd

from astock_engine.data.mock_data import MockDataManager
from astock_engine.backtest.backtest_engine import BacktestEngine, BacktestConfig
from astock_engine.strategies.plugins.volume_price.strategy import VolumePricePluginStrategy


def _get_intraday_data(symbol: str, start: str, end: str):
    manager = MockDataManager(seed=123)
    data = manager.get_stock_data(
        symbols=[symbol],
        start_date=start,
        end_date=end,
        frequency="1min",
    )
    return data[symbol]


def test_volume_price_plugin_t0_closes_positions_by_end_of_day():
    """T+0 模式下，日内持仓应在收盘前全部平掉。"""

    symbol = "600519.SH"
    df = _get_intraday_data(symbol, "2024-01-02", "2024-01-02")

    # 基本回测配置
    config = BacktestConfig(initial_capital=100000)
    engine = BacktestEngine(config=config, enable_risk_control=False)

    strat = VolumePricePluginStrategy(params={"t_mode": "T0", "initial_capital": 100000})

    # 在回测引擎中人为设定一笔持仓，从当日首根分钟 K 线开始持有
    first_ts = df.index[0]
    first_price = float(df.iloc[0]["close"])
    engine.positions[symbol] = {
        "quantity": 100,
        "entry_price": first_price,
        "entry_time": first_ts.to_pydatetime(),
        "current_price": first_price,
    }
    engine.cash -= first_price * 100

    # 将数据包装成 BacktestEngine 需要的 {symbol: df} 结构
    data_dict = {symbol: df}

    engine.run(
        strategy=strat,
        data=data_dict,
        start_date="2024-01-02",
        end_date="2024-01-02",
    )

    # T+0: 日终不应再有持仓
    assert len(engine.positions) == 0


def test_volume_price_plugin_t1_closes_positions_next_day():
    """T+1 模式下，跨日持仓应在次日尽快平掉。"""

    symbol = "600519.SH"
    # 仅生成第二天的分钟数据，用于触发 T+1 平仓
    df = _get_intraday_data(symbol, "2024-01-02", "2024-01-02")

    config = BacktestConfig(initial_capital=100000)
    engine = BacktestEngine(config=config, enable_risk_control=False)

    strat = VolumePricePluginStrategy(params={"t_mode": "T1", "initial_capital": 100000})

    # 在回测引擎中人为设定一笔在前一交易日建仓的持仓
    first_ts_today = df.index[0]
    # 构造前一日的建仓时间
    entry_time = (first_ts_today - timedelta(days=1)).to_pydatetime()
    first_price_today = float(df.iloc[0]["close"])

    engine.positions[symbol] = {
        "quantity": 100,
        "entry_price": first_price_today,
        "entry_time": entry_time,
        "current_price": first_price_today,
    }
    engine.cash -= first_price_today * 100

    data_dict = {symbol: df}

    engine.run(
        strategy=strat,
        data=data_dict,
        start_date="2024-01-02",
        end_date="2024-01-02",
    )

    # T+1: 经过一个交易日后，不应再有跨日持仓
    assert len(engine.positions) == 0
