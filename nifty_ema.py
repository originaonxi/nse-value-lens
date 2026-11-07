#!/usr/bin/env python3
"""Nifty 50 — ONE EMA. Which EMA, on which candle timeframe, tells Nifty's direction best?

The rule (exactly as a trader reads it):
    a candle CLOSES ABOVE EMA(n)  -> bullish: expect Nifty to go up   (stay long)
    a candle CLOSES BELOW EMA(n)  -> bearish: expect Nifty to go down (stay short)
    The view only changes on the opposite close. Nothing else.

Tested: every EMA 3..200 on 5m, 15m, 30m, 75m, 1h, 2h and daily candles.
Measured on the last 140 sessions (fewer where history is shorter) and the last 10 sessions:
    • how often Nifty moved the right way after a close above (up) and after a close below (down),
      measured from that close to the next opposite close (the signal still running is counted at
      the latest close), after ~0.035% of price (about 9 points) of cost per signal
    • average points per signal, net points, profit factor, worst drawdown
    • 1-session follow-through: one session after the signal, was Nifty on the right side?
Arithmetic ranks everything; Jev then judges the best EMA of each timeframe plus the top overall
rules on reliability and recent edge. Final = 60% code score + 40% Jev score. Jev failures are
reported, never invented.

Output: docs/nifty.json (+ public/data). Paper research, not advice.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
PUBLIC = ROOT / "public" / "data"
CACHE = ROOT / "data" / "nifty"
IST = ZoneInfo("Asia/Kolkata")
SYMBOL = "^NSEI"

COST_PCT = 0.00035          # ≈ 0.035% of price per signal ≈ 9 Nifty points at 25,000 (futures round trip)
EMA_PERIODS = list(range(3, 201))
TIMEFRAMES = ["5m", "15m", "30m", "75m", "1h", "2h", "1D"]
TF_MIN = {"5m": 5, "15m": 15, "30m": 30, "75m": 75, "1h": 60, "2h": 120, "1D": None}
BARS_PER_SESSION = {"5m": 75, "15m": 25, "30m": 13, "75m": 5, "1h": 7, "2h": 4, "1D": 1}
WINDOW = 140
RECENT = 10
MIN_TRADES = 8
BLOCK = 10                  # consistency blocks of 10 sessions
EXTRA_FINALISTS = 3
EXPORT_SESSIONS = {"5m": 35}          # all others: WINDOW sessions
ASKED = (5, 6, 9, 10, 11)


# ── data ──────────────────────────────────────────────────────────────────────

def _flatten(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[[c for c in ("Open", "High", "Low", "Close") if c in df.columns]]


def _fetch(interval, period):
    import yfinance as yf
    df = yf.download(SYMBOL, period=period, interval=interval, progress=False, auto_adjust=False)
    return _flatten(df).dropna(subset=["Close"])


def _merge_cache(name, fresh):
    """Keep every bar ever downloaded so the short intraday histories grow each day."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{name}.csv"
    old = pd.DataFrame()
    if path.exists():
        old = pd.read_csv(path, index_col=0)
        old.index = pd.to_datetime(old.index, utc=True)
        old = old[[c for c in ("Open", "High", "Low", "Close") if c in old.columns]]
    if fresh is not None and not fresh.empty:
        idx = fresh.index
        fresh.index = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
        old = pd.concat([old, fresh])
    if old.empty:
        raise SystemExit(f"No Nifty data for {name} (download failed and no cache).")
    old = old[~old.index.duplicated(keep="last")].sort_index()
    old.to_csv(path)
    return old


def _drop_forming(df, minutes, now):
    """Keep only candles that have finished. The last candle of a session ends at 15:30."""
    if df.empty:
        return df
    starts = df.index.tz_convert("UTC").tz_localize(None).to_numpy()
    ends = starts + np.timedelta64(minutes, "m")
    session_close = (df.index.normalize() + pd.Timedelta(hours=15, minutes=30)).tz_convert("UTC").tz_localize(None).to_numpy()
    ends = np.minimum(ends, session_close)
    cut = pd.Timestamp(now).tz_convert("UTC").tz_localize(None).to_datetime64()
    return df[ends <= cut]


def _group_session(df, k, now=None):
    """Merge every k consecutive candles inside one session (anchored at 09:15, never across days)."""
    if df.empty:
        return df
    g = df.copy()
    g["_d"] = g.index.date
    g["_n"] = g.groupby("_d").cumcount() // k
    rows, idx, counts = [], [], []
    for _, grp in g.groupby(["_d", "_n"], sort=True):
        idx.append(grp.index[0])
        counts.append(len(grp))
        rows.append({"Open": grp["Open"].iloc[0], "High": grp["High"].max(),
                     "Low": grp["Low"].min(), "Close": grp["Close"].iloc[-1]})
    out = pd.DataFrame(rows, index=pd.DatetimeIndex(idx))
    if now is not None and len(out) and counts[-1] < k:
        last = out.index[-1]
        if last.date() == now.date() and now.time() < dtime(15, 30):
            out = out.iloc[:-1]                       # group still forming during market hours
    return out


def load_data(now=None):
    now = now or datetime.now(IST)
    raw = {}
    for name, interval, period in (("5m", "5m", "60d"), ("15m", "15m", "60d"),
                                   ("60m", "60m", "730d"), ("1d", "1d", "10y")):
        try:
            fresh = _fetch(interval, period)
        except Exception as e:
            print(f"warn: {name} download failed ({type(e).__name__}); using cache")
            fresh = None
        raw[name] = _merge_cache(name, fresh)

    frames = {}
    for name, tf in (("5m", "5m"), ("15m", "15m"), ("60m", "1h")):
        df = raw[name].copy()
        df.index = df.index.tz_convert(IST)
        t = df.index.time
        df = df[(t >= dtime(9, 15)) & (t < dtime(15, 30))]
        frames[tf] = _drop_forming(df, TF_MIN[tf], now)
    frames["30m"] = _group_session(frames["15m"], 2, now)
    frames["75m"] = _group_session(frames["15m"], 5, now)
    frames["2h"] = _group_session(frames["1h"], 2, now)

    d = raw["1d"].copy()
    d.index = d.index.tz_convert(IST).normalize().tz_localize(None)
    if now.hour * 60 + now.minute < 15 * 60 + 35:
        d = d[d.index.date < now.date()]
    frames["1D"] = d[~d.index.duplicated(keep="last")]

    out = {}
    for tf in TIMEFRAMES:
        df = frames[tf].dropna(subset=["Open", "High", "Low", "Close"]).copy()
        df["session"] = [str(x.date()) for x in df.index]
        out[tf] = df
    return out


# ── the rule ──────────────────────────────────────────────────────────────────

def ema(values, period):
    return pd.Series(values, dtype=float).ewm(span=period, adjust=False).mean().to_numpy()


def ffill_zero(s):
    s = np.asarray(s, dtype=float).copy()
    for i in range(1, len(s)):
        if s[i] == 0:
            s[i] = s[i - 1]
    return s


def side_of(close, period):
    """+1 while the last close is above the EMA, -1 while below."""
    close = np.asarray(close, dtype=float)
    return ffill_zero(np.sign(close - ema(close, period)))


def rule_trades(close, period, warm, cost_pct=COST_PCT):
    """Each signal = a close that switches sides; it is held until the next opposite close.
    Returns flips, ends, dirs (+1 up / -1 down), gross (points the right way, no cost),
    net (after cost), closed (False only for the signal still running)."""
    close = np.asarray(close, dtype=float)
    side = side_of(close, period)
    if warm >= len(close) - 1:
        e = np.array([])
        return np.array([], int), np.array([], int), e, e, e, np.array([], bool)
    flips = np.flatnonzero(np.diff(side[warm:]) != 0) + 1 + warm
    ends = np.append(flips[1:], len(close) - 1).astype(int)
    dirs = side[flips]
    gross = (close[ends] - close[flips]) * dirs
    net = gross - cost_pct * close[flips]
    closed = np.ones(len(flips), bool)
    if len(flips):
        closed[-1] = False
    return flips, ends, dirs, gross, net, closed


def metrics(gross, net, dirs, fwd, nsess, block_net=None):
    """gross/net/dirs = closed signals in the window; fwd = 1-session follow-through."""
    gross, net, dirs, fwd = (np.asarray(x, float) for x in (gross, net, dirs, fwd))
    nsess = max(1, int(nsess))
    fv = fwd[~np.isnan(fwd)]
    out = {"sessions": nsess, "fwd_n": int(len(fv)),
           "fwd_hit": round(float((fv > 0).mean() * 100), 1) if len(fv) else None,
           "fwd_avg": round(float(fv.mean()), 1) if len(fv) else None,
           "fwd_hit_s": round(float(((fv > 0).sum() + 5) / (len(fv) + 10) * 100), 1)}
    if block_net is not None and len(block_net):
        out["blocks_pos"] = int((np.asarray(block_net) > 0).sum())
        out["blocks"] = int(len(block_net))
    n = int(len(net))
    out["trades"] = n
    if n == 0:
        return out | {"dir_hit": None, "dir_hit_s": 50.0, "win_rate": None, "pf": None, "net": 0.0,
                      "avg": None, "max_dd": 0.0, "net_ps": 0.0, "per_session": 0.0,
                      "up_n": 0, "up_hit": None, "down_n": 0, "down_hit": None, "up_net": 0.0, "down_net": 0.0}
    right = gross > 0
    win = net > 0
    gw, gl = net[win].sum(), -net[~win].sum()
    pf = gw / gl if gl > 0 else (10.0 if gw > 0 else 0.0)
    eq = np.concatenate([[0.0], np.cumsum(net)])
    dd = float((np.maximum.accumulate(eq) - eq).max())
    up, dn = dirs > 0, dirs < 0
    return out | {
        "dir_hit": round(float(right.mean() * 100), 1),
        "dir_hit_s": round(float((right.sum() + 5) / (n + 10) * 100), 1),
        "win_rate": round(float(win.mean() * 100), 1), "pf": round(float(min(pf, 10.0)), 2),
        "net": round(float(net.sum()), 1), "avg": round(float(net.mean()), 1), "max_dd": round(dd, 1),
        "net_ps": round(float(net.sum() / nsess), 1), "per_session": round(n / nsess, 2),
        "up_n": int(up.sum()), "up_hit": round(float(right[up].mean() * 100), 1) if up.any() else None,
        "down_n": int(dn.sum()), "down_hit": round(float(right[dn].mean() * 100), 1) if dn.any() else None,
        "up_net": round(float(net[up].sum()), 1), "down_net": round(float(net[dn].sum()), 1),
    }


def sessions_of(df):
    uniq, inv = np.unique(df["session"].to_numpy(), return_inverse=True)
    return uniq, inv


def evaluate(frames):
    """Every EMA on every timeframe. 'main' = the same latest sessions for every timeframe
    (the most all timeframes have, up to 140); 'w140' = up to 140 sessions of each timeframe."""
    usable = [f for f in frames.values() if len(f) >= 200]
    main_n = min(WINDOW, min(f["session"].nunique() for f in usable))
    rules = []
    for tf in TIMEFRAMES:
        df = frames[tf]
        if len(df) < 200:
            continue
        close = df["Close"].to_numpy(float)
        uniq, sidx = sessions_of(df)
        ns = len(uniq)
        H = BARS_PER_SESSION[tf]
        starts = {"main": ns - main_n, "w140": max(0, ns - WINDOW), "recent": max(0, ns - RECENT), "full": 0}
        for p in EMA_PERIODS:
            warm = 3 * p
            if warm >= len(close) - 60:
                continue
            flips, ends, dirs, gross, net, closed = rule_trades(close, p, warm)
            if len(flips) < 3:
                continue
            fi = np.minimum(flips + H, len(close) - 1)
            fwd = np.where(flips + H < len(close), (close[fi] - close[flips]) * dirs, np.nan)
            first_ok = int(sidx[warm])
            r = {"key": f"{tf}|{p}", "tf": tf, "ema": p}
            for name, first in starts.items():
                first = max(first, first_ok)
                m = sidx[flips] >= first
                mc = m                      # the running signal counts at the latest close
                blocks = None
                if name == "main":
                    per = np.bincount(sidx[flips][mc] - first, weights=net[mc], minlength=ns - first)
                    nb = len(per) // BLOCK
                    blocks = per[len(per) - nb * BLOCK:].reshape(nb, BLOCK).sum(1) if nb else per[:0]
                r[name] = metrics(gross[mc], net[mc], dirs[mc], fwd[m], ns - first, blocks)
            rf = max(starts["recent"], first_ok)
            m = sidx[flips] >= rf
            per = np.bincount(sidx[flips][m] - rf, weights=net[m], minlength=ns - rf)
            r["recent_by_session"] = [round(float(x), 1) for x in per]
            rules.append(r)
    return rules, main_n


def score(rules):
    """Rank on the common window so every timeframe is judged on the same dates.
    The user's rule has two halves - close above means up AND close below means down - so a rule
    must make money on both its up signals and its down signals to score fully."""
    elig = [r for r in rules if r["main"]["trades"] >= MIN_TRADES
            and r["main"]["up_n"] >= 2 and r["main"]["down_n"] >= 2]
    if not elig:
        raise SystemExit("No rule has enough signals to rank.")
    g = lambda r, k, w="main": r[w].get(k) or 0
    f = pd.DataFrame({
        "nps": [g(r, "net_ps") for r in elig],
        "pf": [g(r, "pf") for r in elig],
        "cons": [g(r, "blocks_pos") / max(1, g(r, "blocks") or 1) for r in elig],
        "fwd": [g(r, "fwd_hit_s") for r in elig],
        "bal": [min(g(r, "up_net"), g(r, "down_net")) / r["main"]["sessions"] for r in elig],
        "w140": [g(r, "net_ps", "w140") for r in elig],
        "fpf": [g(r, "pf", "full") for r in elig],
        "rec": [g(r, "net", "recent") for r in elig],
    })
    rk = f.rank(pct=True)
    W = {"nps": .20, "pf": .15, "cons": .15, "fwd": .15, "bal": .15, "w140": .10, "fpf": .05, "rec": .05}
    for i, r in enumerate(elig):
        m = r["main"]
        s = 100 * sum(W[k] * rk[k].iloc[i] for k in W)
        if m["net"] <= 0 or (m["pf"] or 0) < 1:
            s *= 0.5
        if m["up_net"] <= 0 or m["down_net"] <= 0:      # only one half of the rule works
            s *= 0.75
        if (r["full"]["pf"] or 0) < 1:
            s *= 0.8
        r["code_score"] = round(float(s), 1)
        r["two_sided"] = bool(m["up_net"] > 0 and m["down_net"] > 0)
    for r in rules:
        r.setdefault("code_score", None)
        r.setdefault("two_sided", False)
    return rules


# ── Jev ───────────────────────────────────────────────────────────────────────

JEV_QUESTIONS = {
    "reliability": {
        "type": "choice",
        "instructions": (
            "A trader reads ONE moving average on the NIFTY 50 index: when a candle of the given timeframe closes "
            "above the EMA he expects Nifty to go up, when it closes below he expects it to go down, and the view "
            "only changes on the opposite close. Using ONLY these numbers (number of signals, how often Nifty went "
            "up after a close above and down after a close below before the opposite close, profit factor, net and "
            "average points per signal after realistic futures costs, worst drawdown, how many 10-session blocks were "
            "profitable, follow-through one session later, and how many sessions were tested), "
            "how reliable is this EMA as a direction signal? Penalise few signals, short test windows, many "
            "signals per session with a thin edge, big drawdowns versus net points, and windows that disagree."),
        "criteria": {"weak": None, "fair": None, "good": None, "strong": None},
    },
    "recent_edge": {
        "type": "choice",
        "instructions": (
            "Compare the last 10 sessions (including net points per session) with the longer window and the full "
            "history for this same EMA rule. Is its edge degrading, stable or improving right now?"),
        "criteria": {"degrading": None, "stable": None, "improving": None},
    },
}
REL_W = {"weak": 0.0, "fair": 1 / 3, "good": 2 / 3, "strong": 1.0}
EDGE_W = {"degrading": 0.0, "stable": 0.5, "improving": 1.0}


def jev_state(r):
    keep = ("trades", "sessions", "dir_hit", "up_n", "up_hit", "down_n", "down_hit", "win_rate", "pf", "net", "avg",
            "max_dd", "per_session", "fwd_hit", "fwd_avg", "blocks_pos", "blocks")
    pick = lambda m: {k: m.get(k) for k in keep}
    return {
        "instrument": "NIFTY 50 index",
        "rule": f"{r['tf']} candle close above EMA {r['ema']} = expect up; close below = expect down",
        "timeframe": r["tf"], "ema_period": r["ema"], "cost_pct_of_price_per_signal": COST_PCT * 100,
        "same_dates_window_all_timeframes": pick(r["main"]),
        "up_to_140_sessions": pick(r["w140"]),
        "last_10_sessions": pick(r["recent"]) | {"net_points_by_session": r["recent_by_session"]},
        "full_history": pick(r["full"]),
    }


def jev_judge(finalists):
    try:
        sys.path.insert(0, str(ROOT))
        from jev_client import Client, MODEL
        client = Client()
    except Exception as e:
        return {"status": f"unavailable: {e}", "model": None}, {}

    def one(r):
        try:
            a = client.ask(jev_state(r), JEV_QUESTIONS)
            rel, edge = a["reliability"], a["recent_edge"]
            s = 100 * (0.7 * sum(REL_W[k] * v for k, v in rel["probabilities"].items())
                       + 0.3 * sum(EDGE_W[k] * v for k, v in edge["probabilities"].items()))
            return r["key"], {"reliability": rel["choice"], "reliability_conf": round(rel["confidence"] * 100),
                              "recent_edge": edge["choice"], "recent_edge_conf": round(edge["confidence"] * 100),
                              "jev_score": round(s, 1)}
        except Exception as e:
            return r["key"], {"error": type(e).__name__ + ": " + str(e)[:80]}

    with ThreadPoolExecutor(max_workers=4) as pool:
        res = dict(pool.map(one, finalists))
    ok = sum(1 for v in res.values() if "jev_score" in v)
    return {"status": f"judged {ok}/{len(finalists)}", "model": MODEL,
            "tokens": [client.input_tokens, client.output_tokens]}, res


# ── export ────────────────────────────────────────────────────────────────────

def chart_time(ts, tf):
    ts = pd.Timestamp(ts)
    if tf == "1D":
        return ts.strftime("%Y-%m-%d")
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)            # IST wall clock, plotted as-is
    return int(ts.value // 1_000_000_000)


def export_chart(df, tf, p):
    close = df["Close"].to_numpy(float)
    e = ema(close, p)
    side = side_of(close, p)
    uniq, sidx = sessions_of(df)
    keep = EXPORT_SESSIONS.get(tf, WINDOW)
    first = max(0, len(uniq) - keep)
    start = int(np.argmax(sidx >= first))
    warm = 3 * p
    times = [chart_time(t, tf) for t in df.index[start:]]
    o, h, l = (df[c].to_numpy(float) for c in ("Open", "High", "Low"))
    bars = [[times[i - start], round(o[i], 2), round(h[i], 2), round(l[i], 2), round(close[i], 2)]
            for i in range(start, len(df))]
    emav = [round(float(e[i]), 2) if i >= warm else None for i in range(start, len(df))]
    flips = np.flatnonzero(np.diff(side) != 0) + 1
    flips = flips[flips >= max(start, warm)]
    marks = [[chart_time(df.index[f], tf), int(side[f]), round(float(close[f]), 2)] for f in flips]
    last_flip = int(flips[-1]) if len(flips) else None
    return {"ema": p, "sessions": int(len(uniq) - first), "bars": bars, "ema_values": emav, "markers": marks,
            "side": "ABOVE" if side[-1] > 0 else "BELOW", "close": round(float(close[-1]), 2),
            "ema_now": round(float(e[-1]), 2),
            "since": str(df.index[last_flip])[:16] if last_flip is not None else None,
            "since_close": round(float(close[last_flip]), 2) if last_flip is not None else None}


def slim(r):
    out = {k: r[k] for k in ("key", "tf", "ema", "code_score", "two_sided", "main", "w140", "recent", "full",
                             "recent_by_session")}
    for k in ("jev", "final"):
        if k in r:
            out[k] = r[k]
    return out


def build(now=None):
    now = now or datetime.now(IST)
    frames = load_data(now)
    coverage = {tf: {"bars": len(f), "sessions": int(f["session"].nunique()),
                     "from": str(f.index[0])[:16], "to": str(f.index[-1])[:16]} for tf, f in frames.items()}
    print("coverage:", {tf: (c["sessions"], c["from"][:10], c["to"][:10]) for tf, c in coverage.items()})

    rules, main_n = evaluate(frames)
    rules = score(rules)
    ranked = sorted([r for r in rules if r["code_score"] is not None], key=lambda r: -r["code_score"])
    best_tf = {}
    for r in ranked:
        best_tf.setdefault(r["tf"], r)
    finalists = list(best_tf.values())
    for r in ranked:
        if len(finalists) >= len(best_tf) + EXTRA_FINALISTS:
            break
        if r not in finalists:
            finalists.append(r)

    jev_meta, jev = jev_judge(finalists)
    judged = sum(1 for v in jev.values() if "jev_score" in v)
    blended = judged >= max(1, int(0.8 * len(finalists)))
    for r in finalists:
        j = jev.get(r["key"])
        r["jev"] = j
        r["final"] = round(0.6 * r["code_score"] + 0.4 * (j or {}).get("jev_score", 50.0), 1) if blended else r["code_score"]
    finalists.sort(key=lambda r: -r["final"])
    chosen = finalists[0]
    jev_meta["blended"] = blended

    # charts: the best EMA of every timeframe (chosen one included)
    charts = {}
    for tf in TIMEFRAMES:
        if tf in best_tf:
            p = chosen["ema"] if tf == chosen["tf"] else best_tf[tf]["ema"]
            charts[tf] = export_chart(frames[tf], tf, p)

    # chosen rule: every signal in the exported window
    df = frames[chosen["tf"]]
    close = df["Close"].to_numpy(float)
    flips, ends, dirs, gross, pts, closed = rule_trades(close, chosen["ema"], 3 * chosen["ema"])
    uniq, sidx = sessions_of(df)
    first = max(0, len(uniq) - WINDOW)
    signals = [[str(df.index[f])[:16], int(d), round(float(close[f]), 2), str(df.index[e])[:16],
                round(float(close[e]), 2), round(float(pt), 1), bool(c)]
               for f, e, d, pt, c in zip(flips, ends, dirs, pts, closed) if sidx[f] >= first]
    cur = charts[chosen["tf"]]
    running = (close[-1] - close[flips[-1]]) * dirs[-1] if len(flips) else 0.0
    common_from = sorted(set(frames["15m"]["session"]))[-main_n]

    heat = {tf: [None] * len(EMA_PERIODS) for tf in TIMEFRAMES}
    for r in rules:
        heat[r["tf"]][r["ema"] - EMA_PERIODS[0]] = r["code_score"]

    d = frames["1D"]
    payload = {
        "version": 2, "name": "Nifty 50 — one EMA",
        "as_of": str(d.index[-1].date()), "generated_at": now.isoformat(timespec="minutes"),
        "last_close": round(float(d["Close"].iloc[-1]), 2),
        "change_pct": round(float(d["Close"].iloc[-1] / d["Close"].iloc[-2] * 100 - 100), 2),
        "cost_pct": COST_PCT * 100, "cost_points_now": round(COST_PCT * float(d["Close"].iloc[-1]), 1),
        "window": WINDOW, "main_sessions": main_n, "main_from": common_from, "recent": RECENT,
        "tested": {"ema_from": EMA_PERIODS[0], "ema_to": EMA_PERIODS[-1], "timeframes": TIMEFRAMES,
                   "rules": len(rules), "ranked": len(ranked)},
        "coverage": coverage,
        "chosen": slim(chosen) | {
            "now": {"side": cur["side"], "close": cur["close"], "ema": cur["ema_now"], "since": cur["since"],
                    "since_close": cur["since_close"], "running_pts": round(float(running), 1),
                    "flip_level": cur["ema_now"]},
            "signals": signals},
        "finalists": [slim(r) for r in finalists],
        "asked": [slim(r) for r in rules if r["ema"] in ASKED],
        "top": [slim(r) for r in ranked[:30]],
        "heatmap": heat,
        "charts": charts,
        "jev": jev_meta,
        "limits": [
            "The winner is picked from the same history it is tested on, so live results will usually be weaker.",
            f"Each signal pays {COST_PCT*100:.3f}% of price (about {COST_PCT*25000:.0f} Nifty points at 25,000): STT 0.02% on the "
            "sell side, stamp duty, exchange fees, brokerage and about 1 point of slippage each side on Nifty futures. "
            "Signals are held overnight until the opposite close, so gaps are included.",
            "5-minute, 15-minute, 30-minute and 75-minute candles only go back about 60 sessions (a Yahoo limit). "
            "The page saves every new candle, so these windows grow by one session each day until they reach 140. "
            "To be fair, every timeframe is ranked on the same dates (the sessions all timeframes have). Hourly, "
            "2-hour and daily rules also show their full 140-session results.",
            "Index candles, not futures. A trend rule like this loses in sideways markets.",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
    }
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for out in (DOCS / "nifty.json", PUBLIC / "nifty.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    c, w = payload["chosen"], payload["chosen"]["main"]
    print(f"nifty.json {payload['as_of']}: {len(rules)} rules | chosen {c['tf']} EMA {c['ema']} "
          f"(code {c['code_score']}, final {c['final']}) | {w['sessions']} sessions: {w['trades']} signals, "
          f"dir {w['dir_hit']}% (up {w['up_hit']}% / down {w['down_hit']}%), PF {w['pf']}, net {w['net']}, blocks {w.get('blocks_pos')}/{w.get('blocks')} | last10 {c['recent']['net']} | "
          f"now {c['now']['side']} EMA {c['now']['ema']} | Jev {jev_meta['status']} | {len(text)//1024}KB")
    print("best per timeframe:", [(r["tf"], r["ema"], r["code_score"], r.get("final")) for r in finalists])
    return payload


if __name__ == "__main__":
    build()
