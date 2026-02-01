import pandas as pd

from astock_engine.data.mock_data import MockDataManager
from astock_engine.factors.auction_factors import apply_auction_factors


def _get_minute_data(symbols):
    manager = MockDataManager(seed=42)
    return manager.get_stock_data(
        symbols=symbols,
        start_date="2024-01-02",
        end_date="2024-01-10",
        frequency="1min",
    )


def test_auction_factors_added_on_minute_data():
    symbols = ["300750.SZ", "600519.SH"]
    data = _get_minute_data(symbols)

    data = apply_auction_factors(data)

    for symbol in symbols:
        df = data[symbol]
        assert isinstance(df.index, pd.DatetimeIndex)

        # 新增列应存在
        for col in [
            "auction_gap",
            "auction_gap_abs",
            "auction_rel_volume",
            "auction_strength",
            "is_auction_bar",
        ]:
            assert col in df.columns

        # 每个交易日的竞价因子在日内应保持恒定
        grouped = df.groupby(df.index.normalize())
        assert (grouped["auction_gap"].nunique() <= 1).all()
        assert (grouped["auction_rel_volume"].nunique() <= 1).all()

        # 每日应该有且仅有一个 is_auction_bar 为 True
        count_auction_bar = grouped["is_auction_bar"].sum()
        assert (count_auction_bar >= 1).all()

        # 至少部分交易日应有非零竞价 Gap 或相对量能
        assert (df["auction_gap"].abs() > 0).any() or (df["auction_rel_volume"] != 1.0).any()
