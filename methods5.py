#!/usr/bin/env python3
"""Nifty 50 · 10 methods · daily race -> docs/methods.json

Ten always-in rules, each taking a BUY or SELL at every candle close of its own timeframe, all
built from the same NSE-checked Upstox 15-minute candles, fills at the NEXT candle's open,
0.035% per side, trading from 2023-07-03 with warmup on the full history.

The 5 classics:
  sma5200   SMA 5 / SMA 200          15m   the current No.1 (best5200.html)
  st1015    Supertrend 10 / 1.5      1h    real Pine maths: Wilder ATR, ratcheting bands
  psma100   close vs SMA 100         30m   price crossing its own average
  don55     Donchian 55 breakout     15m   the Turtle rule
  ema21105  EMA 21 / EMA 105         15m   the first Best tab (best15.html)

The 5 Fable originals (created, named and owned by Fable; Median and Pace families were
also invented, tested and REJECTED because they lost money):
  f_council    Fable Council       15m  the five classics vote at every close; majority rules
  f_twinpulse  Fable Twin Pulse    15m  1h Supertrend + 30m close/SMA 100 must agree, else hold
  f_quorum     Fable Quorum        15m  at least 4 of 5 classics must agree, else hold
  f_heartbeat  Fable Heartbeat     1h   more up-closes than down in the last 155 candles
  f_centreline Fable Centreline    1h   close vs the centre of the last 55 candles' range

For each: every trade, the complete split (total plus, total minus, open, net), yearly results,
a daily cumulative equity race, and a leaderboard with the reasons written from the numbers.

Run: python methods5.py
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
COST = 0.00035
LOT, LOTS = 65, 10
START = pd.Timestamp("2023-07-03")
AGG = {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
BASE5 = ("sma5200", "st1015", "psma100", "don55", "ema21105")


def sma(x, n):
    return pd.Series(x).rolling(n).mean().to_numpy()


def ffill0(a):
    return pd.Series(a).ffill().fillna(0.0).to_numpy().copy()


def supertrend_up(df, n, m):
    """TradingView ta.supertrend: hl2 +- m * Wilder ATR, bands ratchet, flip on close crossing."""
    h, l, c = (df[k].to_numpy(float) for k in ("High", "Low", "Close"))
    tr1 = np.maximum(h[1:], c[:-1]) - np.minimum(l[1:], c[:-1])
    atr = np.r_[np.nan, pd.Series(tr1).ewm(alpha=1 / n, adjust=False).mean().to_numpy()]
    mid = (h + l) / 2
    ub, lb = mid + m * atr, mid - m * atr
    N = len(c)
    fu, fl, trend = ub.copy(), lb.copy(), np.zeros(N)
    fu[1], fl[1] = ub[1], lb[1]
    for i in range(2, N):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        trend[i] = (-1 if c[i] < fl[i] else 1) if trend[i - 1] >= 0 else (1 if c[i] > fu[i] else -1)
    trend[: n + 2] = 0
    return trend > 0, trend != 0


def sig_sma5200(df):
    c = df["Close"].to_numpy(float)
    up = sma(c, 5) > sma(c, 200)
    v = np.ones(len(c), bool); v[:201] = False
    return up, v


def sig_ema21105(df):
    c = df["Close"].to_numpy(float)
    up = np.nan_to_num(E.pine_ema(c, 21)) > np.nan_to_num(E.pine_ema(c, 105))
    v = np.ones(len(c), bool); v[:106] = False
    return up, v


def sig_don55(df):
    c = df["Close"].to_numpy(float)
    hh = pd.Series(c).rolling(55).max().shift(1).to_numpy()
    ll = pd.Series(c).rolling(55).min().shift(1).to_numpy()
    s = ffill0(np.where(c > hh, 1.0, np.where(c < ll, -1.0, np.nan)))
    s[:56] = 0
    return s > 0, s != 0


def sig_psma100(df):
    c = df["Close"].to_numpy(float)
    up = c > sma(c, 100)
    v = np.ones(len(c), bool); v[:101] = False
    return up, v


def sig_heartbeat(df, n=155):
    c = df["Close"].to_numpy(float)
    sgn = np.r_[0.0, np.sign(np.diff(c))]
    cnt = pd.Series(sgn).rolling(n).sum().to_numpy()
    s = ffill0(np.where(cnt > 0, 1.0, np.where(cnt < 0, -1.0, np.nan)))
    s[: n + 1] = 0
    return s > 0, s != 0


def sig_centreline(df, n=55):
    h, l, c = (df[k].to_numpy(float) for k in ("High", "Low", "Close"))
    mid = (pd.Series(h).rolling(n).max().to_numpy() + pd.Series(l).rolling(n).min().to_numpy()) / 2
    up = c > mid
    v = np.ones(len(c), bool); v[: n + 1] = False
    return up, v


def ens_council(B):
    V = np.vstack([B[k] for k in BASE5])
    ok = (V != 0).all(axis=0)
    vote = V.sum(axis=0)
    s = ffill0(np.where(vote > 0, 1.0, np.where(vote < 0, -1.0, np.nan)))
    s[: int(np.argmax(ok))] = 0
    return s


def ens_quorum(B):
    V = np.vstack([B[k] for k in BASE5])
    ok = (V != 0).all(axis=0)
    vote = V.sum(axis=0)
    s = ffill0(np.where(vote >= 3, 1.0, np.where(vote <= -3, -1.0, np.nan)))
    s[: int(np.argmax(ok))] = 0
    return s


def ens_twinpulse(B):
    a, b = B["st1015"], B["psma100"]
    s = ffill0(np.where((a == b) & (a != 0), a, np.nan))
    both = (a != 0) & (b != 0)
    s[: int(np.argmax(both))] = 0
    return s


METHODS = [
    {"key": "sma5200", "name": "SMA 5/200", "tf": "15m", "family": "Average pair",
     "desc": "BUY when the 5-candle average closes above the 200-candle average (15-minute).", "page": "best5200.html",
     "sig": sig_sma5200},
    {"key": "st1015", "name": "Supertrend 10/1.5", "tf": "1h", "family": "Supertrend",
     "desc": "The real Pine Supertrend: Wilder ATR(10) bands at 1.5x that only tighten; flip when a 1-hour candle closes across the band.",
     "page": None, "sig": lambda df: supertrend_up(df, 10, 1.5)},
    {"key": "psma100", "name": "Close vs SMA 100", "tf": "30m", "family": "Price vs average",
     "desc": "BUY when a 30-minute candle closes above its own 100-candle average, SELL below.", "page": None,
     "sig": sig_psma100},
    {"key": "don55", "name": "Donchian 55", "tf": "15m", "family": "Breakout (Turtle)",
     "desc": "BUY when a close beats the highest close of the previous 55 candles, SELL when it breaks the lowest (15-minute).",
     "page": None, "sig": sig_don55},
    {"key": "ema21105", "name": "EMA 21/105", "tf": "15m", "family": "Average pair",
     "desc": "BUY when EMA 21 closes above EMA 105 (15-minute).", "page": "best15.html", "sig": sig_ema21105},
    {"key": "f_council", "name": "Fable Council", "tf": "15m", "family": "Fable original · ensemble",
     "desc": "Created by Fable: at every 15-minute close the five classics vote BUY or SELL; the majority side is the trade.",
     "page": None, "ens": ens_council},
    {"key": "f_twinpulse", "name": "Fable Twin Pulse", "tf": "15m", "family": "Fable original · ensemble",
     "desc": "Created by Fable: the 1-hour Supertrend and the 30-minute close-vs-SMA-100 must point the same way; while they argue, the last agreed side is held.",
     "page": None, "ens": ens_twinpulse},
    {"key": "f_quorum", "name": "Fable Quorum", "tf": "15m", "family": "Fable original · ensemble",
     "desc": "Created by Fable: flip only when at least 4 of the 5 classics agree; anything less holds the previous side.",
     "page": None, "ens": ens_quorum},
    {"key": "f_heartbeat", "name": "Fable Heartbeat", "tf": "1h", "family": "Fable original",
     "desc": "Created by Fable: count the last 155 one-hour candles; more up-closes than down-closes means BUY, fewer means SELL.",
     "page": None, "sig": sig_heartbeat},
    {"key": "f_centreline", "name": "Fable Centreline", "tf": "1h", "family": "Fable original",
     "desc": "Created by Fable: BUY above the centre of the last 55 one-hour candles' range ((highest high + lowest low) / 2), SELL below.",
     "page": None, "sig": sig_centreline},
]


FORMULAS = {
    "sma5200": "SMA5 = mean of the last 5 closes; SMA200 = mean of the last 200 closes, on 15-minute candles. BUY while SMA5 > SMA200 at a close, SELL while below. The flip order fills at the next 15-minute open. 0.035% of price per side.",
    "st1015": "TR = max(high, previous close) - min(low, previous close); ATR = Wilder average of TR over 10 one-hour candles. Bands = (high+low)/2 +- 1.5 x ATR; the upper band can only fall and the lower can only rise (ratchet). BUY while the close is above the line, flip when a 1-hour close crosses it. Fills at the next open; 0.035% per side.",
    "psma100": "SMA100 = mean of the last 100 closes on 30-minute candles. BUY while the close is above its SMA100, SELL while below. Fills at the next open; 0.035% per side.",
    "don55": "HH = highest close of the previous 55 fifteen-minute candles; LL = lowest. A close above HH flips to BUY; a close below LL flips to SELL; in between, keep the current side. Fills at the next open; 0.035% per side.",
    "ema21105": "EMA with a = 2/(n+1): EMA_t = a x close + (1-a) x EMA_(t-1) (TradingView seeding), n = 21 and 105, on 15-minute candles. BUY while EMA21 > EMA105 at a close, SELL while below. Fills at the next open; 0.035% per side.",
    "f_council": "Created by Fable. At every 15-minute close each of the 5 classics gives s = +1 (BUY) or -1 (SELL); vote = s1+s2+s3+s4+s5. BUY while vote > 0, SELL while vote < 0 (five voters, so never a tie). Fills at the next open; 0.035% per side.",
    "f_twinpulse": "Created by Fable. a = the Supertrend 10/1.5 side on 1-hour candles; b = the close-vs-SMA100 side on 30-minute candles. When a = b, take that side; while they disagree, hold the last agreed side. Checked at every 15-minute close; fills at the next open; 0.035% per side.",
    "f_quorum": "Created by Fable. The same vote as the Council. Flip to BUY only when vote >= +3 (at least 4 of 5 agree), to SELL only when vote <= -3; anything in between holds the previous side. Fills at the next open; 0.035% per side.",
    "f_heartbeat": "Created by Fable. count = (up-closes) - (down-closes) over the last 155 one-hour candles. BUY while count > 0, SELL while count < 0, hold on zero. Fills at the next open; 0.035% per side.",
    "f_centreline": "Created by Fable. mid = (highest high + lowest low of the last 55 one-hour candles) / 2. BUY while the close is above mid, SELL while below. Fills at the next open; 0.035% per side.",
}


def supertrend_line(df, n, m):
    """The Supertrend line itself (lower band in an uptrend, upper band in a downtrend)."""
    h, l, c = (df[k].to_numpy(float) for k in ("High", "Low", "Close"))
    tr1 = np.maximum(h[1:], c[:-1]) - np.minimum(l[1:], c[:-1])
    atr = np.r_[np.nan, pd.Series(tr1).ewm(alpha=1 / n, adjust=False).mean().to_numpy()]
    mid = (h + l) / 2
    ub, lb = mid + m * atr, mid - m * atr
    N = len(c)
    fu, fl, trend = ub.copy(), lb.copy(), np.zeros(N)
    fu[1], fl[1] = ub[1], lb[1]
    line = np.full(N, np.nan)
    for i in range(2, N):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        trend[i] = (-1 if c[i] < fl[i] else 1) if trend[i - 1] >= 0 else (1 if c[i] > fu[i] else -1)
        if i > n + 2:
            line[i] = fl[i] if trend[i] > 0 else fu[i]
    return line


def chart_for(key, frames, bases):
    """One year of the method's own candles plus the exact series its formula watches."""
    tfmap = {"sma5200": "15m", "don55": "15m", "ema21105": "15m", "f_council": "15m", "f_twinpulse": "15m",
             "f_quorum": "15m", "psma100": "30m", "st1015": "1h", "f_heartbeat": "1h", "f_centreline": "1h"}
    df = frames[tfmap[key]]
    t = df.index
    h, l, c = (df[k].to_numpy(float) for k in ("High", "Low", "Close"))
    c0 = int(np.searchsorted(t, t[-1] - pd.Timedelta(days=365)))
    lines, aux = [], []

    def L(name, arr):
        lines.append({"name": name, "values": [round(float(v), 2) if v == v else None for v in arr[c0:]]})

    def A(name, arr):
        aux.append({"name": name, "values": [int(v) if v == v else None for v in arr[c0:]]})

    if key == "sma5200":
        L("SMA 5", sma(c, 5)); L("SMA 200", sma(c, 200))
    elif key == "ema21105":
        L("EMA 21", E.pine_ema(c, 21)); L("EMA 105", E.pine_ema(c, 105))
    elif key == "psma100":
        L("SMA 100", sma(c, 100))
    elif key == "don55":
        L("55-candle high", pd.Series(c).rolling(55).max().shift(1).to_numpy())
        L("55-candle low", pd.Series(c).rolling(55).min().shift(1).to_numpy())
    elif key == "st1015":
        L("Supertrend 10/1.5", supertrend_line(df, 10, 1.5))
    elif key == "f_centreline":
        mid = (pd.Series(h).rolling(55).max().to_numpy() + pd.Series(l).rolling(55).min().to_numpy()) / 2
        L("Centreline (55)", mid)
    elif key == "f_heartbeat":
        sgn = np.r_[0.0, np.sign(np.diff(c))]
        A("Up-closes minus down-closes (155)", pd.Series(sgn).rolling(155).sum().to_numpy())
    elif key in ("f_council", "f_quorum"):
        A("Vote of the 5 classics (-5..+5)", np.vstack([bases[k] for k in BASE5]).sum(axis=0))
    elif key == "f_twinpulse":
        a, b = bases["st1015"], bases["psma100"]
        A("Agreement (+1 BUY, -1 SELL, 0 = holding)", np.where((a == b) & (a != 0), a, 0.0))
    bars = [[str(x)[:16], round(float(r.Open), 2), round(float(r.High), 2), round(float(r.Low), 2), round(float(r.Close), 2)]
            for x, r in df.iloc[c0:].iterrows()]
    return {"key": key, "tf": tfmap[key], "bars": bars, "lines": lines, "aux": aux}


JEV_Q = {"grade": {"type": "choice",
                   "instructions": "This is the complete real backtest record of one always-in Nifty 50 trading rule "
                                   "(points are after costs; every rule was selected on this same history, which the "
                                   "record states). Judging strictly from these numbers - consistency across years, "
                                   "profit factor, drawdown versus net, trade count - how sturdy is this rule?",
                   "criteria": {"sturdy": None, "ordinary": None, "fragile": None}}}


def jev_review(out, generated_at):
    """Jev's typed view per method. Display only: the ranking itself stays pure maths."""
    path = DOCS / "methods_jev.json"
    try:
        from jev_client import Client, MODEL
        client = Client()
    except Exception as e:
        if not path.exists():
            path.write_text(json.dumps({"status": f"unavailable: {e}", "answers": {}}), encoding="utf-8")
        print(f"jev: skipped ({e})")
        return
    answers = {}
    for m in out:
        s = m["summary"]
        state = {"name": m["name"], "timeframe": m["tf"], "family": m["family"],
                 "selection_note": "picked after seeing this same 2023-2026 history; shared out-of-sample starts 2026-11-10",
                 "net_pts": s["net_pts"], "gross_profit_pts": s["plus_pts"], "gross_loss_pts": s["minus_pts"],
                 "open_trade_pts": s["open_pts"], "closed_trades": s["trades"], "win_pct": s["win_pct"],
                 "profit_factor": s["profit_factor"], "worst_fall_pts": s["max_dd_pts"],
                 "yearly_pts": {str(y["year"]): y["pts"] for y in m["years"]}}
        try:
            a = client.ask(state, JEV_Q)["grade"]
            p = a["probabilities"]
            answers[m["key"]] = {"grade": a["choice"], "conf": round(a["confidence"] * 100),
                                 "score": round(100 * p.get("sturdy", 0) + 50 * p.get("ordinary", 0), 1),
                                 "p": {k: round(v, 3) for k, v in p.items()}}
        except Exception as e:
            answers[m["key"]] = {"error": type(e).__name__}
    ok = sum(1 for v in answers.values() if "error" not in v)
    path.write_text(json.dumps({"generated_at": generated_at, "model": MODEL, "status": f"judged {ok}/{len(out)}",
                                "note": "Jev's view is shown next to the maths; the ranking itself uses net points only.",
                                "answers": answers}, separators=(",", ":")), encoding="utf-8")
    print(f"jev: judged {ok}/{len(out)}")


def diary(out, generated_at):
    """Record every change versus the previous published state: opened, closed, flipped."""
    prev = {}
    try:
        prev = {m["key"]: m for m in json.loads((DOCS / "methods.json").read_text(encoding="utf-8"))["methods"]}
    except (OSError, ValueError, KeyError):
        pass
    try:
        events = json.loads((DOCS / "methods_events.json").read_text(encoding="utf-8"))
        assert isinstance(events, list)
    except (OSError, ValueError, AssertionError):
        events = []
    new = []
    for m in out:
        pm = prev.get(m["key"])
        if not pm:
            continue
        seen = {x["entry_time"] for x in pm["trades"] if not x["open"]}
        for x in m["trades"]:
            if not x["open"] and x["entry_time"] not in seen:
                new.append({"at": generated_at, "key": m["key"], "name": m["name"],
                            "text": f"CLOSED {x['side']} {x['entry']:,} -> {x['exit']:,} = {x['net_pts']:+,} pts ({x['rupees']:+,} rupees on 1 lot)"})
        oldo = next((x for x in pm["trades"] if x["open"]), None)
        newo = next((x for x in m["trades"] if x["open"]), None)
        if newo and (not oldo or oldo["entry_time"] != newo["entry_time"]):
            new.append({"at": generated_at, "key": m["key"], "name": m["name"],
                        "text": f"OPENED {newo['side']} at {newo['entry']:,} ({newo['entry_time']} IST)"})
    events = (new + events)[:400]
    (DOCS / "methods_events.json").write_text(json.dumps(events, separators=(",", ":")), encoding="utf-8")
    return len(new)

def replay(df, up, valid):
    """Always in from the first valid close at/after START; signal at close i fills at open i+1."""
    o, c = df["Open"].to_numpy(float), df["Close"].to_numpy(float)
    t = df.index
    start_i = int(np.searchsorted(t, START))
    pos, entry, ent_i = 0, 0.0, None
    trades, real = [], 0.0
    eq = np.zeros(len(c))
    for i in range(start_i, len(c)):
        if i > start_i and valid[i - 1]:
            want = 1 if up[i - 1] else -1
            if want != pos:
                px = float(o[i])
                if pos != 0:
                    net = pos * (px - entry) - COST * (entry + px)
                    real += net
                    trades.append({"side": "BUY" if pos > 0 else "SELL", "entry_time": str(t[ent_i])[:16],
                                   "entry": round(entry, 2), "exit_time": str(t[i])[:16], "exit": round(px, 2),
                                   "net_pts": round(net, 2), "rupees": round(net * LOT), "open": False})
                pos, entry, ent_i = want, px, i
        eq[i] = real + (pos * (c[i] - entry) - COST * entry if pos else 0.0)
    if pos:
        net = pos * (float(c[-1]) - entry) - COST * entry
        trades.append({"side": "BUY" if pos > 0 else "SELL", "entry_time": str(t[ent_i])[:16], "entry": round(entry, 2),
                       "exit_time": None, "exit": round(float(c[-1]), 2), "net_pts": round(net, 2),
                       "rupees": round(net * LOT), "open": True})
    day = pd.Series(eq[start_i:], index=t[start_i:]).groupby(t[start_i:].normalize()).last()
    return trades, day


def build(today=None):
    try:
        df15 = I.fetch(today)
        source = "Upstox 15-minute candles, refreshed this run"
    except Exception as e:                                       # pragma: no cover - network
        print(f"warn: Upstox refresh failed ({type(e).__name__}); using the cached candles")
        df15 = pd.read_csv(I.CACHE, index_col=0, parse_dates=True)
        source = "Upstox 15-minute candles from the cache (refresh failed this run)"
    df15 = df15[["Open", "High", "Low", "Close"]].astype(float)
    frames = {"15m": df15,
              "30m": df15.resample("30min", offset="15min").agg(AGG).dropna(),
              "1h": df15.resample("60min", offset="15min").agg(AGG).dropna()}
    last_t = df15.index[-1]

    def side_on15(df, up, valid):
        s = np.where(valid, np.where(up, 1.0, -1.0), 0.0)
        if df is df15:
            return s
        return pd.Series(s, index=df.index).reindex(df15.index).ffill().fillna(0.0).to_numpy()

    out, days_union, bases = [], None, {}
    for m in METHODS:
        if "ens" in m:
            s = m["ens"](bases)
            df, up, valid = df15, s > 0, s != 0
        else:
            df = frames[m["tf"]]
            up, valid = m["sig"](df)
            if m["key"] in BASE5:
                bases[m["key"]] = side_on15(df, up, valid)
        trades, day = replay(df, up, valid)
        closed = [x for x in trades if not x["open"]]
        p = np.array([x["net_pts"] for x in closed], float)
        plus = float(p[p > 0].sum()) if len(p) else 0.0
        minus = float(p[p <= 0].sum()) if len(p) else 0.0
        op = trades[-1] if trades and trades[-1]["open"] else None
        open_pts = op["net_pts"] if op else 0.0
        net = plus + minus + open_pts
        peak = np.maximum.accumulate(np.r_[0.0, day.to_numpy()])
        dd = float((peak - np.r_[0.0, day.to_numpy()]).max())
        w, lo = p[p > 0], p[p <= 0]
        yr_end = day.groupby(day.index.year).last()
        years, prev = [], 0.0
        for y in yr_end.index:
            years.append({"year": int(y), "pts": round(float(yr_end[y]) - prev, 1)})
            prev = float(yr_end[y])
        eqd = day.to_numpy()
        summary = {
            "net_pts": round(net, 1), "net_rs": round(net * LOT), "net_rs_10": round(net * LOT * LOTS),
            "plus_pts": round(plus, 1), "plus_rs": round(plus * LOT),
            "minus_pts": round(minus, 1), "minus_rs": round(minus * LOT),
            "open_pts": round(open_pts, 1), "trades": len(closed),
            "win_pct": round(float((p > 0).mean()) * 100, 1) if len(p) else 0.0,
            "avg_win": round(float(w.mean()), 1) if len(w) else 0.0,
            "avg_loss": round(float(lo.mean()), 1) if len(lo) else 0.0,
            "profit_factor": round(plus / -minus, 2) if minus else None,
            "best_pts": round(float(p.max()), 1) if len(p) else 0.0,
            "worst_pts": round(float(p.min()), 1) if len(p) else 0.0,
            "max_dd_pts": round(dd, 1), "max_dd_rs": round(dd * LOT),
            "last_session_pts": round(float(eqd[-1] - eqd[-2]), 1) if len(eqd) > 1 else 0.0,
            "last20_pts": round(float(eqd[-1] - eqd[-21]), 1) if len(eqd) > 20 else round(float(eqd[-1]), 1),
            "y2026_pts": next((x["pts"] for x in years if x["year"] == 2026), 0.0),
        }
        why = (f"Wins {summary['win_pct']}% of {summary['trades']} trades; the average win +{summary['avg_win']} is "
               f"{abs(round(summary['avg_win'] / summary['avg_loss'], 1)) if summary['avg_loss'] else '-'}x the average loss "
               f"{summary['avg_loss']}; profit factor {summary['profit_factor']}; best trade +{summary['best_pts']:,}; "
               f"2026 so far {summary['y2026_pts']:+,} points.")
        out.append({"key": m["key"], "name": m["name"], "tf": m["tf"], "family": m["family"], "desc": m["desc"],
                    "page": m["page"], "summary": summary, "years": years, "why": why, "trades": trades,
                    "now": {"side": op["side"] if op else None, "entry": op["entry"] if op else None,
                            "entry_time": op["entry_time"] if op else None, "open_pts": round(open_pts, 1)},
                    "_day": day})
        days_union = day.index if days_union is None else days_union.union(day.index)

    race = []
    series = {m["key"]: m["_day"].reindex(days_union).ffill().fillna(0.0) for m in out}
    for d in days_union:
        race.append([str(d.date())] + [round(float(series[m["key"]][d]), 1) for m in out])
    for m in out:
        del m["_day"]

    rank = sorted(out, key=lambda m: -m["summary"]["net_pts"])
    lead, second = rank[0], rank[1]
    gap = round(lead["summary"]["net_pts"] - second["summary"]["net_pts"], 1)
    reasons = [f"{lead['name']} ({lead['tf']}) leads with {lead['summary']['net_pts']:+,} points, {gap:+,} ahead of {second['name']}.",
               f"Complete P&L of the leader: +{lead['summary']['plus_pts']:,} from winners, {lead['summary']['minus_pts']:,} from losers, "
               f"{lead['summary']['open_pts']:+,} in the open trade = {lead['summary']['net_pts']:+,} net "
               f"(Rs {lead['summary']['net_rs']:,} on 1 lot).",
               f"Why: profit factor {lead['summary']['profit_factor']} vs {second['name']}'s {second['summary']['profit_factor']}, "
               f"worst fall {lead['summary']['max_dd_pts']:,} vs {second['summary']['max_dd_pts']:,} points.",
               f"Last session: " + ", ".join(f"{m['name']} {m['summary']['last_session_pts']:+,}" for m in rank) + " points.",
               f"Sides right now: " + ", ".join(f"{m['name']} {m['now']['side']}" for m in rank) + "."]

    for m in out:
        m["formula"] = FORMULAS[m["key"]]
        m["chart"] = f"method_{m['key']}.json"
    generated_at = datetime.now(I.IST).isoformat(timespec="minutes")
    for m in out:
        (DOCS / m["chart"]).write_text(json.dumps(chart_for(m["key"], frames, bases), separators=(",", ":")), encoding="utf-8")
    new_events = diary(out, generated_at)
    jev_review(out, generated_at)

    payload = {"version": 3, "name": "Nifty 50 · 10 methods · daily race",
               "generated_at": generated_at, "new_events": new_events,
               "as_of": str(last_t.date()), "last_candle": str(last_t)[:16], "from": str(START.date()),
               "source": source, "cost_side_pct": COST * 100, "lot": LOT, "lots": LOTS,
               "methods": out, "ranking": [m["key"] for m in rank], "reasons": reasons, "race": race,
               "total_closed_trades": sum(m["summary"]["trades"] for m in out),
               "limits": ["All ten were picked after looking at this same history; their honest shared out-of-sample record starts 10 Nov 2026.",
                          "The Fable ensembles (Council, Quorum, Twin Pulse) reuse the five classics, so they inherit their selection bias too.",
                          "Two more Fable inventions - close vs rolling median, and the regression-slope sign - were tested the same way and REJECTED because they lost money. Only survivors are shown.",
                          "Supertrend 10/1.5 was chosen from 30 period/multiplier/timeframe combinations, so treat its edge as the least proven.",
                          "Fills are assumed exactly at each next open; positions are held overnight.",
                          "Paper research. Not SEBI-registered advice. No orders are placed by this website."]}
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for outp in (DOCS / "methods.json", PUBLIC / "methods.json"):
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(text, encoding="utf-8")
    print(f"methods.json {payload['from']} -> {payload['last_candle']} | " +
          " | ".join(f"{m['name']} {m['summary']['net_pts']:+,.0f}" for m in rank) +
          f" | {payload['total_closed_trades']} closed trades | {len(text) // 1024}KB")
    return payload


if __name__ == "__main__":
    build()
