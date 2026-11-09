#!/usr/bin/env python3
"""Nifty 50 - the best setup from everything researched on this site, tested on every combination.

Base (unchanged): 2-hour NIFTY 50 candles, BUY on a close above EMA 105 (SELL on a close below for the short family).
Every signal researched on the site is a possible confirmation (0-3 at once):
  trend      ADX(14)>20 · Supertrend(10,3) · yesterday's daily close vs daily EMA 50 · vs daily EMA 200 · EMA 105 slope
  momentum   RSI(14) above/below 50 · MACD(12,26,9) histogram · DI+ vs DI-
  order flow (from the NSE F&O bhavcopy, previous session, as on the Order Flow page)
             NIFTY future long build-up (price up, OI up) / short build-up for sells
             option writers: put OI added > call OI added (bullish) / the reverse (bearish)
             put-call ratio above 1 / below 1
  day/night  today's opening gap is up / down (known once the market opens)
Exits (all combinations): a 2-hour close back through EMA 105 always exits; plus optional RSI TOP (68 / 70, then -5),
ATR profit target (1, 1.5, 2, 3 ATR), ATR stop (1.5, 2.5 ATR) and a time stop (12 two-hour candles = 3 sessions).
After a TOP / target / time exit, the rule buys again only when price is back within 1 ATR of EMA 105.

Honesty:
  * ~650 sessions (Mar 2024 → today), never less than 200 for any reported rule.
  * Split in three equal thirds by time; a rule must make money in EVERY third ("walk-forward"), and is ranked by its
    weakest third. The last third is also reported separately as the unseen part.
  * Costs 0.035% of price per trade. Daily and order-flow inputs use the PREVIOUS session (no look-ahead).
  * Bayesian win rate (Beta(1,1)), t-stat, and best-of-N luck level are reported for the number of rules tried.
Output: docs/nifty_best.json (+ public/data), data/order_flow/nifty_flow.csv (NIFTY daily order-flow cache).
Paper research, not advice.
"""
import datetime as dt
import itertools
import json
import math
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import nifty_ema as N       # noqa: E402
import nifty_combo as K     # noqa: E402
import options_desk as od   # noqa: E402

DOCS, PUBLIC = ROOT / "docs", ROOT / "public" / "data"
FLOW_CACHE = ROOT / "data" / "order_flow" / "nifty_flow.csv"
COST = N.COST_PCT
EMA_N = 105
MIN_TRADES = 20
MIN_THIRD = 5
RE_ENTRY_ATR = 1.0
CHART_SESSIONS = 140
EXIT_GRID = {"rsi": (None, 68, 70), "tp": (None, 1.0, 1.5, 2.0, 3.0), "sl": (None, 1.5, 2.5), "maxbars": (None, 12)}


# ── NIFTY order flow, one row per session, from the bhavcopy ──────────────────

def flow_day(day):
    with zipfile.ZipFile(od.raw_path(dt.date.fromisoformat(day))) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        f = pd.read_csv(z.open(name), usecols=["TckrSymb", "FinInstrmTp", "XpryDt", "OptnTp", "ClsPric", "SttlmPric", "PrvsClsgPric",
                                               "OpnIntrst", "ChngInOpnIntrst"], low_memory=False)
    f = f[f.TckrSymb == "NIFTY"]
    f["exp"] = pd.to_datetime(f.XpryDt)
    fut = f[f.FinInstrmTp == "IDF"].sort_values("exp")
    opt = f[(f.FinInstrmTp == "IDO") & (f.exp >= pd.Timestamp(day))]
    if fut.empty or opt.empty:
        return None
    near = fut.iloc[0]
    close = near.ClsPric if near.ClsPric > 0 else near.SttlmPric
    ch = opt[opt.exp == opt.exp.min()]
    pe, ce = ch[ch.OptnTp == "PE"], ch[ch.OptnTp == "CE"]
    oi, oi_chg = float(fut.OpnIntrst.sum()), float(fut.ChngInOpnIntrst.sum())
    return {"date": day, "fut_move": float(close / near.PrvsClsgPric - 1) * 100 if near.PrvsClsgPric else np.nan,
            "oi_pct": oi_chg / (oi - oi_chg) * 100 if oi - oi_chg > 0 else np.nan,
            "pcr": float(pe.OpnIntrst.sum() / ce.OpnIntrst.sum()) if ce.OpnIntrst.sum() > 0 else np.nan,
            "put_add": float(pe.ChngInOpnIntrst.sum()), "call_add": float(ce.ChngInOpnIntrst.sum())}


def nifty_flow(start):
    have = pd.read_csv(FLOW_CACHE) if FLOW_CACHE.exists() else pd.DataFrame(columns=["date"])
    done = set(have.date)
    since = dt.date.fromisoformat(max(done)) - dt.timedelta(days=7) if done else dt.date.fromisoformat(start)
    try:
        od.download(dt.date.today(), start=since, pause=0.15)
    except Exception as e:  # pragma: no cover - network
        print(f"warn: bhavcopy download failed ({type(e).__name__}); using the cache")
    days = [d for d in od.sessions_available() if d >= start and d not in done]
    rows = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for r in pool.map(lambda d: _safe(flow_day, d), days):
            if r:
                rows.append(r)
    out = pd.concat([have, pd.DataFrame(rows)], ignore_index=True) if rows else have
    out = out.drop_duplicates("date", keep="last").sort_values("date")
    FLOW_CACHE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(FLOW_CACHE, index=False)
    out["buildup"] = K_buildup(out.fut_move, out.oi_pct)
    return out.set_index("date"), len(rows)


def _safe(fn, *a):
    try:
        return fn(*a)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, StopIteration):
        return None


def K_buildup(move, oi_pct):
    return np.select([(move > 0) & (oi_pct > 0), (move < 0) & (oi_pct > 0), (move > 0) & (oi_pct < 0), (move < 0) & (oi_pct < 0)],
                     ["LONG_BUILD", "SHORT_BUILD", "SHORT_COVER", "LONG_UNWIND"], "NEUTRAL")


# ── signals on the 2-hour bars ────────────────────────────────────────────────

def features(frames, flow):
    df = frames["2h"]
    X = K.indicators(df, EMA_N, frames["1D"])
    n = len(X["c"])
    dates = pd.Index([str(t.date()) for t in df.index])
    days = sorted(set(dates))
    prev_day = {d: (days[i - 1] if i else None) for i, d in enumerate(days)}
    # previous session's order flow, mapped to every 2-hour bar of today
    def prev(col):
        s = flow[col] if col in flow else pd.Series(dtype=float)
        return np.array([s.get(prev_day[d], np.nan) if prev_day[d] else np.nan for d in dates], dtype=object)
    bu = prev("buildup")
    pcr = prev("pcr").astype(float)
    pa, ca = prev("put_add").astype(float), prev("call_add").astype(float)
    of_ok = ~np.isnan(pcr)
    # today's opening gap vs the previous session's last close
    first_open = df.groupby(dates)["Open"].first()
    last_close = df.groupby(dates)["Close"].last()
    gap = np.array([(first_open[d] / last_close[prev_day[d]] - 1) * 100 if prev_day[d] else np.nan for d in dates])
    F = K.filters(X)
    L = {k: F[k] for k in ("ADX>20", "Supertrend", "Daily>EMA50", "Daily>EMA200", "EMA slope", "RSI>50", "MACD hist", "DI+>DI-")}
    L["Futures build-up"] = (of_ok & (bu == "LONG_BUILD"), of_ok & (bu == "SHORT_BUILD"))
    L["Option writers"] = (of_ok & (pa > ca), of_ok & (ca > pa))
    L["PCR"] = (of_ok & (pcr > 1), of_ok & (pcr < 1))
    L["Opening gap"] = (gap > 0, gap < 0)
    for k in L:
        L[k] = (np.asarray(L[k][0], bool), np.asarray(L[k][1], bool))
    X["gap"], X["pcr_prev"], X["bu_prev"], X["dates"] = gap, pcr, bu, dates
    X["of_from"] = next((dates[i] for i in range(n) if of_ok[i]), None)
    return X, L


INFO = {
    "ADX>20": "ADX(14) above 20 — a trend exists",
    "Supertrend": "Supertrend(10,3) points the same way",
    "Daily>EMA50": "yesterday's daily close is above (sell: below) the daily EMA 50",
    "Daily>EMA200": "yesterday's daily close is above (sell: below) the daily EMA 200",
    "EMA slope": "EMA 105 is rising (sell: falling) over 5 candles",
    "RSI>50": "RSI(14) above 50 (sell: below 50)",
    "MACD hist": "MACD(12,26,9) histogram above 0 (sell: below 0)",
    "DI+>DI-": "DI+ above DI- (sell: DI- above DI+)",
    "Futures build-up": "yesterday the NIFTY future had a long build-up: price up, open interest up (sell: short build-up)",
    "Option writers": "yesterday more put OI than call OI was added (sell: more calls than puts)",
    "PCR": "yesterday's put-call OI ratio above 1 (sell: below 1)",
    "Opening gap": "today Nifty opened above yesterday's close (sell: below)",
}


# ── simulation ────────────────────────────────────────────────────────────────

def simulate(X, ok, side=1, rsi=None, tp=None, sl=None, maxbars=None, start=K.WARM, end=None):
    """Long (side=1) or short (side=-1). Entries and exits at 2-hour closes. Returns (entry, exit, net %, why)."""
    c, e, atr, r, d = X["c"], X["ema"], X["atr"], X["rsi"], X["dist"]
    n = len(c) if end is None else end
    trades, pos, eb, ep, ea, blocked, armed = [], False, 0, 0.0, 0.0, False, False
    for i in range(start, n):
        if pos:
            mv = side * (c[i] - ep)
            why = None
            if side * (c[i] - e[i]) < 0:
                why = "ema"
            elif sl is not None and mv <= -sl * ea:
                why = "stop"
            elif tp is not None and mv >= tp * ea:
                why = "target"
            elif rsi is not None:
                if (side == 1 and r[i] >= rsi) or (side == -1 and r[i] <= 100 - rsi):
                    armed = True
                if armed and ((side == 1 and r[i] < rsi - 5) or (side == -1 and r[i] > 105 - rsi)):
                    why = "top"
            if why is None and maxbars is not None and i - eb >= maxbars:
                why = "time"
            if why:
                trades.append((eb, i, (mv - COST * ep) / ep * 100, why))
                pos, armed = False, False
                blocked = why != "ema"
            continue
        if blocked and (side * (c[i] - e[i]) <= 0 or abs(d[i]) <= RE_ENTRY_ATR):
            blocked = False
        if not blocked and side * (c[i] - e[i]) > 0 and ok[i]:
            pos, eb, ep, ea, armed = True, i, c[i], atr[i], False
    if pos:
        trades.append((eb, n - 1, (side * (c[n - 1] - ep) - COST * ep) / ep * 100, "open"))
    return trades


def stats(tr):
    r = np.array([t[2] for t in tr], float)
    if not len(r):
        return {"n": 0, "win": None, "pf": None, "net": 0.0, "dd": 0.0, "avg": None}
    w = r > 0
    gl = -r[~w].sum()
    eq = np.r_[0.0, np.cumsum(r)]
    return {"n": int(len(r)), "win": round(float(w.mean() * 100), 1), "pf": round(float(min(r[w].sum() / gl, 99.0)), 2) if gl > 0 else 99.0,
            "net": round(float(r.sum()), 2), "dd": round(float((np.maximum.accumulate(eq) - eq).max()), 2),
            "avg": round(float(r.mean()), 3), "avg_win": round(float(r[w].mean()), 3) if w.any() else None,
            "avg_loss": round(float(-r[~w].mean()), 3) if (~w).any() else None}


def score_part(s):
    if not s["n"] or s["pf"] is None:
        return 0.0
    return (min(s["pf"], 5) / 5 * 0.35 + s["win"] / 100 * 0.35 + min(max(s["net"], 0) / max(s["dd"], 0.5), 6) / 6 * 0.30)


def label(r):
    ex = ["exit on a close through EMA 105"]
    if r["rsi"]:
        ex.append(f"TOP at RSI {r['rsi']}")
    if r["tp"]:
        ex.append(f"target {r['tp']:g} ATR")
    if r["sl"]:
        ex.append(f"stop {r['sl']:g} ATR")
    if r["maxbars"]:
        ex.append(f"max {r['maxbars']} candles")
    return ("BUY" if r["side"] == 1 else "SELL") + " · EMA 105" + "".join(" + " + f for f in r["filters"]) + " · " + ", ".join(ex)


def grid(X, L, thirds):
    n = len(X["c"])
    names = list(L)
    combos = [()] + [cb for k in (1, 2, 3) for cb in itertools.combinations(names, k)]
    exits = list(itertools.product(*EXIT_GRID.values()))
    rows = []
    for side in (1, -1):
        for cb in combos:
            ok = np.ones(n, bool)
            for f in cb:
                ok &= L[f][0] if side == 1 else L[f][1]
            if ok[K.WARM:].sum() < 30:
                continue
            for rsi, tp, sl, mb in exits:
                tr = simulate(X, ok, side, rsi, tp, sl, mb)
                al = stats(tr)
                if al["n"] < MIN_TRADES:
                    continue
                parts = [stats([t for t in tr if a <= t[0] < b]) for a, b in thirds]
                row = {"side": side, "filters": list(cb), "rsi": rsi, "tp": tp, "sl": sl, "maxbars": mb, "all": al, "thirds": parts}
                row["every_third"] = all(p["n"] >= MIN_THIRD and (p["pf"] or 0) > 1 for p in parts)
                row["robust"] = round(min(score_part(p) for p in parts), 4) if row["every_third"] else None
                rows.append(row)
    return rows


def bayes(s):
    w = round(s["win"] * s["n"] / 100) if s["n"] else 0
    return round((1 + w) / (2 + s["n"]) * 100, 1) if s["n"] else None


def t_stat(tr):
    r = np.array([t[2] for t in tr], float)
    return round(float(r.mean() / (r.std(ddof=1) / math.sqrt(len(r)))), 2) if len(r) > 2 and r.std(ddof=1) > 0 else None


def jev(finalists):
    try:
        from jev_client import Client, MODEL
        client = Client()
    except Exception as e:  # pragma: no cover
        return {"status": f"unavailable: {e}", "model": None}, {}
    Q = {"reliability": K.JEV_QUESTIONS["reliability"], "overfit": K.JEV_QUESTIONS["overfit"]}

    def one(item):
        i, r = item
        state = {"rule": r["label"], "instrument": "NIFTY 50 index, 2-hour candles", "whole": r["all"],
                 "thirds_by_time": r["thirds"], "unseen_last_third": r["thirds"][-1], "rules_tried": r["tried"],
                 "cost_pct_per_trade": COST * 100}
        try:
            a = client.ask(state, Q)
            rel, ovf = a["reliability"], a["overfit"]
            s = 100 * (0.6 * sum(K.REL_W[k] * v for k, v in rel["probabilities"].items()) + 0.4 * sum(K.OVF_W[k] * v for k, v in ovf["probabilities"].items()))
            return i, {"reliability": rel["choice"], "overfit": ovf["choice"], "jev_score": round(s, 1)}
        except Exception as e:  # pragma: no cover
            return i, {"error": type(e).__name__}
    with ThreadPoolExecutor(max_workers=4) as pool:
        res = dict(pool.map(one, list(enumerate(finalists))))
    ok = sum(1 for v in res.values() if "jev_score" in v)
    return {"status": f"judged {ok}/{len(finalists)}", "model": MODEL}, res


def live_state(X, L, r, trades, df):
    i = len(X["c"]) - 1
    c, e = X["c"], X["ema"]
    side = r["side"]
    checks = [{"name": "2-hour close " + ("above" if side == 1 else "below") + " EMA 105", "ok": bool(side * (c[i] - e[i]) > 0),
               "value": f"{c[i]:,.2f} vs {e[i]:,.2f}"}]
    vals = {"ADX>20": f"ADX {X['adx'][i]:.1f}", "Supertrend": "up" if X["st"][i] == 1 else "down",
            "Daily>EMA50": "above" if X["d50"][i] == 1 else "below", "Daily>EMA200": "above" if X["d200"][i] == 1 else "below",
            "EMA slope": f"{X['slope'][i]:+.2f} ATR", "RSI>50": f"RSI {X['rsi'][i]:.1f}", "MACD hist": f"{X['macdh'][i]:+.1f}",
            "DI+>DI-": f"{X['pdi'][i]:.1f} / {X['ndi'][i]:.1f}", "Futures build-up": str(X["bu_prev"][i]),
            "Option writers": "puts > calls" if L["Option writers"][0][i] else "calls ≥ puts",
            "PCR": f"{X['pcr_prev'][i]:.2f}" if np.isfinite(X["pcr_prev"][i]) else "—",
            "Opening gap": f"{X['gap'][i]:+.2f}%" if np.isfinite(X["gap"][i]) else "—"}
    for f in r["filters"]:
        checks.append({"name": INFO[f], "ok": bool((L[f][0] if side == 1 else L[f][1])[i]), "value": vals[f]})
    last = trades[-1] if trades else None
    if last and last[3] == "open":
        gain = side * (c[i] - c[last[0]]) / c[last[0]] * 100
        armed = r["rsi"] and bool(((X["rsi"][last[0]:i + 1] >= r["rsi"]) if side == 1 else (X["rsi"][last[0]:i + 1] <= 100 - r["rsi"])).any())
        ent = c[last[0]]
        levels = []
        if r["tp"]:
            levels.append(f"target {ent + side * r['tp'] * X['atr'][last[0]]:,.0f}")
        if r["sl"]:
            levels.append(f"stop {ent - side * r['sl'] * X['atr'][last[0]]:,.0f}")
        levels.append(f"exit on a 2-hour close {'below' if side == 1 else 'above'} EMA 105 ({e[i]:,.0f})")
        if r["rsi"]:
            levels.append(f"TOP armed: sell when RSI falls below {r['rsi'] - 5}" if armed else f"TOP when RSI reaches {r['rsi']} and turns down 5")
        state = "BUY NOW" if last[0] == i else "IN TRADE"
        note = f"{'Bought' if side == 1 else 'Sold'} {str(df.index[last[0]])[:16]} at {ent:,.2f} ({gain:+.2f}% now). " + " · ".join(levels) + "."
    elif last and last[1] == i:
        state, note = "EXIT NOW", f"Exit today ({last[3]}): {last[2]:+.2f}% on the trade."
    else:
        all_ok = all(ch["ok"] for ch in checks)
        state = "WAIT"
        note = ("All checks pass but a TOP/target exit was taken: buy again only within 1 ATR of EMA 105 (now "
                f"{X['dist'][i]:.1f} ATR away)." if all_ok else "Not all checks pass: no trade. " +
                "; ".join(ch["name"] for ch in checks if not ch["ok"]) + ".")
    return {"state": state, "note": note, "checks": checks, "close": round(float(c[i]), 2), "ema": round(float(e[i]), 2),
            "rsi": round(float(X["rsi"][i]), 1), "atr": round(float(X["atr"][i]), 1), "bar": str(df.index[i])[:16]}


def build(now=None):
    now = now or dt.datetime.now(N.IST)
    frames = N.load_data(now)
    df = frames["2h"]
    flow, parsed = nifty_flow(str(df.index[0].date()))
    X, L = features(frames, flow)
    n = len(X["c"])
    cuts = [K.WARM + int((n - K.WARM) * k / 3) for k in range(4)]
    thirds = list(zip(cuts[:-1], cuts[1:]))
    rows = grid(X, L, thirds)
    tried = len(rows)
    for r in rows:
        r["label"] = label(r)
        r["tried"] = tried
    robust = sorted([r for r in rows if r["robust"] is not None], key=lambda r: (-r["robust"], -r["all"]["n"]))
    # finalists: best robust overall, best robust buy, best robust sell, and the best of each exit family
    fin, seen = [], set()
    for r in robust[:12]:
        if r["label"] not in seen:
            fin.append(r); seen.add(r["label"])
    jev_meta, jv = jev(fin)
    judged = sum(1 for v in jv.values() if "jev_score" in v)
    for i, r in enumerate(fin):
        r["jev"] = jv.get(i)
        js = (r["jev"] or {}).get("jev_score")
        r["final"] = round(0.7 * r["robust"] * 100 + 0.3 * js, 1) if js is not None and judged >= len(fin) * 0.8 else round(r["robust"] * 100, 1)
    fin.sort(key=lambda r: -r["final"])
    best = fin[0]
    hi = sorted([r for r in rows if (r["all"]["win"] or 0) >= 80], key=lambda r: (-r["all"]["win"], -(r["all"]["pf"] or 0)))
    hi_robust = [r for r in hi if r["every_third"]]
    top_win = sorted([r for r in rows if r["every_third"]], key=lambda r: (-(r["all"]["win"] or 0), -(r["all"]["pf"] or 0)))[:15]

    def full(r):
        ok = np.ones(n, bool)
        for f in r["filters"]:
            ok &= L[f][0] if r["side"] == 1 else L[f][1]
        return simulate(X, ok, r["side"], r["rsi"], r["tp"], r["sl"], r["maxbars"])
    best_tr = full(best)
    base_tr = simulate(X, np.ones(n, bool), 1)
    s1_tr = full({"side": 1, "filters": ["ADX>20", "Supertrend", "Daily>EMA50"], "rsi": 68, "tp": None, "sl": None, "maxbars": None})
    # the 80% setup: highest profit factor among rules with 80%+ wins that made money in every third
    w80 = max(hi_robust, key=lambda r: (r["all"]["pf"] or 0, r["all"]["n"])) if hi_robust else None
    w80_tr = full(w80) if w80 else []
    # the best SELL (short) setup from the same grid: robust ones first, then by the weakest third
    sells = sorted([r for r in rows if r["side"] == -1],
                   key=lambda r: (r["robust"] is None, -(r["robust"] or 0), -min(score_part(p) for p in r["thirds"]), -r["all"]["n"]))
    sell = sells[0] if sells else None
    sell_tr = full(sell) if sell else []
    # last 200 sessions of the winner
    days = pd.Index([str(t.date()) for t in df.index])
    d200 = sorted(set(days))[-200]
    i200 = int(np.argmax(days >= d200))
    pts = lambda tr: round(float(sum(t[2] / 100 * X["c"][t[0]] for t in tr)), 0)
    comp = []
    named = [("EMA 105 alone (buy above, sell below EMA 105)", base_tr),
             ("Setup #1 (EMA 105 + ADX>20 + Supertrend + Daily>EMA50, TOP RSI 68)", s1_tr),
             ("The best setup by the maths (this page)", best_tr)]
    if w80:
        named.append(("The 80% setup (this page)", w80_tr))
    if sell:
        named.append(("The best SELL setup (this page)", sell_tr))
    for nm, tr in named:
        a, l2 = stats(tr), stats([t for t in tr if t[0] >= i200])
        comp.append({"rule": nm, "all": a | {"bayes": bayes(a), "t": t_stat(tr), "points": pts(tr)},
                     "last200": l2 | {"bayes": bayes(l2), "points": pts([t for t in tr if t[0] >= i200])}})
    se = 1 / math.sqrt((df.index[-1] - df.index[K.WARM]).days / 365.25)
    luck = round(se * math.sqrt(2 * math.log(tried)), 2)

    # chart: last CHART_SESSIONS sessions, with BUY / SELL markers for every setup on the page
    uniq = sorted(set(days))
    start = int(np.argmax(days >= uniq[max(0, len(uniq) - CHART_SESSIONS)]))
    tt = [N.chart_time(t, "2h") for t in df.index]
    chart = {"bars": [[tt[i], round(X["o"][i], 2), round(X["h"][i], 2), round(X["l"][i], 2), round(X["c"][i], 2)] for i in range(start, n)],
             "ema": [round(float(X["ema"][i]), 2) for i in range(start, n)], "sets": {}}

    def marks(tr, side):
        out = []
        for eb, xb, net, why in tr:
            if eb >= start:
                out.append([tt[eb], "buy" if side == 1 else "sell", round(float(X["c"][eb]), 2), None, None])
            if xb >= start and why != "open":
                out.append([tt[xb], "sell" if side == 1 else "buy", round(float(X["c"][xb]), 2), round(net, 2), why])
        return out
    chart["sets"]["A"] = marks(best_tr, best["side"])
    if w80:
        chart["sets"]["B"] = marks(w80_tr, w80["side"])
    if sell:
        chart["sets"]["S"] = marks(sell_tr, -1)
    chart["markers"] = chart["sets"]["A"]
    # why 2-hour candles: the single-EMA scan ranked every timeframe (nifty_ema.py -> docs/nifty.json)
    tf_rank = []
    try:
        ema_scan = json.loads((DOCS / "nifty.json").read_text(encoding="utf-8"))
        for r in ema_scan.get("finalists", []):
            if all(x["tf"] != r["tf"] for x in tf_rank):
                m = r.get("main") or {}
                tf_rank.append({"tf": r["tf"], "ema": r["ema"], "final": r.get("final"), "trades": m.get("trades"),
                                "pf": m.get("pf"), "net": m.get("net"), "sessions": m.get("sessions")})
    except (OSError, ValueError, KeyError):
        pass
    slim = lambda r: {k: r[k] for k in ("label", "side", "filters", "rsi", "tp", "sl", "maxbars", "all", "thirds", "every_third", "robust")} | \
        {"bayes": bayes(r["all"]), **({"jev": r.get("jev"), "final": r.get("final")} if "final" in r else {})}
    by_k = []
    for k in range(4):
        rk = [r for r in robust if len(r["filters"]) == k]
        if rk:
            b = max(rk, key=lambda r: (r["all"]["win"], r["all"]["pf"]))
            by_k.append({"confirmations": k, "robust_rules": len(rk), "best_win": b["all"]["win"], "rule": b["label"], "pf": b["all"]["pf"]})
    payload = {
        "version": 1, "name": "Nifty 50 · best setup", "as_of": str(df.index[-1])[:16], "generated_at": now.isoformat(timespec="minutes"),
        "period": {"from": str(df.index[K.WARM])[:10], "to": str(df.index[-1])[:10],
                   "sessions": int(len(set(days[K.WARM:]))), "thirds": [[str(df.index[a])[:10], str(df.index[b - 1])[:10]] for a, b in thirds]},
        "order_flow_from": X["of_from"], "cost_pct": COST * 100, "tried": tried, "robust_count": len(robust),
        "luck_sharpe": luck, "signals": INFO, "exits": EXIT_GRID,
        "best": slim(best) | {"t": t_stat(best_tr), "points": pts(best_tr)},
        "finalists": [slim(r) for r in fin], "robust_top": [slim(r) for r in robust[:25]],
        "win80": {"count": len(hi), "every_third": len(hi_robust), "rules": [slim(r) for r in hi[:25]],
                  "robust_rules": [slim(r) for r in hi_robust[:15]]},
        "setup80": (slim(w80) | {"t": t_stat(w80_tr), "points": pts(w80_tr), "live": live_state(X, L, w80, w80_tr, df),
                                 "trades": [[str(df.index[eb])[:16], round(float(X["c"][eb]), 2), str(df.index[xb])[:16],
                                             round(float(X["c"][xb]), 2), round(net, 3), why] for eb, xb, net, why in w80_tr]}) if w80 else None,
        "sell": (slim(sell) | {"t": t_stat(sell_tr), "points": pts(sell_tr), "live": live_state(X, L, sell, sell_tr, df),
                               "trades": [[str(df.index[eb])[:16], round(float(X["c"][eb]), 2), str(df.index[xb])[:16],
                                           round(float(X["c"][xb]), 2), round(net, 3), why] for eb, xb, net, why in sell_tr]}) if sell else None,
        "timeframes": tf_rank,
        "top_win_robust": [slim(r) for r in top_win], "by_confirmations": by_k, "comparison": comp,
        "live": live_state(X, L, best, best_tr, df),
        "trades": [[str(df.index[eb])[:16], round(float(X["c"][eb]), 2), str(df.index[xb])[:16], round(float(X["c"][xb]), 2), round(net, 3), why]
                   for eb, xb, net, why in best_tr],
        "chart": chart, "jev": jev_meta, "flow_parsed": parsed,
        "limits": [
            f"{tried:,} rules were tried. Even ranked by their weakest third, the winner is partly luck: the best of that many random "
            f"strategies would show a Sharpe of about {luck} by chance.",
            "Index candles, not futures. Entries and exits at the 2-hour close; gaps between candles are included.",
            "Order-flow signals start when the F&O bhavcopy history on disk starts; before that those filters never pass.",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
    }
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for out in (DOCS / "nifty_best.json", PUBLIC / "nifty_best.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    b = payload["best"]["all"]
    print(f"nifty_best.json {payload['as_of']}: {payload['period']['sessions']} sessions | {tried:,} rules tried, {len(robust):,} profitable in every third | "
          f"best: {best['label']} -> n {b['n']} win {b['win']}% PF {b['pf']} net {b['net']}% | 80%+ win rules {len(hi)} "
          f"(every third {len(hi_robust)}) | live {payload['live']['state']} | Jev {jev_meta['status']} | {len(text)//1024}KB")
    return payload


if __name__ == "__main__":
    build()
