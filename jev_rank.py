#!/usr/bin/env python3
"""
jev_rank.py — JEV (TypeSafe System One) judgment layer on top of daily_sr.py output.

Improvements per the TypeSafe paper (Jev Trading Research Paper, 2026):
  1. 6-question parallel battery (was 3): regime, direction, confidence_gate,
     setup_quality, follow_through, risk_reward
  2. Compact numeric JSON state (was verbose text dossier)
  3. Correct response parsing per type: score→.score, choice→.value, noul→.probability
  4. Confidence gate stored in output for sam_picks.py to use

Runs AFTER daily_sr.py. Loads screen_output/sr_levels.json (which now includes
RSI14, EMA10/20/50, Bollinger, Supertrend, Ichimoku fields).

Outputs:
  screen_output/jev_rank.json   — full structured ranking (machine)
  public/data/jev_rank.js       — window.JEV_RANK for the Pages UI

Key: TYPESAFE_API_KEY env, else ~/.omp/profiles/sam/agent/.env. Never print key.
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen

HERE       = Path(__file__).resolve().parent
SR_JSON    = HERE / "screen_output" / "sr_levels.json"
OUT_JSON   = HERE / "screen_output" / "jev_rank.json"
OUT_JS     = HERE / "public" / "data" / "jev_rank.js"
PROFILE_ENV = Path.home() / ".omp" / "profiles" / "sam" / "agent" / ".env"

API_URL     = os.environ.get("TYPESAFE_API_URL", "https://api.typesafe.ai/v1/systemone")
MODEL       = "jev-latest"
TIMEOUT     = 30
MAX_WORKERS = 8
RETRIES     = 3

# ── 6-question battery (paper §V) ─────────────────────────────────────────────
# Rule: arithmetic stays in code; judgment goes to Jev.
# All questions evaluated in one parallel call (latency invariant).
# Type vocabulary: "score" / "choice" / "noul" (NOT "kind").
DIMENSIONS = {
    "regime": {
        "type": "choice",
        "instructions": (
            "Which market regime best describes this stock based only on the numeric features: "
            "ema_trend (UP/DOWN/MIXED), supertrend_dir (1=bull/-1=bear), "
            "ichimoku above_cloud / below_cloud / bullish_cloud flags, rsi14 level, "
            "and monthly regime label. Pick the single best match."
        ),
        "criteria": {
            "trending_up": None,
            "trending_down": None,
            "mean_reverting": None,
            "choppy_no_trend": None,
        },
    },
    "direction": {
        "type": "choice",
        "instructions": (
            "What direction is this stock most likely to move over the next 3-5 sessions "
            "based only on: signal, supertrend_dir, ema_trend, ichimoku tenkan_above_kijun, "
            "chikou_above, rsi14, and bb_pct_b? Pick one."
        ),
        "criteria": {"up": None, "down": None, "neutral": None},
    },
    "confidence_gate": {
        "type": "noul",
        "instructions": (
            "Are the signals in this snapshot clearly aligned and high-confidence actionable? "
            "Return a HIGH probability (>0.7) only if: signal, ema_trend, supertrend_dir, "
            "and ichimoku all point in the same direction AND rsi14 is not extreme overbought "
            "or oversold for the direction. Return LOW probability (<0.4) if signals conflict."
        ),
    },
    "setup_quality": {
        "type": "score",
        "instructions": (
            "Rate the technical setup quality from 1 (poor) to 5 (excellent) based only on: "
            "signal, vol_ratio, dist_resistance_atr, dist_support_atr, floor_strength, "
            "ceiling_strength, breakout_confirmed, bb_pct_b position, ichimoku cloud state."
        ),
        "criteria": ["1 poor", "2 weak", "3 average", "4 good", "5 textbook"],
    },
    "follow_through": {
        "type": "score",
        "instructions": (
            "How likely is price to follow through in the signal direction over 1-5 sessions? "
            "Rate 1 (likely fails) to 5 (high odds) based only on: vol_ratio, floor_strength, "
            "ceiling_strength, rsi14, ema_trend, supertrend_dir, ichimoku state, reclaim_support, "
            "failed_breakout, and AVWAP position."
        ),
        "criteria": ["1 likely fail", "2 low odds", "3 coin flip", "4 decent odds", "5 high odds"],
    },
    "risk_reward": {
        "type": "score",
        "instructions": (
            "Rate the risk/reward from entry at close to nearest floor/ceiling targets: "
            "1 (bad, tight stop + far target OR wide stop + close target) to 5 (excellent). "
            "Use only: floor, ceiling, next_target, next_floor, atr14, dist_resistance_atr, "
            "dist_support_atr, and bb_upper/lower levels."
        ),
        "criteria": ["1 bad", "2 poor", "3 ok", "4 good", "5 excellent"],
    },
}

# Weights for the 3 scored dimensions (choice/noul handled separately)
SCORE_WEIGHTS = {"setup_quality": 0.35, "follow_through": 0.30, "risk_reward": 0.35}


def load_key():
    key = os.environ.get("TYPESAFE_API_KEY")
    if key:
        return key.strip()
    if PROFILE_ENV.exists():
        for line in PROFILE_ENV.read_text().splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def compact_state(s):
    """Compact numeric JSON state (~240 tokens). Arithmetic in code; judgment to Jev."""
    ichi  = s.get("ichimoku") or {}
    avwap = s.get("avwap") or {}
    conf  = s.get("confluence") or {}
    fl    = (conf.get("floor") or {})
    cl    = (conf.get("ceiling") or {})
    return {
        # price & signal
        "symbol":            s["symbol"],
        "signal":            s["signal"],
        "sr_score":          s.get("score"),
        "close":             s["close"],
        "atr14":             s.get("atr14"),
        "vol_ratio":         s.get("vol_ratio"),
        # S/R distances
        "dist_resistance_atr": s.get("dist_resistance_atr"),
        "dist_support_atr":    s.get("dist_support_atr"),
        "floor_strength":      s.get("floor_strength"),
        "ceiling_strength":    s.get("ceiling_strength"),
        "floor_n_sources":     fl.get("n_sources"),
        "ceiling_n_sources":   cl.get("n_sources"),
        # breakout/trap flags
        "breakout_confirmed":  int(bool(s.get("breakout_confirmed"))),
        "reclaim_support":     int(bool(s.get("reclaim_support"))),
        "failed_breakout":     int(bool(s.get("failed_breakout"))),
        # VWAP/AVWAP
        "above_vwap20":        int(bool(s.get("above_vwap"))),
        "vwap20":              s.get("vwap20"),
        "avwap_swing_low":     avwap.get("swing_low"),
        # 52w position (% from 52w high)
        "pct_from_52w_hi":     round((s["close"] / s["hi52w"] - 1) * 100, 1) if s.get("hi52w") else None,
        # New indicators
        "rsi14":               s.get("rsi14"),
        "ema_trend":           s.get("ema_trend"),
        "above_ema50":         int(bool(s.get("above_ema50"))),
        "bb_pct_b":            s.get("bb_pct_b"),
        "bb_bandwidth":        s.get("bb_bandwidth"),
        "supertrend_dir":      s.get("supertrend_dir"),
        "ichi_above_cloud":    int(bool(ichi.get("above_cloud"))),
        "ichi_below_cloud":    int(bool(ichi.get("below_cloud"))),
        "ichi_bullish_cloud":  int(bool(ichi.get("bullish_cloud"))),
        "ichi_tk_above_kijun": int(bool(ichi.get("tenkan_above_kijun"))),
        "ichi_chikou_above":   int(bool(ichi.get("chikou_above"))),
        # Monthly regime (if present on the stock dict)
        "monthly_regime":      s.get("_monthly_regime"),
        "regime_age_months":   s.get("_regime_age"),
    }


def ask_once(state_dict, key):
    body = json.dumps({
        "state":     state_dict,
        "questions": DIMENSIONS,
        "model":     MODEL,
    }).encode()
    req = Request(API_URL, data=body, method="POST", headers={
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {key}",
    })
    with urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def ask(state_dict, key):
    last = None
    for attempt in range(RETRIES):
        try:
            return ask_once(state_dict, key)
        except Exception as e:
            last = e
            time.sleep(2 ** attempt)
    return {"ok": False, "reason": str(last)}


def parse_answers(answers):
    """Extract typed values from JEV response per dimension type.
    score  → .score  (0-based index/float)
    choice → .choice (selected option name)
    noul   → .noul   (float 0-1)
    Returns None for any missing field."""
    out = {}
    for dim, spec in DIMENSIONS.items():
        ans = (answers or {}).get(dim) or {}
        t = spec["type"]
        if t == "score":
            out[dim] = ans.get("score")           # 0-based level index
        elif t == "choice":
            out[dim] = ans.get("choice", ans.get("value"))            # string option name
        elif t == "noul":
            out[dim] = ans.get("noul", ans.get("probability"))        # float 0-1
    return out


def score_from_parsed(parsed):
    """Build composite from the 3 scored dimensions (0-1 normalised).
    Choice and noul contribute separately as metadata, not to composite."""
    max_lvl = {d: len(DIMENSIONS[d]["criteria"]) - 1
               for d in SCORE_WEIGHTS if DIMENSIONS[d]["type"] == "score"}
    norms = {}
    for d in SCORE_WEIGHTS:
        v = parsed.get(d)
        if v is None:
            return None           # incomplete — skip this stock
        norms[d] = v / max_lvl[d]
    return round(sum(SCORE_WEIGHTS[d] * norms[d] for d in SCORE_WEIGHTS), 4)


def main():
    key = load_key()
    if not key:
        sys.exit("TYPESAFE_API_KEY not found in env or " + str(PROFILE_ENV))

    sr = json.loads(SR_JSON.read_text())
    stocks = [s for s in sr["stocks"] if "error" not in s]
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futs = {pool.submit(ask, compact_state(s), key): s for s in stocks}
        for fut in as_completed(futs):
            s    = futs[fut]
            resp = fut.result()
            if not resp.get("ok", True) and "reason" in resp:
                print(f"warn: {s['symbol']} JEV failed: {resp['reason']}", file=sys.stderr)
                continue
            answers = resp.get("answers") or {}
            parsed  = parse_answers(answers)

            composite = score_from_parsed(parsed)
            if composite is None:
                print(f"warn: {s['symbol']} JEV incomplete scores: {parsed}", file=sys.stderr)
                continue

            # Normalise score dimensions for display (0-4 scale for UI back-compat)
            max_lvl = {d: len(DIMENSIONS[d]["criteria"]) - 1
                       for d in SCORE_WEIGHTS if DIMENSIONS[d]["type"] == "score"}

            results.append({
                "symbol":           s["symbol"],
                "name":             s.get("name"),
                "signal":           s["signal"],
                "sr_score":         s.get("score"),
                "close":            s["close"],
                "composite":        composite,
                # Scored dimensions (raw 0-based index)
                "setup_quality":    parsed.get("setup_quality"),
                "follow_through":   parsed.get("follow_through"),
                "risk_reward":      parsed.get("risk_reward"),
                # New: choice & noul answers
                "regime_jev":       parsed.get("regime"),
                "direction_jev":    parsed.get("direction"),
                "confidence_gate":  parsed.get("confidence_gate"),
            })

    results.sort(key=lambda r: -r["composite"])
    for i, r in enumerate(results, 1):
        r["rank"] = i

    payload = {
        "as_of":        sr["as_of"],
        "model":        MODEL,
        "dimensions":   list(DIMENSIONS),
        "score_weights": SCORE_WEIGHTS,
        "judged":       len(results),
        "of_universe":  len(stocks),
        "ranking":      results,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=1))
    js = ("// generated by jev_rank.py — do not edit by hand\n"
          "window.JEV_RANK = " + json.dumps(payload) + ";\n")
    OUT_JS.parent.mkdir(parents=True, exist_ok=True)
    OUT_JS.write_text(js)
    print(f"Saved: {OUT_JSON.name} + {OUT_JS.name} ({len(results)} judged of {len(stocks)})")
    def _gate(r):
        g = r.get('confidence_gate')
        return f"{g:.2f}" if isinstance(g, (int, float)) else "n/a"
    print("Top 5:", ", ".join(
        f"{r['symbol']} {r['composite']:.3f} [{r.get('regime_jev','?')}/{r.get('direction_jev','?')} gate:{_gate(r)}]"
        for r in results[:5]
    ))


if __name__ == "__main__":
    main()
