"""Auto-Fibonacci, today's events and per-stock history for daily_setups.py.

Only daily end-of-day candles exist in this repo, so "the right chart" for Fibonacci means the right SWING,
not the right minute timeframe. For every stock three anchors are measured:
  leg  - the last completed zigzag leg (a move of at least 3 x ATR14)
  3m   - the high/low range of the last 63 sessions (about 3 months)
  6m   - the high/low range of the whole chart (about 6 months)
Each anchor is scored by how often price actually reacted at its 38.2 / 50 / 61.8 / 78.6% levels after the
extreme (touched within 0.3 ATR and closed back on the trend side). The highest score is picked as "auto".
It is a best fit to this stock's own past behaviour, not a guarantee the next reaction will happen.
"""
from __future__ import annotations

RETRACE = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
EXTEND = [1.272, 1.618]
REACT = [0.382, 0.5, 0.618, 0.786]

EVENTS = {
    "breakout":        {"label": "Broke out today",        "tone": "bull", "meaning": "Closed above its closing trigger (last confirmed swing high)."},
    "structure_exit":  {"label": "Structure exit today",   "tone": "bear", "meaning": "Closed below its last confirmed swing low: exit condition for longs."},
    "target_hit":      {"label": "Hit target",             "tone": "bull", "meaning": "Reached the next target of yesterday's plan during today's session."},
    "stop_hit":        {"label": "Hit stop",               "tone": "bear", "meaning": "Touched the stop loss of yesterday's plan during today's session."},
    "upgraded":        {"label": "Category upgraded",      "tone": "bull", "meaning": "Moved to a more bullish category than yesterday."},
    "downgraded":      {"label": "Category downgraded",    "tone": "bear", "meaning": "Moved to a more bearish category than yesterday."},
    "st_flip_up":      {"label": "Supertrend flipped up",  "tone": "bull", "meaning": "Closed above the Supertrend line: trend turned up today."},
    "st_flip_down":    {"label": "Supertrend flipped down", "tone": "bear", "meaning": "Closed below the Supertrend line: trend turned down today."},
    "momentum_up":     {"label": "RSI crossed 55",         "tone": "bull", "meaning": "RSI moved above 55 today: buyers took control."},
    "momentum_down":   {"label": "RSI crossed 45",         "tone": "bear", "meaning": "RSI fell below 45 today: sellers took control."},
    "bb_break_up":     {"label": "Closed above upper band", "tone": "bull", "meaning": "First close above the upper Bollinger band: volatility expanding upward."},
    "bb_break_down":   {"label": "Closed below lower band", "tone": "bear", "meaning": "First close below the lower Bollinger band: volatility expanding downward."},
    "squeeze":         {"label": "Bollinger squeeze",      "tone": "neutral", "meaning": "Bands are among their narrowest of the window: a large move often follows."},
    "volume_spike":    {"label": "Volume 2x average",      "tone": "neutral", "meaning": "Today's volume was at least twice the 20-session average."},
    "high_20d":        {"label": "New 20-day high close",  "tone": "bull", "meaning": "Closed above every high of the previous 20 sessions."},
    "low_20d":         {"label": "New 20-day low close",   "tone": "bear", "meaning": "Closed below every low of the previous 20 sessions."},
    "fib_golden":      {"label": "In Fib golden zone",     "tone": "neutral", "meaning": "Price sits in the 50-61.8% retracement: the most watched pullback zone."},
    "fib_break":       {"label": "Crossed a Fib level",    "tone": "neutral", "meaning": "Today's close crossed a Fibonacci level that yesterday's close had not."},
    "fib_target":      {"label": "Reached Fib extension",  "tone": "neutral", "meaning": "Today's range reached the 127.2% or 161.8% extension of the auto leg."},
}


def atr14(bars, n=14):
    tr = []
    for i, b in enumerate(bars):
        pc = bars[i - 1]["close"] if i else b["close"]
        tr.append(max(b["high"] - b["low"], abs(b["high"] - pc), abs(b["low"] - pc)))
    if len(tr) < n:
        return sum(tr) / max(1, len(tr))
    a = sum(tr[:n]) / n
    for v in tr[n:]:
        a = (a * (n - 1) + v) / n
    return a


def zigzag(bars, threshold):
    """Alternating pivots (index, price, 'H'/'L'). A pivot is fixed once price reverses by >= threshold from it.
    The final element is the still-developing extreme."""
    if len(bars) < 2:
        return []
    piv = []
    trend = 0                      # 0 unknown, 1 rising (tracking a high), -1 falling (tracking a low)
    hi_i = lo_i = 0
    for i, b in enumerate(bars):
        if trend >= 0 and b["high"] >= bars[hi_i]["high"]:
            hi_i = i
        if trend <= 0 and b["low"] <= bars[lo_i]["low"]:
            lo_i = i
        if trend >= 0 and bars[hi_i]["high"] - b["low"] >= threshold and (trend == 1 or hi_i > lo_i):
            piv.append((hi_i, bars[hi_i]["high"], "H"))
            trend, lo_i = -1, i
        elif trend <= 0 and b["high"] - bars[lo_i]["low"] >= threshold and (trend == -1 or lo_i > hi_i):
            piv.append((lo_i, bars[lo_i]["low"], "L"))
            trend, hi_i = 1, i
    if trend == 1:
        piv.append((hi_i, bars[hi_i]["high"], "H"))
    elif trend == -1:
        piv.append((lo_i, bars[lo_i]["low"], "L"))
    return piv


def fib_levels(lo, hi, up):
    span = hi - lo
    if up:   # measured low -> high: retracements fall from the high, extensions above the high
        ret = [{"r": r, "price": round(hi - r * span, 2)} for r in RETRACE]
        ext = [{"r": e, "price": round(lo + e * span, 2)} for e in EXTEND]
    else:    # measured high -> low: retracements rise from the low, extensions below the low
        ret = [{"r": r, "price": round(lo + r * span, 2)} for r in RETRACE]
        ext = [{"r": e, "price": round(hi - e * span, 2)} for e in EXTEND]
    return ret, ext


def anchor_from(bars, i_lo, i_hi, method, label):
    lo, hi = bars[i_lo]["low"], bars[i_hi]["high"]
    if hi <= lo:
        return None
    up = i_hi > i_lo                              # the later extreme sets the leg direction
    start, end = (i_lo, i_hi) if up else (i_hi, i_lo)
    ret, ext = fib_levels(lo, hi, up)
    return {"method": method, "label": label, "dir": "up" if up else "down",
            "from": {"date": bars[start]["date"], "price": round(bars[start]["low" if up else "high"], 2)},
            "to": {"date": bars[end]["date"], "price": round(bars[end]["high" if up else "low"], 2)},
            "end_index": end, "lo": round(lo, 2), "hi": round(hi, 2), "levels": ret, "extensions": ext}


def score_anchor(a, bars, atr):
    """Count reactions at 38.2-78.6% after the leg's end. Broken legs (close beyond 100%) are penalised."""
    lo, hi, up = a["lo"], a["hi"], a["dir"] == "up"
    span = hi - lo
    reactions, hits = 0, []
    broken = False
    for b in bars[a["end_index"] + 1:]:
        if (up and b["close"] < lo) or (not up and b["close"] > hi):
            broken = True
        for r in REACT:
            lvl = hi - r * span if up else lo + r * span
            if up and b["low"] <= lvl + 0.3 * atr and b["low"] >= lvl - 0.3 * atr and b["close"] > lvl:
                reactions += 1; hits.append({"date": b["date"], "r": r}); break
            if not up and b["high"] >= lvl - 0.3 * atr and b["high"] <= lvl + 0.3 * atr and b["close"] < lvl:
                reactions += 1; hits.append({"date": b["date"], "r": r}); break
    size_atr = span / atr if atr else 0
    score = reactions * 2 + min(size_atr, 12) / 4 - (5 if broken else 0)
    return round(score, 2), reactions, hits[-3:], broken, round(size_atr, 1)


def position_words(a, close, inr):
    up, lo, hi = a["dir"] == "up", a["lo"], a["hi"]
    span = hi - lo
    ret = (hi - close) / span if up else (close - lo) / span
    pct = ret * 100
    if ret < 0:
        zone = "beyond the leg's extreme - extension territory"
    elif ret < 0.236:
        zone = "a shallow pullback (strong trend)"
    elif ret < 0.382:
        zone = "a normal pullback"
    elif ret < 0.5:
        zone = "a moderate pullback"
    elif ret <= 0.618:
        zone = "the 50-61.8% GOLDEN ZONE (most watched pullback area)"
    elif ret <= 0.786:
        zone = "a deep pullback"
    elif ret <= 1.0:
        zone = "a very deep pullback - the leg is at risk"
    else:
        zone = "past 100% - this leg has failed"
    levels = sorted([*a["levels"], *a["extensions"]], key=lambda x: x["price"])
    below = [l for l in levels if l["price"] < close]
    above = [l for l in levels if l["price"] > close]
    sup, res = (below[-1] if below else None), (above[0] if above else None)
    name = lambda l: f"{l['r'] * 100:.1f}% ({inr(l['price'])})"
    leg = (f"{'Up' if up else 'Down'}-leg {inr(a['from']['price'])} ({a['from']['date']}) to {inr(a['to']['price'])} ({a['to']['date']})")
    words = f"{leg}. Price {inr(close)} is {pct:.0f}% retraced: {zone}."
    if sup:
        words += f" Nearest Fib support {name(sup)}"
    if res:
        words += (", " if sup else " ") + f"resistance {name(res)}"
    words += "."
    key = next((l for l in a["levels"] if l["r"] == 0.618), None)
    if key and 0 <= ret <= 1:
        words += (f" The {'up' if up else 'down'}trend leg stays valid while price closes {'above' if up else 'below'} 61.8% ({inr(key['price'])})."
                  if ret < 0.618 else f" Below 61.8% ({inr(key['price'])}) already - watch 78.6% / 100%.")
    ext = a["extensions"][0]
    words += f" Extension target 127.2% = {inr(ext['price'])}."
    return round(pct, 1), zone, sup, res, words


def fibonacci(bars, close, inr):
    if len(bars) < 30:
        return None
    atr = atr14(bars)
    cands = []
    piv = zigzag(bars, 3 * atr)
    if len(piv) >= 2:
        (i1, _, k1), (i2, _, _k2) = piv[-2], piv[-1]
        lo_i, hi_i = (i1, i2) if k1 == "L" else (i2, i1)
        a = anchor_from(bars, lo_i, hi_i, "leg", "Last swing leg (3 x ATR zigzag)")
        if a:
            cands.append(a)
    for method, label, n in (("3m", "3-month range (63 sessions)", 63), ("6m", "6-month range (whole chart)", len(bars))):
        w0 = max(0, len(bars) - n)
        seg = range(w0, len(bars))
        hi_i = max(seg, key=lambda i: bars[i]["high"])
        lo_i = min(seg, key=lambda i: bars[i]["low"])
        a = anchor_from(bars, lo_i, hi_i, method, label)
        if a and not any(c["from"] == a["from"] and c["to"] == a["to"] for c in cands):
            cands.append(a)
    if not cands:
        return None
    for a in cands:
        a["score"], a["reactions"], a["recent_reactions"], a["broken"], a["size_atr"] = score_anchor(a, bars, atr)
        a["retrace_pct"], a["zone"], a["support"], a["resistance"], a["words"] = position_words(a, close, inr)
    best = max(cands, key=lambda a: (a["score"], a["method"] == "leg"))
    for a in cands:
        a.pop("end_index", None)
    why = (f"Auto picked the {best['label'].lower()}: price reacted at its 38.2-78.6% levels {best['reactions']} time"
           f"{'s' if best['reactions'] != 1 else ''} after the leg ended"
           + (" (" + ", ".join(f"{h['r'] * 100:.1f}% on {h['date']}" for h in best["recent_reactions"]) + ")" if best["recent_reactions"] else "")
           + f"; leg size {best['size_atr']} x ATR."
           + (" Others scored " + ", ".join(f"{c['method']} {c['score']}" for c in cands if c is not best) + "." if len(cands) > 1 else ""))
    return {"auto": best["method"], "why": why, "anchors": cands}


def cross_levels(prev_close, close, fib):
    a = next(x for x in fib["anchors"] if x["method"] == fib["auto"])
    out = []
    for l in a["levels"][1:-1]:
        p = l["price"]
        if (prev_close - p) * (close - p) < 0:
            out.append({"r": l["r"], "price": p, "dir": "up" if close > p else "down"})
    return out


def history_stats(bars, horizon=10):
    """What this stock did after its own past closing breakouts / structure exits (inside the chart window)."""
    n, out = len(bars), {}
    for key, flag, good in (("breakouts", "structure_breakout", 1), ("exits", "structure_exit", -1)):
        rets = [(bars[i + horizon]["close"] / bars[i]["close"] - 1) * 100 for i in range(n - horizon) if bars[i].get(flag)]
        if not rets:
            out[key] = {"count": 0}
            continue
        worked = sum(1 for r in rets if r * good > 0)
        out[key] = {"count": len(rets), "worked": worked, "avg_pct": round(sum(rets) / len(rets), 2),
                    "best_pct": round(max(rets), 2), "worst_pct": round(min(rets), 2)}
    b, e = out["breakouts"], out["exits"]
    parts = []
    if b["count"]:
        parts.append(f"After its last {b['count']} closing breakout{'s' if b['count'] > 1 else ''} this stock moved {b['avg_pct']:+.1f}% on average over "
                     f"{horizon} sessions ({b['worked']} of {b['count']} went up).")
    else:
        parts.append("No completed closing breakouts in the chart window to learn from.")
    if e["count"]:
        parts.append(f"After {e['count']} structure exit{'s' if e['count'] > 1 else ''} it moved {e['avg_pct']:+.1f}% on average ({e['worked']} of {e['count']} kept falling).")
    parts.append("Small samples: a habit of this stock, not a prediction.")
    out["horizon"] = horizon
    out["words"] = " ".join(parts)
    return out


def detect_events(bars, series, reads, fib, cat_today, prev, order):
    """Event keys for the last bar. `prev` = yesterday's plan {category, side, entry, stop, next_target, source}."""
    ev = []
    t, y = bars[-1], bars[-2]
    if t.get("structure_breakout"):
        ev.append("breakout")
    if t.get("structure_exit"):
        ev.append("structure_exit")
    if prev and prev.get("stop") is not None and prev.get("next_target") is not None and prev.get("entry") is not None:
        # A hit only counts if yesterday's plan could actually have been entered today:
        # long above yesterday's close = buy-stop (today's high must reach it); long below it = buy-limit on a dip
        # (today's low must reach it); bearish plans are entered at yesterday's close.
        e, yc = prev["entry"], y["close"]
        if prev["side"] == "long":
            entered = t["high"] >= e if e > yc else t["low"] <= e if e < yc else True
            if entered and t["high"] >= prev["next_target"]:
                ev.append("target_hit")
            if entered and t["low"] <= prev["stop"]:
                ev.append("stop_hit")
        elif prev["side"] == "short":
            if t["low"] <= prev["next_target"]:
                ev.append("target_hit")
            if t["high"] >= prev["stop"]:
                ev.append("stop_hit")
    if prev and prev.get("category") in order and cat_today in order and "data_check" not in (prev["category"], cat_today):
        if order[cat_today] < order[prev["category"]]:
            ev.append("upgraded")
        elif order[cat_today] > order[prev["category"]]:
            ev.append("downgraded")
    d = series.get("supertrend_dir") or []
    if len(d) >= 2 and d[-1] is not None and d[-2] is not None and d[-1] != d[-2]:
        ev.append("st_flip_up" if d[-1] == 1 else "st_flip_down")
    r = series.get("rsi") or []
    if len(r) >= 2 and r[-1] is not None and r[-2] is not None:
        if r[-2] <= 55 < r[-1]:
            ev.append("momentum_up")
        if r[-2] >= 45 > r[-1]:
            ev.append("momentum_down")
    up, lo = series.get("bb_upper") or [], series.get("bb_lower") or []
    if len(up) >= 2 and None not in (up[-1], up[-2], lo[-1], lo[-2]):
        if t["close"] > up[-1] and y["close"] <= up[-2]:
            ev.append("bb_break_up")
        if t["close"] < lo[-1] and y["close"] >= lo[-2]:
            ev.append("bb_break_down")
    if reads.get("bollinger", {}).get("squeeze"):
        ev.append("squeeze")
    avg = t.get("volume_average20")
    if avg and (t.get("volume") or 0) >= 2 * avg:
        ev.append("volume_spike")
    prior20 = bars[-21:-1]
    if len(prior20) == 20:
        if t["close"] > max(b["high"] for b in prior20):
            ev.append("high_20d")
        if t["close"] < min(b["low"] for b in prior20):
            ev.append("low_20d")
    crossed = []
    if fib:
        a = next(x for x in fib["anchors"] if x["method"] == fib["auto"])
        if 50 <= a["retrace_pct"] <= 61.8:
            ev.append("fib_golden")
        crossed = cross_levels(y["close"], t["close"], fib)
        if crossed:
            ev.append("fib_break")
        ext = a["extensions"]
        if any((t["low"] <= e["price"] <= t["high"]) for e in ext):
            ev.append("fib_target")
    return ev, crossed


def prior_view(row, inr_unused=None):
    """Rebuild yesterday's scanner-like row from the chart (levels as they were known at yesterday's close)."""
    bars = row["chart"]
    if len(bars) < 62:
        return None
    pb, p = bars[:-1], bars[-2]
    day = p["date"]
    swings = [s for s in (row.get("chart_swings") or []) if s.get("confirmed_on", s.get("pivot_date")) <= day]
    highs = [s["price"] for s in swings if s["kind"] == "high"][-2:]
    lows = [s["price"] for s in swings if s["kind"] == "low"][-2:]
    if len(highs) == 2 and len(lows) == 2:
        structure = "HH / HL" if highs[1] > highs[0] and lows[1] > lows[0] else "LH / LL" if highs[1] < highs[0] and lows[1] < lows[0] else "MIXED"
    else:
        structure = "UNCONFIRMED"
    ch, cl = p.get("confirmed_high"), p.get("confirmed_low")
    return {**row, "chart": pb, "chart_swings": swings, "close": p["close"], "data_date": day, "atr": atr14(pb),
            "structure": structure, "zones": {"breakout_above": ch, "structure_exit_below": cl},
            "fresh_breakout": bool(p.get("structure_breakout")), "sell_triggered_today": bool(p.get("structure_exit")),
            "exit_condition": bool(cl and p["close"] < cl), "complete_for_session": True, "data_warnings": []}
