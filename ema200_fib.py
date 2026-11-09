#!/usr/bin/env python3
"""EMA 200 + double Fibonacci desk for the Nifty 200, and a 200-session test of always-in-trade rules.

Groups     every Nifty 200 stock on its last daily close:
             ABOVE  close more than half a day's range (0.5 x ATR 14) above EMA 200
             ON     close within 0.5 x ATR 14 of EMA 200
             BELOW  close more than 0.5 x ATR 14 below EMA 200
Fib        two Fibonacci grids per stock: the swing of the last 200 sessions (big) and of the last 50 (small),
           levels 0 / 23.6 / 38.2 / 50 / 61.8 / 78.6 / 100%, measured back from the most recent extreme.
           A DOUBLE-FIB zone is where a big-grid level and a small-grid level lie within 0.5% of each other;
           if EMA 200 is inside it too, it is marked +EMA 200. Nearest zone below = support, above = resistance.
Test       the last 200 sessions. Signal on a candle close, order at the next candle's open, always in a trade
           once the first signal comes (BUY or SELL, never flat except long-only books).
             Stocks : Rs 1 crore = Rs 50,000 per stock x 200; shorts only on F&O stocks (others go flat);
                      0.1% cost per buy and per sell.
             Nifty  : 10 lots and 20 lots of 65 on 15-minute, 1-hour and daily candles; 0.035% per side.
           Rules are picked on the first 100 sessions and scored on the last 100 (never seen by the pick).
           Jev then reviews the candidates.
Run: python ema200_fib.py   -> docs/ema200.json + docs/ema200/<SYMBOL>.json
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DOCS, PUBLIC = ROOT / "docs", ROOT / "public" / "data"
DET = DOCS / "ema200"
PRICES = ROOT / "data" / "hhhl_prices"
NIFTY_D = ROOT / "data" / "nifty" / "1d.csv"
NIFTY_15 = ROOT / "data" / "nifty" / "upstox_15m.csv"
IST = ZoneInfo("Asia/Kolkata")

N_EMA, BIG, SMALL = 200, 200, 50
RATIOS = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)
TOL = 0.005                 # double-fib: two levels within 0.5% of price
ON_ATR = 0.5                # "on EMA 200": within half an ATR
TOUCH_ATR = 0.3             # a bounce candle's wick reaches within 0.3 ATR of EMA 200
WINDOW = 200
CAPITAL = 1_00_00_000
COST_STK, COST_FUT = 0.001, 0.00035
LOT, LOTS = 65, (10, 20)

KINDS = {
    "state":      "Always in from day 1: BUY while the close is above EMA 200, SELL while below",
    "cross":      "BUY on the first close above EMA 200, SELL on the first close below",
    "band":       "BUY on the first close more than 0.5 ATR above EMA 200, SELL on the first close more than 0.5 ATR below (ON zone = hold)",
    "two":        "BUY after 2 closes in a row above EMA 200, SELL after 2 closes in a row below",
    "ema_bounce": "BUY when an up-trend candle dips to EMA 200 and closes green above it; SELL on the mirror rejection from below",
    "fib_bounce": "BUY when an up-trend candle (above EMA 200) dips into a double-fib zone and closes green above it; SELL on the mirror",
    "any_bounce": "EMA 200 bounce or double-fib bounce, whichever comes first",
}


# ---------- maths ----------
def ema(c, n=N_EMA):
    """TradingView ta.ema: seeded with the simple average of the first n closes."""
    e = np.full(len(c), np.nan)
    if len(c) < n:
        return e
    e[n - 1] = c[:n].mean()
    a = 2 / (n + 1)
    for i in range(n, len(c)):
        e[i] = a * c[i] + (1 - a) * e[i - 1]
    return e


def atr(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def grid(h, l, i, n):
    """Fibonacci levels of the swing in the n candles ending at candle i (inclusive)."""
    a = max(0, i - n + 1)
    hh, ll = h[a:i + 1], l[a:i + 1]
    ih, il = int(np.argmax(hh)), int(np.argmin(ll))
    H, L = float(hh[ih]), float(ll[il])
    up = ih > il                                         # the high came after the low: an up-swing
    lv = {r: (H - r * (H - L)) if up else (L + r * (H - L)) for r in RATIOS}
    return {"high": H, "low": L, "up": bool(up), "levels": lv}


def double_zones(big, small, price, e200=None):
    """Zones where a big-grid level and a small-grid level lie within TOL of price; merged when they overlap.
    A shared swing high or low (0% / 100% of both grids) is the same price point, not a confluence, and is skipped."""
    raw = []
    for rb, pb in big["levels"].items():
        for rs, ps in small["levels"].items():
            if rb in (0.0, 1.0) and rs in (0.0, 1.0):
                continue
            if abs(pb - ps) <= TOL * price:
                raw.append((min(pb, ps), max(pb, ps), rb, rs))
    raw.sort()
    out = []
    for lo, hi, rb, rs in raw:
        if out and lo - out[-1]["hi"] <= TOL * price:
            z = out[-1]
            z["lo"], z["hi"] = min(z["lo"], lo), max(z["hi"], hi)
            z["pairs"].append([rb, rs])
        else:
            out.append({"lo": lo, "hi": hi, "pairs": [[rb, rs]]})
    for z in out:
        z["price"] = (z["lo"] + z["hi"]) / 2
        z["ema200"] = bool(e200 is not None and z["lo"] - TOL * price <= e200 <= z["hi"] + TOL * price)
    return out


def signals(o, h, l, c, e, a, kind, start):
    """+1 BUY / -1 SELL / 0 nothing new, decided at each candle close from `start` on (data up to that close only)."""
    n = len(c)
    s = np.zeros(n)
    above = c > e
    first = max(start, N_EMA + 2, BIG + 1)
    for i in range(first, n):
        if kind == "state":
            s[i] = 1 if above[i] else -1
        elif kind == "cross":
            if above[i] and not above[i - 1]:
                s[i] = 1
            elif not above[i] and above[i - 1]:
                s[i] = -1
        elif kind == "band":
            if c[i] > e[i] + ON_ATR * a[i] and not c[i - 1] > e[i - 1] + ON_ATR * a[i - 1]:
                s[i] = 1
            elif c[i] < e[i] - ON_ATR * a[i] and not c[i - 1] < e[i - 1] - ON_ATR * a[i - 1]:
                s[i] = -1
        elif kind == "two":
            if above[i] and above[i - 1] and not above[i - 2]:
                s[i] = 1
            elif not above[i] and not above[i - 1] and above[i - 2]:
                s[i] = -1
        else:
            b = 0
            if kind in ("ema_bounce", "any_bounce"):
                if above[i] and above[i - 1] and l[i] <= e[i] + TOUCH_ATR * a[i] and c[i] > o[i]:
                    b = 1
                elif not above[i] and not above[i - 1] and h[i] >= e[i] - TOUCH_ATR * a[i] and c[i] < o[i]:
                    b = -1
            if b == 0 and kind in ("fib_bounce", "any_bounce"):
                zs = double_zones(grid(h, l, i - 1, BIG), grid(h, l, i - 1, SMALL), c[i - 1])
                if above[i] and c[i] > o[i] and any(l[i] <= z["hi"] < c[i] for z in zs):
                    b = 1
                elif not above[i] and c[i] < o[i] and any(c[i] < z["lo"] <= h[i] for z in zs):
                    b = -1
            s[i] = b
    return s


def simulate(o, c, t, sig, start, units_of, cost, allow_short):
    """Flat until the first signal at/after `start`; then always in (unless shorts are not allowed).
    Signal at close j-1 -> fill at open j. Per-candle P&L runs open j -> open j+1 (last candle: to its close)."""
    n = len(c)
    pnl = np.zeros(n)
    pos, units, entry, ent_t, trades = 0, 0, 0.0, None, []
    for j in range(start + 1, n):
        s = sig[j - 1]
        want = pos if s == 0 else (1 if s > 0 else (-1 if allow_short else 0))
        if want != pos:
            px = float(o[j])
            if pos != 0:
                fee = cost * units * px
                pnl[j] -= fee
                trades.append({"side": "BUY" if pos > 0 else "SELL", "in": ent_t, "entry": round(entry, 2), "out": str(t[j])[:16],
                               "exit": round(px, 2), "units": units,
                               "rs": round(pos * units * (px - entry) - cost * units * (entry + px)), "open": False})
            if want != 0:
                units = units_of(px)
                entry, ent_t = px, str(t[j])[:16]
                pnl[j] -= cost * units * px
            pos = want
        nxt = float(o[j + 1]) if j + 1 < n else float(c[j])
        pnl[j] += pos * units * (nxt - float(o[j]))
    if pos != 0:
        px = float(c[-1])
        trades.append({"side": "BUY" if pos > 0 else "SELL", "in": ent_t, "entry": round(entry, 2), "out": None, "exit": round(px, 2),
                       "units": units, "rs": round(pos * units * (px - entry) - cost * units * entry), "open": True})
    return trades, pnl


def book_stats(pnl_by_day, trades, half_day):
    """pnl_by_day: pd.Series indexed by session date (portfolio total). trades: list of trade dicts."""
    eq = pnl_by_day.cumsum()
    dd = float((eq.cummax().clip(lower=0) - eq).max()) if len(eq) else 0.0
    closed = [x for x in trades if not x["open"]]
    rs = np.array([x["rs"] for x in closed], float)
    w, lo = rs[rs > 0].sum(), -rs[rs <= 0].sum()
    return {"total": int(round(pnl_by_day.sum())), "h1": int(round(pnl_by_day[pnl_by_day.index < half_day].sum())),
            "h2": int(round(pnl_by_day[pnl_by_day.index >= half_day].sum())), "trades": len(closed),
            "open": len(trades) - len(closed), "win": round(float((rs > 0).mean()) * 100, 1) if len(rs) else 0.0,
            "pf": round(float(w / lo), 2) if lo else None, "max_dd": int(round(dd)),
            "long_rs": int(sum(x["rs"] for x in trades if x["side"] == "BUY")),
            "short_rs": int(sum(x["rs"] for x in trades if x["side"] == "SELL"))}


# ---------- data ----------
def read_daily(path):
    d = pd.read_csv(path)
    d["Date"] = pd.to_datetime(d["Date"].astype(str).str[:10])
    d = d.set_index("Date")[["Open", "High", "Low", "Close"]].astype(float).dropna()
    return d[~d.index.duplicated(keep="last")].sort_index()


def nifty_frames():
    x = pd.read_csv(NIFTY_15, parse_dates=["t"]).set_index("t").sort_index()
    x = x[~x.index.duplicated(keep="last")][["Open", "High", "Low", "Close"]].astype(float)
    g = x.copy()
    g["d"] = g.index.date
    g["n"] = g.groupby("d").cumcount() // 4
    h1 = g.groupby(["d", "n"]).agg(t=("Open", lambda s: s.index[0]), Open=("Open", "first"), High=("High", "max"),
                                   Low=("Low", "min"), Close=("Close", "last")).set_index("t").sort_index()
    return {"15m": x, "1h": h1, "1D": read_daily(NIFTY_D)}


def universe():
    u = pd.read_csv(ROOT / "nifty200.csv")
    fno = set()
    p = DOCS / "fno_ema105.json"
    if p.exists():
        fno = {r["symbol"] for r in json.loads(p.read_text(encoding="utf-8")).get("rows", [])}
    return [{"symbol": r.Symbol, "name": r["Company Name"], "sector": r.Industry, "fno": r.Symbol in fno} for _, r in u.iterrows()]


# ---------- Jev ----------
def jev_review(stock_rows, nifty_rows, stock_pick, nifty_pick):
    try:
        from jev_client import MODEL, Client
        client = Client()
    except Exception as e:                                  # pragma: no cover - needs the key
        return {"status": f"unavailable: {e}", "model": None}

    def ask(title, rows, pick):
        top = rows[:6]
        crit = {r["label"]: None for r in top}
        if pick["label"] not in crit:
            crit[pick["label"]] = None
        lines = [title, "Each row: rule | first 100 sessions Rs | last 100 sessions Rs | total Rs | closed trades | win % | profit factor | worst fall Rs"]
        for r in rows[:10]:
            s = r["stats"]
            lines.append(f"{r['label']} | {s['h1']} | {s['h2']} | {s['total']} | {s['trades']} | {s['win']} | {s['pf']} | {s['max_dd']}")
        lines.append(f"Picked on the first 100 sessions only: {pick['label']}.")
        Q = {"winner": {"type": "choice", "criteria": crit, "instructions": (
                "Judged only on these numbers, which rule is most likely to keep making money from here? Weigh both halves, "
                "the number of trades, the profit factor and the worst fall, not just the total.")},
             "overfit": {"type": "choice", "criteria": {"low": None, "medium": None, "high": None}, "instructions": (
                "How likely is it that the result of the rule picked on the first 100 sessions is luck from fitting the past?")},
             "real_money": {"type": "choice", "criteria": {"paper only": None, "small size": None, "full size": None},
                            "instructions": "Would a careful risk manager put real money behind the picked rule, judged only on these numbers?"}}
        a = client.ask("\n".join(lines), Q)
        return {k: {"choice": v["choice"], "conf": round(v["confidence"] * 100),
                    "probs": {kk: round(vv * 100) for kk, vv in v["probabilities"].items()}} for k, v in a.items()}

    out = {}
    for name, title, rows, pick in (("stocks", "Nifty 200 stocks, Rs 1 crore (Rs 50,000 per stock), daily candles, last 200 sessions, always in a trade.", stock_rows, stock_pick),
                                    ("nifty", "Nifty 50 futures, 10 lots of 65, last 200 sessions, always in a trade.", nifty_rows, nifty_pick)):
        try:
            out[name] = ask(title, rows, pick)
        except Exception as e:                              # pragma: no cover - network
            out[name] = {"error": f"{type(e).__name__}: {e}"[:160]}
    ok = sum("error" not in v for v in out.values())
    return {"status": f"judged {ok}/2", "model": MODEL, "answers": out}


# ---------- build ----------
def build():
    U = universe()
    data = {}
    for u in U:
        p = PRICES / f"{u['symbol']}.NS.csv"
        if p.exists():
            d = read_daily(p)
            if len(d) >= N_EMA + WINDOW + 5:
                data[u["symbol"]] = d
    sessions = sorted(set().union(*[set(d.index) for d in data.values()]))
    last = sessions[-1]
    win_days = sessions[-WINDOW:]
    day0, half_day = win_days[0], win_days[WINDOW // 2]

    # ---- stocks: 7 rules x (both, long only) ----
    books = {(k, m): {"pnl": [], "trades": []} for k in KINDS for m in ("both", "long")}
    per_stock = {}
    hold = []
    for u in U:
        s = u["symbol"]
        if s not in data:
            continue
        d = data[s]
        if d.index[-1] < last - pd.Timedelta(days=7):
            continue
        o, h, l, c = (d[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
        t = d.index
        e, a = ema(c), atr(h, l, c)
        start = int(np.searchsorted(t, day0))
        slot = CAPITAL / len(data)
        units_of = lambda px, slot=slot: max(1, int(slot // px))
        per_stock[s] = {"trades": {}, "o": o, "h": h, "l": l, "c": c, "e": e, "a": a, "t": t}
        q = units_of(float(o[start]))
        hold.append(pd.Series(np.r_[np.diff(c[start:]) * q, 0.0][:len(t) - start], index=t[start:]).shift(1).fillna((c[start] - o[start]) * q))
        for k in KINDS:
            sig = signals(o, h, l, c, e, a, k, start)
            for m in ("both", "long"):
                tr, pnl = simulate(o, c, t, sig, start, units_of, COST_STK, allow_short=(m == "both" and u["fno"]))
                books[(k, m)]["pnl"].append(pd.Series(pnl[start:], index=t[start:]))
                for x in tr:
                    x["symbol"] = s
                books[(k, m)]["trades"] += tr
                if m == "both":
                    per_stock[s]["trades"][k] = tr
    stock_rows = []
    for (k, m), b in books.items():
        daily = pd.concat(b["pnl"], axis=1).fillna(0).sum(axis=1)
        st = book_stats(daily, b["trades"], half_day)
        by_stock = pd.Series({x: 0 for x in per_stock}, dtype=float)
        for x in b["trades"]:
            by_stock[x["symbol"]] += x["rs"]
        st["stocks_up"] = int((by_stock > 0).sum())
        st["return_pct"] = round(st["total"] / CAPITAL * 100, 2)
        stock_rows.append({"kind": k, "mode": m, "label": f"{k} · {'BUY + SELL' if m == 'both' else 'BUY only'}", "rule": KINDS[k], "stats": st,
                           "curve": [[str(i.date()), int(v)] for i, v in daily.cumsum().items()]})
    hold_daily = pd.concat(hold, axis=1).fillna(0).sum(axis=1)
    hold_stats = {"total": int(hold_daily.sum()), "h1": int(hold_daily[hold_daily.index < half_day].sum()),
                  "h2": int(hold_daily[hold_daily.index >= half_day].sum()),
                  "max_dd": int((hold_daily.cumsum().cummax().clip(lower=0) - hold_daily.cumsum()).max())}
    stock_rows.sort(key=lambda r: -r["stats"]["h1"])
    stock_pick = stock_rows[0]

    # ---- Nifty: 3 timeframes x 7 rules x (both, long only), 10 and 20 lots ----
    NF = nifty_frames()
    nifty_rows, nifty_detail = [], {}
    for tf, df in NF.items():
        df = df[df.index.normalize() <= last]
        days = sorted(set(df.index.normalize()))
        if len(days) < WINDOW:
            continue
        d0, dh = days[-WINDOW], days[-WINDOW // 2]
        o, h, l, c = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
        t = df.index
        e, a = ema(c), atr(h, l, c)
        start = int(np.searchsorted(t, d0))
        hold_pts = float(c[-1] - o[start])
        for k in KINDS:
            sig = signals(o, h, l, c, e, a, k, start)
            for m in ("both", "long"):
                tr, pnl = simulate(o, c, t, sig, start, lambda px: LOTS[0] * LOT, COST_FUT, allow_short=(m == "both"))
                daily = pd.Series(pnl[start:], index=t[start:].normalize()).groupby(level=0).sum()
                st = book_stats(daily, tr, dh)
                st["points"] = round(st["total"] / (LOTS[0] * LOT), 1)
                st["lots20"] = {x: st[x] * 2 for x in ("total", "h1", "h2", "max_dd", "long_rs", "short_rs")}
                nifty_rows.append({"tf": tf, "kind": k, "mode": m, "label": f"{tf} · {k} · {'BUY + SELL' if m == 'both' else 'BUY only'}",
                                   "rule": KINDS[k], "stats": st, "hold_pts": round(hold_pts, 1),
                                   "curve": [[str(i.date()), int(v)] for i, v in daily.cumsum().items()]})
                nifty_detail[(tf, k, m)] = tr
    nifty_rows.sort(key=lambda r: -r["stats"]["h1"])
    nifty_pick = nifty_rows[0]

    jev = jev_review(stock_rows, nifty_rows, stock_pick, nifty_pick)

    # ---- the screen: three groups + double-fib zones (data up to the last close) ----
    best_kind = stock_pick["kind"]
    DET.mkdir(parents=True, exist_ok=True)
    rows = []
    for u in U:
        s = u["symbol"]
        if s not in per_stock:
            continue
        P = per_stock[s]
        o, h, l, c, e, a, t = P["o"], P["h"], P["l"], P["c"], P["e"], P["a"], P["t"]
        i = len(c) - 1
        dist = c[i] - e[i]
        zone = "ON" if abs(dist) <= ON_ATR * a[i] else ("ABOVE" if dist > 0 else "BELOW")
        above = c > e
        flips = np.flatnonzero(above[1:] != above[:-1]) + 1
        flips = flips[flips >= N_EMA]
        since = str(t[flips[-1]].date()) if len(flips) else None
        big, small = grid(h, l, i, BIG), grid(h, l, i, SMALL)
        zs = double_zones(big, small, c[i], e[i])
        sup = max((z for z in zs if z["hi"] < c[i]), key=lambda z: z["hi"], default=None)
        res = min((z for z in zs if z["lo"] > c[i]), key=lambda z: z["lo"], default=None)
        tr = P["trades"][best_kind]
        op = next((x for x in tr if x["open"]), None)
        rnd = lambda z: None if z is None else {"price": round(z["price"], 2), "lo": round(z["lo"], 2), "hi": round(z["hi"], 2),
                                                 "pairs": z["pairs"], "ema200": z["ema200"], "pct": round((z["price"] / c[i] - 1) * 100, 2)}
        rows.append({"symbol": s, "name": u["name"], "sector": u["sector"], "fno": u["fno"], "close": round(float(c[i]), 2),
                     "ema200": round(float(e[i]), 2), "dist_pct": round(float(dist / e[i] * 100), 2), "dist_atr": round(float(dist / a[i]), 2),
                     "zone": zone, "since": since, "support": rnd(sup), "resistance": rnd(res), "zones": len(zs),
                     "ema_zone": any(z["ema200"] for z in zs),
                     "position": (op["side"] if op else "FLAT"), "pos_since": op["in"][:10] if op else None,
                     "pos_rs": op["rs"] if op else 0,
                     "book_rs": int(sum(x["rs"] for x in tr))})
        k0 = max(0, len(c) - 260)
        det = {"symbol": s, "name": u["name"], "fno": u["fno"],
               "bars": [[str(t[j].date()), round(float(o[j]), 2), round(float(h[j]), 2), round(float(l[j]), 2), round(float(c[j]), 2)] for j in range(k0, len(c))],
               "ema200": [round(float(x), 2) if x == x else None for x in e[k0:]],
               "big": {"high": round(big["high"], 2), "low": round(big["low"], 2), "up": big["up"], "levels": {str(r): round(v, 2) for r, v in big["levels"].items()}},
               "small": {"high": round(small["high"], 2), "low": round(small["low"], 2), "up": small["up"], "levels": {str(r): round(v, 2) for r, v in small["levels"].items()}},
               "zones": [rnd(z) for z in zs],
               "trades": {k: [[x["side"], x["in"][:10], x["entry"], x["out"][:10] if x["out"] else None, x["exit"], x["rs"], x["open"]] for x in v]
                          for k, v in P["trades"].items()}}
        (DET / f"{s}.json").write_text(json.dumps(det, separators=(",", ":")), encoding="utf-8")

    # Nifty daily chart + its zones
    nd = NF["1D"][NF["1D"].index <= last]
    o, h, l, c = (nd[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    e, a = ema(c), atr(h, l, c)
    i = len(c) - 1
    big, small = grid(h, l, i, BIG), grid(h, l, i, SMALL)
    nzs = double_zones(big, small, c[i], e[i])
    k0 = max(0, len(c) - 260)
    best_n = (nifty_pick["tf"], nifty_pick["kind"], nifty_pick["mode"])
    (DET / "NIFTY.json").write_text(json.dumps({
        "symbol": "NIFTY", "name": "Nifty 50", "fno": True,
        "bars": [[str(nd.index[j].date()), round(float(o[j]), 2), round(float(h[j]), 2), round(float(l[j]), 2), round(float(c[j]), 2)] for j in range(k0, len(c))],
        "ema200": [round(float(x), 2) if x == x else None for x in e[k0:]],
        "big": {"high": round(big["high"], 2), "low": round(big["low"], 2), "up": big["up"], "levels": {str(r): round(v, 2) for r, v in big["levels"].items()}},
        "small": {"high": round(small["high"], 2), "low": round(small["low"], 2), "up": small["up"], "levels": {str(r): round(v, 2) for r, v in small["levels"].items()}},
        "zones": [{"price": round(z["price"], 2), "lo": round(z["lo"], 2), "hi": round(z["hi"], 2), "pairs": z["pairs"], "ema200": z["ema200"],
                   "pct": round((z["price"] / c[i] - 1) * 100, 2)} for z in nzs],
        "trades": {k: [[x["side"], x["in"][:10], x["entry"], x["out"][:10] if x["out"] else None, x["exit"], x["rs"], x["open"]]
                       for x in nifty_detail[("1D", k, "both")]] for k in KINDS},
    }, separators=(",", ":")), encoding="utf-8")
    nifty_now = {"close": round(float(c[i]), 2), "ema200": round(float(e[i]), 2), "dist_pct": round(float((c[i] / e[i] - 1) * 100), 2),
                 "zone": "ON" if abs(c[i] - e[i]) <= ON_ATR * a[i] else ("ABOVE" if c[i] > e[i] else "BELOW"),
                 "pick_trades": [{k: v for k, v in x.items()} for x in nifty_detail[best_n]][-30:]}

    counts = {z: sum(r["zone"] == z for r in rows) for z in ("ABOVE", "ON", "BELOW")}
    payload = {
        "version": 1, "name": "EMA 200 + double Fibonacci · Nifty 200", "generated_at": datetime.now(IST).isoformat(timespec="minutes"),
        "as_of": str(last.date()), "window": {"from": str(day0.date()), "half": str(half_day.date()), "to": str(last.date()), "sessions": WINDOW},
        "counts": counts, "rows": rows, "kinds": KINDS,
        "stocks": {"capital": CAPITAL, "slot": int(CAPITAL / len(per_stock)), "cost_pct": COST_STK * 100, "stocks": len(per_stock),
                   "fno": sum(r["fno"] for r in rows), "rows": stock_rows, "pick": stock_pick["label"], "hold": hold_stats},
        "nifty": {"lot": LOT, "lots": list(LOTS), "cost_pct": COST_FUT * 100, "rows": nifty_rows, "pick": nifty_pick["label"], "now": nifty_now},
        "jev": jev,
        "method": [
            f"EMA 200 of daily closes (TradingView's ta.ema). ABOVE / ON / BELOW: the close is more than / within / below {ON_ATR} x ATR(14) of EMA 200.",
            f"Two Fibonacci grids: the swing of the last {BIG} sessions and of the last {SMALL}. Levels {', '.join(f'{r * 100:g}%' for r in RATIOS)}, measured back from the more recent extreme.",
            f"Double fib: a big-grid level and a small-grid level within {TOL * 100:g}% of price. Support = nearest zone below the close, resistance = nearest above. '+EMA 200' = EMA 200 sits in the zone too.",
            f"Test: the last {WINDOW} sessions ({day0.date()} to {last.date()}). Signal on a close, order at the next open, always in a trade after the first signal.",
            f"Stocks: Rs 1 crore spread as Rs {int(CAPITAL / len(per_stock)):,} per stock; whole shares; {COST_STK * 100:g}% per buy and per sell; SELL (short) only on F&O stocks, others go flat.",
            f"Nifty: {LOTS[0]} and {LOTS[1]} lots of {LOT}; {COST_FUT * 100:g}% per side; 15-minute, 1-hour and daily candles; positions held overnight.",
            f"Pick: the rule with the most rupees in the first {WINDOW // 2} sessions; its last {WINDOW // 2} sessions are the honest result. Jev then reviews all candidates.",
        ],
        "limits": [
            "200 sessions is less than a year: one market phase. A rule that wins here can lose in the next phase.",
            "Daily prices are Yahoo Finance adjusted closes; fills are at the open with no slippage beyond the cost charged.",
            "Stock shorts need F&O futures (lot sizes are far bigger than Rs 50,000); the short side here is a paper scale model.",
            "20 Nifty lots is about Rs 3.3 crore of exposure: 3x leverage on Rs 1 crore. The worst fall shown is per this window only.",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
    }
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for out in (DOCS / "ema200.json", PUBLIC / "ema200.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    sp, nfp = stock_pick["stats"], nifty_pick["stats"]
    print(f"ema200.json {day0.date()} -> {last.date()} | {len(rows)} stocks {counts} | stocks pick {stock_pick['label']}: "
          f"h1 Rs {sp['h1']:,} h2 Rs {sp['h2']:,} | nifty pick {nifty_pick['label']}: h1 Rs {nfp['h1']:,} h2 Rs {nfp['h2']:,} (10 lots) | "
          f"Jev {jev.get('status')} | {len(text) // 1024}KB")
    return payload


if __name__ == "__main__":
    build()
