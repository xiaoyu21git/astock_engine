#!/usr/bin/env python3
"""
train.py — DLFactor 生产级训练 + ONNX 导出

从 Arrow 缓存读取数据 → 训练 LSTM → 导出 ONNX + scaler + feature_config

用法:
  python train.py --data <arrow> --output models/dl_v9 --symbols all --horizon 20 --epochs 100
"""

import argparse, json, os, sys, time, warnings
from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np
import pyarrow as pa, pyarrow.ipc as ipc
import torch, torch.nn as nn, torch.optim as optim
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════
# 配置常量 (训练-推理同步)
# ══════════════════════════════════════════════════════

FEATURE_FIELDS = [
    "close", "open", "high", "low",
    "volume", "turnover_rate", "amplitude",
    "pe_ratio", "pb_ratio", "market_cap",
    "roe", "industry_code",
]

# 市场环境特征 (截面统计量, 同一天所有股票共享)
MARKET_FEATURES = [
    "market_ret",         # 全市场等权平均收益率
    "market_breadth",     # 当日上涨股票占比
    "market_volatility",  # 截面收益率标准差
    "industry_rel_ret",   # 个股收益 - 所属行业平均收益
]
ALL_FIELDS = FEATURE_FIELDS + MARKET_FEATURES

LOOKBACK = 20
PRED_HORIZON = 20       # 需与回测 forwardDays 一致
MIN_LISTED_DAYS = 60

# 时序切分 (包含 9.24 政策转向)
TRAIN_END = "2025-12-31"
VAL_END   = "2026-03-31"
TEST_END  = "2026-07-27"


# ══════════════════════════════════════════════════════
# 模型
# ══════════════════════════════════════════════════════

class FactorLSTM(nn.Module):
    def __init__(self, n_features, hidden_size=128, num_layers=2, dropout=0.2):
        super().__init__()
        self.lstm = nn.LSTM(n_features, hidden_size, num_layers,
                            batch_first=True, dropout=dropout)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])


# ══════════════════════════════════════════════════════
# 标签转换
# ══════════════════════════════════════════════════════

def to_rank_labels(y, dates):
    """按日期截面排序: 每天内对收益排名 → [-1, 1]"""
    from scipy.stats import rankdata
    ranked = np.zeros_like(y)
    for d in sorted(set(dates)):
        mask = np.array([dd == d for dd in dates])
        if mask.sum() > 1:
            ranked[mask] = rankdata(y[mask])
    return (ranked - 1) / (np.maximum(ranked.max(axis=0, initial=1) - 1, 1)) * 2 - 1


# ══════════════════════════════════════════════════════
# 评估
# ══════════════════════════════════════════════════════

def compute_metrics(y_true, y_pred, dates=None):
    """Spearman Rank IC (日均) + 多空价差"""
    from scipy.stats import spearmanr
    n = len(y_pred) // 5
    spread = 0.0
    if n > 0:
        order = np.argsort(y_pred)
        spread = y_true[order[-n:]].mean() - y_true[order[:n]].mean()

    if dates is not None and len(dates) > 0:
        daily_ic = []
        for d in sorted(set(dates)):
            mask = np.array([dd == d for dd in dates])
            if mask.sum() >= 5:
                r, _ = spearmanr(y_true[mask], y_pred[mask])
                if np.isfinite(r): daily_ic.append(r)
        ic = float(np.mean(daily_ic)) if daily_ic else 0.0
    else:
        r, _ = spearmanr(y_true, y_pred)
        ic = float(r) if np.isfinite(r) else 0.0

    half_life = 0
    if len(y_pred) > 10:
        ac = [ic]
        for lag in range(1, min(10, len(y_pred) // 2)):
            if len(y_pred) > lag:
                ac.append(float(np.corrcoef(y_pred[:-lag], y_pred[lag:])[0, 1]))
        for lag, v in enumerate(ac):
            if v < ic / 2:
                half_life = lag; break

    return {"rank_ic": round(ic, 4), "spread": round(spread, 6), "half_life": half_life}


# ══════════════════════════════════════════════════════
# 数据加载 (单遍扫描 + 市场截面特征)
# ══════════════════════════════════════════════════════

def load_data(arrow_path, symbols, raw_fields, lookback, pred_horizon,
              train_end=TRAIN_END, val_end=VAL_END, test_end=TEST_END):
    """单遍 Arrow → 密集矩阵 → 截面统计 → 样本

    Step 1: 单遍加载所有原始数据 → {stock: {date: {field: value}}}
    Step 2: 每只股票 ffill → [n_dates, n_raw]
    Step 3: 按日期收集 close/industry → 计算市场统计量
    Step 4: 构建样本: window_raw + market_features + label
    """
    t0 = time.time()

    print(f"[data] 读取: {arrow_path}")
    f = pa.memory_map(str(arrow_path), "rb")
    reader = ipc.open_file(f)

    # ── 自动发现标的 ──
    if symbols is None or (len(symbols) == 1 and symbols[0] == "all"):
        symbols = set()
        for bi in range(reader.num_record_batches):
            t = pa.Table.from_batches([reader.get_batch(bi)])
            for s in t.column("symbol").to_pylist():
                if s: symbols.add(s)
        symbols = sorted(symbols)
        print(f"[data] 自动发现 {len(symbols)} 只标的")

    sym_set = {s for s in set(symbols)
               if not (s.startswith("000") and s.endswith(".SH"))
               and not s.startswith("200") and not s.startswith("399")}
    symbols = [s for s in symbols if s in sym_set]
    sym_to_idx = {s: i for i, s in enumerate(symbols)}

    ci = raw_fields.index("close")
    ii = raw_fields.index("industry_code")
    n_raw = len(raw_fields)
    n_market = len(MARKET_FEATURES)

    # ── Step 1: 单遍扫描 ──
    stock_data = {s: {} for s in symbols}

    for bi in range(reader.num_record_batches):
        batch = reader.get_batch(bi)
        t = pa.Table.from_batches([batch])
        sc = t.column("symbol").to_pylist()
        dc = t.column("trade_date").to_pylist()
        fc = {fn: t.column(fn).to_pylist() for fn in raw_fields if fn in t.column_names}
        for ri in range(t.num_rows):
            s = sc[ri]
            if s not in sym_to_idx: continue
            d_str = str(dc[ri])[:10]
            row = {}
            for fn in raw_fields:
                if fn in fc:
                    v = fc[fn][ri]
                    row[fn] = float(v) if v is not None and v == v else float("nan")
            stock_data[s][d_str] = row
    print(f"[data] Step1 扫描完成 ({time.time()-t0:.0f}s)")

    # ── Step 2: ffill → 密集矩阵 ──
    stock_feat = {}
    stock_dates = {}
    for s in symbols:
        rows = stock_data[s]
        if len(rows) < MIN_LISTED_DAYS: continue
        sorted_d = sorted(rows.keys())
        n = len(sorted_d)
        feat = np.full((n, n_raw), np.nan, dtype=np.float32)
        for i, d in enumerate(sorted_d):
            for j, fn in enumerate(raw_fields):
                v = rows[d].get(fn, np.nan)
                if np.isfinite(v): feat[i, j] = v
        mask = np.isfinite(feat)
        idx_arr = np.where(mask, np.arange(n)[:, None], 0)
        np.maximum.accumulate(idx_arr, axis=0, out=idx_arr)
        feat = feat[idx_arr, np.arange(n_raw)]
        stock_feat[s] = feat
        stock_dates[s] = sorted_d
    del stock_data

    all_dates = sorted(set(d for dates in stock_dates.values() for d in dates))
    date_to_idx = {d: i for i, d in enumerate(all_dates)}
    nd = len(all_dates)
    print(f"[data] Step2 密集矩阵: {len(stock_feat)} 只股票, {nd} 个交易日 ({time.time()-t0:.0f}s)")

    # ── Step 3: 截面统计 ──
    # 收集每天每只股票的 close, industry_code, 前一日 close
    date_closes = [[] for _ in range(nd)]
    date_prev_close = [{} for _ in range(nd)]   # {stock_idx: prev_close}
    date_inds = [[] for _ in range(nd)]
    date_sids = [[] for _ in range(nd)]

    for s in stock_feat:
        si = sym_to_idx[s]
        feat = stock_feat[s]
        dates = stock_dates[s]
        for i, d in enumerate(dates):
            di = date_to_idx[d]
            c = feat[i, ci]
            ind = feat[i, ii]
            if np.isfinite(c) and c > 1e-9:
                date_closes[di].append(c)
                date_inds[di].append(ind)
                date_sids[di].append(si)
                if i > 0:
                    prev_c = feat[i-1, ci]
                    if np.isfinite(prev_c) and prev_c > 1e-9:
                        date_prev_close[di][si] = prev_c

    market_ret = np.zeros(nd, dtype=np.float32)
    market_breadth = np.zeros(nd, dtype=np.float32)
    market_vol = np.zeros(nd, dtype=np.float32)
    industry_rel = [{} for _ in range(nd)]

    for di in range(nd):
        sids = date_sids[di]
        closes = np.array(date_closes[di], dtype=np.float64)
        inds = np.array(date_inds[di], dtype=np.float64)
        nv = len(closes)
        if nv < 10: continue

        # 日收益率
        rets = np.zeros(nv, dtype=np.float32)
        for j, sid in enumerate(sids):
            pc = date_prev_close[di].get(sid, 0.0)
            rets[j] = closes[j] / max(pc, 1e-9) - 1.0 if pc > 1e-9 else 0.0
        rets = np.clip(rets, -0.2, 0.2)

        market_ret[di] = float(np.mean(rets))
        market_breadth[di] = float(np.mean(rets > 0))
        market_vol[di] = float(np.std(rets))

        # 行业相对收益
        for ind_val in np.unique(inds):
            mask = inds == ind_val
            if mask.sum() >= 3:
                ind_avg = float(np.mean(rets[mask]))
                for j in np.where(mask)[0]:
                    industry_rel[di][sids[j]] = float(rets[j] - ind_avg)

    print(f"[data] Step3 截面统计完成 ({time.time()-t0:.0f}s)")

    # ── Step 4: 构建样本 ──
    gap_calendar = int(pred_horizon * 1.5)
    purge_boundary = (datetime.strptime(train_end, "%Y-%m-%d")
                      + timedelta(days=gap_calendar)).strftime("%Y-%m-%d")
    print(f"[data] 切分: train≤{train_end} val≤{val_end} test≤{test_end} purge={purge_boundary}")

    X_train, y_train, d_train = [], [], []
    X_val, y_val, d_val = [], [], []
    X_test, y_test, d_test = [], [], []
    purged = 0

    for s in stock_feat:
        feat = stock_feat[s]
        dates = stock_dates[s]
        si = sym_to_idx[s]
        n = len(dates)
        if n < lookback + pred_horizon: continue

        for i in range(lookback, n - pred_horizon):
            anchor = dates[i]
            window_raw = feat[i - lookback:i]
            if np.any(np.isnan(window_raw)): continue

            now_c = feat[i, ci]
            fut_c = feat[i + pred_horizon, ci]
            if now_c <= 0 or fut_c <= 0: continue

            # 市场特征: 窗口内每一天的截面统计
            window_market = np.zeros((lookback, n_market), dtype=np.float32)
            for w in range(lookback):
                d_str = dates[i - lookback + w]
                di = date_to_idx.get(d_str, -1)
                if di >= 0:
                    window_market[w, 0] = market_ret[di]
                    window_market[w, 1] = market_breadth[di]
                    window_market[w, 2] = market_vol[di]
                    window_market[w, 3] = industry_rel[di].get(si, 0.0)

            window = np.concatenate([window_raw, window_market], axis=1)
            y_val_i = fut_c / now_c - 1.0

            if anchor <= train_end:
                X_train.append(window); y_train.append(y_val_i); d_train.append(anchor)
            elif anchor <= val_end:
                if anchor > purge_boundary:
                    X_val.append(window); y_val.append(y_val_i); d_val.append(anchor)
                else:
                    purged += 1
            elif anchor <= test_end:
                X_test.append(window); y_test.append(y_val_i); d_test.append(anchor)

    print(f"[data] Step4 样本: train={len(X_train)} val={len(X_val)} test={len(X_test)} purged={purged}")
    print(f"[data] 总耗时: {time.time()-t0:.0f}s")

    if not X_train: raise RuntimeError("无训练样本")

    # ── pack + winsorize + rank labels ──
    n_total = n_raw + n_market

    def pack(lst_x, lst_y, lst_d):
        if not lst_x:
            return (np.zeros((0, lookback, n_total), dtype=np.float32),
                    np.zeros(0, dtype=np.float32), [])
        return np.stack(lst_x).astype(np.float32), np.array(lst_y, dtype=np.float32), lst_d

    X_train, y_train_raw, dt = pack(X_train, y_train, d_train)
    X_val, y_val_raw, dv = pack(X_val, y_val, d_val)
    X_test, y_test_raw, dt2 = pack(X_test, y_test, d_test)

    def winsorize(y, lo=-0.3, hi=0.3):
        return np.clip(np.array(y, dtype=np.float32), lo, hi)

    y_train = to_rank_labels(winsorize(y_train_raw), dt)
    y_val   = to_rank_labels(winsorize(y_val_raw), dv) if len(dv) else y_val_raw
    y_test  = to_rank_labels(winsorize(y_test_raw), dt2) if len(dt2) else y_test_raw

    return ((X_train, y_train, X_val, y_val, X_test, y_test),
            symbols,
            (dt, dv, dt2))


# ══════════════════════════════════════════════════════
# 训练
# ══════════════════════════════════════════════════════

def train(args, X_train, y_train, X_val, y_val, X_test=None, y_test=None,
          d_train=None, d_val=None, d_test=None):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[train] device={device}")

    if device.type == "cuda":
        torch.backends.cudnn.benchmark = True
        torch.set_float32_matmul_precision("high")

    n_features = X_train.shape[2]
    print(f"[train] 特征数={n_features} (raw+market)")
    model = FactorLSTM(n_features, args.hidden_units, args.hidden_layers, args.dropout).to(device)
    if hasattr(torch, "compile"):
        model = torch.compile(model)
        print("[train] torch.compile enabled")

    # 极端值过滤: 1%/99% winsorize
    X_flat = X_train.reshape(-1, n_features)
    p1 = np.percentile(X_flat, 1.0, axis=0)
    p99 = np.percentile(X_flat, 99.0, axis=0)
    X_flat = np.clip(X_flat, p1, p99)

    scaler = StandardScaler()
    X_flat = scaler.fit_transform(X_flat)
    X_train_norm = X_flat.reshape(X_train.shape)

    if len(X_val) > 0:
        X_val_flat = X_val.reshape(-1, n_features)
        X_val_flat = np.clip(X_val_flat, p1, p99)
        X_val_flat = scaler.transform(X_val_flat)
        X_val_norm = X_val_flat.reshape(X_val.shape)
    else:
        X_val_norm = X_val

    Xt = torch.FloatTensor(X_train_norm).to(device)
    yt = torch.FloatTensor(y_train).to(device)
    Xv = torch.FloatTensor(X_val_norm).to(device) if len(X_val) > 0 else Xt[:0]
    yv = torch.FloatTensor(y_val).to(device) if len(y_val) > 0 else yt[:0]

    criterion = nn.MSELoss()
    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-3)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    scaler_amp = torch.cuda.amp.GradScaler() if device.type == "cuda" else None

    best_val_loss = float("inf")
    bs = args.batch_size

    for epoch in range(args.epochs):
        model.train()
        total_loss, n_batches = 0.0, 0
        perm = torch.randperm(len(Xt))
        for i in range(0, len(Xt), bs):
            idx = perm[i:i+bs]
            xb, yb = Xt[idx], yt[idx]
            optimizer.zero_grad()
            if scaler_amp:
                with torch.cuda.amp.autocast():
                    loss = criterion(model(xb).reshape(-1), yb)
                scaler_amp.scale(loss).backward()
                scaler_amp.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler_amp.step(optimizer)
                scaler_amp.update()
            else:
                loss = criterion(model(xb).reshape(-1), yb)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
            total_loss += loss.item(); n_batches += 1

        scheduler.step()
        model.eval()
        with torch.no_grad():
            if len(Xv) > 0:
                vp_all, val_loss = [], 0.0
                for i in range(0, len(Xv), bs):
                    xb = Xv[i:i+bs]; yb = yv[i:i+bs]
                    out = model(xb).reshape(-1)
                    vp_all.append(out.cpu().numpy())
                    val_loss += float(criterion(out.cpu(), yb.cpu().reshape(-1)).item())
                vp = np.concatenate(vp_all)
                val_loss /= max(1, (len(Xv)+bs-1)//bs)
                m = compute_metrics(yv.cpu().numpy(), vp, d_val if d_val else None)
            else:
                val_loss = total_loss / max(n_batches, 1)
                m = {"rank_ic": 0, "spread": 0, "half_life": 0}

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), os.path.join(args.output, "best_model.pt"))

        if epoch % max(1, args.epochs // 10) == 0 or epoch == args.epochs - 1:
            print(f"  epoch {epoch:3d}: loss={total_loss/n_batches:.6f} "
                  f"val={val_loss:.6f} IC={m['rank_ic']:.4f} "
                  f"spread={m['spread']:.6f} hl={m['half_life']}")

    model.load_state_dict(torch.load(os.path.join(args.output, "best_model.pt"), weights_only=True))

    if X_test is not None and len(X_test) > 0:
        Xt_flat = X_test.reshape(-1, n_features)
        Xt_flat = np.clip(Xt_flat, p1, p99)
        Xt_flat = scaler.transform(Xt_flat)
        Xt_t = torch.FloatTensor(Xt_flat.reshape(X_test.shape)).to(device)
        yt_t = torch.FloatTensor(y_test).to(device)
        with torch.no_grad():
            tp_all = []
            for i in range(0, len(Xt_t), bs):
                tp_all.append(model(Xt_t[i:i+bs]).reshape(-1).cpu().numpy())
            tp = np.concatenate(tp_all)
            tm = compute_metrics(yt_t.cpu().numpy(), tp, d_test if d_test else None)
        print(f"  [test]  IC={tm['rank_ic']:.4f}  spread={tm['spread']:.6f}  hl={tm['half_life']}")

    return model, scaler, n_features, p1, p99


# ══════════════════════════════════════════════════════
# 导出
# ══════════════════════════════════════════════════════

def export_onnx(model, scaler, n_features, lookback, output_dir, fields, pred_horizon, p1=None, p99=None):
    if hasattr(model, "_orig_mod"):
        model = model._orig_mod
    model.eval()
    device = next(model.parameters()).device
    dummy = torch.randn(1, lookback, n_features, device=device)

    scaler_data = {
        "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
        "winsor_lo": p1.tolist() if p1 is not None else [],
        "winsor_hi": p99.tolist() if p99 is not None else [],
    }
    with open(os.path.join(output_dir, "scaler.json"), "w") as f:
        json.dump(scaler_data, f)

    config = {"fields": fields, "lookback_window": lookback,
              "n_features": n_features, "pred_horizon": pred_horizon,
              "scaler": scaler_data}
    with open(os.path.join(output_dir, "feature_config.json"), "w") as f:
        json.dump(config, f, indent=2)

    onnx_path = os.path.join(output_dir, "model.onnx")
    torch.onnx.export(model, dummy, onnx_path,
                      input_names=["input"], output_names=["output"],
                      dynamic_axes={"input": {0: "N"}, "output": {0: "N"}},
                      opset_version=18, dynamo=False)
    kb = os.path.getsize(onnx_path) / 1024
    print(f"[export] ONNX: {onnx_path} ({kb:.0f} KB)")


# ══════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="DLFactor 生产级训练")
    parser.add_argument("--data", required=True, help="Arrow 缓存文件路径")
    parser.add_argument("--output", default="models/dl_v3", help="输出目录")
    parser.add_argument("--symbols", nargs="*", default=["all"], help="标的列表")
    parser.add_argument("--fields", nargs="*", default=FEATURE_FIELDS, help="原始特征字段")
    parser.add_argument("--lookback", type=int, default=LOOKBACK)
    parser.add_argument("--horizon", type=int, default=PRED_HORIZON)
    parser.add_argument("--hidden-layers", type=int, default=2)
    parser.add_argument("--hidden-units", type=int, default=128)
    parser.add_argument("--dropout", type=float, default=0.35)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--no-amp", action="store_true", help="禁用混合精度训练")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    # 过滤有效字段
    valid_raw = [f for f in args.fields if f in FEATURE_FIELDS]
    print(f"[train] 原始字段: {valid_raw} ({len(valid_raw)} 个)")
    print(f"[train] 市场字段: {MARKET_FEATURES} ({len(MARKET_FEATURES)} 个)")
    print(f"[train] 标签: 截面排序 (Spearman Rank IC 对齐)")
    print(f"[train] 切分: 训练 ~{TRAIN_END} / 验证 ~{VAL_END}")
    print(f"[train] 加速: amp={not args.no_amp}")

    (X_train, y_train, X_val, y_val, X_test, y_test), syms, \
        (d_train, d_val, d_test) = load_data(
        args.data, args.symbols, valid_raw, args.lookback, args.horizon)

    model, scaler, nf, p1, p99 = train(
        args, X_train, y_train, X_val, y_val, X_test, y_test, d_train, d_val, d_test)

    export_onnx(model, scaler, nf, args.lookback, args.output, ALL_FIELDS, args.horizon, p1, p99)
    print(f"\n[完成] {args.output}/")
    print(f"  model.onnx  scaler.json  feature_config.json")


if __name__ == "__main__":
    main()
