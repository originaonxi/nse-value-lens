#!/usr/bin/env python3
"""Point-in-time Nifty 200 universe snapshot builder.

This is the anti-survivorship gate for the Momentum 30 project. It refuses to
pretend that today's Nifty 200 list is valid historical membership. If a clean
constituent-event ledger is provided, it reconstructs snapshots. If not, it
writes a BLOCKED manifest explaining exactly what data is missing.

Optional input files:
  data/nifty200_base_universe.csv
      columns: symbol[, name]
  data/nifty200_constituent_events.csv
      columns: effective_date, additions, removals
      additions/removals: comma/semicolon/pipe separated NSE symbols
"""
from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "screen_output" / "universe_snapshots.json"
DOCS_OUT = ROOT / "docs" / "universe_snapshots.json"
CURRENT_UNIVERSE = ROOT / "nifty200.csv"
BASE_UNIVERSE = DATA / "nifty200_base_universe.csv"
EVENTS = DATA / "nifty200_constituent_events.csv"


def split_symbols(text: str) -> list[str]:
    if not text:
        return []
    return [x.strip().upper() for x in re.split(r"[,;|]\s*", text) if x.strip()]


def read_symbol_csv(path: Path) -> set[str]:
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8-sig")))
    syms = set()
    for r in rows:
        sym = (r.get("symbol") or r.get("Symbol") or r.get("SYMBOL") or "").strip().upper()
        if sym:
            syms.add(sym)
    return syms


def blocked_manifest() -> dict:
    current = sorted(read_symbol_csv(CURRENT_UNIVERSE)) if CURRENT_UNIVERSE.exists() else []
    return {
        "status": "BLOCKED_MISSING_POINT_IN_TIME_DATA",
        "as_of": date.today().isoformat(),
        "reason": "Historical Nifty 200 membership cannot be reconstructed from today's constituents without survivorship bias.",
        "why_this_matters": "A stock that is in Nifty 200 today may not have been eligible in past years; delisted/removed stocks must remain in old universes or the model cheats.",
        "acceptable_sources": [
            "NSE Indices historical constituent reports / archives",
            "A paid/clean constituent ledger such as niftyhistory.in if licensed for this use",
            "Own audited event ledger of Nifty 200 inclusions/exclusions with effective dates",
        ],
        "required_files": {
            str(BASE_UNIVERSE.relative_to(ROOT)): "starting point-in-time Nifty 200 symbols at first backtest date",
            str(EVENTS.relative_to(ROOT)): "effective_date, additions, removals event ledger",
        },
        "fallback_current_survivor_snapshot": {
            "label": "NOT_FOR_CLAIMS",
            "symbols": current,
            "count": len(current),
        },
    }


def build_snapshots() -> dict:
    if not BASE_UNIVERSE.exists() or not EVENTS.exists():
        return blocked_manifest()
    universe = read_symbol_csv(BASE_UNIVERSE)
    rows = list(csv.DictReader(EVENTS.open(newline="", encoding="utf-8-sig")))
    rows.sort(key=lambda r: r.get("effective_date") or r.get("date") or "")
    snapshots = []
    for r in rows:
        d = r.get("effective_date") or r.get("date")
        adds = split_symbols(r.get("additions") or r.get("added") or "")
        rems = split_symbols(r.get("removals") or r.get("removed") or "")
        for sym in rems:
            universe.discard(sym)
        for sym in adds:
            universe.add(sym)
        snapshots.append({
            "effective_date": d,
            "count": len(universe),
            "additions": adds,
            "removals": rems,
            "symbols": sorted(universe),
        })
    return {
        "status": "OK_POINT_IN_TIME_SNAPSHOTS_BUILT",
        "as_of": date.today().isoformat(),
        "base_file": str(BASE_UNIVERSE.relative_to(ROOT)),
        "events_file": str(EVENTS.relative_to(ROOT)),
        "snapshots": snapshots,
        "snapshot_count": len(snapshots),
        "latest_count": len(universe),
    }


def main() -> None:
    out = build_snapshots()
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    DOCS_OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(out["status"])
    if out["status"].startswith("BLOCKED"):
        print(out["reason"])
    else:
        print(f"snapshots={out['snapshot_count']} latest_count={out['latest_count']}")


if __name__ == "__main__":
    main()
