#!/usr/bin/env python3
"""Value Lens Nifty 100 Fund: the best 50 of the Nifty 100, recalculated after every NSE close.

What it publishes (docs/fund.json, shown on docs/fund.html)
  * The fund today: 50 stock names and % weights that add up to exactly 100% (with the liquid-fund
    sleeve when the market guard is on), and the rupee split of any amount you invest.
  * All 100 Nifty 100 stocks ranked today, with each stock's Jev score, Jev rank and Jev view.
  * Returns 1M ... since inception against the Nifty 50 and the equal-weight Nifty 100, calendar
    years, monthly returns, SIP XIRR, every past month's weights and every downtrend exit.
  * A test of the other rebalance rules (30 vs 50 stocks, monthly vs quarterly, tighter exits).

Rules (fixed in code; the backtest and the live fund use exactly the same rules)
  Decision      last trading session of each month, using closes up to that session only.
  Execution     the next session's close, with COST_PER_SIDE charged on every rupee traded.
  Eligibility   Nifty 100 member, >= 1 year of prices, close above its 200-day average.
  Score         NSE momentum-index method: 6M and 12M return each divided by 12M volatility,
                z-scored across the eligible stocks and averaged.
  Portfolio     top HOLDINGS by score; weight = score / volatility, at most MAX_WEIGHT per stock and
                MAX_SECTOR per sector, rounded to 0.01% so the total is exactly 100.00%.
  Downtrend exit any day a held stock closes below its 200-day average it is sold at the next
                session's close; the money waits in the liquid fund until the month-end rebalance.
  Market guard  if the Nifty 50 closes below its 200-day average on decision day, CASH_GUARD of the
                fund sits in a liquid fund (CASH_YIELD) until the next month.

Jev is shown for every stock but does not pick stocks: Jev scores exist only for recent sessions,
so they cannot be backtested yet. The momentum rules have a full backtest.

Honest limits: today's Nifty 100 members are used back in time (survivorship bias); stock prices
are dividend-adjusted, the Nifty 50 line is the price index. Paper research, not advice.
"""
import csv
import io
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
PRICES = ROOT / "data" / "hhhl_prices"
DOCS = ROOT / "docs"
PUBLIC_DATA = ROOT / "public" / "data"
UNIVERSE_CSV = ROOT / "nifty100.csv"
NIFTY100_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv"

FUND_NAME = "Value Lens Nifty 100 Momentum Fund"
HOLDINGS = 30
MAX_WEIGHT = 0.06
MAX_SECTOR = 0.30
CASH_GUARD = 0.50
CASH_YIELD = 0.065
COST_PER_SIDE = 0.002
LONG, SHORT, DMA = 252, 126, 200
FREQ = "M"
EXIT_RULE = "below_200dma"
DEFAULT_SIP = 400000

# Other rules tested every day with the same prices. (holdings, frequency, exit rule, market guard)
VARIANTS = [
    (50, "M", "below_200dma", CASH_GUARD),
    (50, "M", "none", CASH_GUARD),
    (50, "M", "st_and_50dma", CASH_GUARD),
    (50, "Q", "below_200dma", CASH_GUARD),
    (50, "M", "below_200dma", 0.0),
    (30, "M", "below_200dma", CASH_GUARD),
]
EXIT_WORDS = {
    "none": "no daily exit",
    "below_200dma": "sell when a stock closes below its 200-day average",
    "st_and_50dma": "sell when Supertrend AND the 50-day average both turn down",
}

# Real products, as published (read on 2026-10-30). Shown so the fund's numbers have context.
REAL_WORLD = [
    {"name": "Nifty200 Momentum 30 index (total return)", "period": "Apr 2005 – Oct 2026",
     "cagr": 18.1, "note": "Before costs. Worst fall −68% (2008), not recovered until Apr 2014. 2008: −61%, 2011: −17%.",
     "url": "https://tipsheet.markets/lab/p/mom200/"},
    {"name": "Nifty200 Momentum 30 vs Nifty 50 (SBI MF)", "period": "Apr 2005 – May 2025",
     "cagr": 19.77, "note": "Nifty 50 did 14.50% a year over the same period.",
     "url": "https://investmentguruindia.com/editorial/uploads/news-pdf/f4db14dd_NFO%20Presentation%20-%20SBI%20Nifty200%20Momentum%2030%20Index%20Fund%20(1).pdf"},
    {"name": "Windmill Capital Value & Momentum smallcase", "period": "8 years, live",
     "cagr": 25.31, "note": "One of the best long-running smallcases; live returns since launch.",
     "url": "https://wealth.moolaah.com/product_master/smallcase_stacks_detail_page?sc_id=SCMO_0010"},
    {"name": "Kotak Nifty 200 Momentum 30 Index Fund", "period": "Jun 2023 – Oct 2026",
     "cagr": 9.88, "note": "Same strategy, bad start date: 1-year returns ranged from −21% to +71%.",
     "url": "https://www.kotakmf.com/mutual-funds/passive-funds/kotak-nifty-200-momentum-30-index-fund/dir-g"},
]


# ── Data ──────────────────────────────────────────────────────────────────────────────────
def refresh_universe():
    try:
        from urllib.request import Request, urlopen
        req = Request(NIFTY100_URL, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"})
        txt = urlopen(req, timeout=25).read().decode("utf-8", "replace")
        rows = list(csv.DictReader(io.StringIO(txt)))
        if len(rows) >= 95 and all(r.get("Symbol") for r in rows):
            UNIVERSE_CSV.write_text(txt, encoding="utf-8")
            return "live"
    except Exception:
        pass
    if not UNIVERSE_CSV.exists():
        raise SystemExit("No Nifty 100 list: live fetch failed and nifty100.csv is missing")
    return "cache"


def load_universe():
    rows = list(csv.DictReader(io.StringIO(UNIVERSE_CSV.read_text(encoding="utf-8"))))
    return [{"symbol": r["Symbol"].strip(), "name": r["Company Name"].strip(), "sector": r["Industry"].strip()}
            for r in rows if r.get("Symbol")]


def read_ohlc(path):
    df = pd.read_csv(path)
    df["Date"] = pd.to_datetime(df["Date"].astype(str).str[:10])
    return df.dropna(subset=["Close"]).drop_duplicates("Date", keep="last").set_index("Date").sort_index()


def load_prices(symbols):
    """Closes, highs and lows on a shared trading calendar, plus the Nifty 50 close."""
    raw = {s: read_ohlc(PRICES / f"{s}.NS.csv") for s in symbols if (PRICES / f"{s}.NS.csv").exists()}
    px = pd.DataFrame({s: d["Close"].astype(float) for s, d in raw.items()}).sort_index()
    calendar = px.index[px.notna().sum(axis=1) >= max(20, int(0.6 * px.shape[1]))]
    px = px.reindex(calendar).ffill(limit=5)
    high = pd.DataFrame({s: d["High"].astype(float) for s, d in raw.items()}).reindex(calendar).ffill(limit=5)
    low = pd.DataFrame({s: d["Low"].astype(float) for s, d in raw.items()}).reindex(calendar).ffill(limit=5)
    nifty = read_ohlc(PRICES / "NSEI.csv")["Close"].astype(float).reindex(calendar).ffill(limit=5)
    return px, high, low, nifty


def supertrend_dir(h, l, c, n=10, m=3.0):
    """Supertrend(10, 3) direction: +1 up, -1 down, NaN before enough data."""
    h, l, c = h.to_numpy(float), l.to_numpy(float), c.to_numpy(float)
    N = len(c)
    out = np.full(N, np.nan)
    pc = np.r_[np.nan, c[:-1]]
    with np.errstate(invalid="ignore"):
        tr = np.fmax(np.fmax(h - l, np.abs(h - pc)), np.abs(l - pc))
    atr = pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    hl2 = (h + l) / 2
    ub, lb = hl2 + m * atr, hl2 - m * atr
    fu, fl = ub.copy(), lb.copy()
    d = 1
    for i in range(N):
        if np.isnan(c[i]) or np.isnan(atr[i]):
            continue
        if i > 0 and not np.isnan(fu[i - 1]):
            fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
            fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
            if d == 1 and c[i] < fl[i]:
                d = -1
            elif d == -1 and c[i] > fu[i]:
                d = 1
        out[i] = d
    return out


def exit_signals(px, high, low):
    dma200 = px.rolling(DMA, min_periods=DMA).mean()
    dma50 = px.rolling(50, min_periods=50).mean()
    st = pd.DataFrame({s: supertrend_dir(high[s], low[s], px[s]) for s in px.columns}, index=px.index)
    return {"none": None, "below_200dma": px < dma200, "st_and_50dma": (st == -1) & (px < dma50)}, st


def load_div_bonus():
    """Dividend-quality bonus per symbol (0–0.25 z-score addend), applied only to the live
    portfolio decision — not to the backtest, which has no historical dividend data.
    Nifty 200 only; stocks paying dividends 2+ years with a steady 1.5–9% yield get a lift."""
    try:
        divs = json.loads((DOCS / "dividends.json").read_text(encoding="utf-8"))
        data, bonus = {}, {}
        for r in divs.get("rows", []):
            data[r["symbol"]] = r
            yrs = r.get("years_paid", 0)
            yld = r.get("current_yield", 0)
            if yrs >= 2 and 1.5 <= yld <= 9.0 and not r.get("special_heavy", False):
                years_f = min(yrs / 10.0, 1.0)
                yield_f = min(yld / 5.0, 1.0) if yld <= 5.0 else max(0.0, 1.0 - (yld - 5.0) / 4.0)
                bonus[r["symbol"]] = round(0.25 * years_f * yield_f, 4)
        return data, bonus
    except Exception:
        return {}, {}




# ── Selection & weights ──────────────────────────────────────────────────────────────────
def zscore(x):
    sd = x.std(ddof=0)
    return (x - x.mean()) / sd if sd and np.isfinite(sd) else x * 0


def score_universe(px, i, div_bonus=None):
    """Risk-adjusted momentum of every eligible stock, using rows 0..i only."""
    w = px.iloc[: i + 1]
    elig = w.columns[w.notna().sum() >= LONG + 1]
    if len(elig) == 0:
        return pd.DataFrame()
    w = w[elig]
    p0 = w.iloc[-1]
    vol = np.log(w.iloc[-LONG - 1:]).diff().iloc[1:].std(ddof=0) * math.sqrt(252)
    df = pd.DataFrame({"r6": p0 / w.iloc[-1 - SHORT] - 1, "r12": p0 / w.iloc[-1 - LONG] - 1, "vol": vol,
                       "close": p0, "dma200": w.iloc[-DMA:].mean()}).dropna()
    df = df[(df.vol > 0) & (df.close > df.dma200)]
    if df.empty:
        return df
    df["z"] = 0.5 * zscore(df.r6 / df.vol) + 0.5 * zscore(df.r12 / df.vol)
    if div_bonus:
        bns = pd.Series(div_bonus).reindex(df.index).fillna(0)
        df["z"] = df["z"] + bns
    df["score"] = np.where(df.z >= 0, 1 + df.z, 1 / (1 - df.z))
    return df.sort_values("score", ascending=False)


def cap_weights(raw, sectors, max_w=MAX_WEIGHT, max_s=MAX_SECTOR):
    """Normalise to 1 and enforce the stock and sector caps by redistributing the excess."""
    w = raw / raw.sum()
    sec = pd.Series(sectors).reindex(w.index).fillna("Other")
    for _ in range(100):
        changed = False
        over = w > max_w + 1e-12
        if over.any():
            excess = (w[over] - max_w).sum()
            w[over] = max_w
            room = w[(w < max_w - 1e-12)].index
            if len(room):
                w[room] += excess * w[room] / w[room].sum()
            changed = True
        for name, tot in w.groupby(sec).sum().items():
            if tot > max_s + 1e-12:
                members = sec[sec == name].index
                excess = tot - max_s
                w[members] *= max_s / tot
                room = w[(sec != name) & (w < max_w - 1e-12)].index
                if len(room):
                    w[room] += excess * w[room] / w[room].sum()
                changed = True
        if not changed:
            break
    return w / w.sum()


def round_to_100(weights):
    """Round to 0.01% steps so the published weights add up to exactly 100.00%."""
    weights = weights / weights.sum()
    bp = (weights * 10000).to_numpy()
    floor = np.floor(bp).astype(int)
    order = np.argsort(-(bp - floor))
    floor[order[: 10000 - floor.sum()]] += 1
    return pd.Series(floor / 100.0, index=weights.index)


def market_downtrend(nifty, i):
    n = nifty.iloc[: i + 1].dropna()
    return len(n) >= DMA and n.iloc[-1] < n.iloc[-DMA:].mean()


def build_portfolio(px, nifty, i, sectors, holdings=HOLDINGS, guard=CASH_GUARD, max_w=MAX_WEIGHT):
    ranked = score_universe(px, i)
    picks = ranked.head(holdings)
    if picks.empty:
        return pd.Series(dtype=float), 1.0, ranked
    w = cap_weights(picks.score / picks.vol, sectors, max_w=max_w)
    cash = guard if market_downtrend(nifty, i) else 0.0
    return w * (1 - cash), cash, ranked


# ── Backtest ─────────────────────────────────────────────────────────────────────────────
def nse_holidays():
    """Verified NSE trading holidays kept by the HH/HL refresh (data/hhhl_calendar.json)."""
    p = ROOT / "data" / "hhhl_calendar.json"
    try:
        return set(json.loads(p.read_text(encoding="utf-8")).get("holidays", []))
    except (OSError, ValueError):
        return set()


def next_session(day, holidays):
    """Next NSE trading day after `day`: skips weekends and listed holidays."""
    d = day + pd.Timedelta(days=1)
    while d.weekday() >= 5 or str(d.date()) in holidays:
        d += pd.Timedelta(days=1)
    return d


def month_end_rows(index, holidays=None):
    """Row of the last session of each finished month (the running month is left out).

    The latest month counts as finished only if the next NSE session falls in a later month,
    so a holiday on the last weekday (e.g. 31 Mar 2026) does not skip that month's rebalance."""
    s = pd.Series(range(len(index)), index=index)
    rows = [int(v) for v in s.groupby([index.year, index.month]).max().values]
    last = index[-1]
    if next_session(last, nse_holidays() if holidays is None else holidays).month == last.month:
        rows = rows[:-1]
    return rows


def decision_rows(px, freq=FREQ):
    rows = month_end_rows(px.index)
    if freq == "Q":
        rows = [i for i in rows if px.index[i].month in (3, 6, 9, 12)]
    return [i for i in rows if (px.iloc[: i + 1].notna().sum() >= LONG + 1).sum() >= 50]


def backtest(px, nifty, sectors, holdings=HOLDINGS, guard=CASH_GUARD, max_w=MAX_WEIGHT, freq=FREQ, exit_sig=None):
    rets = px.pct_change(fill_method=None).fillna(0.0)
    cash_daily = (1 + CASH_YIELD) ** (1 / 252) - 1
    decisions = decision_rows(px, freq)
    if not decisions:
        raise SystemExit("Not enough history for the first decision")
    dset, start = set(decisions), decisions[0]
    nav, dates = [100.0], [px.index[start]]
    hold, cash, pending, flagged = pd.Series(dtype=float), 1.0, None, []
    history, turnover, n_exits = [], [], 0
    for i in range(start, len(px.index)):
        day = str(px.index[i].date())
        if i > start:
            grown = hold * (1 + rets.iloc[i].reindex(hold.index).fillna(0.0))
            cash_g = cash * (1 + cash_daily)
            total = grown.sum() + cash_g
            nav.append(nav[-1] * total)
            dates.append(px.index[i])
            hold, cash = grown / total, cash_g / total
            if pending is not None:            # month-end decision executes at this close
                target, tcash = pending
                names = target.index.union(hold.index)
                traded = float((target.reindex(names, fill_value=0) - hold.reindex(names, fill_value=0)).abs().sum())
                nav[-1] *= 1 - traded * COST_PER_SIDE
                hold, cash, pending, flagged = target.copy(), tcash, None, []
                history[-1].update(executed=day, turnover_pct=round(traded * 100, 1))
                turnover.append(traded)
            elif flagged:                      # downtrend exits signalled yesterday sell at this close
                sold = float(hold.reindex([f["symbol"] for f in flagged]).fillna(0).sum())
                nav[-1] *= 1 - sold * COST_PER_SIDE
                cash += sold
                hold = hold.drop([f["symbol"] for f in flagged], errors="ignore")
                for f in flagged:
                    f["sold_on"] = day
                    history[-1]["exits"].append(f)
                n_exits += len(flagged)
                flagged = []
        if i in dset:
            target, tcash, _ = build_portfolio(px, nifty, i, sectors, holdings, guard, max_w)
            pending = (target, tcash)
            history.append({"date": day, "executed": None, "cash_pct": round(tcash * 100, 2),
                            "turnover_pct": None, "guard_on": bool(tcash > 0), "exits": [],
                            "weights": {k: float(v) for k, v in target.sort_values(ascending=False).items()}})
        elif exit_sig is not None and len(hold):
            row = exit_sig.iloc[i].reindex(hold.index).fillna(False)
            flagged = [{"symbol": s, "signal_date": day, "close": round(float(px.iloc[i][s]), 2),
                        "dma200": None, "sold_on": None} for s in row[row].index]
    navs = pd.Series(nav, index=pd.DatetimeIndex(dates))
    bench = nifty.reindex(navs.index).ffill()
    r = px.pct_change(fill_method=None).reindex(navs.index)
    r.iloc[0] = 0.0
    ew = (1 + r.mean(axis=1).fillna(0.0)).cumprod() * 100
    years = (navs.index[-1] - navs.index[0]).days / 365.25
    return {"nav": navs, "bench": bench / bench.iloc[0] * 100, "ew": ew, "history": history,
            "pending_exits": flagged, "avg_turnover": float(np.mean(turnover)) if turnover else 0.0,
            "exits_per_year": n_exits / years if years else 0.0}


# ── Statistics ───────────────────────────────────────────────────────────────────────────
PERIODS = [("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 252), ("2Y", 504), ("3Y", 756), ("4Y", 1008)]


def trailing(series, n):
    s = series.dropna()
    return float(s.iloc[-1] / s.iloc[-1 - n] - 1) if len(s) > n else None


def cagr(series):
    yrs = (series.index[-1] - series.index[0]).days / 365.25
    return float((series.iloc[-1] / series.iloc[0]) ** (1 / yrs) - 1) if yrs > 0 else 0.0


def max_drawdown(series):
    return float((series / series.cummax() - 1).min())


def ann_vol(series):
    return float(series.pct_change().dropna().std() * math.sqrt(252))


def pct(x):
    return None if x is None else round(x * 100, 2)


def returns_table(lines):
    rows = []
    for label, n in PERIODS:
        vals = {k: trailing(v, n) for k, v in lines.items()}
        if vals["fund"] is None:
            continue
        yrs = n / 252
        if n > 252:
            vals = {k: (1 + v) ** (1 / yrs) - 1 for k, v in vals.items()}
        rows.append({"period": label, "annualised": n > 252, **{k: pct(v) for k, v in vals.items()}})
    rows.append({"period": "Since inception", "annualised": True, **{k: pct(cagr(v)) for k, v in lines.items()}})
    return rows


def calendar_years(lines):
    nav = lines["fund"]
    out = []
    for y in sorted(set(nav.index.year)):
        row = {"year": int(y), "partial": bool(y in (nav.index[0].year, nav.index[-1].year))}
        for k, s in lines.items():
            before = s[s.index.year < y]
            start = before.iloc[-1] if len(before) else s.iloc[0]
            row[k] = pct(s[s.index.year == y].iloc[-1] / start - 1)
        out.append(row)
    return out


def monthly_returns(nav, bench):
    f, b = nav.resample("ME").last(), bench.resample("ME").last()
    rf, rb = f.pct_change(), b.pct_change()
    rf.iloc[0], rb.iloc[0] = f.iloc[0] / nav.iloc[0] - 1, b.iloc[0] / bench.iloc[0] - 1
    return [{"month": d.strftime("%Y-%m"), "fund": pct(rf[d]), "nifty50": pct(rb[d])} for d in f.index]


def xirr(flows):
    t0 = flows[0][0]

    def npv(r):
        return sum(c / (1 + r) ** ((d - t0).days / 365.25) for d, c in flows)
    lo, hi = -0.95, 5.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if npv(mid) > 0 else (lo, mid)
    return (lo + hi) / 2


def sip_simulation(lines, amount):
    nav = lines["fund"]
    firsts = nav.groupby([nav.index.year, nav.index.month]).head(1).index
    out = {"monthly": amount, "months": len(firsts), "since": str(firsts[0].date()), "invested": round(amount * len(firsts))}
    for k, s in lines.items():
        value = sum(amount / s[d] for d in firsts) * s.iloc[-1]
        out[k] = {"value": round(value), "xirr": pct(xirr([(d, -amount) for d in firsts] + [(s.index[-1], value)]))}
    return out


def variants(px, nifty, sectors, signals):
    rows = []
    for n, freq, rule, guard in VARIANTS:
        bt = backtest(px, nifty, sectors, holdings=n, guard=guard, max_w=max(MAX_WEIGHT, 1.5 / n),
                      freq=freq, exit_sig=signals[rule])
        nav = bt["nav"]
        years = calendar_years({"fund": nav})
        rows.append({"holdings": n, "freq": "monthly" if freq == "M" else "quarterly", "exit": EXIT_WORDS[rule],
                     "cash_guard_pct": round(guard * 100), "cagr": pct(cagr(nav)), "max_drawdown": pct(max_drawdown(nav)),
                     "volatility": pct(ann_vol(nav)), "one_year": pct(trailing(nav, 252)),
                     "worst_year": min(y["fund"] for y in years), "best_year": max(y["fund"] for y in years),
                     "exits_per_year": round(bt["exits_per_year"]),
                     "live": (n, freq, rule, guard) == (HOLDINGS, FREQ, EXIT_RULE, CASH_GUARD)})
    return rows


def stock_returns(series):
    return {label: pct(trailing(series, n)) for label, n in
            [("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 252), ("3Y", 756), ("5Y", 1260)]}


def load_setups():
    p = DOCS / "daily_setups.json"
    if not p.exists():
        return {}, None
    d = json.loads(p.read_text(encoding="utf-8"))
    return {s["symbol"]: s for s in d.get("stocks", [])}, d.get("as_of")


def jev_fields(s):
    jev = s.get("jev") or {}
    comp = jev.get("composite")
    return {"jev_score": round(comp * 100, 1) if isinstance(comp, (int, float)) else None,
            "jev_rank": jev.get("rank"), "jev_of": jev.get("of"), "jev_direction": jev.get("direction"),
            "jev_regime": jev.get("regime"), "jev_confidence": pct(jev.get("confidence")) if isinstance(jev.get("confidence"), (int, float)) else None,
            "jev_agrees": jev.get("agrees"), "jev_signal": jev.get("signal")}


def published(weights, cash_pct):
    w = pd.Series(weights, dtype=float)
    if cash_pct:
        w = pd.concat([w, pd.Series({"CASH": cash_pct / 100})])
    return round_to_100(w) if len(w) and w.sum() > 0 else pd.Series({"CASH": 100.0})


# ── Build ────────────────────────────────────────────────────────────────────────────────
def build():
    membership = refresh_universe()
    universe = load_universe()
    meta = {u["symbol"]: u for u in universe}
    sectors = {u["symbol"]: u["sector"] for u in universe}
    px, high, low, nifty = load_prices([u["symbol"] for u in universe])
    signals, st = exit_signals(px, high, low)
    today = px.index[-1]
    last = len(px.index) - 1

    bt = backtest(px, nifty, sectors, exit_sig=signals[EXIT_RULE])
    nav, bench, ew, history = bt["nav"], bt["bench"], bt["ew"], bt["history"]
    lines = {"fund": nav, "nifty50": bench, "ew100": ew}
    current = history[-1]
    target = published(current["weights"], current["cash_pct"])
    sold = {e["symbol"]: e for e in current["exits"]}
    selling = {e["symbol"]: e for e in bt["pending_exits"]}

    # Weights for money invested now: sold / selling stocks' share moves to the liquid fund.
    now_w = current["weights"].copy()
    moved = sum(now_w.pop(s, 0.0) for s in list(sold) + list(selling))
    now = published(now_w, current["cash_pct"] + moved * 100)
    stock_now = now.drop("CASH", errors="ignore")

    setups, setups_asof = load_setups()
    div_data, div_bonus = load_div_bonus()
    ranked = score_universe(px, last, div_bonus=div_bonus)
    mom_rank = {s: i + 1 for i, s in enumerate(ranked.index)}
    dma200_today = px.iloc[-DMA:].mean()

    holdings = []
    for rank, sym in enumerate(target.drop("CASH", errors="ignore").sort_values(ascending=False).index, 1):
        s, series = setups.get(sym, {}), px[sym].dropna()
        plan = s.get("plan") or {}
        status = "sold" if sym in sold else "selling" if sym in selling else "held"
        holdings.append({
            "rank": rank, "symbol": sym, "name": meta[sym]["name"], "sector": meta[sym]["sector"],
            "status": status, "exit": sold.get(sym) or selling.get(sym),
            "weight_pct": float(stock_now.get(sym, 0.0)), "target_weight_pct": float(target[sym]),
            "close": round(float(series.iloc[-1]), 2), "dma200": round(float(dma200_today[sym]), 2),
            "returns": stock_returns(series),
            "volatility_pct": pct(float(ranked.loc[sym, "vol"])) if sym in ranked.index else None,
            "momentum_rank": mom_rank.get(sym),
            "supertrend_up": bool(st[sym].iloc[-1] == 1),
            "category": s.get("category"), "structure": s.get("structure"),
            "structure_exit": s.get("structure_exit"), "stop": plan.get("stop"), "plan_side": plan.get("side"),
            "next_target": plan.get("next_target"), "summary": s.get("summary"),
            "div_yield": div_data.get(sym, {}).get("current_yield", 0),
            "div_years": div_data.get(sym, {}).get("years_paid", 0),
            "div_bonus": round(div_bonus.get(sym, 0), 4),
            **jev_fields(s),
        })

    # All 100 ranked today: momentum order first, then the stocks that do not qualify.
    jev_order = sorted((u["symbol"] for u in universe if (setups.get(u["symbol"], {}).get("jev") or {}).get("composite") is not None),
                       key=lambda x: -setups[x]["jev"]["composite"])
    jev_rank100 = {s: i + 1 for i, s in enumerate(jev_order)}
    in_fund = {h["symbol"]: h for h in holdings}
    hist_len = px.notna().sum()
    all100 = []
    for u in universe:
        sym = u["symbol"]
        s = setups.get(sym, {})
        h = in_fund.get(sym)
        if h and h["status"] == "held":
            status = "In the fund"
        elif h:
            status = "Sold: closed below 200-day average" if h["status"] == "sold" else "Selling next session: closed below 200-day average"
        elif sym in mom_rank:
            status = "Would enter if rebalanced today" if mom_rank[sym] <= HOLDINGS else "Qualifies, ranked below the top 50"
        elif hist_len.get(sym, 0) < LONG + 1:
            status = "Under 1 year of prices"
        else:
            status = "Below 200-day average: not eligible"
        all100.append({"symbol": sym, "name": u["name"], "sector": u["sector"], "status": status,
                       "in_fund": bool(h and h["status"] == "held"), "weight_pct": h["weight_pct"] if h else 0.0,
                       "momentum_rank": mom_rank.get(sym), "jev_rank100": jev_rank100.get(sym),
                       "close": round(float(px[sym].dropna().iloc[-1]), 2), "returns": stock_returns(px[sym]),
                       "above_200dma": bool(px[sym].iloc[-1] > dma200_today[sym]),
                       "supertrend_up": bool(st[sym].iloc[-1] == 1), "category": s.get("category"),
                       "div_yield": div_data.get(sym, {}).get("current_yield", 0),
                       "div_years": div_data.get(sym, {}).get("years_paid", 0),
                       **jev_fields(s)})
    all100.sort(key=lambda r: (r["momentum_rank"] is None, r["momentum_rank"] or 999, -(r["jev_score"] or 0)))
    for i, r in enumerate(all100, 1):
        r["position"] = i

    held = [h for h in holdings if h["status"] == "held"]
    jev_view = {"up": 0, "down": 0, "sideways": 0, "none": 0}
    for h in held:
        d = h["jev_direction"]
        jev_view[d if d in jev_view else "none"] += 1
    scored = [h["jev_score"] for h in held if h["jev_score"] is not None]

    prev = published(history[-2]["weights"], history[-2]["cash_pct"]) if len(history) > 1 else pd.Series(dtype=float)
    added = sorted(set(target.index) - set(prev.index) - {"CASH"})
    removed = sorted(set(prev.index) - set(target.index) - {"CASH"})

    sectors_now = {}
    for h in holdings:
        if h["weight_pct"]:
            sectors_now[h["sector"]] = round(sectors_now.get(h["sector"], 0) + h["weight_pct"], 2)
    if "CASH" in now:
        sectors_now["Cash · liquid fund"] = float(now["CASH"])

    decided_today = current["date"] == str(today.date())
    next_dec = today + (pd.offsets.BMonthEnd(1) if decided_today or today == today + pd.offsets.BMonthEnd(0)
                        else pd.offsets.BMonthEnd(0))
    weekly_idx = nav.resample("W-FRI").last().dropna().index
    wk = {k: v.reindex(weekly_idx, method="ffill") for k, v in lines.items()}
    dd = (nav / nav.cummax() - 1).reindex(weekly_idx, method="ffill")
    cash_now = float(now.get("CASH", 0.0))

    payload = {
        "version": 3, "name": FUND_NAME, "as_of": str(today.date()), "setups_as_of": setups_asof,
        "membership_source": membership, "inception": str(nav.index[0].date()),
        "nav": round(float(nav.iloc[-1]), 2),
        "portfolio": {
            "decided_on": current["date"], "executed_on": current["executed"],
            "status": ("New portfolio decided at today's close. The fund buys it at the next trading session's close." if not current["executed"]
                       else f"Bought at the close of {current['executed']}; held until the next month-end decision unless a stock closes below its 200-day average."),
            "next_decision": str(next_dec.date()),
            "guard_on": current["guard_on"], "cash_pct": cash_now,
            "stock_pct": round(float(stock_now.sum()), 2), "holdings_count": int((stock_now > 0).sum()),
            "sold_count": len(sold), "selling_count": len(selling),
            "total_pct": round(float(now.sum()), 2),
            "guard_words": (f"Nifty 50 closed below its 200-day average on {current['date']}, so the market guard keeps "
                            f"{current['cash_pct']:.0f}% in a liquid fund this month."
                            if current["guard_on"] else
                            f"Nifty 50 was above its 200-day average on {current['date']}, so the fund is fully in stocks."),
        },
        "jev": {"held_scored": len(scored), "held": len(held),
                "avg_score": round(sum(scored) / len(scored), 1) if scored else None,
                "views": jev_view, "setups_as_of": setups_asof,
                "words": "Jev is shown for every stock but does not pick stocks yet: its scores exist only for the last few "
                         "sessions, so they cannot be backtested. The momentum rules have a 4-year backtest. Jev's daily "
                         "calls are logged, and once a year of them exists they can be tested as a filter."},
        "holdings": holdings,
        "all100": all100,
        "sector_allocation": dict(sorted(sectors_now.items(), key=lambda kv: -kv[1])),
        "changes": {"added": added, "removed": removed, "turnover_pct": current["turnover_pct"],
                    "sold": list(sold.values()), "selling": list(selling.values())},
        "stats": {
            "cagr": {k: pct(cagr(v)) for k, v in lines.items()},
            "max_drawdown": {k: pct(max_drawdown(v)) for k, v in lines.items()},
            "volatility": {k: pct(ann_vol(v)) for k, v in lines.items()},
            "growth_of_1L": {k: round(100000 * v.iloc[-1] / v.iloc[0]) for k, v in lines.items()},
            "years": round((nav.index[-1] - nav.index[0]).days / 365.25, 2),
            "avg_monthly_turnover_pct": round(bt["avg_turnover"] * 100, 1),
            "exits_per_year": round(bt["exits_per_year"]),
            "months_in_guard": sum(1 for h in history if h["guard_on"]), "months": len(history),
        },
        "returns": returns_table(lines),
        "calendar_years": calendar_years(lines),
        "monthly_returns": monthly_returns(nav, bench),
        "sip": sip_simulation(lines, DEFAULT_SIP),
        "nav_series": {"dates": [str(d.date()) for d in weekly_idx],
                       **{k: [round(float(x), 2) for x in v] for k, v in wk.items()},
                       "drawdown": [round(float(x) * 100, 2) for x in dd]},
        "history": [{"date": h["date"], "executed": h["executed"], "guard_on": h["guard_on"],
                     "turnover_pct": h["turnover_pct"], "exits": h["exits"],
                     "weights": {k: float(v) for k, v in published(h["weights"], h["cash_pct"]).sort_values(ascending=False).items()}}
                    for h in reversed(history)],
        "variants": variants(px, nifty, sectors, signals),
        "real_world": REAL_WORLD,
        "rules": {
            "holdings": HOLDINGS, "max_weight_pct": MAX_WEIGHT * 100, "max_sector_pct": MAX_SECTOR * 100,
            "cash_guard_pct": CASH_GUARD * 100, "cash_yield_pct": CASH_YIELD * 100, "cost_per_side_pct": COST_PER_SIDE * 100,
            "text": [
                "Universe: the official Nifty 100 (Nifty 50 + Nifty Next 50), refreshed from niftyindices.com.",
                "On the last trading session of every month, each stock is scored on its 6- and 12-month return per unit of risk (the NSE momentum-index method). Only stocks above their 200-day average with a full year of prices qualify.",
                f"The fund holds the best {HOLDINGS}. Weight = score ÷ volatility, at most {MAX_WEIGHT*100:.0f}% in one stock and {MAX_SECTOR*100:.0f}% in one sector. Weights are rounded so the total is exactly 100%.",
                "Downtrend exit, checked after every close: if a held stock closes below its 200-day average, it is sold at the next session's close and the money waits in a liquid fund until the month-end rebalance.",
                f"Market guard: if the Nifty 50 closes below its 200-day average on decision day, {CASH_GUARD*100:.0f}% goes to a liquid fund (assumed {CASH_YIELD*100:.1f}% a year) until the next month.",
                f"All trades happen at the next session's close. {COST_PER_SIDE*100:.1f}% is charged on every rupee bought or sold.",
            ],
        },
        "limits": [
            "The backtest starts in September 2022 because each stock needs one year of prices before it can be scored; the price file holds about five years.",
            "Uses today's Nifty 100 members back in time. Stocks that dropped out of the index are missing, which flatters past returns (survivorship bias).",
            "Stock prices are dividend-adjusted; the Nifty 50 line is the price index without dividends (about 1.2% a year in the fund's favour). The equal-weight Nifty 100 uses the same adjusted prices, so it is the fairer comparison.",
            "Taxes (20% on gains held under a year, 12.5% after), DP charges and real fills are not modelled. Turnover is high, so a real investor keeps less.",
            "Four years include no crash like 2008 (when the momentum index fell 61%). Past returns of a rule do not guarantee future returns. Paper research, not SEBI-registered advice.",
        ],
    }
    text = json.dumps(payload, separators=(",", ":"))
    DOCS.mkdir(exist_ok=True)
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    (DOCS / "fund.json").write_text(text, encoding="utf-8")
    (PUBLIC_DATA / "fund.json").write_text(text, encoding="utf-8")
    st_, pf = payload["stats"], payload["portfolio"]
    print(f"fund.json as_of {payload['as_of']}: {pf['holdings_count']} stocks {pf['stock_pct']}% + cash {pf['cash_pct']}% "
          f"= {pf['total_pct']}%; decided {pf['decided_on']} executed {pf['executed_on']}; CAGR fund {st_['cagr']['fund']}% "
          f"/ Nifty50 {st_['cagr']['nifty50']}% / EW100 {st_['cagr']['ew100']}% over {st_['years']}y; max DD "
          f"{st_['max_drawdown']['fund']}%; exits/yr {st_['exits_per_year']}; Jev scored {payload['jev']['held_scored']}/{payload['jev']['held']}")
    return payload


if __name__ == "__main__":
    build()
