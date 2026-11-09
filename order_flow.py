#!/usr/bin/env python3
"""Order Flow - every NSE F&O underlying read from its future, after each close, plus a backtest of the readings.

The maths is ported from MrChartist/order-flow (src/features/market-flow/marketFlowModel.ts, futuresModel.ts,
src/lib/buildUp.ts), Copyright (c) 2026 Mr. Chartist, PolyForm Noncommercial 1.0.0 - see vendor/order-flow/LICENSE.
Like that repo's NSE-archive mode, the source is the exchange's own F&O bhavcopy (end of day, no keys):

  move        near-month future close vs its previous close (%); |move| >= 0.5% -> bullish / bearish, else rangebound
  open int.   all futures months added together (a roll from one month to the next cancels out)
  build-up    price up + OI up = long build-up; down + up = short build-up; up + down = short covering;
              down + down = long unwinding (signs of the two changes, as futuresBuildUp)
  checks      fresh  - positions opened with the move (long build-up for bullish, short build-up for bearish)
              spot   - the underlying's spot moved the same way since the previous close
              hour   - the last hour agrees           -> needs intraday data, not in a bhavcopy: not counted
              options- option writers lean the same way (put OI added > call OI added for bullish, and the reverse)
              sector - its sector leans the same way (>= 3 names, majority rule as the repo)
  conviction  OI % change with the move: opened positions count in full, closing positions at half
  strength    within its side: 0.45 x percentile(move) + 0.35 x percentile(conviction) + 0.20 x share of checks held
  levels      support = heaviest put OI at or below spot, resistance = heaviest call OI at or above spot (nearest expiry)
  zone        needs the intraday OI path, not in a bhavcopy: not shown (the repo rebuilds it; we do not invent it)

Backtest (what the readings were worth): for every session, every reading is traded the next session in the
direction of its side on the future that is still listed tomorrow - close-to-close (hold the night) and
open-to-close (enter at the next open). 0.035% of price is taken off every trade. Results are split into the first
and second half of the sample; "holds up" = profit in both halves.

Output: docs/order_flow.json (+ public/data), data/order_flow/flow_daily.csv.gz (the per-day table, so later runs
only parse new sessions). Paper research, not advice.
"""
import datetime as dt
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import options_desk as od  # noqa: E402  (shared F&O bhavcopy download + cache)

DOCS, PUBLIC = ROOT / "docs", ROOT / "public" / "data"
STORE = ROOT / "data" / "order_flow" / "flow_daily.csv.gz"
HISTORY_DAYS = 460                     # calendar days of bhavcopy kept for the backtest (~300 sessions)
FLOOR_PCT = 0.5                        # FLOOR_DEFAULT.day in marketFlowModel.ts
STRENGTH_W = {"move": 0.45, "conviction": 0.35, "checks": 0.20}
COST = 0.00035
INDEXES = ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50")
CHART_SESSIONS = 60
FEATURED = 3
COLS = ["TradDt", "FinInstrmTp", "TckrSymb", "XpryDt", "StrkPric", "OptnTp", "OpnPric", "HghPric", "LwPric", "ClsPric",
        "SttlmPric", "PrvsClsgPric", "UndrlygPric", "OpnIntrst", "ChngInOpnIntrst", "TtlTradgVol", "NewBrdLotQty"]
# The NIFTY 50 list shipped in order-flow's src/features/market-flow/nifty50.ts (same licence).
NIFTY50 = ["ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV",
           "BEL", "BHARTIARTL", "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL", "GRASIM", "HCLTECH", "HDFCBANK",
           "HDFCLIFE", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDIGO", "INFY", "ITC", "JIOFIN", "JSWSTEEL", "KOTAKBANK",
           "LT", "M&M", "MARUTI", "MAXHEALTH", "NESTLEIND", "NTPC", "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN",
           "SHRIRAMFIN", "SUNPHARMA", "TATACONSUM", "TMPV", "TATASTEEL", "TCS", "TECHM", "TITAN", "TRENT", "ULTRACEMCO",
           "WIPRO"]


# ── one session from the bhavcopy ─────────────────────────────────────────────

def _mark(close, settle):
    return np.where(close > 0, close, settle)


def day_table(day):
    """One row per underlying for one session: futures (near + next month, all-month OI), options OI, levels."""
    with zipfile.ZipFile(od.raw_path(dt.date.fromisoformat(day))) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        f = pd.read_csv(z.open(name), usecols=COLS, low_memory=False)
    dates = pd.to_datetime(f.TradDt).dt.strftime("%Y-%m-%d").unique()
    if len(dates) != 1 or dates[0] != day:
        raise ValueError(f"trade date mismatch in the bhavcopy for {day}")
    f["exp"] = pd.to_datetime(f.XpryDt)
    fut = f[f.FinInstrmTp.isin(["STF", "IDF"])].copy()
    fut["mark"] = _mark(fut.ClsPric, fut.SttlmPric)
    fut = fut.sort_values(["TckrSymb", "exp"])
    g = fut.groupby("TckrSymb")
    first = g.nth(0).set_index("TckrSymb")
    second = g.nth(1).set_index("TckrSymb")
    out = pd.DataFrame(index=first.index)
    out["e0"], out["c0"], out["o0"], out["h0"], out["l0"] = first.exp, first.mark, first.OpnPric, first.HghPric, first.LwPric
    out["p0"] = first.PrvsClsgPric
    out["e1"], out["c1"], out["o1"] = second.exp, second.mark, second.OpnPric
    out["spot"] = first.UndrlygPric
    out["lot"] = first.NewBrdLotQty
    out["oi"] = g.OpnIntrst.sum()
    out["oi_chg"] = g.ChngInOpnIntrst.sum()
    out["fut_vol"] = g.TtlTradgVol.sum()

    opt = f[f.FinInstrmTp.isin(["STO", "IDO"])].join(out[["spot"]], on="TckrSymb")
    live = opt[opt.exp >= pd.Timestamp(day)]
    nearest = live.groupby("TckrSymb").exp.min().rename("near_exp")
    ch = live.join(nearest, on="TckrSymb")
    ch = ch[ch.exp == ch.near_exp]
    pe, ce = ch[ch.OptnTp == "PE"], ch[ch.OptnTp == "CE"]
    out["put_oi"], out["call_oi"] = pe.groupby("TckrSymb").OpnIntrst.sum(), ce.groupby("TckrSymb").OpnIntrst.sum()
    out["put_add"], out["call_add"] = pe.groupby("TckrSymb").ChngInOpnIntrst.sum(), ce.groupby("TckrSymb").ChngInOpnIntrst.sum()

    def heaviest(side, rank):
        s = side[(side.OpnIntrst > 0) & ((side.StrkPric <= side.spot) if side is pe else (side.StrkPric >= side.spot))].copy()
        if s.empty:
            return pd.Series(dtype=float), pd.Series(dtype=float)
        s["d"] = (s.StrkPric - s.spot).abs()
        s = s.sort_values(["TckrSymb", "OpnIntrst", "d"], ascending=[True, False, True])
        pick = s.groupby("TckrSymb").nth(rank).set_index("TckrSymb")
        return pick.StrkPric, pick.OpnIntrst

    out["support"], out["support_oi"] = heaviest(pe, 0)
    out["support2"], _ = heaviest(pe, 1)
    out["resistance"], out["resistance_oi"] = heaviest(ce, 0)
    out["resistance2"], _ = heaviest(ce, 1)
    out["date"] = day
    return out.reset_index().rename(columns={"TckrSymb": "symbol"})


def load_store(days):
    """The per-day table for every session on disk; only sessions not stored yet are parsed."""
    have = pd.DataFrame()
    if STORE.exists():
        have = pd.read_csv(STORE, parse_dates=["e0", "e1"])
    done = set(have.date.unique()) if len(have) else set()
    new = [d for d in days if d not in done]
    parts = [have] if len(have) else []
    for d in new:
        try:
            parts.append(day_table(d))
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as e:
            print(f"warn: {d} skipped ({type(e).__name__}: {e})")
    table = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    table = table[table.date.isin(days)].drop_duplicates(["date", "symbol"], keep="last").sort_values(["date", "symbol"])
    STORE.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(STORE, index=False, compression="gzip")
    return table.reset_index(drop=True), len(new)


# ── readings (the repo's maths) ───────────────────────────────────────────────

def build_up(price_chg, oi_chg):
    """futuresBuildUp: by the signs of the two changes; no change on either side is no build-up."""
    return np.select(
        [(price_chg > 0) & (oi_chg > 0), (price_chg < 0) & (oi_chg > 0), (price_chg > 0) & (oi_chg < 0), (price_chg < 0) & (oi_chg < 0)],
        ["LONG_BUILD", "SHORT_BUILD", "SHORT_COVER", "LONG_UNWIND"], "NEUTRAL")


def pct_rank(values):
    """percentile() in marketFlowModel.ts: share of the list a value sits above, ties sharing a rank; 1 for one item."""
    v = np.asarray(values, float)
    if len(v) <= 1:
        return np.ones(len(v))
    below = (v[None, :] < v[:, None]).sum(1)
    return below / (len(v) - 1)


def readings(T, sectors):
    """Add move, side, build-up, checks, conviction and strength to the per-day table."""
    T = T.sort_values(["symbol", "date"]).copy()
    T["move"] = (T.c0 / T.p0 - 1) * 100
    prev_oi = T.oi - T.oi_chg
    T["oi_pct"] = np.where(prev_oi > 0, T.oi_chg / prev_oi * 100, np.nan)
    T["spot_prev"] = T.groupby("symbol").spot.shift()
    T["spot_move"] = (T.spot / T.spot_prev - 1) * 100
    T["side"] = np.where(T.move.abs() >= FLOOR_PCT, np.where(T.move > 0, "bullish", "bearish"), "rangebound")
    T.loc[T.move.isna(), "side"] = "unread"
    T["buildup"] = build_up(T.c0 - T.p0, T.oi_chg)
    T["sector"] = [sectors.get(s, "Index" if s in INDEXES else "Other") for s in T.symbol]
    T["kind"] = np.where(T.symbol.isin(INDEXES), "index", "stock")
    bull, bear = T.side == "bullish", T.side == "bearish"
    opened = np.where(bull, "LONG_BUILD", np.where(bear, "SHORT_BUILD", ""))
    T["chk_fresh"] = np.where(bull | bear, T.buildup == opened, np.nan)
    sm = np.sign(T.spot_move)
    T["chk_spot"] = np.where((bull | bear) & T.spot_move.notna(), (sm != 0) & ((sm > 0) == bull), np.nan)
    lean = np.where(bull, T.put_add > T.call_add, T.call_add > T.put_add)
    T["chk_options"] = np.where((bull | bear) & T.put_add.notna() & T.call_add.notna(), lean, np.nan)
    # sector lean per day (stocks only, >= 3 names): majority rule from marketFlowModel.ts
    st = T[T.kind == "stock"].groupby(["date", "sector"]).side.agg(
        n="size", b=lambda s: (s == "bullish").sum(), r=lambda s: (s == "bearish").sum(), g=lambda s: (s == "rangebound").sum())
    meas = st.b + st.r + st.g
    st["lean"] = np.where(meas == 0, "mixed", np.where((st.b > st.r) & (st.b * 2 >= meas), "bullish",
                          np.where((st.r > st.b) & (st.r * 2 >= meas), "bearish", np.where(st.g * 2 > meas, "rangebound", "mixed"))))
    st.loc[st.n < 3, "lean"] = None
    T = T.join(st[["lean"]], on=["date", "sector"])
    T["chk_sector"] = np.where((bull | bear) & T.lean.notna() & (T.kind == "stock"), T.lean == T.side, np.nan)
    chk = T[["chk_fresh", "chk_spot", "chk_options", "chk_sector"]].astype(float)
    T["checks_n"] = chk.notna().sum(axis=1)
    T["checks_ok"] = (chk == 1).sum(axis=1)
    T["checks_share"] = np.where(T.checks_n > 0, T.checks_ok / T.checks_n.clip(lower=1), 0.0)
    T["conviction"] = np.where(T.buildup.isin(["LONG_BUILD", "SHORT_BUILD"]), T.oi_pct.clip(lower=0),
                               np.where(T.buildup.isin(["SHORT_COVER", "LONG_UNWIND"]), T.oi_pct.abs() / 2, 0.0))
    T["conviction"] = T.conviction.fillna(0)
    T["strength"] = 0.0
    for (d, s), grp in T[bull | bear].groupby(["date", "side"]):
        T.loc[grp.index, "strength"] = (STRENGTH_W["move"] * pct_rank(grp.move.abs()) + STRENGTH_W["conviction"] *
                                        pct_rank(grp.conviction) + STRENGTH_W["checks"] * grp.checks_share)
    return T.sort_values(["date", "symbol"]).reset_index(drop=True)


# ── next-session results (the backtest) ───────────────────────────────────────

def add_forward(T):
    """Next-session return of the future still listed tomorrow: close-to-close and open-to-close."""
    T = T.sort_values(["symbol", "date"]).copy()
    T["fx_exp"] = np.where(T.e0 > pd.to_datetime(T.date), T.e0, T.e1)
    T["fx_close"] = np.where(T.e0 > pd.to_datetime(T.date), T.c0, T.c1)
    nx = T.groupby("symbol")[["e0", "c0", "o0", "e1", "c1", "o1", "date"]].shift(-1)
    fx = pd.to_datetime(T.fx_exp)
    nc = np.where(nx.e0 == fx, nx.c0, np.where(nx.e1 == fx, nx.c1, np.nan))
    no = np.where(nx.e0 == fx, nx.o0, np.where(nx.e1 == fx, nx.o1, np.nan))
    no = np.where(no > 0, no, np.nan)
    T["next_date"] = nx.date
    T["r_cc"] = (nc / T.fx_close - 1) * 100
    T["r_oc"] = (nc / no - 1) * 100
    return T.sort_values(["date", "symbol"]).reset_index(drop=True)


def trade_stats(r):
    r = np.asarray(r, float)
    r = r[~np.isnan(r)]
    if not len(r):
        return {"n": 0}
    net = r - COST * 100
    w = net > 0
    gl = -net[~w].sum()
    pf = net[w].sum() / gl if gl > 0 else 99.0
    sd = net.std(ddof=1) if len(net) > 1 else np.nan
    t = net.mean() / (sd / np.sqrt(len(net))) if len(net) > 1 and sd > 0 else None
    # Bayesian win rate (quantbot 4.5) with a flat Beta(1,1) prior
    return {"n": int(len(net)), "win": round(float(w.mean() * 100), 1), "win_bayes": round(float((1 + w.sum()) / (2 + len(net)) * 100), 1),
            "avg": round(float(net.mean()), 3), "pf": round(float(min(pf, 99.0)), 2), "sum": round(float(net.sum()), 1),
            "t": round(float(t), 2) if t is not None and np.isfinite(t) else None}


def backtest(T):
    S = T[T.side.isin(["bullish", "bearish"])].copy()
    sign = np.where(S.side == "bullish", 1.0, -1.0)
    S["g_cc"], S["g_oc"] = S.r_cc * sign, S.r_oc * sign
    days = sorted(S.date.unique())
    half = days[len(days) // 2] if days else None
    rules = []

    def add(group, name, mask, what="follow the side"):
        m = np.asarray(mask, bool)
        x = S[m]
        a, b = x[x.date < half], x[x.date >= half]
        row = {"group": group, "rule": name, "what": what,
               "cc": trade_stats(x.g_cc), "oc": trade_stats(x.g_oc),
               "cc_h1": trade_stats(a.g_cc), "cc_h2": trade_stats(b.g_cc),
               "oc_h1": trade_stats(a.g_oc), "oc_h2": trade_stats(b.g_oc)}
        hold = lambda k: (row[f"{k}_h1"].get("avg") or -1) > 0 and (row[f"{k}_h2"].get("avg") or -1) > 0
        row["holds_cc"], row["holds_oc"] = hold("cc"), hold("oc")
        rules.append(row)

    al = np.ones(len(S), bool)
    bull, bear = (S.side == "bullish").to_numpy(), (S.side == "bearish").to_numpy()
    stock = (S.kind == "stock").to_numpy()
    add("1 Every reading", "Every bullish and bearish reading", al)
    add("1 Every reading", "Bullish only (buy)", bull)
    add("1 Every reading", "Bearish only (sell)", bear)
    # a bullish move can only be a long build-up or short covering; a bearish one a short build-up or long unwinding
    for side, sm, bus in (("bullish", bull, ("LONG_BUILD", "SHORT_COVER")), ("bearish", bear, ("SHORT_BUILD", "LONG_UNWIND"))):
        for bu in bus:
            add("2 Side x build-up", f"{side} + {bu.replace('_', ' ').lower()}", sm & (S.buildup == bu).to_numpy())
    for k in range(0, 5):
        add("3 Checks held", f"{k} checks held", (S.checks_ok == k).to_numpy())
    add("3 Checks held", "every measured check held", ((S.checks_ok == S.checks_n) & (S.checks_n >= 3)).to_numpy())
    for c in ("chk_fresh", "chk_spot", "chk_options", "chk_sector"):
        add("4 One check", f"{c[4:]} check holds", (S[c] == 1).to_numpy())
        add("4 One check", f"{c[4:]} check fails", (S[c] == 0).to_numpy())
    rk = S.groupby(["date", "side"]).strength.rank(ascending=False, method="first").to_numpy()
    add("5 Strongest", f"Top {FEATURED} by strength each side (the big cards)", rk <= FEATURED)
    add("5 Strongest", "Strength >= 0.8", (S.strength >= 0.8).to_numpy())
    add("5 Strongest", "Strength <= 0.3", (S.strength <= 0.3).to_numpy())
    mv = S.move.abs().to_numpy()
    add("6 Size of move", "Move 0.5-1.5%", (mv < 1.5))
    add("6 Size of move", "Move 1.5-3%", (mv >= 1.5) & (mv < 3))
    add("6 Size of move", "Move >= 3%", (mv >= 3))
    add("6 Size of move", "Move >= 3% (fade it)", (mv >= 3), what="against the side")
    rules[-1]["cc"] = _flip(S[mv >= 3].g_cc)
    rules[-1]["oc"] = _flip(S[mv >= 3].g_oc)
    x = S[mv >= 3]
    rules[-1]["cc_h1"], rules[-1]["cc_h2"] = _flip(x[x.date < half].g_cc), _flip(x[x.date >= half].g_cc)
    rules[-1]["oc_h1"], rules[-1]["oc_h2"] = _flip(x[x.date < half].g_oc), _flip(x[x.date >= half].g_oc)
    for k in ("cc", "oc"):
        rules[-1][f"holds_{k}"] = (rules[-1][f"{k}_h1"].get("avg") or -1) > 0 and (rules[-1][f"{k}_h2"].get("avg") or -1) > 0
    add("7 Universe", "Nifty 50 stocks only", S.symbol.isin(NIFTY50).to_numpy())
    add("7 Universe", "NIFTY index future only", (S.symbol == "NIFTY").to_numpy())
    add("7 Universe", "Stocks only", stock)
    return rules, {"from": days[0] if days else None, "to": days[-1] if days else None, "half": half, "sessions": len(days)}


def _flip(r):
    r = -np.asarray(r, float)
    return trade_stats(r[~np.isnan(r)] + 0.0)


# ── board for the latest session ──────────────────────────────────────────────

def board(T, meta):
    day = T.date.max()
    D = T[T.date == day].copy()
    rows = []
    for _, r in D.iterrows():
        rows.append({
            "symbol": r.symbol, "name": meta.get(r.symbol, {}).get("name") or r.symbol, "sector": r.sector, "kind": r.kind,
            "n50": r.symbol in NIFTY50 or r.symbol == "NIFTY", "lot": _i(r.lot), "expiry": str(r.e0)[:10],
            "fut": _f(r.c0), "fut_prev": _f(r.p0), "move": _f(r.move, 2), "spot": _f(r.spot), "spot_move": _f(r.spot_move, 2),
            "oi": _i(r.oi), "oi_chg": _i(r.oi_chg), "oi_pct": _f(r.oi_pct, 2), "side": r.side, "buildup": r.buildup,
            "put_oi": _i(r.put_oi), "call_oi": _i(r.call_oi), "put_add": _i(r.put_add), "call_add": _i(r.call_add),
            "pcr": _f(r.put_oi / r.call_oi, 2) if r.call_oi and r.call_oi > 0 else None,
            "support": _f(r.support), "support2": _f(r.support2), "resistance": _f(r.resistance), "resistance2": _f(r.resistance2),
            "checks": {k: (None if pd.isna(r[f"chk_{k}"]) else bool(r[f"chk_{k}"])) for k in ("fresh", "spot", "options", "sector")},
            "checks_ok": int(r.checks_ok), "checks_n": int(r.checks_n), "conviction": _f(r.conviction, 2), "strength": _f(r.strength, 3),
        })
    for side in ("bullish", "bearish"):
        part = sorted([x for x in rows if x["side"] == side], key=lambda x: -abs(x["move"] or 0))
        for i, x in enumerate(part, 1):
            x["rank"] = i
    sectors = []
    for sec, grp in D[D.kind == "stock"].groupby("sector"):
        sectors.append({"sector": sec, "median": _f(grp.move.median(), 2), "n": int(len(grp)),
                        "up": int((grp.side == "bullish").sum()), "down": int((grp.side == "bearish").sum()),
                        "flat": int((grp.side == "rangebound").sum()), "lean": grp.lean.iloc[0] if grp.lean.notna().any() else None})
    sectors.sort(key=lambda s: -(s["median"] or 0))
    return day, rows, sectors


def charts(T, symbols):
    out = {}
    for s in symbols:
        x = T[T.symbol == s].tail(CHART_SESSIONS)
        out[s] = {"d": list(x.date), "o": [_f(v) for v in x.o0], "h": [_f(v) for v in x.h0], "l": [_f(v) for v in x.l0],
                  "c": [_f(v) for v in x.c0], "oi_pct": [_f(v, 2) for v in x.oi_pct], "bu": list(x.buildup),
                  "sup": [_f(v) for v in x.support], "res": [_f(v) for v in x.resistance]}
    return out


def _f(v, d=2):
    return None if v is None or pd.isna(v) or not np.isfinite(float(v)) else round(float(v), d)


def _i(v):
    return None if v is None or pd.isna(v) else int(v)


def meta_map():
    out = {}
    for f in ("hhhl_scan.json", "hhhl_fno.json"):
        try:
            for r in json.loads((DOCS / f).read_text(encoding="utf-8")).get("rows", []):
                out[r["symbol"]] = {"name": r.get("name"), "sector": r.get("sector")}
        except (OSError, ValueError):
            pass
    try:
        fno = json.loads((DOCS / "hhhl_fno.json").read_text(encoding="utf-8"))
        for m in fno["membership"]["members"]:
            out.setdefault(m["symbol"], {"name": m.get("name"), "sector": None})
    except (OSError, ValueError, KeyError):
        pass
    return out


def build(today=None, download=True):
    today = today or dt.date.today()
    start = today - dt.timedelta(days=HISTORY_DAYS)
    stored = []
    if STORE.exists():
        stored = sorted(pd.read_csv(STORE, usecols=["date"]).date.unique())
    # the per-day table is in git; the raw zips are not, so only sessions after the stored ones are downloaded
    fetch_from = max(start, dt.date.fromisoformat(stored[-1]) - dt.timedelta(days=7)) if stored else start
    fetched, missing = od.download(today, start=fetch_from, pause=0.15) if download else ([], [])
    on_disk = [d for d in od.sessions_available(today) if d >= start.isoformat()]
    days = sorted(set(on_disk) | {d for d in stored if d >= start.isoformat()})
    if len(days) < 30:
        raise SystemExit(f"only {len(days)} F&O sessions available")
    T, parsed = load_store(days)
    meta = meta_map()
    sectors = {s: (m.get("sector") or "Other") for s, m in meta.items()}
    T = add_forward(readings(T, sectors))
    rules, span = backtest(T)
    day, rows, sec = board(T, meta)
    D = [r for r in rows]
    counts = {k: sum(1 for r in D if r["side"] == k) for k in ("bullish", "bearish", "rangebound", "unread")}
    bu_counts = {k: sum(1 for r in D if r["buildup"] == k) for k in ("LONG_BUILD", "SHORT_COVER", "SHORT_BUILD", "LONG_UNWIND", "NEUTRAL")}
    holds = [r for r in rules if (r["holds_cc"] or r["holds_oc"]) and min(r["cc"].get("n", 0), r["oc"].get("n", 0)) >= 30]
    payload = {
        "version": 1, "name": "Order Flow", "as_of": day, "generated_at": dt.datetime.now().isoformat(timespec="minutes"),
        "source": "NSE F&O bhavcopy (end of day): BhavCopy_NSE_FO_0_0_0_<date>_F_0000.csv.zip",
        "upstream": {"repo": "https://github.com/MrChartist/order-flow", "licence": "PolyForm Noncommercial 1.0.0",
                     "notice": "Required Notice: Copyright (c) 2026 Mr. Chartist (https://mrchartist.com)",
                     "guide": "https://mrchartist.com/open-source/order-flow"},
        "floor_pct": FLOOR_PCT, "strength_weights": STRENGTH_W, "cost_pct": COST * 100,
        "counts": counts, "buildups": bu_counts, "sectors": sec, "rows": rows,
        "charts": charts(T, [r["symbol"] for r in rows]),
        "backtest": {"span": span, "rules": rules, "holds": [r["rule"] for r in holds]},
        "not_available": [
            "The last-hour check and the open-interest zone need the future's minute-by-minute path; a bhavcopy has only "
            "the day's open, high, low, close and closing OI, so they are left out (not invented).",
            "Live intraday updates need a broker feed; this page is rebuilt after each close.",
        ],
        "limits": [
            f"About {span['sessions']} sessions of NSE F&O bhavcopy ({span['from']} → {span['to']}).",
            "Readings are descriptions of the day, not calls. The backtest shows what following them the next session was worth.",
            "Futures prices and open interest from the exchange file; 0.035% of price is taken off every trade.",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
        "data": {"fetched": len(fetched), "missing": missing[-10:], "parsed": parsed},
    }
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for out in (DOCS / "order_flow.json", PUBLIC / "order_flow.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    ev = rules[0]
    print(f"order_flow.json {day}: {len(rows)} underlyings | {counts} | build-ups {bu_counts} | backtest {span['sessions']} sessions: "
          f"every reading cc win {ev['cc'].get('win')}% avg {ev['cc'].get('avg')}% pf {ev['cc'].get('pf')} | "
          f"rules holding both halves {len(holds)} | parsed {parsed} new | {len(text)//1024}KB")
    return payload


if __name__ == "__main__":
    build()
