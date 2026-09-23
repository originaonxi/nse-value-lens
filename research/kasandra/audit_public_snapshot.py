"""Audit public Kasandra snapshots; no signal generation or broker execution."""
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path


def utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value else None


def read_snapshot(path):
    raw = path.read_bytes()
    return json.loads(raw), {
        "local_file": path.as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "file_modified_utc": utc(path.stat().st_mtime),
    }


def gold_ledger(snapshot, trades):
    if snapshot.get("sym") != "XAUUSD.s":
        raise ValueError("This accounting audit is for the public Gold Zones snapshot.")
    runs = {(r["z"], r["t0"]): r for r in snapshot["runs"]}
    if len(runs) != len(snapshot["runs"]):
        raise ValueError("Duplicate runner identifiers; cannot safely reconcile.")
    base = runner = 0.0
    closed = positive_base = unresolved = 0
    for trade in trades:
        if trade["open"]:
            unresolved += 1
            continue
        closed += 1
        base += trade["pnl"]
        positive_base += trade["pnl"] > 0
        if trade.get("runT0") is not None:
            key = (trade["z"], trade["runT0"])
            if key not in runs:
                raise ValueError("A trade's runner is missing from the snapshot.")
            run = runs[key]
            if run["open"]:
                unresolved += 1
            else:
                runner += run["pnl"]
    spread = snapshot["profile"]["spread"] * snapshot["profile"]["pip"]
    return {
        "signals": len(trades),
        "closed_base_trades": closed,
        "positive_base_trades": positive_base,
        "unresolved_positions_or_runners": unresolved,
        "base_realized_price_units": round(base, 6),
        "runner_realized_price_units": round(runner, 6),
        "combined_realized_price_units": round(base + runner, 6),
        "profile_spread_price_units_per_entry": spread,
        "spread_allowance_price_units": round(closed * spread, 6),
        "realized_after_profile_spread_price_units": round(base + runner - closed * spread, 6),
        "units": "gold quote-price movement per initial position unit; not account cash or percentage return",
        "cost_scope": "Replicates the public demo's one profile spread allowance per closed base trade; no slippage, commission or financing.",
    }


def audit(record_path, demo_path):
    record, record_meta = read_snapshot(record_path)
    demo, demo_meta = read_snapshot(demo_path)
    if record.get("ok") is not True or demo.get("demo") is not True:
        raise ValueError("Expected successful public record and explicitly marked public demo.")
    engines = []
    for engine in record["engines"]:
        if engine.get("error"):
            engines.append({"key": engine["key"], "error": engine["error"]})
            continue
        if engine["wins"] + engine["losses"] + engine.get("flat", 0) != engine["closed"]:
            raise ValueError("Reported closed counts do not reconcile.")
        rows = engine["trades"]
        engines.append({
            "key": engine["key"], "name": engine["name"], "version": engine["version"],
            "since_timestamp_as_supplied": engine["since"],
            "since_date_from_epoch": utc(engine["since"])[:10],
            "reported_closed": engine["closed"], "reported_wins": engine["wins"],
            "reported_losses": engine["losses"],
            "reported_win_rate_pct": round(100 * engine["wins"] / engine["closed"], 2) if engine["closed"] else None,
            "reported_net": engine["net"], "reported_unit": engine["unit"],
            "reported_open": engine["open"], "visible_rows": len(rows),
            "visible_rows_cover_reported_count": len(rows) == engine["closed"],
        })
    gold = next(e for e in record["engines"] if e["key"] == "XAUUSD.s")
    matched = [t for t in demo["trades"] if t.get("t1") and gold["since"] <= t["t1"] <= gold["last"]]
    window = gold_ledger(demo, matched)
    count_matches = window["closed_base_trades"] == gold["closed"]
    subtotal_matches = math.isclose(window["base_realized_price_units"], gold["net"], abs_tol=0.051)
    return {
        "reviewed_on": "2026-09-23",
        "status": "public_output_accounting_review_not_independent_strategy_backtest",
        "sources": {
            "home": "https://kasandra-scanner.com/",
            "guide": "https://kasandra-scanner.com/guide.html",
            "track_record": "https://kasandra-scanner.com/track.html",
            "public_record_json": "https://kasandra-scanner.com/api/record",
            "demo": "https://app.kasandra-scanner.com/demo",
            "demo_snapshot": "https://app.kasandra-scanner.com/api/demo?sym=XAUUSD.s&tf=15&n=3000",
        },
        "provenance": {"record": record_meta, "demo": demo_meta},
        "record_response_at_utc": utc(record["at"]),
        "demo_delay_seconds": demo["delay"],
        "demo_version": demo["v"],
        "engines_as_reported": engines,
        "gold_loaded_demo_ledger": gold_ledger(demo, demo["trades"]),
        "gold_record_window_reconstruction": window,
        "reconciliation": {
            "gold_closed_count_matches": count_matches,
            "gold_reported_net_matches_base_subtotal_with_rounding": subtotal_matches,
            "interpretation": "If both checks match, the reported gold net agrees with the base-trade subtotal before linked runners and the demo spread formula. This does not establish what costs may be embedded in the vendor's supplied fills.",
        },
        "limitations": [
            "Rules and filters remain server-side; no exact algorithm was copied or independently backtested.",
            "Public output is vendor-supplied and is not independently verified broker execution.",
            "Short version-specific records cannot establish a durable edge; Bitcoin Dip has only four closed trades in this snapshot.",
            "Gold and Dow public record lists are capped at 40 visible rows, below their reported totals.",
            "Some site pips labels differ from the demo profile's quote-price/pip conversion; retain reported units and do not interpret them as cash returns.",
            "Event clocks require normalization: instrument metadata reports a server offset of 180 minutes.",
            "The homepage advertises Gold Scalp 5, but this public record response contains Dow Zones instead.",
            "No NSE instruments, historical NSE membership or NSE execution costs were tested.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, default=Path("artifacts/kasandra_record.json"))
    parser.add_argument("--demo", type=Path, default=Path("artifacts/kasandra_demo_snapshot.json"))
    parser.add_argument("--output", type=Path, default=Path("data/kasandra_public_review.json"))
    args = parser.parse_args()
    result = audit(args.record, args.demo)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "engines": len(result["engines_as_reported"]),
        "gold_closed": result["gold_loaded_demo_ledger"]["closed_base_trades"],
        "gold_after_spread_price_units": result["gold_loaded_demo_ledger"]["realized_after_profile_spread_price_units"],
        "reconciliation": result["reconciliation"],
    }, ensure_ascii=True))


if __name__ == "__main__":
    main()
