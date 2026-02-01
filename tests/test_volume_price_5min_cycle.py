import pandas as pd

from astock_engine.data.mock_data import MockDataManager
from astock_engine.strategies.volume_price_strategy import VolumePriceStrategy


def test_volume_price_5min_cycle_indicators_on_minute_data():
    """验证 VolumePriceStrategy 在分钟级数据上能正确计算 5 分钟周期线指标。

    要求：
    - 生成 1 分钟数据并传入 VolumePriceStrategy.calculate_indicators；
    - 产出的 DataFrame 中包含 cycle_5m_resistance / support / trend 等列；
    - 标记列 is_near_5m_resistance / is_near_5m_support / is_rebound_from_5m_support 存在且为布尔型。
    """

    manager = MockDataManager(seed=123)
    symbols = ["600519.SH"]

    data = manager.get_stock_data(
        symbols=symbols,
        start_date="2024-01-02",
        end_date="2024-01-05",
        frequency="1min",
    )

    strat = VolumePriceStrategy(params={"mode": "balanced"})
    data_with_ind = strat.calculate_indicators(data)

    df = data_with_ind[symbols[0]]

    # 应为分钟级时间索引
    assert isinstance(df.index, pd.DatetimeIndex)
    assert not df.empty

    # 检查 5 分钟周期线相关列是否存在
    for col in [
        "cycle_5m_resistance",
        "cycle_5m_support",
        "cycle_5m_trend",
        "is_near_5m_resistance",
        "is_near_5m_support",
        "is_rebound_from_5m_support",
    ]:
        assert col in df.columns

    # 至少有部分行应当有非空的 5 分钟周期线值
    assert df["cycle_5m_resistance"].notna().sum() > 0
    assert df["cycle_5m_support"].notna().sum() > 0

    # 标记列应为布尔类型或可视作布尔
    assert set(df["is_near_5m_resistance"].dropna().unique()).issubset({True, False})
    assert set(df["is_near_5m_support"].dropna().unique()).issubset({True, False})
    assert set(df["is_rebound_from_5m_support"].dropna().unique()).issubset({True, False})
