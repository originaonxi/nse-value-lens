"""BUY / SELL / WATCH ranking for the daily setups, built only from facts on each stock's chart.

Chart score: 11 factors, each worth a fixed number of points to the bull side or the bear side.
Bull points and bear points are each out of 100. Net score = bull - bear (-100 .. +100).
Every factor keeps its measured value, so each point on the page can be traced back to the chart.

Lists follow the HH/HL structure category (a chart fact):
  BUY   = breakout today, ready to break, uptrend          ranked by net score, highest first
  SELL  = structure exit today, below structure, downtrend ranked by net score, lowest first
  WATCH = turning up, sideways                           ranked by |net| (closest to a decision), with its lean
Final ranking inside every list is done by Jev, out of 100 (Jev's own maths, see JEV_POINTS):
  Jev score = 35 x setup_quality/4 + 30 x follow_through/4 + 35 x risk_reward/4   (each answer is a level 0..4)
  BUY and WATCH: Jev list score = Jev score, highest first.
  SELL: Jev scores the setup it sees, it does not score shorts, so Jev list score = 100 - Jev score (weakest setup first).
  Stocks Jev did not assess (F&O names outside Jev's Nifty 200 run) follow, in chart-score order, and are labelled so.
The chart score is kept next to it as the fact check; Combined rank = average of chart rank and Jev rank.
Ties on the Jev list score are broken by chart rank.
"""
from __future__ import annotations

LISTS = {
    "buy": {"label": "Buy", "tone": "bull", "categories": ["breakout_today", "ready_to_break", "uptrend"],
            "meaning": "Rising structure (higher highs and higher lows). Ranked by Jev score out of 100, highest first."},
    "sell": {"label": "Sell", "tone": "bear", "categories": ["exit_today", "below_structure", "downtrend"],
             "meaning": "Broken or falling structure. Ranked by Jev sell score = 100 - Jev score (weakest Jev setup first). Sell = exit longs / bearish via F&O."},
    "watch": {"label": "Watch", "tone": "neutral", "categories": ["turning_up", "sideways"],
              "meaning": "No confirmed direction yet. Ranked by Jev score out of 100 (nearest to becoming a buy first); the chart lean is shown."},
}

FACTORS = [
    {"key": "structure", "name": "HH/HL structure", "max": 20, "rule": "HH/HL = 20 bull; LH/LL = 20 bear; mixed or unconfirmed = 0."},
    {"key": "trigger", "name": "Trigger / structure exit", "max": 15,
     "rule": "Breakout today 15 bull; structure exit today 15 bear; still below structure exit 10 bear; HH/HL within 1 ATR under the trigger 8 bull; HH/HL above the trigger 5 bull."},
    {"key": "supertrend", "name": "Supertrend (10,3)", "max": 10, "rule": "Up = 10 bull; down = 10 bear."},
    {"key": "adx", "name": "ADX (14) + DI", "max": 10, "rule": "ADX >= 25: 10 to the side whose DI leads; ADX 20-25: 5; below 20: 0."},
    {"key": "rsi", "name": "RSI (14)", "max": 10, "rule": "(RSI - 50) / 2, capped at 10: RSI 70 = 10 bull, RSI 30 = 10 bear."},
    {"key": "bollinger", "name": "Bollinger %B", "max": 5, "rule": "%B >= 80 = 5 bull; 60-80 = 2 bull; 20-40 = 2 bear; <= 20 = 5 bear."},
    {"key": "obv", "name": "OBV vs 20-day EMA", "max": 10, "rule": "Accumulation = 10 bull; distribution = 10 bear; mixed = 0."},
    {"key": "vwap", "name": "VWAP-20", "max": 5, "rule": "Close above = 5 bull; below = 5 bear."},
    {"key": "ret20", "name": "20-session return", "max": 5, "rule": "Return / 2, capped at 5: +10% = 5 bull, -10% = 5 bear."},
    {"key": "fib", "name": "Fibonacci position (auto anchor)", "max": 5,
     "rule": "Trend leg intact and retraced < 38.2% (or new extreme) = 5 to the leg's side; 38.2-61.8% = 2 to the leg's side; 78.6-100% = 3 against; leg failed > 100% = 5 against."},
    {"key": "volume", "name": "Volume", "max": 5, "rule": "Volume >= 1.5x its 20-session average: 5 to the side of today's candle."},
]
MAX = sum(f["max"] for f in FACTORS)   # 100

JEV_POINTS = [  # weight in points out of 100; each Jev answer is a level 0..JEV_LEVEL_MAX
    {"key": "setup_quality", "name": "Setup quality", "points": 35},
    {"key": "follow_through", "name": "Follow-through odds", "points": 30},
    {"key": "risk_reward", "name": "Risk / reward", "points": 35},
]
JEV_LEVEL_MAX = 4
assert sum(p["points"] for p in JEV_POINTS) == 100


def _pts(side, n):
    return (n, 0) if side == "bull" else (0, n) if side == "bear" else (0, 0)


def chart_factors(s, bars):
    r = s.get("indicators") or {}
    close, atr = s.get("close"), s.get("atr") or 0
    out = []

    def add(key, value, bull, bear):
        out.append({"key": key, "value": value, "bull": round(bull, 1), "bear": round(bear, 1)})

    st = s.get("structure") or "?"
    add("structure", st, *(_pts("bull", 20) if st == "HH / HL" else _pts("bear", 20) if st == "LH / LL" else (0, 0)))

    ev, trig, ex = s.get("events") or [], s.get("trigger"), s.get("structure_exit")
    if "breakout" in ev:
        add("trigger", f"broke out today above {trig}", 15, 0)
    elif "structure_exit" in ev:
        add("trigger", f"closed below structure exit {ex} today", 0, 15)
    elif ex and close is not None and close < ex:
        add("trigger", f"{(ex - close) / atr:.1f} ATR below structure exit {ex}" if atr else f"below structure exit {ex}", 0, 10)
    elif st == "HH / HL" and trig and atr and close is not None:
        d = (trig - close) / atr
        if 0 <= d <= 1:
            add("trigger", f"{d:.2f} ATR under trigger {trig}", 8, 0)
        elif d < 0:
            add("trigger", f"{-d:.1f} ATR above trigger {trig}", 5, 0)
        else:
            add("trigger", f"{d:.1f} ATR under trigger {trig}", 0, 0)
    else:
        add("trigger", f"trigger {trig} / exit {ex}", 0, 0)

    v = r.get("supertrend") or {}
    add("supertrend", f"{v.get('label', '?')} (line {v.get('value')})", *_pts(v.get("state"), 10) if v.get("state") in ("bull", "bear") else (0, 0))

    v = r.get("adx") or {}
    a, p, m = v.get("value") or 0, v.get("plus_di") or 0, v.get("minus_di") or 0
    n = 10 if a >= 25 else 5 if a >= 20 else 0
    add("adx", f"ADX {a:.1f}, +DI {p:.0f} / -DI {m:.0f}", *(_pts("bull" if p > m else "bear", n)))

    v = r.get("rsi") or {}
    rv = v.get("value")
    if rv is not None:
        x = max(-10.0, min(10.0, (rv - 50) / 2))
        add("rsi", f"RSI {rv:.1f}", max(x, 0), max(-x, 0))
    else:
        add("rsi", "n/a", 0, 0)

    v = r.get("bollinger") or {}
    pb = v.get("value")
    if pb is not None:
        b = (5, 0) if pb >= 80 else (2, 0) if pb >= 60 else (0, 5) if pb <= 20 else (0, 2) if pb <= 40 else (0, 0)
        add("bollinger", f"%B {pb:.0f}" + (" (squeeze)" if v.get("squeeze") else ""), *b)
    else:
        add("bollinger", "n/a", 0, 0)

    v = r.get("obv") or {}
    add("obv", v.get("label", "n/a"), *_pts(v.get("state"), 10) if v.get("state") in ("bull", "bear") else (0, 0))

    v = r.get("vwap20") or {}
    vw = v.get("value")
    if vw and close:
        add("vwap", f"{(close / vw - 1) * 100:+.1f}% vs VWAP {vw}", *(_pts("bull" if close > vw else "bear", 5)))
    else:
        add("vwap", "n/a", 0, 0)

    if len(bars) > 20 and bars[-21]["close"]:
        ret = (bars[-1]["close"] / bars[-21]["close"] - 1) * 100
        x = max(-5.0, min(5.0, ret / 2))
        add("ret20", f"{ret:+.1f}%", max(x, 0), max(-x, 0))
    else:
        add("ret20", "n/a", 0, 0)

    f = s.get("fib")
    a = next((x for x in (f or {}).get("anchors", []) if x["method"] == f["auto"]), None) if f else None
    if a:
        rp, side = a["retrace_pct"], ("bull" if a["dir"] == "up" else "bear")
        against = "bear" if side == "bull" else "bull"
        if rp < 38.2:
            b = _pts(side, 5)
        elif rp <= 61.8:
            b = _pts(side, 2)
        elif 78.6 <= rp <= 100:
            b = _pts(against, 3)
        elif rp > 100:
            b = _pts(against, 5)
        else:
            b = (0, 0)
        add("fib", f"{rp:.0f}% of {a['dir']}-leg ({a['method']})", *b)
    else:
        add("fib", "n/a", 0, 0)

    vr = s.get("volume_ratio")
    if vr is not None and len(bars) > 1:
        up = bars[-1]["close"] >= bars[-1]["open"]
        add("volume", f"{vr:.2f}x avg, {'up' if up else 'down'} candle", *(_pts("bull" if up else "bear", 5) if vr >= 1.5 else (0, 0)))
    else:
        add("volume", "n/a", 0, 0)
    return out


def jev_list_score(s, lst):
    """Jev list score as a 0..1 fraction (kept for callers); see jev_breakdown for the /100 maths."""
    c = (s.get("jev") or {}).get("composite")
    if c is None:
        return None
    return 1 - c if lst == "sell" else c


def jev_breakdown(s, lst):
    """Jev score out of 100 with every point traced to one Jev answer. None when Jev has no view."""
    j = s.get("jev") or {}
    if j.get("composite") is None:
        return None
    parts, levels_known = [], all(isinstance(j.get(p["key"]), (int, float)) for p in JEV_POINTS)
    if levels_known:
        for p in JEV_POINTS:
            lv = float(j[p["key"]])
            parts.append({"key": p["key"], "name": p["name"], "level": round(lv, 2), "max_level": JEV_LEVEL_MAX,
                          "weight": p["points"], "points": round(p["points"] * lv / JEV_LEVEL_MAX, 2)})
        score = round(sum(x["points"] for x in parts), 1)
    else:
        score = round(j["composite"] * 100, 1)
    list_score = round(100 - score, 1) if lst == "sell" else score
    return {"score": score, "list_score": list_score, "points": parts, "composite_x100": round(j["composite"] * 100, 2),
            "direction": j.get("direction"), "confidence": j.get("confidence"), "regime": j.get("regime"),
            "overall_rank": j.get("rank"), "of": j.get("of")}


def _ret20(bars):
    return round((bars[-1]["close"] / bars[-21]["close"] - 1) * 100, 2) if len(bars) > 20 and bars[-21]["close"] else 0.0


def rank_all(stocks, bars_by_symbol):
    """Adds s['rank'] to every stock and returns the payload block."""
    cat_to_list = {c: k for k, v in LISTS.items() for c in v["categories"]}
    for s in stocks:
        lst = cat_to_list.get(s.get("category"))
        if not lst or s.get("symbol") not in bars_by_symbol:
            s["rank"] = None
            continue
        fs = chart_factors(s, bars_by_symbol[s["symbol"]])
        bull, bear = sum(f["bull"] for f in fs), sum(f["bear"] for f in fs)
        s["rank"] = {"list": lst, "bull": round(bull, 1), "bear": round(bear, 1), "net": round(bull - bear, 1), "factors": fs,
                     "ret20": _ret20(bars_by_symbol[s["symbol"]]), "jev": jev_breakdown(s, lst)}

    ranked = [s for s in stocks if s.get("rank")]
    # whole-universe ranks (every stock is ranked for both sides)
    for i, s in enumerate(sorted(ranked, key=lambda s: (-s["rank"]["net"], -s["rank"]["ret20"], s["symbol"])), 1):
        s["rank"]["all_buy_rank"] = i
    for i, s in enumerate(sorted(ranked, key=lambda s: (s["rank"]["net"], s["rank"]["ret20"], s["symbol"])), 1):
        s["rank"]["all_sell_rank"] = i

    block = {"factors": FACTORS, "max_points": MAX, "lists": {},
             "jev_method": {"points": JEV_POINTS, "level_max": JEV_LEVEL_MAX,
                            "formula": "Jev score = " + " + ".join(f"{p['points']} x {p['key']}/{JEV_LEVEL_MAX}" for p in JEV_POINTS),
                            "sell": "Jev sell score = 100 - Jev score", "not_scored": "Stocks Jev did not assess follow in chart-score order."}}
    for key, meta in LISTS.items():
        members = [s for s in ranked if s["rank"]["list"] == key]
        # Ties on net score are broken by the 20-session return (stronger for BUY, weaker for SELL), then symbol.
        chart_key = {"buy": lambda s: (-s["rank"]["net"], -s["rank"]["ret20"], s["symbol"]),
                     "sell": lambda s: (s["rank"]["net"], s["rank"]["ret20"], s["symbol"]),
                     "watch": lambda s: (-abs(s["rank"]["net"]), -abs(s["rank"]["ret20"]), s["symbol"])}[key]
        by_chart = sorted(members, key=chart_key)
        for i, s in enumerate(by_chart, 1):
            s["rank"]["chart_rank"] = i
        with_jev = sorted([s for s in members if s["rank"]["jev"]],
                          key=lambda s: (-s["rank"]["jev"]["list_score"], s["rank"]["chart_rank"], s["symbol"]))
        for i, s in enumerate(with_jev, 1):
            s["rank"]["jev_rank"] = i
        without = [s for s in by_chart if not s["rank"]["jev"]]
        final = with_jev + without
        for i, s in enumerate(final, 1):
            s["rank"]["final_rank"] = i
        for s in members:
            s["rank"].setdefault("jev_rank", None)
            j = s["rank"]["jev_rank"]
            s["rank"]["combined_score"] = (s["rank"]["chart_rank"] + j) / 2 if j else float(s["rank"]["chart_rank"]) + 0.5 * len(members)
        by_comb = sorted(members, key=lambda s: (s["rank"]["combined_score"], s["rank"]["chart_rank"]))
        for i, s in enumerate(by_comb, 1):
            s["rank"]["combined_rank"] = i
        n = len(members)
        for s in members:
            rk, net, jb = s["rank"], s["rank"]["net"], s["rank"]["jev"]
            lean = "bullish" if net > 0 else "bearish" if net < 0 else "flat"
            top = sorted(rk["factors"], key=lambda f: -(f["bull"] if (key == "buy" or (key == "watch" and net >= 0)) else f["bear"]))[:3]
            rk["list_size"] = n
            jev_words = (f"#{rk['final_rank']} of {n} in {meta['label'].upper()} by Jev: Jev score {jb['score']:.1f}/100"
                         + (f", sell score 100 - {jb['score']:.1f} = {jb['list_score']:.1f}" if key == "sell" else "")
                         + f" (#{rk['jev_rank']} of {len(with_jev)} Jev-scored in this list; Jev overall #{jb['overall_rank']} of {jb['of']}). "
                         if jb else
                         f"#{rk['final_rank']} of {n} in {meta['label'].upper()}: no Jev score (Jev assesses the Nifty 200 only), "
                         f"so it follows the {len(with_jev)} Jev-scored stocks in chart-score order. ")
            rk["words"] = (jev_words
                           + f"Chart check: #{rk['chart_rank']} by chart, net {net:+.0f} (bull {rk['bull']:.0f} / bear {rk['bear']:.0f} of {MAX})"
                           + (f", leaning {lean}" if key == "watch" else "")
                           + ". Biggest chart contributors: " + "; ".join(f"{_name(f['key'])} {f['value']}" for f in top) + ". "
                           + f"Combined #{rk['combined_rank']}.")
            rk["combined_score"] = round(rk["combined_score"], 1)
        block["lists"][key] = {**{k: v for k, v in meta.items()}, "count": n, "jev_count": len(with_jev),
                               "not_jev_count": len(without),
                               "final_order": [s["symbol"] for s in final],
                               "chart_order": [s["symbol"] for s in by_chart],
                               "jev_order": [s["symbol"] for s in with_jev],
                               "combined_order": [s["symbol"] for s in by_comb]}
    block["accounting"] = accounting(stocks, block["lists"])
    return block


def accounting(stocks, lists):
    """Every stock is counted exactly once: in one list, or as not ranked with its reason."""
    unranked = [{"symbol": s["symbol"], "category": s.get("category"), "universe": s.get("universe"),
                 "data_date": s.get("data_date"), "why": s.get("summary") or s.get("category")}
                for s in stocks if not s.get("rank")]
    jev_scored = sum(v["jev_count"] for v in lists.values())
    by_universe = {}
    for s in stocks:
        u = by_universe.setdefault(s.get("universe") or "?", {"total": 0, "jev_scored": 0, "ranked": 0})
        u["total"] += 1
        u["ranked"] += bool(s.get("rank"))
        u["jev_scored"] += bool(s.get("rank") and s["rank"].get("jev"))
    total = len(stocks)
    ranked = sum(v["count"] for v in lists.values())
    assert ranked + len(unranked) == total
    words = (f"{total} stocks = " + " + ".join(f"{v['count']} {v['label']}" for v in lists.values())
             + f" + {len(unranked)} not ranked" + (" (" + ", ".join(f"{u['symbol']}: {u['category']}, price date {u['data_date']}" for u in unranked) + ")" if unranked else "")
             + f". Jev-scored: {jev_scored} = " + " + ".join(f"{v['jev_count']} {v['label']}" for v in lists.values())
             + ". Without a Jev score: " + ", ".join(f"{k} {u['total'] - u['jev_scored']} of {u['total']}" for k, u in by_universe.items()) + ".")
    return {"total": total, "ranked": ranked, "jev_scored": jev_scored, "unranked": unranked,
            "by_list": {k: {"count": v["count"], "jev_scored": v["jev_count"], "not_jev_scored": v["not_jev_count"]} for k, v in lists.items()},
            "by_universe": by_universe, "words": words}


def _name(key):
    return next(f["name"] for f in FACTORS if f["key"] == key)
