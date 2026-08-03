#!/usr/bin/env python3
"""测试掘金 60s 分钟线历史覆盖范围"""
import gm.api as gm

TOKEN = "7b386d408bf468c8318c425fcd28fcd199efdb9e"
gm.set_token(TOKEN)

# 单标的测试，和 syncMinute C++ 调用一致
symbol = "SHSE.600519"  # 贵州茅台

# 从2015逐年测试
for yr in range(2015, 2027):
    s = f"{yr}-01-05"
    e = f"{yr}-01-06"
    try:
        bars = gm.history(symbol, "60s", s, e, adjust=0, skip_suspended=True)
        n = len(bars) if bars else 0
        status = "OK" if n > 0 else "EMPTY"
        print(f"{status} {yr}: {n} bars")
    except Exception as ex:
        print(f"ERR {yr}: {ex}")

# 再测 2026 年最近日期确认 API 本身通畅
print()
for m in range(3, 8):
    s = f"2026-{m:02d}-01"
    e = f"2026-{m:02d}-02"
    try:
        bars = gm.history(symbol, "60s", s, e, adjust=0, skip_suspended=True)
        n = len(bars) if bars else 0
        print(f"  2026-{m:02d}: {n} bars")
    except Exception as ex:
        print(f"  ERR 2026-{m:02d}: {ex}")
