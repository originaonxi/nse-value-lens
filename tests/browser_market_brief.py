"""Browser verification against local or deployed brief and scanner pages."""
import argparse
import json
from pathlib import Path
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width":1440,"height":1050})
        errors = []
        page.on("pageerror", lambda error:errors.append(str(error)))
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_function("document.querySelectorAll('#brief-stock-rows tr').length===200", timeout=30000)
        source = page.locator("body").get_attribute("data-source") or ""
        snapshot = page.request.get(urljoin(args.url, source + "market_brief.json")).json()
        status = page.request.get(urljoin(args.url, source + "market_brief_refresh_status.json")).json()
        assert snapshot["judged_count"] == 200, snapshot["audit"]["errors"]
        assert status["state"] in ("fresh","partial"), status["message"]
        assert status["snapshot_id"] == snapshot["id"]
        if args.run_id:
            assert status["run_id"] == args.run_id, (status["run_id"],args.run_id)
        assert "apikey_" not in json.dumps(snapshot), "Credential-shaped value in public data"
        symbol = snapshot["rows"][0]["symbol"]
        page.locator("#brief-search").fill(symbol)
        assert page.locator("#brief-stock-rows tr").count() >= 1
        page.locator(f'button[data-symbol="{symbol}"]').first.click()
        assert symbol in page.locator("#brief-stock-detail").inner_text()
        for context in ("supportive","conflicting","mixed","insufficient"):
            page.locator("#brief-reset").click()
            page.locator("#brief-context").select_option(context)
            assert page.locator("#brief-stock-rows tr").count() == sum(r["context"] == context for r in snapshot["rows"])
        page.locator("#brief-reset").click()
        for value, expected in (("HHHL",sum(r["hhhl_eligible"] for r in snapshot["rows"])),("VCP",sum(r["vcp"] == "WATCH" and r["vcp_ready"] for r in snapshot["rows"]))):
            page.locator("#brief-setup").select_option(value)
            assert page.locator("#brief-stock-rows tr").count() == expected
        page.locator("#brief-reset").click()
        artifacts = Path("artifacts");artifacts.mkdir(exist_ok=True)
        page.screenshot(path=str(artifacts / "market-desktop.png"), full_page=True)
        page.set_viewport_size({"width":390,"height":844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "Mobile page overflow"
        page.screenshot(path=str(artifacts / "market-mobile.png"), full_page=True)
        for name in ("hhhl","vcp"):
            page.goto(urljoin(args.url, name + ".html?symbol=" + symbol), wait_until="networkidle")
            page.wait_for_function("document.querySelector('#market-context-stock') && !document.querySelector('#market-context-stock').hidden", timeout=30000)
            assert symbol in page.locator("#detail-title").inner_text()
            assert "context" in page.locator("#market-context-stock").inner_text().lower()
        for width in (1440,390,320):
            page.set_viewport_size({"width":width,"height":900})
            page.goto(urljoin(args.url, "index.html"),wait_until="networkidle")
            for target in ("hhhl.html","vcp.html","market-brief.html"):
                assert page.locator(f'.home-tools a[href="{target}"]').is_visible()
                assert page.locator(f'.home-primary-nav a[href="{target}"]').is_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "Homepage overflow"
            if width in (1440,390):page.screenshot(path=str(artifacts / f"market-home-{width}.png"))
        assert not errors, errors
        print(json.dumps({"url":args.url,"judged":snapshot["judged_count"],"as_of":snapshot["as_of"],"state":status["state"],"run_id":status["run_id"],"browser_errors":errors}))
        browser.close()


if __name__ == "__main__":main()
