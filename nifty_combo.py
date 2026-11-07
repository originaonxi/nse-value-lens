#!/usr/bin/env python3
"""Nifty 50 - EMA 105 (2-hour) + confirmation indicators. Which combination works best?

Base rule (the winner of nifty_ema.py): a 2-hour candle CLOSES above EMA 105 = up, below = down.

Research grid (every combination is recorded in docs/nifty_combo.json):
  ENTRY confirmations (0-3 at once, 11 candidates):
      RSI(14)>50, MACD(12,26,9) histogram, ADX(14)>20, ADX(14)>25, Supertrend(10,3), yesterday's daily close vs
      daily EMA 50, vs daily EMA 200, EMA 105 slope (5 bars), 0.5 ATR buffer beyond the EMA, 2 closes in a row,
      DI+ vs DI-.
  EXITS / TOP signals (16): opposite close only; stretch k*ATR above the EMA; RSI reaches 65-80 then turns down;
      Supertrend flip; ATR trailing stop; ATR profit target; Bollinger %B top then turn.
  Long only, and long + short.
After a TOP exit the rule waits for price to come back to within 1 ATR of EMA 105 (or a fresh cross) before
buying again - "top, then it moves back toward 105".

Honesty rules:
  * Data are split by time: first 2/3 = in-sample (IS), last 1/3 = out-of-sample (OS, never used to pick).
  * A combo is "robust" only if it makes money in BOTH halves; it is ranked by its WEAKER half.
  * Costs: 0.035% of price per trade (~9 Nifty points). Entries/exits at the 2-hour close.
  * Daily trend filter uses YESTERDAY's daily close (no look-ahead).
  * Independent check on 2016-2023 daily candles (data the 2-hour test never saw).
Jev judges the robust finalists. Output: docs/nifty_combo.json (+ public/data). Paper research, not advice.
"""
import itertools
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import nifty_ema as N  # noqa: E402

DOCS, PUBLIC = ROOT / "docs", ROOT / "public" / "data"
TF, EMA_N = "2h", 105
COST = N.COST_PCT
WARM = 3 * EMA_N
RE_ENTRY_ATR = 1.0
IS_FRAC = 2 / 3
EXPORT_SESSIONS = 140

FILTER_INFO = {
    "RSI>50": "RSI(14) above 50 for buys / below 50 for sells",
    "MACD hist": "MACD(12,26,9) histogram above 0 for buys / below 0 for sells",
    "ADX>20": "ADX(14) above 20 - a trend exists",
    "ADX>25": "ADX(14) above 25 - a strong trend exists",
    "Supertrend": "Supertrend(10,3) pointing the same way",
    "Daily>EMA50": "yesterday's daily close above daily EMA 50 for buys / below for sells",
    "Daily>EMA200": "yesterday's daily close above daily EMA 200 for buys / below for sells",
    "EMA slope": "EMA 105 higher than 5 bars ago for buys / lower for sells",
    "0.5 ATR buffer": "close at least 0.5 ATR beyond EMA 105",
    "2 closes": "two 2-hour closes in a row on the same side",
    "DI+>DI-": "DI+ above DI- for buys / DI- above DI+ for sells",
}
EXITS = ([("cross", None)] + [("stretch", p) for p in (3, 4, 5, 6)] + [("rsi", p) for p in (65, 68, 70, 72, 75, 80)]
         + [("st", None)] + [("trail", p) for p in (2, 3, 4)] + [("tp", p) for p in (2, 3, 4)] + [("bb", 0.8)])
EXIT_INFO = {
    "cross": "only the opposite close through EMA 105",
    "stretch": "TOP when the close is k ATR beyond EMA 105",
    "rsi": "TOP when RSI(14) reaches the level and then falls 5 points",
    "st": "Supertrend(10,3) flips",
    "trail": "trailing stop k ATR from the best close",
    "tp": "profit target k ATR from entry",
    "bb": "TOP when Bollinger %B goes above 1 then back below 0.8",
}


# ── indicators ────────────────────────────────────────────────────────────────

def wilder(x, n):
    return pd.Series(x, dtype=float).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def supertrend(h, l, c, tr, n=10, mult=3.0):
    a = wilder(tr, n)
    hl2 = (h + l) / 2
    ub, lb = hl2 + mult * a, hl2 - mult * a
    fu, fl, st = ub.copy(), lb.copy(), np.ones(len(c))
    for i in range(1, len(c)):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        st[i] = 1 if c[i] > fu[i - 1] else (-1 if c[i] < fl[i - 1] else st[i - 1])
    return st


def rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up, dn = wilder(np.clip(d, 0, None), n), wilder(np.clip(-d, 0, None), n)
    return 100 - 100 / (1 + up / np.where(dn == 0, 1e-9, dn))


def indicators(df, ema_n=EMA_N, daily=None):
    o, h, l, c = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    e = N.ema(c, ema_n)
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    atr = wilder(tr, 14)
    m = N.ema(c, 12) - N.ema(c, 26)
    upm, dnm = h - np.r_[h[0], h[:-1]], np.r_[l[0], l[:-1]] - l
    pdm = np.where((upm > dnm) & (upm > 0), upm, 0.0)
    ndm = np.where((dnm > upm) & (dnm > 0), dnm, 0.0)
    pdi, ndi = 100 * wilder(pdm, 14) / atr, 100 * wilder(ndm, 14) / atr
    dx = 100 * abs(pdi - ndi) / np.where(pdi + ndi == 0, 1e-9, pdi + ndi)
    s20 = pd.Series(c).rolling(20)
    mid, sd = s20.mean().to_numpy(), s20.std(ddof=0).to_numpy()
    X = {"o": o, "h": h, "l": l, "c": c, "ema": e, "atr": atr, "rsi": rsi(c), "macdh": m - N.ema(m, 9),
         "adx": wilder(dx, 14), "pdi": pdi, "ndi": ndi, "st": supertrend(h, l, c, tr),
         "bbp": (c - (mid - 2 * sd)) / np.where(sd == 0, 1e-9, 4 * sd),
         "slope": (e - np.r_[np.full(5, np.nan), e[:-5]]) / atr, "dist": (c - e) / atr, "date": df.index,
         "d50": np.zeros(len(c)), "d200": np.zeros(len(c))}
    if daily is not None:
        dc = daily["Close"].astype(float)
        ref = pd.DataFrame({"a50": np.sign(dc - N.ema(dc.to_numpy(), 50)), "a200": np.sign(dc - N.ema(dc.to_numpy(), 200))},
                           index=pd.to_datetime(dc.index).date).shift(1)       # yesterday's daily close only
        dates = pd.Index(df.index.date)
        X["d50"] = ref["a50"].reindex(dates).ffill().fillna(0).to_numpy()
        X["d200"] = ref["a200"].reindex(dates).ffill().fillna(0).to_numpy()
    return X


def filters(X):
    c, e, d = X["c"], X["ema"], X["dist"]
    above, below = c > e, c < e
    return {
        "RSI>50": (X["rsi"] > 50, X["rsi"] < 50),
        "MACD hist": (X["macdh"] > 0, X["macdh"] < 0),
        "ADX>20": (X["adx"] > 20, X["adx"] > 20),
        "ADX>25": (X["adx"] > 25, X["adx"] > 25),
        "Supertrend": (X["st"] == 1, X["st"] == -1),
        "Daily>EMA50": (X["d50"] == 1, X["d50"] == -1),
        "Daily>EMA200": (X["d200"] == 1, X["d200"] == -1),
        "EMA slope": (X["slope"] > 0, X["slope"] < 0),
        "0.5 ATR buffer": (d > 0.5, d < -0.5),
        "2 closes": (above & np.r_[False, above[:-1]], below & np.r_[False, below[:-1]]),
        "DI+>DI-": (X["pdi"] > X["ndi"], X["ndi"] > X["pdi"]),
    }


# ── simulation ────────────────────────────────────────────────────────────────

def simulate(X, lok, sok, exit_kind="cross", p=None, shorts=True, start=WARM, end=None, re_dist=RE_ENTRY_ATR):
    """Bar-by-bar at 2-hour closes. Returns trades (entry_bar, exit_bar, dir, net_points, reason)."""
    c, atr, r, st, d, bbp = X["c"], X["atr"], X["rsi"], X["st"], X["dist"], X["bbp"]
    n = len(c) if end is None else end
    side = np.sign(c - X["ema"])
    pos, ep, eb, best, blocked, armed = 0, 0.0, 0, 0.0, 0, False
    trades = []
    for i in range(start, n):
        if pos:
            why = None
            if side[i] == -pos:
                why = "cross"
            elif exit_kind == "stretch" and pos * d[i] >= p:
                why = "top"
            elif exit_kind == "rsi":
                if (pos == 1 and r[i] >= p) or (pos == -1 and r[i] <= 100 - p):
                    armed = True
                if armed and ((pos == 1 and r[i] < p - 5) or (pos == -1 and r[i] > 105 - p)):
                    why = "top"
            elif exit_kind == "st" and st[i] == -pos:
                why = "st"
            elif exit_kind == "trail":
                best = max(best, c[i]) if pos == 1 else min(best, c[i])
                if pos * (best - c[i]) >= p * atr[i]:
                    why = "trail"
            elif exit_kind == "tp" and pos * (c[i] - ep) >= p * atr[eb]:
                why = "target"
            elif exit_kind == "bb":
                if (pos == 1 and bbp[i] >= 1) or (pos == -1 and bbp[i] <= 0):
                    armed = True
                if armed and ((pos == 1 and bbp[i] < p) or (pos == -1 and bbp[i] > 1 - p)):
                    why = "top"
            if why:
                trades.append((eb, i, pos, pos * (c[i] - ep) - COST * ep, why))
                blocked = pos if why != "cross" else 0
                pos, armed = 0, False
        if not pos:
            if blocked and (side[i] != blocked or abs(d[i]) <= re_dist):
                blocked = 0
            want = 0
            if side[i] == 1 and lok[i] and blocked != 1:
                want = 1
            elif shorts and side[i] == -1 and sok[i] and blocked != -1:
                want = -1
            if want:
                pos, ep, eb, best, armed = want, c[i], i, c[i], False
    if pos:
        trades.append((eb, n - 1, pos, pos * (c[n - 1] - ep) - COST * ep, "open"))
    return trades


def stats(tr):
    if not tr:
        return {"n": 0, "win": None, "pf": None, "net": 0.0, "dd": 0.0, "avg": None, "long_net": 0.0, "short_net": 0.0}
    net = np.array([t[3] for t in tr])
    w = net > 0
    gl = -net[~w].sum()
    pf = net[w].sum() / gl if gl > 0 else 99.0
    eq = np.r_[0.0, np.cumsum(net)]
    return {"n": int(len(net)), "win": round(float(w.mean() * 100), 1), "pf": round(float(min(pf, 99.0)), 2),
            "net": round(float(net.sum()), 1), "dd": round(float((np.maximum.accumulate(eq) - eq).max()), 1),
            "avg": round(float(net.mean()), 1),
            "long_net": round(float(sum(t[3] for t in tr if t[2] == 1)), 1),
            "short_net": round(float(sum(t[3] for t in tr if t[2] == -1)), 1)}


def half_score(s):
    if not s["n"] or s["pf"] is None:
        return 0.0
    return (min(s["pf"], 5) / 5 * 0.35 + s["win"] / 100 * 0.35
            + min(max(s["net"], 0) / max(s["dd"], 200), 6) / 6 * 0.30)


def run_grid(X, split):
    F = filters(X)
    T = np.ones(len(X["c"]), bool)
    names = list(F)
    combos = [()] + [cb for k in (1, 2, 3) for cb in itertools.combinations(names, k)
                     if not {"ADX>20", "ADX>25"} <= set(cb) and not {"Daily>EMA50", "Daily>EMA200"} <= set(cb)]
    rows = []
    for cb in combos:
        lok, sok = T.copy(), T.copy()
        for f in cb:
            lok &= F[f][0]
            sok &= F[f][1]
        for ek, p in EXITS:
            for shorts in (False, True):
                tr = simulate(X, lok, sok, ek, p, shorts)
                a = stats([t for t in tr if t[0] < split])
                b = stats([t for t in tr if t[0] >= split])
                row = {"filters": list(cb), "exit": ek, "p": p, "shorts": shorts,
                       "is": a, "os": b, "all": stats(tr)}
                ok = a["n"] >= 12 and b["n"] >= 6 and (a["pf"] or 0) > 1 and (b["pf"] or 0) > 1
                row["robust"] = round(min(half_score(a), half_score(b)), 4) if ok else None
                rows.append(row)
    return rows, F


def label(r):
    ex = r["exit"] + ("" if r["p"] is None else f" {r['p']}")
    return ("EMA 105" + "".join(" + " + f for f in r["filters"]) + " | exit: " + ex
            + (" | long+short" if r["shorts"] else " | long only"))


# ── extra facts ───────────────────────────────────────────────────────────────

def sensitivity(X, split, extra="Supertrend"):
    F = filters(X)
    T = np.ones(len(X["c"]), bool)
    out = []
    for a in (15, 18, 20, 22, 25, 30):
        for lvl in (65, 68, 70, 72, 75, 80):
            lok = (X["adx"] > a) & (X["d50"] == 1) & F[extra][0]
            tr = simulate(X, lok, T, "rsi", lvl, False)
            s, o = stats(tr), stats([t for t in tr if t[0] >= split])
            out.append({"adx": a, "rsi_top": lvl, "n": s["n"], "win": s["win"], "pf": s["pf"], "net": s["net"],
                        "os_n": o["n"], "os_win": o["win"], "os_pf": o["pf"]})
    return out


def top_reversion(X, trades):
    c, e, atr = X["c"], X["ema"], X["atr"]
    out = []
    for t in trades:
        if t[4] != "top":
            continue
        i = t[1]
        j = min(len(c) - 1, i + 10)
        low = c[i:j + 1].min()
        out.append({"date": str(X["date"][i])[:16], "close": round(float(c[i]), 2),
                    "atr_above_ema": round(float((c[i] - e[i]) / atr[i]), 1),
                    "drop_10bars": round(float(c[i] - low), 1), "drop_atr": round(float((c[i] - low) / atr[i]), 1),
                    "pct_back_to_ema": round(float((c[i] - low) / max(1.0, c[i] - e[i]) * 100), 0)})
    n = len(out)
    return {"tops": out, "n": n,
            "fell_1atr_pct": round(sum(o["drop_atr"] >= 1 for o in out) / n * 100, 1) if n else None,
            "reached_ema_pct": round(sum(o["pct_back_to_ema"] >= 100 for o in out) / n * 100, 1) if n else None,
            "median_pct_back": float(np.median([o["pct_back_to_ema"] for o in out])) if n else None}


def daily_check(daily, end_date):
    """Independent period: daily candles before the 2-hour data starts. EMA 26 daily ≈ EMA 105 on 2-hour bars."""
    XD = indicators(daily, 26)
    XD["d50"] = np.sign(XD["c"] - N.ema(XD["c"], 250))
    cut = int(np.searchsorted(pd.to_datetime(daily.index), pd.Timestamp(end_date)))
    T = np.ones(len(XD["c"]), bool)
    lok = (XD["adx"] > 20) & (XD["d50"] == 1) & (XD["st"] == 1)
    base = stats(simulate(XD, T, T, "cross", None, False, start=260, end=cut))
    combo = stats(simulate(XD, lok, T, "rsi", 70, False, start=260, end=cut))
    combo_x = stats(simulate(XD, lok, T, "cross", None, False, start=260, end=cut))
    return {"from": str(daily.index[260])[:10], "to": str(daily.index[cut - 1])[:10],
            "note": "Daily EMA 26 (≈ 2-hour EMA 105), trend gate = daily EMA 250, long only.",
            "ema_only": base, "combo_rsi_top": combo, "combo_cross_exit": combo_x}


# ── Jev ───────────────────────────────────────────────────────────────────────

JEV_QUESTIONS = {
    "reliability": {"type": "choice", "instructions": (
        "A rule trades the NIFTY 50 index on 2-hour candles: buy on a close above EMA 105 only when the listed "
        "confirmation indicators agree, and leave on the listed exit. Using ONLY these numbers (in-sample, unseen "
        "out-of-sample last third, full period, trades, win rate, profit factor, net points after costs, drawdown, "
        "and an independent 2016-2023 daily check), how reliable is it going forward? Penalise few trades, a big "
        "gap between in-sample and out-of-sample, and too many conditions."),
        "criteria": {"weak": None, "fair": None, "good": None, "strong": None}},
    "overfit": {"type": "choice", "instructions": (
        "How likely is it that this rule's results come from fitting the past rather than a real edge?"),
        "criteria": {"low": None, "medium": None, "high": None}},
}
REL_W = {"weak": 0.0, "fair": 1 / 3, "good": 2 / 3, "strong": 1.0}
OVF_W = {"low": 1.0, "medium": 0.5, "high": 0.0}


def jev_judge(finalists, daily_fact):
    try:
        from jev_client import Client, MODEL
        client = Client()
    except Exception as e:  # pragma: no cover - network/credential path
        return {"status": f"unavailable: {e}", "model": None}, {}

    def one(r):
        state = {"rule": label(r), "in_sample": r["is"], "out_of_sample_unseen": r["os"], "full": r["all"],
                 "independent_daily_2016_2023_same_family": daily_fact, "cost_pct_per_trade": COST * 100}
        try:
            a = client.ask(state, JEV_QUESTIONS)
            rel, ovf = a["reliability"], a["overfit"]
            s = 100 * (0.6 * sum(REL_W[k] * v for k, v in rel["probabilities"].items())
                       + 0.4 * sum(OVF_W[k] * v for k, v in ovf["probabilities"].items()))
            return r["id"], {"reliability": rel["choice"], "overfit": ovf["choice"], "jev_score": round(s, 1)}
        except Exception as e:  # pragma: no cover
            return r["id"], {"error": type(e).__name__ + ": " + str(e)[:80]}

    with ThreadPoolExecutor(max_workers=4) as pool:
        res = dict(pool.map(one, finalists))
    ok = sum(1 for v in res.values() if "jev_score" in v)
    return {"status": f"judged {ok}/{len(finalists)}", "model": MODEL}, res


# ── build ─────────────────────────────────────────────────────────────────────

def winner_mask(X, F, w):
    m = np.ones(len(X["c"]), bool)
    s = np.ones(len(X["c"]), bool)
    for f in w["filters"]:
        m &= F[f][0]
        s &= F[f][1]
    return m, s


def build(now=None, frames=None):
    now = now or datetime.now(N.IST)
    frames = frames or N.load_data(now)
    df, daily = frames[TF], frames["1D"]
    X = indicators(df, EMA_N, daily)
    n = len(X["c"])
    split = WARM + int((n - WARM) * IS_FRAC)
    rows, F = run_grid(X, split)
    for i, r in enumerate(rows):
        r["id"] = i
        r["label"] = label(r)
    robust = sorted([r for r in rows if r["robust"] is not None], key=lambda r: -r["robust"])
    base = next(r for r in rows if not r["filters"] and r["exit"] == "cross" and not r["shorts"])
    base_ls = next(r for r in rows if not r["filters"] and r["exit"] == "cross" and r["shorts"])

    daily_fact = daily_check(daily, str(df.index[0])[:10])
    finalists = robust[:6]
    jev_meta, jev = jev_judge(finalists, daily_fact)
    judged = sum(1 for v in jev.values() if "jev_score" in v)
    for r in finalists:
        r["jev"] = jev.get(r["id"])
        js = (r["jev"] or {}).get("jev_score")
        r["final"] = round(0.6 * r["robust"] * 100 + 0.4 * js, 1) if judged >= 4 and js is not None else round(r["robust"] * 100, 1)
    finalists.sort(key=lambda r: -r["final"])
    win = finalists[0]

    # highest in-sample win rate, to show what happens out-of-sample (the 80% trap)
    elig = [r for r in rows if r["is"]["n"] >= 12 and r["os"]["n"] >= 6]
    trap = sorted(elig, key=lambda r: (-(r["is"]["win"] or 0), -(r["is"]["pf"] or 0)))[:8]

    # shorts on their own
    short_rows = []
    T = np.ones(n, bool)
    for cb in [()] + [tuple(x) for x in (["Supertrend", "0.5 ATR buffer", "2 closes"], ["MACD hist", "0.5 ATR buffer", "2 closes"],
                                         ["Daily>EMA200", "Supertrend"], ["ADX>20", "Daily>EMA50", "Supertrend"])]:
        sok = T.copy()
        for f in cb:
            sok &= F[f][1]
        for ek, p in (("cross", None), ("rsi", 70), ("tp", 3)):
            tr = [t for t in simulate(X, np.zeros(n, bool), sok, ek, p, True) if t[2] == -1]
            short_rows.append({"label": "SELL below EMA 105" + "".join(" + " + f for f in cb) + f" | exit: {ek}{'' if p is None else ' ' + str(p)}",
                               "is": stats([t for t in tr if t[0] < split]), "os": stats([t for t in tr if t[0] >= split]),
                               "all": stats(tr)})

    lok, sok = winner_mask(X, F, win)
    trades = simulate(X, lok, sok, win["exit"], win["p"], win["shorts"])
    rev = top_reversion(X, trades)
    sens = sensitivity(X, split, next((f for f in win["filters"] if f in ("Supertrend", "RSI>50", "DI+>DI-")), "Supertrend"))

    # chart export (last 140 sessions)
    uniq, sidx = N.sessions_of(df)
    first = max(0, len(uniq) - EXPORT_SESSIONS)
    start = int(np.argmax(sidx >= first))
    tt = [N.chart_time(t, TF) for t in df.index]
    bars = [[tt[i], round(X["o"][i], 2), round(X["h"][i], 2), round(X["l"][i], 2), round(X["c"][i], 2)] for i in range(start, n)]
    emav = [round(float(X["ema"][i]), 2) for i in range(start, n)]
    marks = []
    for eb, xb, dr, pts, why in trades:
        if eb >= start:
            marks.append([tt[eb], "buy" if dr == 1 else "sell", round(X["c"][eb], 2), None])
        if xb >= start and why != "open":
            marks.append([tt[xb], why, round(X["c"][xb], 2), round(pts, 1)])
    trade_list = [[str(df.index[eb])[:16], dr, round(X["c"][eb], 2), str(df.index[xb])[:16], round(X["c"][xb], 2),
                   round(pts, 1), why] for eb, xb, dr, pts, why in trades]

    i = n - 1
    in_trade = bool(trades and trades[-1][4] == "open")
    checks = [{"name": "Close vs EMA 105", "ok": bool(X["c"][i] > X["ema"][i]),
               "value": f"{X['c'][i]:,.2f} vs {X['ema'][i]:,.2f}"}]
    for f in win["filters"]:
        val = {"ADX>20": f"ADX {X['adx'][i]:.1f}", "ADX>25": f"ADX {X['adx'][i]:.1f}", "RSI>50": f"RSI {X['rsi'][i]:.1f}",
               "Supertrend": "up" if X["st"][i] == 1 else "down", "Daily>EMA50": "above" if X["d50"][i] == 1 else "below",
               "Daily>EMA200": "above" if X["d200"][i] == 1 else "below", "MACD hist": f"{X['macdh'][i]:.1f}",
               "EMA slope": f"{X['slope'][i]:.2f} ATR", "0.5 ATR buffer": f"{X['dist'][i]:.1f} ATR",
               "2 closes": "yes" if F[f][0][i] else "no", "DI+>DI-": f"{X['pdi'][i]:.1f} / {X['ndi'][i]:.1f}"}[f]
        checks.append({"name": FILTER_INFO[f], "ok": bool(F[f][0][i]), "value": val})
    rsi_now, dist_now = float(X["rsi"][i]), float(X["dist"][i])
    if in_trade:
        state = "HOLD BUY"
        armed = bool(win["exit"] == "rsi" and (X["rsi"][trades[-1][0]:i + 1] >= win["p"]).any())
        note = (f"Bought {str(df.index[trades[-1][0]])[:16]} at {X['c'][trades[-1][0]]:,.2f}. "
                + (f"RSI has touched {win['p']}: TOP exit when RSI falls below {win['p'] - 5}." if armed else
                   f"TOP exit after RSI reaches {win['p']} and falls 5 points; stop = close below EMA 105 ({X['ema'][i]:,.0f})."))
    else:
        all_ok = all(ch["ok"] for ch in checks)
        state = "BUY" if all_ok else "WAIT"
        note = ("All confirmations agree at this close." if all_ok else
                "Not all confirmations agree: no new buy. After a TOP, the rule waits until price is within "
                f"{RE_ENTRY_ATR:g} ATR of EMA 105 (now {dist_now:.1f} ATR away).")

    payload = {
        "version": 1, "name": "Nifty 50 - EMA 105 + confirmations", "tf": TF, "ema": EMA_N,
        "as_of": str(df.index[-1])[:16], "generated_at": now.isoformat(timespec="minutes"),
        "period": {"from": str(df.index[WARM])[:10], "to": str(df.index[-1])[:10], "bars": n - WARM,
                   "split": str(df.index[split])[:10]},
        "cost_pct": COST * 100, "tested": len(rows), "robust_count": len(robust),
        "filters": FILTER_INFO, "exits": EXIT_INFO,
        "base": {"long_only": base, "long_short": base_ls},
        "winner": win, "finalists": finalists, "top_robust": robust[:25], "trap": trap,
        "short_side": short_rows, "sensitivity": sens, "top_reversion": rev, "daily_check": daily_fact,
        "now": {"state": state, "note": note, "checks": checks, "rsi": round(rsi_now, 1), "atr_from_ema": round(dist_now, 1),
                "close": round(float(X["c"][i]), 2), "ema": round(float(X["ema"][i]), 2)},
        "chart": {"bars": bars, "ema": emav, "markers": marks},
        "trades": trade_list, "jev": jev_meta,
        "limits": [
            "The winner is chosen from 2,000+ tested combinations; even with an unseen out-of-sample third, some luck remains.",
            "2-hour data start Nov 2023 (about 3 years). The out-of-sample third holds only about 10 trades.",
            "Index candles, not futures. Costs 0.035% of price per trade. Gaps between 2-hour bars are included.",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
    }
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for out in (DOCS / "nifty_combo.json", PUBLIC / "nifty_combo.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    b, w = base["all"], win["all"]
    print(f"nifty_combo.json {payload['as_of']}: {len(rows)} combos, {len(robust)} robust | base win {b['win']}% PF {b['pf']} "
          f"net {b['net']} | winner: {win['label']} -> win {w['win']}% PF {w['pf']} net {w['net']} dd {w['dd']} "
          f"(OS win {win['os']['win']}% PF {win['os']['pf']}) | now {state} | Jev {jev_meta['status']} | {len(text)//1024}KB")
    return payload


if __name__ == "__main__":
    build()
