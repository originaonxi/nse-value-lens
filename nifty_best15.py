#!/usr/bin/env python3
"""Nifty 50 · the best tested setup · EMA 21 / EMA 105 on 15-minute candles · always in a trade (BUY or SELL).

Why this one: of 2,055 EMA rules tested on Nifty (10m, 15m, 1h, 2h, daily; every fast/slow pair; always in, BUY or
watch, SELL or watch) from 3 Jul 2023, it made money in every year and did as well on 2025-26 as on 2023-24, and the
rules around it (EMA 13-25 vs EMA 100-144) did too.

Rule (same as the TradingView Pine script "Nifty EMA 21 / EMA 105 (15m)"):
  BUY  when a 15-minute candle closes with EMA 21 above EMA 105
  SELL (short) when a 15-minute candle closes with EMA 21 below EMA 105
  the order fills at the next candle's open; the position flips straight from BUY to SELL, so it is always in a trade.
  0.035% of price on every buy and every sell. 1 lot = 65 (today's NSE lot); positions are held overnight.
Candles: Upstox 15-minute Nifty 50 candles (intraday15.fetch), each day checked against NSE's official index file.

Run: python nifty_best15.py   -> docs/best15.json
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import ema921 as E  # noqa: E402
import intraday15 as I  # noqa: E402

DOCS, PUBLIC = ROOT / "docs", ROOT / "public" / "data"
FAST, SLOW = 21, 105
KIND, OUT = "ema", "best15"                 # --sma F S --out NAME builds the same page for an SMA pair
COST = 0.00035
LOT, LOTS = 65, 10
START = pd.Timestamp("2023-07-03")          # first trading day after the EMAs have 6 months of candles
SPLIT = pd.Timestamp("2025-01-01")          # rule chosen on data before this; after it is the unseen part
CHART_DAYS = 365


def ma(c, n):
    """The rule's moving average: SMA-seeded EMA (TradingView ta.ema) or a plain SMA."""
    return E.pine_ema(c, n) if KIND == "ema" else pd.Series(c).rolling(n).mean().to_numpy()


def flip_price(e_fast, e_slow, closes=None):
    """The next 15-minute close at which the fast average lands exactly on the slow one."""
    if KIND == "sma":
        cf = float(np.sum(closes[-(FAST - 1):]))
        cs = float(np.sum(closes[-(SLOW - 1):]))
        return (FAST * cs - SLOW * cf) / (SLOW - FAST)
    a, b = 2 / (FAST + 1), 2 / (SLOW + 1)
    return ((1 - b) * e_slow - (1 - a) * e_fast) / (a - b)


def replay(df, start_i):
    """Always in from the first close at/after start_i. Signal at close i -> fill at open i+1."""
    o, c = df["Open"].to_numpy(float), df["Close"].to_numpy(float)
    t = df.index
    ef, es = ma(c, FAST), ma(c, SLOW)
    up = np.nan_to_num(ef) > np.nan_to_num(es)
    pos, entry, ent_i = 0, 0.0, None
    trades, real = [], 0.0
    eq = np.zeros(len(c))
    for i in range(start_i, len(c)):
        if i > start_i:
            want = 1 if up[i - 1] else -1
            if want != pos:
                px = float(o[i])
                if pos != 0:
                    net = pos * (px - entry) - COST * (entry + px)
                    real += net
                    trades.append({"side": "BUY" if pos > 0 else "SELL", "signal_time": str(t[ent_i - 1])[:16],
                                   "entry_time": str(t[ent_i])[:16], "entry": round(entry, 2),
                                   "exit_signal_time": str(t[i - 1])[:16], "exit_time": str(t[i])[:16], "exit": round(px, 2),
                                   "net_pts": round(net, 2), "rupees": round(net * LOT), "candles": i - ent_i,
                                   "days": (t[i].normalize() - t[ent_i].normalize()).days, "open": False})
                pos, entry, ent_i = want, px, i
        unreal = pos * (c[i] - entry) - COST * entry if pos else 0.0
        eq[i] = real + unreal
    if pos:
        last = float(c[-1])
        net = pos * (last - entry) - COST * entry
        trades.append({"side": "BUY" if pos > 0 else "SELL", "signal_time": str(t[ent_i - 1])[:16], "entry_time": str(t[ent_i])[:16],
                       "entry": round(entry, 2), "exit_signal_time": None, "exit_time": None, "exit": round(last, 2),
                       "net_pts": round(net, 2), "rupees": round(net * LOT), "candles": len(c) - 1 - ent_i,
                       "days": (t[-1].normalize() - t[ent_i].normalize()).days, "open": True})
    return trades, eq, ef, es, up


def side_stats(tr):
    p = np.array([x["net_pts"] for x in tr], float)
    if not len(p):
        return {"trades": 0, "pts": 0.0, "win_pct": 0.0}
    return {"trades": len(p), "pts": round(float(p.sum()), 1), "win_pct": round(float((p > 0).mean()) * 100, 1)}


def build(today=None):
    try:
        df = I.fetch(today)
        source = "Upstox 15-minute candles, refreshed this run"
    except Exception as e:                                      # pragma: no cover - network
        print(f"warn: Upstox refresh failed ({type(e).__name__}); using the cached candles")
        df = pd.read_csv(I.CACHE, index_col=0, parse_dates=True)
        source = "Upstox 15-minute candles from the cache (refresh failed this run)"
    df = df[["Open", "High", "Low", "Close"]].astype(float)
    flbl = f"{KIND.upper()} {FAST}"
    slbl = f"{KIND.upper()} {SLOW}"
    check = I.check_data(df)
    t = df.index
    start_i = int(np.searchsorted(t, START))
    trades, eq, ef, es, up = replay(df, start_i)
    o, c = df["Open"].to_numpy(float), df["Close"].to_numpy(float)

    closed = [x for x in trades if not x["open"]]
    op = trades[-1] if trades and trades[-1]["open"] else None
    p = np.array([x["net_pts"] for x in closed], float)
    w, lo = p[p > 0], p[p <= 0]
    run = best = 0
    for v in p:
        run = run + 1 if v <= 0 else 0
        best = max(best, run)
    curve_pts = eq[start_i:]
    peak = np.maximum.accumulate(np.r_[0.0, curve_pts])
    dd = peak - np.r_[0.0, curve_pts]
    dd_i = int(np.argmax(dd))
    total = float(curve_pts[-1])
    hold = float(c[-1] - o[start_i])
    split_i = int(np.searchsorted(t, SPLIT))
    before = float(eq[split_i - 1]) if split_i > start_i else 0.0
    summary = {
        "total_pts": round(total, 1), "total_rs": round(total * LOT), "total_rs_10": round(total * LOT * LOTS),
        "realised_pts": round(float(p.sum()), 1), "open_pts": op["net_pts"] if op else 0.0,
        "trades": len(closed), "wins": int((p > 0).sum()), "losses": int((p <= 0).sum()),
        "win_pct": round(float((p > 0).mean()) * 100, 1) if len(p) else 0.0,
        "avg_win_pts": round(float(w.mean()), 1) if len(w) else 0.0, "avg_loss_pts": round(float(lo.mean()), 1) if len(lo) else 0.0,
        "profit_factor": round(float(w.sum() / -lo.sum()), 2) if lo.sum() else None,
        "best_pts": round(float(p.max()), 1) if len(p) else 0.0, "worst_pts": round(float(p.min()), 1) if len(p) else 0.0,
        "longest_losing_run": int(best),
        "max_dd_pts": round(float(dd.max()), 1), "max_dd_rs": round(float(dd.max()) * LOT), "max_dd_rs_10": round(float(dd.max()) * LOT * LOTS),
        "max_dd_on": str(t[start_i + dd_i - 1])[:10] if dd_i else None,
        "buy": side_stats([x for x in closed if x["side"] == "BUY"]), "sell": side_stats([x for x in closed if x["side"] == "SELL"]),
        "hold_pts": round(hold, 1), "hold_rs": round(hold * LOT), "hold_rs_10": round(hold * LOT * LOTS),
        "pick_period_pts": round(before, 1), "unseen_period_pts": round(total - before, 1),
        "trades_per_month": round(len(closed) / max(1, (t[-1] - t[start_i]).days / 30.44), 1),
    }

    last_t = t[-1]
    trig = flip_price(ef[-1], es[-1], c)
    side = "BUY" if up[-1] else "SELL"
    pending = op is not None and op["side"] != side
    if pending:
        state = f"{side} at the next 15-minute candle's open"
        what = f"{flbl} crossed {'above' if up[-1] else 'below'} {slbl} on the last candle; the position flips to {side} at the next open."
    else:
        state = f"IN TRADE · {side}"
        what = (f"Stays BUY until {flbl} crosses below {slbl}. One single 15-minute close below about {trig:,.2f} would do it right now; "
                "normally it comes after a slide over many candles." if side == "BUY"
                else f"Stays SELL until {flbl} crosses above {slbl}. One single 15-minute close above about {trig:,.2f} would do it right now; "
                "normally it comes after a rise over many candles.")
    now = {"time": str(last_t)[:16], "close": round(float(c[-1]), 2), "ema21": round(float(ef[-1]), 2), "ema105": round(float(es[-1]), 2),
           "side": side, "state": state, "what": what, "flip": round(float(trig), 2), "flip_pts": round(float(trig - c[-1]), 1)}

    # state the browser needs to continue the averages live during market hours (Upstox allows CORS from the site)
    live = {"time": str(last_t)[:16], "ema21": round(float(ef[-1]), 4), "ema105": round(float(es[-1]), 4), "kind": KIND,
            "side": side, "pending": bool(pending),
            "entry": op["entry"] if op else None, "entry_time": op["entry_time"] if op else None,
            "feed": "https://api.upstox.com/v3/historical-candle/intraday/NSE_INDEX%7CNifty%2050/minutes/1",
            "session_ist": ["09:15", "15:30"], "poll_s": 30}
    if KIND == "sma":
        live["closes"] = [round(float(x), 2) for x in c[-(SLOW - 1):]]      # the browser's rolling window

    # daily curve (last value of each day) vs holding Nifty
    day = pd.Series(curve_pts, index=t[start_i:]).groupby(t[start_i:].normalize()).last()
    hold_day = pd.Series(c[start_i:] - o[start_i], index=t[start_i:]).groupby(t[start_i:].normalize()).last()
    curve = [[str(d.date()), round(float(v), 1), round(float(h), 1)] for (d, v), h in zip(day.items(), hold_day.to_numpy())]
    yr_end = day.groupby(day.index.year).last()
    hold_yr = hold_day.groupby(hold_day.index.year).last()
    years_mtm, prev_v, prev_h = [], 0.0, 0.0
    for y in yr_end.index:                                      # each year's change, open trade valued at the year-end close
        years_mtm.append({"year": int(y), "pts": round(float(yr_end[y]) - prev_v, 1), "rupees": round((float(yr_end[y]) - prev_v) * LOT),
                          "hold_pts": round(float(hold_yr[y]) - prev_h, 1)})
        prev_v, prev_h = float(yr_end[y]), float(hold_yr[y])


    c0 = int(np.searchsorted(t, last_t - pd.Timedelta(days=CHART_DAYS)))
    chart = {"bars": [[str(x)[:16], round(float(r.Open), 2), round(float(r.High), 2), round(float(r.Low), 2), round(float(r.Close), 2)]
                      for x, r in df.iloc[c0:].iterrows()],
             "ema21": [round(float(x), 2) if x == x else None for x in ef[c0:]],
             "ema105": [round(float(x), 2) if x == x else None for x in es[c0:]]}

    if KIND == "ema":
        why = ["Picked from 2,055 EMA rules on Nifty (10-minute, 15-minute, 1-hour, 2-hour and daily candles; BUY+SELL, BUY only, SELL only).",
               "It made money in every year since July 2023, including 2026 when Nifty fell, and did as well after 1 Jan 2025 as before.",
               "The rules next to it (EMA 13, 15, 20, 25 against EMA 100, 105, 144) also made money every year, so 21 / 105 is not a lucky pair."]
        pick_limit = "Picked after looking at this same history. The 10-minute EMA 8 / 200 made more in total but fell to +506 points in 2026; this one was steadier."
    else:
        why = ["Found by widening the search beyond EMAs: 401 rules from 6 families (Supertrend, Donchian, MACD, RSI, SMA pairs, price-vs-SMA) after 2,680 EMA tests. This made the most points of every rule with zero losing years.",
               "Its whole neighbourhood works: every SMA pair from 3-8 against 180-220 made money with no losing year, so 5 / 200 is a plateau, not a lucky spike.",
               "Ranked No.1 on 2023-24 data alone, then made +4,278 points on 2025-26 it had never seen, and was positive in BOTH halves of the last 200 sessions (EMA 21/105 was not).",
               "Confirmation filters were tested and rejected: waiting for the next candle to confirm the cross turned the profit negative; entering plainly at the next open kept it."]
        pick_limit = "First published 10 Nov 2026, picked after looking at this same history: its honest out-of-sample record only starts now."
    payload = {
        "version": 1, "name": f"Nifty 50 · {flbl} / {slbl} · 15-minute · always in",
        "generated_at": datetime.now(I.IST).isoformat(timespec="minutes"),
        "as_of": str(last_t.date()), "last_candle": str(last_t)[:16], "from": str(t[start_i])[:10], "split": str(SPLIT.date()),
        "source": source, "fast": FAST, "slow": SLOW, "kind": KIND, "fast_label": flbl, "slow_label": slbl,
        "cost_side_pct": COST * 100, "lot": LOT, "lots": LOTS,
        "rule": [f"BUY when a 15-minute candle closes with {flbl} above {slbl}. The order fills at the next candle's open.",
                 f"SELL (short) when a 15-minute candle closes with {flbl} below {slbl}. The position flips straight from BUY to SELL: always in a trade.",
                 "No stop and no target: the next crossover is the exit. Positions are held overnight.",
                 f"{COST * 100:.3f}% of price on every buy and every sell. Rupees: 1 lot = {LOT}, and {LOTS} lots."],
        "why": why,
        "summary": summary, "now": now, "live": live, "trades": trades, "months": E.periods(trades, 7), "years": E.periods(trades, 4), "years_mtm": years_mtm,
        "curve": curve, "chart": chart, "data": check,
        "limits": [
            pick_limit,
            "About 64% of trades lose. The profit comes from a few long trends, and long losing runs are normal.",
            "Positions are held overnight, so an opening gap can move the trade a long way before you can act.",
            f"Fills are assumed exactly at each 15-minute open. {LOTS} lots of {LOT} is about Rs {LOTS * LOT * float(c[-1]) / 1e7:.1f} crore of Nifty: check margin before trading that size.",
            "TradingView's 15-minute candles can differ by a few points, so a signal there can be one candle apart.",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
    }
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for out in (DOCS / f"{OUT}.json", PUBLIC / f"{OUT}.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    s = summary
    print(f"{OUT}.json {payload['from']} -> {payload['last_candle']} | {s['trades']} closed trades, won {s['win_pct']}% | "
          f"total {s['total_pts']} pts = Rs {s['total_rs']:,} (1 lot) / Rs {s['total_rs_10']:,} (10 lots) | hold {s['hold_pts']} pts | "
          f"worst fall {s['max_dd_pts']} pts | now {now['state']} | {len(text) // 1024}KB")
    return payload


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build the best-setup page data (default: EMA 21/105 -> best15.json)")
    ap.add_argument("--sma", nargs=2, type=int, metavar=("FAST", "SLOW"), help="use an SMA pair instead of EMA 21/105")
    ap.add_argument("--out", help="output name, e.g. best5200")
    args = ap.parse_args()
    if args.sma:
        KIND, FAST, SLOW = "sma", args.sma[0], args.sma[1]
    if args.out:
        OUT = args.out
    build()
