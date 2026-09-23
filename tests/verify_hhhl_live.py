"""Real published-site checks, executed after every automated Pages deployment."""
import argparse
from collections import Counter
import json
from pathlib import Path
import time
import requests
from playwright.sync_api import sync_playwright

SITES = [
    ("pages", "https://originaonxi.github.io/nse-value-lens/", ""),
    ("railway", "https://nifty.up.railway.app/", "data/"),
]


def validate(scan, status, run_id):
    assert str(status["run_id"]) == str(run_id), "Refresh status has not reached the website"
    assert status["state"] in ("fresh", "partial", "waiting"), "Refresh failed"
    assert scan["as_of"] == status["scan_as_of"]
    assert scan["generated_at"] == status["snapshot_generated_at"], "Snapshot/status publication mismatch"
    assert scan["universe_count"] == len(scan["rows"]) == 200
    assert len({r["symbol"] for r in scan["rows"]}) == 200
    counts = Counter(r["status"] for r in scan["rows"])
    assert all(counts[s] == scan["counts"][s] for s in scan["counts"])
    for row in scan["rows"]:
        assert row["as_of"] == scan["as_of"]
        assert not row["data_date"] or row["data_date"] <= scan["as_of"]
        if row["status"] == "BUY":
            assert row["complete_for_session"] and row["fresh_breakout"] and row["entry_allowed"]
            assert scan["market"]["new_entries_allowed"]
        if not row["complete_for_session"]:
            assert row["status"] == "CAUTION" and not row["zones"]
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--timeout", type=int, default=360)
    args = parser.parse_args()
    out = Path("artifacts")
    out.mkdir(exist_ok=True)
    report = {"run_id": args.run_id, "sites": []}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, base, source in SITES:
            deadline = time.monotonic() + args.timeout
            while True:
                try:
                    stamp = str(time.time_ns())
                    response = requests.get(base+source+"hhhl_refresh_status.json?v="+stamp, timeout=20)
                    response.raise_for_status()
                    status = response.json()
                    response = requests.get(base+source+"hhhl_scan.json?v="+stamp, timeout=20)
                    response.raise_for_status()
                    scan = response.json()
                    validate(scan, status, args.run_id)
                    break
                except (AssertionError, requests.RequestException, ValueError) as exc:
                    if time.monotonic() >= deadline:
                        raise RuntimeError(name+": "+str(exc)) from exc
                    print(name+": awaiting published snapshot/status", flush=True)
                    time.sleep(10)
            page = browser.new_page(viewport={"width": 1440, "height": 1100}, accept_downloads=True)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base+"hhhl.html?test="+args.run_id, wait_until="networkidle")
            page.wait_for_function("document.querySelector('#count-ALL').textContent === '200'")
            page.wait_for_function("document.querySelector('#refresh-status').dataset.runId === "+json.dumps(args.run_id))
            assert page.locator("#stock-rows tr[data-symbol]").count() == 200
            for state, count in scan["counts"].items():
                page.locator('[data-status="'+state+'"]').click()
                assert page.locator("#stock-rows tr[data-symbol]").count() == count
            page.locator('[data-status="ALL"]').click()
            symbol = scan["rows"][0]["symbol"]
            page.locator("#search").fill(symbol)
            page.locator('button.stock-name[data-symbol="'+symbol+'"]').click()
            assert page.locator("#stock-detail").is_visible()
            page.locator("#reset").click()
            with page.expect_download() as download:
                page.locator("#download-csv").click()
            import csv
            saved = out/("hhhl-live-"+name+".csv")
            download.value.save_as(saved)
            assert len(list(csv.DictReader(saved.open(encoding="utf-8-sig")))) == 200
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
            page.screenshot(path=str(out/("hhhl-live-"+name+".png")))
            assert not errors, errors
            report["sites"].append({"site": name, "url": base+"hhhl.html", "state": status["state"],
                                    "as_of": scan["as_of"], "complete": scan["complete_count"],
                                    "all_200_rows": True, "all_five_filters": True,
                                    "csv_rows": 200, "mobile": True, "js_errors": errors})
            page.close()
        browser.close()
    (out/"hhhl-live-report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
