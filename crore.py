#!/usr/bin/env python3
"""₹1 crore test · Nifty 50 · 2-hour candles · every combination, real lots, every trade in rupees.

Two windows: ₹1 crore put in two years ago, and ₹1 crore put in 200 sessions ago.

Rules searched (all permutations): EMA 105 as the base (buy on a 2-hour close above, short on a close below), plus
0 to 4 of 12 confirmations (ADX, Supertrend, daily EMA 50/200, EMA slope, RSI, MACD, DI, NIFTY futures build-up,
option writers, put-call ratio, opening gap), times 180 exit settings (RSI top, ATR target, ATR stop, time limit),
buy side and sell side.

Money (the same for everything):
  - ₹1,00,00,000 split equally into sleeves. A sleeve trades whole NIFTY futures lots at the 2-hour close of the index:
    lots = floor(sleeve cash ÷ (price × lot size)), lot size from the NSE F&O bhavcopy of the entry day. No leverage.
  - P&L = side × lots × lot size × (exit − entry) − 0.035% of the position. Gains stay in the sleeve (compounding).
  - A buy rule and a sell rule can share ONE sleeve: a buy is held only while price is above EMA 105 and a sell only
    while it is below, so they are never open at the same time. The same cash works both ways.
  - Every session is valued at its last 2-hour close.

Portfolios: every set of 1 to 5 sleeves from the best non-overlapping rules is tried with exact rupees; the most money
and the best money-per-drawdown are reported. Picking after seeing the data flatters, so two honest tests pick on the
earlier part only: year 1 -> traded in year 2, and the sessions before the last 200 -> traded in the last 200.

Run: python crore.py  -> docs/crore.json
"""
import itertools
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import nifty_best as B  # noqa: E402
import nifty_ema as N  # noqa: E402
import nifty_ema105_audit as A  # noqa: E402

DOCS, PUBLIC = ROOT / "docs", ROOT / "public" / "data"
CAPITAL = 1_00_00_000
YEARS, LAST = 2, 200
COST = N.COST_PCT
TAX = 0.312               # F&O profit is business income: 30% slab + 4% cess
DEPTH = 4                 # up to 4 confirmations on top of EMA 105
MIN_TRADES = {"2y": 15, "200": 6}
MIN_TRAIN = 8
OVERLAP = 0.5             # two picked rules may share at most half of their time in the market
N_LONG, N_SHORT, N_PAIR, MAX_K = 10, 8, 10, 5
EXITS = list(itertools.product(*B.EXIT_GRID.values()))
_G = {}


# ── the search, in parallel ───────────────────────────────────────────────────

def mask_of(L, filters, side, n):
    ok = np.ones(n, bool)
    for f in filters:
        ok &= L[f][0] if side == 1 else L[f][1]
    return ok


def growth(rets):
    return float(np.prod(1 + np.asarray(rets, float) / 100)) if len(rets) else 1.0


def trade_dd(rets):
    eq = np.cumprod(np.r_[1.0, 1 + np.asarray(rets, float) / 100])
    pk = np.maximum.accumulate(eq)
    return float(((pk - eq) / pk).max() * 100)


def _init(X, L):
    _G["X"], _G["L"] = X, L


def _job(args):
    side, cb, (w0, w1, w200, w2m) = args
    X, L = _G["X"], _G["L"]
    ok = mask_of(L, cb, side, len(X["c"]))
    if ok[w0:].sum() < 30:
        return []
    out = []
    for ei, (rsi, tp, sl, mb) in enumerate(EXITS):
        tr = B.simulate(X, ok, side, rsi, tp, sl, mb, start=w0)
        closed = [t for t in tr if t[3] != "open"]
        if len(closed) < MIN_TRADES["200"]:
            continue
        r = [t[2] for t in tr]
        sel = lambda f: [t[2] for t in tr if f(t)]
        out.append((side, cb, ei, len(closed), sum(t[2] > 0 for t in closed), growth(r), trade_dd(r),
                    growth(sel(lambda t: t[3] != "open" and t[1] < w1)), sum(1 for t in closed if t[1] < w1),
                    growth(sel(lambda t: t[0] >= w1)),
                    growth(sel(lambda t: t[3] != "open" and t[1] < w200)), sum(1 for t in closed if t[1] < w200),
                    growth(sel(lambda t: t[0] >= w200)), sum(1 for t in tr if t[0] >= w200),
                    growth(sel(lambda t: w200 <= t[0] < w2m)), growth(sel(lambda t: t[0] >= w2m))))
    return out


FIELDS = ("side", "filters", "ex", "n", "wins", "g", "dd", "gY1", "nY1", "gY2", "gPre", "nPre", "gL", "nL", "gLa", "gLb")


def search(X, L, cuts):
    names = list(L)
    combos = [()] + [cb for k in range(1, DEPTH + 1) for cb in itertools.combinations(names, k)]
    jobs = [(side, cb, cuts) for side in (1, -1) for cb in combos]
    rows = []
    with ProcessPoolExecutor(max_workers=os.cpu_count() or 2, initializer=_init, initargs=(X, L)) as pool:
        for res in pool.map(_job, jobs, chunksize=4):
            for t in res:
                r = dict(zip(FIELDS, t))
                r["filters"] = list(r["filters"])
                r["rsi"], r["tp"], r["sl"], r["maxbars"] = EXITS[r["ex"]]
                rows.append(r)
    return rows, len(jobs) * len(EXITS)


# ── trades -> rupees ──────────────────────────────────────────────────────────

def lot_sizes(days):
    """NIFTY lot size per session from the NSE F&O bhavcopy (via the audit's official table). Gaps take the last known size."""
    off = A.official(list(days))
    got = off["lot"].to_dict() if "lot" in off else {}
    out, last = {}, None
    for d in sorted(days):
        v = got.get(d)
        last = int(v) if v == v and v else last
        out[d] = last
    first = next((v for v in out.values() if v), 75)
    return {d: (v or first) for d, v in out.items()}


def trades_of(X, L, r, start):
    tr = B.simulate(X, mask_of(L, r["filters"], r["side"], len(X["c"])), r["side"], r["rsi"], r["tp"], r["sl"], r["maxbars"], start=start)
    return [(eb, xb, r["side"], why) for eb, xb, _, why in tr]


def ema_alone(X, start, buy_only):
    flips, ends, dirs, _, _, closed = N.rule_trades(X["c"], 105, start, COST)
    return [(int(f), int(x), int(d), "ema" if cl else "open") for f, x, d, cl in zip(flips, ends, dirs, closed)
            if not (buy_only and d < 0)]


def in_market(n, trades, start):
    m = np.zeros(n, np.int8)
    for eb, xb, sd, _ in trades:
        m[eb:xb] = sd
    return m[start:]


def overlap(a, b):
    any_ = ((a != 0) | (b != 0)).sum()
    return ((a != 0) & (a == b)).sum() / any_ if any_ else 0.0


def run_money(X, df, trades, capital, lots, start, name):
    """Whole lots, no leverage, gains stay in the sleeve. Returns trade rows and the sleeve value on every bar."""
    c = X["c"]
    n = len(c)
    cash = float(capital)
    value = np.full(n, np.nan)
    value[start:] = cash
    rows, last_x = [], -1
    for eb, xb, sd, why in sorted(trades):
        if eb < last_x:
            raise ValueError(f"{name}: trades overlap inside one sleeve")
        last_x = xb
        day = df["session"].iloc[eb]
        lot = int(lots[day])
        P, Q = float(c[eb]), float(c[xb])
        q = int(cash // (P * lot))
        side = "BUY" if sd > 0 else "SELL"
        if q == 0:
            rows.append({"strategy": name, "side": side, "entry_time": str(df.index[eb])[:16], "entry": round(P, 2),
                         "skipped": f"₹{cash:,.0f} is less than one lot (₹{P * lot:,.0f})"})
            continue
        notional = q * lot * P
        cost = COST * notional
        pnl = sd * q * lot * (Q - P) - cost
        value[eb:xb] = cash - cost + sd * q * lot * (c[eb:xb] - P)
        cash += pnl
        value[xb:] = cash
        rows.append({"strategy": name, "side": side, "entry_time": str(df.index[eb])[:16], "entry": round(P, 2),
                     "exit_time": str(df.index[xb])[:16], "exit": round(Q, 2), "lots": q, "lot_size": lot, "qty": q * lot,
                     "notional": round(notional), "cost": round(cost), "points": round(sd * (Q - P), 2), "pnl": round(pnl),
                     "sleeve_after": round(cash), "why": why, "open": why == "open"})
    return rows, value


def daily(df, value, start):
    return pd.Series(value[start:], index=df.index[start:]).groupby(df["session"].iloc[start:].to_numpy()).last()


def summary(name, kind, sleeves, df, start, capital, note=""):
    total = sum(v for _, v, _ in sleeves)
    d = daily(df, total, start)
    end = float(d.iloc[-1])
    peak = d.cummax()
    ddp = (peak - d) / peak
    i = int(ddp.to_numpy().argmax())
    days = (pd.Timestamp(d.index[-1]) - pd.Timestamp(d.index[0])).days
    trades = [t for _, _, rows in sleeves for t in rows if "pnl" in t]
    closed = [t for t in trades if not t["open"]]
    profit = end - capital
    return {"name": name, "kind": kind, "note": note, "start": capital, "end": round(end), "profit": round(profit),
            "return_pct": round(profit / capital * 100, 2),
            "cagr_pct": round(((end / capital) ** (365.25 / days) - 1) * 100, 2) if days > 0 and end > 0 else None,
            "max_dd": round(float((peak - d).max())), "max_dd_pct": round(float(ddp.max() * 100), 2), "dd_day": str(d.index[i]),
            "trades": len(closed), "open": len(trades) - len(closed),
            "wins": sum(1 for t in closed if t["pnl"] > 0), "losses": sum(1 for t in closed if t["pnl"] <= 0),
            "win_pct": round(sum(1 for t in closed if t["pnl"] > 0) / len(closed) * 100, 1) if closed else None,
            "won": round(sum(t["pnl"] for t in closed if t["pnl"] > 0)), "lost": round(sum(t["pnl"] for t in closed if t["pnl"] <= 0)),
            "costs": round(sum(t["cost"] for t in trades)), "open_pnl": round(sum(t["pnl"] for t in trades if t["open"])),
            "skipped": sum(1 for _, _, rows in sleeves for t in rows if "skipped" in t),
            "after_tax_profit": round(profit * (1 - TAX)) if profit > 0 else round(profit),
            "curve": [[k, round(float(v))] for k, v in d.items()],
            "sleeves": [{"strategy": nm, "start": round(capital / len(sleeves)), "end": round(float(v[-1])),
                         "profit": round(float(v[-1]) - capital / len(sleeves)),
                         "trades": sum(1 for t in rows if "pnl" in t and not t["open"]),
                         "wins": sum(1 for t in rows if "pnl" in t and not t["open"] and t["pnl"] > 0),
                         "skipped": sum(1 for t in rows if "skipped" in t)} for nm, v, rows in sleeves]}


def portfolio(name, kind, X, df, units, start, lots, note=""):
    """units: list of (name, trades). ₹1 crore split equally."""
    cap = CAPITAL / len(units)
    sleeves, rows = [], []
    for nm, tr in units:
        r, v = run_money(X, df, tr, cap, lots, start, nm)
        sleeves.append((nm, v, r)); rows += r
    s = summary(name, kind, sleeves, df, start, CAPITAL, note)
    s["trade_rows"] = sorted(rows, key=lambda t: t["entry_time"])
    return s


def benchmark(X, df, start, name="Nifty 50 bought and held"):
    v = np.full(len(X["c"]), np.nan)
    v[start:] = CAPITAL * X["c"][start:] / X["c"][start]
    return summary(name, "benchmark", [("Nifty 50 index", v, [])], df, start, CAPITAL,
                   "₹1 crore in the index on day one, never sold. No dividends, no costs.")


# ── units, combinations ───────────────────────────────────────────────────────

def label(r):
    return B.label(r)


def rkey(r):
    return (r["side"], tuple(r["filters"]), r["ex"])


def pick_rules(X, L, cands, key, k, start, end=None):
    """Best by `key`, skipping rules whose time in the market overlaps a picked one by more than OVERLAP."""
    out, masks = [], []
    n = len(X["c"])
    for r in sorted(cands, key=lambda r: -r[key]):
        m = in_market(n, trades_of(X, L, r, start), start)
        m = m[:end - start] if end else m
        if all(overlap(m, q) <= OVERLAP for q in masks):
            out.append(r); masks.append(m)
            if len(out) == k:
                break
    return out


def units_of(X, L, longs, shorts, key, start):
    U = [{"name": label(r), "kind": "buy", "rules": [r], "parts": {rkey(r)}, "trades": trades_of(X, L, r, start)} for r in longs]
    U += [{"name": label(r), "kind": "sell", "rules": [r], "parts": {rkey(r)}, "trades": trades_of(X, L, r, start)} for r in shorts]
    pairs = sorted(((a, b) for a in longs for b in shorts), key=lambda p: -(p[0][key] * p[1][key]))[:N_PAIR]
    U += [{"name": "BUY + SELL in one sleeve: " + label(a) + "  ‖  " + label(b), "kind": "pair", "rules": [a, b],
           "parts": {rkey(a), rkey(b)}, "trades": trades_of(X, L, a, start) + trades_of(X, L, b, start)} for a, b in pairs]
    return U


def combinations(X, df, U, start, lots):
    """Exact rupees for every set of 1..MAX_K units (no rule used twice). ₹1 crore split equally."""
    days = None
    curves = {}
    for k in range(1, MAX_K + 1):
        cs = []
        for u in U:
            _, v = run_money(X, df, u["trades"], CAPITAL / k, lots, start, u["name"])
            d = daily(df, v, start)
            days = list(d.index)
            cs.append(d.to_numpy(float))
        curves[k] = np.array(cs)
    out, tried = [], 0
    for k in range(1, min(MAX_K, len(U)) + 1):
        idx = np.array([s for s in itertools.combinations(range(len(U)), k)
                        if sum(len(U[i]["parts"]) for i in s) == len(set().union(*(U[i]["parts"] for i in s)))])
        if not len(idx):
            continue
        tried += len(idx)
        ends, dds = [], []
        for b in range(0, len(idx), 4000):
            V = curves[k][idx[b:b + 4000]].sum(axis=1)
            pk = np.maximum.accumulate(V, axis=1)
            ends.append(V[:, -1]); dds.append(((pk - V) / pk).max(axis=1))
        ends, dds = np.concatenate(ends), np.concatenate(dds)
        ret = (ends / CAPITAL - 1) * 100
        calmar = np.where(dds > 0, ret / (dds * 100), 0)
        for order, by in ((np.argsort(-ends)[:3], "money"), (np.argsort(-calmar)[:3], "money per drawdown")):
            for j in order:
                out.append({"k": k, "by": by, "units": [int(i) for i in idx[j]], "names": [U[i]["name"] for i in idx[j]],
                            "end": round(float(ends[j])), "return_pct": round(float(ret[j]), 2),
                            "max_dd_pct": round(float(dds[j] * 100), 2), "ret_per_dd": round(float(calmar[j]), 2)})
    return out, tried, days


# ── one window ────────────────────────────────────────────────────────────────

def window(X, L, df, rows, lots, start, wkey, both, nkey, minn, title, setups):
    cands = [r for r in rows if r[nkey] >= minn and all(r[k] > 1 for k in both)]
    longs = pick_rules(X, L, [r for r in cands if r["side"] == 1], wkey, N_LONG, start)
    shorts = pick_rules(X, L, [r for r in cands if r["side"] == -1], wkey, N_SHORT, start)
    U = units_of(X, L, longs, shorts, wkey, start)
    combos, tried, _ = combinations(X, df, U, start, lots)
    money = [c for c in combos if c["by"] == "money"]
    best_money = max(money, key=lambda c: c["end"])
    best_rd = max((c for c in combos if c["by"] == "money per drawdown"), key=lambda c: c["ret_per_dd"])
    kmax = max(c["k"] for c in money)
    best5 = max((c for c in money if c["k"] == kmax), key=lambda c: c["end"])
    P = [benchmark(X, df, start),
         portfolio("EMA 105 alone · buy only", "ema", X, df, [("EMA 105 · buy above, exit below", ema_alone(X, start, True))], start, lots,
                   "Buy on a 2-hour close above EMA 105, sell on a close below. In cash while below."),
         portfolio("EMA 105 alone · buy and sell", "ema", X, df, [("EMA 105 · long above, short below", ema_alone(X, start, False))], start, lots,
                   "Always in the market: long above EMA 105, short below.")]
    for nm, r in setups:
        P.append(portfolio(f"{nm} · ₹1 crore", "setup", X, df, [(label(r), trades_of(X, L, r, start))], start, lots, f"{nm} from the homepage."))
    for c, nm, note in ((best_money, "Most money", "The single sleeve or set of sleeves that ended with the most money."),
                        (best_rd, "Best money per drawdown", "The set with the highest return ÷ worst fall."),
                        (best5, f"Best {best5['k']} sleeves", "The best set of the most sleeves ₹1 crore can fund without leverage.")):
        P.append(portfolio(f"{nm} · {c['k']} sleeve{'s' if c['k'] > 1 else ''}", "best", X, df,
                           [(U[i]["name"], U[i]["trades"]) for i in c["units"]], start, lots, note))
    slim = lambda r: {"rule": label(r), "side": "BUY" if r["side"] == 1 else "SELL", "trades": r["n"],
                      "win": round(r["wins"] / r["n"] * 100, 1) if r["n"] else None, "growth": round(r[wkey], 4),
                      "return_pct": round((r[wkey] - 1) * 100, 2)}
    return {"title": title, "from": str(df["session"].iloc[start]), "to": str(df["session"].iloc[-1]),
            "sessions": int(df["session"].iloc[start:].nunique()), "candidates": len(cands), "sets_tried": tried,
            "longs": [slim(r) for r in longs], "shorts": [slim(r) for r in shorts],
            "units": [{"name": u["name"], "kind": u["kind"]} for u in U], "combos": combos, "portfolios": P}


def honest(X, L, df, rows, lots, train_key, train_n, train_start, test_start, title, setups_note):
    """Pick only from the earlier part, then trade the later part with ₹1 crore."""
    cands = [r for r in rows if r[train_n] >= MIN_TRAIN and r[train_key] > 1]
    longs = pick_rules(X, L, [r for r in cands if r["side"] == 1], train_key, 5, train_start, test_start)
    shorts = pick_rules(X, L, [r for r in cands if r["side"] == -1], train_key, 5, train_start, test_start)
    P = [benchmark(X, df, test_start),
         portfolio("EMA 105 alone · buy only", "ema", X, df, [("EMA 105 · buy above, exit below", ema_alone(X, test_start, True))], test_start, lots)]
    if longs:
        P.append(portfolio("Best BUY rule from the earlier part", "honest", X, df, [(label(longs[0]), trades_of(X, L, longs[0], test_start))],
                           test_start, lots))
    if longs and shorts:
        a, b = longs[0], shorts[0]
        P.append(portfolio("Best BUY + best SELL in one sleeve", "honest", X, df,
                           [("BUY + SELL: " + label(a) + "  ‖  " + label(b), trades_of(X, L, a, test_start) + trades_of(X, L, b, test_start))],
                           test_start, lots))
    top = sorted(longs + shorts, key=lambda r: -r[train_key])[:MAX_K]
    if top:
        P.append(portfolio(f"Top {len(top)} from the earlier part", "honest", X, df,
                           [(label(r), trades_of(X, L, r, test_start)) for r in top], test_start, lots))
    return {"title": title, "test_from": str(df["session"].iloc[test_start]), "picked_on": setups_note,
            "picked": [{"rule": label(r), "train_trades": r[train_n], "train_return_pct": round((r[train_key] - 1) * 100, 2)} for r in top],
            "portfolios": P}


# ── Jev ───────────────────────────────────────────────────────────────────────

JEV_Q = {
    "overfit": {"type": "choice", "criteria": {"low": None, "medium": None, "high": None}, "instructions": (
        "This is a Nifty 50 futures strategy result over the stated window, chosen from tens of thousands of rule "
        "combinations. Given the number of trades, the worst fall, how it did when picked on earlier data only "
        "(honest test) and how many rules were tried, how likely is it that the money shown is luck from fitting the past?")},
    "real_money": {"type": "choice", "criteria": {"paper only": None, "small size": None, "full size": None}, "instructions": (
        "Would a careful risk manager put real money behind this, judged only on these numbers?")},
}


def jev_review(items):
    try:
        from jev_client import Client, MODEL
        client = Client()
    except Exception as e:  # pragma: no cover - needs the key
        return {"status": f"unavailable: {e}", "model": None, "answers": {}}

    def one(kv):
        name, state = kv
        try:
            a = client.ask(state, JEV_Q)
            return name, {k: {"choice": v["choice"], "conf": round(v["confidence"] * 100)} for k, v in a.items()}
        except Exception as e:  # pragma: no cover - network
            return name, {"error": type(e).__name__}
    with ThreadPoolExecutor(max_workers=3) as pool:
        ans = dict(pool.map(one, items.items()))
    ok = sum(1 for v in ans.values() if "error" not in v)
    return {"status": f"judged {ok}/{len(items)}", "model": MODEL, "answers": ans}


def state_of(p, tried, honest_line):
    keep = ("name", "return_pct", "cagr_pct", "max_dd_pct", "trades", "wins", "losses", "win_pct", "skipped")
    return {k: p[k] for k in keep} | {"rules_tried": tried, "honest_test": honest_line, "sleeves": [s["strategy"] for s in p["sleeves"]]}


# ── build ─────────────────────────────────────────────────────────────────────

def build(now=None):
    now = now or datetime.now(N.IST)
    frames = N.load_data(now)
    df = frames["2h"]
    flow, _ = B.nifty_flow(str(df.index[0].date()))
    X, L = B.features(frames, flow)
    sess = df["session"].to_numpy()
    first = (now.date() - timedelta(days=365 * YEARS + 1)).isoformat()
    w0 = int(np.argmax(sess >= first))
    uniq = sorted(set(sess[w0:]))
    w1 = int(np.argmax(sess >= uniq[len(uniq) // 2]))
    w200 = int(np.argmax(sess >= uniq[-LAST]))
    w2m = int(np.argmax(sess >= uniq[-LAST // 2]))
    lots = lot_sizes(uniq)
    print(f"2 years {uniq[0]} -> {uniq[-1]} ({len(uniq)} sessions) | year 2 from {sess[w1]} | last 200 from {sess[w200]} | "
          f"lot sizes {sorted(set(lots.values()))}", flush=True)
    t = datetime.now()
    rows, tried = search(X, L, (w0, w1, w200, w2m))
    print(f"searched {tried:,} rules ({len(rows):,} with enough trades) in {(datetime.now() - t).seconds}s", flush=True)

    setups = []
    try:
        nb = json.loads((DOCS / "nifty_best.json").read_text(encoding="utf-8"))
        setups = [(nm, nb[k]) for k, nm in (("best", "Setup A"), ("setup80", "Setup B"), ("sell", "Setup C")) if nb.get(k)]
    except (OSError, ValueError):
        pass
    W2 = window(X, L, df, rows, lots, w0, "g", ("gY1", "gY2"), "n", MIN_TRADES["2y"], f"₹1 crore put in {YEARS} years ago", setups)
    W200 = window(X, L, df, rows, lots, w200, "gL", ("gLa", "gLb"), "nL", MIN_TRADES["200"], f"₹1 crore put in {LAST} sessions ago", setups)
    H1 = honest(X, L, df, rows, lots, "gY1", "nY1", w0, w1, "Picked on year 1, traded in year 2", f"{uniq[0]} -> {sess[w1 - 1]}")
    H2 = honest(X, L, df, rows, lots, "gPre", "nPre", w0, w200, f"Picked before the last {LAST} sessions, traded in them",
                f"{uniq[0]} -> {sess[w200 - 1]}")

    def hl(H):
        b = H["portfolios"][0]["return_pct"]
        return "; ".join(f"{p['name']}: {p['return_pct']:+.1f}% (Nifty held {b:+.1f}%)" for p in H["portfolios"][2:])
    review = {}
    for W, H in ((W2, H1), (W200, H2)):
        for p in W["portfolios"]:
            if p["kind"] in ("best", "setup"):
                review[f"{W['title']} · {p['name']}"] = state_of(p, tried, hl(H))
    jev = jev_review(review)

    payload = {
        "version": 1, "name": "₹1 crore test · Nifty 50 · 2-hour candles", "generated_at": now.isoformat(timespec="minutes"),
        "capital": CAPITAL, "cost_pct": COST * 100, "tax_pct": round(TAX * 100, 1), "lot_sizes": sorted(set(int(v) for v in lots.values())),
        "rules_tried": tried, "rules_with_trades": len(rows), "signals": list(L), "depth": DEPTH, "exit_settings": len(EXITS),
        "windows": {"2y": W2, "200": W200}, "honest": [H1, H2], "jev": jev,
        "money_rules": [
            "₹1,00,00,000 on the first session of the window, split equally between the sleeves.",
            "Each trade = whole NIFTY futures lots at the 2-hour close of the Nifty 50 index: lots = sleeve cash ÷ (price × lot size), "
            "lot size from the NSE F&O bhavcopy of the entry day. No leverage: the full value of the position is covered by cash.",
            f"Cost {COST * 100:.3f}% of the position on every trade. Gains and losses stay in the sleeve, so it compounds.",
            "A BUY rule and a SELL rule can share one sleeve: a buy is only open above EMA 105 and a sell only below, so they never overlap.",
            "Every session is valued at its last 2-hour close; a trade still open is valued at the latest close.",
            f"After-tax profit assumes F&O income taxed at 30% + 4% cess ({TAX * 100:.1f}%).",
        ],
        "limits": [
            "Most money / best sets were chosen after seeing the same data they are scored on. The honest tests are the fairer guide.",
            "One NIFTY lot is worth ₹15-19 lakh, so ₹1 crore funds at most 5-6 sleeves without leverage; smaller sleeves skip trades.",
            "Fills at the index's 2-hour close. Real futures trade at a premium to the index and orders slip; idle cash earns nothing here.",
            "Index candles from Yahoo Finance, checked against the NSE bhavcopies (see the audit).",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
    }
    try:
        au = json.loads((DOCS / "nifty_ema105_audit.json").read_text(encoding="utf-8"))
        au.pop("trades", None)
        payload["audit"] = au
    except (OSError, ValueError):
        payload["audit"] = None
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for out in (DOCS / "crore.json", PUBLIC / "crore.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    for W in (W2, W200):
        print(f"\n== {W['title']}: {W['from']} -> {W['to']} ({W['sessions']} sessions), {W['candidates']} candidate rules, {W['sets_tried']:,} sets")
        for p in W["portfolios"]:
            print(f"  {p['name']:<44} ₹{p['end']:>13,}  {p['return_pct']:+8.1f}%  DD {p['max_dd_pct']:5.1f}%  trades {p['trades']:>3} "
                  f"win {p['win_pct']}  skipped {p['skipped']}")
    for H in (H1, H2):
        print(f"\n== honest: {H['title']} (test from {H['test_from']})")
        for p in H["portfolios"]:
            print(f"  {p['name']:<44} ₹{p['end']:>13,}  {p['return_pct']:+8.1f}%  DD {p['max_dd_pct']:5.1f}%  trades {p['trades']:>3}")
    print(f"\nJev {jev['status']} | crore.json {len(text) // 1024}KB")
    return payload


if __name__ == "__main__":
    build()
