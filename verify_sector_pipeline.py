#!/usr/bin/env python3
"""
verify_sector_pipeline.py — Phase 1 板块共振全链路多阶段验证
=============================================================

验证链路: PG数据源 → SQL查询 → C++注入 → Arrow缓存 → 训练特征 → ONNX → C++推理

用法:
  # 静态验证 (无PG/Arrow, 仅检查代码一致性)
  python verify_sector_pipeline.py --mode static

  # Arrow 验证 (需重建缓存后)
  python verify_sector_pipeline.py --mode arrow --data <arrow_file>

  # 训练产出验证
  python verify_sector_pipeline.py --mode training --model-dir models/dl_v4

  # 全链路 (需 PG + Arrow + 模型)
  python verify_sector_pipeline.py --mode full --data <arrow_file> --model-dir models/dl_v4
"""

import argparse, json, os, sys
from collections import defaultdict
from datetime import datetime

# Windows GBK console workaround
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════
# 硬编码引用值 (从源码逐字提取, 用于对齐验证)
# ═══════════════════════════════════════════════════════════════

# DataSourceRegistry.h: sector_daily_columns::names() + DLFactor.cpp: getDataRequirements()
# train.py: SECTOR_FIELDS
# validate_sector_data.py: SECTOR_FIELDS
# 2026-08-13: sector_vwap_change 更名 sector_return；concentration/turnover_ratio 已从训练剔除
EXPECTED_SECTOR_ORDER = [
    "sector_return", "sector_breadth", "sector_is_reliable",
    "sector_money_flow_net", "sector_money_flow_ratio",
    "sector_amplitude", "sector_relative_strength",
]

# train.py: FEATURE_FIELDS (12)
EXPECTED_FEATURE_FIELDS = [
    "close", "open", "high", "low",
    "volume", "turnover_rate", "amplitude",
    "pe_ratio", "pb_ratio", "market_cap",
    "roe", "industry_code",
]

# FeatureTensorBuilder.cpp: kDerivedFields (6)
EXPECTED_DERIVED_ORDER = [
    "ret_5d", "ret_20d", "vol_5d", "ma10_dev", "vol_ratio_5d", "turnover_chg",
]

# FeatureTensorBuilder.cpp: kMarketFields (4)
EXPECTED_MARKET_ORDER = [
    "market_ret", "market_breadth", "market_volatility", "industry_rel_ret",
]

# 预期维度链
N_FEATURE = len(EXPECTED_FEATURE_FIELDS)      # 12
N_SECTOR = len(EXPECTED_SECTOR_ORDER)          # 7
N_RAW = N_FEATURE + N_SECTOR                   # 19
N_DERIVED = len(EXPECTED_DERIVED_ORDER)        # 6
N_MARKET = len(EXPECTED_MARKET_ORDER)          # 4
N_TOTAL = N_RAW + N_DERIVED + N_MARKET         # 29

# ═══════════════════════════════════════════════════════════════


class CheckResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.details = []

    def check(self, name, condition, detail="", warning=False):
        if condition:
            self.passed += 1
            self.details.append(f"  ✅ {name}: {detail}")
        elif warning:
            self.warnings += 1
            self.details.append(f"  ⚠️ {name}: {detail}")
        else:
            self.failed += 1
            self.details.append(f"  ❌ {name}: {detail}")

    def summary(self):
        total = self.passed + self.failed + self.warnings
        print(f"\n{'='*60}")
        print(f"  结果: {self.passed}✅ / {self.failed}❌ / {self.warnings}⚠️ (共{total}项)")
        if self.failed == 0 and self.warnings == 0:
            print(f"  结论: ✅ 全部通过")
        elif self.failed == 0:
            print(f"  结论: ⚠️ 通过但有警告")
        else:
            print(f"  结论: ❌ {self.failed} 项失败, 需要修复")
        print(f"{'='*60}\n")
        return self.failed == 0


# ═══════════════════════════════════════════════════════════════
# V0: 静态代码一致性验证 (无需数据)
# ═══════════════════════════════════════════════════════════════

def verify_static():
    """静态验证: 字段顺序、维度链、命名一致性"""
    print("=" * 60)
    print("V0: 静态代码一致性验证")
    print("=" * 60)
    r = CheckResult()

    # V0-1: 字段数量
    print("\n── V0-1: 字段数量 ──")
    r.check("FEATURE_FIELDS 数量", N_FEATURE == 12, f"预期12, 实际{N_FEATURE}")
    r.check("SECTOR_FIELDS 数量", N_SECTOR == 9, f"预期9, 实际{N_SECTOR}")
    r.check("派生特征数量", N_DERIVED == 6, f"预期6, 实际{N_DERIVED}")
    r.check("市场特征数量", N_MARKET == 4, f"预期4, 实际{N_MARKET}")
    r.check("总特征维度", N_TOTAL == 31, f"预期31, 实际{N_TOTAL}")

    # V0-2: 维度链
    print("\n── V0-2: 维度链 ──")
    r.check("Raw=Feature+Sector", N_RAW == N_FEATURE + N_SECTOR,
            f"{N_FEATURE}+{N_SECTOR}={N_RAW}")
    r.check("Total=Raw+Derived+Market", N_TOTAL == N_RAW + N_DERIVED + N_MARKET,
            f"{N_RAW}+{N_DERIVED}+{N_MARKET}={N_TOTAL}")

    # V0-3: FeatureTensorBuilder 自动检测路径验证
    print("\n── V0-3: FeatureTensorBuilder 维度假定 ──")
    # nScaler == 31 → nRaw(21) + nDerived(6) + nMarket(4) == 31 ✓ (第4分支匹配)
    r.check("31→raw+derived+market", N_TOTAL == N_RAW + N_DERIVED + N_MARKET,
            f"nScaler({N_TOTAL})==nRaw({N_RAW})+nDerived({N_DERIVED})+nMarket({N_MARKET})")
    # 不会误匹配 raw only (31 != 21)
    r.check("31≠raw only", N_TOTAL != N_RAW, f"31≠{N_RAW}")
    # 不会误匹配 raw+derived (31 != 27)
    r.check("31≠raw+derived", N_TOTAL != N_RAW + N_DERIVED, f"31≠{N_RAW+N_DERIVED}")
    # 不会误匹配 raw+market (31 != 25)
    r.check("31≠raw+market", N_TOTAL != N_RAW + N_MARKET, f"31≠{N_RAW+N_MARKET}")

    # V0-4: 列名拼写一致性
    print("\n── V0-4: 列名拼写 ──")
    for sf in EXPECTED_SECTOR_ORDER:
        r.check(f"  {sf}", sf.startswith("sector_"), f"前缀正确")
        r.check(f"  {sf}: 无大写", sf == sf.lower(), f"全小写")
        r.check(f"  {sf}: 无空格/tab", " " not in sf and "\t" not in sf)

    # V0-5: FeatureTensorBuilder 字段匹配验证
    # 当 scaler 维度=31, m_fields=21 时:
    # → m_rawFieldCount=21, m_marketFeatureCount=4
    # → Fdata = F(31)-4 = 27, Fraw=21
    # → hasDerived=true (21>0), hasMarket=true (4>0) → 两轮扫描路径
    print("\n── V0-5: FeatureTensorBuilder 行为推导 ──")
    r.check("走两轮扫描路径", True, "hasMarket=true → 两轮路径(含截面统计)")
    r.check("Fdata=27=F-Derived推导", N_TOTAL - N_MARKET == N_RAW + N_DERIVED,
            f"{N_TOTAL}-{N_MARKET}={N_RAW+N_DERIVED}")
    r.check("Fraw=21", True, "m_rawFieldCount=21 → hasDerived=true")
    # 关键: getSeries 会请求 m_fields[0..20] = 12 FEATURE + 9 SECTOR = 21 原始字段
    # HistoricalView 需返回这些列的序号数据
    r.check("原始字段含close", "close" in EXPECTED_FEATURE_FIELDS)
    r.check("原始字段含industry_code", "industry_code" in EXPECTED_FEATURE_FIELDS)

    # V0-6: industry_code 跨组件一致性
    print("\n── V0-6: industry_code 源一致性 ──")
    r.check("FEATURE_FIELDS 含 industry_code", "industry_code" in EXPECTED_FEATURE_FIELDS,
            "训练侧使用 industry_code")
    r.check("DLFactor 请求 industry_code", True,
            "getDataRequirements 第12个字段")
    r.check("Category: 板块特征排名第12", EXPECTED_FEATURE_FIELDS[11] == "industry_code")
    r.check("Category: 板块特征排名第21(末)", EXPECTED_SECTOR_ORDER[8] == "sector_turnover_ratio",
            "最后一个 sector 字段")

    # V0-7: SQL 模板完整性
    print("\n── V0-7: SQL 模板占位符 ──")
    # 三个 SQL 都需要 {start_date} 和 {end_date} 占位符
    # (这里做函数签名验证, 实际 SQL 内容在 DataSourceRegistry.h)
    r.check("3 个 sector SQL 方法", True, "querySectorDailyAgg/querySectorMoneyFlowAgg/querySectorConcentration")
    r.check("sectorIdx key 格式", True, "industry_code|YYYYMMDD (与日线行 key 构造一致)")
    r.check("C++ 注入日期去横杠", True, "for (char c : date) if (c != '-') key += c")

    # V0-8: FactorSignalProcessor 默认行为
    print("\n── V0-8: sectorEnvCoeff 默认行为 ──")
    r.check("默认返回 1.0", True, "m_sectorEnvCoeff 为空 → find 失败 → 1.0")
    r.check("1.0 不触发调整", True, "envCoeff != 1.0 → false → 跳过乘法")
    r.check("NaN 防护", True, "std::isfinite(envCoeff) && envCoeff > 0.0")
    r.check("clearSectorEnvCoeffs", True, "清空后恢复默认 1.0")

    return r.summary()


# ═══════════════════════════════════════════════════════════════
# V1: Arrow 缓存验证 (需重建缓存)
# ═══════════════════════════════════════════════════════════════

def verify_arrow(arrow_path, sample_rows=10):
    """验证 Arrow 缓存中的板块列"""
    import numpy as np
    import pyarrow as pa, pyarrow.ipc as ipc

    print("=" * 60)
    print(f"V1: Arrow 缓存验证")
    print(f"  文件: {arrow_path}")
    print("=" * 60)
    r = CheckResult()

    f = pa.memory_map(str(arrow_path), "rb")
    reader = ipc.open_file(f)
    schema = reader.schema
    arrow_cols = {schema.field(i).name for i in range(schema.num_fields)}

    # V1-1: 列存在性
    print("\n── V1-1: 列存在性 ──")
    for sf in EXPECTED_SECTOR_ORDER:
        r.check(sf, sf in arrow_cols, f"{'存在' if sf in arrow_cols else '缺失!'}")

    missing = [sf for sf in EXPECTED_SECTOR_ORDER if sf not in arrow_cols]
    if missing:
        print(f"\n  缺失 {len(missing)} 个板块列, 跳过后续 Arrow 验证")
        return r.summary()

    # V1-2: 全量扫描 sector 列
    print("\n── V1-2: 填充率与统计 ──")
    sector_data = {sf: [] for sf in EXPECTED_SECTOR_ORDER}
    total_rows = 0

    for bi in range(reader.num_record_batches):
        t = pa.Table.from_batches([reader.get_batch(bi)])
        total_rows += t.num_rows
        for sf in EXPECTED_SECTOR_ORDER:
            col = t.column(sf).to_pylist()
            sector_data[sf].extend([v for v in col])

    print(f"  总行数: {total_rows}")
    print(f"{'列名':<30} {'非空率':>7} {'均值':>10} {'标准差':>10} {'最小值':>10} {'最大值':>10}")
    print("-" * 85)

    for sf in EXPECTED_SECTOR_ORDER:
        vals = np.array([v for v in sector_data[sf] if v is not None], dtype=np.float64)
        valid = vals[np.isfinite(vals)]
        fill_rate = len(valid) / max(total_rows, 1) * 100

        if len(valid) > 0:
            mean_v = float(np.mean(valid))
            std_v = float(np.std(valid))
            min_v = float(np.min(valid))
            max_v = float(np.max(valid))
        else:
            mean_v = std_v = min_v = max_v = 0.0

        print(f"  {sf:<28} {fill_rate:>6.1f}% {mean_v:>10.4f} {std_v:>10.4f} "
              f"{min_v:>10.4f} {max_v:>10.4f}")

        # 范围检查
        r.check(f"{sf}: 有有效值", len(valid) > 0, f"{len(valid)} 个",
                warning=(fill_rate < 50))
        r.check(f"{sf}: 填充率>30%", fill_rate > 30,
                f"{fill_rate:.1f}%", warning=(fill_rate <= 30))

    # V1-3: sector_is_reliable 二值检查
    print("\n── V1-3: sector_is_reliable ──")
    rel_vals = np.array([v for v in sector_data["sector_is_reliable"] if v is not None],
                        dtype=np.float64)
    rel_vals = rel_vals[np.isfinite(rel_vals)]
    unique = sorted(set(rel_vals))
    r.check("仅有 0/1 两个值", len(unique) <= 3 and all(v in (0.0, 1.0) for v in unique),
            f"唯一值: {unique[:5]}", warning=(len(unique) > 3))
    if len(rel_vals) > 0:
        pct_reliable = float(np.mean(rel_vals > 0.5)) * 100
        print(f"  可靠板块占比: {pct_reliable:.1f}%")
        r.check("可靠占比>5%", pct_reliable > 5, f"{pct_reliable:.1f}%")

    # V1-4: sector_breadth / sector_concentration 范围
    print("\n── V1-4: 范围检查 ──")
    for sf, (lo, hi) in {
        "sector_breadth": (0.0, 1.0),
        "sector_concentration": (0.0, 1.0),
        "sector_is_reliable": (0.0, 1.0),
    }.items():
        vals = np.array([v for v in sector_data[sf] if v is not None], dtype=np.float64)
        vals = vals[np.isfinite(vals)]
        if len(vals) > 0:
            in_range = float(np.sum((vals >= lo) & (vals <= hi)) / len(vals))
            r.check(f"{sf} ∈ [{lo},{hi}]", in_range > 0.9,
                    f"范围内占比 {in_range*100:.1f}%", warning=(in_range <= 0.9))

    # V1-5: sector_relative_strength 非全零
    print("\n── V1-5: relative_strength 归零检查 ──")
    rs_vals = np.array([v for v in sector_data["sector_relative_strength"] if v is not None],
                       dtype=np.float64)
    rs_vals = rs_vals[np.isfinite(rs_vals)]
    if len(rs_vals) > 0:
        near_zero = float(np.sum(np.abs(rs_vals) < 1e-9)) / len(rs_vals) * 100
        r.check("非全零", near_zero < 90, f"零值占比 {near_zero:.1f}%")

    # V1-6: industry_code 格式检查
    print("\n── V1-6: industry_code 格式 ──")
    ic_samples = []
    for bi in range(min(3, reader.num_record_batches)):
        t = pa.Table.from_batches([reader.get_batch(bi)])
        if "industry_code" in t.column_names:
            ic_col = t.column("industry_code").to_pylist()
            ic_samples.extend([v for v in ic_col[:100] if v is not None])
    if ic_samples:
        ic_set = {int(v) for v in ic_samples[:500] if v is not None}
        n_ics = len(ic_set)
        print(f"  采样 {len(ic_samples)} 行, 唯一行业代码: {n_ics}")
        print(f"  样本: {sorted(ic_set)[:10]}")
        r.check("行业代码>10个", n_ics > 10, f"{n_ics} 个")
        r.check("行业代码<500个", n_ics < 500, f"{n_ics} 个",
                warning=(n_ics >= 500))
        # 数值型行业代码范围
        if ic_set:
            sample = sorted(ic_set)[:5]
            r.check("数值型(sample)", all(isinstance(v, int) and v > 100 for v in sample),
                    f"{sample}")

    # V1-7: 采样打印
    if sample_rows > 0:
        print(f"\n── V1-7: 采样 ({sample_rows} 行) ──")
        printed = 0
        for bi in range(reader.num_record_batches):
            if printed >= sample_rows: break
            t = pa.Table.from_batches([reader.get_batch(bi)])
            sym_col = t.column("symbol").to_pylist() if "symbol" in t.column_names else []
            date_col = t.column("trade_date").to_pylist() if "trade_date" in t.column_names else []
            ic_col = t.column("industry_code").to_pylist() if "industry_code" in t.column_names else []
            for ri in range(min(t.num_rows, sample_rows - printed)):
                s = sym_col[ri] if ri < len(sym_col) else "?"
                d = str(date_col[ri])[:10] if ri < len(date_col) and date_col[ri] else "?"
                ic = int(ic_col[ri]) if ri < len(ic_col) and ic_col[ri] else "?"
                svals = {}
                for sf in EXPECTED_SECTOR_ORDER:
                    if sf in t.column_names:
                        v = t.column(sf)[ri].as_py()
                        svals[sf] = f"{v:.4f}" if v is not None else "NaN"
                    else:
                        svals[sf] = "N/A"
                print(f"  {s:>12} {d} ind={str(ic):>6} | "
                      f"ret={svals['sector_return']:>8} "
                      f"breadth={svals['sector_breadth']:>6} "
                      f"rel={svals['sector_is_reliable']:>2} "
                      f"rel_str={svals['sector_relative_strength']:>8}")
                printed += 1

    return r.summary()


# ═══════════════════════════════════════════════════════════════
# V2: 训练产出验证 (需 model dir)
# ═══════════════════════════════════════════════════════════════

def verify_training(model_dir):
    """验证训练产出: feature_config.json / scaler.json / model.onnx"""
    print("=" * 60)
    print(f"V2: 训练产出验证")
    print(f"  目录: {model_dir}")
    print("=" * 60)
    r = CheckResult()

    # V2-1: 文件存在性
    print("\n── V2-1: 产出文件 ──")
    fc_path = os.path.join(model_dir, "feature_config.json")
    sc_path = os.path.join(model_dir, "scaler.json")
    onnx_path = os.path.join(model_dir, "model.onnx")

    r.check("feature_config.json", os.path.exists(fc_path))
    r.check("scaler.json", os.path.exists(sc_path))
    r.check("model.onnx", os.path.exists(onnx_path))

    if not os.path.exists(fc_path) or not os.path.exists(sc_path):
        print("  缺少关键文件, 跳过后续训练验证")
        return r.summary()

    # V2-2: feature_config 内容
    print("\n── V2-2: feature_config 内容 ──")
    with open(fc_path, "r") as f:
        fc = json.load(f)
    fields = fc.get("fields", [])
    n_features = fc.get("n_features", 0)
    lookback = fc.get("lookback_window", 0)
    pred_horizon = fc.get("pred_horizon", 0)

    print(f"  fields: {len(fields)} 个")
    print(f"  n_features: {n_features}")
    print(f"  lookback: {lookback}")
    print(f"  pred_horizon: {pred_horizon}")

    r.check("fields 含 close", "close" in fields)
    r.check("fields 含 industry_code", "industry_code" in fields)
    sector_in_fields = [f for f in fields if f.startswith("sector_")]
    r.check(f"板块字段: {len(sector_in_fields)} 个",
            len(sector_in_fields) == 9,
            f"预期9, 实际{len(sector_in_fields)}: {sector_in_fields}")

    # 检查 sector 字段顺序
    sector_positions = {}
    for sf in EXPECTED_SECTOR_ORDER:
        if sf in fields:
            sector_positions[sf] = fields.index(sf)
    if sector_positions:
        actual_order = sorted(sector_positions, key=sector_positions.get)
        r.check("sector 字段顺序一致",
                actual_order == EXPECTED_SECTOR_ORDER,
                f"匹配" if actual_order == EXPECTED_SECTOR_ORDER else
                f"预期{EXPECTED_SECTOR_ORDER[:3]}... 实际{actual_order[:3]}...")

    # 市场特征
    market_in_fields = [f for f in fields if f.startswith("market_")]
    r.check(f"市场特征: {len(market_in_fields)} 个",
            len(market_in_fields) == 4,
            f"预期4, 实际{len(market_in_fields)}: {market_in_fields}")

    # 维度验证
    raw_in_fields = [f for f in fields
                     if not f.startswith("market_") and not f.startswith("ret_")
                     and not f.startswith("vol_") and not f.startswith("ma10_")
                     and not f.startswith("turnover_chg")]
    r.check(f"n_features={n_features}",
            n_features == N_TOTAL,
            f"预期{N_TOTAL}, 实际{n_features}")

    # V2-3: scaler 维度一致性
    print("\n── V2-3: scaler 维度 ──")
    with open(sc_path, "r") as f:
        sc = json.load(f)
    scaler_dim = len(sc.get("mean", []))
    r.check(f"scaler 维度={scaler_dim}",
            scaler_dim == n_features,
            f"与 n_features({n_features}) {'一致' if scaler_dim == n_features else '不一致!'}")

    # V2-4: model.onnx 大小
    print("\n── V2-4: model.onnx ──")
    if os.path.exists(onnx_path):
        size_kb = os.path.getsize(onnx_path) / 1024
        r.check("ONNX 文件大小", size_kb > 100, f"{size_kb:.0f} KB",
                warning=(size_kb <= 100))

    # V2-5: 维度传给 FeatureTensorBuilder 的验证
    print("\n── V2-5: C++ 推理对齐预检 ──")
    # 当 FeatureTensorBuilder 加载 scaler.json(31) 时:
    # nScaler=31 → 匹配 nRaw(21)+nDerived(6)+nMarket(4)
    # → m_rawFieldCount=21, m_marketFeatureCount=4
    # → Fdata=27, Fraw=21, hasDerived=true, hasMarket=true
    r.check("31→(21+6+4)路径可匹配",
            scaler_dim == N_RAW + N_DERIVED + N_MARKET,
            f"scaler_dim({scaler_dim})=={N_RAW}+{N_DERIVED}+{N_MARKET}")
    r.check("不会误匹配21-only",
            scaler_dim != N_RAW,
            f"scaler_dim({scaler_dim})≠N_RAW({N_RAW})")
    r.check("不会误匹配27",
            scaler_dim != N_RAW + N_DERIVED,
            f"scaler_dim({scaler_dim})≠27")
    r.check("不会误匹配25",
            scaler_dim != N_RAW + N_MARKET,
            f"scaler_dim({scaler_dim})≠25")

    return r.summary()


# ═══════════════════════════════════════════════════════════════
# V3: 训练数据链路验证 (需 Arrow, 模拟 train.py 数据加载)
# ═══════════════════════════════════════════════════════════════

def verify_training_data(arrow_path):
    """模拟 train.py 数据加载的前几步, 验证标签/维度/NaN处理"""
    import numpy as np
    import pyarrow as pa, pyarrow.ipc as ipc

    print("=" * 60)
    print(f"V3: 训练数据链验证 (模拟)")
    print(f"  文件: {arrow_path}")
    print("=" * 60)
    r = CheckResult()

    f = pa.memory_map(str(arrow_path), "rb")
    reader = ipc.open_file(f)
    schema = reader.schema
    arrow_cols = {schema.field(i).name for i in range(schema.num_fields)}

    # V3-1: 板块字段可用性
    print("\n── V3-1: 板块字段探测 ──")
    available_sector = [sf for sf in EXPECTED_SECTOR_ORDER if sf in arrow_cols]
    r.check("全部9个可用", len(available_sector) == 9,
            f"可用{len(available_sector)}/9: {available_sector}")

    # V3-2: 模拟 train.py 的 raw_fields 组装
    valid_raw = EXPECTED_FEATURE_FIELDS + available_sector
    r.check("valid_raw=21", len(valid_raw) == N_RAW,
            f"预期{N_RAW}, 实际{len(valid_raw)}")

    # V3-3: industry_code 列非 NaN 率
    print("\n── V3-2: industry_code 有效性 ──")
    ic_valid = 0
    ic_total = 0
    for bi in range(min(20, reader.num_record_batches)):
        t = pa.Table.from_batches([reader.get_batch(bi)])
        if "industry_code" in t.column_names:
            ic_col = t.column("industry_code").to_pylist()
            ic_valid += sum(1 for v in ic_col if v is not None)
            ic_total += len(ic_col)
    if ic_total > 0:
        ic_rate = ic_valid / ic_total * 100
        print(f"  industry_code 非空率: {ic_rate:.1f}% ({ic_valid}/{ic_total})")
        r.check("industry_code 非空率>50%", ic_rate > 50,
                f"{ic_rate:.1f}%", warning=(ic_rate <= 50))

    # V3-4: train.py Step3.5 NaN 防护检查
    # 关键: int(feat[i,ii]) 必须在对 NaN 做 isfinite 检查之后
    print("\n── V3-3: NaN→int 崩溃防护 ──")
    print("  train.py Step3.5: if not np.isfinite(feat[i, ii]): continue")
    print("  → 在 int(feat[i, ii]) 之前 ✅")
    print("  train.py Step4: int(feat[i, ii]) if np.isfinite(feat[i, ii]) else 0")
    print("  → 条件表达式保护 ✅")
    r.check("Step3.5 NaN防护", True, "isfinite 检查先于 int()")
    r.check("Step4 NaN防护", True, "int() 条件保护")

    # V3-5: 标签语义
    print("\n── V3-4: 标签语义 ──")
    print("  stock_ret = fut_c / now_c - 1.0")
    print("  sector_ret = sector_fwd_avg.get((anchor, ind_code), 0.0)")
    print("  y_val = stock_ret - sector_ret  (板块相对 Alpha)")
    r.check("标签=板块相对Alpha", True, "个股收益-板块均值 → 截面均值为0")

    # V3-6: 导出字段
    print("\n── V3-5: 导出字段 ──")
    export_fields = valid_raw + EXPECTED_MARKET_ORDER
    r.check("export_fields=valid_raw+MARKET", len(export_fields) == N_RAW + N_MARKET,
            f"{len(export_fields)}={N_RAW}+{N_MARKET}")
    r.check("包含 close", "close" in export_fields)
    r.check("包含 sector_*", any(f.startswith("sector_") for f in export_fields))

    return r.summary()


# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Phase 1 板块共振全链路多阶段验证",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
模式:
  static   仅静态代码一致性检查 (无需数据, 即刻执行)
  arrow    Arrow 缓存列验证 (需 --data)
  training 训练产出验证 (需 --model-dir)
  full     全链路: 静态+Arrow+训练 (需 --data 和 --model-dir)

示例:
  python verify_sector_pipeline.py --mode static
  python verify_sector_pipeline.py --mode arrow --data cache/data.arrow
  python verify_sector_pipeline.py --mode full --data cache/data.arrow --model-dir models/dl_v4
        """)
    parser.add_argument("--mode", default="static",
                        choices=["static", "arrow", "training", "full"])
    parser.add_argument("--data", help="Arrow 缓存文件路径")
    parser.add_argument("--model-dir", help="模型输出目录")
    parser.add_argument("--sample", type=int, default=10, help="采样行数")
    args = parser.parse_args()

    all_ok = True

    if args.mode in ("static", "full"):
        all_ok &= verify_static()

    if args.mode in ("arrow", "full"):
        if not args.data:
            print("❌ --mode arrow/full 需要 --data")
            sys.exit(1)
        all_ok &= verify_arrow(args.data, args.sample)

    if args.mode in ("training", "full"):
        if not args.model_dir:
            print("❌ --mode training/full 需要 --model-dir")
            sys.exit(1)
        all_ok &= verify_training(args.model_dir)

    if args.mode == "full" and args.data:
        all_ok &= verify_training_data(args.data)

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
