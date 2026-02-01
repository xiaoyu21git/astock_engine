"""简化版 情绪 / 政策 因子

提供两个便于集成的函数：

- apply_simple_sentiment(data):
	根据所有标的在每个交易日的涨跌情况，计算全市场情绪分数 market_sentiment，
	并将其写入每只股票的 DataFrame。

- apply_policy_factor(data):
	根据预定义的 POLICY_EVENTS（按题材 theme 作用于相关股票），
	为每只股票在每个交易日计算 policy_score。

两者都设计为对 {symbol: DataFrame} 结构进行就地扩展，并返回同一 dict 引用。
"""

from typing import Dict

import numpy as np
import pandas as pd

from astock_engine.data.sector_universe import get_symbol_tags
from astock_engine.data.policy_events import iter_policy_events


def apply_simple_sentiment(data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
	"""根据所有标的的当日涨跌计算简化版市场情绪因子。

	定义：
	- 对每个交易日，统计所有标的的涨跌方向：
	  sentiment = (上涨家数 - 下跌家数) / 总家数 ∈ [-1, 1]
	- 将该值写入每只股票该日的 'market_sentiment' 列。
	"""

	frames = []
	for symbol, df in data.items():
		if df is None or df.empty:
			continue
		tmp = df.copy()
		tmp["symbol"] = symbol
		frames.append(tmp)

	if not frames:
		return data

	combined = pd.concat(frames, axis=0)
	if not isinstance(combined.index, pd.DatetimeIndex):
		combined.index = pd.to_datetime(combined.index)

	combined.sort_index(inplace=True)

	# 计算单日收益率
	combined["ret"] = combined.groupby("symbol")["close"].pct_change()

	def _daily_sentiment(group: pd.DataFrame) -> float:
		rets = group["ret"].dropna()
		if rets.empty:
			return 0.0
		up = (rets > 0).sum()
		down = (rets < 0).sum()
		total = len(rets)
		if total == 0:
			return 0.0
		return float((up - down) / total)

	daily_sent = combined.groupby(combined.index.date).apply(_daily_sentiment)
	daily_sent.index = pd.to_datetime(daily_sent.index)
	daily_sent.name = "market_sentiment"

	# 回写到每一行
	combined["market_sentiment"] = daily_sent.reindex(combined.index.date, method=None).values

	# 拆回单只股票
	for symbol, df in data.items():
		if df is None or df.empty:
			continue
		sub = combined[combined["symbol"] == symbol]
		sub = sub.reindex(df.index)
		df["market_sentiment"] = sub["market_sentiment"]
		data[symbol] = df

	return data


def apply_policy_factor(data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
	"""根据预定义的政策事件，计算每只股票的 policy_score。

	简化规则：
	- 每条 PolicyEvent 只作用于对应题材 theme；
	- 某日某标的的 policy_score = 当日所有与其题材匹配的事件 score 之和；
	- 未匹配到题材或无事件时为 0。
	"""

	events = iter_policy_events()
	if not events:
		return data

	# 构造 (date, theme) -> score 的快速查询表
	key_to_score = {}
	for ev in events:
		key = (ev.date, ev.theme)
		key_to_score[key] = key_to_score.get(key, 0.0) + float(ev.score)

	for symbol, df in data.items():
		if df is None or df.empty:
			continue

		tags = get_symbol_tags(symbol)
		themes = tags.get("themes") or []

		if not themes:
			df["policy_score"] = 0.0
			data[symbol] = df
			continue

		scores = []
		for ts in pd.to_datetime(df.index):
			d = ts.date()
			s = 0.0
			for t in themes:
				s += key_to_score.get((d, t), 0.0)
			scores.append(s)

		df["policy_score"] = np.array(scores, dtype=float)
		data[symbol] = df

	return data