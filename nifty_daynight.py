#!/usr/bin/env python3
"""Nifty 50 - DAY vs NIGHT. Where does Nifty make its points: overnight (close -> next open) or during the day
(open -> close)? Plus 10 more ideas about how a session is built, each tested as a BUY and a SELL rule.

Idea (Lou, Polk & Skouras, "A tug of war: overnight versus intraday expected returns", JFE 2019; Kelly & Clark
2011; Cooper, Cliff & Gulen 2008): in many markets most of the gain arrives overnight and the day hands it back.

Every number here is recomputed after each NSE close:
  * Night = today's open - yesterday's close.  Day = today's close - today's open.  Night + Day = close-to-close
    (checked to the paisa on every run; the build stops if it fails).
  * Opens are cross-checked against the first hourly candle's open (median gap reported).
  * Costs: 0.035% of price per round trip (~9 Nifty points) on every trade.
  * Every rule is split into its first and last 100 sessions; "holds up" = profitable in both halves.
  * Intraday ideas use hourly candles only (no daily high/low look-ahead). The opening-range breakout is
    re-checked on 5-minute candles for the sessions where they exist.
Output: docs/nifty_daynight.json (+ public/data). Paper research, not advice.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import nifty_ema as N      # noqa: E402
import nifty_combo as K    # noqa: E402

DOCS, PUBLIC = ROOT / "docs", ROOT / "public" / "data"
SESSIONS = 200
COST = N.COST_PCT


# ── maths ─────────────────────────────────────────────────────────────────────

def leg(points, entry, mask=None, side=1):
    """One trade per selected session. points = price change of the held stretch (long view)."""
    p = side * np.asarray(points, float)
    e = np.asarray(entry, float)
    m = np.ones(len(p), bool) if mask is None else np.asarray(mask, bool)
    m = m & ~np.isnan(p) & ~np.isnan(e)
    p, e = p[m], e[m]
    if not len(p):
        return {"n": 0, "gross": 0.0, "net": 0.0, "win": None, "pf": None, "avg": None, "dd": 0.0}
    net = p - COST * e
    w = net > 0
    gl = -net[~w].sum()
    pf = net[w].sum() / gl if gl > 0 else 99.0
    eq = np.r_[0.0, np.cumsum(net)]
    return {"n": int(len(p)), "gross": round(float(p.sum()), 1), "net": round(float(net.sum()), 1),
            "win": round(float(w.mean() * 100), 1), "pf": round(float(min(pf, 99.0)), 2),
            "avg": round(float(net.mean()), 1), "dd": round(float((np.maximum.accumulate(eq) - eq).max()), 1)}


def daily_table(d):
    t = pd.DataFrame({"o": d["Open"].astype(float), "h": d["High"].astype(float), "l": d["Low"].astype(float),
                      "c": d["Close"].astype(float)})
    t.index = pd.to_datetime(t.index).normalize()
    t["pc"] = t["c"].shift()
    t["night"] = t["o"] - t["pc"]
    t["day"] = t["c"] - t["o"]
    t["cc"] = t["c"] - t["pc"]
    t["rng"] = t["h"] - t["l"]
    t["clv"] = (t["c"] - t["l"]) / t["rng"].replace(0, np.nan)
    return t


def hourly_table(h, index):
    g = h.groupby(h.index.date)
    out = pd.DataFrame({
        "o1": g["Open"].first(), "c1": g.apply(lambda x: x["Close"].iloc[0]),
        "h1": g.apply(lambda x: x["High"].iloc[0]), "l1": g.apply(lambda x: x["Low"].iloc[0]),
        "lo": g.apply(lambda x: x["Open"].iloc[-1]), "hc": g["Close"].last(), "nb": g.size()})
    out.index = pd.to_datetime(out.index)
    return out.reindex(index)


def ema_state(frames, index):
    df = frames["2h"]
    e = N.ema(df["Close"].to_numpy(float), K.EMA_N)
    st = pd.Series(np.sign(df["Close"].to_numpy(float) - e), index=df.index).groupby(df.index.date).last()
    st.index = pd.to_datetime(st.index)
    return st.reindex(index).ffill()


def orb(bars_by_day, first_n):
    """Opening-range breakout with no look-ahead: range = first n bars; enter at the range level on the FIRST later
    bar that breaks it; hold to the close. A bar breaking both sides counts as a full-range loss (worst case)."""
    tr = []
    for day, x in bars_by_day:
        if len(x) <= first_n:
            continue
        hi, lo, close = x["High"].iloc[:first_n].max(), x["Low"].iloc[:first_n].min(), x["Close"].iloc[-1]
        for k in range(first_n, len(x)):
            up, dn = x["High"].iloc[k] > hi, x["Low"].iloc[k] < lo
            if up and dn:
                tr.append((str(day), 0, -(hi - lo) - COST * hi))
                break
            if up or dn:
                s, ep = (1, hi) if up else (-1, lo)
                tr.append((str(day), s, s * (close - ep) - COST * ep))
                break
    return tr


def orb_stats(tr):
    if not tr:
        return {"n": 0}
    net = np.array([t[2] for t in tr])
    w = net > 0
    gl = -net[~w].sum()
    eq = np.r_[0.0, np.cumsum(net)]
    return {"n": len(net), "win": round(float(w.mean() * 100), 1), "pf": round(float(net[w].sum() / gl), 2) if gl > 0 else 99.0,
            "net": round(float(net.sum()), 1), "dd": round(float((np.maximum.accumulate(eq) - eq).max()), 1),
            "buy_net": round(float(sum(t[2] for t in tr if t[1] == 1)), 1),
            "sell_net": round(float(sum(t[2] for t in tr if t[1] == -1)), 1)}


def split_ema_trades(frames, since):
    """Night vs day points inside the EMA 105 trades (rules unchanged, from nifty_combo)."""
    df = frames["2h"]
    X = K.indicators(df, K.EMA_N, frames["1D"])
    F = K.filters(X)
    T = np.ones(len(X["c"]), bool)
    c, o = X["c"], X["o"]
    dates = pd.Index(df.index.date)
    newday = np.r_[True, dates[1:] != dates[:-1]]
    cut = int(np.searchsorted(df.index, since))

    def decomp(trades, start=0):
        night = day = 0.0
        cnt = 0
        for eb, xb, dr, _net, _why in trades:
            if eb < start:
                continue
            cnt += 1
            for k in range(eb + 1, xb + 1):
                if newday[k]:
                    night += dr * (o[k] - c[k - 1])
                    day += dr * (c[k] - o[k])
                else:
                    day += dr * (c[k] - c[k - 1])
        return {"trades": cnt, "night": round(night, 1), "day": round(day, 1)}

    win_mask = (X["adx"] > 20) & (X["d50"] == 1) & F["Supertrend"][0]
    rules = {
        "EMA 105 (buy above, sell below)": K.simulate(X, T, T, "cross", None, True),
        "EMA 105 buy only": K.simulate(X, T, T, "cross", None, False),
        "EMA 105 + confirmations (the winner)": K.simulate(X, win_mask, T, "rsi", 68, False),
    }
    return [{"rule": k, "all": decomp(v), "last200": decomp(v, cut)} for k, v in rules.items()]


# ── build ─────────────────────────────────────────────────────────────────────

def build(now=None, frames=None):
    now = now or datetime.now(N.IST)
    frames = frames or N.load_data(now)
    D = daily_table(frames["1D"])
    S = D.iloc[-SESSIONS:].copy()
    if len(S) < SESSIONS or S[["o", "c", "pc"]].isna().any().any():
        raise SystemExit("not enough clean daily sessions")
    ident = float((S["night"] + S["day"] - S["cc"]).abs().max())
    if ident > 0.01:
        raise SystemExit(f"night + day != close-to-close (max error {ident})")
    H = hourly_table(frames["1h"], S.index)
    open_gap = (S["o"] - H["o1"]).abs()
    checks = {"identity_max_error": round(ident, 4),
              "open_vs_first_hour_median": round(float(open_gap.median()), 2),
              "open_vs_first_hour_p95": round(float(open_gap.quantile(.95)), 1),
              "hourly_sessions": int(H["nb"].notna().sum()), "flat_opens": int((S["night"].abs() < 0.01).sum())}

    S["dow"] = S.index.dayofweek
    S["ema"] = ema_state(frames, S.index).shift()       # state at the previous close (known before the night)
    rng_med = D["rng"].rolling(20).median().shift().reindex(S.index)
    S["p_cc"], S["p_clv"], S["p_rng"] = D["cc"].shift().reindex(S.index), D["clv"].shift().reindex(S.index), \
        D["rng"].shift().reindex(S.index)
    tom = pd.Series(False, index=S.index)
    per = S.index.to_period("M")
    for m in per.unique():
        idx = np.where(per == m)[0]
        tom.iloc[idx[:3]] = True
        tom.iloc[idx[-1:]] = True
    first, rest = H["c1"] - H["o1"], H["hc"] - H["c1"]
    to_last, last = H["lo"] - H["o1"], H["hc"] - H["lo"]
    half = SESSIONS // 2
    T = pd.Series(True, index=S.index)

    rules = []

    def add(idea, rule, pts, entry, mask, side):
        mask = pd.Series(np.asarray(mask, bool), index=S.index)
        a = leg(pts.iloc[:half], entry.iloc[:half], mask.iloc[:half], side)
        b = leg(pts.iloc[half:], entry.iloc[half:], mask.iloc[half:], side)
        r = {"idea": idea, "rule": rule, "side": "BUY" if side == 1 else "SELL", **leg(pts, entry, mask, side),
             "h1": a["net"], "h2": b["net"], "h1_n": a["n"], "h2_n": b["n"]}
        r["holds"] = bool(a["net"] > 0 and b["net"] > 0)
        rules.append(r)

    night, day, pc, o = S["night"], S["day"], S["pc"], S["o"]
    add("1 Day vs night", "Buy at close, sell next open (night)", night, pc, T, 1)
    add("1 Day vs night", "Sell at close, buy back next open (night)", night, pc, T, -1)
    add("1 Day vs night", "Buy at open, sell at close (day)", day, o, T, 1)
    add("1 Day vs night", "Sell at open, buy back at close (day)", day, o, T, -1)
    add("2 With the EMA 105 trend", "Night buy only when 2h close > EMA 105", night, pc, S["ema"] == 1, 1)
    add("2 With the EMA 105 trend", "Night sell only when 2h close < EMA 105", night, pc, S["ema"] == -1, -1)
    add("2 With the EMA 105 trend", "Day buy only when EMA 105 is up", day, o, S["ema"] == 1, 1)
    add("2 With the EMA 105 trend", "Day sell only when EMA 105 is down", day, o, S["ema"] == -1, -1)
    for k, nm in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]):
        add("3 Day of the week", f"{nm} night buy (previous close → {nm} open)", night, pc, S["dow"] == k, 1)
        add("3 Day of the week", f"{nm} night sell", night, pc, S["dow"] == k, -1)
        add("3 Day of the week", f"{nm} day buy (open → close)", day, o, S["dow"] == k, 1)
        add("3 Day of the week", f"{nm} day sell", day, o, S["dow"] == k, -1)
    gap = 0.25 * rng_med
    add("4 Gaps", "Gap up > ¼ normal range → sell the open (fade)", day, o, night > gap, -1)
    add("4 Gaps", "Gap up > ¼ normal range → buy the open (follow)", day, o, night > gap, 1)
    add("4 Gaps", "Gap down > ¼ normal range → buy the open (fade)", day, o, night < -gap, 1)
    add("4 Gaps", "Gap down > ¼ normal range → sell the open (follow)", day, o, night < -gap, -1)
    add("5 Where it closed", "Closed in top ¼ of the day's range → night buy", night, pc, S["p_clv"] > .75, 1)
    add("5 Where it closed", "Closed in bottom ¼ → night sell", night, pc, S["p_clv"] < .25, -1)
    add("5 Where it closed", "Closed in bottom ¼ → night buy (bounce)", night, pc, S["p_clv"] < .25, 1)
    add("6 After an up / down day", "Down day → night buy", night, pc, S["p_cc"] < 0, 1)
    add("6 After an up / down day", "Down day → next day buy", day, o, S["p_cc"] < 0, 1)
    add("6 After an up / down day", "Up day → next day sell", day, o, S["p_cc"] > 0, -1)
    add("7 Inside the day", "First hour up → buy 10:15, sell at close", rest, H["c1"], first > 0, 1)
    add("7 Inside the day", "First hour down → sell 10:15, buy back at close", rest, H["c1"], first < 0, -1)
    add("7 Inside the day", "09:15→15:15 up → buy the last 15 minutes", last, H["lo"], to_last > 0, 1)
    add("7 Inside the day", "09:15→15:15 down → sell the last 15 minutes", last, H["lo"], to_last < 0, -1)
    add("8 Turn of the month", "Last day + first 3 days: night buy", night, pc, tom, 1)
    add("8 Turn of the month", "Last day + first 3 days: day buy", day, o, tom, 1)
    add("8 Turn of the month", "Other days: day sell", day, o, ~tom, -1)
    add("9 After a wide / quiet day", "Range > 1.5× normal → next day buy", day, o, S["p_rng"] > 1.5 * rng_med, 1)
    add("9 After a wide / quiet day", "Range > 1.5× normal → next day sell", day, o, S["p_rng"] > 1.5 * rng_med, -1)
    add("9 After a wide / quiet day", "Range < 0.7× normal → night buy", night, pc, S["p_rng"] < 0.7 * rng_med, 1)

    days = set(S.index.date)
    hb = [(d_, x) for d_, x in frames["1h"].groupby(frames["1h"].index.date) if d_ in days]
    m5 = frames["5m"]
    b5 = list(m5.groupby(m5.index.date))
    o1h = orb(hb, 1)
    since5 = str(b5[0][0]) if b5 else None
    orb_res = {
        "first_hour_1h_200": orb_stats(o1h),
        "first_hour_1h_h1": orb_stats(o1h[:len(o1h) // 2]), "first_hour_1h_h2": orb_stats(o1h[len(o1h) // 2:]),
        "first_hour_1h_same_days_as_5m": orb_stats([t for t in o1h if since5 and t[0] >= since5]),
        "first_hour_5m": orb_stats(orb(b5, 12)), "first_15m_5m": orb_stats(orb(b5, 3)),
        "first_30m_5m": orb_stats(orb(b5, 6)), "sessions_5m": len(b5),
    }
    rules.append({"idea": "10 Opening-range breakout", "rule": "Break of the first-hour high (buy) or low (sell), hold to close",
                  "side": "BOTH", **orb_res["first_hour_1h_200"], "gross": None, "avg": None,
                  "h1": orb_res["first_hour_1h_h1"]["net"], "h2": orb_res["first_hour_1h_h2"]["net"],
                  "holds": bool(orb_res["first_hour_1h_h1"]["net"] > 0 and orb_res["first_hour_1h_h2"]["net"] > 0)})

    D10 = D.dropna(subset=["pc"])
    years = []
    for y, x in D10.groupby(D10.index.year):
        years.append({"year": int(y), "sessions": int(len(x)), "night": round(float(x["night"].sum()), 0),
                      "day": round(float(x["day"].sum()), 0),
                      "night_pct": round(float((x["night"] / x["pc"]).sum() * 100), 1),
                      "day_pct": round(float((x["day"] / x["o"]).sum() * 100), 1),
                      "night_up_pct": round(float((x["night"] > 0).mean() * 100), 1),
                      "day_up_pct": round(float((x["day"] > 0).mean() * 100), 1)})

    ema_split = split_ema_trades(frames, pd.Timestamp(S.index[0]).tz_localize(N.IST))

    series = [[str(t.date()), round(float(r.o), 2), round(float(r.c), 2), round(float(r.night), 2), round(float(r.day), 2)]
              for t, r in S.iterrows()]
    tot = {"night": round(float(night.sum()), 1), "day": round(float(day.sum()), 1), "cc": round(float(S["cc"].sum()), 1),
           "night_up_days": int((night > 0).sum()), "day_up_days": int((day > 0).sum()),
           "night_abs_avg": round(float(night.abs().mean()), 1), "day_abs_avg": round(float(day.abs().mean()), 1)}
    holds = [r for r in rules if r["holds"] and r["n"] >= 20]
    payload = {
        "version": 1, "name": "Nifty 50 - day vs night", "as_of": str(S.index[-1].date()),
        "generated_at": now.isoformat(timespec="minutes"), "sessions": SESSIONS,
        "from": str(S.index[0].date()), "to": str(S.index[-1].date()), "half_split": str(S.index[half].date()),
        "cost_pct": COST * 100, "checks": checks, "totals": tot, "series": series, "years": years,
        "rules": rules, "holds": [r["rule"] for r in holds], "orb": orb_res, "ema_split": ema_split,
        "source": "Lou, Polk & Skouras (2019) 'A tug of war: overnight versus intraday expected returns', "
                  "Journal of Financial Economics 134(1); Cooper, Cliff & Gulen (2008); Kelly & Clark (2011).",
        "limits": [
            "200 sessions is a short sample: a rule needs to hold up in both halves before it means anything.",
            "Index prices, not futures. Futures carry a premium and gap differently from the index at 09:15.",
            "Every trade pays 0.035% of price (about 9 points); most small day/night edges disappear after that.",
            "Hourly candles have no order inside the bar, so breakout entries assume the level was hit first; a bar "
            "that breaks both sides is booked as a loss.",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
    }
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for out in (DOCS / "nifty_daynight.json", PUBLIC / "nifty_daynight.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(f"nifty_daynight.json {payload['as_of']}: {SESSIONS} sessions {payload['from']}→{payload['to']} | night {tot['night']} "
          f"day {tot['day']} cc {tot['cc']} | {len(rules)} rules, {len(holds)} hold up in both halves | checks {checks} | "
          f"{len(text)//1024}KB")
    return payload


if __name__ == "__main__":
    build()
