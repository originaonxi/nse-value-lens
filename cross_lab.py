#!/usr/bin/env python3
"""Nifty 50 EMA cross lab · intraday · 5 / 15 / 30-minute candles · ₹1 crore · Jev picks the best.

Question: is there an intraday "golden cross" - a fast EMA crossing a slow EMA - that, traded non-stop from 09:15 to
15:00 (BUY above the cross, SELL below it), makes the most money? And does a cross "always give at least 50 points"?

Rules tested (all intraday, flat by 15:00 or 15:15, never overnight):
  EMA fast x EMA slow, any pair from 3, 5, 8, 9, 10, 12, 13, 14, 20, 21
  entry   plain cross (fast above slow = long, below = short), or cross + a candle closing beyond both EMAs
  side    buy and sell (always in), buy only, sell only
  exits   the opposite cross, the 15:00 / 15:15 close-out, and (stage 2) a stop / target in Nifty points (30, 50, 100)
Decision on a candle's close, filled at the next candle's open, 0.035% cost per round trip.

Scored on the last 200 sessions (and each 100-session half), the 200 sessions before (for an honest pick), and
₹1 crore of whole NIFTY lots one year back and 200 sessions back, at 1x to 10x with a 10% capital stop per trade.
Jev is shown the finalists and picks the one most likely to keep making money.

Run: python cross_lab.py   -> docs/cross.json
"""
import itertools
import json
import math
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import intraday15 as I  # noqa: E402

DOCS, PUBLIC = ROOT / "docs", ROOT / "public" / "data"
CACHE5 = ROOT / "data" / "nifty" / "upstox_5m.csv"
YAHOO5 = ROOT / "data" / "nifty" / "5m.csv"
TFS = [5, 15, 30]
EMAS = [3, 5, 8, 9, 10, 12, 13, 14, 20, 21]
PAIRS = list(itertools.combinations(EMAS, 2))
MODES = ["cross", "cross + close"]
SIDES = ["both", "buy", "sell"]
FLATS = ["15:00", "15:15"]
EXITS = [(30, None), (50, None), (100, None), (None, 50), (None, 100), (50, 50), (30, 50), (50, 100), (100, 100)]
COST = I.COST_RT
CAPITAL = 1_00_00_000
LAST, MIN_TRADES, STAGE2 = 200, 80, 25
LEVS = [1, 2, 3, 4, 5, 6, 8, 10]
STOP_FRAC = 0.10
USER_PAIRS = [(9, 14), (9, 10), (5, 9)]


# ── data ──────────────────────────────────────────────────────────────────────

def fetch(unit, cache, today=None):
    today = today or datetime.now(I.IST).date()
    key = urllib.parse.quote(I.KEY, safe="")
    have = pd.read_csv(cache, index_col=0, parse_dates=True) if cache.exists() else pd.DataFrame()
    start = have.index.max().date().replace(day=1) if len(have) else I.FIRST_MONTH
    parts, m = [have], start
    while m <= today:
        nxt = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
        to = min(nxt - timedelta(days=1), today)
        parts.append(I._frame(I._get(f"https://api.upstox.com/v3/historical-candle/{key}/minutes/{unit}/{to}/{m}")))
        m = nxt
        time.sleep(0.3)
    parts.append(I._frame(I._get(f"https://api.upstox.com/v3/historical-candle/intraday/{key}/minutes/{unit}")))
    df = pd.concat([p for p in parts if len(p)])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    mins = df.index.hour * 60 + df.index.minute
    df = df[(mins >= 555) & (mins <= 930 - unit)]
    now = datetime.now(I.IST).replace(tzinfo=None)
    df = df[df.index + pd.Timedelta(minutes=unit) <= now]                # finished candles only
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.round(2).to_csv(cache)
    return df


def to30(df15):
    m = (df15.index.hour * 60 + df15.index.minute - 555) // 30
    key = df15.index.normalize() + pd.to_timedelta(555 + m * 30, unit="min")
    g = df15.groupby(key)
    return pd.DataFrame({"Open": g.Open.first(), "High": g.High.max(), "Low": g.Low.min(), "Close": g.Close.last()})


def check(df, unit):
    g = df.groupby(df.index.date)
    day = pd.DataFrame({"open": g.Open.first(), "high": g.High.max(), "low": g.Low.min(), "bars": g.size()})
    day.index = day.index.astype(str)
    out = {"tf": unit, "sessions": int(len(day)), "from": day.index[0], "to": day.index[-1],
           "short_days": int((day.bars < math.ceil(375 / unit)).sum())}
    if I.OFFICIAL.exists():
        off = pd.read_csv(I.OFFICIAL, index_col=0)
        off.index = off.index.astype(str)
        j = day.join(off[["ind_open", "ind_high", "ind_low"]], how="inner").dropna()
        gap = np.abs(j[["open", "high", "low"]].to_numpy() - j[["ind_open", "ind_high", "ind_low"]].to_numpy())
        out["vs_nse"] = {"days": int(len(j)), "median_pts": round(float(np.median(gap)), 2), "p95_pts": round(float(np.quantile(gap, .95)), 2),
                         "days_within_1pt": int((gap.max(axis=1) <= 1).sum())}
    if unit == 5 and YAHOO5.exists():
        y = pd.read_csv(YAHOO5, index_col=0)
        y.index = pd.to_datetime(y.index, utc=True).tz_convert(I.IST).tz_localize(None)
        j = df.join(y[["Close"]].rename(columns={"Close": "yc"}), how="inner").dropna()
        if len(j):
            d = (j.Close - j.yc).abs()
            out["vs_yahoo"] = {"bars": int(len(j)), "median_pts": round(float(d.median()), 2), "p95_pts": round(float(d.quantile(.95)), 2)}
    return out


# ── features and rules ────────────────────────────────────────────────────────

def features(df, unit):
    O, H, L, C = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    dstr = np.array([str(t.date()) for t in df.index])
    days, did = np.unique(dstr, return_inverse=True)
    n = len(C)
    newday = np.r_[True, did[1:] != did[:-1]]
    lastbar = np.r_[did[1:] != did[:-1], True]
    hhmm = np.asarray(df.index.hour * 100 + df.index.minute)
    full = np.bincount(did)[did] >= int(0.8 * math.ceil(375 / unit))
    return {"O": O, "H": H, "L": L, "C": C, "did": did, "days": days, "newday": newday, "lastbar": lastbar,
            "hhmm": hhmm, "full": full, "n": n, "time": df.index, "unit": unit, "ema": {k: I.ema(C, k) for k in EMAS}}


def state(X, a, b, mode):
    """+1 / -1 / 0 at each candle's close. Plain cross = which side the fast EMA is on. Cross + close also needs a candle
    closing beyond both EMAs (after that cross, the same day) before it takes that side; then it holds until the next cross."""
    f, s = X["ema"][a], X["ema"][b]
    sg = np.sign(f - s)
    if mode == "cross":
        return sg
    C = X["C"]
    conf = ((sg > 0) & (C > np.maximum(f, s))) | ((sg < 0) & (C < np.minimum(f, s)))
    seg = np.cumsum(np.r_[True, (sg[1:] != sg[:-1]) | X["newday"][1:]])
    on = pd.Series(conf).groupby(seg).cummax().to_numpy()
    return np.where(on, sg, 0.0)


def desired(X, st, side, flat):
    s = st if side == "both" else (np.maximum(st, 0) if side == "buy" else np.minimum(st, 0))
    d = np.r_[0.0, s[:-1]]                                               # decided at close k-1, held during k
    ok = (~X["newday"]) & (~X["lastbar"]) & X["full"] & (X["hhmm"] < I.hm(flat))
    return np.where(ok, d, 0.0)


def simulate(X, p, sl, tp):
    """Stop / target in Nifty points. After either, that side waits for the next cross (the wanted side must change)."""
    if sl is None and tp is None:
        return I.trades_vec(X, p)
    p = p.tolist()
    O, H, L, newday = X["O"].tolist(), X["H"].tolist(), X["L"].tolist(), X["newday"].tolist()
    S, E, SD, G, EP = [], [], [], [], []
    pos, ep, ei, blocked, stop, tgt = 0, 0.0, 0, 0, None, None
    for k in range(X["n"]):
        if newday[k]:
            blocked = 0
        want = p[k]
        if blocked and want != blocked:
            blocked = 0
        if blocked:
            want = 0
        if pos and want != pos:
            S.append(ei); E.append(k); SD.append(pos); G.append(pos * (O[k] - ep)); EP.append(ep)
            pos = 0
        if not pos and want:
            pos, ep, ei = want, O[k], k
            stop = ep - pos * sl if sl else None
            tgt = ep + pos * tp if tp else None
        if pos:
            px, gap = None, k != ei
            if stop is not None and ((pos > 0 and L[k] <= stop) or (pos < 0 and H[k] >= stop)):
                px = (min(O[k], stop) if pos > 0 else max(O[k], stop)) if gap else stop       # stop first: the worse case
            elif tgt is not None and ((pos > 0 and H[k] >= tgt) or (pos < 0 and L[k] <= tgt)):
                px = (max(O[k], tgt) if pos > 0 else min(O[k], tgt)) if gap else tgt
            if px is not None:
                S.append(ei); E.append(k); SD.append(pos); G.append(pos * (px - ep)); EP.append(ep)
                blocked, pos = pos, 0
    a = lambda v, t=float: np.asarray(v, dtype=t)
    return a(S, int), a(E, int), a(SD), a(G), a(EP)


def label(r):
    side = {"both": "BUY above, SELL (short) below, always in", "buy": "BUY above only", "sell": "SELL (short) below only"}[r["side"]]
    ex = [f"flat by {r['flat']}"]
    if r["sl"]:
        ex.append(f"stop {r['sl']} pts")
    if r["tp"]:
        ex.append(f"target {r['tp']} pts")
    return (f"{r['tf']}-min · EMA {r['a']} × EMA {r['b']} " + ("cross" if r["mode"] == "cross" else "cross + close beyond both")
            + f" · {side} · " + " · ".join(ex))


def run(X, r):
    return simulate(X, desired(X, state(X, r["a"], r["b"], r["mode"]), r["side"], r["flat"]), r["sl"], r["tp"])


# ── does a cross give 50 points? ──────────────────────────────────────────────

def out_bars(X, flat):
    """Per day: the first candle at or after the close-out time (the day's last candle if none)."""
    cache = X.setdefault("_ob", {})
    if flat not in cache:
        ok = np.flatnonzero((X["hhmm"] >= I.hm(flat)) | X["lastbar"])
        first = {}
        for k in ok:
            first.setdefault(int(X["did"][k]), int(k))
        cache[flat] = first
    return cache[flat]


def cross_moves(X, a, b, d0, flat="15:00", pts=50):
    """Every cross after day d0: from the next open until the opposite cross or the close-out, how far it went each way."""
    sg = np.sign(X["ema"][a] - X["ema"][b])
    O, H, L, did, hh, n = X["O"], X["H"], X["L"], X["did"], X["hhmm"], X["n"]
    ks = np.flatnonzero((sg[1:] != sg[:-1]) & (sg[1:] != 0)) + 1
    fl, ob = I.hm(flat), out_bars(X, flat)
    res = []
    for i, k in enumerate(ks):
        if did[k] < d0 or k + 1 >= n or did[k + 1] != did[k] or hh[k + 1] >= fl:
            continue
        d, j, e = sg[k], k + 1, O[k + 1]
        nxt = ks[i + 1] + 1 if i + 1 < len(ks) else n
        end = min(nxt, ob[int(did[k])])
        if end <= j or end >= n:
            continue
        hi, lo = H[j:end], L[j:end]
        fav = (hi - e) if d > 0 else (e - lo)
        adv = (e - lo) if d > 0 else (hi - e)
        up = fav >= pts
        dn = adv >= pts
        fu = int(np.argmax(up)) if up.any() else None
        fd = int(np.argmax(dn)) if dn.any() else None
        res.append((float(fav.max()), float(adv.max()), fu is not None, fu is not None and (fd is None or fu < fd),
                    float(d * (O[end] - e))))
    if not res:
        return {"n": 0}
    f = np.array(res)
    return {"n": int(len(f)), "reach": round(float(f[:, 2].mean() * 100), 1), "first": round(float(f[:, 3].mean() * 100), 1),
            "mfe_median": round(float(np.median(f[:, 0])), 1), "mae_median": round(float(np.median(f[:, 1])), 1),
            "result_median": round(float(np.median(f[:, 4])), 1), "result_avg": round(float(f[:, 4].mean()), 1)}


# ── money ─────────────────────────────────────────────────────────────────────

def cap_stop(X, tr, lev, frac=STOP_FRAC):
    """Close a trade once it has lost `frac` of the money behind it (at `lev`x that is frac/lev of the price)."""
    s, e, side, g, ep = tr
    g = g.copy()
    H, L = X["H"], X["L"]
    lim = frac * ep / lev
    hits = 0
    for i in range(len(s)):
        if e[i] <= s[i]:
            continue
        adv = (ep[i] - L[s[i]:e[i]].min()) if side[i] > 0 else (H[s[i]:e[i]].max() - ep[i])
        if adv >= lim[i] and g[i] > -lim[i]:
            g[i] = -lim[i]
            hits += 1
    return (s, e, side, g, ep), hits


def money(X, tr, d0, lots, lev=1, cost=COST, name=""):
    tr2, hits = cap_stop(X, tr, lev)
    rows, sm = I.money(X, tr2, d0, lots, capital=CAPITAL, lev=lev, name=name, cost=cost)
    sm["stops_hit"] = hits
    sm["lev"] = lev
    return rows, sm


# ── Jev ───────────────────────────────────────────────────────────────────────

def jev_pick(cands, fifty):
    try:
        from jev_client import Client, MODEL
        client = Client()
    except Exception as e:  # pragma: no cover - needs the key
        return {"status": f"unavailable: {e}", "model": None}
    letters = [c["id"] for c in cands]
    Q = {
        "best": {"type": "choice", "criteria": {k: None for k in letters}, "instructions": (
            "These are Nifty 50 intraday EMA-cross strategies (futures, flat every day). Which ONE is most likely to keep making "
            "money from here? Judge it on robustness - both 100-session halves, the 200 sessions before (an honest test the "
            "rules never saw when chosen), the result with doubled costs, number of trades and the worst fall - not only "
            "on the biggest profit.")},
        "double": {"type": "choice", "criteria": {"no": None, "unlikely": None, "possible": None}, "instructions": (
            "From these results (money at 1x to 10x with a 10% capital stop per trade, and the leverage each would need), "
            "can any of them turn ₹1 crore into ₹2 crore in one year with acceptable risk?")},
        "fifty": {"type": "choice", "criteria": {"yes": None, "no": None}, "instructions": (
            "A trader believes an EMA cross on Nifty 50 intraday always gives at least 50 points. Using the measured cross table "
            "(share of crosses that ever reached +50 points, and that reached +50 before -50), is that true?")},
    }
    for k in letters:
        Q["luck_" + k] = {"type": "choice", "criteria": {"low": None, "medium": None, "high": None}, "instructions": (
            f"For strategy {k} only: how likely is it that its profit is luck from picking the best of thousands of rules?")}
    state = {"strategies": cands, "cross_table": fifty}
    try:
        a = client.ask(state, Q)
    except Exception as e:  # pragma: no cover - network
        return {"status": f"error: {type(e).__name__}: {str(e)[:80]}", "model": MODEL}
    out = {k: {"choice": v["choice"], "conf": round(v["confidence"] * 100),
               "probs": {kk: round(vv * 100) for kk, vv in v["probabilities"].items()}} for k, v in a.items()}
    return {"status": "judged", "model": MODEL, "answers": out, "tokens": [client.input_tokens, client.output_tokens]}


# ── next cross ────────────────────────────────────────────────────────────────

def cross_price(ef, es, a, b):
    """The next close at which EMA a and EMA b become equal (both update with that close)."""
    fa, fb = 2 / (a + 1), 2 / (b + 1)
    return (es * (1 - fb) - ef * (1 - fa)) / (fa - fb)


def next_signal(X, r):
    i = X["n"] - 1
    ef, es = float(X["ema"][r["a"]][i]), float(X["ema"][r["b"]][i])
    p = cross_price(ef, es, r["a"], r["b"])
    above = ef > es
    lines = [f"Now EMA {r['a']} {ef:,.2f} is {'above' if above else 'below'} EMA {r['b']} {es:,.2f} "
             f"({'buy side' if above else 'sell side'}), Nifty {X['C'][i]:,.2f} at the last {r['tf']}-min close"]
    flip = "SELL (short)" if above else "BUY"
    if (above and r["side"] in ("both", "sell")) or (not above and r["side"] in ("both", "buy")):
        lines.append(f"{flip} signal if a {r['tf']}-min candle closes {'below' if above else 'above'} {p:,.2f} "
                     f"(the EMAs cross there; {p - X['C'][i]:+,.0f} pts from the last close; it moves with every candle)")
    if r["mode"] != "cross":
        lines.append("Then it waits for a candle to close beyond both EMAs before entering")
    if r["side"] == "both":
        lines.append(f"Next session it starts on the {'buy' if above else 'sell'} side from the first {r['tf']}-min close unless the EMAs cross first")
    elif r["side"] == "buy":
        lines.append("This rule only buys; below the cross it stays out")
    else:
        lines.append("This rule only shorts; above the cross it stays out")
    if r["sl"]:
        lines.append(f"Stop {r['sl']} points from the entry")
    if r["tp"]:
        lines.append(f"Target {r['tp']} points, then wait for the next cross")
    lines.append(f"Everything closed at the {r['flat']} candle's open")
    return {"ema_fast": round(ef, 2), "ema_slow": round(es, 2), "cross_price": round(p, 2), "side_now": "buy" if above else "sell",
            "close": round(float(X["C"][i]), 2), "lines": lines}


# ── build ─────────────────────────────────────────────────────────────────────

def build():
    t0 = time.time()
    df15 = I.fetch()
    df5 = fetch(5, CACHE5)
    frames = {5: df5, 15: df15, 30: to30(df15)}
    checks = [check(frames[u], u) for u in TFS]
    XS = {u: features(frames[u], u) for u in TFS}
    full15 = XS[15]["days"][np.bincount(XS[15]["did"]) >= 20]
    D = {"last200": full15[-LAST], "mid": full15[-LAST // 2], "pre": full15[-2 * LAST],
         "year": (date.fromisoformat(full15[-1]) - timedelta(days=365)).isoformat(), "end": full15[-1]}
    di = {u: {k: int(np.searchsorted(XS[u]["days"], v)) for k, v in D.items() if k != "end"} for u in TFS}
    print(f"windows {D} | 5m {checks[0]['from']}..{checks[0]['to']} ({checks[0]['sessions']} sessions) | {time.time() - t0:.0f}s", flush=True)

    def score(X, u, tr, cost=COST):
        w = di[u]
        return {"last200": I.stats(X, tr, w["last200"], cost=cost), "h1": I.stats(X, tr, w["last200"], w["mid"], cost=cost),
                "h2": I.stats(X, tr, w["mid"], cost=cost), "pre": I.stats(X, tr, w["pre"], w["last200"], cost=cost)}

    rows = []
    for u in TFS:
        X = XS[u]
        for (a, b), mode in itertools.product(PAIRS, MODES):
            st = state(X, a, b, mode)
            for side, flat in itertools.product(SIDES, FLATS):
                r = {"tf": u, "a": a, "b": b, "mode": mode, "side": side, "flat": flat, "sl": None, "tp": None}
                rows.append({"r": r, **score(X, u, I.trades_vec(X, desired(X, st, side, flat)))})
    s1 = len(rows)
    print(f"stage 1: {s1} rules in {time.time() - t0:.0f}s", flush=True)

    robust = lambda x: x["last200"]["n"] >= MIN_TRADES and x["h1"]["net"] > 0 and x["h2"]["net"] > 0
    seen = {json.dumps(x["r"]) for x in rows}
    for u in TFS:
        mine = [x for x in rows if x["r"]["tf"] == u]
        base = sorted([x for x in mine if robust(x)], key=lambda x: -x["last200"]["net"])[:STAGE2]
        base += sorted([x for x in mine if x["pre"]["n"] >= MIN_TRADES], key=lambda x: -x["pre"]["net"])[:STAGE2]
        base += [x for x in mine if x["r"]["mode"] == "cross" and x["r"]["side"] == "both" and x["r"]["flat"] == "15:00"
                 and (x["r"]["a"], x["r"]["b"]) in USER_PAIRS]
        for x in base:
            for sl, tp in EXITS:
                r = dict(x["r"], sl=sl, tp=tp)
                k = json.dumps(r)
                if k in seen:
                    continue
                seen.add(k)
                rows.append({"r": r, **score(XS[u], u, run(XS[u], r))})
    tried = len(rows)
    print(f"stage 2: {tried} rules in {time.time() - t0:.0f}s", flush=True)

    rob = sorted([x for x in rows if robust(x)], key=lambda x: -x["last200"]["net"])
    by_tf = {u: next((x for x in rob if x["r"]["tf"] == u), None) for u in TFS}
    honest = max([x for x in rows if x["pre"]["n"] >= MIN_TRADES], key=lambda x: x["pre"]["net"])
    plain = {}
    for u in TFS:
        for a, b in USER_PAIRS:
            plain[(u, a, b)] = next(x for x in rows if x["r"] == {"tf": u, "a": a, "b": b, "mode": "cross", "side": "both",
                                                                    "flat": "15:00", "sl": None, "tp": None})
    user50 = {}
    for u in TFS:
        for a, b in USER_PAIRS:
            k = {"tf": u, "a": a, "b": b, "mode": "cross", "side": "both", "flat": "15:00", "sl": 50, "tp": 50}
            user50[(u, a, b)] = next((x for x in rows if x["r"] == k), None)

    # does a cross give 50 points? every pair on every timeframe, last 200 sessions
    fifty = []
    for u in TFS:
        for a, b in PAIRS:
            m = cross_moves(XS[u], a, b, di[u]["last200"])
            if m["n"]:
                fifty.append({"tf": u, "a": a, "b": b, **m})
    fifty.sort(key=lambda f: -f["first"])
    print(f"50-point table: {len(fifty)} pairs in {time.time() - t0:.0f}s", flush=True)

    # finalists, money, Jev
    lots = I.lot_sizes(list(XS[5]["days"]))
    fin, ids = [], iter("ABCDEFGH")
    named = [(f"Best on {u}-min", by_tf[u]) for u in TFS if by_tf[u]]
    named += [("Honest pick (chosen on the 200 sessions before)", honest),
              ("Your cross: 15-min EMA 9 × 14, buy above / sell below", plain[(15, 9, 14)])]
    for nm, x in named:
        if any(json.dumps(f["x"]["r"]) == json.dumps(x["r"]) for f in fin):
            continue
        fin.append({"id": next(ids), "name": nm, "x": x})
    for f in fin:
        r = f["x"]["r"]
        u, X = r["tf"], XS[r["tf"]]
        tr = run(X, r)
        f["rows"], f["year"] = money(X, tr, di[u]["year"], lots, name=f["name"])
        _, f["s200"] = money(X, tr, di[u]["last200"], lots, name=f["name"])
        f["ladder"] = []
        for lev in LEVS:
            _, sm = money(X, tr, di[u]["year"], lots, lev=lev)
            f["ladder"].append({"lev": lev, "end": sm["end"], "return_pct": sm["return_pct"], "max_dd_pct": sm["max_dd_pct"],
                                "stops_hit": sm["stops_hit"], "worst_day": sm["worst_day"]})
        _, f["dbl"] = money(X, tr, di[u]["year"], lots, cost=2 * COST)
        f["dbl_pts"] = I.stats(X, tr, di[u]["last200"], cost=2 * COST)
        f["lev_for_2cr"] = next((l["lev"] for l in f["ladder"] if l["end"] >= 2 * CAPITAL), None)
        f["cross"] = cross_moves(X, r["a"], r["b"], di[u]["last200"], flat=r["flat"])
    cands = [{"id": f["id"], "name": f["name"], "rule": label(f["x"]["r"]),
              "last200_points": f["x"]["last200"], "half1_points": f["x"]["h1"]["net"], "half2_points": f["x"]["h2"]["net"],
              "before200_points": f["x"]["pre"]["net"], "cost_doubled_last200_points": f["dbl_pts"]["net"],
              "one_year_1x": {k: f["year"][k] for k in ("return_pct", "made", "lost", "trades", "win_pct", "max_dd_pct")},
              "one_year_cost_doubled_return_pct": f["dbl"]["return_pct"],
              "leverage_ladder": f["ladder"], "leverage_needed_for_2_crore": f["lev_for_2cr"]} for f in fin]
    key3 = {(15, 9, 14), (5, 9, 14), (30, 9, 14)}
    jev = jev_pick(cands, fifty[:10] + [x for x in fifty if (x["tf"], x["a"], x["b"]) in key3])
    pick_id = ((jev.get("answers") or {}).get("best") or {}).get("choice") or fin[0]["id"]
    chosen = next(f for f in fin if f["id"] == pick_id)
    r = chosen["x"]["r"]
    X = XS[r["tf"]]

    # chart: the chosen rule's timeframe, last 10 sessions, both EMAs, every trade
    c0 = int(np.searchsorted(X["did"], max(0, len(X["days"]) - 10)))
    ct = lambda k: int(pd.Timestamp(X["time"][k]).value // 1_000_000_000)
    marks = []
    for t in chosen["rows"]:
        if t["t_in"] >= c0:
            marks.append([ct(t["t_in"]), "in", t["side"], f"{t['side']} {t['lots']}"])
            if t["t_out"] < X["n"]:
                marks.append([ct(t["t_out"]), "out", t["side"], f"{t['points']:+.0f} pts {'+' if t['pnl'] > 0 else '−'}₹{abs(t['pnl']) / 1e5:.2f}L"])
    chart = {"tf": r["tf"], "bars": [[ct(k), round(X["O"][k], 2), round(X["H"][k], 2), round(X["L"][k], 2), round(X["C"][k], 2)] for k in range(c0, X["n"])],
             "emas": {str(n): [round(float(X["ema"][n][k]), 2) for k in range(c0, X["n"])] for n in (r["a"], r["b"])},
             "markers": marks, "day_starts": [ct(k) for k in range(c0, X["n"]) if X["newday"][k]]}

    strip = lambda rows_: [{k: v for k, v in t.items() if k not in ("t_in", "t_out")} for t in rows_]
    slim = lambda x: x and {"rule": label(x["r"]), "last200": x["last200"], "h1": x["h1"], "h2": x["h2"], "pre": x["pre"]}
    payload = {
        "version": 1, "name": "Nifty 50 EMA cross lab", "generated_at": datetime.now(I.IST).isoformat(timespec="minutes"),
        "as_of": D["end"], "last_candle": str(XS[5]["time"][-1])[:16], "capital": CAPITAL, "cost_pct": COST * 100,
        "windows": D, "data": checks, "rules_tried": tried, "stage1": s1, "robust": len(rob),
        "emas": EMAS, "timeframes": TFS, "exits": EXITS, "stop_frac": STOP_FRAC, "levs": LEVS,
        "finalists": [{k: v for k, v in f.items() if k not in ("x", "rows")} | {"rule": label(f["x"]["r"]), "key": f["x"]["r"],
                       "last200": f["x"]["last200"], "h1": f["x"]["h1"], "h2": f["x"]["h2"], "pre": f["x"]["pre"]} for f in fin],
        "chosen": pick_id, "chosen_by": "Jev" if jev.get("answers") else "fallback: most points among robust rules",
        "by_tf": {str(u): slim(by_tf[u]) for u in TFS},
        "user_pairs": [{"tf": u, "a": a, "b": b, "rule": label(x["r"]), "last200": x["last200"], "h1": x["h1"], "h2": x["h2"], "pre": x["pre"],
                        "with_50_50": slim(user50[(u, a, b)]),
                        "cross": next((f for f in fifty if (f["tf"], f["a"], f["b"]) == (u, a, b)), None)} for (u, a, b), x in plain.items()],
        "fifty": fifty, "top": [slim(x) for x in rob[:30]],
        "trades": strip(chosen["rows"]), "today": strip([t for t in chosen["rows"] if t["day"] == D["end"]]),
        "next": next_signal(X, r), "chart": chart, "jev": jev,
        "limits": [
            "The finalists were picked on the same last 200 sessions they are scored on; the honest pick and the 'before' column are the fairer guide.",
            "Index candles, not futures. Decisions on a candle's close, filled at the next candle's open; stops and targets fill at their level "
            "(at the open if a candle opens past it). Real fills slip.",
            f"Cost {COST * 100:.3f}% of the position per round trip; the doubled-cost numbers show how much of the edge survives worse fills.",
            "The 10% capital stop closes a trade once it has lost 10% of the money behind it: at 1x that is a 10% Nifty move, which does not "
            "happen inside a day, so at 1x it never triggers; at 5x it is a 2% move, at 10x a 1% move.",
            "Leverage multiplies losses exactly as it multiplies profits. Exchange margin limits how much is available.",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
    }
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for out in (DOCS / "cross.json", PUBLIC / "cross.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(f"tried {tried} | robust {len(rob)} | Jev {jev.get('status')} picked {pick_id} | {len(text) // 1024}KB in {time.time() - t0:.0f}s")
    for f in fin:
        y = f["year"]
        print(f"  {f['id']} {f['name']:<50} last200 {f['x']['last200']['net']:+8.1f} pts n={f['x']['last200']['n']} (halves {f['x']['h1']['net']:+.0f}/{f['x']['h2']['net']:+.0f}, "
              f"before {f['x']['pre']['net']:+.0f}, 2x cost {f['dbl_pts']['net']:+.0f}) | 1y ₹1cr -> {y['end']:,} ({y['return_pct']:+.1f}%) "
              f"made {y['made']:,} lost {y['lost']:,} trades {y['trades']} win {y['win_pct']} | 5x {f['ladder'][4]['return_pct']:+.1f}% "
              f"DD {f['ladder'][4]['max_dd_pct']}% | 2cr at {f['lev_for_2cr']}x")
        print(f"     {label(f['x']['r'])}")
    return payload


if __name__ == "__main__":
    build()
