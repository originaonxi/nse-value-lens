#!/usr/bin/env python3
"""
Momentum-5: Pure-math top-5 from full Nifty 200 universe
=========================================================
Formula (no gates, no human filters — every stock competes equally):

  ram6  = mom6%  / vol%          ← Sharpe-like ratio per stock (same units cancel)
  ram12 = mom12% / vol%          ← same for 12-month window
  score = ( z(ram6) + z(ram12) ) / 2   ← z-score the ratios cross-sectionally, then average

  Rank descending → top 5 → equal weight ₹2,00,000 each (₹10L total)

Why this formula?
  - Combining 6m + 12m captures both medium and longer momentum
    (Nifty200 Momentum 30 uses the same two horizons [NSE methodology])
  - vol-adjust first, then z-score: ram=return%/vol% → z(ram) cross-sectionally
    → only relative risk-adjusted rank matters; avoids double-transformation
  - Cross-sectional z-score = only relative rank within universe matters,
    not absolute return level (avoids market-wide bias)
  - Equal weight within 5 = maximum simplicity, no score-weighting subjectivity
  - No DMA / F&O gate = pure maths as requested

Outputs (screen_output/):
  m5_portfolio.json   holdings + formula details
  m5_portfolio.csv    flat table
"""
import csv
import json
import statistics
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT  = HERE / "screen_output"
MASTER = OUT / "quant_upgrade_master.csv"

SEED     = 1_000_000   # Rs 10 lakh
N_PICKS  = 5
ALLOC    = SEED / N_PICKS  # Rs 2,00,000 per stock — equal weight


def zscore(values):
    """Cross-sectional z-score across all values."""
    mu = statistics.mean(values)
    sd = statistics.stdev(values)
    if sd == 0:
        return [0.0] * len(values)
    return [(v - mu) / sd for v in values]


def build():
    rows = list(csv.DictReader(open(MASTER, newline="", encoding="utf-8-sig")))

    # Parse numerics — use every row (no gate)
    stocks = []
    for r in rows:
        try:
            stocks.append({
                "symbol" : r["symbol"].strip(),
                "name"   : r.get("name", "").strip(),
                "mom12"  : float(r["mom12%"]),
                "mom6"   : float(r["mom6%"]),
                "vol"    : float(r["vol%"]),   # annualised %, keep same unit as mom%
                "price"  : float(r["price"]),
                "in_fno" : r.get("in_fno","").strip().lower() in ("true","1"),
                "above_dma": r.get("above_dma","").strip().lower() in ("true","1"),
                "dma_rising": r.get("dma_rising","").strip().lower() in ("true","1"),
                "last_bar": r.get("last_bar",""),
            })
        except (ValueError, KeyError):
            continue

    n = len(stocks)
    print(f"Universe: {n} stocks from Nifty 200")

    # Step 1: risk-adjust each return by its own vol (Sharpe-like ratio)
    #         ram = return% / vol%  → dimensionless, same units cancel
    # Step 2: z-score those ratios cross-sectionally across all 194 stocks
    # Step 3: average the two z-scores → final rank signal
    # This matches Nifty200 Momentum 30 index logic (normalise by vol first)
    ram6_list  = [s["mom6"]  / max(s["vol"], 1.0) for s in stocks]
    ram12_list = [s["mom12"] / max(s["vol"], 1.0) for s in stocks]

    zr6_list  = zscore(ram6_list)
    zr12_list = zscore(ram12_list)

    for i, s in enumerate(stocks):
        s["zr6"]   = zr6_list[i]
        s["zr12"]  = zr12_list[i]
        s["score"] = (zr6_list[i] + zr12_list[i]) / 2

    # Pure rank — no filter
    ranked = sorted(stocks, key=lambda s: s["score"], reverse=True)
    top5   = ranked[:N_PICKS]

    # Allocate equal weight
    deployed = 0.0
    holdings = []
    for rank, s in enumerate(top5, 1):
        shares = int(ALLOC // s["price"])
        value  = shares * s["price"]
        deployed += value
        holdings.append({
            "rank"       : rank,
            "symbol"     : s["symbol"],
            "name"       : s["name"],
            "score"      : round(s["score"], 4),
            "zr12"       : round(s["zr12"], 3),
            "zr6"        : round(s["zr6"], 3),
            "mom12_pct"  : round(s["mom12"], 1),
            "mom6_pct"   : round(s["mom6"], 1),
            "vol_pct"    : round(s["vol"], 1),
            "price"      : round(s["price"], 2),
            "shares"     : shares,
            "value_rs"   : round(value, 2),
            "target_rs"  : round(ALLOC, 2),
            "in_fno"     : s["in_fno"],
            "above_dma"  : s["above_dma"],
            "dma_rising" : s["dma_rising"],
        })

    cash = round(SEED - deployed, 2)

    portfolio = {
        "fund"          : "Momentum-5 (Pure Maths, Nifty 200)",
        "as_of"         : date.today().isoformat(),
        "seed_rs"       : SEED,
        "deployed_rs"   : round(deployed, 2),
        "cash_rs"       : cash,
        "cash_pct"      : round(cash / SEED * 100, 2),
        "universe_size" : n,
        "holdings_count": N_PICKS,
        "formula"       : "ram6=mom6%/vol%, ram12=mom12%/vol%  →  score=(z(ram6)+z(ram12))/2  |  top-5  |  equal weight Rs 2L each  |  no gates",
        "gates"         : "NONE — every Nifty 200 EQ stock competes equally",
        "rebalance"     : "monthly (re-run script)",
        "holdings"      : holdings,
    }

    (OUT / "m5_portfolio.json").write_text(json.dumps(portfolio, indent=2), encoding="utf-8")

    with open(OUT / "m5_portfolio.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank","symbol","name","score","zr12","zr6","mom12%","mom6%","vol%",
                    "price","shares","value_rs","in_fno","above_dma","dma_rising"])
        for h in holdings:
            w.writerow([h["rank"],h["symbol"],h["name"],h["score"],h["zr12"],h["zr6"],
                        h["mom12_pct"],h["mom6_pct"],h["vol_pct"],h["price"],
                        h["shares"],h["value_rs"],h["in_fno"],h["above_dma"],h["dma_rising"]])

    print(f"\nMomentum-5  |  Deployed ₹{deployed:,.0f}  |  Cash ₹{cash:,.0f}")
    print(f"{'#':<3} {'Symbol':<12} {'Score':>7} {'12m%':>7} {'6m%':>7} {'Vol%':>6} {'Shares':>7} {'Price':>10} {'Value':>12}  FnO  DMA")
    for h in holdings:
        fno = "✓" if h["in_fno"] else "✗"
        dma = "✓" if h["above_dma"] and h["dma_rising"] else "✗"
        print(f"{h['rank']:<3} {h['symbol']:<12} {h['score']:>7.3f} {h['mom12_pct']:>6.1f}% {h['mom6_pct']:>6.1f}% {h['vol_pct']:>5.1f}% {h['shares']:>7,} {h['price']:>10,.2f} {h['value_rs']:>12,.0f}  {fno}    {dma}")

    print(f"\nFormula: ram6=mom6%/vol%, ram12=mom12%/vol%  →  score=(z(ram6)+z(ram12))/2  |  No gates, pure maths")
    print(f"FnO = eligible for futures  |  DMA = above rising 200-day avg (info only, not a filter)")
    return portfolio


if __name__ == "__main__":
    build()
