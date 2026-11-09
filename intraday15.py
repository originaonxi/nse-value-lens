#!/usr/bin/env python3
"""Nifty 50 · 15-minute candles · intraday only · EMA 9 or lower · ₹1 crore one year back.

Data: Nifty 50 index 15-minute candles from Upstox's public historical-candle API (no login), cached in
data/nifty/upstox_15m.csv. Every day is checked against NSE's official index open/high/low/close
(data/nifty/official_daily.csv, from the NSE index close files) and against the Yahoo 15-minute bars we keep.

Rules (all intraday: no position is ever held overnight):
  signal   close vs EMA n (n = 2..9), or EMA fast vs EMA slow (2 <= fast < slow <= 9)
  side     buy only, sell (short) only, or both
  filter   none · day open side · previous close side · opening-range break · daily EMA 9 trend · day open + daily EMA 9
  window   first trade from 09:30, 09:45 or 10:30 · flat at 15:15 or 14:45
  exits    the signal turns, the window ends, or (stage 2) an ATR stop / ATR target
A decision is made on a 15-minute close and filled at the next candle's open. Everything is closed at the
open of the 15:15 candle (or 14:45). Cost 0.035% of the position per round trip.

Pick: most Nifty points over the last 200 sessions, among rules with 60+ trades that made money in both
100-session halves. Honest pick: the same rule search, judged only on the 200 sessions before those.

Money: ₹1,00,00,000 put in one year back, whole NIFTY futures lots (lot size from the NSE F&O bhavcopy),
no leverage, gains compound.

Run: python intraday15.py   -> docs/intraday.json
"""
import itertools
import json
import math
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
DOCS, PUBLIC = ROOT / "docs", ROOT / "public" / "data"
CACHE = ROOT / "data" / "nifty" / "upstox_15m.csv"
OFFICIAL = ROOT / "data" / "nifty" / "official_daily.csv"
YAHOO15 = ROOT / "data" / "nifty" / "15m.csv"
IST = ZoneInfo("Asia/Kolkata")
KEY = "NSE_INDEX|Nifty 50"
API = "https://api.upstox.com/v3/historical-candle/{key}/minutes/15/{to}/{frm}"
API_TODAY = "https://api.upstox.com/v3/historical-candle/intraday/{key}/minutes/15"
FIRST_MONTH = date(2023, 1, 1)

CAPITAL = 1_00_00_000
COST_RT = 0.00035            # per round trip, share of the position (STT, exchange, stamp, GST, brokerage, ~1 pt slippage)
LAST, MIN_TRADES, MIN_BARS = 200, 60, 20
EMAS = range(2, 10)
FILTERS = ["none", "day open", "prev close", "opening range", "daily EMA 9", "day open + daily EMA 9"]
STARTS = ["09:30", "09:45", "10:30"]
FLATS = ["15:15", "14:45"]
SIDES = ["both", "buy", "sell"]
STOPS = [None, 0.5, 1.0, 1.5, 2.0]
TARGETS = [None, 1.0, 2.0, 3.0]
STAGE2 = 40


# ── data ──────────────────────────────────────────────────────────────────────

def _get(url):
    for i in range(4):
        try:
            r = requests.get(url, headers={"Accept": "application/json"}, timeout=30)
            if r.status_code == 200:
                return (r.json().get("data") or {}).get("candles") or []
            if r.status_code in (429, 500, 502, 503):
                time.sleep(2 ** i)
                continue
            return []
        except requests.RequestException:
            time.sleep(2 ** i)
    return []


def _frame(candles):
    if not candles:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close"])
    f = pd.DataFrame(candles, columns=["t", "Open", "High", "Low", "Close", "v", "oi"])
    f.index = pd.to_datetime(f.t, utc=True).dt.tz_convert(IST).dt.tz_localize(None)
    return f[["Open", "High", "Low", "Close"]].astype(float)


def fetch(today=None):
    """Cached 15-minute candles + any missing months + today's candles. Returns a sorted frame (IST wall clock)."""
    today = today or datetime.now(IST).date()
    key = urllib.parse.quote(KEY, safe="")
    have = pd.read_csv(CACHE, index_col=0, parse_dates=True) if CACHE.exists() else pd.DataFrame()
    start = (have.index.max().date().replace(day=1) if len(have) else FIRST_MONTH)
    parts, m = [have], start
    while m <= today:
        nxt = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
        to = min(nxt - timedelta(days=1), today)
        parts.append(_frame(_get(API.format(key=key, to=to.isoformat(), frm=m.isoformat()))))
        m = nxt
        time.sleep(0.3)
    parts.append(_frame(_get(API_TODAY.format(key=key))))
    df = pd.concat([p for p in parts if len(p)])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    t = df.index.time
    df = df[(t >= pd.Timestamp("09:15").time()) & (t <= pd.Timestamp("15:15").time())]
    now = datetime.now(IST).replace(tzinfo=None)
    df = df[df.index + pd.Timedelta(minutes=15) <= now]                 # finished candles only
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.round(2).to_csv(CACHE)
    return df


def check_data(df):
    """Day by day against NSE's official index OHLC, bar by bar against the Yahoo 15-minute cache."""
    g = df.groupby(df.index.date)
    day = pd.DataFrame({"open": g.Open.first(), "high": g.High.max(), "low": g.Low.min(), "close": g.Close.last(), "bars": g.size()})
    day.index = day.index.astype(str)
    out = {"sessions": int(len(day)), "from": day.index[0], "to": day.index[-1],
           "short_days": {d: int(b) for d, b in day.bars.items() if b != 25}}
    if OFFICIAL.exists():
        off = pd.read_csv(OFFICIAL, index_col=0)
        off.index = off.index.astype(str)
        j = day.join(off[["ind_open", "ind_high", "ind_low", "ind_close"]], how="inner").dropna()
        f = {}
        for k in ("open", "high", "low", "close"):
            d = (j[k] - j["ind_" + k]).abs()
            f[k] = {"median_pts": round(float(d.median()), 2), "p95_pts": round(float(d.quantile(.95)), 2),
                    "max_pts": round(float(d.max()), 2), "days_over_0.05pct": int((d / j["ind_" + k] > 0.0005).sum())}
        ours = j[["open", "high", "low", "close"]].to_numpy()
        nse = j[["ind_open", "ind_high", "ind_low", "ind_close"]].to_numpy()
        within = (np.abs(ours - nse) / nse).max(axis=1) <= 0.0005
        out["vs_nse"] = {"days": int(len(j)), "fields": f, "days_all_within_0.05pct": int(within.sum())}
    if YAHOO15.exists():
        y = pd.read_csv(YAHOO15, index_col=0)
        y.index = pd.to_datetime(y.index, utc=True).tz_convert(IST).tz_localize(None)
        j = df.join(y[["Close"]].rename(columns={"Close": "yc"}), how="inner").dropna()
        if len(j):
            d = (j.Close - j.yc).abs()
            out["vs_yahoo_15m"] = {"bars": int(len(j)), "median_pts": round(float(d.median()), 2),
                                   "p95_pts": round(float(d.quantile(.95)), 2), "max_pts": round(float(d.max()), 2)}
    return out


# ── features ──────────────────────────────────────────────────────────────────

def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def wilder(x, n):
    return pd.Series(x).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def features(df):
    O, H, L, C = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    days = df.index.normalize()
    dstr = np.array([str(d.date()) for d in days])
    uniq, did = np.unique(dstr, return_inverse=True)
    n = len(C)
    newday = np.r_[True, did[1:] != did[:-1]]
    lastbar = np.r_[did[1:] != did[:-1], True]
    hhmm = df.index.hour * 100 + df.index.minute
    pc = np.r_[C[0], C[:-1]]
    tr = np.maximum(H - L, np.maximum(abs(H - pc), abs(L - pc)))
    X = {"O": O, "H": H, "L": L, "C": C, "did": did, "days": uniq, "newday": newday, "lastbar": lastbar,
         "hhmm": np.asarray(hhmm), "atr": wilder(tr, 14), "n": n, "time": df.index}
    X["ema"] = {k: ema(C, k) for k in EMAS}
    # per-day reference levels (known at each bar's close)
    dopen = pd.Series(O).groupby(did).transform("first").to_numpy()
    orh = pd.Series(H).groupby(did).transform("first").to_numpy()
    orl = pd.Series(L).groupby(did).transform("first").to_numpy()
    dclose = pd.Series(C).groupby(did).last().to_numpy()                 # last 15-minute close per day
    prev_close = np.r_[np.nan, dclose[:-1]][did]
    de9 = ema(dclose, 9)
    trend = np.sign(dclose - de9)                                        # known at that day's close
    prev_trend = np.r_[0, trend[:-1]][did]                               # yesterday's -> usable all of today
    X.update(dopen=dopen, orh=orh, orl=orl, prev_close=prev_close, dclose=dclose, de9=de9, prev_trend=prev_trend)
    first = newday.copy()
    F = {"none": (np.ones(n, bool), np.ones(n, bool)),
         "day open": (C > dopen, C < dopen),
         "prev close": (C > prev_close, C < prev_close),
         "opening range": ((C > orh) & ~first, (C < orl) & ~first),
         "daily EMA 9": (prev_trend > 0, prev_trend < 0)}
    F["day open + daily EMA 9"] = (F["day open"][0] & F["daily EMA 9"][0], F["day open"][1] & F["daily EMA 9"][1])
    X["F"] = F
    bars_in_day = np.bincount(did)
    X["full"] = bars_in_day[did] >= MIN_BARS
    return X


def signal(X, sig):
    C = X["C"]
    if sig[0] == "px":
        return np.sign(C - X["ema"][sig[1]])
    return np.sign(X["ema"][sig[1]] - X["ema"][sig[2]])


def hm(s):
    h, m = s.split(":")
    return int(h) * 100 + int(m)


def desired(X, r):
    """Position wanted for each held candle k (decided at the close of k-1, filled at the open of k)."""
    s = signal(X, r["sig"])
    if r["side"] == "buy":
        s = np.maximum(s, 0)
    elif r["side"] == "sell":
        s = np.minimum(s, 0)
    fl, fs = X["F"][r["filt"]]
    s = np.where((s > 0) & fl, 1.0, np.where((s < 0) & fs, -1.0, 0.0))     # filters read at the same close
    d = np.r_[0.0, s[:-1]]                                               # decided at close k-1, held during k
    ok = (~X["newday"]) & (~X["lastbar"]) & X["full"] & (X["hhmm"] >= hm(r["start"])) & (X["hhmm"] < hm(r["flat"]))
    return np.where(ok, d, 0.0)


# ── stage 1: vectorised, no stops ─────────────────────────────────────────────

def trades_vec(X, p):
    """Trades from a held-position array: entry bar, exit bar (filled at its open), side, gross points, entry price."""
    O = X["O"]
    prev = np.r_[0.0, p[:-1]]
    nxt = np.r_[p[1:], 0.0]
    starts = np.flatnonzero((p != 0) & ((p != prev) | X["newday"]))
    ends = np.flatnonzero((p != 0) & ((p != nxt) | X["lastbar"]))
    ex = ends + 1
    side = p[starts]
    gross = side * (O[ex] - O[starts])
    return starts, ex, side, gross, O[starts]


def stats(X, tr, d0, d1=None, cost=None):
    cost = COST_RT if cost is None else cost
    s, e, side, gross, ep = tr
    did = X["did"][s]
    m = (did >= d0) & (did < (d1 if d1 is not None else 10 ** 9))
    net = gross[m] - cost * ep[m]
    if not len(net):
        return {"n": 0, "net": 0.0, "win": None, "pf": None, "dd": 0.0}
    eq = np.r_[0.0, np.cumsum(net)]
    w = net > 0
    gl = -net[~w].sum()
    return {"n": int(len(net)), "net": round(float(net.sum()), 1), "win": round(float(w.mean() * 100), 1),
            "pf": round(float(net[w].sum() / gl), 2) if gl > 0 else None,
            "dd": round(float((np.maximum.accumulate(eq) - eq).max()), 1), "avg": round(float(net.mean()), 2),
            "buy": round(float(net[side[m] > 0].sum()), 1), "sell": round(float(net[side[m] < 0].sum()), 1)}


def rules():
    sigs = [("px", k) for k in EMAS] + [("x", a, b) for a, b in itertools.combinations(EMAS, 2)]
    for sig, side, filt, start, flat in itertools.product(sigs, SIDES, FILTERS, STARTS, FLATS):
        yield {"sig": sig, "side": side, "filt": filt, "start": start, "flat": flat, "sl": None, "tp": None}


# ── stage 2: bar-by-bar with ATR stop / target ────────────────────────────────

def simulate(X, r):
    """Same rule as trades_vec plus an ATR stop and target. After a stop or target the rule waits for a
    fresh signal (the wanted side must change) before it trades that side again the same day."""
    if r["sl"] is None and r["tp"] is None:
        return trades_vec(X, desired(X, r))
    p = desired(X, r).tolist()
    O, H, L = X["O"].tolist(), X["H"].tolist(), X["L"].tolist()
    atr, newday = X["atr"].tolist(), X["newday"].tolist()
    S, E, SD, G, EP = [], [], [], [], []
    pos, ep, stop, tgt, blocked, ei = 0, 0.0, None, None, 0, 0
    for k in range(X["n"]):
        if newday[k]:
            blocked = 0
        want = p[k]
        if blocked and want != blocked:
            blocked = 0
        if blocked:
            want = 0
        if pos and want != pos:                                          # signal / window exit at the open
            S.append(ei); E.append(k); SD.append(pos); G.append(pos * (O[k] - ep)); EP.append(ep)
            pos = 0
        if not pos and want:
            pos, ep, ei = want, O[k], k
            a = atr[k - 1]
            stop = ep - pos * r["sl"] * a if r["sl"] else None
            tgt = ep + pos * r["tp"] * a if r["tp"] else None
        if pos:
            px = None
            gap = k != ei                                                   # later candles can open past the level
            if stop is not None and ((pos > 0 and L[k] <= stop) or (pos < 0 and H[k] >= stop)):
                px = (min(O[k], stop) if pos > 0 else max(O[k], stop)) if gap else stop      # stop first: the worse case
            elif tgt is not None and ((pos > 0 and H[k] >= tgt) or (pos < 0 and L[k] <= tgt)):
                px = (max(O[k], tgt) if pos > 0 else min(O[k], tgt)) if gap else tgt
            if px is not None:
                S.append(ei); E.append(k); SD.append(pos); G.append(pos * (px - ep)); EP.append(ep)
                blocked, pos = pos, 0
    a = lambda v, t=float: np.asarray(v, dtype=t)
    return a(S, int), a(E, int), a(SD), a(G), a(EP)


# ── labels ────────────────────────────────────────────────────────────────────

def label(r):
    s = r["sig"]
    sig = f"15-min close above / below EMA {s[1]}" if s[0] == "px" else f"EMA {s[1]} above / below EMA {s[2]}"
    side = {"both": "BUY above, SELL (short) below", "buy": "BUY only", "sell": "SELL (short) only"}[r["side"]]
    ex = [f"from {r['start']}", f"flat by {r['flat']}"]
    if r["filt"] != "none":
        ex.insert(0, f"filter: {r['filt']}")
    if r["sl"]:
        ex.append(f"stop {r['sl']:g} ATR")
    if r["tp"]:
        ex.append(f"target {r['tp']:g} ATR")
    return f"{sig} · {side} · " + " · ".join(ex)


def key(r):
    return json.dumps({k: r[k] for k in ("sig", "side", "filt", "start", "flat", "sl", "tp")})


# ── money ─────────────────────────────────────────────────────────────────────

def lot_sizes(days):
    if not OFFICIAL.exists():
        return {d: 75 for d in days}
    off = pd.read_csv(OFFICIAL, index_col=0)
    off.index = off.index.astype(str)
    known = {d: int(v) for d, v in off["lot"].items() if v == v and v}
    out = {}
    for d in days:
        prev = [k for k in known if k <= d]
        out[d] = known[max(prev)] if prev else known[min(known)]
    return out


def money(X, tr, d0, lots, capital=CAPITAL, lev=1.0, name="", cost=None):
    cost = COST_RT if cost is None else cost
    """Whole lots, gains compound. Returns trade rows, the daily P&L and a summary."""
    s, e, side, gross, ep = tr
    O, did, days, T = X["O"], X["did"], X["days"], X["time"]
    cash = float(capital)
    rows, daily = [], {}
    order = np.argsort(s)
    for i in order:
        if did[s[i]] < d0:
            continue
        day = days[did[s[i]]]
        lot = lots.get(day, 75)
        price_in = float(ep[i])
        price_out = price_in + float(gross[i]) * float(side[i])
        q = int(cash * lev // (price_in * lot))
        if q <= 0:
            continue
        pts = float(side[i]) * (price_out - price_in)
        fee = cost * q * lot * price_in
        pnl = pts * q * lot - fee
        cash += pnl
        daily[day] = daily.get(day, 0.0) + pnl
        rows.append({"day": day, "side": "BUY" if side[i] > 0 else "SELL", "in_time": str(T[s[i]])[11:16], "in": round(price_in, 2),
                     "out_time": str(T[e[i]])[11:16] if e[i] < len(T) else "", "out": round(price_out, 2),
                     "lots": q, "lot": lot, "points": round(pts, 2), "cost": round(fee), "pnl": round(pnl), "cash": round(cash),
                     "t_in": int(s[i]), "t_out": int(e[i])})
    all_days = [d for d in days[d0:]]
    dp = np.array([daily.get(d, 0.0) for d in all_days])
    eq = capital + np.cumsum(dp)
    pk = np.maximum.accumulate(np.r_[capital, eq])[1:]
    pnl = np.array([r["pnl"] for r in rows]) if rows else np.zeros(0)
    traded = dp[[d in daily for d in all_days]]
    months = {}
    for d, v in zip(all_days, dp):
        months.setdefault(d[:7], [0.0, 0])
        months[d[:7]][0] += v
        months[d[:7]][1] += d in daily
    summ = {"name": name, "start": capital, "end": round(float(eq[-1])) if len(eq) else capital,
            "profit": round(float(eq[-1] - capital)) if len(eq) else 0,
            "return_pct": round(float((eq[-1] / capital - 1) * 100), 2) if len(eq) else 0.0,
            "made": round(float(pnl[pnl > 0].sum())), "lost": round(float(pnl[pnl <= 0].sum())),
            "costs": int(sum(r["cost"] for r in rows)), "trades": len(rows), "wins": int((pnl > 0).sum()),
            "win_pct": round(float((pnl > 0).mean() * 100), 1) if len(pnl) else None,
            "max_dd": round(float((pk - eq).max())) if len(eq) else 0,
            "max_dd_pct": round(float(((pk - eq) / pk).max() * 100), 2) if len(eq) else 0.0,
            "days": len(all_days), "days_traded": len(daily), "green_days": int((traded > 0).sum()), "red_days": int((traded < 0).sum()),
            "best_day": round(float(dp.max())) if len(dp) else 0, "worst_day": round(float(dp.min())) if len(dp) else 0,
            "avg_day": round(float(traded.mean())) if len(traded) else 0,
            "months": [{"month": m, "pnl": round(v[0]), "days_traded": v[1]} for m, v in sorted(months.items())],
            "curve": [[d, round(float(v))] for d, v in zip(all_days, eq)]}
    return rows, summ


# ── Jev ───────────────────────────────────────────────────────────────────────

def jev_review(items):
    try:
        from jev_client import Client, MODEL
        client = Client()
    except Exception as e:  # pragma: no cover - needs the key
        return {"status": f"unavailable: {e}", "model": None, "answers": {}}
    Q = {"overfit": {"type": "choice", "criteria": {"low": None, "medium": None, "high": None}, "instructions": (
            "This is a Nifty 50 intraday futures rule on 15-minute candles, picked from thousands of EMA rules. Given the "
            "number of trades, profit factor, the result in each half, the worst fall, the cost-doubled result and how the "
            "rule picked only on earlier data did, how likely is it that the profit shown is luck from fitting the past?")},
         "real_money": {"type": "choice", "criteria": {"paper only": None, "small size": None, "full size": None},
                        "instructions": "Would a careful risk manager put real money behind this, judged only on these numbers?"}}
    out = {}
    for name, state in items.items():
        try:
            a = client.ask(state, Q)
            out[name] = {k: {"choice": v["choice"], "conf": round(v["confidence"] * 100)} for k, v in a.items()}
        except Exception as e:  # pragma: no cover - network
            out[name] = {"error": type(e).__name__}
    return {"status": f"judged {sum('error' not in v for v in out.values())}/{len(items)}", "model": MODEL, "answers": out}


# ── next session ──────────────────────────────────────────────────────────────

def next_session(X, r):
    i = X["n"] - 1
    s = r["sig"]
    lines = []
    e_now = {k: round(float(X["ema"][k][i]), 2) for k in EMAS}
    if s[0] == "px":
        lv = e_now[s[1]]
        if r["side"] in ("both", "buy"):
            lines.append(f"BUY when a 15-min candle closes above EMA {s[1]} (now {lv:,.2f}; it moves with every candle)")
        if r["side"] in ("both", "sell"):
            lines.append(f"SELL (short) when a 15-min candle closes below EMA {s[1]} (now {lv:,.2f})")
    else:
        a, b = s[1], s[2]
        state = "above" if e_now[a] > e_now[b] else "below"
        lines.append(f"EMA {a} is {state} EMA {b} now ({e_now[a]:,.2f} vs {e_now[b]:,.2f})")
        if r["side"] in ("both", "buy"):
            lines.append(f"BUY when a 15-min candle closes with EMA {a} above EMA {b}; sell it when EMA {a} closes back below")
        if r["side"] in ("both", "sell"):
            lines.append(f"SELL (short) when a 15-min candle closes with EMA {a} below EMA {b}; buy it back when EMA {a} closes back above")
        if r["side"] == "sell":
            lines.append("This rule never buys: when Nifty is rising it stays out")
    f = r["filt"]
    trend = "up" if X["dclose"][-1] > X["de9"][-1] else "down"
    buys, sells = r["side"] in ("both", "buy"), r["side"] in ("both", "sell")
    both = lambda b, s: " and ".join(x for x, ok in ((b, buys), (s, sells)) if ok)
    if "daily EMA 9" in f:
        allowed = (trend == "up" and buys) or (trend == "down" and sells)
        lines.append(f"Daily EMA 9 filter: today's close {X['dclose'][-1]:,.2f} is {'above' if trend == 'up' else 'below'} the daily EMA 9 "
                     f"{X['de9'][-1]:,.2f}, so tomorrow it " + (f"may {'buy' if trend == 'up' else 'short'}" if allowed else "takes no trades"))
    if "day open" in f:
        lines.append("Day-open filter: " + both("buys only while price is above tomorrow's 09:15 open", "shorts only while price is below tomorrow's 09:15 open"))
    if f == "prev close":
        lines.append(f"Previous-close filter: " + both(f"buys only above today's last close {X['dclose'][-1]:,.2f}",
                                                         f"shorts only below today's last close {X['dclose'][-1]:,.2f}"))
    if f == "opening range":
        lines.append("Opening-range filter: " + both("buys only above the high of the 09:15 candle", "shorts only below the low of the 09:15 candle"))
    lines.append(f"First entry at {r['start']} at the earliest; everything is closed at the {r['flat']} open")
    if r["sl"]:
        lines.append(f"Stop {r['sl']:g} ATR from the entry (15-min ATR now {X['atr'][i]:,.1f} pts = {r['sl'] * X['atr'][i]:,.0f} pts)")
    if r["tp"]:
        lines.append(f"Target {r['tp']:g} ATR ({r['tp'] * X['atr'][i]:,.0f} pts)")
    return {"close": round(float(X["C"][i]), 2), "emas": e_now, "daily_trend": trend, "atr": round(float(X["atr"][i]), 1), "lines": lines}


# ── build ─────────────────────────────────────────────────────────────────────

def build(today=None):
    t0 = time.time()
    df = fetch(today)
    check = check_data(df)
    X = features(df)
    full_days = np.flatnonzero(np.bincount(X["did"]) >= MIN_BARS)
    D = len(X["days"])
    d200 = int(full_days[-LAST])
    dmid = int(full_days[-LAST // 2])
    dpre = int(full_days[-2 * LAST])
    one_year = (date.fromisoformat(X["days"][-1]) - timedelta(days=365)).isoformat()
    dyear = int(np.argmax(X["days"] >= one_year))
    print(f"15m candles {check['from']} -> {check['to']} ({check['sessions']} sessions) | last 200 from {X['days'][d200]} | "
          f"1 year from {X['days'][dyear]}", flush=True)

    # stage 1
    R = list(rules())
    rows = []
    for r in R:
        tr = trades_vec(X, desired(X, r))
        a, h1, h2, pre = stats(X, tr, d200), stats(X, tr, d200, dmid), stats(X, tr, dmid), stats(X, tr, dpre, d200)
        rows.append({"r": r, "last200": a, "h1": h1, "h2": h2, "pre": pre})
    print(f"stage 1: {len(rows)} rules in {time.time() - t0:.0f}s", flush=True)

    def robust(x):
        return x["last200"]["n"] >= MIN_TRADES and x["h1"]["net"] > 0 and x["h2"]["net"] > 0

    def robust_pre(x):
        return x["pre"]["n"] >= MIN_TRADES

    # stage 2: stops and targets on the best 40 by the last 200 and the best 40 on the earlier 200
    top = sorted([x for x in rows if robust(x)], key=lambda x: -x["last200"]["net"])[:STAGE2]
    top_pre = sorted([x for x in rows if robust_pre(x)], key=lambda x: -x["pre"]["net"])[:STAGE2]
    seen = {key(x["r"]) for x in rows}
    for base in top + top_pre:
        for sl, tp in itertools.product(STOPS, TARGETS):
            if sl is None and tp is None:
                continue
            r = dict(base["r"], sl=sl, tp=tp)
            if key(r) in seen:
                continue
            seen.add(key(r))
            tr = simulate(X, r)
            rows.append({"r": r, "last200": stats(X, tr, d200), "h1": stats(X, tr, d200, dmid), "h2": stats(X, tr, dmid),
                         "pre": stats(X, tr, dpre, d200)})
    tried = len(rows)
    print(f"stage 2: {tried} rules in {time.time() - t0:.0f}s", flush=True)

    rob = sorted([x for x in rows if robust(x)], key=lambda x: -x["last200"]["net"])
    best = rob[0] if rob else max(rows, key=lambda x: x["last200"]["net"])
    raw = max([x for x in rows if x["last200"]["n"] >= MIN_TRADES], key=lambda x: x["last200"]["net"])
    honest = max([x for x in rows if robust_pre(x)], key=lambda x: x["pre"]["net"])
    ema9 = next(x for x in rows if x["r"] == {"sig": ("px", 9), "side": "both", "filt": "none", "start": "09:30", "flat": "15:15", "sl": None, "tp": None})
    ema9b = next(x for x in rows if x["r"] == {"sig": ("px", 9), "side": "buy", "filt": "none", "start": "09:30", "flat": "15:15", "sl": None, "tp": None})

    # money: ₹1 crore one year back
    lots = lot_sizes(list(X["days"]))
    named = [("The winner (most points, last 200 sessions)", best), ("Picked only on the 200 sessions before (honest)", honest),
             ("EMA 9 alone · buy and sell all day", ema9), ("EMA 9 alone · buy only", ema9b)]
    if key(raw["r"]) != key(best["r"]):
        named.insert(1, ("Most points, even if one half lost", raw))
    port, trades_by, port200 = [], {}, []
    for nm, x in named:
        tr = simulate(X, x["r"])
        rws, sm = money(X, tr, dyear, lots, name=nm)
        sm.update(rule=label(x["r"]), last200=x["last200"], h1=x["h1"], h2=x["h2"], pre=x["pre"])
        port.append(sm)
        trades_by[nm] = rws
        _, s200 = money(X, tr, d200, lots, name=nm)
        port200.append({k: s200[k] for k in ("name", "end", "profit", "return_pct", "made", "lost", "trades", "win_pct", "max_dd_pct")})
    # leverage and double cost for the winner, Nifty held
    tr = simulate(X, best["r"])
    _, lev3 = money(X, tr, dyear, lots, lev=3.0, name="The winner at 3x margin")
    _, dbl = money(X, tr, dyear, lots, name="The winner with costs doubled (0.07%)", cost=2 * COST_RT)
    s2 = stats(X, tr, d200, cost=2 * COST_RT)
    i0 = int(np.argmax(X["did"] == dyear))
    hold = {"name": "Nifty 50 bought and held", "start": CAPITAL, "end": round(CAPITAL * X["C"][-1] / X["O"][i0]),
            "return_pct": round((X["C"][-1] / X["O"][i0] - 1) * 100, 2)}
    hold["profit"] = hold["end"] - CAPITAL

    # chart: last 60 sessions, the winner's EMAs and every trade
    c0 = int(np.argmax(X["did"] >= max(0, D - 60)))
    ct = lambda k: int(pd.Timestamp(X["time"][k]).value // 1_000_000_000)
    s = best["r"]["sig"]
    lines = [s[1]] if s[0] == "px" else [s[1], s[2]]
    win_rows = trades_by[named[0][0]]
    marks = []
    for t in win_rows:
        if t["t_in"] >= c0:
            buy = t["side"] == "BUY"
            marks.append([ct(t["t_in"]), "in", t["side"], f"{t['side']} {t['lots']}"])
            if t["t_out"] < X["n"]:
                marks.append([ct(t["t_out"]), "out", t["side"], f"{'+' if t['pnl'] > 0 else '−'}₹{abs(t['pnl']) / 1e5:.2f}L"])
    chart = {"bars": [[ct(k), round(X["O"][k], 2), round(X["H"][k], 2), round(X["L"][k], 2), round(X["C"][k], 2)] for k in range(c0, X["n"])],
             "emas": {str(n): [round(float(X["ema"][n][k]), 2) for k in range(c0, X["n"])] for n in lines},
             "markers": marks, "day_starts": [ct(k) for k in range(c0, X["n"]) if X["newday"][k]]}
    today_trades = [t for t in win_rows if t["day"] == X["days"][-1]]
    slim = lambda x: {"rule": label(x["r"]), "last200": x["last200"], "h1": x["h1"], "h2": x["h2"], "pre": x["pre"]}

    review = {}
    for sm in port[:3]:
        review[sm["name"]] = {k: sm[k] for k in ("rule", "return_pct", "max_dd_pct", "trades", "win_pct", "made", "lost")} | {
            "last200_points": sm["last200"], "rules_tried": tried, "honest_pick_one_year_return_pct": port[1]["return_pct"] if len(port) > 1 else None,
            "cost_doubled_one_year_return_pct": dbl["return_pct"], "nifty_held_return_pct": hold["return_pct"]}
    jev = jev_review(review)

    payload = {
        "version": 1, "name": "Nifty 50 · 15-minute intraday · EMA 9 or lower", "generated_at": datetime.now(IST).isoformat(timespec="minutes"),
        "as_of": X["days"][-1], "last_candle": str(X["time"][-1])[:16], "capital": CAPITAL, "cost_pct": COST_RT * 100,
        "data": check, "source": "Upstox public historical-candle API (NSE_INDEX|Nifty 50, 15 minute)",
        "windows": {"last200_from": X["days"][d200], "half2_from": X["days"][dmid], "pre_from": X["days"][dpre], "year_from": X["days"][dyear]},
        "rules_tried": tried, "stage1": len(R), "robust": len(rob),
        "best": slim(best) | {"label": label(best["r"]), "rule_key": best["r"], "double_cost_last200": s2},
        "honest": slim(honest), "raw": slim(raw),
        "top": [slim(x) for x in rob[:25]], "portfolios": port, "from200": port200, "extra": [lev3, dbl, hold],
        "trades": [{k: v for k, v in t.items() if k not in ("t_in", "t_out")} for t in win_rows],
        "today": [{k: v for k, v in t.items() if k not in ("t_in", "t_out")} for t in today_trades],
        "next": next_session(X, best["r"]), "chart": chart, "jev": jev,
        "limits": [
            "The winner was picked on the same last 200 sessions it is scored on. The honest row (picked only on the 200 sessions "
            "before) is the fairer guide to what comes next.",
            "Index candles, not futures fills. A decision on a 15-minute close is filled at the next candle's open; stops and targets "
            "fill at their price (at the open if the market gaps past them). Real fills slip.",
            f"Cost {COST_RT * 100:.3f}% of the position per round trip (STT, exchange, stamp, GST, brokerage and about 1 point of slippage). "
            "The doubled-cost row shows how much of the edge survives worse fills.",
            "₹1 crore buys about 5-6 NIFTY lots without leverage. Intraday margin would allow many more; profits and losses grow by the same factor.",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
    }
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for out in (DOCS / "intraday.json", PUBLIC / "intraday.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    b = port[0]
    print(f"winner: {label(best['r'])}")
    print(f"  last 200: {best['last200']} | halves {best['h1']['net']} / {best['h2']['net']}")
    for sm in port + [lev3, dbl]:
        print(f"  {sm['name']:<52} ₹1 cr -> ₹{sm['end']:>12,} ({sm['return_pct']:+.1f}%) made {sm['made']:>11,} lost {sm['lost']:>12,} "
              f"trades {sm['trades']} win {sm['win_pct']} DD {sm['max_dd_pct']}%")
    print(f"  Nifty held: {hold['return_pct']:+.1f}% | Jev {jev['status']} | intraday.json {len(text) // 1024}KB in {time.time() - t0:.0f}s")
    return payload


if __name__ == "__main__":
    build()
