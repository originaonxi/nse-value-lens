#!/usr/bin/env python3
"""Nifty 50 · EMA 9 / EMA 21 trend rule on 1-hour candles · every trade of the last 2 years · rebuilt after every close.

The same rule as the TradingView Pine script "Nifty EMA 9/21 Trend (1H) - tested":
  BUY    when a 1-hour candle closes with EMA 9 above EMA 21 and we are flat  -> filled at the next candle's open
  EXIT   when a 1-hour candle closes with EMA 9 below EMA 21 while long       -> filled at the next candle's open
  Buy only, no stop, positions are held overnight. 0.035% cost on every buy and every sell (as in the Pine script).
Candles: NSE Nifty 50 index 15-minute candles from Upstox's public API (intraday15.fetch, cached in
data/nifty/upstox_15m.csv), grouped into 1-hour candles anchored at 09:15 like TradingView's NSE 1-hour chart
(09:15, 10:15 ... 14:15, and a 15-minute 15:15 candle). Each day's open/high/low/close is checked against NSE's
official index close file. Rupees use 1 NIFTY futures lot with the lot size from the NSE F&O bhavcopy of the entry day.

Run: python ema921.py   -> docs/ema921.json
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import intraday15 as I  # noqa: E402

DOCS, PUBLIC = ROOT / "docs", ROOT / "public" / "data"
FAST, SLOW = 9, 21
COST_SIDE = 0.00035                    # 0.035% of the traded value on every buy and every sell
YEARS = 2


def pine_ema(x, n):
    """TradingView ta.ema: seeded with the simple average of the first n closes."""
    e = np.full(len(x), np.nan)
    if len(x) < n:
        return e
    e[n - 1] = x[:n].mean()
    a = 2 / (n + 1)
    for i in range(n, len(x)):
        e[i] = a * x[i] + (1 - a) * e[i - 1]
    return e


def hourly(df15):
    """15-minute candles -> 1-hour candles anchored at 09:15 within each session (never across days)."""
    g = df15.copy()
    g["d"] = g.index.date
    g["n"] = g.groupby("d").cumcount() // 4
    h = g.groupby(["d", "n"]).agg(t=("Open", lambda s: s.index[0]), Open=("Open", "first"), High=("High", "max"),
                                  Low=("Low", "min"), Close=("Close", "last"), bars=("Close", "size"))
    return h.set_index("t").sort_index()


def exit_price(e_fast, e_slow):
    """The 1-hour close at which EMA 9 lands exactly on EMA 21 (below it -> EXIT, above it -> BUY)."""
    a, b = 2 / (FAST + 1), 2 / (SLOW + 1)
    return ((1 - b) * e_slow - (1 - a) * e_fast) / (a - b)


def replay(h, lots, start):
    """Pine-identical replay from candle `start`: returns trades and the per-candle equity (points and rupees, 1 lot)."""
    o, c = h["Open"].to_numpy(float), h["Close"].to_numpy(float)
    ef, es = pine_ema(c, FAST), pine_ema(c, SLOW)
    bull = np.nan_to_num(ef) > np.nan_to_num(es)
    bull[: SLOW - 1] = False
    t = h.index
    pos, order = 0, None
    trades, cur = [], None
    eq_pts, eq_rs, realised_pts, realised_rs = [], [], 0.0, 0.0
    for i in range(start, len(c)):
        if order is not None:                                   # fill at this candle's open
            lot = lots[str(t[i].date())]
            if order == "BUY" and pos == 0:
                pos, cur = 1, {"entry_time": str(t[i])[:16], "entry": float(o[i]), "lot": lot, "entry_i": i,
                               "signal_time": str(t[i - 1])[:16]}
            elif order == "EXIT" and pos == 1:
                gross = float(o[i]) - cur["entry"]
                cost = COST_SIDE * (cur["entry"] + float(o[i]))
                net = gross - cost
                cur.update({"exit_time": str(t[i])[:16], "exit": float(o[i]), "exit_signal_time": str(t[i - 1])[:16],
                            "gross_pts": round(gross, 2), "cost_pts": round(cost, 2), "net_pts": round(net, 2),
                            "rupees": round(net * cur["lot"]), "candles": i - cur["entry_i"],
                            "days": (t[i].normalize() - pd.Timestamp(cur["entry_time"][:10])).days, "open": False})
                realised_pts += net
                realised_rs += net * cur["lot"]
                trades.append(cur)
                pos, cur = 0, None
            order = None
        unreal = (c[i] - cur["entry"] - COST_SIDE * (cur["entry"] + c[i])) if pos else 0.0
        eq_pts.append(realised_pts + unreal)
        eq_rs.append(realised_rs + (unreal * cur["lot"] if pos else 0.0))
        if bull[i] and pos == 0:
            order = "BUY"
        elif not bull[i] and pos == 1 and not np.isnan(ef[i]):
            order = "EXIT"
    if pos:                                                     # still open: valued at the last close
        last = float(c[-1])
        gross = last - cur["entry"]
        cost = COST_SIDE * (cur["entry"] + last)
        cur.update({"exit_time": None, "exit": round(last, 2), "exit_signal_time": None, "gross_pts": round(gross, 2),
                    "cost_pts": round(cost, 2), "net_pts": round(gross - cost, 2), "rupees": round((gross - cost) * cur["lot"]),
                    "candles": len(c) - 1 - cur["entry_i"],
                    "days": (t[-1].normalize() - pd.Timestamp(cur["entry_time"][:10])).days, "open": True})
        trades.append(cur)
    for x in trades:
        x.pop("entry_i", None)
        x["entry"] = round(x["entry"], 2)
        x["exit"] = round(x["exit"], 2) if x["exit"] is not None else None
    return trades, np.array(eq_pts), np.array(eq_rs), ef, es, bull, order


def summary(trades, eq_rs, h, start, lots):
    closed = [x for x in trades if not x["open"]]
    op = next((x for x in trades if x["open"]), None)
    p = np.array([x["net_pts"] for x in closed]) if closed else np.zeros(0)
    rs = np.array([x["rupees"] for x in closed]) if closed else np.zeros(0)
    eq = np.r_[0.0, eq_rs]
    peak = np.maximum.accumulate(eq)
    dd_i = int(np.argmax(peak - eq))
    c = h["Close"].to_numpy(float)
    lot0 = lots[str(h.index[start].date())]
    hold_pts = float(c[-1] - h["Open"].iloc[start + 1]) if start + 1 < len(c) else 0.0
    wins = rs[rs > 0]
    loss = rs[rs <= 0]
    streak = best = 0
    for v in rs:
        streak = streak + 1 if v <= 0 else 0
        best = max(best, streak)
    return {
        "trades": len(closed), "wins": int((rs > 0).sum()), "losses": int((rs <= 0).sum()),
        "win_pct": round(float((rs > 0).mean()) * 100, 1) if len(rs) else 0.0,
        "net_pts": round(float(p.sum()), 1), "realised_rs": int(rs.sum()),
        "gross_win_rs": int(wins.sum()), "gross_loss_rs": int(loss.sum()),
        "cost_rs": int(sum(x["cost_pts"] * x["lot"] for x in closed)),
        "profit_factor": round(float(wins.sum() / -loss.sum()), 2) if loss.sum() else None,
        "avg_win_rs": int(wins.mean()) if len(wins) else 0, "avg_loss_rs": int(loss.mean()) if len(loss) else 0,
        "best_rs": int(rs.max()) if len(rs) else 0, "worst_rs": int(rs.min()) if len(rs) else 0,
        "longest_losing_run": int(best),
        "open_rs": int(op["rupees"]) if op else 0, "open_pts": op["net_pts"] if op else 0.0,
        "total_rs": int(rs.sum() + (op["rupees"] if op else 0)),
        "total_pts": round(float(p.sum() + (op["net_pts"] if op else 0)), 1),
        "max_dd_rs": int((peak - eq).max()), "max_dd_on": str(h.index[start + dd_i - 1])[:10] if dd_i else None,
        "nifty_held_pts": round(hold_pts, 1), "nifty_held_rs": int(hold_pts * lot0),
        "time_in_market_pct": None,
    }


def periods(trades, key):
    out = {}
    for x in trades:
        if x["open"]:
            continue
        k = x["exit_time"][:key]
        o = out.setdefault(k, {"period": k, "trades": 0, "wins": 0, "net_pts": 0.0, "rupees": 0})
        o["trades"] += 1
        o["wins"] += int(x["rupees"] > 0)
        o["net_pts"] = round(o["net_pts"] + x["net_pts"], 1)
        o["rupees"] += x["rupees"]
    return [out[k] for k in sorted(out)]


def build(today=None):
    try:
        df = I.fetch(today)
        source = "Upstox 15-minute candles, refreshed this run"
    except Exception as e:                                      # pragma: no cover - network
        print(f"warn: Upstox refresh failed ({type(e).__name__}); using the cached candles")
        df = pd.read_csv(I.CACHE, index_col=0, parse_dates=True)
        source = "Upstox 15-minute candles from the cache (refresh failed this run)"
    check = I.check_data(df)
    h = hourly(df)
    days = sorted({str(d) for d in h.index.date})
    lots = I.lot_sizes(days)
    first_day = (h.index[-1] - timedelta(days=365 * YEARS)).normalize()
    start = int(np.searchsorted(h.index, first_day))
    trades, eq_pts, eq_rs, ef, es, bull, pending = replay(h, lots, start)
    s = summary(trades, eq_rs, h, start, lots)
    s["time_in_market_pct"] = round(float(bull[start:].mean()) * 100, 1)

    c = h["Close"].to_numpy(float)
    last_t = h.index[-1]
    trig = exit_price(ef[-1], es[-1])
    in_trade = bool(trades and trades[-1]["open"])
    if pending == "BUY":
        state, what = "BUY at the next candle's open", f"EMA 9 crossed above EMA 21 on the last candle; the BUY fills at the next 1-hour candle's open."
    elif pending == "EXIT":
        state, what = "EXIT at the next candle's open", "EMA 9 crossed below EMA 21 on the last candle; the EXIT fills at the next 1-hour candle's open."
    elif in_trade:
        state, what = "IN TRADE · LONG", f"EXIT when a 1-hour candle closes below about {trig:,.2f} (EMA 9 would drop under EMA 21)."
    else:
        state, what = "FLAT · waiting", f"BUY when a 1-hour candle closes above about {trig:,.2f} (EMA 9 would rise over EMA 21)."
    now = {"time": str(last_t)[:16], "close": round(float(c[-1]), 2), "ema9": round(float(ef[-1]), 2),
           "ema21": round(float(es[-1]), 2), "state": state, "what": what, "trigger": round(float(trig), 2),
           "trigger_pts": round(float(trig - c[-1]), 1), "pending": pending,
           "lot": lots[str(last_t.date())]}

    # chart: the 2-year window (plus 60 warm-up candles so the lines start drawn)
    c0 = max(0, start - 60)
    bars = [[str(t)[:16], round(float(r.Open), 2), round(float(r.High), 2), round(float(r.Low), 2), round(float(r.Close), 2)]
            for t, r in h.iloc[c0:].iterrows()]
    curve = [[str(t)[:10], int(v)] for t, v in zip(h.index[start:], eq_rs)]
    daily_curve, seen = [], {}
    for d, v in curve:
        seen[d] = v
    hold0 = float(h["Open"].iloc[start + 1]) if start + 1 < len(c) else float(c[start])
    lot0 = lots[str(h.index[start].date())]
    closes_by_day = h["Close"].groupby(h.index.date).last()
    for d, v in seen.items():
        nc = float(closes_by_day.loc[pd.Timestamp(d).date()])
        daily_curve.append([d, v, int((nc - hold0) * lot0)])

    payload = {
        "version": 1, "name": "Nifty 50 · EMA 9 / EMA 21 · 1-hour candles",
        "generated_at": datetime.now(I.IST).isoformat(timespec="minutes"),
        "as_of": str(last_t.date()), "last_candle": str(last_t)[:16], "from": str(h.index[start].date()),
        "source": source, "fast": FAST, "slow": SLOW, "cost_side_pct": COST_SIDE * 100,
        "rule": [f"BUY when a 1-hour candle closes with EMA {FAST} above EMA {SLOW} (and you are flat). The order fills at the next candle's open.",
                 f"EXIT when a 1-hour candle closes with EMA {FAST} below EMA {SLOW}. The order fills at the next candle's open.",
                 "Buy only. No stop. The trade is held overnight until the exit signal.",
                 f"{COST_SIDE * 100:.3f}% is charged on every buy and every sell. Rupees are for 1 NIFTY futures lot, lot size from the NSE F&O bhavcopy of the entry day."],
        "summary": s, "now": now, "trades": trades, "months": periods(trades, 7), "years": periods(trades, 4),
        "curve": daily_curve,
        "chart": {"bars": bars, "ema9": [round(float(x), 2) if x == x else None for x in ef[c0:]],
                  "ema21": [round(float(x), 2) if x == x else None for x in es[c0:]], "start": str(h.index[start])[:16]},
        "data": check,
        "limits": [
            "This rule was picked by testing many rules on 2023-24 and checking it on 2025-26. It made money in both, but less than simply holding Nifty in rising years.",
            "Fills are assumed exactly at each candle's open; a real order slips a little. The 0.035% cost covers fees and about 1 point of slippage.",
            "Rupees are for 1 lot of NIFTY futures, with no rollover cost and no margin interest. Futures roll every month in real life.",
            "TradingView's 1-hour candles come from its own data feed; prices can differ by a few points, so a signal can be one candle apart.",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
    }
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for out in (DOCS / "ema921.json", PUBLIC / "ema921.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(f"ema921.json {payload['from']} -> {payload['last_candle']} | {s['trades']} closed trades, won {s['win_pct']}% | "
          f"realised Rs {s['realised_rs']:,} + open Rs {s['open_rs']:,} = Rs {s['total_rs']:,} ({s['total_pts']} pts) | "
          f"Nifty held Rs {s['nifty_held_rs']:,} | worst fall Rs {s['max_dd_rs']:,} | now: {now['state']} | {len(text) // 1024}KB")
    return payload


if __name__ == "__main__":
    build()
