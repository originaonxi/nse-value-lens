#!/usr/bin/env python3
"""Confluence Top-Picks: 7 independent systems vote on every Nifty 200 stock.
Top 10 BUY (most unanimous) and Top 10 SELL. Exports full OHLC + signal detail
for proper candlestick chart rendering on confluence.html.

Systems:
  1. HHHL price structure  (HH/HL = bullish, LH/LL = bearish)
  2. Daily setups category (uptrend/turning_up = bull; downtrend = bear)
  3. 5-indicator count      (≥4 bull = bull, ≥4 bear = bear)
  4. Jev direction          (up = bull, down = bear)
  5. DMA crossover type     (platinum/golden/silver/watch = bull; bear/death = bear)
  6. Fund screen            (above 200-DMA AND supertrend up = bull)
  7. F&O 20-signal          (buy_strong / buy = bull; sell_strong / sell = bear)
"""
import json, math, pathlib, time
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent
PRICES = ROOT / "data" / "hhhl_prices"
DOCS   = ROOT / "docs"
PUBLIC = ROOT / "public" / "data"

BULL_CAT = {"uptrend", "turning_up", "ready_to_break", "breakout_today"}
BEAR_CAT  = {"downtrend", "exit_today", "below_structure"}

# ── load published JSONs ─────────────────────────────────────────────────────

def load_all():
    J = lambda f: json.loads((DOCS / f).read_text(encoding="utf-8"))
    fund  = J("fund.json")
    dma   = J("dma.json")
    fno   = J("fno-play.json")
    jev   = J("jev_rank.json")
    hh    = J("hhhl_scan.json")
    st    = J("daily_setups.json")
    div   = J("dividends.json")
    return fund, dma, fno, jev, hh, st, div

def index_all(fund, dma, fno, jev, hh, st, div):
    return {
        "hh":  {r["symbol"]: r for r in hh["rows"]},
        "st":  {s["symbol"]: s for s in st["stocks"]},
        "jv":  {r["symbol"]: r for r in jev["ranking"]},
        "dm":  {r["symbol"]: r for r in dma["rows"]},
        "fd":  {r["symbol"]: r for r in fund["all100"]},
        "fn":  {r["symbol"]: r for r in fno["rows"]},
        "dv":  {r["symbol"]: r for r in div["rows"]},
    }

# ── 7-system score ─────────────────────────────────────────────────────────

def score_symbol(sym, idx):
    h, s, j, d, f, n, dv = (idx["hh"].get(sym), idx["st"].get(sym), idx["jv"].get(sym),
                              idx["dm"].get(sym), idx["fd"].get(sym), idx["fn"].get(sym),
                              idx["dv"].get(sym))
    votes = {}

    if h:
        struct = h.get("structure", "")
        votes["HHHL"] = (1 if struct == "HH / HL" else -1 if struct == "LH / LL" else 0,
                         struct, h.get("status"), h.get("close"))

    if s and s.get("category") not in (None, "data_check"):
        cat = s.get("category", "")
        ic  = s.get("indicator_counts") or {}
        conv = s.get("conviction", 0)
        votes["Setups"] = (1 if cat in BULL_CAT else -1 if cat in BEAR_CAT else 0,
                           cat, conv, ic.get("bull", 0), ic.get("bear", 0))
        if ic:
            bull_i, bear_i = ic.get("bull", 0), ic.get("bear", 0)
            votes["5-Indicators"] = (1 if bull_i >= 4 else -1 if bear_i >= 4 else 0,
                                     bull_i, bear_i)

    if j:
        comp = j.get("composite")
        votes["Jev"] = (1 if j["direction_jev"] == "up" else -1 if j["direction_jev"] == "down" else 0,
                        round(comp * 100) if comp else None, j.get("direction_jev"), j.get("signal"))

    if d:
        ct = d.get("crossover_type", "")
        votes["DMA"] = (1 if ct in ("platinum","golden","silver","watch") else -1 if ct in ("bear","death") else 0,
                        ct, d.get("total_score"), d.get("bt_win_rate_3m"), d.get("bt_win_rate_6m"))

    if f:
        a200, st_ = f.get("above_200dma", False), f.get("supertrend_up", False)
        in_f = f.get("in_fund", False)
        votes["Fund"] = (1 if (a200 and st_) else -1 if (not a200 and not st_) else 0,
                         a200, st_, in_f, f.get("jev_score"))

    if n:
        sig = n.get("signal", "")
        is_buy  = "buy"  in sig and "watch" not in sig
        is_sell = "sell" in sig and "watch" not in sig
        votes["F&O"] = (1 if is_buy else -1 if is_sell else 0,
                        sig, n.get("twenty_score"), n.get("zone_buy_wr"), n.get("zone_sell_wr"), n.get("rsi"))

    net   = sum(v[0] for v in votes.values())
    n_sys = len(votes)
    return net, n_sys, votes, h, s, j, d, f, n, dv

# ── OHLC history for chart ───────────────────────────────────────────────────

def ohlc_history(sym, n=150):
    for suf in (".NS.csv", ".csv"):
        p = PRICES / f"{sym}{suf}"
        if p.exists():
            try:
                df = pd.read_csv(p, index_col=0, parse_dates=True).sort_index()
                df.columns = [c.strip() for c in df.columns]
                df = df[df.index.dayofweek < 5].iloc[-n:]
                idx = df.index
                def col(name, default=None):
                    if name in df.columns:
                        v = df[name]
                        return [round(float(x), 2) if not (isinstance(x, float) and math.isnan(x)) else default for x in v]
                    return [default] * len(idx)
                closes = col("Close") or col("Adj Close")
                if not closes:
                    return None
                cs = pd.Series(closes, dtype=float)
                d20  = cs.rolling(20).mean().tolist()
                d50  = cs.rolling(50).mean().tolist()
                d100 = cs.rolling(100).mean().tolist()
                d200 = cs.rolling(200).mean().tolist()
                def rnd(lst):
                    return [round(x, 2) if x is not None and not (isinstance(x, float) and math.isnan(x)) else None for x in lst]
                return {
                    "dates":  [str(d.date()) for d in idx],
                    "opens":  col("Open", closes[i] if i < len(closes) else None),
                    "highs":  col("High", closes[i] if i < len(closes) else None),
                    "lows":   col("Low",  closes[i] if i < len(closes) else None),
                    "closes": closes,
                    "dma20":  rnd(d20),
                    "dma50":  rnd(d50),
                    "dma100": rnd(d100),
                    "dma200": rnd(d200),
                }
            except Exception:
                pass
    return None

# ── build payload ─────────────────────────────────────────────────────────────

def build():
    fund, dma, fno, jev, hh, st, div = load_all()
    idx = index_all(fund, dma, fno, jev, hh, st, div)
    as_of = hh["as_of"]
    print(f"Scoring all Nifty 200 stocks as of {as_of}…")

    all_syms = set(idx["hh"]) | set(idx["st"]) | set(idx["jv"])
    scored = []
    for sym in all_syms:
        net, n_sys, votes, h, s, j, d, f, n, dv = score_symbol(sym, idx)
        if n_sys < 5:
            continue
        scored.append((sym, net, n_sys, votes, h, s, j, d, f, n, dv))

    bull = sorted([x for x in scored if x[1] > 0], key=lambda x: (-x[1]/x[2], -x[2], -(x[3].get("Jev") or [0])[1] if x[3].get("Jev") and x[3]["Jev"][1] else 0))
    bear = sorted([x for x in scored if x[1] < 0], key=lambda x: (x[1]/x[2], -x[2]))
    picks_bull = bull[:10]
    picks_bear = bear[:10]
    print(f"  BUY unanimous: {sum(1 for x in scored if x[1]==x[2])} | picks: {[x[0] for x in picks_bull[:5]]}")
    print(f"  SELL unanimous: {sum(1 for x in scored if x[1]==-x[2])} | picks: {[x[0] for x in picks_bear[:5]]}")

    def detail(sym, net, n_sys, votes, h, s, j, d, f, n, dv):
        name = (h or s or j or d or f or n or {}).get("name") or sym
        close = (h or s or f or {}).get("close")
        print(f"  {sym}: loading history…")
        hist = ohlc_history(sym)

        # key levels for chart annotation
        levels = []
        if d and d.get("dma200"): levels.append({"price": d["dma200"], "label": "200-DMA", "color": "#EF4444"})
        if d and d.get("dma50"):  levels.append({"price": d["dma50"],  "label": "50-DMA",  "color": "#F59E0B"})
        if d and d.get("buy_zones"):
            for z in (d["buy_zones"] or [])[:2]:
                levels.append({"price": z["price"], "label": "BUY " + " + ".join(z["levels"][:2]), "color": "#16a34a"})
        if d and d.get("sell_zones"):
            for z in (d["sell_zones"] or [])[:1]:
                levels.append({"price": z["price"], "label": "SELL " + " + ".join(z["levels"][:2]), "color": "#dc2626"})
        if h:
            zb = h.get("zones", {})
            if zb.get("breakout_above"): levels.append({"price": zb["breakout_above"], "label": "Breakout", "color": "#7c3aed"})
            if zb.get("structure_exit_below"): levels.append({"price": zb["structure_exit_below"], "label": "Exit", "color": "#dc2626"})

        # signal detail for dashboard
        signals = []
        for system, val in votes.items():
            v = val[0]
            if system == "HHHL":
                signals.append({"system": "HH/HL Structure", "vote": v, "detail": f"{val[1]} · {val[2] or '—'}"})
            elif system == "Setups":
                signals.append({"system": "Setups Category", "vote": v, "detail": f"{val[1]} · conviction {val[2]}"})
            elif system == "5-Indicators":
                signals.append({"system": "5 Indicators", "vote": v, "detail": f"Bull {val[1]} / Bear {val[2]} / Neutral {5-val[1]-val[2]}"})
            elif system == "Jev":
                signals.append({"system": "Jev AI Score", "vote": v, "detail": f"{val[1]}/100 · {val[2]} · {val[3]}"})
            elif system == "DMA":
                signals.append({"system": "DMA Crossover", "vote": v, "detail": f"{val[1]} · score {val[2]} · BT 3M {val[3]}%"})
            elif system == "Fund":
                signals.append({"system": "Fund 200+SuperT", "vote": v, "detail": f"200DMA {'above' if val[1] else 'below'} · ST {'up' if val[2] else 'down'} · in fund {val[3]} · Jev {val[4]}"})
            elif system == "F&O":
                wr = val[3] if v > 0 else val[4]
                signals.append({"system": "F&O 20-signal", "vote": v, "detail": f"{val[1]} · {val[2]}/20 · zone {wr}% win · RSI {val[5]}"})

        div_yield = dv.get("current_yield", 0) if dv else 0
        adr = (h or {}).get("atr") or (d or {}).get("vol_pct")

        return {
            "symbol": sym, "name": name,
            "side": "buy" if net > 0 else "sell",
            "net": net, "n_sys": n_sys,
            "agree_pct": round(abs(net) / n_sys * 100),
            "close": close,
            "adr": round(adr, 2) if adr else None,
            "div_yield": round(div_yield, 2),
            "signals": signals,
            "levels": levels,
            "history": hist,
            "action": {
                "entry": round(float(close), 2) if close else None,
                "stop":  round(float(d["dma200"]) if d and d.get("dma200") else float(close)*0.97 if close else 0, 2),
                "why":   _why(net, votes, h, s, j, d),
            },
        }

    def _why(net, votes, h, s, j, d):
        parts = []
        if (votes.get("HHHL") or (0,))[0] > 0: parts.append("price making HH/HL")
        if (votes.get("Setups") or (0,))[0] > 0: parts.append(f"{(votes['Setups'])[1]}")
        if (votes.get("Jev") or (0,))[0] > 0: parts.append(f"Jev {(votes['Jev'])[1]}/100 up")
        if (votes.get("DMA") or (0,))[0] > 0: parts.append(f"DMA {(votes['DMA'])[1]}")
        if (votes.get("HHHL") or (0,))[0] < 0: parts.append("price making LH/LL")
        if (votes.get("Setups") or (0,))[0] < 0: parts.append(f"{(votes.get('Setups') or ('','',''))[1]}")
        if (votes.get("Jev") or (0,))[0] < 0: parts.append(f"Jev {(votes.get('Jev') or (0,0))[1]}/100 down")
        if (votes.get("DMA") or (0,))[0] < 0: parts.append(f"DMA {(votes.get('DMA') or (0,''))[1]}")
        return "; ".join(parts[:4]) or "multi-system agreement"

    print("Building detail for top 20…")
    stocks = [detail(*x) for x in picks_bull + picks_bear]

    payload = {
        "version": 1,
        "name": "Confluence Top Picks",
        "as_of": as_of,
        "generated_at": datetime.now().isoformat(),
        "scored": len(scored),
        "systems": 7,
        "unanimous_bull": sum(1 for x in scored if x[1] == x[2]),
        "unanimous_bear": sum(1 for x in scored if x[1] == -x[2]),
        "stocks": stocks,
        "method_note": "No stock is 100% certain. These stocks are where multiple independent technical systems agree. Always use a stop loss.",
        "systems_list": [
            "HH/HL price structure (HHHL page)",
            "Daily setups category (Setups page)",
            "5-indicator count (Setups indicators)",
            "Jev AI score and direction (Jev model)",
            "DMA crossover type (DMA Intelligence Desk)",
            "Fund screen: above 200-DMA and Supertrend up (Our Fund)",
            "F&O 20-signal composite (₹1 Play Desk)",
        ],
    }

    text = json.dumps(payload, separators=(",", ":"), default=str)
    DOCS.mkdir(exist_ok=True); PUBLIC.mkdir(parents=True, exist_ok=True)
    (DOCS / "confluence.json").write_text(text, encoding="utf-8")
    (PUBLIC / "confluence.json").write_text(text, encoding="utf-8")
    print(f"confluence.json: {len(stocks)} stocks, {round(len(text)/1024)}KB | bull {sum(1 for s in stocks if s['side']=='buy')} | bear {sum(1 for s in stocks if s['side']=='sell')}")
    return payload


if __name__ == "__main__":
    build()
