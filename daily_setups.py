"""Daily setups: every Nifty 200 + F&O stock sorted into one plain-English category after the close.

Inputs (all already produced by other daily jobs; each input keeps its own date):
  docs/hhhl_scan.json      200 stocks: official closing candles, confirmed swings, trigger / structure-exit levels
  docs/hhhl_fno.json       extra F&O stocks (same row shape) + official F&O lot sizes
  docs/jev_rank.json       Jev ranking of the 200 (rank, composite, direction, regime, confidence)
  docs/market_brief.json   Jev US + India context per stock (supportive / conflicting, event risk)
  docs/options_desk.json   per-stock option data: ATM IV, expiry, strikes, call / put OI walls

Output: docs/daily_setups.json (+ compact history in data/daily_setups_history/<date>.json).

Five indicators, each covering a different question, are computed from the SAME candles the chart draws:
  1. Supertrend (10, 3)        trend direction + trailing stop        "which way is it going?"
  2. ADX (14) with +DI / -DI   trend strength                         "is the move strong or choppy?"
  3. RSI (14)                  momentum                               "are buyers or sellers pushing?"
  4. Bollinger Bands (20, 2)   volatility, squeeze / expansion        "is a big move loading?"
  5. OBV vs its 20-day EMA     volume / money flow                    "is money flowing in or out?"
VWAP-20 (20-session volume-weighted price) is shown as the fair-value reference line.

Research output only. Option premiums are Black-Scholes estimates from end-of-day ATM IV, not quotes.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

import setup_rank as rank
import setup_signals as sig

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
OUT = DOCS / "daily_setups.json"
HISTORY = ROOT / "data" / "daily_setups_history"
VERSION = 1
RISK_FREE = 0.065
OPTS_DATE = None             # set in main(): date of the options desk file used for IV / strikes
SERIES_BARS = 120           # chart file keeps the last 120 sessions (the page shows up to 110)
CAPITAL = 1_000_000          # sizing example: Rs 10 lakh
RISK_PCT = 0.5               # repo rule: 0.5% risk per position
MAX_POSITION_PCT = 20        # repo rule: max 20% of capital per position

CATEGORIES = {
    "breakout_today": {
        "label": "Breakout today", "side": "long", "tone": "bull", "order": 1,
        "meaning": "Closed above its closing trigger (the last confirmed swing high) today with higher highs and higher lows. "
                   "Plan: buy at the next open only if it opens inside the entry band.",
    },
    "ready_to_break": {
        "label": "Ready to break", "side": "long", "tone": "bull", "order": 2,
        "meaning": "Rising structure (higher highs + higher lows) and the close is within 1 ATR of the trigger. "
                   "Plan: buy only after a daily CLOSE above the trigger.",
    },
    "uptrend": {
        "label": "Uptrend - wait", "side": "long", "tone": "bull", "order": 3,
        "meaning": "Rising structure, but price is not near a fresh trigger. Holders trail the stop; new buyers wait "
                   "for the trigger close or a dip to support.",
    },
    "turning_up": {
        "label": "Turning up", "side": "watch", "tone": "neutral", "order": 4,
        "meaning": "Mixed structure but trend indicators have turned up. Not a buy yet: it needs a higher low and a close above the trigger.",
    },
    "sideways": {
        "label": "Sideways / no trend", "side": "none", "tone": "neutral", "order": 5,
        "meaning": "No clear direction. Stay out until price closes above the trigger (bullish) or below the structure exit (bearish).",
    },
    "exit_today": {
        "label": "Structure exit today", "side": "short", "tone": "bear", "order": 6,
        "meaning": "Closed below its last confirmed swing low TODAY. Longs exit at the next open. Bearish trades only through F&O "
                   "(no overnight short in cash).",
    },
    "below_structure": {
        "label": "Below structure", "side": "short", "tone": "bear", "order": 7,
        "meaning": "Already broke its last swing low on an earlier day and has not repaired. Avoid buying; wait for a new higher low.",
    },
    "downtrend": {
        "label": "Downtrend", "side": "short", "tone": "bear", "order": 8,
        "meaning": "Lower highs and lower lows. Avoid buying; bounces into resistance are selling zones for F&O traders.",
    },
    "data_check": {
        "label": "Data check", "side": "none", "tone": "neutral", "order": 9,
        "meaning": "Incomplete or suspect price data for this session, so no plan is shown.",
    },
}

INDICATORS = {
    "supertrend": {"name": "Supertrend (10, 3)", "color": "#7c3aed", "covers": "Trend direction + trailing stop",
                   "how": "Green line under price = uptrend; red line above price = downtrend. A close through the line flips it."},
    "adx": {"name": "ADX (14)", "color": "#d97706", "covers": "Trend strength",
            "how": "Below 20 = choppy, 20-25 = trend forming, above 25 = strong trend. +DI above -DI means buyers lead."},
    "rsi": {"name": "RSI (14)", "color": "#2563eb", "covers": "Momentum",
            "how": "Above 55 = buyers in control, below 45 = sellers in control. Above 70 is stretched, below 30 is washed out."},
    "bollinger": {"name": "Bollinger Bands (20, 2)", "color": "#0d9488", "covers": "Volatility / squeeze",
                  "how": "Price riding the upper band = strong; lower band = weak. Very narrow bands (squeeze) often come before a big move."},
    "obv": {"name": "OBV vs 20-day EMA", "color": "#db2777", "covers": "Volume / money flow",
            "how": "OBV adds volume on up days and subtracts it on down days. Above its average and rising = accumulation."},
    "vwap20": {"name": "VWAP-20", "color": "#64748b", "covers": "Fair-value reference",
               "how": "Average price paid over 20 sessions, weighted by volume. Price above it = buyers are in profit."},
}


# ── maths ────────────────────────────────────────────────────────────────────

def ema(values, n):
    out, k, prev = [], 2 / (n + 1), None
    for v in values:
        prev = v if prev is None else prev + k * (v - prev)
        out.append(prev)
    return out


def rma(values, n):
    """Wilder smoothing (TradingView ta.rma): SMA seed for the first n values, then recursive."""
    out, prev = [None] * len(values), None
    for i, v in enumerate(values):
        if i < n - 1:
            continue
        prev = sum(values[:n]) / n if prev is None else (prev * (n - 1) + v) / n
        out[i] = prev
    return out


def true_range(bars):
    out = []
    for i, b in enumerate(bars):
        if i == 0:
            out.append(b["high"] - b["low"])
        else:
            pc = bars[i - 1]["close"]
            out.append(max(b["high"] - b["low"], abs(b["high"] - pc), abs(b["low"] - pc)))
    return out


def rsi(closes, n=14):
    gains = [0.0] + [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [0.0] + [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    ag, al = rma(gains[1:], n), rma(losses[1:], n)
    out = [None]
    for g, l in zip(ag, al):
        out.append(None if g is None else (100.0 if l == 0 else 100 - 100 / (1 + g / l)))
    return out


def supertrend(bars, n=10, mult=3.0):
    atr = rma(true_range(bars), n)
    line, direction = [None] * len(bars), [None] * len(bars)
    fub = flb = None
    for i, b in enumerate(bars):
        if atr[i] is None:
            continue
        hl2 = (b["high"] + b["low"]) / 2
        ub, lb = hl2 + mult * atr[i], hl2 - mult * atr[i]
        pc = bars[i - 1]["close"] if i else b["close"]
        if fub is None:
            fub, flb, d = ub, lb, 1
        else:
            fub = ub if (ub < fub or pc > fub) else fub
            flb = lb if (lb > flb or pc < flb) else flb
            prev_d = direction[i - 1] or 1
            if prev_d == 1 and b["close"] < flb:
                d = -1
            elif prev_d == -1 and b["close"] > fub:
                d = 1
            else:
                d = prev_d
        direction[i] = d
        line[i] = flb if d == 1 else fub
    return line, direction


def adx(bars, n=14):
    tr = true_range(bars)
    pdm, mdm = [0.0], [0.0]
    for i in range(1, len(bars)):
        up = bars[i]["high"] - bars[i - 1]["high"]
        dn = bars[i - 1]["low"] - bars[i]["low"]
        pdm.append(up if up > dn and up > 0 else 0.0)
        mdm.append(dn if dn > up and dn > 0 else 0.0)
    atr, sp, sm = rma(tr[1:], n), rma(pdm[1:], n), rma(mdm[1:], n)
    pdi, mdi, dx = [None], [None], []
    for a, p, m in zip(atr, sp, sm):
        if a is None or a == 0:
            pdi.append(None); mdi.append(None); dx.append(None)
            continue
        pv, mv = 100 * p / a, 100 * m / a
        pdi.append(pv); mdi.append(mv)
        dx.append(0.0 if pv + mv == 0 else 100 * abs(pv - mv) / (pv + mv))
    valid = [i for i, v in enumerate(dx) if v is not None]
    adx_line = [None] * len(bars)
    if len(valid) >= n:
        start = valid[0]
        smooth = rma(dx[start:], n)
        for j, v in enumerate(smooth):
            adx_line[start + j + 1] = v
    return adx_line, pdi, mdi


def bollinger(closes, n=20, k=2.0):
    mid, up, lo = [None] * len(closes), [None] * len(closes), [None] * len(closes)
    for i in range(n - 1, len(closes)):
        w = closes[i - n + 1:i + 1]
        m = sum(w) / n
        sd = math.sqrt(sum((x - m) ** 2 for x in w) / n)
        mid[i], up[i], lo[i] = m, m + k * sd, m - k * sd
    return mid, up, lo


def obv(bars):
    out, total = [], 0.0
    for i, b in enumerate(bars):
        if i:
            pc = bars[i - 1]["close"]
            total += (b.get("volume") or 0) * (1 if b["close"] > pc else -1 if b["close"] < pc else 0)
        out.append(total)
    return out


def vwap_rolling(bars, n=20):
    out = [None] * len(bars)
    for i in range(n - 1, len(bars)):
        w = bars[i - n + 1:i + 1]
        vol = sum((b.get("volume") or 0) for b in w)
        if vol > 0:
            out[i] = sum((b["high"] + b["low"] + b["close"]) / 3 * (b.get("volume") or 0) for b in w) / vol
    return out


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_price(spot, strike, years, vol, kind, r=RISK_FREE):
    if years <= 0 or vol <= 0:
        return max(0.0, spot - strike) if kind == "CE" else max(0.0, strike - spot)
    d1 = (math.log(spot / strike) + (r + vol * vol / 2) * years) / (vol * math.sqrt(years))
    d2 = d1 - vol * math.sqrt(years)
    if kind == "CE":
        return spot * norm_cdf(d1) - strike * math.exp(-r * years) * norm_cdf(d2)
    return strike * math.exp(-r * years) * norm_cdf(-d2) - spot * norm_cdf(-d1)


def r2(v, d=2):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return None
    return int(round(float(v))) if d == 0 else round(float(v), d)


def inr(v):
    if v is None:
        return "-"
    return f"Rs {v:,.2f}" if abs(v) < 1000 else f"Rs {v:,.0f}" if abs(v) >= 100000 else f"Rs {v:,.1f}"


# ── indicators → states + plain English ─────────────────────────────────────

def indicator_pack(bars):
    closes = [b["close"] for b in bars]
    st_line, st_dir = supertrend(bars)
    adx_line, pdi, mdi = adx(bars)
    rsi_line = rsi(closes)
    mid, up, lo = bollinger(closes)
    obv_line = obv(bars)
    obv_ema = ema(obv_line, 20)
    vwap = vwap_rolling(bars)
    i, close = len(bars) - 1, closes[-1]

    reads = {}
    # 1 Supertrend
    d, s = st_dir[i], st_line[i]
    flips = next((len(bars) - 1 - j for j in range(i, 0, -1) if st_dir[j] is not None and st_dir[j - 1] is not None and st_dir[j] != st_dir[j - 1]), None)
    reads["supertrend"] = {
        "value": r2(s), "state": "bull" if d == 1 else "bear",
        "label": "Uptrend" if d == 1 else "Downtrend",
        "words": (f"GREEN at {inr(s)} under the price: the trend is up. A daily close below {inr(s)} flips it to down."
                  if d == 1 else
                  f"RED at {inr(s)} above the price: the trend is down. A daily close above {inr(s)} flips it to up.")
                 + (f" Last flip {flips} session{'s' if flips != 1 else ''} ago." if flips is not None else ""),
    }
    # 2 ADX
    a, p, m = adx_line[i], pdi[i], mdi[i]
    strength = "strong" if a >= 25 else "forming" if a >= 20 else "weak / choppy"
    lead = "buyers (+DI)" if p > m else "sellers (-DI)"
    st = "bull" if a >= 20 and p > m else "bear" if a >= 20 and m > p else "neutral"
    rising = adx_line[i - 3] is not None and a > adx_line[i - 3]
    reads["adx"] = {
        "value": r2(a, 1), "plus_di": r2(p, 1), "minus_di": r2(m, 1), "state": st,
        "label": f"{strength.capitalize()} ({'rising' if rising else 'falling'})",
        "words": f"ADX {a:.0f} = trend is {strength} and {'getting stronger' if rising else 'fading'}; {lead} lead "
                 f"(+DI {p:.0f} vs -DI {m:.0f})." + (" Below 20 means breakouts fail more often." if a < 20 else ""),
    }
    # 3 RSI
    rv = rsi_line[i]
    st = "bull" if rv >= 55 else "bear" if rv <= 45 else "neutral"
    zone = ("overbought - stretched, a pause is common" if rv >= 70 else "oversold - washed out, bounces are common" if rv <= 30
            else "buyers in control" if rv >= 55 else "sellers in control" if rv <= 45 else "balanced")
    reads["rsi"] = {"value": r2(rv, 1), "state": st, "label": zone.split(" - ")[0].capitalize(),
                    "words": f"RSI {rv:.0f} = {zone}. (Above 55 bullish, below 45 bearish, 70+ stretched, 30- washed out.)"}
    # 4 Bollinger
    width_series = [(u - l) / mm for u, l, mm in zip(up, lo, mid) if mm]
    width = width_series[-1]
    pct_rank = sum(1 for w in width_series if w <= width) / len(width_series)
    pb = (close - lo[i]) / (up[i] - lo[i]) if up[i] != lo[i] else 0.5
    squeeze = pct_rank <= 0.15
    st = "bull" if pb >= 0.8 else "bear" if pb <= 0.2 else "neutral"
    where = ("riding the upper band (strong)" if pb >= 1 else "near the upper band" if pb >= 0.8 else
             "below the lower band (very weak)" if pb <= 0 else "near the lower band" if pb <= 0.2 else "inside the middle of the bands")
    reads["bollinger"] = {
        "value": r2(pb * 100, 0), "upper": r2(up[i]), "middle": r2(mid[i]), "lower": r2(lo[i]),
        "width_pct": r2(width * 100, 1), "squeeze": squeeze, "state": st,
        "label": "Squeeze" if squeeze else where.split(" (")[0].capitalize(),
        "words": f"Price is {where}: {pb * 100:.0f}% of the way from the lower band {inr(lo[i])} to the upper band {inr(up[i])}. "
                 + (f"Bands are very narrow ({width * 100:.1f}% wide, tightest {pct_rank * 100:.0f}% of the window) - a squeeze; a big move often follows."
                    if squeeze else f"Band width {width * 100:.1f}% of price.")}
    # 5 OBV
    ov, oe = obv_line[i], obv_ema[i]
    slope = ov - obv_line[max(0, i - 10)]
    st = "bull" if ov > oe and slope > 0 else "bear" if ov < oe and slope < 0 else "neutral"
    reads["obv"] = {
        "value": r2(ov, 0), "ema20": r2(oe, 0), "state": st,
        "label": "Accumulation" if st == "bull" else "Distribution" if st == "bear" else "Mixed flow",
        "words": ("More volume on up days than down days: OBV is above its 20-day average and rising - money is flowing IN."
                  if st == "bull" else
                  "More volume on down days: OBV is below its 20-day average and falling - money is flowing OUT."
                  if st == "bear" else
                  "Volume flow is mixed: OBV and its 20-day average disagree on direction."),
    }
    # VWAP-20 reference
    vw = vwap[i]
    reads["vwap20"] = {"value": r2(vw), "state": "bull" if close > vw else "bear",
                       "label": "Above value" if close > vw else "Below value",
                       "words": f"Price {inr(close)} is {abs(close / vw - 1) * 100:.1f}% {'above' if close > vw else 'below'} the 20-session VWAP {inr(vw)}: "
                                + ("recent buyers are in profit (support)." if close > vw else "recent buyers are at a loss (overhead supply).")}

    five = ["supertrend", "adx", "rsi", "bollinger", "obv"]
    bulls = sum(reads[k]["state"] == "bull" for k in five)
    bears = sum(reads[k]["state"] == "bear" for k in five)
    series = {
        "supertrend": [r2(v) for v in st_line], "supertrend_dir": st_dir,
        "bb_upper": [r2(v) for v in up], "bb_middle": [r2(v) for v in mid], "bb_lower": [r2(v) for v in lo],
        "vwap20": [r2(v) for v in vwap], "rsi": [r2(v, 1) for v in rsi_line],
        "adx": [r2(v, 1) for v in adx_line], "plus_di": [r2(v, 1) for v in pdi], "minus_di": [r2(v, 1) for v in mdi],
        "obv": [r2(v, 0) for v in obv_line], "obv_ema20": [r2(v, 0) for v in obv_ema],
    }
    return reads, {"bull": bulls, "bear": bears, "neutral": 5 - bulls - bears}, series


# ── classification + plans ─────────────────────────────────────────────────

def classify(row, reads):
    """Return exactly one category key. Structure (the scanner's confirmed swings) decides first; indicators break ties."""
    if not row.get("complete_for_session") or row.get("data_warnings") or len(row.get("chart") or []) < 60:
        return "data_check"
    last = row["chart"][-1]
    if row.get("fresh_breakout") or last.get("structure_breakout"):
        return "breakout_today"
    if row.get("sell_triggered_today") or last.get("structure_exit"):
        return "exit_today"
    structure = row.get("structure")
    if structure == "HH / HL" and not row.get("exit_condition"):
        trig, close, atr = row["zones"].get("breakout_above"), row["close"], row.get("atr") or 0
        if trig and atr and 0 <= (trig - close) / atr <= 1:
            return "ready_to_break"
        return "uptrend"
    if row.get("exit_condition"):
        return "below_structure"
    if structure == "LH / LL":
        return "downtrend"
    if reads["supertrend"]["state"] == "bull" and (reads["rsi"]["value"] or 0) > 50:
        return "turning_up"
    return "sideways"


def swing_levels(row, kind):
    return sorted({round(s["price"], 2) for s in (row.get("chart_swings") or []) if s.get("kind") == kind})


def long_plan(row, cat, reads):
    z, close, atr = row["zones"], row["close"], row["atr"]
    trig, exit_below = z.get("breakout_above"), z.get("structure_exit_below")
    st_val, vw = reads["supertrend"]["value"], reads["vwap20"]["value"]
    if cat == "breakout_today":
        entry, how = close, f"Buy at the next open only if it opens between {inr(close - atr)} and {inr(close + atr)} (1 ATR band around today's close)."
    elif cat in ("ready_to_break",) or (trig and close < trig):
        entry, how = trig, f"Buy only after a daily CLOSE above {inr(trig)}; enter at the next open."
    else:
        dip = max(v for v in (st_val, vw, exit_below) if v and v < close) if any(v and v < close for v in (st_val, vw, exit_below)) else close
        entry, how = dip, f"Already above the trigger. Holders trail the stop. New buyers wait for a dip toward {inr(dip)} (Supertrend / VWAP-20 support)."
    stops = [v for v in (exit_below, entry - 2 * atr) if v and v < entry]
    stop = max(stops) if stops else entry - 2 * atr
    risk = entry - stop
    res = [p for p in swing_levels(row, "high") if p >= entry + risk]
    t1 = res[0] if res and res[0] <= entry + 2 * risk else entry + 1.5 * risk
    targets = sorted({round(t1, 2), round(entry + 2 * risk, 2), round(entry + 3 * risk, 2)})
    return entry, stop, targets, how


def short_plan(row, cat, reads):
    z, close, atr = row["zones"], row["close"], row["atr"]
    highs = [p for p in swing_levels(row, "high") if p > close]
    st_val = reads["supertrend"]["value"]
    candidates = [v for v in (z.get("structure_exit_below") if cat == "exit_today" else None,
                              st_val if reads["supertrend"]["state"] == "bear" else None,
                              highs[0] if highs else None) if v and v > close]
    stop = min(candidates) if candidates else close + 2 * atr
    stop = max(stop, close + 0.75 * atr)       # never tighter than 3/4 ATR (noise)
    entry = close
    risk = stop - entry
    sup = [p for p in reversed(swing_levels(row, "low")) if p <= entry - risk]
    t1 = sup[0] if sup and sup[0] >= entry - 2 * risk else entry - 1.5 * risk
    targets = sorted({round(t1, 2), round(entry - 2 * risk, 2), round(entry - 3 * risk, 2)}, reverse=True)
    how = (f"Longs: exit at the next open (closed below the structure exit). Bearish view only via F&O; it is wrong above {inr(stop)}."
           if cat == "exit_today" else
           f"Do not buy. Bearish view only via F&O on a weak bounce; it is wrong on a close above {inr(stop)}.")
    return entry, stop, targets, how


def sizing(entry, stop, side):
    risk_per_share = abs(entry - stop)
    if risk_per_share <= 0:
        return None
    qty = int((CAPITAL * RISK_PCT / 100) / risk_per_share)
    cap = int((CAPITAL * MAX_POSITION_PCT / 100) / entry)
    qty = min(qty, cap)
    return {"capital": CAPITAL, "risk_pct": RISK_PCT, "qty": qty, "value": r2(qty * entry, 0),
            "max_loss": r2(qty * risk_per_share, 0),
            "words": f"On Rs 10 lakh capital risking {RISK_PCT}% (Rs {CAPITAL * RISK_PCT / 100:,.0f}) per trade: "
                     f"{qty} shares = {inr(qty * entry)}; loss at stop about {inr(qty * risk_per_share)}"
                     + (" (capped at 20% of capital)." if qty == cap else ".")}


# ── hedges (F&O names only) ─────────────────────────────────────────────────

def strike_grid(opt):
    strikes = sorted((opt.get("oi_profile") or {}).get("strikes") or [])
    if len(strikes) < 3:
        return None, strikes
    steps = sorted(b - a for a, b in zip(strikes, strikes[1:]) if b > a)
    return steps[len(steps) // 2], strikes


def nearest(strikes, value, step, mode="near"):
    k = round(value / step) * step if mode == "near" else math.floor(value / step) * step if mode == "down" else math.ceil(value / step) * step
    return float(k)


def leg(side, kind, strike, spot, years, iv):
    return {"side": side, "type": kind, "strike": strike, "premium": r2(bs_price(spot, strike, years, iv, kind))}


def spread_metrics(legs, lot, kind):
    net = sum(l["premium"] * (1 if l["side"] == "BUY" else -1) for l in legs)   # >0 debit
    k = sorted(l["strike"] for l in legs)
    width = k[-1] - k[0]
    if kind == "debit":
        return {"net_debit": r2(net), "max_profit": r2((width - net) * lot, 0), "max_loss": r2(net * lot, 0),
                "reward_risk": r2((width - net) / net if net > 0 else None)}
    credit = -net
    return {"net_credit": r2(credit), "max_profit": r2(credit * lot, 0), "max_loss": r2((width - credit) * lot, 0),
            "reward_risk": r2(credit / (width - credit) if width > credit else None)}


def hedge(row, cat, plan, opt, lot):
    if not opt or not lot:
        return {"available": False,
                "words": "Not in F&O - no options to hedge with. The stop loss IS the hedge: size the position so the stop costs at most 0.5% of capital."}
    step, strikes = strike_grid(opt)
    iv = (opt.get("atm_iv") or 0) / 100
    dte = opt.get("days_to_expiry") or 0
    spot = row["close"]   # today's official close; IV / strikes / OI walls keep the options desk's own date
    if not step or iv <= 0 or dte < 3:
        return {"available": False, "words": "F&O stock, but option data (IV / strikes / expiry) is incomplete today."}
    years = dte / 365
    entry, stop, targets = plan["entry"], plan["stop"], plan["targets"]
    base = {"available": True, "expiry": opt.get("expiry"), "days_to_expiry": dte, "lot": lot, "atm_iv_pct": opt.get("atm_iv"),
            "call_wall": opt.get("call_wall"), "put_wall": opt.get("put_wall"), "buildup": opt.get("buildup"),
            "pricing": f"Black-Scholes estimate: today's close {row['close']}, ATM IV from the {OPTS_DATE or 'latest'} options file; real bid/ask will differ."}
    tone = CATEGORIES[cat]["tone"]
    if tone == "bull":
        k1 = nearest(strikes, entry, step, "up" if cat == "ready_to_break" else "near")
        k2 = max(k1 + step, nearest(strikes, targets[1] if len(targets) > 1 else targets[0], step))
        legs = [leg("BUY", "CE", k1, spot, years, iv), leg("SELL", "CE", k2, spot, years, iv)]
        m = spread_metrics(legs, lot, "debit")
        kp = nearest(strikes, stop, step, "down")
        put = leg("BUY", "PE", kp, spot, years, iv)
        base.update(name="Bull call spread", legs=legs, **m, breakeven=r2(k1 + m["net_debit"]),
                    words=f"BUY {k1:g} CE + SELL {k2:g} CE ({opt.get('expiry')}): pay about {inr(m['net_debit'])} x {lot} = {inr(m['max_loss'])} per lot (max loss). "
                          f"Max profit {inr(m['max_profit'])} per lot if it closes above {k2:g} at expiry. Breakeven {k1 + m['net_debit']:,.1f}.",
                    holder={"name": "Protective put", "legs": [put], "cost_per_lot": r2(put["premium"] * lot, 0),
                            "words": f"Already holding {lot} shares? BUY {kp:g} PE for about {inr(put['premium'])} x {lot} = {inr(put['premium'] * lot)}: "
                                     f"losses below {kp:g} are covered until {opt.get('expiry')} ({put['premium'] / spot * 100:.1f}% of the stock price)."})
    elif tone == "bear":
        k1 = nearest(strikes, entry, step)
        k2 = min(k1 - step, nearest(strikes, targets[1] if len(targets) > 1 else targets[0], step))
        legs = [leg("BUY", "PE", k1, spot, years, iv), leg("SELL", "PE", k2, spot, years, iv)]
        m = spread_metrics(legs, lot, "debit")
        kc = nearest(strikes, stop, step, "up")
        cc = leg("SELL", "CE", kc, spot, years, iv)
        base.update(name="Bear put spread", legs=legs, **m, breakeven=r2(k1 - m["net_debit"]),
                    words=f"BUY {k1:g} PE + SELL {k2:g} PE ({opt.get('expiry')}): pay about {inr(m['net_debit'])} x {lot} = {inr(m['max_loss'])} per lot (max loss). "
                          f"Max profit {inr(m['max_profit'])} per lot if it closes below {k2:g} at expiry. Breakeven {k1 - m['net_debit']:,.1f}.",
                    holder={"name": "Exit, or covered call while you decide", "legs": [cc], "credit_per_lot": r2(cc["premium"] * lot, 0),
                            "words": f"The rule says exit longs. If you must keep {lot} shares: SELL {kc:g} CE (above the stop / call wall) for about "
                                     f"{inr(cc['premium'] * lot)} per lot - a small cushion, NOT protection against a further fall."})
    else:
        pw, cw = opt.get("put_wall"), opt.get("call_wall")
        lo_k = nearest(strikes, pw if pw and pw < spot else spot * 0.94, step, "down")
        hi_k = nearest(strikes, cw if cw and cw > spot else spot * 1.06, step, "up")
        legs = [leg("BUY", "PE", lo_k - step, spot, years, iv), leg("SELL", "PE", lo_k, spot, years, iv),
                leg("SELL", "CE", hi_k, spot, years, iv), leg("BUY", "CE", hi_k + step, spot, years, iv)]
        credit = sum(l["premium"] * (-1 if l["side"] == "BUY" else 1) for l in legs)
        base.update(name="Iron condor (range)", legs=legs, net_credit=r2(credit), max_profit=r2(credit * lot, 0),
                    max_loss=r2((step - credit) * lot, 0), range=[lo_k, hi_k],
                    reward_risk=r2(credit / (step - credit) if step > credit else None),
                    words=f"No trend: collect about {inr(credit)} x {lot} = {inr(credit * lot)} per lot if it stays between {lo_k:g} and {hi_k:g} "
                          f"(OI walls) until {opt.get('expiry')}. Max loss {inr((step - credit) * lot)} per lot if it breaks out either side.",
                    holder={"name": "Collar", "words": f"Holding shares in a range: SELL {hi_k:g} CE and BUY {lo_k:g} PE - the call pays most of the put."})
    return base


# ── assembly ────────────────────────────────────────────────────────────────

def load(name):
    p = DOCS / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def session_jev_sources(as_of, symbols, jr, brief):
    """Use only same-session views; preserve source dates even when rejected."""
    expected = set(symbols)
    maps, metadata = [], {}
    for key, source, field in (("jev_rank", jr, "ranking"), ("market_brief", brief, "rows")):
        source_date = source.get("as_of")
        raw = source.get(field) or []
        eligible = [r for r in raw if r.get("symbol")
                    and (key != "market_brief" or r.get("judged"))
                    and source_date == as_of and bool(as_of)
                    and all(r.get(k) in (None, as_of) for k in ("as_of", "data_date"))]
        mapping = {r["symbol"]: dict(r) for r in eligible}
        covered = len(expected & mapping.keys())
        status = ("missing" if not source else "stale" if source_date != as_of
                  else "complete" if covered == len(expected) else "partial")
        metadata[key] = {"as_of": source_date, "status": status, "covered": covered,
                         "expected": len(expected), "source_rows": len(raw),
                         "accepted_rows": len(mapping), "generated_at": source.get("generated_at")}
        if key == "jev_rank":
            mapping = {sym: {**r, "_of": len(raw)} for sym, r in mapping.items()}
        maps.append(mapping)
    return maps[0], maps[1], {"scan_as_of": as_of, **metadata}


def jev_view(sym, jev_map, brief_map, side, freshness=None):
    j, b = jev_map.get(sym), brief_map.get(sym)
    if not j and not b:
        details = ("; ".join(f"{key}: {freshness[key]['status']} (source {freshness[key]['as_of'] or 'undated'})"
                             for key in ("jev_rank", "market_brief")) if freshness else "no same-session view supplied")
        return {"available": False, "words": f"Jev unavailable for {sym}: {details}. No Jev contribution to ranking."}
    out = {"available": True}
    if j:
        out.update(rank=j.get("rank"), of=j.get("_of"), composite=j.get("composite"), direction=j.get("direction_jev"),
                   regime=j.get("regime_jev"), confidence=j.get("confidence_gate"), signal=j.get("signal"),
                   setup_quality=j.get("setup_quality"), follow_through=j.get("follow_through"), risk_reward=j.get("risk_reward"))
    if b:
        out.update(context=b.get("context"), event_risk=b.get("event_risk"), driver=b.get("dominant_driver"))
    want = "up" if side == "long" else "down" if side == "short" else None
    agrees = None if not j or not want else (j.get("direction_jev") == want)
    out["agrees"] = agrees
    parts = []
    if j:
        parts.append(f"Jev ranks it #{j.get('rank')} of {j.get('_of')} (score {j.get('composite', 0):.2f}); reads the trend as "
                     f"{str(j.get('regime_jev') or '?').replace('_', ' ')}, direction {j.get('direction_jev') or '?'}, confidence {round((j.get('confidence_gate') or 0) * 100)}%.")
    if agrees is not None:
        parts.append("Jev AGREES with this category." if agrees else "Jev does NOT agree with this category - lower conviction.")
    if b and b.get("context"):
        parts.append(f"US + India news context: {b['context']}" + (f", event risk {b['event_risk']}" if b.get("event_risk") else "") + ".")
    if not j:
        parts.append("Same-session Jev ranking unavailable for this stock; news context only, no Jev rank contribution.")
    out["words"] = " ".join(parts)
    return out


def conviction(cat, counts, jev):
    tone = CATEGORIES[cat]["tone"]
    if tone == "neutral":
        return None
    aligned = counts["bull"] if tone == "bull" else counts["bear"]
    score = aligned / 5 * 60
    if jev.get("composite") is not None:
        score += jev["composite"] * 40 * (1 if jev.get("agrees") else 0.5)
    else:
        score += 20
    return round(score)


def build_stock(row, universe, member_lots, opt_map, jev_map, brief_map, as_of=None, freshness=None):
    bars = row["chart"]
    if len(bars) < 60:
        reads, counts, series = {}, {"bull": 0, "bear": 0, "neutral": 5}, {}
        cat = "data_check"
    else:
        reads, counts, series = indicator_pack(bars)
        cat = classify(row, reads)
    if as_of is not None and row.get("data_date") != as_of:
        cat = "data_check"
    meta = CATEGORIES[cat]
    sym = row["symbol"]
    lot = member_lots.get(sym)
    out = {
        "symbol": sym, "name": row.get("name"), "sector": row.get("sector"), "universe": universe, "fno": bool(lot),
        "lot": lot, "data_date": row.get("data_date"), "close": row.get("close"), "atr": r2(row.get("atr")),
        "change_pct": r2((bars[-1]["close"] / bars[-2]["close"] - 1) * 100) if len(bars) > 1 else None,
        "structure": row.get("structure"), "scanner_status": row.get("status"), "category": cat,
        "trigger": row["zones"].get("breakout_above"), "structure_exit": row["zones"].get("structure_exit_below"),
        "volume_ratio": row.get("volume_ratio"), "indicators": reads, "indicator_counts": counts,
    }
    if cat == "data_check":
        out.update(plan=None, hedge=None, jev=jev_view(sym, jev_map, brief_map, None, freshness), conviction=None,
                   summary=f"{sym}: {meta['meaning']}" + (
                       f" Price session {row.get('data_date') or 'unavailable'} differs from scan {as_of}; no ranked plan."
                       if as_of is not None and row.get("data_date") != as_of else ""))
        return out, series
    side = meta["side"]
    if meta["tone"] == "bull":
        entry, stop, targets, how = long_plan(row, cat, reads)
    elif meta["tone"] == "bear":
        entry, stop, targets, how = short_plan(row, cat, reads)
    else:
        entry, stop, targets = row["close"], None, []
        trig, ex = out["trigger"], out["structure_exit"]
        how = (f"No trade. Turns bullish on a close above {inr(trig)}; bearish on a close below {inr(ex)}."
               if trig and ex else "No trade until a clear trigger forms.")
    plan = {"side": side, "entry": r2(entry), "stop": r2(stop), "targets": [r2(t) for t in targets], "how": how}
    if stop is not None:
        risk = abs(entry - stop)
        plan.update(risk=r2(risk), risk_pct=r2(risk / entry * 100),
                    reward_risk=[r2(abs(t - entry) / risk) if risk else None for t in targets],
                    next_target=r2(targets[0]) if targets else None)
        if side == "long":
            plan["sizing"] = sizing(entry, stop, side)
        verb = "Buy" if side == "long" else "Bearish"
        plan["words"] = (f"{verb} {inr(entry)} | stop {inr(stop)} ({risk / entry * 100:.1f}% risk) | next target {inr(targets[0])} "
                         f"({abs(targets[0] - entry) / risk:.1f}R)" + (f", then {', '.join(inr(t) for t in targets[1:])}" if len(targets) > 1 else "") + ".")
    else:
        plan["words"] = how
    jev = jev_view(sym, jev_map, brief_map, side if side in ("long", "short") else None, freshness)
    out.update(plan=plan, jev=jev, hedge=hedge(row, cat, {"entry": entry, "stop": stop or entry, "targets": targets or [entry]},
                                               opt_map.get(sym), lot),
               conviction=conviction(cat, counts, jev))
    agree = counts["bull"] if meta["tone"] == "bull" else counts["bear"] if meta["tone"] == "bear" else None
    out["summary"] = (f"{meta['label']}: {plan['words']} "
                      + (f"{agree} of 5 indicators agree. " if agree is not None else f"Indicators: {counts['bull']} bullish, {counts['bear']} bearish. ")
                      + (f"Jev #{jev['rank']}/{jev['of']} {'agrees' if jev.get('agrees') else 'disagrees' if jev.get('agrees') is False else 'neutral'}."
                         if jev.get("rank") else ""))
    return out, series


def previous_published(as_of):
    """Latest published compact list strictly before `as_of` (data/daily_setups_history/<date>.json)."""
    if not HISTORY.exists():
        return None
    days = sorted(p.stem for p in HISTORY.glob("*.json") if p.stem < (as_of or ""))
    if not days:
        return None
    d = json.loads((HISTORY / f"{days[-1]}.json").read_text(encoding="utf-8"))
    out = {s["symbol"]: s for s in d.get("stocks") or []}
    out["_as_of"] = d.get("as_of") or days[-1]
    return out


def rebuilt_prev(row):
    """Yesterday's category and plan, rebuilt only from levels known at yesterday's close."""
    pr = sig.prior_view(row)
    if not pr:
        return None
    reads = indicator_pack(pr["chart"])[0]
    cat = classify(pr, reads)
    tone = CATEGORIES[cat]["tone"]
    if tone == "bull":
        entry, stop, targets, _ = long_plan(pr, cat, reads)
    elif tone == "bear":
        entry, stop, targets, _ = short_plan(pr, cat, reads)
    else:
        return {"category": cat, "side": CATEGORIES[cat]["side"], "entry": None, "stop": None, "next_target": None,
                "date": pr["data_date"], "source": "rebuilt"}
    return {"category": cat, "side": CATEGORIES[cat]["side"], "entry": r2(entry), "stop": r2(stop),
            "next_target": r2(targets[0]) if targets else None, "date": pr["data_date"], "source": "rebuilt"}


def event_words(key, bars, ser, fib, prev, crossed, s):
    t, y = bars[-1], bars[-2]
    lab = lambda c: CATEGORIES.get(c, {}).get("label", c)
    src = "yesterday's published list" if (prev or {}).get("source") == "published" else "yesterday's plan (rebuilt)"
    a = next((x for x in fib["anchors"] if x["method"] == fib["auto"]), None) if fib else None
    lv = lambda r: next((l["price"] for l in a["levels"] if l["r"] == r), None) if a else None
    rsi, st, up, lo = ser.get("rsi") or [], ser.get("supertrend") or [], ser.get("bb_upper") or [], ser.get("bb_lower") or []
    trig = y.get("confirmed_high") or t.get("confirmed_high")
    floor = y.get("confirmed_low") or t.get("confirmed_low")
    w = {
        "breakout": f"Closed {inr(t['close'])} above the closing trigger {inr(trig)}.",
        "structure_exit": f"Closed {inr(t['close'])} below the last swing low {inr(floor)}.",
        "target_hit": (f"Today's {'high' if (prev or {}).get('side') == 'long' else 'low'} "
                       f"{inr(t['high'] if (prev or {}).get('side') == 'long' else t['low'])} reached the next target {inr((prev or {}).get('next_target'))} from {src}."),
        "stop_hit": (f"Today's {'low' if (prev or {}).get('side') == 'long' else 'high'} "
                     f"{inr(t['low'] if (prev or {}).get('side') == 'long' else t['high'])} touched the stop {inr((prev or {}).get('stop'))} from {src}."),
        "upgraded": f"{lab((prev or {}).get('category'))} -> {lab(s['category'])}.",
        "downgraded": f"{lab((prev or {}).get('category'))} -> {lab(s['category'])}.",
        "st_flip_up": f"Supertrend turned up; its line is now {inr(st[-1] if st else None)} under the price.",
        "st_flip_down": f"Supertrend turned down; its line is now {inr(st[-1] if st else None)} above the price.",
        "momentum_up": f"RSI {rsi[-2]:.0f} -> {rsi[-1]:.0f}." if len(rsi) > 1 and rsi[-1] is not None and rsi[-2] is not None else "",
        "momentum_down": f"RSI {rsi[-2]:.0f} -> {rsi[-1]:.0f}." if len(rsi) > 1 and rsi[-1] is not None and rsi[-2] is not None else "",
        "bb_break_up": f"Close {inr(t['close'])} above the upper band {inr(up[-1] if up else None)}.",
        "bb_break_down": f"Close {inr(t['close'])} below the lower band {inr(lo[-1] if lo else None)}.",
        "squeeze": f"Band width {s['indicators'].get('bollinger', {}).get('width_pct')}% of price.",
        "volume_spike": (f"Volume {(t.get('volume') or 0) / t['volume_average20']:.1f}x the 20-session average."
                         if t.get("volume_average20") else ""),
        "high_20d": f"Close {inr(t['close'])} above the prior 20-session high {inr(max(b['high'] for b in bars[-21:-1]))}.",
        "low_20d": f"Close {inr(t['close'])} below the prior 20-session low {inr(min(b['low'] for b in bars[-21:-1]))}.",
        "fib_golden": (f"{a['retrace_pct']:.0f}% retraced; golden zone {inr(lv(0.618) if a and a['dir'] == 'up' else lv(0.5))}"
                       f" to {inr(lv(0.5) if a and a['dir'] == 'up' else lv(0.618))}." if a else ""),
        "fib_break": "; ".join(f"Closed {c['dir']} through {c['r'] * 100:.1f}% ({inr(c['price'])})" for c in crossed) + "." if crossed else "",
        "fib_target": ("Today's range reached the " + " / ".join(f"{e['r'] * 100:.1f}% extension {inr(e['price'])}" for e in a["extensions"]
                                                           if t["low"] <= e["price"] <= t["high"]) + "." if a else ""),
    }
    return w.get(key, "")


def enrich(s, row, ser, published):
    """Fibonacci, today's events (vs the previous session) and this stock's own breakout / exit history."""
    bars = row["chart"]
    s.update(fib=None, events=[], event_words={}, prev=None, history=None)
    if len(bars) < 62 or not ser:
        return
    s["fib"] = sig.fibonacci(bars, row["close"], inr)
    s["history"] = sig.history_stats(bars)
    pub = (published or {}).get(s["symbol"])
    if pub and pub.get("category"):
        prev = {"category": pub["category"], "side": pub.get("side") or CATEGORIES.get(pub["category"], {}).get("side"),
                "entry": pub.get("entry"), "stop": pub.get("stop"), "next_target": pub.get("next_target"),
                "date": published.get("_as_of"), "source": "published"}
    else:
        prev = rebuilt_prev(row)
    s["prev"] = prev
    order = {k: v["order"] for k, v in CATEGORIES.items()}
    events, crossed = sig.detect_events(bars, ser, s.get("indicators") or {}, s["fib"], s["category"], prev, order)
    s["events"] = events
    s["event_words"] = {k: event_words(k, bars, ser, s["fib"], prev, crossed, s) for k in events}


def main():
    scan, fno = load("hhhl_scan.json"), load("hhhl_fno.json") or {}
    if not scan or len(scan.get("rows") or []) < 150:
        raise SystemExit("hhhl_scan.json missing or incomplete")
    global OPTS_DATE
    jr, brief, opts = load("jev_rank.json") or {}, load("market_brief.json") or {}, load("options_desk.json") or {}
    OPTS_DATE = opts.get("as_of")
    as_of = scan.get("as_of")
    jev_map, brief_map, freshness = session_jev_sources(as_of, [r["symbol"] for r in scan["rows"]], jr, brief)
    opt_map = {r["symbol"]: r for r in opts.get("rows") or [] if r.get("kind") == "stock"}
    member_lots = {m["symbol"]: m.get("lot_size") for m in ((fno.get("membership") or {}).get("members") or [])}

    published = previous_published(scan.get("as_of"))
    stocks, series = [], {}
    rows = [(r, "Nifty 200") for r in scan["rows"]] + [(r, "F&O extra") for r in fno.get("rows") or []]
    seen = set()
    for row, uni in rows:
        if row["symbol"] in seen:
            continue
        seen.add(row["symbol"])
        try:
            s, ser = build_stock(row, uni, member_lots, opt_map, jev_map, brief_map, as_of, freshness)
            enrich(s, row, ser, published)
        except (KeyError, TypeError, ValueError, ZeroDivisionError, StopIteration) as exc:
            s, ser = {"symbol": row.get("symbol"), "name": row.get("name"), "universe": uni, "category": "data_check",
                      "close": row.get("close"), "data_date": row.get("data_date"), "plan": None, "hedge": None,
                      "jev": {"available": False}, "indicators": {}, "events": [], "summary": f"Could not compute: {exc}"}, {}
        stocks.append(s)
        if ser:
            ch = row["chart"][-SERIES_BARS:]
            cut = len(row["chart"]) - len(ch)
            series[s["symbol"]] = {
                "dates": [b["date"] for b in ch], "o": [r2(b["open"]) for b in ch], "h": [r2(b["high"]) for b in ch],
                "l": [r2(b["low"]) for b in ch], "c": [r2(b["close"]) for b in ch],
                "v": [int(b.get("volume") or 0) for b in ch],
                "swings": [{"d": p["pivot_date"], "p": r2(p["price"]), "k": p["kind"], "t": p.get("label")}
                           for p in (row.get("chart_swings") or [])[-14:]],
                **{k: v[cut:] for k, v in ser.items()}}

    def sort_key(s):
        return (CATEGORIES[s["category"]]["order"], -(s.get("conviction") or 0),
                (s.get("jev") or {}).get("rank") or 999, s["symbol"])
    stocks.sort(key=sort_key)
    rankable = {s["symbol"] for s in stocks if s["category"] != "data_check"}
    ranking = rank.rank_all(stocks, {r["symbol"]: r["chart"] for r, _ in rows
                                   if r["symbol"] in rankable and r.get("data_date") == as_of
                                   and len(r.get("chart") or []) >= 60})
    counts = {k: sum(1 for s in stocks if s["category"] == k) for k in CATEGORIES}
    market = scan.get("market") or {}
    as_of = scan.get("as_of")
    gate_open = bool(market.get("new_entries_allowed"))
    payload = {
        "version": VERSION, "as_of": as_of, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "universe_count": len(stocks), "fno_count": sum(1 for s in stocks if s.get("fno")),
        "inputs": {
            "hhhl_scan": scan.get("as_of"), "hhhl_fno": fno.get("as_of"), "jev_rank": jr.get("as_of"),
            "market_brief": brief.get("as_of"), "options_desk": opts.get("as_of"),
        },
        "freshness": freshness,
        "market": {
            "close": market.get("close"), "sma200": r2(market.get("sma200")), "gate_open": gate_open,
            "words": (f"Market gate OPEN: Nifty {market.get('close'):,.2f} is above its 200-day average {market.get('sma200'):,.2f}; long setups are allowed."
                      if gate_open else
                      f"Market gate CLOSED: Nifty {market.get('close'):,.2f} is below its 200-day average {market.get('sma200'):,.2f}. "
                      f"The strategy rule blocks NEW longs - bullish plans below are paper-only until Nifty closes back above it."),
        },
        "categories": [{"key": k, **{kk: vv for kk, vv in v.items() if kk != "order"}, "count": counts[k]} for k, v in CATEGORIES.items()],
        "events": [{"key": k, **v, "count": sum(1 for s in stocks if k in (s.get("events") or []))} for k, v in sig.EVENTS.items()],
        "ranking": ranking,
        "previous_list": published.get("_as_of") if published else None,
        "indicator_guide": INDICATORS,
        "method": {
            "conviction": "Directional setups only: (indicators agreeing with the category / 5) x 60 + Jev composite x 40 "
                          "(halved when Jev disagrees; 20 points when Jev has no view).",
            "long_stop": "Higher of the structure exit and entry - 2 x ATR14 (scanner rule).",
            "targets": "T1 = nearest confirmed swing high above entry (or 1.5R if none within 2R), T2 = 2R, T3 = 3R. Bearish setups mirror this with swing lows.",
            "hedges": "F&O names only. Premiums are Black-Scholes estimates from end-of-day ATM IV and the official lot size.",
            "fibonacci": "Three anchors per stock (last 3 x ATR zigzag leg, 3-month range, 6-month range). Each is scored by how often price "
                         "reacted at its 38.2-78.6% levels after the leg ended; the best fit is 'auto'. Daily candles only - there is no intraday data.",
            "events": "Compared with the previous session: yesterday's published list when it exists, otherwise yesterday's plan rebuilt "
                      "from the levels known at yesterday's close. Target / stop hits use today's high and low.",
        },
        "limitations": [
            "End-of-day research, not live quotes and not investment advice. No strategy here is validated as profitable.",
            "Categories describe what price has done; they do not predict that targets will be reached.",
            "Option premiums are model estimates; check the live chain, liquidity and margin before trading.",
            "Short trades are shown only for F&O names; cash shares cannot be shorted overnight.",
        ],
        "stocks": stocks,
        "series_file": "daily_setups_series.json",
    }
    OUT.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    (DOCS / "daily_setups_series.json").write_text(
        json.dumps({"as_of": as_of, "series": series}, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    HISTORY.mkdir(parents=True, exist_ok=True)
    compact = {"as_of": as_of, "generated_at": payload["generated_at"], "stocks": [
        {"symbol": s["symbol"], "category": s["category"], "close": s.get("close"),
         **({k: s["plan"].get(k) for k in ("side", "entry", "stop", "next_target")} if s.get("plan") else {}),
         "events": s.get("events") or [], "conviction": s.get("conviction")} for s in stocks]}
    (HISTORY / f"{as_of}.json").write_text(json.dumps(compact, separators=(",", ":")), encoding="utf-8")
    print(f"daily_setups {as_of}: {len(stocks)} stocks | " + ", ".join(f"{k}={v}" for k, v in counts.items() if v))


if __name__ == "__main__":
    main()
