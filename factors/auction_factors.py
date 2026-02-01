"""竞价因子

基于每日开盘前后的价格与量能特征，构造一组简单的竞价因子，
在分钟级或日线数据上均可使用。

核心入口：apply_auction_factors(data: Dict[str, DataFrame])
- 输入：{symbol: df}，df 至少包含 ['open','close','volume'] 列；索引为日期或精确到分钟的 DatetimeIndex；
- 输出：在每个 df 上附加列：
  - 'auction_gap'          : 当日开盘价相对于前一交易日收盘价的相对涨跌幅；
  - 'auction_gap_abs'      : 绝对涨跌幅；
  - 'auction_rel_volume'   : 当日“竞价/开盘”成交量相对于过去若干日同时间段成交量中位数的比例；
  - 'auction_strength'     : 简化的综合强度评分 = auction_gap * auction_rel_volume；
  - 'is_auction_bar'       : 是否为当日的首个 bar（分钟级则为首个分钟，日线则整日为 True）。

设计原则：
- 日线数据下，视 'open' 为竞价+开盘价，'volume' 为当日总量；
- 分钟级数据下，视每日首个 bar 的 open/volume 为竞价+开盘的近似；
- 因子值按“日”为粒度，在当日所有 bar 上保持不变，便于日内策略在任意时刻访问同一竞价信息。
"""

from typing import Dict

import numpy as np
import pandas as pd


def apply_auction_factors(data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """在多只股票数据上附加竞价相关因子。

    本函数既适用于日线，也适用于分钟级数据：
    - 对日线：每个交易日只有一个 bar，视为竞价+全天；
    - 对分钟级：以每日首个 bar 的 open/volume 作为竞价近似。
    """

    for symbol, df in data.items():
        if df is None or df.empty:
            continue

        # 保留原始索引顺序
        original_index = df.index

        # 工作副本，确保为 DatetimeIndex
        work = df.copy()
        if not isinstance(work.index, pd.DatetimeIndex):
            work.index = pd.to_datetime(work.index)

        work.sort_index(inplace=True)

        required_cols = {"open", "close"}
        if not required_cols.issubset(set(work.columns)):
            # 缺少必要价格列时，不计算竞价因子
            data[symbol] = work.reindex(original_index)
            continue

        # 归一化为“交易日”键
        work["_date"] = work.index.normalize()

        # 每日首个 bar 的 open 与 volume 视作竞价信息
        daily_first = work.groupby("_date").agg({
            "open": "first",
            "volume": "first" if "volume" in work.columns else "sum",
        })
        daily_first.rename(columns={"open": "auction_open", "volume": "auction_volume"}, inplace=True)

        # 前一交易日收盘价
        daily_last_close = work.groupby("_date")["close"].last()
        prev_close = daily_last_close.shift(1)

        daily = pd.concat([daily_first, prev_close.rename("prev_close")], axis=1)

        # 竞价涨跌幅
        prev = daily["prev_close"].to_numpy(dtype=float)
        ao = daily["auction_open"].to_numpy(dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            gap = np.where((prev > 0) & np.isfinite(prev), (ao - prev) / prev, 0.0)
        daily["auction_gap"] = gap
        daily["auction_gap_abs"] = np.abs(gap)

        # 竞价相对量能：当前 "竞价量" 相对历史中位数（不含当日本身）
        vol = daily["auction_volume"].to_numpy(dtype=float)
        vol_series = pd.Series(vol, index=daily.index)
        hist_median = vol_series.rolling(window=5, min_periods=1).median().shift(1)
        hist = hist_median.to_numpy(dtype=float)

        with np.errstate(divide="ignore", invalid="ignore"):
            rel_vol = np.where(hist > 0, vol / hist, 1.0)
        daily["auction_rel_volume"] = rel_vol

        # 简单综合强度：gap * 相对量能
        strength = daily["auction_gap"].to_numpy(dtype=float) * daily["auction_rel_volume"].to_numpy(dtype=float)
        daily["auction_strength"] = strength

        # 将日级别因子对齐回逐 bar 数据
        work = work.join(
            daily[[
                "auction_gap",
                "auction_gap_abs",
                "auction_rel_volume",
                "auction_strength",
            ]],
            on="_date",
        )

        # 标记每日首个 bar（便于策略在开盘附近做特殊处理）
        # 对日线数据，每日仅有一行，因此全为 True。
        first_mask = ~work["_date"].duplicated(keep="first")
        work["is_auction_bar"] = first_mask

        # 清理临时列并按原始顺序还原
        work = work.drop(columns=["_date"])
        work = work.reindex(original_index)

        data[symbol] = work

    return data
