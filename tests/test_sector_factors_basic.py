import pandas as pd

from astock_engine.data.mock_data import MockDataManager
from astock_engine.data.sector_universe import get_symbol_tags
from astock_engine.factors.sector_factors import apply_sector_factors


def test_sector_factors_add_industry_and_theme_columns():
    manager = MockDataManager(seed=42)
    symbols = ["300750.SZ", "600519.SH"]

    raw = manager.get_stock_data(
        symbols=symbols,
        start_date="2024-01-02",
        end_date="2024-01-10",
    )

    data = apply_sector_factors(raw)

    for symbol in symbols:
        df = data[symbol]
        assert isinstance(df.index, pd.DatetimeIndex)
        assert "industry" in df.columns
        assert "primary_theme" in df.columns
        assert "industry_ret" in df.columns
        assert "industry_volume" in df.columns
        assert "theme_ret" in df.columns
        assert "theme_volume" in df.columns

        tags = get_symbol_tags(symbol)
        # 标签应正确回填
        assert df["industry"].iloc[0] == tags["industry"]
        if tags["themes"]:
            assert df["primary_theme"].iloc[0] == tags["themes"][0]

        # 至少一部分行应有非空行业/题材加权指标
        assert df["industry_ret"].notna().sum() > 0
        assert df["industry_volume"].notna().sum() > 0
        assert df["theme_ret"].notna().sum() > 0
        assert df["theme_volume"].notna().sum() > 0
