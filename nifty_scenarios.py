"""Nifty 50 scenario engine: the best BULL, BEAR and SIDEWAYS option trades from LIVE data.

1. Trend analysis (HH/HL style): live Kotak price + 5 years of daily bars -> EMA 9/21, SMA 20/50/200,
   RSI 14, ATR 14, 20-day typical-price average, previous-day high/low/close, today's range,
   confirmed swing high/low, live option-chain OI walls, PCR and max pain, live ATM IV.
2. Triggers and exits per scenario come from those levels (reclaim / breakdown / range).
3. Scenario probabilities for the planned exit date, from four independent sources:
   options market (live IV, lognormal), Kronos (paths incl. today's live bar), historical analogs
   (Nifty days in the same trend state, forward returns) and Jev (live typed judgment). Blended equally.
   Bull = Nifty more than +1% above live price at exit, bear = more than -1% below, sideways = between.
4. Every defined-risk structure on the live chain (bid/ask fills) is valued at the exit date with
   Black-Scholes at each leg's own live implied vol. Best per scenario = highest average P&L over a
   1-2% move in that direction (wider if the implied 1-sigma move is larger) per rupee of max loss.
   Cards are ranked by probability-weighted P&L per rupee of max loss.

Research output from live quotes and models. Not investment advice.
"""
import datetime as dt
import json
import math
import os
import pathlib
import sys
import time

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import kotak_live as kl  # noqa: E402
import nifty_chain as nc  # noqa: E402

od = nc.od
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
NSEI_CSV = ROOT / "data" / "hhhl_prices" / "NSEI.csv"
JEV_CACHE = ROOT / ".cache" / "jev_scenario.json"
JEV_MAX_AGE = 20 * 60
BAND = 0.01                     # sideways = within +/-1% at the exit date
MOVES = [-0.02, -0.015, -0.01, -0.005, 0.0, 0.005, 0.01, 0.015, 0.02]
SPAN = 0.04                     # strikes within +/-4% of spot are priced live
MIN_OI = 50_000                 # open interest (units) below this = illiquid, skipped
MAX_SPREAD = 0.12               # bid/ask wider than 12% of mid -> fill at LTP, flagged
WIDTHS = range(100, 701, 50)
GRID = np.round(np.arange(-0.06, 0.06001, 0.001), 4)     # exit-date move grid
SCEN = ("bull", "side", "bear")
CENTER = {"bull": 0.015, "side": 0.0, "bear": -0.015}


# ── small helpers ───────────────────────────────────────────────────────────
def _px(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x > 0 else None


def rnd(v, d=2):
    return None if v is None or not np.isfinite(v) else round(float(v), d)


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def implied_vol(price, s, k, t, call):
    if not (price and t > 0):
        return None
    intrinsic = max(s - k, 0.0) if call else max(k - s, 0.0)
    if price <= intrinsic + 0.05:
        return None
    lo, hi = 0.01, 2.0
    for _ in range(70):
        mid = (lo + hi) / 2
        if float(nc._bs_price(s, k, t, mid, call)) > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def leg_cost(px, side):
    return float(od.leg_costs(np.array(px), np.array(side), np.array("index")))


# ── 1. trend analysis ───────────────────────────────────────────────────────
def daily_bars(live, today):
    """Official daily bars before today + today's provisional live bar (Kotak O/H/L/LTP)."""
    df = pd.read_csv(NSEI_CSV, index_col=0, parse_dates=True)
    df.columns = [c.strip().capitalize() for c in df.columns]
    df = df[["Open", "High", "Low", "Close"]].dropna().sort_index()
    df = df[df.index.normalize() < pd.Timestamp(today)]
    last_completed = df.index[-1].date().isoformat()
    o, h, l, c = (live.get(k) for k in ("open", "high", "low", "ltp"))
    if all(_px(v) for v in (o, h, l, c)):
        df.loc[pd.Timestamp(today)] = [o, max(h, o, c), min(l, o, c), c]
    return df, last_completed


def indicators(df):
    c, h, l = df["Close"], df["High"], df["Low"]
    prev = c.shift(1)
    tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    return dict(ema9=c.ewm(span=9, adjust=False).mean(), ema21=c.ewm(span=21, adjust=False).mean(),
                sma20=c.rolling(20).mean(), sma50=c.rolling(50).mean(), sma200=c.rolling(200).mean(),
                atr14=tr.ewm(alpha=1 / 14, adjust=False).mean(), rsi14=100 - 100 / (1 + up / dn),
                tp20=((h + l + c) / 3).rolling(20).mean())


def chain_stats(q, spot):
    ce = {k: v["oi"] for (k, t), v in q.items() if t == "CE" and v.get("oi")}
    pe = {k: v["oi"] for (k, t), v in q.items() if t == "PE" and v.get("oi")}
    if not ce or not pe:
        return {}
    above = {k: o for k, o in ce.items() if k >= spot}
    below = {k: o for k, o in pe.items() if k <= spot}
    strikes = sorted(set(ce) | set(pe))
    pain = {K: sum(o * max(K - k, 0) for k, o in ce.items()) + sum(o * max(k - K, 0) for k, o in pe.items()) for K in strikes}
    return dict(pcr=rnd(sum(pe.values()) / sum(ce.values()), 3),
                call_wall=max(above, key=above.get) if above else None,
                put_wall=max(below, key=below.get) if below else None,
                max_pain=min(pain, key=pain.get), strikes=f"{strikes[0]:.0f}-{strikes[-1]:.0f}")


def analyse(df, ind, chain, live, q, spot, iv, h_days, dte):
    i = -1
    val = {k: float(s.iloc[i]) for k, s in ind.items() if pd.notna(s.iloc[i])}
    prev = df.iloc[-2]
    st = chain["index"].get("structure") or {}
    hi_c, lo_c = st.get("confirmed_high"), st.get("confirmed_low")
    oi = chain_stats(q, spot)
    eod = next((e for e in chain.get("expiries", []) if e.get("trade_expiry")), {})
    sig_h, sig_e = iv * math.sqrt(h_days / 365), iv * math.sqrt(dte / 365)
    votes = []

    def vote(name, ok_bull, ok_bear, value, detail=""):
        side = "bull" if ok_bull else "bear" if ok_bear else "neutral"
        votes.append(dict(name=name, side=side, value=value, detail=detail))

    for key, label in (("ema9", "EMA 9"), ("ema21", "EMA 21"), ("sma20", "SMA 20"), ("sma50", "SMA 50"), ("sma200", "SMA 200")):
        if key in val:
            vote(f"Price vs {label}", spot > val[key], spot < val[key], f"{spot - val[key]:+,.0f} pts", f"{label} {val[key]:,.0f}")
    if "ema9" in val and "ema21" in val:
        vote("EMA 9 vs EMA 21", val["ema9"] > val["ema21"], val["ema9"] < val["ema21"], f"{val['ema9'] - val['ema21']:+,.0f} pts", "short-term momentum")
    if "rsi14" in val:
        vote("RSI 14", val["rsi14"] > 55, val["rsi14"] < 45, f"{val['rsi14']:.1f}", ">55 bull, <45 bear")
    pc = live.get("close")
    vote("Today vs previous close", pc and spot > pc * 1.0025, pc and spot < pc * 0.9975,
         f"{(spot / pc - 1) * 100:+.2f}%" if pc else "—", f"previous close {pc:,.2f}" if pc else "")
    vote("Previous-day range", spot > prev["High"], spot < prev["Low"],
         "above high" if spot > prev["High"] else "below low" if spot < prev["Low"] else "inside",
         f"PDH {prev['High']:,.0f} / PDL {prev['Low']:,.0f}")
    s_lbl = st.get("structure") or ""
    vote("Swing structure (HH/HL)", s_lbl.startswith("HH") and s_lbl.endswith("HL"), s_lbl.startswith("LH") and s_lbl.endswith("LL"),
         s_lbl or "—", f"confirmed high {hi_c:,.0f} / low {lo_c:,.0f}" if hi_c and lo_c else "")
    if hi_c and lo_c:
        vote("Price vs confirmed swing levels", spot > hi_c, spot < lo_c,
             "above swing high" if spot > hi_c else "below swing low" if spot < lo_c else "between",
             "HH/HL breakout above, structural exit below")
    bull = sum(v["side"] == "bull" for v in votes)
    bear = sum(v["side"] == "bear" for v in votes)
    label = "BULLISH" if bull - bear >= 3 else "BEARISH" if bear - bull >= 3 else "SIDEWAYS / MIXED"

    def lvl(name, v, kind=""):
        return dict(name=name, value=rnd(v), dist_pct=rnd((v / spot - 1) * 100, 2) if v else None, kind=kind) if v else None

    levels = [x for x in [
        lvl("Live price (Kotak)", spot, "live"), lvl("Today open", live.get("open")), lvl("Today high", live.get("high")),
        lvl("Today low", live.get("low")), lvl("Previous close", pc), lvl("Previous high (PDH)", prev["High"]),
        lvl("Previous low (PDL)", prev["Low"]), lvl("EMA 9", val.get("ema9")), lvl("EMA 21", val.get("ema21")),
        lvl("SMA 20", val.get("sma20")), lvl("SMA 50", val.get("sma50")), lvl("SMA 200", val.get("sma200")),
        lvl("20-day typical-price avg (VWAP proxy)", val.get("tp20")), lvl("Confirmed swing high", hi_c, "structure"),
        lvl("Confirmed swing low", lo_c, "structure"), lvl("Call OI wall (live)", oi.get("call_wall"), "oi"),
        lvl("Put OI wall (live)", oi.get("put_wall"), "oi"), lvl("Max pain (live, near strikes)", oi.get("max_pain"), "oi"),
    ] if x]
    stats = dict(rsi14=rnd(val.get("rsi14"), 1), atr14=rnd(val.get("atr14"), 0),
                 atr_pct=rnd(val.get("atr14", 0) / spot * 100, 2), live_atm_iv=rnd(iv * 100, 2),
                 eod_atm_iv=chain["index"].get("atm_iv"), vix_eod=chain["index"].get("vix"),
                 iv_percentile=chain["index"].get("iv_pct"), pcr_live=oi.get("pcr"), pcr_eod=eod.get("pcr"),
                 max_pain_eod=eod.get("max_pain"), buildup_eod=chain["index"].get("buildup"),
                 move_1sigma_exit_pts=rnd(spot * sig_h, 0), move_1sigma_exit_pct=rnd(sig_h * 100, 2),
                 move_1sigma_expiry_pts=rnd(spot * sig_e, 0), oi_strikes=oi.get("strikes"))
    return dict(label=label, bull=bull, bear=bear, neutral=len(votes) - bull - bear, votes=votes,
                levels=levels, stats=stats, values=val, prev=dict(high=float(prev["High"]), low=float(prev["Low"]), close=pc),
                structure=dict(label=s_lbl, high=hi_c, low=lo_c), oi=oi)


def triggers(a, live, spot):
    """HH/HL-style entry triggers and Nifty invalidation levels for each scenario."""
    v, s, oi, p = a["values"], a["structure"], a["oi"], a["prev"]
    ema9, tp20 = v.get("ema9", spot), v.get("tp20", spot)
    t_low, t_high = live.get("low") or spot, live.get("high") or spot
    bull_lvl = max(ema9, tp20)
    bull_confirm = s["high"] if s.get("high") and s["high"] > bull_lvl else p["high"]
    bull_stop = max(x for x in (t_low, s.get("low") or 0) if x < spot) if any(x < spot for x in (t_low, s.get("low") or 0)) else spot * 0.99
    bear_lvl = min(ema9, tp20, p["low"])
    bear_confirm = s.get("low") or t_low
    bear_stop = max(ema9, tp20)
    lo = max(x for x in (s.get("low"), oi.get("put_wall"), spot * 0.985) if x)
    hi = min(x for x in (s.get("high"), oi.get("call_wall"), spot * 1.015) if x)
    if not lo < spot < hi:
        lo, hi = spot * 0.99, spot * 1.01
    return {
        "bull": dict(active=spot > bull_lvl, level=rnd(bull_lvl, 0), confirm=rnd(bull_confirm, 0), stop=rnd(bull_stop, 0),
                     text=f"Enter when Nifty holds above {bull_lvl:,.0f} (reclaims EMA 9 and the 20-day average); "
                          f"HH/HL confirmation above {bull_confirm:,.0f}.",
                     exit=f"Exit if Nifty closes below {bull_stop:,.0f} (today's low / confirmed swing low)."),
        "bear": dict(active=spot < bear_lvl, level=rnd(bear_lvl, 0), confirm=rnd(bear_confirm, 0), stop=rnd(bear_stop, 0),
                     text=f"Active while Nifty stays below {bear_lvl:,.0f} (EMA 9 / 20-day average / previous low); "
                          f"structural breakdown below {bear_confirm:,.0f}.",
                     exit=f"Exit if Nifty reclaims {bear_stop:,.0f} (back above EMA 9 and the 20-day average)."),
        "side": dict(active=lo < spot < hi, level=None, range=[rnd(lo, 0), rnd(hi, 0)], stop=None,
                     text=f"Range trade while Nifty holds {lo:,.0f}-{hi:,.0f} (swing low / put wall to swing high / call wall).",
                     exit=f"Exit if Nifty closes outside {lo:,.0f}-{hi:,.0f}."),
    }


# ── 2. scenario probabilities ───────────────────────────────────────────────
def bucket(moves):
    m = np.asarray(moves, dtype=float)
    n = len(m)
    if not n:
        return None
    bull, bear = int((m > BAND).sum()), int((m < -BAND).sum())
    return dict(bull=bull / n, side=(n - bull - bear) / n, bear=bear / n, n=n)


def implied_probs(sigma, h_days):
    t = h_days / 365
    s, mu = sigma * math.sqrt(t), (od.RATE - 0.5 * sigma ** 2) * t
    up = 1 - ncdf((math.log(1 + BAND) - mu) / s)
    dn = ncdf((math.log(1 - BAND) - mu) / s)
    return dict(bull=up, side=1 - up - dn, bear=dn, note=f"lognormal at live ATM IV {sigma * 100:.1f}%")


def kronos_probs(kentry, exit_iso):
    if not kentry:
        return None
    ends = [b["c"] for p in kentry["paths"] for b in p if b["d"] == exit_iso]
    r = bucket([e / kentry["last_close"] - 1 for e in ends])
    if r:
        live = bool(kentry.get("live_bar"))
        r.update(note=f"{r['n']} NeoQuasar/Kronos-small paths, input {kentry['data_as_of']}"
                      + (" incl. today's live bar" if live else " (EOD)"), live=live)
    return r


def history_probs(df, ind, sessions):
    c = df["Close"]
    feats = pd.DataFrame({"above EMA 9": c > ind["ema9"], "above SMA 50": c > ind["sma50"],
                          "above SMA 200": c > ind["sma200"], "5-day return up": c.pct_change(5) > 0})
    fwd = c.shift(-sessions) / c - 1
    valid = ind["sma200"].notna() & fwd.notna()
    now = feats.iloc[-1]
    cols, m = list(feats.columns), None
    for k in (4, 3, 2):
        cols = list(feats.columns)[:k]
        m = valid & (feats[cols] == now[cols]).all(axis=1)
        if m.sum() >= 40:
            break
    r = bucket(fwd[m].values)
    if r:
        state = ", ".join(f"{'' if now[k] else 'not '}{k}" for k in cols)
        r.update(note=f"{r['n']} past Nifty days in the same state ({state}), {sessions}-session forward return "
                      f"since {df.index[0].date()}; overlapping windows", state={k: bool(now[k]) for k in cols})
    return r


def _typesafe_key():
    if os.environ.get("TYPESAFE_API_KEY"):
        return os.environ["TYPESAFE_API_KEY"]
    p = pathlib.Path.home() / ".omp" / "profiles" / os.environ.get("OMP_PROFILE", "sam") / "agent" / ".env"
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            k, _, v = ln.strip().partition("=")
            if k.strip() == "TYPESAFE_API_KEY" and v.strip():
                return v.strip().strip('"').strip("'")
    return None


def jev_probs(evidence, chain, spot, exit_iso, sessions):
    """Live Jev judgment on the three scenarios (cached 20 min); falls back to the EOD Jev reading."""
    try:
        c = json.loads(JEV_CACHE.read_text(encoding="utf-8"))
        if time.time() - c["at"] < JEV_MAX_AGE and abs(c["spot"] / spot - 1) < 0.003 and c["exit"] == exit_iso:
            return c["result"]
    except (OSError, ValueError, KeyError):
        pass
    err = None
    key = _typesafe_key()
    if key:
        try:
            import jev_client
            q = {"scenario": {"type": "choice", "criteria": {"bullish": None, "bearish": None, "sideways": None},
                              "instructions": (f"Judge the Nifty 50 index close on {exit_iso} ({sessions} trading sessions ahead) "
                                               f"relative to the live price {spot:,.2f}. bullish = more than 1% above, "
                                               f"bearish = more than 1% below, sideways = within 1% either way. "
                                               f"Use only the evidence supplied.")}}
            a = jev_client.Client(key).ask(json.dumps(evidence, separators=(",", ":")), q)["scenario"]
            p = a["probabilities"]
            r = dict(bull=p["bullish"], side=p["sideways"], bear=p["bearish"], confidence=rnd(a["confidence"], 3),
                     choice=a["choice"], live=True, note=f"live Jev {jev_client.MODEL} judgment of today's evidence")
            JEV_CACHE.parent.mkdir(parents=True, exist_ok=True)
            JEV_CACHE.write_text(json.dumps(dict(at=time.time(), spot=spot, exit=exit_iso, result=r)), encoding="utf-8")
            return r
        except Exception as e:  # Jev is one of four sources; never fatal
            err = str(e)[:120]
    d = ((chain.get("jev") or {}).get("index") or {}).get("direction") or {}
    p = d.get("probabilities") or {}
    tot = sum(p.get(k, 0) for k in ("bullish", "bearish", "range_bound"))
    if not tot:
        return None
    return dict(bull=p.get("bullish", 0) / tot, side=p.get("range_bound", 0) / tot, bear=p.get("bearish", 0) / tot,
                confidence=d.get("confidence"), live=False,
                note=f"EOD Jev index direction ({chain.get('as_of')}), renormalised" + (f"; live call failed: {err}" if err else ""))


def blend(sources):
    have = [s for s in sources.values() if s]
    out = {k: sum(s[k] for s in have) / len(have) for k in SCEN}
    t = sum(out.values())
    return {k: round(v / t, 4) for k, v in out.items()}


# ── 3. live chain and structures ────────────────────────────────────────────
def chain_contracts(rows, expiry):
    out = {}
    for r in rows:
        if r.get("pSymbolName") != "NIFTY" or r.get("pOptionType") not in ("CE", "PE"):
            continue
        try:
            k = round(float(r.get("dStrikePrice")) / 100.0, 2)
        except (TypeError, ValueError):
            continue
        if kl.kotak_expiry_date(r.get("lExpiryDate") or r.get("pExpiryDate")) == expiry:
            out[(k, r["pOptionType"])] = dict(pSymbol=r.get("pSymbol"), trd=r.get("pTrdSymbol"), lot=kl._f(r.get("lLotSize")))
    return out


def live_chain(sess, contracts, spot):
    want = {k: c for k, c in contracts.items() if abs(k[0] - spot) <= spot * SPAN and k[0] % 50 == 0}
    toks = {f"nse_fo|{c['pSymbol']}": k for k, c in want.items()}
    out, items = {}, list(toks.items())
    for i in range(0, len(items), 40):
        chunk = dict(items[i:i + 40])
        res = kl.quotes(list(chunk), sess=sess)
        res = res if isinstance(res, list) else (res or {}).get("data", [])
        for q in res or []:
            key = chunk.get(f"{q.get('exchange')}|{q.get('exchange_token')}")
            if key is None:
                continue
            dep = q.get("depth") or {}
            bid = _px(((dep.get("buy") or [{}])[0] or {}).get("price"))
            ask = _px(((dep.get("sell") or [{}])[0] or {}).get("price"))
            out[key] = dict(ltp=_px(q.get("ltp")), bid=bid, ask=ask, oi=_px(q.get("open_int")),
                            volume=_px(q.get("last_volume")), contract=want[key]["trd"])
    return out


def mid(qd):
    b, a = qd.get("bid"), qd.get("ask")
    return (a + b) / 2 if b and a and a >= b else qd.get("ltp")


def fill(qd, side):
    b, a = qd.get("bid"), qd.get("ask")
    if b and a and a >= b and (a - b) <= max(1.0, MAX_SPREAD * (a + b) / 2):
        return (a, "ask") if side == "BUY" else (b, "bid")
    return qd.get("ltp"), "ltp"


def tradable(qd):
    return qd and qd.get("ltp") and (qd.get("oi") or 0) >= MIN_OI and fill(qd, "BUY")[0] and fill(qd, "SELL")[0]


def candidates(q, spot, step=50):
    atm = round(spot / step) * step
    ks = sorted({k for k, _ in q})
    have = lambda k, t: tradable(q.get((k, t)))  # noqa: E731
    out = []

    def add(scen, kind, legs):
        if all(have(k, t) for _, k, t in legs):
            out.append(dict(scenario=scen, kind=kind, legs=legs))

    for k1 in ks:
        for w in WIDTHS:
            if atm - 150 <= k1 <= atm + 300:
                add("bull", "Bull call spread", [("BUY", k1, "CE"), ("SELL", k1 + w, "CE")])
            if atm - 600 <= k1 <= atm + 100:
                add("bull", "Bull put spread (credit)", [("SELL", k1, "PE"), ("BUY", k1 - w, "PE")])
            if atm - 300 <= k1 <= atm + 150:
                add("bear", "Bear put spread", [("BUY", k1, "PE"), ("SELL", k1 - w, "PE")])
            if atm - 100 <= k1 <= atm + 600:
                add("bear", "Bear call spread (credit)", [("SELL", k1, "CE"), ("BUY", k1 + w, "CE")])
        if atm - 100 <= k1 <= atm + 200:
            add("bull", "Long call", [("BUY", k1, "CE")])
        if atm - 200 <= k1 <= atm + 100:
            add("bear", "Long put", [("BUY", k1, "PE")])
    puts = [k for k in ks if spot * 0.97 <= k <= spot * 0.995]
    calls = [k for k in ks if spot * 1.005 <= k <= spot * 1.03]
    for kp in puts:
        for kc in calls:
            for w in range(100, 501, 50):
                add("side", "Iron condor", [("SELL", kp, "PE"), ("BUY", kp - w, "PE"), ("SELL", kc, "CE"), ("BUY", kc + w, "CE")])
    for k0 in (atm - 50, atm, atm + 50):
        for w in range(200, 801, 50):
            add("side", "Iron butterfly", [("SELL", k0, "PE"), ("SELL", k0, "CE"), ("BUY", k0 - w, "PE"), ("BUY", k0 + w, "CE")])
    return out


def expiry_payoff(legs, s):
    s = np.asarray(s, dtype=float)
    v = np.zeros_like(s)
    for l in legs:
        intr = np.maximum(s - l["strike"], 0) if l["type"] == "CE" else np.maximum(l["strike"] - s, 0)
        v += (1 if l["side"] == "BUY" else -1) * (intr - l["fill"])
    return v


def max_pl(legs, lot):
    ks = sorted({l["strike"] for l in legs})
    pts = np.array([0.0] + ks + [ks[-1] + 5000.0])
    vals = expiry_payoff(legs, pts) * lot
    slope_hi = sum((1 if l["side"] == "BUY" else -1) for l in legs if l["type"] == "CE")
    return (None if slope_hi > 0 else float(vals.max())), (None if slope_hi < 0 else float(vals.min()))


def breakevens(legs, spot):
    s = spot * (1 + np.linspace(-0.1, 0.1, 2001))
    v = expiry_payoff(legs, s)
    idx = np.where(np.diff(np.sign(v)) != 0)[0]
    return [rnd(s[i] - v[i] * (s[i + 1] - s[i]) / (v[i + 1] - v[i]), 0) for i in idx if v[i + 1] != v[i]]


def name_of(kind, legs):
    ks = "/".join(f"{l['strike']:,.0f}" for l in legs)
    return f"{kind} {ks}"


def evaluate(c, ctx):
    lot, prices = ctx["lot"], ctx["prices"]
    legs, entry, cost_unit = [], 0.0, 0.0
    vx, v1 = np.zeros_like(prices), np.zeros_like(prices)
    for side, k, t in c["legs"]:
        qd, sg = ctx["q"][(k, t)], (1 if side == "BUY" else -1)
        px, basis = fill(qd, side)
        entry += sg * px
        vx += sg * ctx["vexit"][(k, t)]
        v1 += sg * ctx["v1d"][(k, t)]
        flat = float(np.interp(ctx["spot"], prices, ctx["vexit"][(k, t)]))
        cost_unit += leg_cost(px, side) + leg_cost(max(flat, 0.0), "SELL" if side == "BUY" else "BUY")
        legs.append(dict(side=side, strike=k, type=t, contract=qd["contract"], bid=qd.get("bid"), ask=qd.get("ask"),
                         ltp=qd.get("ltp"), fill=px, fill_basis=basis, iv=rnd(ctx["iv"][(k, t)] * 100, 2), oi=qd.get("oi")))
    costs = cost_unit * lot + od.BROKERAGE * 2 * len(legs) * (1 + od.GST)
    pnl_x = (vx - entry) * lot - costs
    pnl_1 = (v1 - entry) * lot - costs
    mp, ml = max_pl(legs, lot)
    if ml is None or ml >= 0:
        return None
    band = {"bull": (GRID >= BAND) & (GRID <= ctx["B"]), "bear": (GRID <= -BAND) & (GRID >= -ctx["B"]),
            "side": np.abs(GRID) <= BAND}
    if_ = {s: float(pnl_x[m].mean()) for s, m in band.items()}
    # Full conditional expectation per scenario bucket (tails included) under the live-IV lognormal.
    bucket_m = {"bull": GRID > BAND, "bear": GRID < -BAND, "side": np.abs(GRID) <= BAND}
    cond = {s: float((pnl_x[m] * ctx["mass"][m]).sum() / ctx["mass"][m].sum()) for s, m in bucket_m.items()}
    at = lambda m: float(np.interp(m, GRID, pnl_x))  # noqa: E731
    return dict(scenario=c["scenario"], kind=c["kind"], name=name_of(c["kind"], legs), legs=legs,
                net=dict(type="debit" if entry > 0 else "credit", per_unit=rnd(abs(entry)), per_lot=rnd(abs(entry) * lot, 0)),
                max_profit=rnd(mp, 0), max_loss=rnd(ml, 0), costs=rnd(costs, 0), breakevens=breakevens(legs, ctx["spot"]),
                if_=if_, cond=cond, center=at(CENTER[c["scenario"]]), implied_ev=float((pnl_x * ctx["mass"]).sum()),
                _pnl_x=pnl_x, _pnl_1=pnl_1, _entry=entry)


def best_structures(evals, scen, probs, top=4):
    """Best structure if `scen` plays out: highest average P&L over a 1-2% move that way per rupee of max loss."""
    pool = [e for e in evals if e["scenario"] == scen and e["if_"][scen] > 0 and e["center"] > 0]
    for e in pool:
        e["score"] = e["if_"][scen] / -e["max_loss"]
        # Probability-weighted P&L across all three scenarios, each with its full conditional (tails included).
        e["regime_ev"] = sum(probs[s] * e["cond"][s] for s in SCEN)
    pool.sort(key=lambda e: (-e["score"], -e["regime_ev"]))
    picked, kinds = [], set()
    for e in pool:  # best overall, then the best of each other structure type
        if not picked or e["kind"] not in kinds:
            picked.append(e)
            kinds.add(e["kind"])
        if len(picked) >= top:
            break
    return picked


def exits(e, ctx, scen):
    """Rupee stop/target and the Nifty levels where they hit (stop on a next-day curve, target at exit date)."""
    prices, lot, spot = ctx["prices"], ctx["lot"], ctx["spot"]
    debit = e["_entry"] > 0
    if debit:
        stop = 0.5 * e["_entry"] * lot
        target = 0.6 * e["max_profit"] if e["max_profit"] else e["_entry"] * lot
        rule = "60% of max profit" if e["max_profit"] else "100% of the debit"
    else:
        credit = -e["_entry"] * lot
        stop = min(1.5 * credit, 0.6 * -e["max_loss"])
        target = 0.5 * credit
        rule = "50% of the credit"
    p1, px = e["_pnl_1"], e["_pnl_x"]
    # A target the position cannot reach by the exit date is useless: cap it at 75% of the best exit-date P&L
    # within the +/-band of this scenario.
    reach = {"bull": (GRID >= 0) & (GRID <= ctx["B"]), "bear": (GRID <= 0) & (GRID >= -ctx["B"]),
             "side": np.abs(GRID) <= BAND}[scen]
    best = float(px[reach].max())
    if best > 0 and target > 0.75 * best:
        target, rule = 0.75 * best, "75% of the best P&L reachable by the exit date"
    i0 = int(np.argmin(np.abs(prices - spot)))
    dn = next((prices[i] for i in range(i0, -1, -1) if p1[i] <= -stop), None)
    up = next((prices[i] for i in range(i0, len(prices)) if p1[i] <= -stop), None)
    if scen == "bull":
        tgt = next((prices[i] for i in range(i0, len(prices)) if px[i] >= target), None)
        tgt_txt = f"Nifty about {tgt:,.0f} by the exit date" if tgt else "not reached within +6%"
    elif scen == "bear":
        tgt = next((prices[i] for i in range(i0, -1, -1) if px[i] >= target), None)
        tgt_txt = f"Nifty about {tgt:,.0f} by the exit date" if tgt else "not reached within -6%"
    else:
        ok = np.where(px >= target)[0]
        tgt_txt = (f"Nifty between {prices[ok[0]]:,.0f} and {prices[ok[-1]]:,.0f} on the exit date" if len(ok) else "not reached")
    return dict(stop_rupees=rnd(-stop, 0), stop_rule="lose 50% of the debit" if debit else "loss reaches 1.5x the credit (max 60% of max loss)",
                stop_nifty_below=rnd(dn, 0), stop_nifty_above=rnd(up, 0),
                target_rupees=rnd(target, 0), target_rule=rule, target_text=tgt_txt)


def card(e, ctx, scen, probs, trig, alts):
    pnl_moves = []
    moves = MOVES + ([round(ctx["B"], 4), -round(ctx["B"], 4)] if ctx["B"] > 0.0201 else [])
    for m in sorted(set(moves)):
        pnl_moves.append(dict(move_pct=round(m * 100, 2), nifty=rnd(ctx["spot"] * (1 + m), 0),
                              pnl=rnd(float(np.interp(m, GRID, e["_pnl_x"])), 0)))
    ex = exits(e, ctx, scen)
    t = trig[scen]
    return dict(scenario=scen, probability=probs[scen], structure=e["kind"], name=e["name"], legs=e["legs"],
                net=e["net"], max_profit=e["max_profit"], max_loss=e["max_loss"], breakevens=e["breakevens"],
                costs=e["costs"], pnl_moves=pnl_moves,
                if_scenario={s: rnd(e["if_"][s], 0) for s in SCEN}, regime_ev=rnd(e["regime_ev"], 0),
                regime_ev_per_risk=rnd(e["regime_ev"] / -e["max_loss"] * 100, 2),
                scenario_return_on_risk=rnd(e["score"] * 100, 1), implied_ev=rnd(e["implied_ev"], 0),
                trigger=t, structure_exit=t["exit"], exits=ex, exit_by=ctx["exit_by"],
                alternatives=[dict(name=a["name"], net=a["net"], max_profit=a["max_profit"], max_loss=a["max_loss"],
                                   if_scenario=rnd(a["if_"][scen], 0), scenario_return_on_risk=rnd(a["score"] * 100, 1),
                                   regime_ev=rnd(a["regime_ev"], 0)) for a in alts])


# ── 4. build ────────────────────────────────────────────────────────────────
def build(sess, chain, kentry, live, today, exit_by, rows):
    """live = kotak nifty50 dict (ltp, open, high, low, close=previous close)."""
    spot = live.get("ltp")
    if not _px(spot):
        raise RuntimeError("no live Nifty price")
    expiry = chain["index"]["trade_expiry"]
    dte = (dt.date.fromisoformat(expiry) - today).days
    h_days = (exit_by - today).days
    sessions = int(np.busday_count(today, exit_by))
    contracts = chain_contracts(rows, expiry)
    q = live_chain(sess, contracts, spot)
    if len(q) < 20:
        raise RuntimeError(f"live chain too thin ({len(q)} quotes)")
    lot = int(next(iter(contracts.values()))["lot"] or chain["index"].get("lot") or 65)
    t0, t_rem, t_1d = dte / 365, max(dte - h_days, 0.5) / 365, max(dte - 1, 0.5) / 365
    atm = min({k for k, _ in q}, key=lambda k: abs(k - spot))
    ivs = {}
    for key, qd in q.items():
        v = implied_vol(mid(qd), spot, key[0], t0, key[1] == "CE")
        if v:
            ivs[key] = v
    atm_iv = np.mean([ivs[(atm, t)] for t in ("CE", "PE") if (atm, t) in ivs]) if any((atm, t) in ivs for t in ("CE", "PE")) \
        else chain["index"]["atm_iv"] / 100
    q = {k: v for k, v in q.items() if k in ivs}
    prices = spot * (1 + GRID)
    ctx = dict(q=q, iv=ivs, lot=lot, spot=spot, prices=prices, exit_by=exit_by.isoformat(),
               B=min(max(0.02, atm_iv * math.sqrt(h_days / 365)), 0.06),
               vexit={k: nc._bs_price(prices, k[0], t_rem, ivs[k], k[1] == "CE") for k in q},
               v1d={k: nc._bs_price(prices, k[0], t_1d, ivs[k], k[1] == "CE") for k in q},
               mass=nc._lognorm_mass(prices, spot, atm_iv, h_days / 365))
    df, last_completed = daily_bars(live, today)
    ind = indicators(df)
    a = analyse(df, ind, chain, live, q, spot, atm_iv, h_days, dte)
    trig = triggers(a, live, spot)
    evidence = dict(nifty_live=spot, previous_close=live.get("close"), today=dict(open=live.get("open"), high=live.get("high"), low=live.get("low")),
                    previous_day=a["prev"], indicators={k: rnd(v, 1) for k, v in a["values"].items()},
                    structure=a["structure"], option_chain=a["oi"], stats=a["stats"], trend_votes=[(v["name"], v["side"], v["value"]) for v in a["votes"]],
                    participants=chain.get("participants"), horizon=dict(exit_date=exit_by.isoformat(), sessions=sessions))
    sources = dict(implied=implied_probs(atm_iv, h_days), kronos=kronos_probs(kentry, exit_by.isoformat()),
                   history=history_probs(df, ind, sessions),
                   jev=jev_probs(evidence, chain, spot, exit_by.isoformat(), sessions))
    probs = blend(sources)
    evals = [e for e in (evaluate(c, ctx) for c in candidates(q, spot)) if e]
    cards, missing = [], []
    for scen in SCEN:
        picks = best_structures(evals, scen, probs)
        if picks:
            cards.append(card(picks[0], ctx, scen, probs, trig, picks[1:]))
        else:
            missing.append(scen)
    cards.sort(key=lambda c: -(c["regime_ev_per_risk"] or -1e9))
    for i, c in enumerate(cards, 1):
        c["rank"] = i
    return dict(
        generated_at=dt.datetime.now(IST).isoformat(timespec="seconds"), spot=spot, change_pct=rnd((spot / live["close"] - 1) * 100, 2) if live.get("close") else None,
        today=dict(open=live.get("open"), high=live.get("high"), low=live.get("low")), expiry=expiry, dte=dte, lot=lot,
        exit_by=exit_by.isoformat(), sessions=sessions, horizon_days=h_days, band_pct=BAND * 100, band_max_pct=rnd(ctx["B"] * 100, 2),
        last_completed_bar=last_completed, trend=a, triggers=trig,
        probabilities=dict(sources={k: ({kk: (rnd(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()} if v else None) for k, v in sources.items()},
                           blended=probs),
        cards=cards, no_structure=missing, chain_quotes=len(q), candidates=len(evals),
        method=("Bull/bear = Nifty more than 1% above/below the live price on the exit date; sideways = within 1%. "
                "Probabilities are the equal-weight average of the four sources shown. Each structure is valued at the exit date with "
                "Black-Scholes at every leg's own live implied volatility, entered at live bid/ask, costs removed. "
                "'If scenario' = average P&L over a 1-2% move that way (wider if the implied 1-sigma move is larger). "
                "Ranking = probability-weighted P&L per rupee of max loss. Probabilities are not calibrated forecasts."))
