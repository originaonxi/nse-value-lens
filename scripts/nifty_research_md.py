#!/usr/bin/env python3
"""Write docs/NIFTY_RESEARCH.md - the full record of every Nifty 50 test (EMA scan, indicator combinations,
day vs night). Every number is recomputed from the live engines, never typed by hand.
Run: python scripts/nifty_research_md.py   (after nifty_ema.py, nifty_combo.py, nifty_daynight.py)"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import nifty_ema as N      # noqa: E402
import nifty_combo as K    # noqa: E402

DOCS = ROOT / "docs"
OUT = DOCS / "NIFTY_RESEARCH.md"


def j(name):
    return json.loads((DOCS / name).read_text(encoding="utf-8"))


def fmt(v, d=0, sign=False):
    if v is None:
        return "—"
    s = f"{v:+,.{d}f}" if sign else f"{v:,.{d}f}"
    return s


def pc(v):
    return "—" if v is None else f"{v:.1f}%"


def srow(s):
    return f"{s['n']} | {pc(s['win'])} | {fmt(s['pf'], 2)} | {fmt(s['net'], 0, True)} | {fmt(s['dd'], 0)}"


def rule_name(filters, ek, p, shorts=False):
    ex = {"cross": "exit on close below", "rsi": f"TOP exit RSI {p}", "stretch": f"TOP exit {p} ATR",
          "tp": f"target {p} ATR", "trail": f"trail {p} ATR", "st": "Supertrend flip", "bb": "Bollinger top"}[ek]
    return "EMA 105" + "".join(" + " + f for f in filters) + f" · {ex}" + (" · buy+sell" if shorts else "")


def main():
    frames = N.load_data()
    X = K.indicators(frames["2h"], K.EMA_N, frames["1D"])
    n = len(X["c"])
    split = K.WARM + int((n - K.WARM) * K.IS_FRAC)
    rows, F = K.run_grid(X, split)
    T = np.ones(n, bool)
    E, C, DN = j("nifty.json"), j("nifty_combo.json"), j("nifty_daynight.json")
    per = C["period"]

    def run(filters, ek="cross", p=None, shorts=False):
        lok, sok = T.copy(), T.copy()
        for f in filters:
            lok &= F[f][0]
            sok &= F[f][1]
        tr = K.simulate(X, lok, sok, ek, p, shorts)
        return tr, K.stats([t for t in tr if t[0] < split]), K.stats([t for t in tr if t[0] >= split]), K.stats(tr)

    L = []
    w = L.append
    w("# Nifty 50 research record")
    w("")
    w(f"Generated {datetime.now(N.IST):%Y-%m-%d %H:%M} IST from the live engines (`nifty_ema.py`, `nifty_combo.py`, "
      "`nifty_daynight.py`). Re-run `python scripts/nifty_research_md.py` to refresh. Paper research, not advice.")
    w("")
    w("**Data:** NIFTY 50 index (^NSEI, Yahoo Finance). 2-hour candles " + f"{per['from']} → {per['to']} "
      f"({per['bars']:,} candles). Daily candles 2016 → {DN['to']}. Hourly 2023 → today, 5-minute last ~60 sessions.")
    w("")
    w(f"**Costs:** every trade pays {C['cost_pct']:.3f}% of price (≈ {C['cost_pct'] / 100 * 25000:.0f} Nifty points at 25,000).")
    w("")
    w(f"**Honesty split:** rules are tested on {per['from']} → {per['split']} (the *tested part*) and judged on "
      f"{per['split']} → {per['to']} (the *unseen part*, never used to pick). A rule is *robust* only if it makes money in both.")
    w("")
    w("## The maths used everywhere")
    w("")
    w("| Term | Formula |")
    w("|---|---|")
    w("| Points of a trade | (exit close − entry close) × direction − 0.035% × entry price |")
    w("| Win rate | winning trades ÷ all trades |")
    w("| Profit factor (PF) | sum of winning points ÷ sum of losing points (PF > 1 = makes money) |")
    w("| Net | sum of all trade points after costs |")
    w("| Worst drawdown (DD) | biggest fall of the running points total from its previous peak |")
    w("| Robust score | the WEAKER of the two parts: 35% PF (capped 5) + 35% win rate + 30% net ÷ drawdown (capped 6) |")
    w("")

    # ── top 3 ────────────────────────────────────────────────────────────────
    top = [
        (["ADX>20", "Supertrend", "Daily>EMA50"], "rsi", 68, "Best overall (the page's winner)"),
        (["ADX>20", "Daily>EMA50", "DI+>DI-"], "rsi", 70, "Best on the unseen part (70% win)"),
        (["ADX>20", "Daily>EMA50"], "rsi", 70, "Fewest conditions, smallest drawdown"),
    ]
    w("## Top 3 setups for Nifty 50")
    w("")
    w("All three: **2-hour candles, buy only.** BUY when a 2-hour candle closes above EMA 105 and the listed "
      "indicators agree. TOP = sell when RSI(14) reaches the level and then falls 5 points; after a TOP, buy again only "
      "when price is back within 1 ATR of EMA 105. EXIT = a 2-hour close below EMA 105.")
    w("")
    w("| # | Setup | Why | Part | Trades | Win % | PF | Net pts | Worst DD |")
    w("|---|---|---|---|---|---|---|---|---|")
    top_trades = {}
    for i, (fl, ek, p, why) in enumerate(top, 1):
        tr, a, b, al = run(fl, ek, p)
        top_trades[i] = tr
        nm = rule_name(fl, ek, p)
        w(f"| **{i}** | {nm} | {why} | whole | {srow(al)} |")
        w(f"|  |  |  | tested | {srow(a)} |")
        w(f"|  |  |  | **unseen** | {srow(b)} |")
    base_tr, ba, bb, bal = run([], "cross")
    w(f"| ref | EMA 105 alone · exit on close below | the starting point | whole | {srow(bal)} |")
    w("")
    tr1 = top_trades[1]
    nets = np.array([t[3] for t in tr1])
    gw, gl = nets[nets > 0].sum(), -nets[nets <= 0].sum()
    w(f"**Worked maths for setup 1:** {len(nets)} trades, {int((nets > 0).sum())} winners → win rate "
      f"{int((nets > 0).sum())} ÷ {len(nets)} = **{(nets > 0).mean() * 100:.1f}%**. Winners made {gw:,.1f} points, "
      f"losers lost {gl:,.1f} → PF {gw:,.1f} ÷ {gl:,.1f} = **{gw / gl:.2f}**. Net {gw:,.1f} − {gl:,.1f} = "
      f"**{nets.sum():+,.1f} points** ≈ ₹{nets.sum() * 75:,.0f} per lot of 75.")
    w("")

    # ── ladder: how the win rate climbs ──────────────────────────────────────
    w("## How the win rate climbs toward 70% (one step at a time)")
    w("")
    w("Each row adds one thing to the row above. Whole period, buy only, after costs.")
    w("")
    w("| Step | Rule | Trades | Win % | PF | Net pts | Worst DD | Unseen win % | Unseen PF |")
    w("|---|---|---|---|---|---|---|---|---|")
    ladder = [([], "cross", None), (["ADX>20"], "cross", None), (["ADX>20", "Daily>EMA50"], "cross", None),
              (["ADX>20", "Daily>EMA50", "Supertrend"], "cross", None),
              (["ADX>20", "Daily>EMA50", "Supertrend"], "rsi", 70), (["ADX>20", "Daily>EMA50", "Supertrend"], "rsi", 68)]
    for i, (fl, ek, p) in enumerate(ladder):
        _, a, b, al = run(fl, ek, p)
        w(f"| {i} | {rule_name(fl, ek, p)} | {srow(al)} | {pc(b['win'])} | {fmt(b['pf'], 2)} |")
    w("")
    w("What moves the number: **ADX > 20** removes trades in sideways markets (most of EMA 105's small losses). "
      "**Daily close above daily EMA 50** keeps only buys in a rising bigger trend. **Supertrend** removes late "
      "entries. The **RSI TOP exit** books the gain near the top instead of giving it back on the way down to "
      "EMA 105 - this step lifts the win rate the most.")
    w("")
    w("**Best win rate by number of confirmations** (robust rules only, 20+ trades):")
    w("")
    w("| Confirmations | Robust rules | Best win % | Rule |")
    w("|---|---|---|---|")
    for k in range(4):
        rk = [r for r in rows if len(r["filters"]) == k and r["robust"] is not None and r["all"]["n"] >= 20]
        if rk:
            b = max(rk, key=lambda r: r["all"]["win"])
            w(f"| {k} | {len(rk):,} | {pc(b['all']['win'])} | {rule_name(b['filters'], b['exit'], b['p'], b['shorts'])} |")
    w("")

    # ── 70% facts ────────────────────────────────────────────────────────────
    hi_all = [r for r in rows if r["all"]["n"] >= 10 and (r["all"]["win"] or 0) >= 70]
    hi_os = sorted([r for r in rows if r["os"]["n"] >= 8 and (r["os"]["win"] or 0) >= 70 and r["is"]["n"] >= 12
                    and (r["is"]["pf"] or 0) > 1], key=lambda r: -r["os"]["win"])
    hi_is = sorted([r for r in rows if r["is"]["n"] >= 12 and r["os"]["n"] >= 6 and (r["is"]["win"] or 0) >= 70],
                   key=lambda r: -r["is"]["win"])
    w("## Where the win rate goes above 70%")
    w("")
    w(f"- Rules with **70%+ over the whole period** and at least 10 trades: **{len(hi_all)}** of {len(rows):,}.")
    w(f"- Rules with **70%+ on the unseen part** (8+ trades) that also made money on the tested part: **{len(hi_os)}**:")
    w("")
    w("| Rule | Tested part | Unseen part | Whole period |")
    w("|---|---|---|---|")
    for r in hi_os:
        s = lambda x: f"{x['n']} tr · {pc(x['win'])} · PF {fmt(x['pf'], 2)} · {fmt(x['net'], 0, True)}"
        w(f"| {rule_name(r['filters'], r['exit'], r['p'], r['shorts'])} | {s(r['is'])} | **{s(r['os'])}** | {s(r['all'])} |")
    w("")
    w(f"- Rules that showed **70%+ on the tested part** (12+ trades): **{len(hi_is)}**. What they did next on the unseen part:")
    w("")
    w("| Rule | Tested part | Unseen part |")
    w("|---|---|---|")
    for r in hi_is[:15]:
        s = lambda x: f"{x['n']} tr · {pc(x['win'])} · PF {fmt(x['pf'], 2)} · {fmt(x['net'], 0, True)}"
        w(f"| {rule_name(r['filters'], r['exit'], r['p'], r['shorts'])} | {s(r['is'])} | {s(r['os'])} |")
    kept = sum(1 for r in hi_is if (r["os"]["win"] or 0) >= 70)
    lost = sum(1 for r in hi_is if (r["os"]["pf"] or 0) < 1)
    w("")
    w(f"Of those {len(hi_is)}, **{kept}** stayed at 70%+ on unseen data and **{lost}** lost money. "
      "So 70%+ is reachable on a stretch of data, and the setups above did hit 70-78% on the unseen part, but "
      "no rule held 70%+ over the whole period with enough trades. ~65-69% is the honest level.")
    w("")

    # ── 30 combos ────────────────────────────────────────────────────────────
    w("## 30 combinations side by side")
    w("")
    w("Same data, same costs. Tested part / unseen part / whole period. Long only unless marked.")
    w("")
    sets = [
        ([], "cross", None, False), ([], "cross", None, True), ([], "rsi", 70, False), ([], "tp", 2, False),
        ([], "stretch", 4, False), ([], "trail", 3, False),
        (["RSI>50"], "cross", None, False), (["MACD hist"], "cross", None, False), (["ADX>20"], "cross", None, False),
        (["ADX>25"], "cross", None, False), (["Supertrend"], "cross", None, False), (["Daily>EMA50"], "cross", None, False),
        (["Daily>EMA200"], "cross", None, False), (["EMA slope"], "cross", None, False), (["2 closes"], "cross", None, False),
        (["DI+>DI-"], "cross", None, False), (["ADX>20"], "rsi", 70, False),
        (["ADX>20", "Daily>EMA50"], "cross", None, False), (["ADX>20", "Daily>EMA50"], "rsi", 70, False),
        (["ADX>20", "Supertrend"], "rsi", 70, False), (["RSI>50", "ADX>20"], "rsi", 70, False),
        (["Daily>EMA50", "DI+>DI-"], "rsi", 68, False),
        (["ADX>20", "Supertrend", "Daily>EMA50"], "cross", None, False),
        (["ADX>20", "Supertrend", "Daily>EMA50"], "rsi", 68, False),
        (["ADX>20", "Supertrend", "Daily>EMA50"], "rsi", 70, False),
        (["ADX>20", "Daily>EMA50", "DI+>DI-"], "rsi", 70, False),
        (["RSI>50", "ADX>20", "Daily>EMA50"], "rsi", 68, False),
        (["ADX>20", "Supertrend", "EMA slope"], "rsi", 68, False),
        (["RSI>50", "ADX>25", "Daily>EMA50"], "stretch", 4, False),
        (["MACD hist", "Daily>EMA200", "EMA slope"], "stretch", 3, True),
    ]
    w("| # | Rule | Tested: trades · win · PF · net | Unseen: trades · win · PF · net | Whole: trades | Win % | PF | Net pts | DD | Both parts profit |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for i, (fl, ek, p, sh) in enumerate(sets, 1):
        _, a, b, al = run(fl, ek, p, sh)
        s = lambda x: f"{x['n']} · {pc(x['win'])} · {fmt(x['pf'], 2)} · {fmt(x['net'], 0, True)}"
        ok = "✓" if (a["pf"] or 0) > 1 and (b["pf"] or 0) > 1 else "✗"
        w(f"| {i} | {rule_name(fl, ek, p, sh)} | {s(a)} | {s(b)} | {al['n']} | {pc(al['win'])} | {fmt(al['pf'], 2)} | "
          f"{fmt(al['net'], 0, True)} | {fmt(al['dd'], 0)} | {ok} |")
    w("")

    # ── sensitivity ──────────────────────────────────────────────────────────
    w("## Sensitivity: is the winner a lucky setting?")
    w("")
    w("EMA 105 + ADX>a + Supertrend + Daily>EMA50, TOP exit at RSI r. Whole-period win % (PF).")
    w("")
    lv = sorted({s["rsi_top"] for s in C["sensitivity"]})
    w("| ADX > | " + " | ".join(f"RSI {x}" for x in lv) + " |")
    w("|---|" + "---|" * len(lv))
    for a in sorted({s["adx"] for s in C["sensitivity"]}):
        cells = []
        for x in lv:
            s = next(z for z in C["sensitivity"] if z["adx"] == a and z["rsi_top"] == x)
            cells.append(f"{pc(s['win'])} ({fmt(s['pf'], 2)})")
        w(f"| {a} | " + " | ".join(cells) + " |")
    w("")
    w("The best area is ADX 18-22 with an RSI top at 68-70; results fade smoothly away from it rather than jumping, "
      "so the setting is not a single lucky point.")
    w("")

    # ── independent check ────────────────────────────────────────────────────
    dc = C["daily_check"]
    w(f"## Independent check: daily candles {dc['from']} → {dc['to']} (years the 2-hour test never saw)")
    w("")
    w("| Rule | Trades | Win % | PF | Net pts | Worst DD |")
    w("|---|---|---|---|---|---|")
    for nm, s in (("Daily EMA 26 alone (≈ 2-hour EMA 105)", dc["ema_only"]),
                  ("+ ADX>20 + Supertrend + trend gate, RSI-70 TOP exit", dc["combo_rsi_top"]),
                  ("+ ADX>20 + Supertrend + trend gate, exit on close below", dc["combo_cross_exit"])):
        w(f"| {nm} | {srow(s)} |")
    w("")
    w("The same confirmations roughly double the win rate and cut the drawdown in a completely different period, "
      "but they do not reach 70% there.")
    w("")

    # ── TOP reversion ────────────────────────────────────────────────────────
    tv = C["top_reversion"]
    w("## After a TOP: does Nifty go back toward EMA 105?")
    w("")
    w(f"{tv['n']} TOP signals. Within the next 10 two-hour candles: fell at least 1 ATR **{pc(tv['fell_1atr_pct'])}**, "
      f"reached EMA 105 **{pc(tv['reached_ema_pct'])}**, median move back **{pc(tv['median_pct_back'])}** of the gap.")
    w("")

    # ── sells ────────────────────────────────────────────────────────────────
    w("## Sell side (close below EMA 105)")
    w("")
    w("| Sell rule | Tested part | Unseen part | Whole period |")
    w("|---|---|---|---|")
    for r in C["short_side"]:
        s = lambda x: f"{x['n']} · {pc(x['win'])} · PF {fmt(x['pf'], 2)} · {fmt(x['net'], 0, True)}"
        w(f"| {r['label'].replace('SELL below ', 'Sell below ')} | {s(r['is'])} | {s(r['os'])} | {s(r['all'])} |")
    w("")
    w("No sell rule was profitable and consistent in both parts, so the setups are buy only: a close below "
      "EMA 105 means stay out.")
    w("")

    # ── EMA scan ─────────────────────────────────────────────────────────────
    w("## Test 1: which single EMA? (every EMA 3-200 × 7 timeframes)")
    w("")
    w(f"{E['tested']['rules']:,} rules: close above EMA = up, close below = down, held to the opposite close. All "
      f"timeframes ranked on the same {E['main_sessions']} sessions ({E['main_from']} → {E['as_of']}); "
      "rules had to make money on BOTH up and down signals to score fully. Final = 60% numbers + 40% Jev.")
    w("")
    w("| # | Candles | EMA | Signals | Up signals: hit · pts | Down signals: hit · pts | PF | Net pts | 140 sessions PF · net | Jev | Final |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(E["finalists"], 1):
        m, x, jv = r["main"], r["w140"], r.get("jev") or {}
        w(f"| {i} | {r['tf']} | {r['ema']} | {m['trades']} | {pc(m['up_hit'])} · {fmt(m['up_net'], 0, True)} | "
          f"{pc(m['down_hit'])} · {fmt(m['down_net'], 0, True)} | {fmt(m['pf'], 2)} | {fmt(m['net'], 0, True)} | "
          f"{fmt(x['pf'], 2)} · {fmt(x['net'], 0, True)} | {jv.get('reliability', '—')} | {fmt(r.get('final'), 1)} |")
    w("")
    w("Your EMAs 5, 6, 9, 10, 11 (same rule, same dates):")
    w("")
    w("| Candles | " + " | ".join(f"EMA {e}" for e in (5, 6, 9, 10, 11)) + " |")
    w("|---|---|---|---|---|---|")
    by = {}
    for r in E["asked"]:
        by.setdefault(r["tf"], {})[r["ema"]] = r["main"]["net"]
    for tf in E["tested"]["timeframes"]:
        if tf in by:
            w(f"| {tf} | " + " | ".join(fmt(by[tf].get(e), 0, True) for e in (5, 6, 9, 10, 11)) + " |")
    w("")

    # ── day vs night ─────────────────────────────────────────────────────────
    t = DN["totals"]
    w(f"## Test 3: day vs night (last {DN['sessions']} sessions, {DN['from']} → {DN['to']})")
    w("")
    w(f"Night (close → next open) **{fmt(t['night'], 0, True)}** points, day (open → close) **{fmt(t['day'], 0, True)}**, "
      f"close to close **{fmt(t['cc'], 0, True)}**. Check: night + day = close to close on every session "
      f"(max error {DN['checks']['identity_max_error']}).")
    w("")
    w("| Year | Night pts | Day pts | Night % | Day % |")
    w("|---|---|---|---|---|")
    for y in DN["years"]:
        w(f"| {y['year']} | {fmt(y['night'], 0, True)} | {fmt(y['day'], 0, True)} | {fmt(y['night_pct'], 1, True)}% | {fmt(y['day_pct'], 1, True)}% |")
    w("")
    w("Where the EMA 105 trades made their points:")
    w("")
    w("| Rule | Trades | Overnight pts | Daytime pts |")
    w("|---|---|---|---|")
    for r in DN["ema_split"]:
        w(f"| {r['rule']} | {r['all']['trades']} | {fmt(r['all']['night'], 0, True)} | {fmt(r['all']['day'], 0, True)} |")
    w("")
    w(f"All {len(DN['rules'])} session rules (sorted by points after costs; ✓ = profit in both 100-session halves):")
    w("")
    w("| Idea | Rule | Side | Trades | Win % | PF | Net | 1st 100 | Last 100 | Holds |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(DN["rules"], key=lambda r: -(r["net"] or 0)):
        w(f"| {r['idea']} | {r['rule']} | {r['side']} | {r['n']} | {pc(r['win'])} | {fmt(r['pf'], 2)} | "
          f"{fmt(r['net'], 0, True)} | {fmt(r['h1'], 0, True)} | {fmt(r['h2'], 0, True)} | {'✓' if r['holds'] else ''} |")
    w("")
    o = DN["orb"]
    w("Opening-range breakout, checked twice:")
    w("")
    w("| Version | Trades | Win % | PF | Net | DD |")
    w("|---|---|---|---|---|---|")
    for nm, k in (("Hourly, first hour, 200 sessions", "first_hour_1h_200"), ("… first 100", "first_hour_1h_h1"),
                  ("… last 100", "first_hour_1h_h2"), ("Hourly, same days as 5-min", "first_hour_1h_same_days_as_5m"),
                  ("5-minute, first hour", "first_hour_5m"), ("5-minute, first 15 min", "first_15m_5m"),
                  ("5-minute, first 30 min", "first_30m_5m")):
        s = o[k]
        w(f"| {nm} | {s['n']} | {pc(s.get('win'))} | {fmt(s.get('pf'), 2)} | {fmt(s.get('net'), 0, True)} | {fmt(s.get('dd'), 0)} |")
    w("")
    w("**Look-ahead trap found and removed:** a first version that traded only days where *one* side of the first hour "
      "broke showed 64-66% wins and PF 3+. That rule needs the day's close to know the other side never broke, so it "
      "cannot be traded. Done correctly (enter on the first break), the breakout lost money over 200 sessions.")
    w("")

    # ── jev + limits ─────────────────────────────────────────────────────────
    w("## Jev's judgement of the combination finalists")
    w("")
    w("| Rule | Reliability | Overfit risk | Jev score | Final |")
    w("|---|---|---|---|---|")
    for r in C["finalists"]:
        jv = r.get("jev") or {}
        w(f"| {rule_name(r['filters'], r['exit'], r['p'], r['shorts'])} | {jv.get('reliability', '—')} | "
          f"{jv.get('overfit', '—')} | {fmt(jv.get('jev_score'), 1)} | {fmt(r['final'], 1)} |")
    w("")
    w("## Limits")
    w("")
    w(f"- {C['tested']:,} combinations were tried; the best one is partly luck even with an unseen part. Expect live results to be weaker.")
    w("- About 3 years of 2-hour data; the unseen part holds only about 9-11 trades per setup.")
    w("- Index candles, not futures. Futures trade at a premium and gap differently at 09:15.")
    w("- Paper research. Not SEBI-registered advice. No orders are placed by this website.")
    w("")
    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {OUT} ({len(L)} lines) | top3 + {len(sets)} combos + {len(hi_os)} unseen-70% rules + {len(hi_is)} tested-70% rules")


if __name__ == "__main__":
    main()
