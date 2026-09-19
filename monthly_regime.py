#!/usr/bin/env python3
"""
monthly_regime.py — Monthly trend-regime screener for all Nifty 200 stocks.

Runs INDEPENDENTLY of daily_sr.py (monthly cadence, ≤ once per week practical).
Uses adjusted monthly closes from yfinance; excludes current incomplete month.
Computes trailing 12-month return regime (UP/DOWN/SIDE) per Fama-French convention.
Then runs TypeSafe/JEV judgment layer for regime quality, persistence odds, and reversal watch.

Outputs:
  screen_output/monthly_regimes.json  — full structured regime data (machine)
  public/data/monthly_regime.js       — window.MONTHLY_REGIME for Pages UI (no key client-side)
  screen_output/monthly_regime_jev.json — JEV-scored ranking
"""
import csv, json, os, statistics, sys, time, warnings
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

warnings.filterwarnings('ignore')
import yfinance as yf

HERE     = Path(__file__).resolve().parent
OUT      = HERE / "screen_output"
UNIV     = HERE / "nifty200.csv"
OUT_JS   = HERE / "public" / "data" / "monthly_regime.js"
PROFILE_ENV = Path.home() / ".omp" / "profiles" / "sam" / "agent" / ".env"
API_URL  = os.environ.get("TYPESAFE_API_URL", "https://api.typesafe.ai/v1/systemone")
MODEL    = "jev-latest"
BAND     = 0.05   # ±5% trailing 12m return = SIDE threshold
LOOKBACK = 12     # trailing months for regime label
MAX_WORKERS = 12
JEV_WORKERS = 8
RETRIES  = 3

RECENTLY_LISTED_MIN_BARS = 14

DIMENSIONS = {
    "regime_quality": {
        "type": "score",
        "instructions": "Quality of this monthly regime as a swing-trade context based ONLY on numbers: label, age vs historical mean for that direction, reversal_risk_ratio, 12m/6m momentum alignment, recent segment history. 0=contradictory, 4=high-conviction.",
        "criteria": ["0 contradictory", "1 weak", "2 moderate", "3 solid", "4 high-conviction"],
    },
    "persistence_odds": {
        "type": "score",
        "instructions": "Probability the current monthly regime persists >= 2 more months based ONLY on age vs historical mean run, reversal_risk_ratio, and momentum. 0=likely reversing, 4=high persistence.",
        "criteria": ["0 likely reversing", "1 stretched", "2 uncertain", "3 probably continuing", "4 high persistence"],
    },
    "reversal_watch": {
        "type": "score",
        "instructions": "Urgency to watch for regime reversal right now based ONLY on reversal_risk_ratio, regime age, recent segment choppiness. 0=no urgency young regime, 4=critical very stretched.",
        "criteria": ["0 no watch", "1 minor", "2 moderate", "3 elevated", "4 critical"],
    },
}
WEIGHTS = {"regime_quality": 0.40, "persistence_odds": 0.35, "reversal_watch": 0.25}
MAX_LVL  = {k: len(v["criteria"]) - 1 for k, v in DIMENSIONS.items()}


def load_key():
    key = os.environ.get("TYPESAFE_API_KEY")
    if key:
        return key.strip()
    if PROFILE_ENV.exists():
        for line in PROFILE_ENV.read_text().splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def monthly_adj(symbol, periods=("15y", "5y", "3y")):
    now = datetime.now()
    for period in periods:
        try:
            df = yf.Ticker(symbol + ".NS").history(period=period, interval="1mo", auto_adjust=True, actions=False)
            df = df.dropna(subset=["Close"])
            if len(df) and df.index[-1].year == now.year and df.index[-1].month == now.month:
                df = df.iloc[:-1]
            m = [(idx.strftime("%Y-%m"), float(row.Close)) for idx, row in df.iterrows()]
            if len(m) >= RECENTLY_LISTED_MIN_BARS:
                return m
        except Exception:
            pass
    return []


def detect_regimes(months):
    out = []
    for i in range(LOOKBACK, len(months)):
        dt, c = months[i]; pc = months[i - LOOKBACK][1]
        r = c / pc - 1
        lab = "UP" if r > BAND else "DOWN" if r < -BAND else "SIDE"
        out.append((dt, c, r, lab))
    segs = []
    if not out:
        return segs
    cur = out[0][3]; start = out[0][0]; startc = out[0][1]; vals = []
    prev_dt = out[0][0]; prev_c = out[0][1]
    for dt, c, r, lab in out:
        if lab != cur:
            segs.append({"label": cur, "start": start, "end": prev_dt, "months": len(vals),
                         "price_start": round(startc, 2), "price_end": round(prev_c, 2),
                         "ret_pct": round((prev_c / startc - 1) * 100, 1),
                         "avg_12m_ret_pct": round(statistics.mean(vals) * 100, 1)})
            cur = lab; start = dt; startc = c; vals = []
        vals.append(r); prev_dt = dt; prev_c = c
    segs.append({"label": cur, "start": start, "end": prev_dt, "months": len(vals),
                 "price_start": round(startc, 2), "price_end": round(prev_c, 2),
                 "ret_pct": round((prev_c / startc - 1) * 100, 1),
                 "avg_12m_ret_pct": round(statistics.mean(vals) * 100, 1)})
    return segs


def hstat(arr):
    if not arr:
        return None
    return {"n": len(arr), "median": round(statistics.median(arr), 1),
            "mean": round(statistics.mean(arr), 1), "max": max(arr)}


def analyse(symbol, name):
    m = monthly_adj(symbol)
    if len(m) < RECENTLY_LISTED_MIN_BARS:
        return symbol, {"symbol": symbol, "name": name, "recently_listed": True,
                        "note": "Listed < 14 months — no monthly regime data yet",
                        "current": {"label": "N/A"}}
    segs = detect_regimes(m)
    if not segs:
        return symbol, {"symbol": symbol, "error": "no_regimes"}
    cur = segs[-1]
    hist = {"UP": [], "DOWN": [], "SIDE": []}
    for s in segs[:-1]:
        hist[s["label"]].append(s["months"])
    close_now = m[-1][1]
    close_12m = m[-13][1] if len(m) >= 13 else None
    close_6m  = m[-7][1]  if len(m) >= 7  else None
    hist_mean = statistics.mean(hist[cur["label"]] + [cur["months"]]) if hist[cur["label"]] else None
    rev_risk  = round(cur["months"] / (hist_mean or cur["months"]), 2)
    return symbol, {
        "symbol": symbol, "name": name,
        "last_bar": m[-1][0], "close": round(close_now, 2),
        "mom12_pct": round((close_now / close_12m - 1) * 100, 1) if close_12m else None,
        "mom6_pct":  round((close_now / close_6m  - 1) * 100, 1) if close_6m  else None,
        "current": {"label": cur["label"], "start": cur["start"],
                    "age_months": cur["months"], "ret_pct": cur["ret_pct"],
                    "avg_12m_ret_pct": cur["avg_12m_ret_pct"]},
        "reversal_risk_ratio": rev_risk,
        "hist_up":   hstat(hist["UP"]),
        "hist_down": hstat(hist["DOWN"]),
        "recent_segs": segs[-5:],
        "all_segs": segs,
    }


def dossier(s):
    cur = s.get("current", {}); hu = s.get("hist_up") or {}; hd = s.get("hist_down") or {}
    seg_str = " ".join(f"{x['label']}{x['months']}m({x['ret_pct']}%)" for x in s.get("recent_segs", []))
    return (f"{s['symbol']} | regime={cur.get('label')} age={cur.get('age_months')}m "
            f"since={cur.get('start')} ret={cur.get('ret_pct')}% avg12m={cur.get('avg_12m_ret_pct')}% "
            f"rev_risk={s.get('reversal_risk_ratio')} mom12={s.get('mom12_pct')}% mom6={s.get('mom6_pct')}% "
            f"hist_up_mean={hu.get('mean')}m hist_down_mean={hd.get('mean')}m segs={seg_str}")


def ask_jev(state, key):
    last = None
    for attempt in range(RETRIES):
        try:
            body = json.dumps({"state": state, "questions": DIMENSIONS, "model": MODEL}).encode()
            req  = Request(API_URL, data=body, method="POST",
                           headers={"Content-Type": "application/json",
                                    "Authorization": f"Bearer {key}"})
            with urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            last = e; time.sleep(2 ** attempt)
    return {"ok": False, "reason": str(last)}


def run_jev(stocks, key):
    ranked = []
    with ThreadPoolExecutor(max_workers=JEV_WORKERS) as pool:
        futs = {pool.submit(ask_jev, dossier(s), key): s for s in stocks}
        for fut in as_completed(futs):
            s   = futs[fut]
            res = fut.result()
            ans = res.get("answers") or {}
            scores = {d: (ans.get(d) or {}).get("score") for d in DIMENSIONS}
            if all(v is not None for v in scores.values()):
                # reversal_watch: high score = critical/stretched = BAD for a trade → invert
                norm  = {d: (1 - scores[d] / MAX_LVL[d]) if d == 'reversal_watch'
                         else scores[d] / MAX_LVL[d] for d in scores}
                comp  = sum(WEIGHTS[d] * norm[d] for d in WEIGHTS)
                ranked.append({**s, "jev": {"composite": round(comp, 4), **{d: scores[d] for d in DIMENSIONS}}})
            else:
                ranked.append({**s, "jev": None})
    ranked.sort(key=lambda x: -(x.get("jev") or {}).get("composite", -1))
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return ranked


def main():
    rows = list(csv.DictReader(open(UNIV, newline="", encoding="utf-8-sig")))
    syms = [(r["Symbol"].strip(), r.get("Company Name", "").strip())
            for r in rows if r.get("Series", "EQ").strip() == "EQ"]

    print(f"Fetching monthly close + regimes for {len(syms)} stocks…")
    results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(analyse, s, n): (s, n) for s, n in syms}
        done = 0
        for f in as_completed(futs):
            sym, data = f.result()
            results[sym] = data
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(syms)}…")

    recent = [v for v in results.values() if v.get("recently_listed")]
    valid  = [v for v in results.values() if "error" not in v and not v.get("recently_listed")]
    errors = {k: v for k, v in results.items() if "error" in v}
    sig    = Counter(v["current"]["label"] for v in valid)

    print(f"Regimes: {dict(sig)} | recently_listed: {len(recent)} | errors: {len(errors)}")

    key = load_key()
    if key:
        print("Running JEV judgment layer…")
        ranked = run_jev(valid, key)
    else:
        print("TYPESAFE_API_KEY not found — skipping JEV layer")
        ranked = sorted(valid, key=lambda x: ("DOWN","SIDE","UP","N/A").index(x["current"]["label"]))

    output = {
        "as_of": max((v["last_bar"] for v in valid), default=""),
        "universe": len(syms), "fetched": len(valid),
        "recently_listed": [v["symbol"] for v in recent],
        "errors": len(errors), "error_detail": {k: v for k, v in errors.items()},
        "summary": dict(sig),
        "jev_model": MODEL if key else None,
        "stocks": ranked + recent,
    }
    (OUT / "monthly_regimes.json").write_text(json.dumps(output, indent=1), encoding="utf-8")
    js = "// generated by monthly_regime.py\nwindow.MONTHLY_REGIME = " + json.dumps(output) + ";\n"
    OUT_JS.parent.mkdir(parents=True, exist_ok=True)
    OUT_JS.write_text(js, encoding="utf-8")
    print(f"Saved: monthly_regimes.json + monthly_regime.js ({len(valid)} stocks, {len(recent)} recently listed)")
    print("Top 5:", ", ".join(f"{r['symbol']}({r['current']['label']})" for r in ranked[:5]))


if __name__ == "__main__":
    main()
