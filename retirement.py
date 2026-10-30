#!/usr/bin/env python3
"""Retirement 2031 — our own "top 50 of the Nifty 100" fund + the Rs 5 crore goal math.

Reads the already-built, already-verified daily setups (docs/daily_setups.json) so this
page is automatically as fresh as the daily HHHL/Jev pipeline. It never re-fetches prices
or re-calls Jev; it is a selection + goal-tracking layer on top of existing signals.

Universe:  Nifty 50 + Nifty Next 50 = the official Nifty 100 (membership from
           niftyindices.com, cached to nifty100.csv like nifty200.csv).
Selection: rank those 100 by a transparent composite of signals the pipeline already
           computes (daily rank.net, Jev composite/agreement, trend category, structure,
           momentum, reward:risk) and keep the best 50 — "our mutual fund".
Goal math: core-satellite plan toward Rs 5 crore on 15 Feb 2031. The ~70% safe core
           locks the floor; the ~30% satellite is this top-50 engine. Capital plan is
           configurable below and only drives the required-return gauge.

Outputs:
  docs/retirement.json            machine + UI payload
  public/data/retirement.json     mirror for the Pages UI

PAPER RESEARCH, NOT ADVICE. Selection is technical/sentiment, not fundamental valuation.
"""
import json
import csv
import io
import math
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
DOCS = HERE / "docs"
PUBLIC_DATA = HERE / "public" / "data"
NIFTY100_CSV = HERE / "nifty100.csv"
NIFTY100_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv"

# ── Goal + capital plan (edit these; they only move the required-return gauge) ──────
TARGET_RUPEES = 5_00_00_000          # Rs 5 crore
TARGET_DATE = date(2031, 2, 15)      # the birthday
LUMP_RUPEES = 1_00_00_000            # Rs 1 crore deployed now
MONTHLY_SIP = 4_00_000               # Rs 4 lakh / month on top
CORE_FRACTION = 0.70                 # ~70% safe core locks the floor
SATELLITE_FRACTION = 0.30            # ~30% aggressive "our top 50"
FUND_SIZE = 50                       # keep the best 50 of the 100

# Composite weights (sum = 1.0). Transparent and tunable.
WEIGHTS = {
    "daily_rank": 0.30,   # the pipeline's own buy/sell net strength (rank.net)
    "jev":        0.30,   # Jev composite quality + agreement
    "trend":      0.20,   # trend category + Dow structure
    "momentum":   0.12,   # recent change + participation (volume)
    "reward":     0.08,   # plan reward:risk quality
}

CATEGORY_SCORE = {
    "breakout": 1.00, "ready_to_break": 0.85, "uptrend": 0.80,
    "sideways": 0.45, "data_check": 0.40,
    "structure_exit": 0.15, "downtrend": 0.05,
}


def load_json(name):
    p = DOCS / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def nifty100_symbols():
    """Official Nifty 100 membership; refresh the cache when the live list is reachable."""
    try:
        req = Request(NIFTY100_URL, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"})
        txt = urlopen(req, timeout=25).read().decode("utf-8", "replace")
        rows = list(csv.DictReader(io.StringIO(txt)))
        syms = [r["Symbol"].strip() for r in rows if r.get("Series", "EQ").strip() == "EQ" and r.get("Symbol")]
        if len(syms) >= 95:
            NIFTY100_CSV.write_text(txt, encoding="utf-8")
            return set(syms), "live"
    except Exception:
        pass
    if NIFTY100_CSV.exists():
        rows = list(csv.DictReader(io.StringIO(NIFTY100_CSV.read_text(encoding="utf-8"))))
        return {r["Symbol"].strip() for r in rows if r.get("Symbol")}, "cache"
    raise SystemExit("No Nifty 100 membership: live fetch failed and nifty100.csv missing")


def clamp01(x):
    return max(0.0, min(1.0, x))


def score_stock(s):
    """Blend existing signals into a 0-100 retirement composite. All inputs already computed."""
    rank = s.get("rank") or {}
    net = rank.get("net")                       # ~ -100..+100 (bull - bear)
    daily = clamp01((net + 100) / 200) if isinstance(net, (int, float)) else 0.5

    jev = s.get("jev") or {}
    jc = jev.get("composite")
    jev_q = clamp01(jc) if isinstance(jc, (int, float)) else 0.5
    if jev.get("agrees") is True:
        jev_q = clamp01(jev_q + 0.08)
    elif jev.get("agrees") is False:
        jev_q = clamp01(jev_q - 0.08)

    cat = CATEGORY_SCORE.get((s.get("category") or "").lower(), 0.4)
    struct = 1.0 if (s.get("structure") or "").upper().startswith("HH") else 0.4
    trend = 0.65 * cat + 0.35 * struct

    chg = s.get("change_pct")
    vol = s.get("volume_ratio")
    mom = clamp01(0.5 + (chg / 6.0 if isinstance(chg, (int, float)) else 0.0))
    if isinstance(vol, (int, float)):
        mom = clamp01(mom + min(0.15, (vol - 1) * 0.15))

    plan = s.get("plan") or {}
    rr = plan.get("reward_risk")
    rr2 = rr[1] if isinstance(rr, list) and len(rr) > 1 else (rr if isinstance(rr, (int, float)) else None)
    reward = clamp01((rr2 / 3.0) if isinstance(rr2, (int, float)) else 0.5)

    parts = {"daily_rank": daily, "jev": jev_q, "trend": trend, "momentum": mom, "reward": reward}
    composite = sum(WEIGHTS[k] * parts[k] for k in WEIGHTS)
    return round(composite * 100, 2), parts


def action_for(s, score):
    """Map signal state to a hold/trim/exit decision for a long-term satellite position."""
    cat = (s.get("category") or "").lower()
    jev = s.get("jev") or {}
    if cat in ("downtrend", "structure_exit") or jev.get("direction") == "down" and score < 45:
        return "EXIT"
    if cat == "sideways" or score < 50:
        return "TRIM"
    if cat in ("breakout", "ready_to_break") and score >= 62:
        return "ADD"
    return "HOLD"


def months_between(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month) + (1 if b.day >= a.day else 0)


def fv_lump(P, r, years):
    return P * (1 + r) ** years


def fv_sip(P, r, n):
    if n <= 0:
        return 0.0
    m = (1 + r) ** (1 / 12) - 1
    return P * (((1 + m) ** n - 1) / m) * (1 + m)


def required_cagr(lump, monthly, n, years, target):
    lo, hi = -0.5, 0.8
    for _ in range(80):
        mid = (lo + hi) / 2
        if fv_lump(lump, mid, years) + fv_sip(monthly, mid, n) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def goal_math(as_of):
    today = date.fromisoformat(as_of)
    n = max(0, months_between(today, TARGET_DATE))
    years = n / 12 if n else 0.0001
    contrib = LUMP_RUPEES + MONTHLY_SIP * n
    projections = []
    for r in (0.08, 0.10, 0.12, 0.15, 0.18, 0.20):
        v = fv_lump(LUMP_RUPEES, r, years) + fv_sip(MONTHLY_SIP, r, n)
        projections.append({"cagr": r, "value": round(v), "hits_target": v >= TARGET_RUPEES})
    req = required_cagr(LUMP_RUPEES, MONTHLY_SIP, n, years, TARGET_RUPEES)
    return {
        "target": TARGET_RUPEES,
        "target_date": TARGET_DATE.isoformat(),
        "months_left": n,
        "years_left": round(years, 2),
        "lump": LUMP_RUPEES,
        "monthly_sip": MONTHLY_SIP,
        "total_contribution": contrib,
        "required_cagr": round(req, 4),
        "required_cagr_pct": round(req * 100, 1),
        "projections": projections,
        "note": ("At this capital plan you only need {:.1f}% a year to reach Rs 5 cr; your "
                 "own contributions are Rs {:.2f} cr of it. Aggression is for upside, not "
                 "for hitting the floor.").format(req * 100, contrib / 1e7),
    }


def find_vix():
    for name in ("daily_market.json", "global_markets.json"):
        d = load_json(name)
        buckets = []
        for key in ("indices", "rows", "markets", "breadth"):
            v = d.get(key)
            if isinstance(v, list):
                buckets.append(v)
        for rows in buckets:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                nm = (row.get("name") or row.get("index") or row.get("Index Name") or "").lower()
                if "vix" in nm:
                    return {"value": row.get("close") or row.get("value") or row.get("Close"),
                            "change_pct": row.get("change_pct") or row.get("change"), "source": name}
    return None


def build():
    setups = load_json("daily_setups.json")
    if not setups:
        raise SystemExit("docs/daily_setups.json missing — run the daily pipeline first")
    as_of = setups["as_of"]
    universe100, membership_src = nifty100_symbols()
    by_symbol = {s["symbol"]: s for s in setups.get("stocks", [])}

    present = [sym for sym in universe100 if sym in by_symbol]
    missing = sorted(universe100 - set(by_symbol))

    scored = []
    for sym in present:
        s = by_symbol[sym]
        sc, parts = score_stock(s)
        scored.append((sc, parts, s))
    scored.sort(key=lambda t: -t[0])

    picks = []
    for i, (sc, parts, s) in enumerate(scored[:FUND_SIZE], 1):
        jev = s.get("jev") or {}
        plan = s.get("plan") or {}
        picks.append({
            "fund_rank": i,
            "symbol": s["symbol"],
            "name": s.get("name"),
            "sector": s.get("sector"),
            "close": s.get("close"),
            "change_pct": s.get("change_pct"),
            "category": s.get("category"),
            "structure": s.get("structure"),
            "retire_score": sc,
            "score_parts": {k: round(v, 3) for k, v in parts.items()},
            "action": action_for(s, sc),
            "conviction": s.get("conviction"),
            "jev": {k: jev.get(k) for k in ("composite", "rank", "of", "direction", "regime",
                                            "confidence", "agrees", "signal")},
            "entry": plan.get("entry"),
            "stop": plan.get("stop"),
            "structure_exit": s.get("structure_exit"),
            "targets": plan.get("targets"),
            "next_target": plan.get("next_target"),
            "reward_risk": plan.get("reward_risk"),
            "words": plan.get("words"),
        })

    # Sector heatmap across the chosen 50
    sectors = {}
    for p in picks:
        d = sectors.setdefault(p["sector"] or "Unknown", {"count": 0, "score_sum": 0.0})
        d["count"] += 1
        d["score_sum"] += p["retire_score"]
    heatmap = sorted(
        ({"sector": k, "count": v["count"], "avg_score": round(v["score_sum"] / v["count"], 1)}
         for k, v in sectors.items()),
        key=lambda x: -x["avg_score"])

    actions = {}
    for p in picks:
        actions[p["action"]] = actions.get(p["action"], 0) + 1

    payload = {
        "version": 1,
        "as_of": as_of,
        "generated_from": "docs/daily_setups.json",
        "membership_source": membership_src,
        "disclaimer": "PAPER RESEARCH, NOT ADVICE. Technical/sentiment selection, not fundamentals.",
        "goal": goal_math(as_of),
        "allocation": {
            "core_fraction": CORE_FRACTION,
            "satellite_fraction": SATELLITE_FRACTION,
            "core": "Large-cap index fund + short-duration debt / FD. Locks the Rs 5 cr floor.",
            "satellite": "This 'Our Top 50' engine. Swings for 20%+ with structure-exits.",
        },
        "vix": find_vix(),
        "fund_size": len(picks),
        "universe": {"name": "Nifty 100 (Nifty 50 + Next 50)", "available": len(present),
                     "missing": missing},
        "action_summary": actions,
        "sector_heatmap": heatmap,
        "picks": picks,
    }

    DOCS.mkdir(exist_ok=True)
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    (DOCS / "retirement.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    (PUBLIC_DATA / "retirement.json").write_text(json.dumps(payload), encoding="utf-8")
    g = payload["goal"]
    print(f"retirement.json: as_of {as_of}, {len(picks)} picks of {len(present)} Nifty-100 "
          f"names ({membership_src} membership); {g['months_left']} months left; "
          f"required {g['required_cagr_pct']}% CAGR; actions {actions}")
    if missing:
        print(f"  note: {len(missing)} Nifty-100 names absent from setups: {', '.join(missing[:8])}"
              + (" ..." if len(missing) > 8 else ""))
    return payload


if __name__ == "__main__":
    build()
