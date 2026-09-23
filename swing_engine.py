"""Shared completed-bar swing rules and cash-constrained research simulator."""
from __future__ import annotations
import math
import numpy as np
import pandas as pd

STRATEGIES = {"breakout": {"name": "20-day breakout", "hold": 20},
              "pullback": {"name": "Trend pullback", "hold": 10},
              "reversion": {"name": "Short mean reversion", "hold": 5}}
RISK, ALLOCATION, MAX_POSITIONS = .005, .20, 5
FEE, SLIPPAGE = .0015, .0005  # per-side scenario assumptions, not broker tariffs

def features(frame):
    d = frame.copy().sort_index()
    c, h, low, v = (d[k] for k in ("Close", "High", "Low", "Volume"))
    d["sma50"], d["sma200"] = c.rolling(50).mean(), c.rolling(200).mean()
    d["ema20"] = c.ewm(span=20, adjust=False, min_periods=20).mean()
    d["prior_high"] = h.shift(1).rolling(20).max()
    d["vol_ratio"] = v/v.shift(1).rolling(20).mean().replace(0, np.nan)
    d["turnover"] = (c*v).rolling(20).mean()
    tr = pd.concat([h-low, (h-c.shift()).abs(), (low-c.shift()).abs()], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    d["ret63"] = c.pct_change(63)
    change = c.diff()
    gain = change.clip(lower=0).ewm(alpha=.5, adjust=False).mean()
    loss = (-change.clip(upper=0)).ewm(alpha=.5, adjust=False).mean()
    d["rsi2"] = 100-100/(1+gain/loss.replace(0, np.nan))
    d.loc[(loss == 0) & (gain > 0), "rsi2"] = 100
    d["prev_close"], d["prev_ema20"] = c.shift(), d["ema20"].shift()
    return d

def setup(row, market, strategy):
    """Freeze plan at close t. Scanner and simulator use this exact function."""
    needed = ["Close", "atr", "sma50", "sma200", "ema20", "ret63", "turnover", "vol_ratio"]
    if market is None or any(not math.isfinite(float(row.get(k, np.nan))) for k in needed):
        return None
    c, atr = float(row.Close), float(row.atr)
    if not market.Close > market.sma50 > market.sma200:
        return None
    if c < 50 or atr <= 0 or not .005 <= atr/c <= .06 or row.turnover < 100_000_000:
        return None
    if not c > row.sma200 or not math.isfinite(float(market.ret63)):
        return None
    relative = float(row.ret63-market.ret63)
    if strategy == "breakout":
        valid = c > row.prior_high and c > row.sma50 and row.vol_ratio >= 1.5 and relative > 0
        why = "Closed above the prior 20-session high, with 1.5x volume and positive 63-session strength versus Nifty."
    elif strategy == "pullback":
        valid = (row.prev_close <= row.prev_ema20 and c > row.ema20 > row.sma50
                 and relative > 0 and row.vol_ratio >= 1)
        why = "Reclaimed the 20-day EMA in an uptrend, with positive relative strength and at least average volume."
    elif strategy == "reversion":
        valid = row.rsi2 < 10 and c > row.sma50
        why = "Two-period RSI below 10 while above the 50- and 200-day averages."
    else:
        raise ValueError(strategy)
    if not valid or c-2*atr <= 0:
        return None
    return {"strategy": strategy, "close": c, "atr": atr, "entry_low": c-.5*atr,
            "entry_high": c+.5*atr, "stop": c-2*atr, "target": c+4*atr,
            "hold": STRATEGIES[strategy]["hold"], "relative_strength": relative,
            "volume_ratio": float(row.vol_ratio), "reason": why}

def fill(plan, open_price, equity, cash, fee=FEE, slippage=SLIPPAGE):
    """Next session open only. Cancel outside band, including excessive gap down."""
    entry = float(open_price)*(1+slippage)
    if not plan["entry_low"] <= entry <= plan["entry_high"] or entry <= plan["stop"]:
        return None
    risk = entry-plan["stop"]
    qty = math.floor(min(equity*RISK/(risk+entry*fee+plan["stop"]*(fee+slippage)),
                         equity*ALLOCATION/(entry*(1+fee)), cash/(entry*(1+fee))))
    if qty <= 0:
        return None
    return {"entry": entry, "stop": plan["stop"], "target": entry+2*risk,
            "qty": qty, "cost": qty*entry*(1+fee), "risk_cash": qty*risk,
            "hold": plan["hold"], "age": 0}

def exit_price(position, bar, slippage=SLIPPAGE):
    """Daily ambiguity: stop before target. A gap through stop fills at open."""
    if bar.Open <= position["stop"]:
        return float(bar.Open)*(1-slippage), "gap stop"
    if bar.Low <= position["stop"]:
        return position["stop"]*(1-slippage), "stop"
    if bar.High >= position["target"]:
        return position["target"]*(1-slippage), "target"
    if position["age"] >= position["hold"]:
        return float(bar.Close)*(1-slippage), "time exit"
    return None

def backtest(frames, market, sectors, strategy, start, end, cost_scale=1):
    """Flat start per window. No parameter search. Mark open positions daily."""
    capital = cash = 100_000.0
    fee, slip = FEE*cost_scale, SLIPPAGE*cost_scale
    positions, pending, trades, curve = {}, [], [], []
    missing = 0
    records = {s: {d: r for d, r in f.iterrows()} for s, f in frames.items()}
    market_rows = {d: r for d, r in market.iterrows()}
    dates = [d for d in market.index if start <= str(d.date()) <= end]
    for day in dates:
        bars = {s: rows[day] for s, rows in records.items() if day in rows}
        equity = cash+sum(p["qty"]*p["mark"] for p in positions.values())
        for symbol, plan in pending:
            if len(positions) >= MAX_POSITIONS or symbol in positions or symbol not in bars:
                continue
            sector = sectors.get(symbol, "Unknown")
            if sum(p["sector"] == sector for p in positions.values()) >= 2:
                continue
            pos = fill(plan, bars[symbol].Open, equity, cash, fee, slip)
            if pos:
                pos.update(symbol=symbol, sector=sector, entry_date=str(day.date()), mark=pos["entry"])
                cash -= pos["cost"]
                positions[symbol] = pos
        pending = []
        for symbol, pos in list(positions.items()):
            pos["age"] += 1
            bar = bars.get(symbol)
            if bar is None:
                missing += 1
                continue
            pos["mark"] = float(bar.Close)
            outcome = exit_price(pos, bar, slip)
            if outcome is not None:
                price, reason = outcome
                proceeds = pos["qty"]*price*(1-fee)
                cash += proceeds
                trades.append({"symbol": symbol, "entry_date": pos["entry_date"],
                               "exit_date": str(day.date()), "pnl": round(proceeds-pos["cost"], 2),
                               "r": (proceeds-pos["cost"])/pos["risk_cash"], "reason": reason,
                               "sessions": pos["age"]})
                del positions[symbol]
        equity = cash+sum(p["qty"]*p["mark"] for p in positions.values())
        curve.append({"date": str(day.date()), "equity": round(equity, 2)})
        for symbol, bar in bars.items():
            if symbol not in positions:
                plan = setup(bar, market_rows[day], strategy)
                if plan:
                    pending.append((symbol, plan))
        pending.sort(key=lambda x: (-x[1]["relative_strength"], x[0]))
    # Reserve closing costs on residual positions without inventing fills.
    equity = cash+sum(p["qty"]*p["mark"]*(1-fee-slip) for p in positions.values())
    if curve:
        curve[-1]["equity"] = round(equity, 2)
    peak, drawdown = capital, 0
    for value in [capital]+[v["equity"] for v in curve]:
        peak = max(peak, value)
        drawdown = max(drawdown, 1-value/peak)
    gains = sum(max(0, t["pnl"]) for t in trades)
    losses = -sum(min(0, t["pnl"]) for t in trades)
    return {"return_pct": round(100*(equity/capital-1), 2),
            "max_drawdown_pct": round(100*drawdown, 2), "trades": len(trades),
            "win_rate_pct": round(100*sum(t["pnl"] > 0 for t in trades)/len(trades), 1) if trades else None,
            "profit_factor": round(gains/losses, 2) if losses else None,
            "expectancy_r": round(float(np.mean([t["r"] for t in trades])), 3) if trades else None,
            "open_positions": len(positions), "missing_position_bars": missing,
            "benchmark_price_return_pct": round(100*(market.loc[dates[-1]].Close/market.loc[dates[0]].Open-1), 2) if dates else None,
            "start": start, "end": end, "curve": curve, "trade_log": trades}
