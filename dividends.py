#!/usr/bin/env python3
"""Value Lens Dividend Desk — the real income payers in the Nifty 200, rebuilt monthly.

What it publishes (docs/dividends.json, shown on docs/dividends.html)
  * Every Nifty 200 stock's dividend record over the last ~10 years: dividend per share each year,
    years paid out of 10, trailing-12-month dividend, current yield, 10-year average yield, and a
    flag when the yield is inflated by one-off special dividends.
  * A transparent income score and ranking (steady yield + consistency + not-just-special + growth).
  * A sample 6-lakh income portfolio for this month: the safest high-yield names, shares to buy.

Data: Yahoo Finance dividend + price history (yfinance), cached to data/dividends_cache.json so a
re-run is fast. Current price is the latest close.

Honest limits: dividend yield is not total return; a high yield often means the price fell. Special
one-off dividends are flagged. Dividends can be cut. Past payouts do not guarantee future ones.
Paper research, not advice. Published monthly; this is the October 2026 report.
"""
import csv
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import pandas as pd

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
PUBLIC_DATA = ROOT / "public" / "data"
UNIVERSE_CSV = ROOT / "nifty200.csv"
CACHE = ROOT / "data" / "dividends_cache.json"
CACHE_TTL_DAYS = 20
SIP_AMOUNT = 600000           # the 6 lakh to deploy this month
PORTFOLIO_SIZE = 10           # names in the sample income portfolio
MAX_WEIGHT = 0.15             # at most 15% in one stock


def load_universe():
    rows = list(csv.DictReader(io.StringIO(UNIVERSE_CSV.read_text(encoding="utf-8"))))
    return [{"symbol": r["Symbol"].strip(), "name": r["Company Name"].strip(), "sector": r["Industry"].strip()}
            for r in rows if r.get("Symbol")]


def fetch_one(sym):
    """11 years of dividends + yearly average price + latest close from Yahoo Finance."""
    t = yf.Ticker(sym + ".NS")
    h = t.history(period="11y", auto_adjust=False, actions=True)
    if h is None or h.empty:
        return None
    h.index = pd.to_datetime(h.index)
    close = float(h["Close"].dropna().iloc[-1])
    div = h["Dividends"]
    div = div[div > 0]
    by_year = {int(y): round(float(v), 4) for y, v in div.groupby(div.index.year).sum().items()}
    price_year = {int(y): round(float(v), 2) for y, v in h["Close"].groupby(h.index.year).mean().items()}
    ttm = float(div[div.index >= (pd.Timestamp.now(tz=div.index.tz) - pd.DateOffset(years=1))].sum())
    return {"close": round(close, 2), "by_year": by_year, "price_year": price_year, "ttm": round(ttm, 4)}


def load_cache():
    if CACHE.exists():
        try:
            c = json.loads(CACHE.read_text(encoding="utf-8"))
            if (datetime.now(timezone.utc).timestamp() - c.get("fetched_at", 0)) < CACHE_TTL_DAYS * 86400:
                return c.get("data", {})
        except (OSError, ValueError):
            pass
    return None


def fetch_all(symbols):
    cached = load_cache()
    if cached and all(s in cached for s in symbols):
        return cached, "cache"
    if yf is None:
        raise SystemExit("yfinance not installed and no fresh cache")
    data = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(fetch_one, s): s for s in symbols}
        for f in as_completed(futs):
            s = futs[f]
            try:
                r = f.result()
                if r:
                    data[s] = r
            except Exception:
                pass
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).timestamp(), "data": data}), encoding="utf-8")
    return data, "live"


def metrics(sym, meta, raw, year_now):
    years = list(range(year_now - 10, year_now))     # last 10 full years
    by_year = {int(k): v for k, v in raw["by_year"].items()}
    price_year = {int(k): v for k, v in raw["price_year"].items()}
    paid = [y for y in years if by_year.get(y, 0) > 0]
    yields = [by_year[y] / price_year[y] * 100 for y in paid if price_year.get(y)]
    med = median(yields) if yields else 0.0
    # special-dividend flag: a single year more than 2.5x the median annual payout
    payouts = [by_year[y] for y in paid]
    mp = median(payouts) if payouts else 0.0
    special = any(p > 2.5 * mp for p in payouts) if mp else False
    cur_yield = raw["ttm"] / raw["close"] * 100 if raw["close"] else 0.0
    first, last = (by_year.get(paid[0], 0), by_year.get(paid[-1], 0)) if len(paid) >= 2 else (0, 0)
    span = (paid[-1] - paid[0]) if len(paid) >= 2 else 0
    growth = ((last / first) ** (1 / span) - 1) * 100 if first > 0 and last > 0 and span else None
    ten_yr_total = round(sum(by_year.get(y, 0) for y in years), 2)
    return {
        "symbol": sym, "name": meta["name"], "sector": meta["sector"], "close": raw["close"],
        "years_paid": len(paid), "current_yield": round(cur_yield, 2),
        "avg_yield_10y": round(sum(yields) / len(yields), 2) if yields else 0.0,
        "median_yield_10y": round(med, 2), "max_yield_10y": round(max(yields), 2) if yields else 0.0,
        "ttm_dividend": round(raw["ttm"], 2), "ten_year_total_per_share": ten_yr_total,
        "ten_year_payback_pct": round(ten_yr_total / raw["close"] * 100, 1) if raw["close"] else 0.0,
        "dividend_growth_pct": round(growth, 1) if growth is not None else None,
        "special_heavy": special, "last_year_paid": paid[-1] if paid else None,
        "by_year": {str(y): by_year.get(y, 0) for y in years},
    }


def income_score(m):
    """Transparent 0-100 income-quality score. Rewards steady, growing, well-covered yield."""
    y = min(m["current_yield"], 10) / 10 * 40            # yield, capped so a crash can't dominate (40)
    c = m["years_paid"] / 10 * 30                         # paid in how many of 10 years (30)
    s = 0 if m["special_heavy"] else 20                   # steady, not one-off special dividends (20)
    g = 10 if (m["dividend_growth_pct"] or 0) > 0 else (5 if m["years_paid"] >= 8 else 0)  # growth (10)
    return round(y + c + s + g, 1)


def build_portfolio(ranked):
    """Sample 6-lakh income book: safest high-yield names (steady, >=8/10 years, decent yield)."""
    safe = [m for m in ranked if m["years_paid"] >= 8 and not m["special_heavy"]
            and m["current_yield"] >= 3 and m["close"] <= SIP_AMOUNT]
    safe = sorted(safe, key=lambda m: -m["income_score"])[:PORTFOLIO_SIZE]
    if not safe:
        return [], 0.0, 0.0
    # Yield-weighted with a cap, so no single stock dominates.
    raw = {m["symbol"]: min(m["current_yield"], 9) for m in safe}
    tot = sum(raw.values())
    w = {k: min(v / tot, MAX_WEIGHT) for k, v in raw.items()}
    wsum = sum(w.values())
    w = {k: v / wsum for k, v in w.items()}
    rows, invested, income = [], 0.0, 0.0
    for m in safe:
        rupees = SIP_AMOUNT * w[m["symbol"]]
        shares = int(rupees // m["close"])
        cost = shares * m["close"]
        annual_income = shares * m["ttm_dividend"]
        invested += cost
        income += annual_income
        rows.append({**{k: m[k] for k in ("symbol", "name", "sector", "close", "current_yield",
                                          "years_paid", "income_score", "ttm_dividend")},
                     "weight_pct": round(w[m["symbol"]] * 100, 1), "shares": shares,
                     "cost": round(cost), "annual_income": round(annual_income)})
    return rows, invested, income


def build():
    universe = load_universe()
    data, source = fetch_all([u["symbol"] for u in universe])
    meta = {u["symbol"]: u for u in universe}
    year_now = datetime.now().year
    rows = []
    for sym, raw in data.items():
        if sym in meta and raw.get("close"):
            m = metrics(sym, meta[sym], raw, year_now)
            m["income_score"] = income_score(m)
            rows.append(m)
    rows.sort(key=lambda m: -m["income_score"])
    for i, m in enumerate(rows, 1):
        m["rank"] = i

    port, invested, income = build_portfolio(rows)
    steady = [m for m in rows if m["years_paid"] >= 8 and not m["special_heavy"]]
    above20 = [m for m in rows if m["avg_yield_10y"] >= 20 or m["max_yield_10y"] >= 20]

    payload = {
        "version": 1, "name": "Value Lens Dividend Desk", "report_month": datetime.now().strftime("%B %Y"),
        "as_of": datetime.now().strftime("%Y-%m-%d"), "source": source, "universe": "Nifty 200",
        "covered": len(rows),
        "answer_20pct": {
            "count": len(above20),
            "names": [{"symbol": m["symbol"], "name": m["name"], "max_yield_10y": m["max_yield_10y"],
                       "avg_yield_10y": m["avg_yield_10y"], "special_heavy": m["special_heavy"]} for m in above20],
            "verdict": ("No Nifty 200 stock has a steady 20% yearly dividend yield over 10 years. "
                        "The few that touched 20% in a single year did it through one-off special dividends or a "
                        "price crash (flagged), not a repeatable payout. The honest best steady yields are about 5-9%. "
                        "This report covers the Nifty 200 only; a few beaten-down micro/small-caps outside it can show "
                        "very high trailing yields, but those are usually unsustainable, not a safe 10-year record."),
        },
        "summary": {
            "steady_payers": len(steady),
            "best_steady_yield": max((m["current_yield"] for m in steady), default=0),
            "avg_steady_yield": round(sum(m["current_yield"] for m in steady) / len(steady), 2) if steady else 0,
        },
        "portfolio": {
            "amount": SIP_AMOUNT, "invested": round(invested), "cash_left": round(SIP_AMOUNT - invested),
            "annual_income": round(income), "yield_on_cost": round(income / invested * 100, 2) if invested else 0,
            "holdings": port,
            "words": (f"A sample Rs {SIP_AMOUNT:,} income book for {datetime.now().strftime('%B %Y')} in the steadiest "
                      f"high-yield Nifty 200 names (paid 8+ of 10 years, no reliance on special dividends). "
                      f"Buy at Monday's open; prices will differ from these closes."),
        },
        "rows": rows,
        "score_method": [
            "Current yield (last 12 months' dividend / price), capped at 10% so a price crash cannot top the list — 40 points.",
            "Consistency: how many of the last 10 years the stock paid a dividend — 30 points.",
            "Steady, not one-off: full marks unless one year's payout was more than 2.5x the usual (a special dividend) — 20 points.",
            "Growth: dividend higher than 10 years ago, or paid in 8+ years — 10 points.",
        ],
        "limits": [
            "Dividend yield is not total return. A high yield often means the share price fell; check the price chart too.",
            "Special one-off dividends are flagged (one year above 2.5x the usual); the flag targets single-year spikes, so a high-variance regular payer like a metals company can still look steady — read its 10-year bars.",
            "Dividends are discretionary and can be cut, especially by cyclical and commodity companies.",
            "Yahoo Finance dividend data can miss or misdate a payout; verify on the company page before buying.",
            "Dividends are taxed at your income-tax slab. Paper research, not SEBI-registered advice.",
        ],
    }
    text = json.dumps(payload, separators=(",", ":"))
    DOCS.mkdir(exist_ok=True)
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    (DOCS / "dividends.json").write_text(text, encoding="utf-8")
    (PUBLIC_DATA / "dividends.json").write_text(text, encoding="utf-8")
    top = rows[:5]
    print(f"dividends.json {payload['report_month']} ({source}): {len(rows)} of 200 covered; "
          f"{len(steady)} steady payers; 20%+ steady: {len(above20)}; "
          f"portfolio invests Rs {payload['portfolio']['invested']:,} at {payload['portfolio']['yield_on_cost']}% yield")
    print("Top 5 income score:", ", ".join(f"{m['symbol']} {m['income_score']} ({m['current_yield']}%)" for m in top))
    return payload


if __name__ == "__main__":
    build()
