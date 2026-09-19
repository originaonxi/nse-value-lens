#!/usr/bin/env python3
"""
jev_rank.py — JEV (TypeSafe System One) judgment layer on top of daily_sr.py output.

Runs AFTER daily_sr.py. Loads screen_output/sr_levels.json, builds one numeric
dossier per stock (no narratives — JEV judges data, not names), asks Jev three
scored questions per stock in one parallel request, composes a weighted
composite, and writes:

  screen_output/jev_rank.json   — full structured ranking (machine)
  public/data/jev_rank.js       — window.JEV_RANK for the Pages UI (no key client-side)

Key resolution: TYPESAFE_API_KEY env, else ~/.omp/profiles/sam/agent/.env.
Set TYPESAFE_API_URL to override the endpoint. Never print the key.
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
SR_JSON = HERE / "screen_output" / "sr_levels.json"
OUT_JSON = HERE / "screen_output" / "jev_rank.json"
OUT_JS = HERE / "public" / "data" / "jev_rank.js"
PROFILE_ENV = Path.home() / ".omp" / "profiles" / "sam" / "agent" / ".env"

API_URL = os.environ.get("TYPESAFE_API_URL", "https://api.typesafe.ai/v1/systemone")
MODEL = "jev-latest"
TIMEOUT = 30
MAX_WORKERS = 8
RETRIES = 3

DIMENSIONS = {
    "setup_quality": {
        "type": "score",
        "instructions": "Quality of this technical swing-trade setup judging ONLY the numeric features: signal state, ATR-buffered breakout confirmation, volume confirmation, distance to nearest S/R, confluence strength/source diversity, touches, rejection depth, AVWAP/round-number support, VWAP position, pivot/Donchian context. 0=poor/choppy, 4=textbook clean",
        "criteria": ["1 poor", "2 weak", "3 average", "4 good", "5 textbook"],
    },
    "follow_through": {
        "type": "score",
        "instructions": "Likelihood the price follows through in the signal direction over the next 1-5 sessions based ONLY on the numbers: vol ratio, ATR distances, floor/ceiling strength, touch/rejection history, AVWAP/volume-profile confluence, 52w position, and reclaim/failed-break flags. 0=likely fail, 4=high odds",
        "criteria": ["1 likely fail", "2 low", "3 coin flip", "4 decent", "5 high odds"],
    },
    "risk_reward": {
        "type": "score",
        "instructions": "Trade risk/reward from entry at close using floor/ceiling, their confluence strengths, next_target, next_floor, ATR distances, and trap/reclaim flags ONLY. 0=bad, 4=excellent",
        "criteria": ["1 bad", "2 poor", "3 ok", "4 good", "5 excellent"],
    },
}
WEIGHTS = {"setup_quality": 0.35, "follow_through": 0.30, "risk_reward": 0.35}


def load_key():
    key = os.environ.get("TYPESAFE_API_KEY")
    if key:
        return key.strip()
    if PROFILE_ENV.exists():
        for line in PROFILE_ENV.read_text().splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def dossier(s):
    p = s.get("pivot", {})
    c = s.get("confluence") or {}
    floor_c = c.get("floor") or {}
    ceil_c = c.get("ceiling") or {}
    return (
        f"{s['symbol']} | signal={s['signal']} score={s.get('score')} "
        f"close={s['close']} ATR14={s['atr14']} vol_ratio={s.get('vol_ratio')} "
        f"R_dist={s.get('dist_resistance_atr')}ATR S_dist={s.get('dist_support_atr')}ATR "
        f"floor={s.get('floor')} floor_strength={s.get('floor_strength')} "
        f"floor_sources={','.join(floor_c.get('sources') or [])} "
        f"floor_touches={floor_c.get('touches')} floor_rejection_atr={floor_c.get('rejection_atr')} "
        f"ceiling={s.get('ceiling')} ceiling_strength={s.get('ceiling_strength')} "
        f"ceiling_sources={','.join(ceil_c.get('sources') or [])} "
        f"ceiling_touches={ceil_c.get('touches')} ceiling_rejection_atr={ceil_c.get('rejection_atr')} "
        f"next_target={s.get('next_target')} next_floor={s.get('next_floor')} "
        f"above_vwap20={s.get('above_vwap')} vwap20={s.get('vwap20')} "
        f"avwap={s.get('avwap')} reclaim_support={s.get('reclaim_support')} failed_breakout={s.get('failed_breakout')} "
        f"breakout_confirmed={s.get('breakout_confirmed')} buffer_atr={s.get('breakout_buffer_atr')} "
        f"pivotPP={p.get('PP')} d20_high={s.get('d20_high')} d20_low={s.get('d20_low')} "
        f"52w_hi={s.get('hi52w')} 52w_lo={s.get('lo52w')} POC={s.get('poc')}"
    )


def ask_once(state, key):
    body = json.dumps({"state": state, "questions": DIMENSIONS, "model": MODEL}).encode()
    req = Request(API_URL, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    })
    with urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def ask(state, key):
    last = None
    for attempt in range(RETRIES):
        try:
            return ask_once(state, key)
        except Exception as e:  # noqa: BLE001 — network faults fall back, never crash the nightly job
            last = e
            time.sleep(2 ** attempt)
    return {"ok": False, "reason": str(last)}


def main():
    key = load_key()
    if not key:
        sys.exit("TYPESAFE_API_KEY not found in env or " + str(PROFILE_ENV))
    sr = json.loads(SR_JSON.read_text())
    stocks = [s for s in sr["stocks"] if "error" not in s]
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futs = {pool.submit(ask, dossier(s), key): s for s in stocks}
        for fut in as_completed(futs):
            s = futs[fut]
            resp = fut.result()
            answers = resp.get("answers") or {}
            scores = {d: (answers.get(d) or {}).get("score") for d in DIMENSIONS}
            if all(v is not None for v in scores.values()):
                # JEV score answers are 0-based level indices; mirror SAM lib/typesafe.js rankItems
                max_lvl = {d: len(DIMENSIONS[d]['criteria']) - 1 for d in DIMENSIONS}
                norm = {d: scores[d] / max_lvl[d] for d in scores}
                composite = sum(WEIGHTS[d] * norm[d] for d in WEIGHTS)
                results.append({
                    "symbol": s["symbol"], "name": s.get("name"),
                    "signal": s["signal"], "sr_score": s.get("score"),
                    "close": s["close"],
                    "composite": round(composite, 4),
                    **{d: scores[d] for d in DIMENSIONS},
                })
            else:
                print(f"warn: {s['symbol']} JEV failed: {resp.get('reason') or answers}", file=sys.stderr)

    results.sort(key=lambda r: -r["composite"])
    for i, r in enumerate(results, 1):
        r["rank"] = i

    payload = {
        "as_of": sr["as_of"],
        "model": MODEL,
        "dimensions": list(DIMENSIONS),
        "weights": WEIGHTS,
        "judged": len(results),
        "of_universe": len(stocks),
        "ranking": results,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=1))
    js = "// generated by jev_rank.py — do not edit by hand\nwindow.JEV_RANK = " + json.dumps(payload) + ";\n"
    OUT_JS.parent.mkdir(parents=True, exist_ok=True)
    OUT_JS.write_text(js)
    print(f"Saved: {OUT_JSON.name} + {OUT_JS.name} ({len(results)} judged of {len(stocks)})")
    print("Top 5:", ", ".join(f"{r['symbol']} {r['composite']:.3f}" for r in results[:5]))


if __name__ == "__main__":
    main()
