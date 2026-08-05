"""
盘中市场监控 — 检测指数急跌/急涨
每轮轮询检查指数实时价格, 相对上次记录变化超过阈值时生成风控事件
"""

import logging
import time
import urllib.request
from typing import Dict, Optional, List

logger = logging.getLogger("MarketMonitor")

# 监控的指数 (sina 代码, 名称, 急跌阈值%, 急涨阈值%)
MONITOR_INDICES = [
    ("sh000001", "上证指数", 1.0, 1.5),
    ("sz399001", "深证成指", 1.2, 1.8),
    ("sz399006", "创业板指", 1.5, 2.0),
    ("sh000300", "沪深300", 1.0, 1.5),
]

# 个股急跌监控 (可选, 默认不启用)
# MONITOR_SYMBOLS = ["000001.SZ","600519.SH",...]


class MarketMonitor:
    """盘中指数监控器 — 检测急跌/急涨"""

    def __init__(self):
        self._last_prices: Dict[str, float] = {}   # sina_code → last_close
        self._last_check_time = 0.0
        self._alerts: List[dict] = []               # 本轮检测到的预警

    def check(self) -> List[dict]:
        """检查指数变化, 返回预警事件列表 [{\"type\":\"market_alert\",\"level\":\"market\",...}]"""
        self._alerts = []
        now = time.time()

        symbols = ",".join([s for s, _, _, _ in MONITOR_INDICES])
        try:
            url = f"https://hq.sinajs.cn/list={symbols}"
            req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("gbk")
        except Exception as e:
            logger.warning("[MarketMonitor] 获取指数失败: %s", e)
            return self._alerts

        for line in raw.strip().split("\n"):
            if "=" not in line:
                continue
            code = line.split("=")[0].split("_")[-1]
            fields = line.split('"')[1].split(",") if '"' in line else []
            if len(fields) < 4:
                continue
            name = fields[0]
            price = float(fields[1]) if fields[1] else 0
            if price <= 0:
                continue

            # 找到对应的阈值
            threshold_down = 1.0
            threshold_up = 2.0
            for s, n, td, tu in MONITOR_INDICES:
                if s == code:
                    threshold_down = td
                    threshold_up = tu
                    break

            prev = self._last_prices.get(code)
            self._last_prices[code] = price

            if prev and prev > 0:
                pct = (price - prev) / prev * 100
                if pct <= -threshold_down:
                    self._alerts.append({
                        "type": "market_alert",
                        "title": f"盘中急跌: {name} {pct:+.1f}% (当前{price:.0f})",
                        "level": "market",
                        "action": "reduce_exposure" if abs(pct) > 2 else "alert",
                        "severity": "urgent" if abs(pct) > 2 else "high",
                        "severity_val": str(min(1.0, abs(pct) / 5)),
                        "sentiment_direction": "利空",
                        "pct": round(pct, 2),
                    })
                    logger.warning("[MarketMonitor] %s 急跌 %.1f%% (%s → %s)",
                                   name, pct, prev, price)
                elif pct >= threshold_up and len(self._alerts) == 0:
                    # 急涨也记录, 但不触发风控
                    logger.info("[MarketMonitor] %s 急涨 %.1f%%", name, pct)

        self._last_check_time = now
        return self._alerts
