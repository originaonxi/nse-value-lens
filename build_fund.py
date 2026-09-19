#!/usr/bin/env python3
"""
Open Mutual Fund — Portfolio Constructor
========================================
Turns the momentum screen (screen_output/quant_upgrade_master.csv) into an
actually-investable Rs 10,00,000 portfolio.

Rules (locked in from project spec):
  seed        : Rs 10,00,000
  universe    : strict gate = in_fno AND above 200-DMA AND 200-DMA rising
  rank        : z(RAM) = z-score of (12-1 momentum / annualised vol), desc
  hold        : top 15 (min 2 enforced)
  weighting   : proportional to max(z_ram, 0), capped at CAP per name, renormalised
  execution   : integer shares = floor(target_rupees / price); leftover -> cash
  rebalance   : monthly (re-run after each monthly screen)

Outputs (screen_output/):
  fund_portfolio.json   full holdings + weights + cash + metadata
  fund_portfolio.csv    flat holdings table
  openalgo_basket.json  PAPER-ONLY basket by default; live quantities require explicit env unlock
"""
import csv
import json
import os
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "screen_output"
MASTER = OUT / "quant_upgrade_master.csv"

SEED = 1_000_000          # Rs 10 lakh
TOP_N = 15               # target holdings
CAP = 0.12               # max single-name weight (12%)
MIN_HOLDINGS = 2         # never a single-stock fund
LIVE_UNLOCK_ENV = "NSE_MOMENTUM30_LIVE_TRADING"
LIVE_UNLOCK_VALUE = "I_UNDERSTAND_RISK_ENABLE_LIVE"


def live_trading_enabled():
    """Manual hard gate: no live OpenAlgo-ready quantities unless explicitly unlocked."""
    return os.environ.get(LIVE_UNLOCK_ENV) == LIVE_UNLOCK_VALUE



def load_candidates():
    rows = list(csv.DictReader(open(MASTER, newline="", encoding="utf-8-sig")))
    def truthy(v):
        return str(v).strip().lower() in ("true", "1", "yes")
    gate = [
        r for r in rows
        if truthy(r.get("in_fno")) and truthy(r.get("above_dma")) and truthy(r.get("dma_rising"))
    ]
    for r in gate:
        r["_z"] = float(r.get("z_ram") or 0.0)
        r["_price"] = float(r.get("price") or 0.0)
    gate = [r for r in gate if r["_price"] > 0]
    gate.sort(key=lambda r: r["_z"], reverse=True)
    return gate


def apply_cap(weights, cap):
    """Iteratively cap weights at `cap` and redistribute excess to uncapped names."""
    w = dict(weights)
    for _ in range(100):
        total = sum(w.values())
        w = {k: v / total for k, v in w.items()}
        over = {k: v for k, v in w.items() if v > cap + 1e-9}
        if not over:
            break
        excess = sum(v - cap for v in over.values())
        for k in over:
            w[k] = cap
        under = {k: v for k, v in w.items() if v < cap - 1e-9}
        pool = sum(under.values())
        if pool <= 0:
            break
        for k in under:
            w[k] += excess * (under[k] / pool)
    return w


def build():
    cands = load_candidates()
    if len(cands) < MIN_HOLDINGS:
        raise SystemExit(f"Only {len(cands)} names pass the strict gate; need >= {MIN_HOLDINGS}.")

    picks = cands[:TOP_N]
    raw = {r["symbol"]: max(r["_z"], 0.0) for r in picks}
    if sum(raw.values()) <= 0:
        raw = {k: 1.0 for k in raw}  # degenerate: equal weight
    weights = apply_cap(raw, CAP)

    holdings = []
    deployed = 0.0
    for r in picks:
        sym = r["symbol"]
        wt = weights[sym]
        target = SEED * wt
        price = r["_price"]
        shares = int(target // price)
        value = shares * price
        deployed += value
        holdings.append({
            "symbol": sym,
            "name": r.get("name", ""),
            "target_weight_pct": round(wt * 100, 2),
            "price": round(price, 2),
            "shares": shares,
            "value_rs": round(value, 2),
            "actual_weight_pct": 0.0,   # filled after total known
            "z_ram": round(r["_z"], 3),
            "mom12_pct": float(r.get("mom12%") or 0),
            "vol_pct": float(r.get("vol%") or 0),
        })

    cash = round(SEED - deployed, 2)
    for h in holdings:
        h["actual_weight_pct"] = round(h["value_rs"] / SEED * 100, 2)

    live_enabled = live_trading_enabled()
    portfolio = {
        "fund": "NSE 200 Momentum 30 Algorithm Prediction — research scaffold portfolio",
        "as_of": date.today().isoformat(),
        "seed_rs": SEED,
        "deployed_rs": round(deployed, 2),
        "cash_rs": cash,
        "cash_pct": round(cash / SEED * 100, 2),
        "holdings_count": len(holdings),
        "method": "z(RAM) score-weighted, 12% cap, top 15, strict F&O+rising-200DMA gate",
        "rebalance": "monthly",
        "gate_pass_count": len(cands),
        "trading_mode": "LIVE_UNLOCKED" if live_enabled else "PAPER_ONLY_BLOCKED",
        "live_unlock_required": f"Manual server-side unlock required via {LIVE_UNLOCK_ENV}; exact confirmation value is intentionally not emitted in generated artifacts.",
        "holdings": holdings,
    }

    (OUT / "fund_portfolio.json").write_text(json.dumps(portfolio, indent=2), encoding="utf-8")

    with open(OUT / "fund_portfolio.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "name", "shares", "price", "value_rs", "weight_pct", "z_ram", "mom12_pct"])
        for h in holdings:
            w.writerow([h["symbol"], h["name"], h["shares"], h["price"],
                        h["value_rs"], h["actual_weight_pct"], h["z_ram"], h["mom12_pct"]])

    if live_enabled:
        orders = [
            {
                "symbol": h["symbol"],
                "exchange": "NSE",
                "action": "BUY",
                "quantity": h["shares"],
                "pricetype": "MARKET",
                "product": "CNC",
            }
            for h in holdings if h["shares"] > 0
        ]
        note = "LIVE UNLOCKED by explicit environment variable; review manually before sending to broker."
    else:
        orders = [
            {
                "symbol": h["symbol"],
                "exchange": "NSE",
                "action": "BUY",
                "quantity": 0,
                "paper_quantity": h["shares"],
                "pricetype": "MARKET",
                "product": "CNC",
                "blocked_reason": f"Paper-only mode. Manual server-side unlock via {LIVE_UNLOCK_ENV} is allowed only after verified walk-forward validation and manual approval.",
            }
            for h in holdings if h["shares"] > 0
        ]
        note = "PAPER ONLY: live order quantities are zeroed by default; paper_quantity shows simulation size."
    basket = {
        "strategy": f"NSE_MOMENTUM30_RESEARCH_{date.today().isoformat()}",
        "mode": "LIVE_UNLOCKED" if live_enabled else "PAPER_ONLY_BLOCKED",
        "_note": note,
        "orders": orders,
    }
    (OUT / "openalgo_basket.json").write_text(json.dumps(basket, indent=2), encoding="utf-8")

    print(f"Fund built: {len(holdings)} holdings")
    print(f"Deployed Rs {deployed:,.0f} | Cash Rs {cash:,.0f} ({portfolio['cash_pct']}%)")
    for h in holdings:
        print(f"  {h['symbol']:<12} {h['shares']:>5} sh x Rs {h['price']:>10,.2f} = Rs {h['value_rs']:>12,.0f}  ({h['actual_weight_pct']:>5}%)")
    return portfolio


if __name__ == "__main__":
    build()
