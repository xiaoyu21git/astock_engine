#!/usr/bin/env python3
"""
validate_sector_data.py — 板块共振数据质量验证 (Phase 1)
检查 Arrow 缓存中 sector_daily_columns 的完整性、数值范围和板块可靠性。

用法:
  python validate_sector_data.py --data <arrow_file>
  python validate_sector_data.py --data cache/datasets/dataset_14/raw/data.arrow --sample
"""

import argparse, sys
import numpy as np
import pyarrow as pa, pyarrow.ipc as ipc

SECTOR_FIELDS = [
    "sector_vwap_change", "sector_breadth", "sector_is_reliable",
    "sector_money_flow_net", "sector_money_flow_ratio",
    "sector_amplitude", "sector_relative_strength",
    "sector_concentration", "sector_turnover_ratio",
]

VALIDATION_CHECKS = {
    "sector_vwap_change":      {"range": (-0.15, 0.15),   "desc": "板块VWAP涨跌幅"},
    "sector_breadth":          {"range": (0.0, 1.0),      "desc": "板块上涨家数占比"},
    "sector_is_reliable":      {"range": (0.0, 1.0),      "desc": "板块统计可靠性(0/1)"},
    "sector_money_flow_net":   {"range": (-1e12, 1e12),   "desc": "板块资金净流入(元)"},
    "sector_money_flow_ratio": {"range": (-0.5, 0.5),     "desc": "板块资金净流入/成交额"},
    "sector_amplitude":        {"range": (0.0, 0.2),      "desc": "板块VWAP日内振幅"},
    "sector_relative_strength":{"range": (-0.1, 0.1),     "desc": "板块相对大盘涨跌幅差"},
    "sector_concentration":    {"range": (0.0, 1.0),      "desc": "板块Top3成交额占比"},
    "sector_turnover_ratio":   {"range": (0.0, 5.0),      "desc": "板块成交额/20日均值"},
}


def main():
    parser = argparse.ArgumentParser(description="板块共振数据质量验证")
    parser.add_argument("--data", required=True, help="Arrow 缓存文件路径")
    parser.add_argument("--sample", type=int, default=20, help="采样打印行数(0=不打印)")
    args = parser.parse_args()

    print(f"[验证] 读取: {args.data}")
    f = pa.memory_map(str(args.data), "rb")
    reader = ipc.open_file(f)
    schema = reader.schema
    arrow_cols = {schema.field(i).name for i in range(schema.num_fields)}

    # ── 1. 列存在性检查 ──
    print("\n── 1. 列存在性 ──")
    missing = []
    for sf in SECTOR_FIELDS:
        status = "✅" if sf in arrow_cols else "❌"
        print(f"  {status} {sf}")
        if sf not in arrow_cols:
            missing.append(sf)

    if missing:
        print(f"\n❌ 缺失 {len(missing)} 个板块列，无法继续验证。请重建 Arrow 缓存。")
        sys.exit(1)

    # ── 2. 全量读取板块列 ──
    print("\n── 2. 数值统计 ──")
    sector_data = {sf: [] for sf in SECTOR_FIELDS}
    industry_codes = []
    total_rows = 0

    for bi in range(reader.num_record_batches):
        batch = reader.get_batch(bi)
        t = pa.Table.from_batches([batch])
        total_rows += t.num_rows

        for sf in SECTOR_FIELDS:
            if sf in t.column_names:
                col = t.column(sf).to_pylist()
                sector_data[sf].extend([v for v in col if v is not None])

        if "industry_code" in t.column_names:
            ic_col = t.column("industry_code").to_pylist()
            industry_codes.extend([v for v in ic_col if v is not None])

    print(f"  总行数: {total_rows}")
    unique_industries = len(set(industry_codes))
    print(f"  唯一行业代码数: {unique_industries}")

    # ── 3. 逐列统计 ──
    print(f"\n{'列名':<28} {'非空率':>7} {'均值':>10} {'标准差':>10} {'最小值':>12} {'最大值':>12} {'范围检查':>8}")
    print("-" * 95)
    all_ok = True
    for sf in SECTOR_FIELDS:
        vals = np.array(sector_data[sf], dtype=np.float64)
        valid = vals[np.isfinite(vals)]
        fill_rate = len(valid) / max(total_rows, 1) * 100
        if len(valid) > 0:
            mean_v = np.mean(valid)
            std_v = np.std(valid)
            min_v = np.min(valid)
            max_v = np.max(valid)
        else:
            mean_v = std_v = min_v = max_v = 0.0

        # 范围检查
        check = VALIDATION_CHECKS.get(sf, {})
        expected_range = check.get("range")
        if expected_range and len(valid) > 0:
            lo, hi = expected_range
            # 允许10%超出(极值)，超50%则告警
            in_range = np.sum((valid >= lo) & (valid <= hi)) / len(valid)
            if in_range < 0.5:
                range_flag = "⚠️ 异常"
                all_ok = False
            elif in_range < 0.9:
                range_flag = "⚠️ 边界"
            else:
                range_flag = "✅"
        else:
            range_flag = "  N/A"

        print(f"  {sf:<26} {fill_rate:>6.1f}% {mean_v:>10.4f} {std_v:>10.4f} "
              f"{min_v:>12.4f} {max_v:>12.4f} {range_flag:>8}")

    # ── 4. 板块可靠性检查 ──
    print("\n── 3. 板块可靠性 ──")
    if "sector_is_reliable" in sector_data and "sector_breadth" in sector_data:
        reliable_vals = np.array(sector_data["sector_is_reliable"], dtype=np.float64)
        reliable_vals = reliable_vals[np.isfinite(reliable_vals)]
        if len(reliable_vals) > 0:
            pct_reliable = np.mean(reliable_vals > 0.5) * 100
            print(f"  可靠板块行占比: {pct_reliable:.1f}%")
            if pct_reliable < 20:
                print(f"  ⚠️ 可靠板块占比过低，可能大量板块成分股 < 5")
                all_ok = False
            elif pct_reliable > 95:
                print(f"  ✅ 绝大多数板块成分股 >= 5，数据覆盖良好")

    # ── 5. sector_relative_strength 归零检查 ──
    print("\n── 4. sector_relative_strength 归零检查 ──")
    if "sector_relative_strength" in sector_data:
        rs_vals = np.array(sector_data["sector_relative_strength"], dtype=np.float64)
        rs_vals = rs_vals[np.isfinite(rs_vals)]
        if len(rs_vals) > 0:
            near_zero = np.sum(np.abs(rs_vals) < 1e-9) / len(rs_vals) * 100
            print(f"  绝对零值占比: {near_zero:.1f}% (C++ 计算异常则全为 0)")
            if near_zero > 90:
                print(f"  ❌ 几乎所有 relative_strength 为 0，C++ 注入逻辑可能异常")
                all_ok = False
            elif near_zero > 30:
                print(f"  ⚠️ relative_strength 零值偏高，可能部分日期市场均值计算失败")
            else:
                print(f"  ✅ relative_strength 分布正常")

    # ── 6. 采样打印 ──
    if args.sample > 0:
        print(f"\n── 5. 采样 ({args.sample} 行) ──")
        printed = 0
        for bi in range(reader.num_record_batches):
            if printed >= args.sample:
                break
            batch = reader.get_batch(bi)
            t = pa.Table.from_batches([batch])
            sym_col = t.column("symbol").to_pylist() if "symbol" in t.column_names else []
            date_col = t.column("trade_date").to_pylist() if "trade_date" in t.column_names else []
            ic_col = t.column("industry_code").to_pylist() if "industry_code" in t.column_names else []

            sector_cols = {}
            for sf in SECTOR_FIELDS:
                if sf in t.column_names:
                    sector_cols[sf] = t.column(sf).to_pylist()

            for ri in range(min(t.num_rows, args.sample - printed)):
                sym = sym_col[ri] if ri < len(sym_col) else "?"
                date = str(date_col[ri])[:10] if ri < len(date_col) and date_col[ri] else "?"
                ic = ic_col[ri] if ri < len(ic_col) else "?"
                sv = {sf: sector_cols[sf][ri] for sf in sector_cols if ri < len(sector_cols[sf])}
                print(f"  [{sym}] {date} ind={ic} | vwap_chg={sv.get('sector_vwap_change','?'):.4f} "
                      f"breadth={sv.get('sector_breadth','?'):.3f} reliable={sv.get('sector_is_reliable','?')} "
                      f"rel_str={sv.get('sector_relative_strength','?'):.4f}")
                printed += 1

    # ── 7. 结论 ──
    print(f"\n{'='*40}")
    if all_ok and not missing:
        print("✅ 板块数据验证通过")
    else:
        print("❌ 板块数据验证发现问题，请检查上述 ⚠️/❌ 标记")
    print(f"{'='*40}")


if __name__ == "__main__":
    main()
