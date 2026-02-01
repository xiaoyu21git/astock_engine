import pandas as pd

from astock_engine.data.mock_data import MockDataManager
from astock_engine.factors.sentiment_policy_factors import (
    apply_simple_sentiment,
    apply_policy_factor,
)
from astock_engine.data.sector_universe import get_symbol_tags


def _get_daily_data(symbols):
    manager = MockDataManager(seed=42)
    return manager.get_stock_data(
        symbols=symbols,
        start_date="2024-01-02",
        end_date="2024-01-10",
    )


def test_apply_simple_sentiment_adds_market_sentiment():
    symbols = ["300750.SZ", "600519.SH"]
    data = _get_daily_data(symbols)

    data = apply_simple_sentiment(data)

    for symbol in symbols:
        df = data[symbol]
        assert "market_sentiment" in df.columns
        # 至少有部分交易日有非零情绪分数
        assert df["market_sentiment"].notna().sum() > 0


def test_apply_policy_factor_adds_policy_score():
    # 选取包含新能源和白酒题材的股票，确保能命中示例政策事件
    symbols = ["300750.SZ", "600519.SH"]
    data = _get_daily_data(symbols)

    data = apply_policy_factor(data)

    for symbol in symbols:
        df = data[symbol]
        tags = get_symbol_tags(symbol)
        assert "policy_score" in df.columns
        # 有对应题材的股票，至少应该有一天 policy_score 非零
        if tags["themes"]:
            assert (df["policy_score"].abs() > 0).any()
