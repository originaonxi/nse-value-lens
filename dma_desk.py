#!/usr/bin/env python3
"""Nifty 500 DMA Intelligence Desk — multi-timeframe crossover detection + backtest + portfolio.

Crossover taxonomy (strongest → weakest):
  platinum  close > 20DMA > 50DMA > 100DMA > 200DMA  — perfect bull stack
  golden    50DMA crossed above 200DMA in ≤ 20 sessions   — classic signal
  silver    20DMA crossed above 50DMA  in ≤ 10 sessions
  bronze    price crossed above 200DMA in ≤  5 sessions
  watch     50DMA > 200DMA sustained, no fresh cross
  neutral   price above 200DMA, DMAs not aligned
  bear      50DMA < 200DMA, price below 50DMA
  death     50DMA freshly crossed below 200DMA in ≤ 20 sessions

Score (0–100):
  DMA alignment   35 pts  (5 per gate: close>200, >100, >50, >20, 100>200, 50>100, 20>50)
  Cross recency   25 pts  (platinum=25, golden=20, silver=15, bronze=10, watch=5)
  HHHL trend      20 pts  (uptrend=20, turning_up=15, ready_to_break=12, sideways=5)
  Backtest        20 pts  (3M win-rate × 20; neutral 10 if <MIN_EVENTS crossovers)

Portfolio: top 30 eligible by score, weighted score/vol, ≤6% per stock, ≤30% per sector.
Market guard: Nifty 50 < 200-DMA → 50% cash sleeve.
Exit: close < 200-DMA at day-end → sell at next open. Rebalance: last session of each month.
"""
import csv, io, json, math, time
from datetime import datetime
from pathlib import Path
from statistics import median
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
PRICES = ROOT / "data" / "hhhl_prices"
DOCS = ROOT / "docs"
PUBLIC_DATA = ROOT / "public" / "data"
N500_CSV = ROOT / "nifty500.csv"
N500_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"

DMA_WINDOWS = [20, 50, 100, 200]
HOLDINGS = 30
MAX_WEIGHT = 0.06
MAX_SECTOR = 0.30
CASH_GUARD = 0.50
MIN_HIST = 252 * 2          # 2 years minimum for backtest
MIN_BACKTEST_EVENTS = 5     # crossovers needed to use backtest score
LONG = 250                  # 12M volatility window


# ── Universe ──────────────────────────────────────────────────────────────────

def load_universe():
    """Load Nifty 500 constituents, refreshing from NSE at most once a month."""
    if N500_CSV.exists() and (time.time() - N500_CSV.stat().st_mtime) < 28 * 86400:
        with open(N500_CSV, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    else:
        try:
            rows = _fetch_n500()
        except Exception as e:
            print(f"WARN: NSE fetch failed ({e}); using cached {N500_CSV.name}")
            with open(N500_CSV, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))

    result = []
    for r in rows:
        sym = (r.get("Symbol") or r.get("symbol") or "").strip().upper()
        name = (r.get("Company Name") or r.get("name") or sym).strip()
        sector = (r.get("Industry") or r.get("sector") or "Other").strip()
        if sym:
            result.append({"symbol": sym, "name": name, "sector": sector})
    return result


def _fetch_n500():
    req = Request(N500_URL, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*",
                                     "Referer": "https://www.niftyindices.com/"})
    raw = urlopen(req, timeout=30).read().decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(raw)))
    N500_CSV.write_text(raw, encoding="utf-8")
    return rows


# ── Prices ────────────────────────────────────────────────────────────────────

def load_prices(symbols):
    """Return DataFrame of adjusted closes (date × symbol).
    Uses hhhl_prices CSV cache; fetches missing via yfinance."""
    loaded, to_fetch = {}, []
    for sym in symbols:
        p = PRICES / f"{sym}.NS.csv"
        if p.exists():
            try:
                df = pd.read_csv(p, index_col=0, parse_dates=True)
                col = next((c for c in ["Close", "Adj Close", "close"] if c in df.columns), None)
                if col and len(df) >= 100:
                    loaded[sym] = df[col].rename(sym)
                    continue
            except Exception:
                pass
        to_fetch.append(sym)

    if to_fetch:
        _fetch_yfinance(to_fetch, loaded)

    if not loaded:
        return pd.DataFrame()
    px = pd.concat(loaded.values(), axis=1).sort_index()
    px = px[px.index.dayofweek < 5]
    return px


def _fetch_yfinance(symbols, result_dict):
    try:
        import yfinance as yf
        tickers = [f"{s}.NS" for s in symbols]
        raw = yf.download(tickers, period="6y", interval="1d",
                          auto_adjust=True, progress=False,
                          group_by="ticker", threads=True)
        if raw.empty:
            return
        for sym in symbols:
            ticker = f"{sym}.NS"
            try:
                df = raw[ticker] if len(symbols) > 1 else raw
                df = df.dropna(how="all")
                if len(df) < 100:
                    continue
                col = next((c for c in ["Close", "Adj Close"] if c in df.columns), None)
                if col:
                    (PRICES / f"{sym}.NS.csv").write_text(df.to_csv())
                    result_dict[sym] = df[col].rename(sym)
            except Exception:
                pass
    except ImportError:
        print("WARN: yfinance not installed; only cached prices available")
    except Exception as e:
        print(f"WARN: yfinance batch fetch error: {e}")


def get_nifty50_guard():
    """True if Nifty 50 closed below its 200-DMA today."""
    try:
        mkt = json.loads((DOCS / "daily_market.json").read_text(encoding="utf-8"))
        for key in ("NIFTY 50", "NIFTY50", "nifty50", "Nifty 50"):
            n = mkt.get(key) or (mkt.get("indices") or {}).get(key)
            if n:
                c, d = float(n.get("close", 0) or 0), float(n.get("dma200", 0) or 0)
                if c and d:
                    return c < d
        # Fallback: find any nifty entry
        for v in mkt.values():
            if isinstance(v, dict) and "dma200" in v and "close" in v:
                c, d = float(v.get("close", 0) or 0), float(v.get("dma200", 0) or 0)
                if c and d:
                    return c < d
    except Exception:
        pass
    return False  # default: no guard


# ── DMA computation ───────────────────────────────────────────────────────────

def compute_dmas(px):
    """Return {window: DataFrame} for each DMA period."""
    return {w: px.rolling(w, min_periods=w).mean() for w in DMA_WINDOWS}


# ── Crossover classification ──────────────────────────────────────────────────

CROSS_RECENCY_SCORE = {
    "platinum": 25, "golden": 20, "silver": 15, "bronze": 10,
    "watch": 5, "neutral": 2, "bear": 0, "death": 0,
}
CROSS_LABEL = {
    "platinum": "Platinum 🏆", "golden": "Golden 🥇", "silver": "Silver 🥈",
    "bronze": "Bronze 🥉", "watch": "Watch 👀", "neutral": "Neutral ➡️",
    "bear": "Bear 📉", "death": "Death 💀",
}


def _safe_last(series):
    s = series.dropna()
    return float(s.iloc[-1]) if len(s) else None


def classify_crossover(sym, px_col, dmas):
    """Return (crossover_type, alignment_score, gates_dict, dma_values_dict)."""
    try:
        series = px_col.dropna()
        if len(series) < 210:
            return "neutral", 0, {}, {}

        close = float(series.iloc[-1])
        dv = {w: _safe_last(dmas[w][sym]) if sym in dmas[w].columns else None
              for w in DMA_WINDOWS}
        if any(v is None for v in dv.values()):
            return "neutral", 0, {}, dv

        d20, d50, d100, d200 = dv[20], dv[50], dv[100], dv[200]
        gates = {
            "close_gt_200": close > d200, "close_gt_100": close > d100,
            "close_gt_50": close > d50,   "close_gt_20": close > d20,
            "d100_gt_200": d100 > d200,   "d50_gt_100":  d50 > d100,
            "d20_gt_50":   d20 > d50,
        }
        align_score = sum(5 for g in gates.values() if g)  # 0–35

        cross_type = _detect_cross(sym, series, dmas)
        return cross_type, align_score, gates, dv
    except Exception:
        return "neutral", 0, {}, {}


def _detect_cross(sym, series, dmas):
    try:
        d50  = dmas[50].get(sym, pd.Series(dtype=float)).dropna() if sym in dmas[50].columns else pd.Series(dtype=float)
        d200 = dmas[200].get(sym, pd.Series(dtype=float)).dropna() if sym in dmas[200].columns else pd.Series(dtype=float)
        d20  = dmas[20].get(sym, pd.Series(dtype=float)).dropna() if sym in dmas[20].columns else pd.Series(dtype=float)
        d100 = dmas[100].get(sym, pd.Series(dtype=float)).dropna() if sym in dmas[100].columns else pd.Series(dtype=float)
        if len(d50) < 25 or len(d200) < 25:
            return "neutral"

        close = float(series.dropna().iloc[-1])
        d50n, d200n = float(d50.iloc[-1]), float(d200.iloc[-1])
        d20n  = float(d20.iloc[-1])  if len(d20)  else d50n
        d100n = float(d100.iloc[-1]) if len(d100) else d200n

        # Platinum: perfect stack
        if close > d20n > d50n > d100n > d200n:
            return "platinum"

        # Death cross: 50 freshly crossed below 200
        r50, r200 = d50.iloc[-20:], d200.iloc[-20:]
        if d50n < d200n:
            if ((r50 < r200) & (r50.shift(1) >= r200.shift(1))).any():
                return "death"
            return "bear"

        # Golden cross: 50 freshly crossed above 200
        if ((r50 > r200) & (r50.shift(1) <= r200.shift(1))).any():
            return "golden"

        # Silver cross: 20 freshly crossed above 50
        if d20n > d50n and len(d20) >= 10:
            r20s, r50s = d20.iloc[-10:], d50.iloc[-10:]
            if ((r20s > r50s) & (r20s.shift(1) <= r50s.shift(1))).any():
                return "silver"

        # Bronze: price freshly crossed above 200
        if close > d200n and len(series.dropna()) >= 5:
            rc = series.dropna().iloc[-5:]
            r2 = d200.iloc[-5:]
            if ((rc > r2) & (rc.shift(1) <= r2.shift(1))).any():
                return "bronze"

        if d50n > d200n:
            return "watch"
        if close > d200n:
            return "neutral"
        return "bear"
    except Exception:
        return "neutral"


# ── Backtesting ───────────────────────────────────────────────────────────────

def backtest_golden_cross(sym, series, dmas):
    """Find all 50/200 golden crosses historically; measure 3M and 6M forward returns."""
    try:
        if sym not in dmas[50].columns or sym not in dmas[200].columns:
            return _empty_bt()
        d50  = dmas[50][sym].dropna()
        d200 = dmas[200][sym].dropna()
        if len(d50) < MIN_HIST or len(d200) < MIN_HIST:
            return _empty_bt()

        idx = d50.index.intersection(d200.index).intersection(series.dropna().index)
        if len(idx) < MIN_HIST:
            return _empty_bt()
        d50a, d200a, sera = d50.reindex(idx), d200.reindex(idx), series.reindex(idx)

        cross_up = (d50a > d200a) & (d50a.shift(1) <= d200a.shift(1))
        events = cross_up[cross_up].index

        r3m, r6m = [], []
        for dt in events:
            pos = idx.get_loc(dt)
            ep = float(sera.iloc[pos])
            if ep <= 0:
                continue
            if pos + 60 < len(sera):
                r3m.append(float(sera.iloc[pos + 60]) / ep - 1)
            if pos + 120 < len(sera):
                r6m.append(float(sera.iloc[pos + 120]) / ep - 1)

        def st(rets):
            if not rets:
                return None, None
            return round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1), round(float(np.mean(rets)) * 100, 1)

        wr3, ar3 = st(r3m)
        wr6, ar6 = st(r6m)
        return {"events": len(events), "win_rate_3m": wr3, "avg_ret_3m": ar3,
                "win_rate_6m": wr6, "avg_ret_6m": ar6}
    except Exception:
        return _empty_bt()


def _empty_bt():
    return {"events": 0, "win_rate_3m": None, "avg_ret_3m": None,
            "win_rate_6m": None, "avg_ret_6m": None}


def bt_score(bt):
    """0–20 score. Neutral 10 if insufficient history."""
    if bt["events"] < MIN_BACKTEST_EVENTS or bt["win_rate_3m"] is None:
        return 10
    return round(min(20, bt["win_rate_3m"] / 100 * 20))


# ── History + comprehensive crossover backtest ────────────────────────────────

def compute_history(sym, px_col, dmas, n=150):
    """Last n trading days of close + 4 DMA values for chart rendering."""
    try:
        s = px_col.dropna().iloc[-n:]
        idx = s.index
        def dma_arr(w):
            if sym not in dmas[w].columns:
                return [None] * len(idx)
            v = dmas[w][sym].reindex(idx)
            return [round(float(x), 2) if not np.isnan(float(x)) else None for x in v]
        return {
            "dates":  [str(d.date()) for d in idx],
            "closes": [round(float(x), 2) for x in s],
            "dma20":  dma_arr(20),
            "dma50":  dma_arr(50),
            "dma100": dma_arr(100),
            "dma200": dma_arr(200),
        }
    except Exception:
        return None


def find_crossover_events(sym, series, dmas):
    """All DMA crossover events in price history: golden/death/silver/bronze/platinum."""
    events = []
    try:
        s = series.dropna()
        if len(s) < 220:
            return events
        d50  = dmas[50][sym].dropna()  if sym in dmas[50].columns  else pd.Series(dtype=float)
        d200 = dmas[200][sym].dropna() if sym in dmas[200].columns else pd.Series(dtype=float)
        if len(d50) < 210 or len(d200) < 210:
            return events
        idx = s.index.intersection(d50.index).intersection(d200.index)
        sa, a50, a200 = s.reindex(idx), d50.reindex(idx), d200.reindex(idx)
        def _add(mask, ctype):
            for dt in idx[mask.fillna(False).to_numpy(bool)]:
                p = idx.get_loc(dt)
                events.append({"date": str(dt.date()), "type": ctype,
                               "close": round(float(sa.iloc[p]), 2)})
        _add((a50 > a200) & (a50.shift(1) <= a200.shift(1)), "golden")
        _add((a50 < a200) & (a50.shift(1) >= a200.shift(1)), "death")
        if sym in dmas[20].columns:
            a20 = dmas[20][sym].dropna().reindex(idx)
            _add((a20 > a50) & (a20.shift(1) <= a50.shift(1)), "silver")
            if sym in dmas[100].columns:
                a100 = dmas[100][sym].dropna().reindex(idx)
                plat = (sa > a20) & (a20 > a50) & (a50 > a100) & (a100 > a200)
                _add(plat & ~plat.shift(1).fillna(False), "platinum")
        _add((sa > a200) & (sa.shift(1) <= a200.shift(1)), "bronze")
        events.sort(key=lambda e: e["date"])
    except Exception:
        pass
    return events


def backtest_by_crossover_type(sym, series, dmas):
    """1M/3M/6M/1Y forward returns after each crossover type. Used for the chart backtest table."""
    result = {}
    try:
        s = series.dropna()
        if len(s) < 300:
            return result
        d50  = dmas[50][sym].dropna()  if sym in dmas[50].columns  else pd.Series(dtype=float)
        d200 = dmas[200][sym].dropna() if sym in dmas[200].columns else pd.Series(dtype=float)
        if len(d50) < 250 or len(d200) < 250:
            return result
        idx = s.index.intersection(d50.index).intersection(d200.index)
        sa, a50, a200 = s.reindex(idx), d50.reindex(idx), d200.reindex(idx)

        def _measure(mask):
            rets = {20: [], 60: [], 120: [], 250: []}
            n_events = int(mask.fillna(False).sum())
            for dt in idx[mask.fillna(False).to_numpy(bool)]:
                p = idx.get_loc(dt)
                ep = float(sa.iloc[p])
                if ep <= 0:
                    continue
                for fwd, lst in rets.items():
                    if p + fwd < len(sa):
                        lst.append(float(sa.iloc[p + fwd]) / ep - 1)
            def _s(lst):
                if len(lst) < 2:
                    return None, None
                w = sum(1 for r in lst if r > 0)
                return round(w / len(lst) * 100, 1), round(float(np.mean(lst)) * 100, 1)
            out = {"n": n_events}
            for fwd, label in [(20,"1m"), (60,"3m"), (120,"6m"), (250,"1y")]:
                w, a = _s(rets[fwd])
                out[f"win_{label}"] = w
                out[f"avg_{label}"] = a
            return out

        result["golden"] = _measure((a50 > a200) & (a50.shift(1) <= a200.shift(1)))
        result["death"]  = _measure((a50 < a200) & (a50.shift(1) >= a200.shift(1)))
        if sym in dmas[20].columns:
            a20 = dmas[20][sym].dropna().reindex(idx)
            result["silver"] = _measure((a20 > a50) & (a20.shift(1) <= a50.shift(1)))
        result["bronze"] = _measure((sa > a200) & (sa.shift(1) <= a200.shift(1)))
    except Exception:
        pass
    return result


# ── HHHL integration ──────────────────────────────────────────────────────────

HHHL_SCORE_MAP = {
    "uptrend": 20, "turning_up": 15, "ready_to_break": 12,
    "breakout_today": 18, "sideways": 5, "downtrend": 0,
}


def load_hhhl():
    for fname in ("hhhl_scan.json",):
        p = DOCS / fname
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                return {r["symbol"]: r for r in d.get("rows", [])}
            except Exception:
                pass
    return {}


# ── Full scoring ──────────────────────────────────────────────────────────────

def score_universe(px, dmas, hhhl_data, meta):
    """Score every stock 0–100. Returns list of row dicts, sorted descending."""
    rows = []
    for sym in px.columns:
        series = px[sym].dropna()
        if len(series) < 210:
            continue
        close = float(series.iloc[-1])

        cross_type, align_sc, gates, dv = classify_crossover(sym, series, dmas)
        cross_sc = CROSS_RECENCY_SCORE.get(cross_type, 0)

        hhhl = hhhl_data.get(sym, {})
        hhhl_cat = hhhl.get("category") or hhhl.get("trend_category") or "neutral"
        hhhl_sc = HHHL_SCORE_MAP.get(hhhl_cat, 0)

        bt = backtest_golden_cross(sym, series, dmas)
        bt_sc = bt_score(bt)

        total = min(100, align_sc + cross_sc + hhhl_sc + bt_sc)

        vol_series = np.log(series.iloc[-LONG - 1:]).diff().iloc[1:]
        vol = float(vol_series.std(ddof=0) * math.sqrt(252)) if len(vol_series) > 10 else None

        d200 = dv.get(200)

        # Chart history, crossover events, comprehensive backtest per type
        hist   = compute_history(sym, series, dmas, n=150)
        events = find_crossover_events(sym, series, dmas)
        bt_full = backtest_by_crossover_type(sym, series, dmas)

        rows.append({
            "symbol": sym,
            "name": meta.get(sym, {}).get("name", sym),
            "sector": meta.get(sym, {}).get("sector", "Other"),
            "total_score": total,
            "align_score": align_sc,
            "cross_score": cross_sc,
            "hhhl_score": hhhl_sc,
            "bt_score_pts": bt_sc,
            "crossover_type": cross_type,
            "close": round(close, 2),
            "dma20":  round(dv[20],  2) if dv.get(20)  else None,
            "dma50":  round(dv[50],  2) if dv.get(50)  else None,
            "dma100": round(dv[100], 2) if dv.get(100) else None,
            "dma200": round(dv[200], 2) if dv.get(200) else None,
            "above_200dma": bool(d200 and close > d200),
            "pct_above_200": round((close / d200 - 1) * 100, 1) if d200 else None,
            "vol_pct": round(vol * 100, 1) if vol else None,
            "hhhl_category": hhhl_cat,
            "hhhl_structure": hhhl.get("structure"),
            "bt_events": bt["events"],
            "bt_win_rate_3m": bt["win_rate_3m"],
            "bt_avg_ret_3m": bt["avg_ret_3m"],
            "bt_win_rate_6m": bt["win_rate_6m"],
            "bt_avg_ret_6m": bt["avg_ret_6m"],
            "history": hist,
            "crossover_events": events[-30:],
            "bt_by_type": bt_full,
        })

    rows.sort(key=lambda r: -r["total_score"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


# ── Portfolio ─────────────────────────────────────────────────────────────────

def zscore(x):
    sd = x.std(ddof=0)
    return (x - x.mean()) / sd if sd and np.isfinite(sd) else x * 0


def build_portfolio(scored_rows, guard_on, sip=1_000_000):
    """Top HOLDINGS by score; weight = score/vol; apply market guard."""
    cash_pct  = CASH_GUARD * 100 if guard_on else 0.0
    stock_pct = 100.0 - cash_pct

    eligible = [r for r in scored_rows
                if r["above_200dma"]
                and r["crossover_type"] not in ("bear", "death")
                and r["vol_pct"]][:HOLDINGS]

    if not eligible:
        return [], cash_pct, stock_pct

    syms = [r["symbol"] for r in eligible]
    scores = np.array([r["total_score"] for r in eligible], dtype=float)
    vols   = np.array([r["vol_pct"] for r in eligible], dtype=float)
    raw_w  = scores / np.maximum(vols, 1)
    w      = raw_w / raw_w.sum()

    # Cap at MAX_WEIGHT
    for _ in range(100):
        over = w > MAX_WEIGHT + 1e-12
        if not over.any():
            break
        excess = (w[over] - MAX_WEIGHT).sum()
        w[over] = MAX_WEIGHT
        room_mask = w < MAX_WEIGHT - 1e-12
        if room_mask.any():
            w[room_mask] += excess * w[room_mask] / w[room_mask].sum()

    w = w * (stock_pct / 100)

    holdings = []
    for i, r in enumerate(eligible):
        weight = float(w[i])
        alloc  = sip * weight
        close  = r["close"]
        shares = int(alloc // close) if close > 0 else 0
        holdings.append({
            "rank": i + 1,
            "symbol": r["symbol"],
            "name": r["name"],
            "sector": r["sector"],
            "weight_pct": round(weight * 100, 2),
            "alloc_rs": round(alloc),
            "shares": shares,
            "close": close,
            "crossover_type": r["crossover_type"],
            "total_score": r["total_score"],
            "dma20": r["dma20"], "dma50": r["dma50"],
            "dma100": r["dma100"], "dma200": r["dma200"],
            "pct_above_200": r["pct_above_200"],
            "hhhl_category": r["hhhl_category"],
            "bt_events": r["bt_events"],
            "bt_win_rate_3m": r["bt_win_rate_3m"],
            "bt_avg_ret_3m": r["bt_avg_ret_3m"],
        })

    return holdings, cash_pct, stock_pct


# ── Main build ────────────────────────────────────────────────────────────────

def build():
    universe = load_universe()
    meta = {u["symbol"]: u for u in universe}
    symbols = [u["symbol"] for u in universe]
    print(f"Universe: {len(universe)} stocks")

    print("Loading prices…")
    px = load_prices(symbols)
    if px.empty:
        raise SystemExit("No price data available; check data/hhhl_prices/")
    print(f"Prices: {len(px.columns)} stocks")

    dmas = compute_dmas(px)
    hhhl_data = load_hhhl()
    print(f"HHHL data: {len(hhhl_data)} stocks")

    print("Scoring…")
    scored = score_universe(px, dmas, hhhl_data, meta)

    guard_on = get_nifty50_guard()
    print(f"Nifty 50 guard: {'ON (50% cash)' if guard_on else 'OFF (fully invested)'}")

    holdings, cash_pct, stock_pct = build_portfolio(scored, guard_on)

    cross_counts = {}
    for r in scored:
        cross_counts[r["crossover_type"]] = cross_counts.get(r["crossover_type"], 0) + 1

    today = datetime.now().strftime("%Y-%m-%d")
    payload = {
        "version": 1,
        "name": "Value Lens DMA Intelligence Desk",
        "as_of": today,
        "universe": "Nifty 500",
        "covered": len(scored),
        "portfolio": {
            "guard_on": guard_on,
            "cash_pct": cash_pct,
            "stock_pct": stock_pct,
            "holdings_count": len(holdings),
            "guard_words": ("Nifty 50 below its 200-DMA — 50% in liquid fund this month."
                            if guard_on else "Nifty 50 above its 200-DMA — fully invested."),
        },
        "holdings": holdings,
        "crossover_summary": {t: cross_counts.get(t, 0)
                              for t in ("platinum","golden","silver","bronze","watch","neutral","bear","death")},
        "score_method": [
            "DMA alignment (35 pts): 5 pts each — close>200DMA, close>100DMA, close>50DMA, close>20DMA, 100>200, 50>100, 20>50.",
            "Crossover recency (25 pts): platinum=25, golden=20, silver=15, bronze=10, watch=5.",
            "HHHL trend confirmation (20 pts): uptrend=20, breakout_today=18, turning_up=15, ready_to_break=12, sideways=5, downtrend=0.",
            "Backtest win rate (20 pts): 3M forward win rate × 20; neutral 10 pts if fewer than 5 historical golden crossovers.",
        ],
        "rules": [
            "Eligible: close above 200-DMA and not in bear/death crossover.",
            "Weight: score ÷ annualised volatility, capped at 6% per stock.",
            "Market guard: if Nifty 50 closes below its 200-DMA, 50% is kept in a liquid fund.",
            "Daily exit: any held stock closing below its 200-DMA is sold at the next session open.",
            "Monthly rebalance: last trading session of each month picks a fresh top-30.",
        ],
        "limits": [
            "Survivorship bias: Nifty 500 membership uses today's list back in time.",
            "Backtest uses the same daily closes used for signals — no out-of-sample test.",
            "Crossover detection is end-of-day; execution at next-session open adds slippage.",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
        "rows": [{k: (None if (isinstance(v, float) and not math.isfinite(v)) else v)
                  for k, v in r.items()} for r in scored],
    }

    text = json.dumps(payload, separators=(",", ":"), default=str)
    DOCS.mkdir(exist_ok=True)
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    (DOCS / "dma.json").write_text(text, encoding="utf-8")
    (PUBLIC_DATA / "dma.json").write_text(text, encoding="utf-8")

    top3 = scored[:3]
    print(
        f"dma.json {today}: {len(scored)} scored | "
        f"🏆{cross_counts.get('platinum',0)} 🥇{cross_counts.get('golden',0)} "
        f"🥈{cross_counts.get('silver',0)} 🥉{cross_counts.get('bronze',0)} "
        f"📉{cross_counts.get('bear',0)+cross_counts.get('death',0)} | "
        f"portfolio {len(holdings)} stocks + {cash_pct:.0f}% cash | "
        f"top: {', '.join(r['symbol'] for r in top3)}"
    )
    return payload


if __name__ == "__main__":
    build()
