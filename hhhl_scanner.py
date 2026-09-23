"""Dated HH/HL classification for every Nifty 200 constituent.

Uses the confirmed-pivot and Wilder ATR implementations from indicator_research.
This is a scan, not a backtest or an order generator.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from indicator_research import confirmed_structure, cross, wilder
from swing_research import publish

ROOT = Path(__file__).resolve().parent
STATUSES = ("BUY", "SELL", "WATCH", "CAUTION", "AVOID")
OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def number(value, digits=4):
    return round(float(value), digits) if value is not None and np.isfinite(float(value)) else None


def read_prices(path, as_of):
    raw = pd.read_csv(path, index_col=0, parse_dates=True)
    raw.index = pd.to_datetime([str(pd.Timestamp(d).date()) for d in raw.index])
    raw = raw.loc[raw.index <= pd.Timestamp(as_of), OHLCV]
    raw = raw[~raw.index.duplicated(keep="last")].sort_index()
    for col in OHLCV:
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    valid = (
        raw[OHLCV].notna().all(axis=1)
        & (raw[["Open", "High", "Low", "Close"]] > 0).all(axis=1)
        & (raw.High >= raw[["Open", "Close", "Low"]].max(axis=1))
        & (raw.Low <= raw[["Open", "Close"]].min(axis=1))
        & (raw.Volume >= 0)
    )
    invalid_dates = [str(x.date()) for x in raw.index[~valid]]
    return raw.loc[valid].copy(), invalid_dates


def feature_frame(frame):
    d = frame.copy()
    c, h, l = d.Close, d.High, d.Low
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    d["atr"] = wilder(tr, 14)
    d["turnover"] = (c*d.Volume).rolling(20).mean()
    d = d.join(confirmed_structure(d, width=2))
    d["breakout"] = (d.rising_structure & cross(c, d.confirmed_high)).fillna(False)
    d["exit_condition"] = (c < d.confirmed_low).fillna(False)
    d["exit_trigger"] = d.exit_condition & ~d.exit_condition.shift(1, fill_value=False)
    d["volume_average20"] = d.Volume.rolling(20).mean().shift(1)
    return d


def pivot_events(frame):
    """Original pivot dates and the dates on which they became knowable."""
    found = {"high": [], "low": []}
    for i in range(2, len(frame)-2):
        for kind, col, sign in [("high", "High", 1), ("low", "Low", -1)]:
            values = frame[col].to_numpy()
            neighbors = np.r_[values[i-2:i], values[i+1:i+3]]
            if (values[i] > neighbors.max()) if sign > 0 else (values[i] < neighbors.min()):
                found[kind].append({
                    "price": number(values[i]),
                    "pivot_date": str(frame.index[i].date()),
                    "confirmed_on": str(frame.index[i+2].date()),
                })
    return found


def chart_swings(pivots, first_date):
    """Labels use full-history confirmed pivots, not rounded chart candles."""
    events = []
    for kind in ("high", "low"):
        previous = None
        for point in pivots[kind]:
            price = point["price"]
            if previous is None:
                label = "H" if kind == "high" else "L"
            elif price == previous:
                label = "EH" if kind == "high" else "EL"
            elif kind == "high":
                label = "HH" if price > previous else "LH"
            else:
                label = "HL" if price > previous else "LL"
            if point["pivot_date"] >= first_date:
                events.append(dict(point, kind=kind, label=label))
            previous = price
    return sorted(events, key=lambda p: (p["pivot_date"], p["kind"]))


def classify(*, fresh, enough, gaps, volume, exit_condition, structure,
             breakout, above_high, market_ready, market_on, price, turnover, atr_pct):
    if not fresh:
        return "CAUTION", "No complete candle for the requested session."
    if gaps:
        return "CAUTION", "Missing price sessions in the structure lookback."
    if not enough:
        return "CAUTION", "Insufficient history or confirmed swing pivots."
    if not volume or volume <= 0:
        return "CAUTION", "No positive trading volume in the latest candle."
    if exit_condition:
        return "SELL", "Close is below the last confirmed swing low: exit condition for an existing long."
    if price < 50:
        return "AVOID", "Price is below the strategy minimum of Rs 50."
    if turnover is None or turnover < 1e8:
        return "AVOID", "20-session average traded value is below Rs 10 crore."
    if atr_pct is None or not .5 <= atr_pct <= 6:
        return "AVOID", "ATR is outside the strategy's 0.5%-6% price range."
    if breakout:
        if not market_ready:
            return "CAUTION", "Fresh HH/HL breakout, but the benchmark data gate is incomplete."
        if not market_on:
            return "CAUTION", "Fresh HH/HL breakout, but Nifty is below its 200-session average."
        return "BUY", "Fresh confirmed HH/HL breakout; eligible for a next-session paper entry only."
    if structure and above_high:
        return "CAUTION", "Price is already above resistance; no fresh breakout today. Do not chase."
    if structure:
        return "WATCH", "Higher highs and higher lows confirmed; wait for a fresh closing breakout."
    return "AVOID", "Two rising confirmed highs and two rising confirmed lows are not present."


def scan_stock(meta, frame, invalid_dates, as_of, market, calendar):
    base = {
        "symbol": meta["Symbol"], "name": meta.get("Company Name", meta["Symbol"]),
        "sector": meta.get("Industry", "Unknown"), "as_of": as_of,
        "data_source": "Previously downloaded Yahoo adjusted daily OHLCV",
        "data_date": None, "complete_for_session": False, "status": "CAUTION",
        "reason": "Price history unavailable.", "close": None, "atr": None,
        "atr_pct": None, "turnover_crore": None, "structure": "UNKNOWN",
        "fresh_breakout": False, "exit_condition": False, "sell_triggered_today": False,
        "last_breakout_date": None, "distance_to_breakout_pct": None,
        "pivots": {"high": [], "low": []}, "zones": {}, "chart": [],
        "data_warnings": [], "entry_allowed": False, "entry_plan": None, "chart_swings": [], "entry_checks": [], "volume_ratio": None,
    }
    if frame.empty:
        return base
    frame = frame.loc[frame.index <= pd.Timestamp(as_of)].copy()
    if frame.empty:
        return base
    d = feature_frame(frame)
    r = d.iloc[-1]
    last_date = str(d.index[-1].date())
    fresh = last_date == as_of
    pivots = pivot_events(frame)
    highs, lows = pivots["high"], pivots["low"]
    enough = len(d) >= 20 and len(highs) >= 2 and len(lows) >= 2 and np.isfinite(r.atr)
    high = number(r.confirmed_high)
    low = number(r.confirmed_low)
    previous_high = highs[-2]["price"] if len(highs) >= 2 else None
    previous_low = lows[-2]["price"] if len(lows) >= 2 else None
    hh = high is not None and previous_high is not None and high > previous_high
    hl = low is not None and previous_low is not None and low > previous_low
    lh = high is not None and previous_high is not None and high < previous_high
    ll = low is not None and previous_low is not None and low < previous_low
    structure = "HH / HL" if hh and hl else "LH / LL" if lh and ll else "MIXED" if enough else "UNCONFIRMED"
    atr_pct = number(100*r.atr/r.Close)
    expected = calendar[(calendar >= max(frame.index[0], pd.Timestamp(as_of)-pd.Timedelta(days=95))) & (calendar <= pd.Timestamp(as_of))]
    gaps = [str(x.date()) for x in expected if x not in frame.index]
    status, reason = classify(
        fresh=fresh, enough=enough, gaps=gaps, volume=r.Volume,
        exit_condition=bool(r.exit_condition), structure=bool(r.rising_structure),
        breakout=bool(r.breakout), above_high=high is not None and r.Close > high,
        market_ready=market["data_ready"], market_on=market["reference_filter_passed"],
        price=float(r.Close), turnover=number(r.turnover), atr_pct=atr_pct,
    )
    warnings = []
    if invalid_dates:
        warnings.append("Invalid vendor candle(s) excluded: " + ", ".join(invalid_dates[-5:]))
    if not fresh:
        warnings.append("Latest complete prices are from " + last_date + "; zones are withheld.")
    if gaps:
        warnings.append("Missing recent session(s): " + ", ".join(gaps[-5:]))
    entry_plan = None
    zones = {}
    if fresh and enough and not gaps and r.Volume > 0:
        zones = {
            "breakout_above": high, "structure_exit_below": low,
            "watch_band": [number(max(low, high-r.atr)), high] if bool(r.rising_structure) and low < high else None,
            "extended_above": number(high+r.atr),
            "stop_distance": number(2*r.atr),
        }
        if bool(r.breakout):
            entry_plan = {
                "signal_date": as_of,
                "opening_price_band": [number(r.Close-r.atr), number(r.Close+r.atr)],
                "eligible": status == "BUY", "max_sessions": 10,
                "stop_formula": "Actual entry minus 2 x signal-day ATR14",
                "stop_at_signal_close_reference": number(r.Close-2*r.atr),
                "target": None,
                "exit": "Initial stop; close below last confirmed low then exit next open; or close of session 10.",
                "timing": "Only the next NSE session open after the signal date; cancel if opening price is outside the band.",
            }
    signals = d.index[d.breakout]
    chart = [{
        "date": str(day.date()), "open": number(row.Open), "high": number(row.High),
        "low": number(row.Low), "close": number(row.Close), "volume": number(row.Volume, 0),
        "volume_average20": number(row.volume_average20, 0),
        "confirmed_high": number(row.confirmed_high), "confirmed_low": number(row.confirmed_low),
        "structure_breakout": bool(row.breakout), "structure_exit": bool(row.exit_trigger),
    } for day, row in d.tail(140).iterrows()]
    def check(key, label, passed, detail, waiting=False):
        return {"key": key, "label": label, "state": "pass" if passed else "wait" if waiting else "fail", "detail": detail}
    checks = [
        check("data", "Complete session & history", fresh and enough and not gaps and r.Volume > 0,
              "Complete prices, enough confirmed pivots and no recent missing sessions required."),
        check("higher_highs", "Two rising highs", hh, f"Previous {previous_high}; latest {high}."),
        check("higher_lows", "Two rising lows", hl, f"Previous {previous_low}; latest {low}."),
        check("trigger", "Fresh closing breakout", fresh and bool(r.breakout),
              "A new closing cross over the confirmed high is required; an intraday wick is insufficient.",
              waiting=bool(r.rising_structure) and not bool(r.exit_condition)),
        check("market", "Nifty above 200-session average", market["data_ready"] and market["reference_filter_passed"],
              "Benchmark must be complete and above its 200-session average."),
        check("price", "Price at least Rs 50", r.Close >= 50, f"Latest close Rs {number(r.Close)}."),
        check("liquidity", "Average turnover at least Rs 10 crore", np.isfinite(r.turnover) and r.turnover >= 1e8,
              f"20-session average Rs {number(r.turnover/1e7, 2)} crore."),
        check("volatility", "ATR between 0.5% and 6%", atr_pct is not None and .5 <= atr_pct <= 6,
              f"ATR14 is {atr_pct}% of price."),
        check("structure_exit", "Structure exit not triggered", not bool(r.exit_condition),
              "A close below the confirmed low is an exit condition for existing longs."),
    ]
    base.update({
        "data_date": last_date, "complete_for_session": fresh, "status": status, "reason": reason,
        "close": number(r.Close), "atr": number(r.atr), "atr_pct": atr_pct,
        "turnover_crore": number(r.turnover/1e7, 2), "structure": structure,
        "fresh_breakout": fresh and bool(r.breakout), "exit_condition": fresh and bool(r.exit_condition),
        "sell_triggered_today": fresh and bool(r.exit_condition) and len(d) > 1 and not bool(d.iloc[-2].exit_condition),
        "last_breakout_date": str(signals[-1].date()) if len(signals) else None,
        "distance_to_breakout_pct": number(100*(high/r.Close-1), 2) if high else None,
        "pivots": {"high": highs[-2:], "low": lows[-2:]},
        "zones": zones, "chart": chart, "chart_swings": chart_swings(pivots, chart[0]["date"]), "data_warnings": warnings,
        "entry_allowed": status == "BUY", "entry_plan": entry_plan, "entry_checks": checks,
        "volume_ratio": number(r.Volume/r.volume_average20, 2) if r.volume_average20 > 0 else None,
    })
    return base


def priority_watchlist(rows, limit=10):
    """Deterministic review order, not a return forecast or new entry rule."""
    pool = [r for r in rows if r["structure"] == "HH / HL"
            and r["complete_for_session"] and r["zones"]
            and r["status"] in ("BUY", "WATCH", "CAUTION")
            and all(c["state"] == "pass" for c in r.get("entry_checks", [])
                    if c["key"] not in ("trigger", "market"))]
    def key(row):
        tier = 0 if row["status"] == "BUY" else 1 if row["fresh_breakout"] else 2 if row["status"] == "WATCH" else 3
        distance = abs(row["close"]-row["zones"]["breakout_above"])/row["atr"] if row["atr"] else float("inf")
        return tier, distance, row["symbol"]
    pool.sort(key=key)
    return [{"rank": i+1, "symbol": r["symbol"], "status": r["status"],
             "distance_atr": number(abs(r["close"]-r["zones"]["breakout_above"])/r["atr"], 2),
             "reason": "Eligible fresh breakout" if r["status"] == "BUY" else
                       "Fresh breakout; entry blocked" if r["fresh_breakout"] else
                       "Rising structure; waiting for a close above the trigger" if r["status"] == "WATCH" else
                       "Already above the trigger; no fresh entry"}
            for i, r in enumerate(pool[:limit])]


def normalize_sessions(loaded, minimum_symbols=100):
    """Discard market-wide zero-volume placeholders before counting pivot bars."""
    frequency = Counter(date for frame in loaded.values() for date in frame.index[frame.Volume > 0])
    calendar = pd.DatetimeIndex(sorted(date for date, count in frequency.items() if count >= minimum_symbols))
    normalized, removed = {}, {}
    for symbol, frame in loaded.items():
        usable = frame.index.isin(calendar) & (frame.Volume > 0)
        removed[symbol] = int((~usable).sum())
        normalized[symbol] = frame.loc[usable].copy()
    return calendar, normalized, removed


def build(as_of, cache_dir=ROOT/".cache/swing", universe_path=ROOT/"nifty200.csv"):
    universe = list(csv.DictReader(universe_path.open(encoding="utf-8-sig")))
    universe = [r for r in universe if r.get("Series", "EQ") == "EQ"]
    if len(universe) != 200 or len({r["Symbol"] for r in universe}) != 200:
        raise ValueError("Expected exactly 200 unique EQ constituents; no silent omissions.")
    loaded, invalid, failures, fingerprints = {}, {}, {}, {}
    for row in universe:
        symbol = row["Symbol"]
        path = cache_dir/(symbol+".NS.csv")
        try:
            loaded[symbol], invalid[symbol] = read_prices(path, as_of)
            fingerprints[symbol] = hashlib.sha256(path.read_bytes()).hexdigest()
        except (OSError, ValueError, KeyError) as exc:
            loaded[symbol] = pd.DataFrame(columns=OHLCV)
            invalid[symbol] = []
            failures[symbol] = str(exc)[:140]
    calendar, loaded, placeholder_rows_removed = normalize_sessions(loaded)
    market_frame, bad_market = read_prices(cache_dir/"NSEI.csv", as_of)
    market_frame = market_frame.loc[market_frame.index.isin(calendar)]
    if len(market_frame) < 200:
        raise ValueError("Benchmark needs at least 200 observations.")
    m = market_frame.iloc[-1]
    expected_market = calendar[calendar <= pd.Timestamp(as_of)][-200:]
    market_gaps = [str(day.date()) for day in expected_market if day not in market_frame.index]
    ref_average = float(market_frame.Close.tail(200).mean())
    ready = str(market_frame.index[-1].date()) == as_of and not market_gaps and len(expected_market) >= 200
    market = {
        "symbol": "NIFTY 50", "data_date": str(market_frame.index[-1].date()),
        "close": number(m.Close), "sma200": number(ref_average) if ready else None,
        "average_200_available_bars": number(ref_average),
        "reference_filter_passed": bool(m.Close > ref_average),
        "data_ready": ready, "new_entries_allowed": ready and bool(m.Close > ref_average),
        "missing_sessions": market_gaps, "invalid_dates": bad_market,
        "note": "The market gate requires 200 complete shared trading sessions. A 200-observation reference is shown separately when a benchmark session is missing.",
    }
    rows = [scan_stock(meta, loaded[meta["Symbol"]], invalid[meta["Symbol"]], as_of, market, calendar) for meta in universe]
    order = {s: i for i, s in enumerate(["BUY", "WATCH", "CAUTION", "SELL", "AVOID"])}
    rows.sort(key=lambda r: (order[r["status"]], -int(r["fresh_breakout"]),
                            abs(r["distance_to_breakout_pct"]) if r["distance_to_breakout_pct"] is not None else 999,
                            r["symbol"]))
    counts = {s: sum(r["status"] == s for r in rows) for s in STATUSES}
    return {
        "version": 1, "as_of": as_of, "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy_id": "hhhl_h10_nifty_above_200", "validated": False,
        "universe_count": len(universe), "complete_count": sum(r["complete_for_session"] for r in rows),
        "classifiable_count": sum(bool(r["zones"]) for r in rows), "counts": counts,
        "market": market, "rows": rows, "failures": failures,
        "priority_watchlist": priority_watchlist(rows),
        "priority_method": "Review order: eligible breakouts, blocked fresh breakouts, then waiting HH/HL setups nearest their trigger in ATR units. Late setups last. No forecast score or promise of profit.",
        "data_audit": {
            "price_source": "Previously downloaded Yahoo adjusted daily OHLCV; dates and OHLC checked locally.",
            "latest_recheck": "Local history scan; fetch provenance is supplied by hhhl_refresh.py for automated runs.",
            "universe_source": "Saved nifty200.csv; exactly 200 unique EQ symbols validated.",
            "universe_url": "https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv",
            "universe_sha256": hashlib.sha256(universe_path.read_bytes()).hexdigest(),
            "price_sha256": fingerprints,
            "zero_volume_or_non_session_rows_removed": placeholder_rows_removed,
            "calendar_policy": "Trading sessions require positive volume in at least 100 constituents; market-wide zero-volume holiday placeholders are excluded before pivots and ATR.",
            "benchmark_sha256": hashlib.sha256((cache_dir/"NSEI.csv").read_bytes()).hexdigest(),
            "date_policy": "All observations after the requested date are excluded before indicators and pivots are calculated.",
        },
        "rules": {
            "pivot_left": 2, "pivot_right": 2, "minimum_turnover_crore": 10,
            "minimum_price": 50, "atr_percent_range": [.5, 6], "stop_atr": 2,
            "holding_sessions": 10, "opening_gap_atr": 1, "profit_target": None,
            "risk_per_position_pct": .5, "max_positions": 5, "max_position_pct": 20,
            "max_per_sector": 2,
            "entry": "Fresh closing cross over latest confirmed high with two rising highs and lows. Market gate must pass. Next open within one signal ATR of close.",
            "sell": "Close below confirmed low is an exit condition only for existing long holdings. It is not an overnight short recommendation.",
            "watch": "Rising structure without a fresh breakout. The displayed one-ATR band below resistance is an orientation zone, not an entry signal.",
            "caution": "Missing data, incomplete pivots, blocked fresh breakout or an already-passed breakout.",
            "avoid": "No rising structure or failed price, liquidity or ATR screen; this does not mean the company is a bad investment.",
            "execution": "These are dated scanner states, not portfolio orders. Actual fills, existing stops, time exits, earnings dates and allocation limits still matter.",
        },
        "status_definitions": {
            "BUY": "Fresh qualifying breakout; next-session paper entry only.",
            "SELL": "Structure exit condition for an existing long position.",
            "WATCH": "HH/HL structure; wait for a closing breakout.",
            "CAUTION": "Data issue, blocked entry or missed fresh trigger.",
            "AVOID": "No qualifying HH/HL setup or failed entry screen.",
        },
        "limitations": [
            f"This is a fixed {as_of} snapshot, not a live price feed.",
            "No trading strategy has been forward validated. Classifications are research states.",
            "One missing stock candle is retained as Caution rather than dropped from the 200-stock list.",
            "Current repository membership and cached adjusted prices have source and corporate-action limitations.",
            "No earnings-calendar gate. Existing position stops and 10-session exits require your actual entry record.",
            "There is no fixed profit target in the tested HH/HL rule; adding one would change the strategy.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", required=True, help="Completed NSE session, YYYY-MM-DD; use hhhl_refresh.py for automatic dates")
    args = parser.parse_args()
    datetime.strptime(args.as_of, "%Y-%m-%d")
    result = build(args.as_of)
    publish("hhhl_scan", result)
    print(json.dumps({
        "as_of": result["as_of"], "universe": result["universe_count"],
        "complete": result["complete_count"], "counts": result["counts"], "market": result["market"],
        "fresh_breakouts": [r["symbol"] for r in result["rows"] if r["fresh_breakout"]],
        "missing": [r["symbol"] for r in result["rows"] if not r["complete_for_session"]],
    }, indent=2))


if __name__ == "__main__":
    main()
