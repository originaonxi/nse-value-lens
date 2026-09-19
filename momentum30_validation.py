#!/usr/bin/env python3
"""Official Momentum 30 validation gate.

This script is intentionally strict. It will not claim that the model predicts
Momentum 30 unless official historical constituents and/or official index return
series are supplied. Without those inputs it writes a BLOCKED manifest.

Optional input files:
  data/momentum30_constituents.csv
      Either rows: effective_date,symbol
      Or rows: effective_date,constituents (comma/semicolon/pipe separated)
  data/nifty200_momentum30_tri.csv
      date,close  (official TRI or price index values; source must be recorded)
"""
from __future__ import annotations

import csv
import json
import math
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "screen_output" / "momentum30_validation.json"
DOCS_OUT = ROOT / "docs" / "momentum30_validation.json"
OFFICIAL_CONSTITUENTS = DATA / "momentum30_constituents.csv"
OFFICIAL_RETURNS = DATA / "nifty200_momentum30_tri.csv"


def split_symbols(text: str) -> list[str]:
    return [x.strip().upper() for x in re.split(r"[,;|]\s*", text or "") if x.strip()]


def load_constituents(path: Path) -> dict[str, set[str]]:
    by_date: dict[str, set[str]] = {}
    for r in csv.DictReader(path.open(newline="", encoding="utf-8-sig")):
        d = r.get("effective_date") or r.get("date") or ""
        if not d:
            continue
        if r.get("constituents"):
            syms = split_symbols(r["constituents"])
        else:
            sym = (r.get("symbol") or r.get("Symbol") or "").strip().upper()
            syms = [sym] if sym else []
        by_date.setdefault(d, set()).update(syms)
    return by_date


def benchmark_returns(path: Path) -> dict:
    rows = []
    for r in csv.DictReader(path.open(newline="", encoding="utf-8-sig")):
        d = r.get("date") or r.get("Date")
        v = r.get("close") or r.get("Close") or r.get("tri") or r.get("TRI")
        if not d or not v:
            continue
        rows.append((d, float(str(v).replace(",", ""))))
    rows.sort(key=lambda x: x[0])
    if len(rows) < 2:
        return {"status": "ERROR", "reason": "official return file has fewer than 2 valid rows"}
    start, end = rows[0][1], rows[-1][1]
    total = end / start - 1.0
    years = max(len(rows) / 252.0, 1 / 252)
    cagr = (end / start) ** (1 / years) - 1.0
    peak = rows[0][1]
    maxdd = 0.0
    for _, v in rows:
        peak = max(peak, v)
        maxdd = max(maxdd, (peak - v) / peak)
    return {
        "status": "OK_OFFICIAL_RETURNS_LOADED",
        "rows": len(rows),
        "start_date": rows[0][0],
        "end_date": rows[-1][0],
        "total_ret_pct": round(total * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "max_drawdown_pct": round(maxdd * 100, 2),
    }


def main() -> None:
    out = {
        "as_of": date.today().isoformat(),
        "status": "BLOCKED_MISSING_OFFICIAL_VALIDATION_DATA",
        "constituent_prediction": {
            "status": "BLOCKED",
            "required_file": str(OFFICIAL_CONSTITUENTS.relative_to(ROOT)),
            "reason": "Need official historical Momentum 30 constituents to score precision@30, entrants, exits, and rank hit-rate.",
        },
        "official_return_benchmark": {
            "status": "BLOCKED",
            "required_file": str(OFFICIAL_RETURNS.relative_to(ROOT)),
            "reason": "Need official Momentum 30 TRI/price index history to benchmark shadow portfolio returns.",
        },
        "acceptable_sources": [
            "NSE/Nifty Indices official historical index reports/API for index values",
            "NSE/Nifty Indices official constituent/factsheet archives for Momentum 30 membership",
            "Licensed third-party historical constituent ledger with effective dates",
        ],
        "no_fake_result_rule": "Do not mark the strategy as validated until these files exist and the script reports OK statuses.",
    }
    if OFFICIAL_CONSTITUENTS.exists():
        c = load_constituents(OFFICIAL_CONSTITUENTS)
        counts = [len(v) for v in c.values()]
        out["constituent_prediction"] = {
            "status": "OK_OFFICIAL_CONSTITUENTS_LOADED",
            "rebalance_dates": len(c),
            "min_count": min(counts) if counts else 0,
            "max_count": max(counts) if counts else 0,
            "next_required_step": "Compare shadow top30 as-of each prior prediction date against these future official sets.",
        }
    if OFFICIAL_RETURNS.exists():
        out["official_return_benchmark"] = benchmark_returns(OFFICIAL_RETURNS)
    if out["constituent_prediction"].get("status", "").startswith("OK") and out["official_return_benchmark"].get("status", "").startswith("OK"):
        out["status"] = "OK_READY_FOR_WALK_FORWARD_VALIDATION"
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    DOCS_OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(out["status"])
    print(out["constituent_prediction"]["status"], out["official_return_benchmark"]["status"])


if __name__ == "__main__":
    main()
