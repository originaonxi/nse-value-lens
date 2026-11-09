"""Check the Nifty chain page against a served snapshot or a local JSON file.

Usage:
  py -3 tests/browser_nifty_chain.py --url http://127.0.0.1:8765/nifty-chain.html [--data docs/nifty_chain.json]
"""
import argparse
import copy
import json
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import expect, sync_playwright


def strike_window(expiry, spot, width):
    rows = expiry["rows"]
    centre = min(range(len(rows)), key=lambda i: abs(rows[i]["strike"] - spot))
    return rows[max(0, centre - width): centre + width + 1]


def verify(page, data):
    """Checks the page as it is built today (nifty-chain.html / nifty-chain.js), against the published snapshot."""
    expect(page.locator("body")).to_have_attribute("data-ready", "true", timeout=30000)
    sd = page.locator("#session-date").inner_text().strip()
    assert sd not in ("", "—", "Loading…"), "session date missing"
    assert "constituents" in page.locator("#coverage").inner_text(), "coverage line missing"

    # 1. market snapshot: Nifty spot shown as published (integer, as the page formats it)
    idx = data["index"]
    spot = idx.get("option_spot") or idx["close"]
    cards = page.locator("#market-cards").inner_text().replace(",", "")
    assert str(round(spot)) in cards, ("Nifty spot not shown", round(spot), cards[:200])

    # 2. ranked setup feed
    n_setups = page.locator("#setup-cards .nc-setup-card").count()
    assert n_setups > 0, "no setup cards"

    # 3. option chain: every expiry selectable, one ATM row, sigma cards and OI chart drawn
    page.locator("#section-chain summary").click()
    expect(page.locator("#expiry-select option")).to_have_count(len(data["expiries"]))
    for e in data["expiries"][:3]:
        page.locator("#expiry-select").select_option(e["expiry"])
        expect(page.locator("#chain-table-wrap tr.nc-atm")).to_have_count(1)
        assert page.locator("#chain-table-wrap tbody tr").count() > 5, e["expiry"]
    assert page.locator("#oi-chart-wrap svg").count() >= 1, "OI chart missing"
    assert page.locator("#hhhl-chart svg").count() >= 1, "HH/HL chart missing"

    # 4. rules evidence
    page.locator("#section-rules summary").click()
    if data["rules"]:
        expect(page.locator("#rules-wrap tbody tr")).to_have_count(len(data["rules"]))

    # 5. constituents: count, filters, search
    total = data["constituents_count"]
    page.locator("#section-constituents summary").click()
    rows = "#constituents-wrap tbody tr"
    expect(page.locator(rows)).to_have_count(total)
    assert page.locator("#const-count").inner_text().strip() == f"{total} of {total} constituents"
    for status in ("BUY", "WATCH", "SELL", "CAUTION", "AVOID"):
        page.locator("#const-status").select_option(status)
        expect(page.locator(rows)).to_have_count(sum(c.get("hhhl_status") == status for c in data["constituents"]))
    page.locator("#const-status").select_option("")
    sym = data["constituents"][0]["symbol"]
    page.locator("#const-search").fill(sym)
    expect(page.locator(rows)).to_have_count(sum(sym.lower() in (c["symbol"] or "").lower() for c in data["constituents"]))
    page.locator("#const-search").fill("")
    expect(page.locator(rows)).to_have_count(total)

    # 6. links and nothing broken anywhere
    bad = page.evaluate("""() => [...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href'))
        .filter(h => !/^(https?:|[a-z0-9-]+\\.html|#)/i.test(h))""")
    assert not bad, ("unexpected link targets", bad[:5])
    html = page.locator("main").inner_html() if page.locator("main").count() else page.locator("body").inner_html()
    for token in ("NaN", "undefined", "[object Object]", "Infinity"):
        assert token not in html, f"{token} found in rendered HTML"


def run(url, data_path=None, live_json=None):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        if data_path:
            body = Path(data_path).read_text(encoding="utf-8")
            data = json.loads(body)
            page.route("**/nifty_chain.json*", lambda route: route.fulfill(status=200, content_type="application/json", body=body))
        else:
            resp = ctx.request.get(urljoin(url, "nifty_chain.json"))
            assert resp.ok, f"nifty_chain.json HTTP {resp.status}"
            data = resp.json()
        page.goto(url)
        verify(page, data)
        assert not errors, errors
        # invalid snapshot must show a visible error instead of the page
        broken = copy.deepcopy(data)
        broken["constituents_count"] = broken["constituents_count"] + 1
        bad = ctx.new_page()
        bad.route("**/nifty_chain.json*", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(broken)))
        bad.goto(url)
        expect(bad.locator("body")).to_have_attribute("data-ready", "error", timeout=30000)
        expect(bad.locator("#notice")).to_contain_text("constituents_count mismatch")
        assert bad.locator("#notice").is_visible()
        browser.close()
    print(f"nifty chain page OK: {data['as_of']}, {len(data['expiries'])} expiries, {data['constituents_count']} constituents, "
          f"{len(data['rules'])} rules, {len(data['setups'])} setups today, jev {data['jev'].get('state')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--data")
    a = ap.parse_args()
    run(a.url, a.data)
