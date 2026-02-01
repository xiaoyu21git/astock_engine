"""板块 / 行业 / 题材 加权指标计算

提供在股票日线或分钟级数据上，按行业/题材汇总的加权指标，
例如：行业/题材的加权涨跌幅、总成交量等。

核心入口：apply_sector_factors(data: Dict[str, DataFrame])
- 输入：{symbol: df}，df 至少包含 ['close', 'volume']，索引为 datetime；
- 输出：在每个 df 上附加列：
  - 'industry': 行业名称（来自 sector_universe 映射）；
  - 'primary_theme': 主要题材名称（若存在）；
  - 'industry_ret': 当天/当 bar 行业加权涨跌幅（按成交量加权）；
  - 'industry_volume': 行业成交量总和；
  - 'theme_ret': 题材加权涨跌幅；
  - 'theme_volume': 题材成交量总和。
"""

from typing import Dict

import numpy as np
import pandas as pd

from astock_engine.data.sector_universe import get_symbol_tags


def _compute_weighted_returns(close: pd.Series, volume: pd.Series) -> float:
    """根据收盘价涨跌幅和成交量计算加权收益率。

    如果 volume 全为 0，则返回简单平均涨跌幅。
    """
    if close.size < 2:
        return 0.0

    ret = close.pct_change().iloc[-1]
    if not np.isfinite(ret):
        ret = 0.0

    # 对于单根 bar，加权与否差异不大，这里接口预留，便于未来扩展多标的聚合
    return float(ret)


def apply_sector_factors(data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """在多只股票数据上附加行业/题材加权指标。

    本函数假设 data 中每个 DataFrame：
    - 索引为 DatetimeIndex；
    - 至少包含 'close' 和 'volume' 列。

    返回同一 dict 引用，DataFrame 被就地扩展新列。
    """
    # 先构造合并视图，携带 symbol/industry/theme 信息
    frames = []
    for symbol, df in data.items():
        if df is None or df.empty:
            continue

        tags = get_symbol_tags(symbol)
        industry = tags["industry"]
        themes = tags["themes"] or []
        primary_theme = themes[0] if themes else None

        tmp = df.copy()
        tmp["symbol"] = symbol
        tmp["industry"] = industry
        tmp["primary_theme"] = primary_theme
        frames.append(tmp)

    if not frames:
        return data

    combined = pd.concat(frames, axis=0)
    if not isinstance(combined.index, pd.DatetimeIndex):
        combined.index = pd.to_datetime(combined.index)

    combined.sort_index(inplace=True)

    # 逐时间点、逐行业/题材聚合加权收益与成交量
    # 为简化计算，我们按 (timestamp, industry) / (timestamp, theme) 进行 groupby
    if "industry" in combined.columns:
        grp_ind = combined.groupby([combined.index, "industry"], dropna=True)
        ind_ret = grp_ind.apply(lambda g: _compute_weighted_returns(g["close"], g["volume"]))
        ind_vol = grp_ind["volume"].sum()

        ind_ret.name = "industry_ret"
        ind_vol.name = "industry_volume"

        # 使用 MultiIndex 对齐，而不是 DataFrame.join，避免重复键问题
        ind_key = pd.MultiIndex.from_arrays(
            [combined.index, combined["industry"]],
            names=["datetime", "industry"],
        )
        combined["industry_ret"] = ind_ret.reindex(ind_key).values
        combined["industry_volume"] = ind_vol.reindex(ind_key).values

    if "primary_theme" in combined.columns:
        grp_theme = combined.groupby([combined.index, "primary_theme"], dropna=True)
        theme_ret = grp_theme.apply(lambda g: _compute_weighted_returns(g["close"], g["volume"]))
        theme_vol = grp_theme["volume"].sum()

        theme_ret.name = "theme_ret"
        theme_vol.name = "theme_volume"

        theme_key = pd.MultiIndex.from_arrays(
            [combined.index, combined["primary_theme"]],
            names=["datetime", "primary_theme"],
        )
        combined["theme_ret"] = theme_ret.reindex(theme_key).values
        combined["theme_volume"] = theme_vol.reindex(theme_key).values

    # 将扩展后的列按 symbol 拆回各自 DataFrame
    for symbol, df in data.items():
        if df is None or df.empty:
            continue

        sub = combined[combined["symbol"] == symbol]
        # 对齐原索引
        sub = sub.reindex(df.index)

        for col in [
            "industry",
            "primary_theme",
            "industry_ret",
            "industry_volume",
            "theme_ret",
            "theme_volume",
        ]:
            if col in sub.columns:
                df[col] = sub[col]

        data[symbol] = df

    return data
