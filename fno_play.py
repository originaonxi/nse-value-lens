#!/usr/bin/env python3
"""F&O ₹1 Play Desk — daily EOD signal for the next session's ₹1 scalp.

For every top-50 F&O stock:
  ADR (20-day average daily range in ₹): tells you how easily ₹1 moves happen.
  Signal score (−1 to +1):
      Trend      40%  — close vs 5-DMA and 20-DMA
      Range pos  30%  — where in today's H-L did price close?
      Momentum   20%  — close vs open (was today bullish or bearish?)
      Volume     10%  — above/below 20-day avg volume
  Backtest win rate: on LONG-signal days, what % of time did the next session's
      High reach prev_close + ₹1? Likewise for SHORT. Computed from full history.
  Pivot levels (classic floor-trader pivots from prev session):
      P = (H+L+C)/3 · R1 = 2P−L · R2 = P+(H−L) · S1 = 2P−H · S2 = P−(H−L)

Signal →  buy / sell / wait / caution / avoid
          Set an alert at the entry zone. Confirm with 15-min ORB before entering.

IMPORTANT: EOD signals only. Actual intraday entries need live price confirmation
via your broker (Kotak Neo, Kite, etc.). This page provides directional bias,
not real-time tick data. Paper research. Not SEBI-registered advice.
"""
import json, math, time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
PRICES = ROOT / "data" / "hhhl_prices"
DOCS  = ROOT / "docs"
PUBLIC_DATA = ROOT / "public" / "data"

# ── F&O universe with official NSE lot sizes ──────────────────────────────────
# Lot sizes updated quarterly by NSE. Last verified Oct 2026.
LOT_SIZES = {
    "RELIANCE":  250,  "HDFCBANK":  550,  "ICICIBANK": 700,   "INFY":     300,
    "BHARTIARTL":1125, "TCS":       150,  "KOTAKBANK": 400,   "AXISBANK": 625,
    "BAJFINANCE":125,  "BAJAJ-AUTO":75,   "MARUTI":    50,    "SBIN":    1500,
    "LT":        175,  "WIPRO":    1500,  "HCLTECH":   350,   "TATAMOTORS":1425,
    "SUNPHARMA": 700,  "DIVISLAB":  50,   "DRREDDY":   100,   "NTPC":    3000,
    "ONGC":     1550,  "COALINDIA":2100,  "ADANIPORTS":625,   "BAJAJFINSV":125,
    "TITAN":     175,  "ULTRACEMCO":100,  "ASIANPAINT":200,   "M&M":      350,
    "NESTLEIND":  50,  "EICHERMOT": 50,   "TECHM":     300,   "HINDUNILVR":300,
    "BRITANNIA": 100,  "ADANIENT":  375,  "GRASIM":    175,   "APOLLOHOSP":125,
    "CIPLA":     650,  "INDUSINDBK":300,  "BANKBARODA":4350,  "TATACONSUM":600,
    "POWERGRID":2750,  "HDFCLIFE": 1000,  "SBILIFE":   375,   "HEROMOTOCO":100,
    "TATASTEEL":2025,  "JSWSTEEL": 2250,  "SHRIRAMFIN":200,   "GODREJCP":  500,
    "TRENT":     175,  "ETERNAL":  1000,
}

STOCK_NAMES = {
    "RELIANCE":"Reliance Industries","HDFCBANK":"HDFC Bank","ICICIBANK":"ICICI Bank",
    "INFY":"Infosys","BHARTIARTL":"Bharti Airtel","TCS":"TCS","KOTAKBANK":"Kotak Bank",
    "AXISBANK":"Axis Bank","BAJFINANCE":"Bajaj Finance","BAJAJ-AUTO":"Bajaj Auto",
    "MARUTI":"Maruti Suzuki","SBIN":"SBI","LT":"L&T","WIPRO":"Wipro",
    "HCLTECH":"HCL Technologies","TATAMOTORS":"Tata Motors","SUNPHARMA":"Sun Pharma",
    "DIVISLAB":"Divi's Labs","DRREDDY":"Dr Reddy's","NTPC":"NTPC",
    "ONGC":"ONGC","COALINDIA":"Coal India","ADANIPORTS":"Adani Ports",
    "BAJAJFINSV":"Bajaj Finserv","TITAN":"Titan","ULTRACEMCO":"UltraTech Cement",
    "ASIANPAINT":"Asian Paints","M&M":"Mahindra & Mahindra","NESTLEIND":"Nestle India",
    "EICHERMOT":"Eicher Motors","TECHM":"Tech Mahindra","HINDUNILVR":"HUL",
    "BRITANNIA":"Britannia","ADANIENT":"Adani Enterprises","GRASIM":"Grasim",
    "APOLLOHOSP":"Apollo Hospitals","CIPLA":"Cipla","INDUSINDBK":"IndusInd Bank",
    "BANKBARODA":"Bank of Baroda","TATACONSUM":"Tata Consumer","POWERGRID":"Power Grid",
    "HDFCLIFE":"HDFC Life","SBILIFE":"SBI Life","HEROMOTOCO":"Hero MotoCorp",
    "TATASTEEL":"Tata Steel","JSWSTEEL":"JSW Steel","SHRIRAMFIN":"Shriram Finance",
    "GODREJCP":"Godrej Consumer","TRENT":"Trent","ETERNAL":"Eternal (Zomato)",
}

SIGNAL_MAP = {
    "buy_strong":  {"label": "🟢 BUY",       "color": "buy-strong"},
    "buy":         {"label": "🟢 Buy",        "color": "buy"},
    "watch_buy":   {"label": "👀 Watch ↑",   "color": "watch-buy"},
    "wait":        {"label": "🟡 WAIT",       "color": "wait"},
    "watch_sell":  {"label": "👀 Watch ↓",   "color": "watch-sell"},
    "sell":        {"label": "🔴 Sell",       "color": "sell"},
    "sell_strong": {"label": "🔴 SELL",       "color": "sell-strong"},
    "avoid":       {"label": "⛔ AVOID",      "color": "avoid"},
}


# ── Price loading ─────────────────────────────────────────────────────────────

def load_ohlcv(symbol):
    """Load OHLCV DataFrame for a symbol from the hhhl_prices cache."""
    for suffix in [".NS.csv", ".csv"]:
        p = PRICES / f"{symbol}{suffix}"
        if p.exists():
            try:
                df = pd.read_csv(p, index_col=0, parse_dates=True)
                # Normalise column names
                df.columns = [c.strip() for c in df.columns]
                rename = {}
                for c in df.columns:
                    cl = c.lower()
                    if "adj" in cl and "close" in cl:
                        rename[c] = "Close"
                    elif cl == "open":
                        rename[c] = "Open"
                    elif cl == "high":
                        rename[c] = "High"
                    elif cl == "low":
                        rename[c] = "Low"
                    elif cl == "close" and c != "Close":
                        rename[c] = "Close"
                    elif cl in ("volume", "vol"):
                        rename[c] = "Volume"
                if rename:
                    df = df.rename(columns=rename)
                needed = [c for c in ["Open","High","Low","Close"] if c in df.columns]
                if "Close" in needed and len(df) >= 50:
                    df = df.sort_index()
                    df = df[df.index.dayofweek < 5]
                    return df[needed + (["Volume"] if "Volume" in df.columns else [])]
            except Exception:
                pass
    return pd.DataFrame()


def get_vix():
    """Try to extract India VIX from published JSON files."""
    for fname in ("daily_market.json", "options_desk.json"):
        try:
            d = json.loads((DOCS / fname).read_text(encoding="utf-8"))
            # Recurse through common nesting
            for path in (["market"], ["indices"], []):
                sub = d
                for key in path:
                    sub = sub.get(key, {}) if isinstance(sub, dict) else {}
                if not isinstance(sub, dict):
                    continue
                for k, v in sub.items():
                    if "vix" in k.lower() and isinstance(v, (int, float)):
                        return float(v)
                    if isinstance(v, dict):
                        vx = v.get("vix") or v.get("india_vix") or v.get("VIX")
                        if vx:
                            return float(vx)
        except Exception:
            pass
    return 15.0  # neutral default


# ── Signal computation ────────────────────────────────────────────────────────

def compute_metrics(df, n_adr=20, n_short=5, n_long=20):
    """Return a metrics dict for the most recent session from OHLCV DataFrame."""
    if len(df) < n_long + 5:
        return None
    close = df["Close"].dropna()
    if len(close) < n_long + 5:
        return None

    # Latest session
    last = df.iloc[-1]
    prev = df.iloc[-2]
    c = float(close.iloc[-1])
    h = float(df["High"].iloc[-1])  if "High"   in df.columns else c
    lo= float(df["Low"].iloc[-1])   if "Low"    in df.columns else c
    o = float(df["Open"].iloc[-1])  if "Open"   in df.columns else c
    pc= float(close.iloc[-2])  # prev close

    # ADR 20
    if "High" in df.columns and "Low" in df.columns:
        ranges = (df["High"] - df["Low"]).dropna().iloc[-n_adr:]
        adr20 = float(ranges.mean()) if len(ranges) >= 5 else abs(h - lo)
    else:
        adr20 = abs(h - lo)

    # DMAs
    dma5  = float(close.iloc[-n_short:].mean())
    dma20 = float(close.iloc[-n_long:].mean())

    # Volume ratio
    vol_ratio = 1.0
    if "Volume" in df.columns:
        vol_series = df["Volume"].dropna()
        if len(vol_series) >= n_long:
            avg_vol = float(vol_series.iloc[-n_long:-1].mean())
            cur_vol = float(vol_series.iloc[-1])
            vol_ratio = cur_vol / avg_vol if avg_vol > 0 else 1.0

    # Range position: where in today's H-L did price close? (0=low, 1=high)
    day_range = h - lo
    range_pos = (c - lo) / day_range if day_range > 0.01 else 0.5

    # Pivot levels (from THIS session; use in next session as S&R)
    pivot = (h + lo + c) / 3
    r1 = 2 * pivot - lo
    r2 = pivot + (h - lo)
    s1 = 2 * pivot - h
    s2 = pivot - (h - lo)

    return {
        "close": round(c, 2),  "high": round(h, 2),   "low": round(lo, 2),
        "open": round(o, 2),   "prev_close": round(pc, 2),
        "adr20": round(adr20, 2),
        "dma5": round(dma5, 2), "dma20": round(dma20, 2),
        "vol_ratio": round(vol_ratio, 2),
        "range_pos": round(range_pos, 3),
        "pivot": round(pivot, 2),
        "r1": round(r1, 2), "r2": round(r2, 2),
        "s1": round(s1, 2), "s2": round(s2, 2),
        "change_pct": round((c - pc) / pc * 100, 2) if pc else 0,
    }


def signal_score(m, vix=15.0):
    """Compute a signal score from −1 (strong sell) to +1 (strong buy)."""
    score = 0.0
    reasons = []

    # 1. Trend (40%): price vs DMAs
    if m["close"] > m["dma5"]:
        score += 0.2; reasons.append("Above 5-DMA")
    else:
        score -= 0.2; reasons.append("Below 5-DMA")
    if m["close"] > m["dma20"]:
        score += 0.2; reasons.append("Above 20-DMA")
    else:
        score -= 0.2; reasons.append("Below 20-DMA")

    # 2. Range position (30%): upper half = bullish, lower half = bearish
    rp = m["range_pos"]
    if rp >= 0.65:
        score += 0.3; reasons.append(f"Closed top {round((1-rp)*100)}% of range")
    elif rp >= 0.5:
        score += 0.1; reasons.append("Closed above midrange")
    elif rp <= 0.35:
        score -= 0.3; reasons.append(f"Closed bottom {round(rp*100)}% of range")
    else:
        score -= 0.1; reasons.append("Closed below midrange")

    # 3. Day momentum (20%): close vs open
    day_move = m["close"] - m["open"]
    if abs(day_move) > 0.5:
        if day_move > 0:
            score += 0.2; reasons.append("Green candle (close > open)")
        else:
            score -= 0.2; reasons.append("Red candle (close < open)")

    # 4. Volume (10%): volume spike confirms direction
    if m["vol_ratio"] > 1.3:
        vol_boost = 0.1 * (1 if score > 0 else -1)
        score += vol_boost
        reasons.append(f"Volume {m['vol_ratio']:.1f}× avg (confirms direction)")

    # VIX override: very high VIX → reduce conviction
    if vix > 25:
        score *= 0.7
        reasons.append(f"VIX {vix:.1f} — wide stops, reduce size")

    return round(max(-1.0, min(1.0, score)), 3), reasons


def classify_signal(score, adr20, vix=15.0):
    """Convert numeric score to action label."""
    if adr20 < 5:
        return "avoid"
    if vix > 30:
        return "avoid"
    if score >= 0.6:
        return "buy_strong"
    if score >= 0.3:
        return "buy"
    if score >= 0.1:
        return "watch_buy"
    if score <= -0.6:
        return "sell_strong"
    if score <= -0.3:
        return "sell"
    if score <= -0.1:
        return "watch_sell"
    return "wait"


# ── Backtest ─────────────────────────────────────────────────────────────────

def backtest_rs1(df, n_short=5, n_long=20):
    """Historical win rate: on LONG-signal days, how often does next session
    trade ≥ prev_close + ₹1?  Likewise for SHORT."""
    if len(df) < n_long + 50:
        return {"long_wr": None, "short_wr": None, "long_n": 0, "short_n": 0}

    close  = df["Close"].dropna()
    high   = df["High"].dropna()   if "High"  in df.columns else close
    low    = df["Low"].dropna()    if "Low"   in df.columns else close
    opens  = df["Open"].dropna()   if "Open"  in df.columns else close

    # Align
    idx = close.index.intersection(high.index).intersection(low.index).intersection(opens.index)
    c, h, lo, op = close.reindex(idx), high.reindex(idx), low.reindex(idx), opens.reindex(idx)

    long_wins, long_n = 0, 0
    short_wins, short_n = 0, 0

    # For each day from n_long onward (skip last row — no future data)
    for i in range(n_long, len(idx) - 1):
        ci    = float(c.iloc[i])
        dma5  = float(c.iloc[i - n_short: i].mean())
        dma20 = float(c.iloc[i - n_long:  i].mean())
        day_range = float(h.iloc[i]) - float(lo.iloc[i])
        rp    = (ci - float(lo.iloc[i])) / day_range if day_range > 0.01 else 0.5
        day_move  = ci - float(op.iloc[i])

        # Compute score without volume (volume often unreliable in cache)
        sc = 0.0
        sc += 0.2 if ci > dma5  else -0.2
        sc += 0.2 if ci > dma20 else -0.2
        sc += (0.3 if rp >= 0.65 else 0.1 if rp >= 0.5 else -0.3 if rp <= 0.35 else -0.1)
        sc += (0.2 if day_move > 0.5 else -0.2 if day_move < -0.5 else 0.0)

        next_h = float(h.iloc[i + 1])
        next_l = float(lo.iloc[i + 1])

        if sc >= 0.3:
            long_n += 1
            if next_h >= ci + 1.0:
                long_wins += 1
        elif sc <= -0.3:
            short_n += 1
            if next_l <= ci - 1.0:
                short_wins += 1

    return {
        "long_wr":  round(long_wins  / long_n  * 100, 1) if long_n  >= 5 else None,
        "short_wr": round(short_wins / short_n * 100, 1) if short_n >= 5 else None,
        "long_n":   long_n,
        "short_n":  short_n,
    }


# ── Main build ────────────────────────────────────────────────────────────────

def rs1_action(m, signal_key, lot_size):
    """Return the exact action note with entry/target/stop."""
    c = m["close"]
    is_buy  = signal_key in ("buy_strong", "buy")
    is_sell = signal_key in ("sell_strong", "sell")
    if is_buy:
        entry  = round(c, 2)
        target = round(c + 1.0, 2)
        stop   = round(c - 1.0, 2)
        note   = f"Buy around ₹{entry} · Target ₹{target} · Stop ₹{stop} · ₹1×{lot_size} lots = ₹{lot_size}/lot"
    elif is_sell:
        entry  = round(c, 2)
        target = round(c - 1.0, 2)
        stop   = round(c + 1.0, 2)
        note   = f"Sell around ₹{entry} · Target ₹{target} · Stop ₹{stop} · ₹1×{lot_size} lots = ₹{lot_size}/lot"
    else:
        note = "Wait for opening 15-min range to establish direction before entering."
    return note


def build():
    vix = get_vix()
    today = datetime.now().strftime("%Y-%m-%d")
    rows = []
    missing = []

    for sym, lot in LOT_SIZES.items():
        df = load_ohlcv(sym)
        if df.empty or len(df) < 50:
            missing.append(sym)
            continue

        m = compute_metrics(df)
        if m is None:
            missing.append(sym); continue

        sc, reasons = signal_score(m, vix)
        sig = classify_signal(sc, m["adr20"], vix)
        bt  = backtest_rs1(df)
        action_note = rs1_action(m, sig, lot)

        # Conviction: how reliable is this signal?
        wr = bt["long_wr"] if sig in ("buy_strong","buy") else (
             bt["short_wr"] if sig in ("sell_strong","sell") else None)
        conviction = ("high"   if wr is not None and wr >= 75 else
                      "medium" if wr is not None and wr >= 60 else
                      "low"    if wr is not None else "unproven")

        rows.append({
            "symbol":      sym,
            "name":        STOCK_NAMES.get(sym, sym),
            "lot_size":    lot,
            "rs1_per_lot": lot,        # ₹1 × lot = profit per lot per ₹1 move
            "signal":      sig,
            "signal_label":SIGNAL_MAP[sig]["label"],
            "signal_color":SIGNAL_MAP[sig]["color"],
            "score":       sc,
            "conviction":  conviction,
            "reasons":     reasons,
            "action":      action_note,
            "close":       m["close"],
            "high":        m["high"],
            "low":         m["low"],
            "open":        m["open"],
            "prev_close":  m["prev_close"],
            "change_pct":  m["change_pct"],
            "adr20":       m["adr20"],
            "adr_vs_rs1":  round(m["adr20"] / 1.0, 1),  # ADR / ₹1 — how many ₹1 moves in avg day
            "dma5":        m["dma5"],
            "dma20":       m["dma20"],
            "vol_ratio":   m["vol_ratio"],
            "pivot":       m["pivot"],
            "r1":          m["r1"],  "r2": m["r2"],
            "s1":          m["s1"],  "s2": m["s2"],
            "bt_long_wr":  bt["long_wr"],
            "bt_short_wr": bt["short_wr"],
            "bt_long_n":   bt["long_n"],
            "bt_short_n":  bt["short_n"],
        })

    # Sort: actionable signals first (buy_strong, sell_strong, buy, sell), then conviction, then ADR
    order = {"buy_strong":0,"sell_strong":0,"buy":1,"sell":1,"watch_buy":2,"watch_sell":2,"wait":3,"avoid":4}
    rows.sort(key=lambda r: (order.get(r["signal"],5), -r["adr20"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    # Top picks: highest conviction actionable signals
    top_picks = [r for r in rows if r["signal"] in ("buy_strong","sell_strong","buy","sell")
                 and r["adr20"] >= 10][:10]

    # Count signals
    sig_counts = {}
    for r in rows:
        sig_counts[r["signal"]] = sig_counts.get(r["signal"], 0) + 1

    payload = {
        "version": 1,
        "name": "F&O ₹1 Play Desk",
        "as_of": today,
        "vix": vix,
        "covered": len(rows),
        "missing": missing,
        "top_picks": top_picks,
        "signal_counts": sig_counts,
        "rows": rows,
        "method": [
            "Trend (40%): close above/below 5-DMA and 20-DMA.",
            "Range position (30%): where in today's High-Low did the price close?",
            "Day momentum (20%): was today's candle green or red (close vs open)?",
            "Volume (10%): above-average volume confirms the direction.",
            "ADR (avg daily range ₹): must be > ₹5 for a ₹1 play to be feasible.",
            "Backtest: on historical BUY-signal days, what % of the time did next-day High ≥ prev_close + ₹1?",
        ],
        "rules": [
            "Wait for the first 15-minute opening range (ORB) to form before entering.",
            "Enter near the pivot or previous close with a ₹1 stop and ₹1 target (1:1 R/R).",
            "Exit the trade by 3:15 PM regardless — never hold F&O futures overnight.",
            "Start with 1 lot. Scale to multiple lots only after 10 consecutive green days.",
            "On VIX > 20: reduce size by half. On VIX > 25: step aside entirely.",
        ],
        "limits": [
            "EOD signals only. Intraday entries need live price confirmation from your broker.",
            "Futures margin: ~15-20% of contract value. BHARTIARTL 1 lot needs ~₹3.5L margin.",
            "₹1 target is achievable but bid-ask spread + brokerage typically costs ₹0.2-0.4/share.",
            "Paper research. Not SEBI-registered advice. No orders placed by this website.",
        ],
    }

    text = json.dumps(payload, separators=(",", ":"), default=str)
    DOCS.mkdir(exist_ok=True)
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    (DOCS / "fno-play.json").write_text(text, encoding="utf-8")
    (PUBLIC_DATA / "fno-play.json").write_text(text, encoding="utf-8")

    buy_n  = sig_counts.get("buy_strong",0) + sig_counts.get("buy",0)
    sell_n = sig_counts.get("sell_strong",0) + sig_counts.get("sell",0)
    print(
        f"fno-play.json {today}: {len(rows)} stocks | VIX {vix:.1f} | "
        f"BUY {buy_n} SELL {sell_n} WAIT {sig_counts.get('wait',0)} AVOID {sig_counts.get('avoid',0)} | "
        f"top: {', '.join(r['symbol'] for r in top_picks[:5])}"
    )
    return payload


if __name__ == "__main__":
    build()
