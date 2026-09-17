#!/usr/bin/env python3
"""
NSE 12-1 Momentum Screener
==========================
Methodology (NSE momentum research consensus, e.g. ftInvstr 2026 / Nifty200 Momentum 30):
  universe  : NIFTY 200 constituents (Series == EQ), source: nifty200.csv (NSE archives)
  signal    : 12-month price momentum skipping the most recent month
              mom_12_1 = close(t - skip) / close(t - lookback) - 1  (sessions)
  filter    : close > 200-day SMA (trend filter; --no-trend-filter disables)
  rebalance : monthly (run this script monthly)
Data  : jugaad-data (NSE direct, primary); yfinance (.NS) per-symbol fallback
Outputs (./screen_output/):
  momentum_<date>.csv    ranked screening table
  openalgo_basket.json   OpenAlgo /api/v1/basketorder-compatible payload (quantity=1 placeholder)
  openalgo_symbols.txt   plain NSE symbols for OpenAlgo watchlist
CLI:
  python momentum_screener.py [--top 25] [--lookback 252] [--skip 21] [--workers 4]
                              [--no-trend-filter] [--limit N]
"""
import argparse
import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
UNIVERSE_CSV = HERE / "nifty200.csv"
OUT_DIR = HERE / "screen_output"
FETCH_DAYS = 560  # calendar days of history (~380 sessions; need lookback+skip+buffer)


def load_universe():
    rows = list(csv.DictReader(open(UNIVERSE_CSV, newline="", encoding="utf-8-sig")))
    eq = [r for r in rows if r.get("Series", "EQ").strip() == "EQ"]
    return [(r["Symbol"].strip(), r.get("Company Name", "").strip()) for r in eq]


def fetch_jugaad(symbol, start, end):
    """Primary: NSE direct via jugaad-data. Returns ascending date/close/volume lists."""
    from jugaad_data.nse import stock_df

    last_err = None
    for attempt in range(2):
        try:
            df = stock_df(symbol=symbol, from_date=start, to_date=end, series="EQ")
            if df is None or len(df) == 0:
                raise ValueError("empty frame")
            df = df.sort_values("DATE")
            return {
                "date": [pd.Timestamp(d).date() for d in df["DATE"]],
                "close": [float(x) for x in df["CLOSE"]],
                "volume": [float(x) for x in df.get("VOLUME", [0] * len(df))],
            }
        except Exception as e:  # noqa: BLE001 - any NSE-side error -> retry once, then fallback
            last_err = e
            time.sleep(1.0 + attempt)
    raise RuntimeError(f"jugaad failed: {last_err}")


def fetch_yfinance(symbol, start, end):
    """Fallback: Yahoo Finance .NS (auto-adjusted)."""
    import yfinance as yf

    df = yf.download(symbol + ".NS", start=start, end=end + timedelta(days=1),
                     progress=False, auto_adjust=True, threads=False)
    if df is None or len(df) == 0:
        raise RuntimeError("yfinance empty")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return {
        "date": [pd.Timestamp(d).date() for d in df.index],
        "close": [float(x) for x in df["Close"]],
        "volume": [float(x) for x in df["Volume"]],
    }


def analyse(symbol, name, lookback, skip):
    start, end = date.today() - timedelta(days=FETCH_DAYS), date.today()
    time.sleep(0.15)  # be polite to NSE
    data, source = None, None
    try:
        data, source = fetch_jugaad(symbol, start, end), "jugaad"
    except Exception:  # noqa: BLE001
        try:
            data, source = fetch_yfinance(symbol, start, end), "yfinance"
        except Exception:  # noqa: BLE001
            return None
    closes, vols, dates = data["close"], data["volume"], data["date"]
    need = lookback + skip + 5
    if len(closes) < need:
        return None
    t = len(closes) - 1
    mom_12_1 = closes[t - skip] / closes[t - lookback] - 1.0
    mom_6_1 = closes[t - skip] / closes[t - 126] - 1.0 if t >= 147 else float("nan")
    dma200 = sum(closes[-200:]) / 200.0 if len(closes) >= 200 else float("nan")
    above200 = bool(closes[t] > dma200) if dma200 == dma200 else False
    turn20 = sum(c * v for c, v in zip(closes[-20:], vols[-20:])) / 20.0
    return {
        "symbol": symbol, "name": name, "mom_12_1": mom_12_1, "mom_6_1": mom_6_1,
        "close": closes[t], "dma200": dma200, "above200dma": above200,
        "turnover20d_inr": turn20, "last_bar": dates[t].isoformat(),
        "source": source, "bars": len(closes),
    }


def main():
    ap = argparse.ArgumentParser(description="NSE 12-1 momentum screener (NIFTY 200)")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--lookback", type=int, default=252)
    ap.add_argument("--skip", type=int, default=21)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-trend-filter", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="debug: only first N symbols")
    a = ap.parse_args()

    universe = load_universe()
    if a.limit:
        universe = universe[: a.limit]
    print(f"universe: {len(universe)} NIFTY-200 EQ symbols | "
          f"lookback={a.lookback} skip={a.skip} workers={a.workers}")

    results, failed = [], 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(analyse, s, n, a.lookback, a.skip): s for s, n in universe}
        for i, fut in enumerate(as_completed(futs), 1):
            row = fut.result()
            if row:
                results.append(row)
            else:
                failed += 1
            if i % 25 == 0:
                print(f"  ...{i}/{len(universe)} done ({failed} failed)")

    df = pd.DataFrame(results)
    if len(df) == 0:
        raise SystemExit("no data for any symbol - check network/NSE reachability")
    n_jugaad = int((df.source == "jugaad").sum())
    print(f"data ok: {len(df)} ({n_jugaad} via jugaad-data, "
          f"{len(df) - n_jugaad} via yfinance) | failed: {failed}")

    screened = df if a.no_trend_filter else df[df.above200dma]
    screened = screened.sort_values("mom_12_1", ascending=False).head(a.top).reset_index(drop=True)
    screened.insert(0, "rank", screened.index + 1)

    OUT_DIR.mkdir(exist_ok=True)
    stamp = date.today().isoformat()
    csv_path = OUT_DIR / f"momentum_{stamp}.csv"
    screened.to_csv(csv_path, index=False)

    (OUT_DIR / "openalgo_symbols.txt").write_text("\n".join(screened.symbol) + "\n")

    basket = {
        "strategy": f"NSE_12_1_MOMENTUM_{stamp}",
        "_note": ("Template payload for OpenAlgo POST /api/v1/basketorder. "
                  "quantity=1 placeholder - apply your own position sizing "
                  "(e.g. <=5% NAV/name) and risk controls before any execution."),
        "orders": [
            {"symbol": r.symbol, "exchange": "NSE", "action": "BUY",
             "product": "CNC", "pricetype": "MARKET", "quantity": 1,
             "price": 0, "trigger_price": 0, "disclosed_quantity": 0}
            for r in screened.itertuples()
        ],
    }
    json_path = OUT_DIR / "openalgo_basket.json"
    json_path.write_text(json.dumps(basket, indent=2))

    cols = ["rank", "symbol", "mom_12_1", "mom_6_1", "close", "dma200", "above200dma", "last_bar", "source"]
    show = screened[cols].copy()
    show[["mom_12_1", "mom_6_1"]] = (show[["mom_12_1", "mom_6_1"]] * 100).round(1)
    print("\n=== SCREEN OUTPUT (as of", stamp, ") ===")
    print(show.head(10).to_string(index=False))
    print(f"\nfull table: {csv_path}")
    print(f"openalgo symbols: {OUT_DIR / 'openalgo_symbols.txt'}")
    print(f"openalgo basket payload: {json_path}")


if __name__ == "__main__":
    main()
