"""Refresh swing desk and compare fixed rules. Run: python swing_research.py [--cached]."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
import csv
import json
import pandas as pd
import yfinance as yf
from swing_engine import features, setup, backtest, STRATEGIES

ROOT = Path(__file__).resolve().parent
CACHE = ROOT/".cache"/"swing"
IST = timezone(timedelta(hours=5, minutes=30))

def clean(frame, now=None):
    now = now or datetime.now(IST)
    d = frame[["Open", "High", "Low", "Close", "Volume"]].copy()
    d.index = pd.to_datetime([str(x.date()) for x in d.index])
    d = d[~d.index.duplicated(keep="last")].sort_index().dropna()
    # Reject incomplete current candle and impossible OHLC rows.
    cutoff = now.date() if now.hour >= 16 else now.date()-timedelta(days=1)
    d = d[d.index.date <= cutoff]
    d = d[(d[["Open", "High", "Low", "Close"]] > 0).all(axis=1) &
          (d.High >= d[["Open", "Close", "Low"]].max(axis=1)) &
          (d.Low <= d[["Open", "Close"]].min(axis=1)) & (d.Volume >= 0)]
    return d

def fetch(symbol, cached):
    file = CACHE/(symbol.replace("^", "")+".csv")
    if cached:
        if not file.exists():
            raise ValueError("cache missing")
        return clean(pd.read_csv(file, index_col=0, parse_dates=True))
    raw = yf.Ticker(symbol).history(period="5y", auto_adjust=True, actions=False, timeout=30)
    d = clean(raw)
    if len(d) < 210:
        raise ValueError("fewer than 210 complete bars")
    d.to_csv(file)
    return d

def publish(name, payload):
    text = json.dumps(payload, allow_nan=False, separators=(",", ":"))
    for directory in [ROOT/"screen_output", ROOT/"docs", ROOT/"public"/"data"]:
        directory.mkdir(parents=True, exist_ok=True)
        temp = directory/(name+".json.tmp")
        temp.write_text(text, encoding="utf-8")
        temp.replace(directory/(name+".json"))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cached", action="store_true")
    parser.add_argument("--scan-only", action="store_true")
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    universe = list(csv.DictReader((ROOT/"nifty200.csv").open(encoding="utf-8-sig")))
    symbols = sorted({r["Symbol"] for r in universe if r.get("Series", "EQ") == "EQ"})
    sectors = {r["Symbol"]: r.get("Industry", "Unknown") for r in universe}
    names = {r["Symbol"]: r.get("Company Name", r["Symbol"]) for r in universe}
    market = features(fetch("^NSEI", args.cached))
    asof = market.index[-1]
    frames, failures = {}, {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch, s+".NS", args.cached): s for s in symbols}
        for f in as_completed(futures):
            s = futures[f]
            try:
                data = f.result()
                frames[s] = features(data.loc[:asof])
            except Exception as exc:
                failures[s] = str(exc)[:150]
            if (len(frames)+len(failures)) % 25 == 0:
                print(f"Fetched {len(frames)} / {len(symbols)}; unavailable {len(failures)}", flush=True)
    if len(frames) < .9*len(symbols):
        raise RuntimeError("Under 90% universe coverage; keeping previous snapshots")
    date_string = str(asof.date())
    fresh = {s:f for s,f in frames.items() if len(f) and f.index[-1] == asof}
    candidates = []
    for s, f in fresh.items():
        for strategy in STRATEGIES:
            plan = setup(f.iloc[-1], market.iloc[-1], strategy)
            if plan:
                candidates.append(dict(plan, symbol=s, name=names.get(s,s), sector=sectors[s]))
    candidates.sort(key=lambda p: (-p["relative_strength"], p["symbol"], p["strategy"]))
    risk_on = bool(market.iloc[-1].Close > market.iloc[-1].sma50 > market.iloc[-1].sma200)
    limitations = [
        "Research only: no strategy is validated for live capital.",
        "Uses current Nifty 200 membership, not historical membership; survivorship bias remains.",
        "Yahoo adjusted daily OHLCV, not exchange-verified execution data. Corporate actions may need review.",
        "Daily bars cannot resolve intraday order, circuit locks, spread or actual fills. Stop-first convention is conservative, not certainty.",
        "No earnings calendar gate. Check upcoming results and corporate actions before any manual trade.",
        "Historical windows are retrospective diagnostics, not an untouched prospective test.",
    ]
    payload = {"version": 1, "as_of": date_string, "generated_at": datetime.now(IST).isoformat(),
        "validated": False, "mode": "PAPER RESEARCH", "market": {"risk_on": risk_on,
        "close": float(market.iloc[-1].Close), "sma50": float(market.iloc[-1].sma50),
        "sma200": float(market.iloc[-1].sma200)},
        "universe_count": len(symbols), "fresh_count": len(fresh), "failures": failures,
        "stale_symbols": sorted(set(frames)-set(fresh)), "candidates": candidates,
        "strategies": STRATEGIES, "limitations": limitations,
        "rules": {"risk_pct": .5, "max_position_pct": 20, "max_positions": 5,
                  "max_same_industry": 2, "fee_per_side_pct": .15, "slippage_per_side_pct": .05,
                  "min_turnover_crore": 10, "entry": "Next session open only within displayed band; otherwise cancel.",
                  "exit": "2 ATR initial stop, 2R target from actual fill; time exit after 5, 10 or 20 sessions. Stop may fill worse on gaps."}}
    publish("swing_desk", payload)
    if args.scan_only:
        return
    dates = market.index
    if len(dates) < 800:
        raise ValueError("Need at least 800 benchmark bars for separated research windows")
    split = str(dates[-252].date())
    windows = {"earlier": (str(dates[210].date()), str(dates[-253].date())),
               "recent": (split, date_string)}
    report = {"as_of": date_string, "validated": False, "limitations": limitations,
              "universe_count": len(frames), "windows": windows, "results": {},
              "cost_note": "0.15% fees/taxes assumption plus 0.05% slippage per side; stress doubles both. Broker-specific charges and fixed DP fees are not replicated.",
              "benchmark_note": "Nifty 50 price return, no dividends; portfolio has variable cash exposure. This is not a risk-matched alpha test."}
    for strategy in STRATEGIES:
        report["results"][strategy] = {}
        for label, (start, end) in windows.items():
            result = backtest(frames, market, sectors, strategy, start, end)
            report["results"][strategy][label] = result
            print(f'{strategy} {label}: {result["return_pct"]}% / {result["trades"]} closed trades', flush=True)
        report["results"][strategy]["stress"] = backtest(frames, market, sectors, strategy, *windows["recent"], cost_scale=2)
    publish("swing_evidence", report)
    print(f"Published {len(candidates)} paper setups, market risk_on={risk_on}, data={date_string}", flush=True)

if __name__ == "__main__":
    main()
