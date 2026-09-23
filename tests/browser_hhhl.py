"""Browser check for the dated HH/HL scanner."""
import argparse
import csv
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://localhost:3219/hhhl.html")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
data = json.loads((root/"public/data/hhhl_scan.json").read_text())
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width":1440,"height":1080}, accept_downloads=True)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(args.url, wait_until="networkidle")
    page.wait_for_function("document.querySelectorAll('#stock-rows tr').length === 200")
    assert page.locator("#count-ALL").inner_text() == "200"
    assert "199 complete" in page.locator("#coverage").inner_text()
    assert page.locator("#market-gate").inner_text() == "BLOCKED"
    assert "2026-09-22" in page.locator("#market-note").inner_text()
    for state, count in data["counts"].items():
        page.locator('[data-status="'+state+'"]').click()
        assert page.locator("#stock-rows tr[data-symbol]").count() == count
    page.locator('[data-status="BUY"]').click()
    assert "No stocks match" in page.locator("#stock-rows").inner_text()
    assert "blocked" in page.locator("#stock-rows").inner_text()
    page.locator("#reset").click()
    sector = data["rows"][0]["sector"]
    page.locator("#sector").select_option(sector)
    assert page.locator("#stock-rows tr[data-symbol]").count() == sum(r["sector"]==sector for r in data["rows"])
    page.locator("#reset").click()
    page.locator("#structure").select_option("HH / HL")
    assert page.locator("#stock-rows tr[data-symbol]").count() == sum(r["structure"]=="HH / HL" for r in data["rows"])
    page.locator("#reset").click()
    with page.expect_download() as event:
        page.locator("#download-csv").click()
    path=root/"artifacts/hhhl-export.csv"
    event.value.save_as(str(path))
    with path.open(encoding="utf-8-sig", newline="") as handle:
        exported=list(csv.DictReader(handle))
    assert len(exported)==200 and len({r["Symbol"] for r in exported})==200
    assert all(r["Snapshot date"]=="2026-09-23" for r in exported)
    page.locator("#search").fill("ICICIAMC")
    assert page.locator("#stock-rows tr[data-symbol]").count()==1
    page.locator('button[data-symbol="ICICIAMC"]').click()
    assert "Zones are withheld" in page.locator("#zone-panel").inner_text()
    assert "22 Sept 2026" in page.locator("#detail-subtitle").inner_text() or "22 Sep 2026" in page.locator("#detail-subtitle").inner_text()
    page.locator("#search").fill("APOLLOHOSP")
    page.locator('button[data-symbol="APOLLOHOSP"]').click()
    assert page.locator("#stock-chart svg").count()==1
    assert "BLOCKED" in page.locator("#zone-panel").inner_text()
    assert "9,024.00" in page.locator("#zone-panel").inner_text()
    assert "8,672.50" in page.locator("#zone-panel").inner_text()
    page.screenshot(path=str(root/"artifacts/hhhl-desktop-detail.png"), full_page=True)
    page.locator("#reset").click()
    page.evaluate("window.scrollTo(0,0)")
    page.screenshot(path=str(root/"artifacts/hhhl-desktop.png"), full_page=True)
    page.set_viewport_size({"width":390,"height":844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.locator('[data-status="WATCH"]').click()
    assert page.locator("#stock-rows tr[data-symbol]").count()==data["counts"]["WATCH"]
    page.screenshot(path=str(root/"artifacts/hhhl-mobile.png"), full_page=True)
    page.route("**/hhhl_scan.json", lambda route: route.fulfill(status=503, body="unavailable"))
    page.reload(wait_until="networkidle")
    assert "could not be loaded" in page.locator("#notice").inner_text()
    assert page.locator("#stock-rows tr").count()==0
    assert page.locator("#download-csv").is_disabled()
    assert not errors, errors
    browser.close()
print("PASS: 200 rows; five state filters; market block; search/sector/structure; chart and zones; stale stock; 200-row CSV; mobile; fetch failure; no JS errors.")
