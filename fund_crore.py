#!/usr/bin/env python3
"""₹1 crore in the Value Lens Nifty 100 Momentum Fund, one year back, in whole shares.

Same rules as fund.py (it calls fund.py's own scoring, weights, market guard and 200-day exit):
  * Decision on the last trading session of each month; the new portfolio is bought / sold at the next session's close.
  * Any day a held stock closes below its 200-day average, it is sold at the next session's close; the money waits in the
    liquid fund until the month-end rebalance.
  * Market guard: if the Nifty 50 is below its 200-day average on decision day, 50% stays in the liquid fund (6.5% a year).
  * 0.2% cost on every rupee bought or sold.
The only difference from fund.py's NAV: here every position is a whole number of shares and every trade is listed in rupees.

Run: python fund_crore.py   -> docs/fund_crore.json
"""
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import fund as F  # noqa: E402

DOCS, PUBLIC = ROOT / "docs", ROOT / "public" / "data"
CAPITAL = 1_00_00_000
TAX_STCG, TAX_LTCG = 0.20, 0.125


def replay(px, nifty, sectors, exit_sig, start_row):
    """Whole-share replay from the decision at `start_row` to the last close. Returns trades, rebalances, daily value."""
    idx = px.index
    cash_daily = (1 + F.CASH_YIELD) ** (1 / 252) - 1
    decisions = [i for i in F.decision_rows(px) if i >= start_row]
    dset = set(decisions)
    shares, cost_basis, bought_on = {}, {}, {}
    cash = float(CAPITAL)
    pending, flagged = None, []
    trades, rebal, daily = [], [], []
    fees = 0.0

    def value(i):
        return cash + sum(q * float(px.iloc[i][s]) for s, q in shares.items())

    def sell(i, s, q, why):
        nonlocal cash, fees
        p = float(px.iloc[i][s])
        amt = q * p
        fee = amt * F.COST_PER_SIDE
        cash += amt - fee
        fees += round(fee)                                   # total matches the rounded per-trade fees shown
        basis = cost_basis[s] * q / shares[s]
        pnl = amt - fee - basis
        trades.append({"date": str(idx[i].date()), "side": "SELL", "symbol": s, "shares": int(q), "price": round(p, 2),
                       "amount": round(amt), "fee": round(fee), "pnl": round(pnl), "why": why,
                       "held_days": int((idx[i] - bought_on[s]).days)})
        cost_basis[s] -= basis
        shares[s] -= q
        if shares[s] == 0:
            del shares[s], cost_basis[s], bought_on[s]
        return pnl

    def buy(i, s, q, why):
        nonlocal cash, fees
        p = float(px.iloc[i][s])
        amt = q * p
        fee = amt * F.COST_PER_SIDE
        cash -= amt + fee
        fees += round(fee)
        cost_basis[s] = cost_basis.get(s, 0.0) + amt + fee
        if s not in shares:
            bought_on[s] = idx[i]
        shares[s] = shares.get(s, 0) + q
        trades.append({"date": str(idx[i].date()), "side": "BUY", "symbol": s, "shares": int(q), "price": round(p, 2),
                       "amount": round(amt), "fee": round(fee), "pnl": None, "why": why, "held_days": None})

    for i in range(start_row, len(idx)):
        day = str(idx[i].date())
        if i > start_row:
            cash *= 1 + cash_daily
            if pending is not None:                               # month-end decision executes at this close
                target, tcash, dec_day = pending
                total = value(i)
                want = {s: int(math.floor(w * total / float(px.iloc[i][s]))) for s, w in target.items() if w > 0}
                added = sorted(set(want) - set(shares))
                removed = sorted(set(shares) - set(want))
                for s in list(shares):                            # sells first, so the cash is there for the buys
                    d = shares[s] - want.get(s, 0)
                    if d > 0:
                        sell(i, s, d, "rebalance: dropped" if s in removed else "rebalance: trimmed")
                for s, q in want.items():
                    d = q - shares.get(s, 0)
                    d = min(d, int(math.floor(max(cash, 0.0) / (float(px.iloc[i][s]) * (1 + F.COST_PER_SIDE)))))
                    if d > 0:                                     # never spend more cash than there is (fee included)
                        buy(i, s, d, "rebalance: new" if s in added else "rebalance: topped up")
                rebal.append({"decided": dec_day, "executed": day, "guard_on": bool(tcash > 0), "cash_pct": round(tcash * 100, 1),
                              "holdings": len(want), "added": added, "removed": removed,
                              "turnover": round(sum(t["amount"] for t in trades if t["date"] == day)),
                              "value_after": round(value(i))})
                pending, flagged = None, []
            elif flagged:                                         # 200-day exits signalled yesterday sell at this close
                for s in flagged:
                    if s in shares:
                        sell(i, s, shares[s], "closed below its 200-day average")
                flagged = []
        if i in dset:
            target, tcash, _ = F.build_portfolio(px, nifty, i, sectors)
            pending = (target, tcash, day)
        elif exit_sig is not None and shares:
            row = exit_sig.iloc[i].reindex(list(shares)).fillna(False)
            flagged = list(row[row].index)
        daily.append((day, value(i), cash))
    held = [{"symbol": s, "shares": int(q), "price": round(float(px.iloc[-1][s]), 2), "value": round(q * float(px.iloc[-1][s])),
             "cost": round(cost_basis[s]), "pnl": round(q * float(px.iloc[-1][s]) - cost_basis[s]),
             "since": str(bought_on[s].date()), "sector": sectors.get(s, "")} for s, q in shares.items()]
    held.sort(key=lambda h: -h["value"])
    return trades, rebal, daily, held, cash, fees, flagged


def build():
    F.refresh_universe()
    universe = F.load_universe()
    sectors = {u["symbol"]: u["sector"] for u in universe}
    names = {u["symbol"]: u["name"] for u in universe}
    px, high, low, nifty = F.load_prices([u["symbol"] for u in universe])
    signals, _ = F.exit_signals(px, high, low)
    exit_sig = signals[F.EXIT_RULE]
    year_ago = px.index[-1] - pd.DateOffset(years=1)
    dec = [i for i in F.decision_rows(px) if px.index[i] <= year_ago]
    start = dec[-1] if dec else F.decision_rows(px)[0]
    trades, rebal, daily, held, cash, fees, pending_exits = replay(px, nifty, sectors, exit_sig, start)

    dates = [d for d, _, _ in daily]
    vals = np.array([v for _, v, _ in daily])
    n0 = float(nifty.iloc[start])
    nif = CAPITAL * nifty.iloc[start:].to_numpy(float) / n0
    r = px.pct_change(fill_method=None).iloc[start:]
    r.iloc[0] = 0.0
    ew = CAPITAL * (1 + r.mean(axis=1).fillna(0.0)).cumprod().to_numpy()
    nav = F.backtest(px, nifty, sectors, exit_sig=exit_sig)["nav"]
    nav = nav[nav.index >= px.index[start]]
    nav_ret = float(nav.iloc[-1] / nav.iloc[0] - 1) * 100

    end = float(vals[-1])
    pk = np.maximum.accumulate(vals)
    dd = (pk - vals) / pk
    sells = [t for t in trades if t["side"] == "SELL"]
    realised = sum(t["pnl"] for t in sells)
    stcg = sum(t["pnl"] for t in sells if t["held_days"] < 365)
    ltcg = sum(t["pnl"] for t in sells if t["held_days"] >= 365)
    tax_est = max(0.0, stcg) * TAX_STCG + max(0.0, ltcg - 125000) * TAX_LTCG
    months = {}
    for d, v in zip(dates, vals):
        months[d[:7]] = v
    mlist, prev = [], float(CAPITAL)
    for m, v in months.items():
        mlist.append({"month": m, "value": round(v), "return_pct": round((v / prev - 1) * 100, 2)})
        prev = v
    exits = [t for t in sells if t["why"].startswith("closed below")]
    for t in trades:
        t["name"] = names.get(t["symbol"], t["symbol"])
    payload = {
        "version": 1, "name": "₹1 crore in the fund, one year back", "generated_at": datetime.now().isoformat(timespec="minutes"),
        "as_of": dates[-1], "start": dates[0], "capital": CAPITAL, "cost_per_side_pct": F.COST_PER_SIDE * 100, "cash_yield_pct": F.CASH_YIELD * 100,
        "summary": {"end": round(end), "profit": round(end - CAPITAL), "return_pct": round((end / CAPITAL - 1) * 100, 2),
                    "max_dd_pct": round(float(dd.max()) * 100, 2), "dd_day": dates[int(dd.argmax())],
                    "nifty50_end": round(float(nif[-1])), "nifty50_return_pct": round((nif[-1] / CAPITAL - 1) * 100, 2),
                    "ew100_end": round(float(ew[-1])), "ew100_return_pct": round((ew[-1] / CAPITAL - 1) * 100, 2),
                    "fund_nav_return_pct": round(nav_ret, 2), "realised_pnl": round(realised), "unrealised_pnl": round(sum(h["pnl"] for h in held)),
                    "fees": round(fees), "trades": len(trades), "buys": len(trades) - len(sells), "sells": len(sells),
                    "exits_200dma": len(exits), "rebalances": len(rebal), "cash_now": round(cash), "stocks_now": len(held),
                    "stcg": round(stcg), "ltcg": round(ltcg), "tax_estimate": round(tax_est),
                    "after_tax_profit": round(end - CAPITAL - tax_est)},
        "rebalances": rebal, "trades": trades, "held": held, "pending_exits": pending_exits, "months": mlist,
        "curve": [[d, round(v), round(float(n)), round(float(e))] for d, v, n, e in zip(dates, vals, nif, ew)],
        "limits": [
            "Uses fund.py's exact rules and the same daily prices. Prices are dividend-adjusted, so share counts and rupee amounts are close to, not "
            "exactly, what a broker would have shown on each date.",
            "Uses today's Nifty 100 members back in time (survivorship bias): stocks that dropped out of the index are missing.",
            "Trades at the closing price of the execution day; real fills slip. 0.2% is charged on every rupee bought or sold.",
            "Tax estimate: 20% on gains from shares held under a year, 12.5% above ₹1.25 lakh on shares held longer; losses are not carried forward. "
            "Not tax advice.",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
    }
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for out in (DOCS / "fund_crore.json", PUBLIC / "fund_crore.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    s = payload["summary"]
    print(f"fund_crore.json {dates[0]} -> {dates[-1]} | ₹1 crore -> ₹{s['end']:,} ({s['return_pct']:+.2f}%) | fund NAV same window {s['fund_nav_return_pct']:+.2f}% | "
          f"Nifty 50 {s['nifty50_return_pct']:+.2f}% | EW100 {s['ew100_return_pct']:+.2f}% | worst fall {s['max_dd_pct']}% | {s['trades']} trades "
          f"({s['exits_200dma']} 200-DMA exits, {s['rebalances']} rebalances) | fees ₹{s['fees']:,} | {len(text) // 1024}KB")
    return payload


if __name__ == "__main__":
    build()
