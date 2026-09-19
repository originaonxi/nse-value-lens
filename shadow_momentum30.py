#!/usr/bin/env python3
"""Survivor-biased Shadow Nifty200 Momentum 30 scaffold.

Purpose: predict the past first. At each historical rebalance date this script
uses prices available on or before that date, forms a top-30 momentum portfolio,
and evaluates the next holding window.

Current limitation: screen_output/bt_ohlcv_cache.pkl has today's surviving 194
stocks and only ~2 years of data. That means this is NOT leakage-safe enough for
claims: it is a scaffold/smoke test. Final research must reconstruct historical
Nifty 200 membership and include delisted/removed names to avoid survivorship
bias, then validate against official Momentum 30 constituent history.
"""
from __future__ import annotations

import json
import math
import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "screen_output" / "bt_ohlcv_cache.pkl"
OUT = ROOT / "screen_output" / "shadow_momentum30.json"
DOCS_OUT = ROOT / "docs" / "shadow_momentum30.json"
CAPITAL = 1_00_00_000
COST_BPS_ROUND_TRIP = 0.0020
TOP_N = 30
TRADING_DAYS_6M = 126
TRADING_DAYS_12M = 252
VOL_DAYS = 252


@dataclass(frozen=True)
class Contract:
    name: str = "NSE 200 Momentum 30 Algorithm Prediction"
    mode: str = "research/backtest scaffold only"
    date_leakage_guard: str = "Each rebalance uses only prices available on or before that date."
    survivorship_warning: str = "This scaffold still uses current surviving symbols; final claims require point-in-time Nifty 200 universe plus delisted names."
    no_return_promise: str = "No 30-100% or must-make-money claim is encoded; real orders require separate manual enablement after verified walk-forward validation."


def clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_convert(None)
    out = out.sort_index()
    return out[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])


def load_data() -> dict[str, pd.DataFrame]:
    data = pickle.loads(CACHE.read_bytes())
    return {s: clean_frame(df) for s, df in data.items() if len(df) >= TRADING_DAYS_12M + 5}


def common_calendar(data: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    # Use the most complete symbol as the trading calendar anchor.
    master = max(data.values(), key=len)
    return master.index


def zscore(values: dict[str, float]) -> dict[str, float]:
    xs = np.array([v for v in values.values() if math.isfinite(v)], dtype=float)
    if len(xs) < 5:
        return {k: 0.0 for k in values}
    mu = float(xs.mean())
    sd = float(xs.std(ddof=0)) or 1.0
    return {k: (v - mu) / sd if math.isfinite(v) else -99.0 for k, v in values.items()}


def score_on_date(data: dict[str, pd.DataFrame], as_of: pd.Timestamp) -> list[dict]:
    raw6: dict[str, float] = {}
    raw12: dict[str, float] = {}
    stats: dict[str, dict] = {}
    for sym, df in data.items():
        hist = df[df.index <= as_of]
        if len(hist) <= TRADING_DAYS_12M:
            continue
        c = hist["Close"].to_numpy(dtype=float)
        ret = np.diff(np.log(c[-(VOL_DAYS + 1):]))
        vol = float(np.std(ret, ddof=0) * math.sqrt(252)) if len(ret) >= VOL_DAYS else float("nan")
        if not math.isfinite(vol) or vol <= 0:
            continue
        mom6 = c[-1] / c[-TRADING_DAYS_6M] - 1.0
        mom12 = c[-1] / c[-TRADING_DAYS_12M] - 1.0
        raw6[sym] = mom6 / vol
        raw12[sym] = mom12 / vol
        stats[sym] = {"close": float(c[-1]), "mom6": float(mom6), "mom12": float(mom12), "vol": vol}
    z6 = zscore(raw6)
    z12 = zscore(raw12)
    rows = []
    for sym in stats:
        score = 0.5 * z6.get(sym, -99.0) + 0.5 * z12.get(sym, -99.0)
        row = {"symbol": sym, "score": round(score, 6), "z6": round(z6.get(sym, 0.0), 6), "z12": round(z12.get(sym, 0.0), 6)}
        row.update({k: round(v, 6) for k, v in stats[sym].items()})
        rows.append(row)
    return sorted(rows, key=lambda r: r["score"], reverse=True)


def month_end_rebalance_dates(cal: pd.DatetimeIndex) -> list[pd.Timestamp]:
    usable = cal[TRADING_DAYS_12M:]
    if len(usable) == 0:
        return []
    s = pd.Series(usable, index=usable)
    dates = list(s.groupby([usable.year, usable.month]).max())
    # Need a next month to test forward return.
    return dates[:-1]


def next_date(cal: pd.DatetimeIndex, d: pd.Timestamp, months_forward: int = 1) -> pd.Timestamp | None:
    target = d + pd.DateOffset(months=months_forward)
    nxt = cal[cal >= target]
    return None if len(nxt) == 0 else nxt[0]


def portfolio_return(data: dict[str, pd.DataFrame], symbols: list[str], start: pd.Timestamp, end: pd.Timestamp) -> tuple[float, int]:
    rets = []
    for sym in symbols:
        df = data[sym]
        a = df[df.index <= start]
        b = df[df.index <= end]
        if len(a) == 0 or len(b) == 0:
            continue
        p0 = float(a.iloc[-1]["Close"])
        p1 = float(b.iloc[-1]["Close"])
        if p0 > 0:
            rets.append(p1 / p0 - 1.0)
    if not rets:
        return 0.0, 0
    return float(np.mean(rets) - COST_BPS_ROUND_TRIP), len(rets)


def run_walk_forward(data: dict[str, pd.DataFrame], cal: pd.DatetimeIndex) -> dict:
    rebalances = month_end_rebalance_dates(cal)
    periods = []
    equity = CAPITAL
    peak = CAPITAL
    maxdd = 0.0
    last_top: set[str] = set()
    for d in rebalances:
        end = next_date(cal, d, months_forward=1)
        if end is None:
            continue
        ranked = score_on_date(data, d)
        top = [r["symbol"] for r in ranked[:TOP_N]]
        ret, held = portfolio_return(data, top, d, end)
        turnover = len(set(top) - last_top) / TOP_N if last_top else 1.0
        last_top = set(top)
        equity *= 1.0 + ret
        peak = max(peak, equity)
        maxdd = max(maxdd, (peak - equity) / peak)
        periods.append({
            "rebalance": str(d.date()),
            "hold_to": str(end.date()),
            "ret_pct": round(ret * 100, 2),
            "equity": round(equity, 2),
            "turnover_pct": round(turnover * 100, 1),
            "held": held,
            "top5": top[:5],
        })
    total_ret = equity / CAPITAL - 1.0
    years = max(len(periods) / 12.0, 1 / 12)
    cagr = (equity / CAPITAL) ** (1 / years) - 1.0
    wins = [p for p in periods if p["ret_pct"] > 0]
    return {
        "periods": periods,
        "months": len(periods),
        "final_equity": round(equity, 2),
        "total_ret_pct": round(total_ret * 100, 2),
        "approx_cagr_pct": round(cagr * 100, 2),
        "win_months_pct": round(len(wins) / len(periods) * 100, 1) if periods else 0,
        "max_drawdown_pct": round(maxdd * 100, 2),
    }


def main() -> None:
    data = load_data()
    cal = common_calendar(data)
    latest = cal[-1]
    latest_rank = score_on_date(data, latest)
    walk = run_walk_forward(data, cal)
    out = {
        "as_of": str(latest.date()),
        "contract": Contract().__dict__,
        "method": {
            "universe": f"{len(data)} current cached symbols with >=252 trading days (survivor-biased scaffold)",
            "score": "0.5*z(6m_return/annualised_vol) + 0.5*z(12m_return/annualised_vol)",
            "rebalance_test": "monthly scaffold, equal-weight top 30, 0.20% round-trip cost",
            "official_gap": "Official index uses point-in-time Nifty 200 eligibility, free-float/factor-tilt weights and semi-annual rebalances; production validation must compare predicted past constituents against official constituent history.",
        },
        "latest_top30": latest_rank[:TOP_N],
        "walk_forward_scaffold": walk,
        "verdict": "Survivor-biased scaffold only. Do not use for claims or real money until point-in-time universe and official constituent validation are added.",
    }
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    DOCS_OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"months={walk['months']} total={walk['total_ret_pct']}% cagr={walk['approx_cagr_pct']}% maxdd={walk['max_drawdown_pct']}%")
    print("top10", ", ".join(r["symbol"] for r in latest_rank[:10]))


if __name__ == "__main__":
    main()
