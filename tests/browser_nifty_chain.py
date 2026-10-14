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
    expect(page.locator("body")).to_have_attribute("data-ready", "true", timeout=30000)
    assert page.locator("#session-date").inner_text().strip() not in ("", "Loading…"), "session date missing"

    # 1. index cards: Nifty close shown as published
    cards = page.locator("#index-cards").inner_text()
    close = f"{data['index']['close']:,.2f}"
    assert any(close.replace(",", "") in t.replace(",", "") for t in [cards]), ("Nifty close not shown", close)

    # 2. option chain: default expiry is the trade expiry, +/-20 strikes, Greeks rendered
    spot = data["index"]["option_spot"]
    trade = next((e for e in data["expiries"] if e["trade_expiry"]), data["expiries"][0])
    assert page.locator("#expiry").input_value() == trade["expiry"]
    expect(page.locator("#chain-rows tr[data-strike]")).to_have_count(len(strike_window(trade, spot, 20)))
    atm = page.locator(f'#chain-rows tr[data-strike="{trade["atm"]:g}"]')
    if atm.count() == 0:
        atm = page.locator("#chain-rows tr.nc-atm")
    expect(atm).to_have_count(1)
    cells = atm.locator("td").all_inner_texts()
    assert len(cells) == 19, len(cells)
    ce_delta, pe_delta = cells[4], cells[14]
    assert ce_delta not in ("--", "") and pe_delta.startswith("-"), (ce_delta, pe_delta)
    page.locator("#width").select_option("10")
    expect(page.locator("#chain-rows tr[data-strike]")).to_have_count(len(strike_window(trade, spot, 10)))
    for e in data["expiries"]:
        page.locator("#expiry").select_option(e["expiry"])
        expect(page.locator("#chain-rows tr[data-strike]")).to_have_count(len(strike_window(e, spot, 10)))
        assert f"{e['expected_move']:,.0f}".replace(",", "") in page.locator("#sigma-card").inner_text().replace(",", ""), e["expiry"]
        if e.get("oi_profile"):
            expect(page.locator("#oi-chart svg")).to_have_count(1)
    page.locator("#oi-mode").select_option("chg")
    expect(page.locator("#oi-chart svg")).to_have_count(1)
    page.locator("#oi-mode").select_option("oi")

    # 3. charts
    expect(page.locator("#vol-chart svg")).to_have_count(1)
    expect(page.locator("#hhhl-chart svg")).to_have_count(1)
    shown_swings = [s for s in data["hhhl"]["swings"] if s["pivot_date"] in set(data["hhhl"]["dates"])]
    expect(page.locator("#hhhl-chart text.swing")).to_have_count(len(shown_swings))
    expect(page.locator("#part-chart svg")).to_have_count(1)

    # 4. participants, setups, rules
    expect(page.locator("#participant-rows tr[data-participant]")).to_have_count(len(data["participants"] or []))
    expect(page.locator("#setup-cards .nc-setup")).to_have_count(len(data["setups"]))
    for s in data["setups"]:
        expect(page.locator(f'#setup-cards .nc-setup[data-rule="{s["rule"]}"] svg.nc-payoff')).to_have_count(1)
    expect(page.locator("#rule-rows tr[data-rule]")).to_have_count(len(data["rules"]))
    best = data["best_setup"]["label"]
    assert best in page.locator("#best-setup").inner_text(), best
    jev_text = page.locator("#jev-index").inner_text()
    if data["jev"].get("index"):
        assert "Direction" in jev_text and data["jev"]["index"]["direction"]["choice"].replace("_", " ") in jev_text.lower(), jev_text[:200]
    else:
        assert "Jev not run" in jev_text

    # 5. constituents: count, filters, search, Jev, CSV
    total = data["constituents_count"]
    rows = "#constituent-rows tr[data-symbol]"
    expect(page.locator(rows)).to_have_count(total)
    assert page.locator("#const-count").inner_text().strip() == f"{total} of {total} constituents shown"
    for status in ("BUY", "WATCH", "SELL", "CAUTION", "AVOID"):
        page.locator("#const-status").select_option(status)
        expect(page.locator(rows)).to_have_count(sum(c["hhhl_status"] == status for c in data["constituents"]))
    page.locator("#const-status").select_option("ALL")
    for stance in ("bullish", "bearish", "neutral"):
        page.locator("#const-stance").select_option(stance)
        expect(page.locator(rows)).to_have_count(sum((c.get("jev") or {}).get("stance") == stance for c in data["constituents"]))
    page.locator("#const-stance").select_option("ALL")
    syms = [c["symbol"] for c in data["constituents"]]
    uniq = next(s for s in syms if not any(o != s and s.lower() in o.lower() for o in syms)
                and not any(s.lower() in (c["industry"] + c["name"]).lower() for c in data["constituents"] if c["symbol"] != s))
    page.locator("#const-search").fill(uniq)
    expect(page.locator(rows)).to_have_count(1)
    page.locator("#const-search").fill("")
    expect(page.locator(rows)).to_have_count(total)
    if data["jev"].get("state") == "ok":
        reviewed = sum(1 for c in data["constituents"] if c.get("jev"))
        assert reviewed == total, f"Jev reviewed {reviewed} of {total} constituents"
    with page.expect_download() as info:
        page.locator("#const-download").click()
    csv_text = Path(info.value.path()).read_text(encoding="utf-8")
    assert len(csv_text.strip().splitlines()) == total + 1, "CSV row count"

    # 6. research section
    research = data.get("research") or {}
    expect(page.locator("#institution-list .nc-research")).to_have_count(len(research.get("institutions", [])))
    expect(page.locator("#strategy-rows tr[data-strategy]")).to_have_count(len(research.get("strategies", [])))
    expect(page.locator("#github-rows tr")).to_have_count(len(research.get("github", [])))
    bad = page.evaluate("""() => [...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href'))
        .filter(h => !/^(https?:|[a-z0-9-]+\\.html)/i.test(h))""")
    assert not bad, ("unexpected link targets", bad[:5])

    # 7. nothing broken anywhere
    html = page.locator("body").inner_html()
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
        expect(bad.locator("#notice")).to_contain_text("could not be shown")
        assert not bad.locator("#constituent-rows").is_visible()
        browser.close()
    print(f"nifty chain page OK: {data['as_of']}, {len(data['expiries'])} expiries, {data['constituents_count']} constituents, "
          f"{len(data['rules'])} rules, {len(data['setups'])} setups today, jev {data['jev'].get('state')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--data")
    a = ap.parse_args()
    run(a.url, a.data)
