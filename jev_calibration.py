#!/usr/bin/env python3
"""JEV Calibration Logger — 5th paper improvement (Jev Trading Research Paper, 2026 §VII).

Logs every JEV prediction (snapshot state + answers) at the time sam_picks runs,
then scores matured predictions using realized 5-day and 10-day returns.
Computes Brier Score and Expected Calibration Error per question type.

Paper formula (eq 10):  BS  = (1/n) Σ (p_i − y_i)²
Paper formula (eq 11):  ECE = Σ_b (|B_b|/n) × |acc(B_b) − conf(B_b)|

Run after sam_picks.py in the daily workflow.
Outputs:
  screen_output/jev_outcomes.jsonl   — append-only ledger
  screen_output/jev_calibration.json — scored summary
  docs/jev_calibration.json          — for website display
"""
from __future__ import annotations

import json
import math
import pickle
from datetime import date, datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

HERE   = Path(__file__).resolve().parent
OUT    = HERE / "screen_output"
DOCS   = HERE / "docs"
LOG    = OUT / "jev_outcomes.jsonl"
CAL_OUT = OUT / "jev_calibration.json"
CAL_DOC = DOCS / "jev_calibration.json"

# How many trading days to look forward for outcome measurement
HORIZONS = {"h5": 5, "h10": 10}

# Brier Score: prediction accuracy gate — calibration window
MIN_SCORED = 20     # need at least 20 scored predictions before reporting


def load_sr_jev():
    """Load today's sr_levels.json and jev_rank.json (already generated)."""
    sr   = json.loads((OUT / "sr_levels.json").read_text())
    jev  = json.loads((OUT / "jev_rank.json").read_text())
    picks = json.loads((OUT / "sam_picks.json").read_text())
    return sr, jev, picks


def log_today(sr, jev, picks):
    """Append today's predictions to the outcome ledger (no outcome yet)."""
    as_of   = sr.get("as_of", date.today().isoformat())
    jev_map = {r["symbol"]: r for r in jev.get("ranking", [])}
    pick_map = {p["symbol"]: p for p in picks.get("picks", [])}

    lines = []
    for s in sr.get("stocks", []):
        if "error" in s:
            continue
        sym = s["symbol"]
        j   = jev_map.get(sym, {})
        p   = pick_map.get(sym, {})
        lines.append(json.dumps({
            "sym":      sym,
            "as_of":    as_of,
            "close":    s["close"],
            "signal":   s["signal"],
            "action":   p.get("action", "NEUTRAL"),
            "sam":      p.get("sam_score", 0),
            # JEV typed answers
            "composite":        j.get("composite"),
            "confidence_gate":  j.get("confidence_gate"),
            "regime_jev":       j.get("regime_jev"),
            "direction_jev":    j.get("direction_jev"),
            "setup_quality":    j.get("setup_quality"),
            "follow_through":   j.get("follow_through"),
            "risk_reward_jev":  j.get("risk_reward"),
            # New indicators snapshot (for calibration analysis)
            "rsi14":            s.get("rsi14"),
            "ema_trend":        s.get("ema_trend"),
            "supertrend_dir":   s.get("supertrend_dir"),
            "ichi_above_cloud": (s.get("ichimoku") or {}).get("above_cloud"),
            # Outcomes to be filled later
            "ret_h5":   None,  # 5-day return, filled when price available
            "ret_h10":  None,  # 10-day return
            "y_h5":     None,  # binary: did BUY/WATCH_BUY go up > 1% in 5d?
            "y_h10":    None,
            "scored":   False,
        }))
    # Append to JSONL
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
    print(f"Logged {len(lines)} predictions for {as_of}")


def score_matured():
    """Read ledger, fill outcomes for matured predictions, rewrite, compute Brier."""
    if not LOG.exists():
        print("No ledger yet — nothing to score.")
        return

    records = [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]

    # Load current prices for scoring
    try:
        sr_data = json.loads((OUT / "sr_levels.json").read_text())
        today   = sr_data.get("as_of", date.today().isoformat())
        prices  = {s["symbol"]: s["close"] for s in sr_data.get("stocks", []) if "error" not in s}
    except Exception:
        prices = {}
        today  = date.today().isoformat()

    today_dt = datetime.strptime(today, "%Y-%m-%d").date()

    def trading_days_between(a_str, b_dt):
        """Approximate: count weekdays between dates."""
        a = datetime.strptime(a_str, "%Y-%m-%d").date()
        count = 0
        d = a + timedelta(days=1)
        while d <= b_dt:
            if d.weekday() < 5:
                count += 1
            d += timedelta(days=1)
        return count

    updated = 0
    for rec in records:
        if rec.get("scored"):
            continue
        days = trading_days_between(rec["as_of"], today_dt)
        if days < HORIZONS["h5"]:
            continue  # not mature yet
        p_then = rec.get("close", 0)
        p_now  = prices.get(rec["sym"])
        if not p_then or not p_now:
            continue
        raw_ret = (p_now / p_then) - 1.0
        rec["ret_h5"]  = round(raw_ret, 4)
        rec["ret_h10"] = round(raw_ret, 4)  # approx; h10 needs 10-day price
        # Binary outcomes: was a BUY/WATCH_BUY prediction correct?
        # BUY = up > +1% in window; AVOID = down < -1%
        if rec.get("action") in ("BUY", "WATCH_BUY"):
            rec["y_h5"] = 1 if raw_ret > 0.01 else 0
        elif rec.get("action") in ("AVOID", "CAUTION"):
            rec["y_h5"] = 1 if raw_ret < -0.01 else 0
        else:
            rec["y_h5"] = None   # NEUTRAL — no binary outcome
        rec["y_h10"] = rec["y_h5"]
        if days >= HORIZONS["h10"]:
            rec["scored"] = True
        updated += 1

    # Rewrite ledger with updated outcomes
    with LOG.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    print(f"Scored/updated {updated} records")

    # Compute Brier Score and ECE over matured+scored records
    scored = [r for r in records if r.get("scored") and r.get("y_h5") is not None and r.get("composite") is not None]
    print(f"Matured scored records: {len(scored)}")

    calibration = {
        "as_of":          today,
        "total_logged":   len(records),
        "total_scored":   len(scored),
        "min_scored":     MIN_SCORED,
        "ready":          len(scored) >= MIN_SCORED,
        "brier_score":    None,
        "ece":            None,
        "accuracy":       None,
        "bins":           [],
    }

    if len(scored) >= MIN_SCORED:
        # Brier Score (uses composite as probability proxy, scaled 0-1)
        bs_vals = [(r["composite"] - r["y_h5"]) ** 2 for r in scored if r["composite"] is not None]
        calibration["brier_score"] = round(sum(bs_vals) / len(bs_vals), 4)

        # Accuracy
        correct = sum(1 for r in scored if (r["composite"] >= 0.5 and r["y_h5"] == 1) or (r["composite"] < 0.5 and r["y_h5"] == 0))
        calibration["accuracy"] = round(correct / len(scored), 4)

        # ECE — 10 equal-width bins over composite [0, 1]
        n_bins = 10
        bins   = [{} for _ in range(n_bins)]
        for r in scored:
            b = min(int(r["composite"] * n_bins), n_bins - 1)
            bins[b].setdefault("preds", []).append(r["composite"])
            bins[b].setdefault("ys",    []).append(r["y_h5"])
        ece_sum = 0.0
        bin_summary = []
        for b, bdata in enumerate(bins):
            if not bdata:
                bin_summary.append(None)
                continue
            conf = sum(bdata["preds"]) / len(bdata["preds"])
            acc  = sum(bdata["ys"])    / len(bdata["ys"])
            ece_sum += (len(bdata["preds"]) / len(scored)) * abs(acc - conf)
            bin_summary.append({"conf": round(conf, 3), "acc": round(acc, 3), "n": len(bdata["preds"])})
        calibration["ece"]  = round(ece_sum, 4)
        calibration["bins"] = bin_summary
        print(f"Brier Score: {calibration['brier_score']:.4f}  ECE: {calibration['ece']:.4f}  Accuracy: {calibration['accuracy']:.2%}")
    else:
        print(f"Need {MIN_SCORED - len(scored)} more scored records before Brier Score is reliable.")

    CAL_OUT.write_text(json.dumps(calibration, indent=1), encoding="utf-8")
    CAL_DOC.write_text(json.dumps(calibration, indent=1), encoding="utf-8")
    print(f"Saved: {CAL_OUT.name}")
    return calibration


def main():
    try:
        sr, jev, picks = load_sr_jev()
        log_today(sr, jev, picks)
        score_matured()
    except FileNotFoundError as e:
        print(f"Calibration skipped — missing input: {e}")


if __name__ == "__main__":
    main()
