#!/usr/bin/env python3
"""Momentum 30 Daily — Nifty 200 Momentum 30 style ranking with daily auto-refresh.

Uses fresh daily OHLCV (same source as daily_sr.py) to compute:
- 6-month and 12-month price returns
- Annualized volatility (252d log-return std * sqrt(252))
- Vol-adjusted momentum score = 0.5*z(6m/vol) + 0.5*z(12m/vol)
- Ranks top 30, assigns BUY/WATCH_BUY/NEUTRAL/AVOID signals
- Outputs to screen_output/momentum30_daily.json + docs/momentum30_daily.json

Designed to run in daily_sr.yml after daily_sr.py so it uses fresh same-day prices.
"""
from __future__ import annotations

import csv
import json
import math
from datetime import date, datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import yfinance as yf

HERE = Path(__file__).resolve().parent
OUT = HERE / "screen_output"
DOCS = HERE / "docs"
UNIV = HERE / "nifty200.csv"

WORKERS = 12
TOP_N = 30
TRADING_DAYS_6M = 126
TRADING_DAYS_12M = 252
VOL_DAYS = 252
MIN_DAYS = 126  # need at least 6 months for any momentum

SIGNAL_MAP = {
    "BUY": "#3fb950",
    "WATCH_BUY": "#58a6ff",
    "NEUTRAL": "#8b949e",
    "AVOID": "#f778ba",
}


def fetch_ohlcv(symbol: str) -> list[dict] | None:
    """Fetch 1y daily OHLCV for one symbol via yfinance."""
    try:
        t = yf.Ticker(symbol + ".NS")
        df = t.history(period="1y", interval="1d", actions=False, auto_adjust=True)
        if df.empty or len(df) < 126:  # need at least 6 months
            return None
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
        if getattr(df.index, "tz", None) is not None:
            df.index = df.index.tz_convert(None)
        df = df.reset_index()
        return df.to_dict("records")
    except Exception:
        return None


def compute_metrics(records: list[dict]) -> dict | None:
    """Compute momentum metrics from OHLCV records."""
    n = len(records)
    if n < TRADING_DAYS_6M:
        return None

    closes = np.array([r["Close"] for r in records], dtype=float)
    dates = [datetime.fromisoformat(r["Date"]) if isinstance(r.get("Date"), str) else
             r["Date"] for r in records]

    mom6 = closes[-1] / closes[-TRADING_DAYS_6M] - 1.0
    mom12 = closes[-1] / closes[-TRADING_DAYS_12M] - 1.0 if len(closes) >= TRADING_DAYS_12M else None

    # Annualized volatility (log returns, need 252d)
    if len(closes) >= VOL_DAYS + 1:
        rets = np.diff(np.log(closes[-(VOL_DAYS + 1):]))
        vol = float(np.std(rets, ddof=0) * math.sqrt(252))
    else:
        # fallback: use available data, min 60 days
        rets = np.diff(np.log(closes))
        if len(rets) < 60:
            return None
        vol = float(np.std(rets, ddof=0) * math.sqrt(252))

    if vol <= 0 or not math.isfinite(vol):
        return None

    return {
        "close": float(records[-1]["Close"]),
        "mom6": float(mom6),
        "mom12": float(mom12) if mom12 is not None else None,
        "vol": vol,
        "date": dates[-1].date().isoformat(),
    }


def process_symbol(symbol: str) -> tuple[str, dict | None]:
    recs = fetch_ohlcv(symbol)
    if recs is None:
        return symbol, None
    return symbol, compute_metrics(recs)


def zscore(values: dict[str, float]) -> dict[str, float]:
    xs = np.array([v for v in values.values() if math.isfinite(v)])
    if len(xs) < 5:
        return {k: 0.0 for k in values}
    mu = float(xs.mean())
    sd = float(xs.std(ddof=0)) or 1.0
    return {k: (v - mu) / sd if math.isfinite(v) else -99.0 for k, v in values.items()}


def assign_signal(rank: int, total: int) -> str:
    """Map rank (1-based) to signal."""
    if rank <= 10:
        return "BUY"
    if rank <= 20:
        return "WATCH_BUY"
    if rank <= total:
        return "NEUTRAL"
    return "AVOID"


def main() -> None:
    # Load Nifty 200 EQ symbols
    rows = list(csv.DictReader(open(UNIV, newline="", encoding="utf-8-sig")))
    syms = [(r["Symbol"].strip(), r.get("Company Name", "").strip())
            for r in rows if r.get("Series", "EQ").strip() == "EQ"]
    print(f"Fetching fresh OHLCV for {len(syms)} Nifty 200 EQ stocks...")

    # Fetch fresh OHLCV for all symbols
    metrics = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(process_symbol, s): s for s, _ in syms}
        for fut in futures:
            s = futures[fut]
            res = fut.result()
            if res[1] is not None and res[1]["vol"] is not None:
                metrics[s] = res[1]

    print(f"Computed metrics for {len(metrics)} stocks")

    # Build vol-adjusted momentum scores
    m6_scores = {s: m["mom6"] / m["vol"] for s, m in metrics.items()}
    m12_scores = {s: m["mom12"] / m["vol"] for s, m in metrics.items() if m["mom12"] is not None}

    z6 = zscore(m6_scores)
    z12 = zscore(m12_scores)

    ranked = []
    for s in metrics:
        score = 0.5 * z6.get(s, -99.0) + 0.5 * z12.get(s, -99.0)
        ranked.append((score, s))

    ranked.sort(key=lambda x: x[0], reverse=True)
    top30 = ranked[:TOP_N]

    # Build output
    as_of = date.today().isoformat()
    holdings = []
    for i, (score, sym) in enumerate(top30, 1):
        m = metrics[sym]
        action = assign_signal(i, TOP_N)
        holdings.append({
            "rank": i,
            "symbol": sym,
            "company": next(n for s, n in syms if s == sym),
            "signal": action,
            "color": SIGNAL_MAP[action],
            "score": round(score, 4),
            "z6": round(z6.get(sym, 0), 4),
            "z12": round(z12.get(sym, 0), 4),
            "mom6_pct": round(m["mom6"] * 100, 2),
            "mom12_pct": round(m["mom12"] * 100, 2) if m["mom12"] is not None else None,
            "vol_pct": round(m["vol"] * 100, 2),
            "close": round(m["close"], 2),
            "price_date": m["date"],
            "formula": "score = 0.5*z(mom6/vol) + 0.5*z(mom12/vol); vol = std(log_ret, 252d)*sqrt(252); mom6 = P/P_126-1; mom12 = P/P_252-1"
        })

    output = {
        "as_of": date.today().isoformat(),
        "universe": "Nifty 200 EQ (~194 stocks)",
        "method": "Nifty 200 Momentum 30 style: 0.5*z(6m_return/annualised_vol) + 0.5*z(12m_return/annualised_vol); fresh daily yfinance OHLCV",
        "top_n": TOP_N,
        "holdings": holdings,
        "note": "Approximation — official Nifty200 Momentum 30 uses free-float factor weights and semi-annual rebalance; this is a daily-refresh proxy."
    }

    OUT.mkdir(exist_ok=True)
    (OUT / "momentum30_daily.json").write_text(json.dumps(output, indent=1), encoding="utf-8")
    DOCS.mkdir(exist_ok=True)
    (DOCS / "momentum30_daily.json").write_text(json.dumps(output, indent=1), encoding="utf-8")

    print(f"Written: screen_output/momentum30_daily.json, docs/momentum30_daily.json")
    print(f"Top 10: {[h['symbol'] for h in holdings[:10]]}")
    print(f"Actions: BUY={sum(1 for h in holdings if h['signal']=='BUY')}, WATCH_BUY={sum(1 for h in holdings if h['signal']=='WATCH_BUY')}, NEUTRAL={sum(1 for h in holdings if h['signal']=='NEUTRAL')}, AVOID={sum(1 for h in holdings if h['signal']=='AVOID')}")


if __name__ == "__main__":
    main()