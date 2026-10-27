#!/usr/bin/env python3
"""Check local/generated or published setups against their dated source files.

--inputs-only --require-jev is the pre-publication gate: all core stocks must
have same-session Jev scores. It never relabels data or calls the Jev API.
"""
import argparse
import json
import math
import time
from pathlib import Path
from urllib.request import Request, urlopen

DOCS = Path(__file__).resolve().parents[1] / "docs"


def validate_inputs(scan, jev, require_jev=False):
    day = scan.get("as_of")
    rows = scan.get("rows") or []
    core = {r["symbol"] for r in rows}
    assert day and len(core) == len(rows) == 200, "HHHL must contain exactly 200 unique core stocks"
    if require_jev:
        ranks = jev.get("ranking") or []
        assert jev.get("as_of") == day, f"Waiting for Jev {day}: source is {jev.get('as_of')}"
        assert len(ranks) == len(core) == jev.get("judged") == jev.get("of_universe"), "Waiting for complete Jev coverage"
        assert {r["symbol"] for r in ranks} == core, "Jev coverage differs from the HHHL universe"
        assert all(isinstance(r.get("composite"), (int, float)) and math.isfinite(r["composite"])
                   and 0 <= r["composite"] <= 1 for r in ranks), "Jev has invalid/missing scores"
        assert all(all(r.get(k) in (None, day) for k in ("as_of", "data_date")) for r in ranks), "Jev contains stale per-stock assessments"
    return day


def validate_snapshot(data, scan, fno, jev, series, require_jev=False):
    day = validate_inputs(scan, jev, require_jev)
    assert data.get("as_of") == day == series.get("as_of"), "List, chart series and price scan dates differ"
    assert data.get("generated_at"), "Missing generation timestamp"
    inputs = data.get("inputs") or {}
    assert inputs.get("hhhl_scan") == day, "Wrong HHHL provenance"
    assert inputs.get("hhhl_fno") == fno.get("as_of"), "F&O source changed; rebuild the list"
    assert inputs.get("jev_rank") == jev.get("as_of"), "Jev source changed; rebuild the list"
    sources = {r["symbol"]: r for r in fno.get("rows", [])}
    sources.update({r["symbol"]: r for r in scan["rows"]})  # core takes precedence
    stocks = data.get("stocks") or []
    by_symbol = {s["symbol"]: s for s in stocks}
    assert len(stocks) == len(by_symbol) == data.get("universe_count"), "Duplicate/wrong universe count"
    assert set(by_symbol) == set(sources), "List does not cover its source universe"
    ranked = set()
    jev_by_symbol = {r["symbol"]: r for r in jev.get("ranking") or []} if jev.get("as_of") == day else {}
    for sym, s in by_symbol.items():
        src = sources[sym]
        assert s.get("data_date") == src.get("data_date"), f"{sym}: price date was relabelled"
        assert s.get("close") == src.get("close"), f"{sym}: close differs from source"
        if src.get("data_date") != day:
            assert s["category"] == "data_check" and not s.get("rank") and not s.get("plan"), f"{sym}: stale price ranked"
        j = s.get("jev") or {}
        if j.get("composite") is not None:
            assert sym in jev_by_symbol and j["composite"] == jev_by_symbol[sym]["composite"], f"{sym}: stale/wrong Jev score"
        r = s.get("rank")
        if not r:
            assert s["category"] == "data_check", f"{sym}: eligible stock missing ranks"
            continue
        ranked.add(sym)
        assert s["category"] != "data_check", f"{sym}: invalid data ranked"
        assert abs(r["bull"] - sum(f["bull"] for f in r["factors"])) <= 0.11, f"{sym}: bull factor total"
        assert abs(r["bear"] - sum(f["bear"] for f in r["factors"])) <= 0.11, f"{sym}: bear factor total"
        assert abs(r["net"] - (r["bull"] - r["bear"])) <= 0.11, f"{sym}: net score"
        assert sym in series.get("series", {}), f"{sym}: no chart series"
    lists = (data.get("ranking") or {}).get("lists") or {}
    assert set(lists) == {"buy", "sell", "watch"}, "Missing ranked lists"
    listed = []
    for key, block in lists.items():
        order = block["chart_order"]
        listed.extend(order)
        assert block["count"] == len(order), f"{key}: count mismatch"
        assert len(set(order)) == len(order), f"{key}: duplicate symbols"
        assert set(order) == set(block["combined_order"]), f"{key}: combined coverage"
        expected_jev = {sym for sym in order if by_symbol[sym].get("jev", {}).get("composite") is not None}
        assert set(block["jev_order"]) == expected_jev and len(block["jev_order"]) == block["jev_count"], f"{key}: Jev coverage"
        for field, rank_field in (("chart_order", "chart_rank"), ("jev_order", "jev_rank"), ("combined_order", "combined_rank")):
            for i, sym in enumerate(block[field], 1):
                r = by_symbol[sym]["rank"]
                assert r["list"] == key and r[rank_field] == i, f"{sym}: incorrect {rank_field}"
        nets = [by_symbol[sym]["rank"]["net"] for sym in order]
        want = sorted(nets, reverse=True) if key == "buy" else sorted(nets) if key == "sell" else sorted(nets, key=abs, reverse=True)
        assert nets == want, f"{key}: chart order"
        final = block.get("final_order")
        if final is not None:  # Jev-first ranking (score out of 100)
            assert sorted(final) == sorted(order), f"{key}: final order coverage"
            scored = [sym for sym in final if by_symbol[sym]["rank"].get("jev")]
            assert final[:len(scored)] == scored == block["jev_order"], f"{key}: Jev-scored stocks must lead, in Jev order"
            assert final[len(scored):] == [sym for sym in order if sym not in set(scored)], f"{key}: unscored tail must follow chart order"
            assert block.get("not_jev_count") == len(final) - len(scored), f"{key}: not-Jev count"
            prev = None
            for i, sym in enumerate(final, 1):
                r = by_symbol[sym]["rank"]
                assert r.get("final_rank") == i, f"{sym}: incorrect final_rank"
                jb = r.get("jev")
                if not jb:
                    continue
                j = by_symbol[sym]["jev"]
                pts = jb.get("points") or []
                assert [p["key"] for p in pts] == ["setup_quality", "follow_through", "risk_reward"] and sum(p["weight"] for p in pts) == 100, f"{sym}: Jev weights"
                for p in pts:
                    assert p["level"] == round(float(j[p["key"]]), 2) and 0 <= p["level"] <= p["max_level"] == 4, f"{sym}: Jev level {p['key']}"
                    assert abs(p["points"] - p["weight"] * float(j[p["key"]]) / 4) <= 0.006, f"{sym}: Jev points {p['key']}"
                assert abs(jb["score"] - sum(p["points"] for p in pts)) <= 0.051, f"{sym}: Jev score is not the sum of its points"
                assert abs(jb["score"] - j["composite"] * 100) <= 0.1, f"{sym}: Jev score differs from Jev composite x 100"
                assert 0 <= jb["score"] <= 100, f"{sym}: Jev score outside 0-100"
                want_list = round(100 - jb["score"], 1) if key == "sell" else jb["score"]
                assert abs(jb["list_score"] - want_list) <= 0.051, f"{sym}: Jev list score"
                assert prev is None or jb["list_score"] <= prev + 1e-9, f"{key}: Jev order is not highest list score first"
                prev = jb["list_score"]
    acct = (data.get("ranking") or {}).get("accounting")
    if acct is not None:
        unranked = {u["symbol"] for u in acct["unranked"]}
        assert unranked == set(by_symbol) - ranked, "Accounting: unranked stocks differ"
        assert acct["total"] == len(stocks) == acct["ranked"] + len(unranked), "Accounting: totals do not add up"
        assert acct["ranked"] == len(ranked) and acct["jev_scored"] == sum(b["jev_count"] for b in lists.values()), "Accounting: ranked / Jev counts"
        assert sum(u["total"] for u in acct["by_universe"].values()) == len(stocks), "Accounting: universe totals"
    assert len(listed) == len(set(listed)) and set(listed) == ranked, "Ranked universe mismatch"
    return f"daily setups verified: {day}, {len(stocks)} stocks, {len(ranked)} ranked; source dates, prices, Jev provenance and Jev /100 maths match"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", help="Published site root; omit to check local docs")
    p.add_argument("--timeout", type=float, default=0, help="Seconds to retry a live publication")
    p.add_argument("--inputs-only", action="store_true")
    p.add_argument("--require-jev", action="store_true")
    args = p.parse_args()
    deadline = time.monotonic() + args.timeout

    def load(name):
        if not args.url:
            path = DOCS / name
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        url = args.url.rstrip("/") + "/" + name + "?verify=" + str(time.time_ns())
        with urlopen(Request(url, headers={"Cache-Control": "no-cache"}), timeout=25) as resp:
            return json.load(resp)

    while True:
        try:
            scan, jev = load("hhhl_scan.json"), load("jev_rank.json")
            if args.inputs_only:
                day = validate_inputs(scan, jev, args.require_jev)
                print(f"Daily setups inputs ready for {day}")
            else:
                print(validate_snapshot(load("daily_setups.json"), scan, load("hhhl_fno.json"), jev,
                                        load("daily_setups_series.json"), args.require_jev))
            return
        except (AssertionError, OSError, ValueError, KeyError, TypeError) as exc:
            if not args.url or time.monotonic() >= deadline:
                raise SystemExit(f"Daily setups verification failed: {exc}") from exc
            print(f"Waiting for consistent published snapshot: {exc}", flush=True)
            time.sleep(min(10, max(0, deadline - time.monotonic())))


if __name__ == "__main__":
    main()
