"""Acceptance checks for the top-ten strategy chart on current scanner data."""
import argparse
import json
from pathlib import Path
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument("--url",default="http://localhost:3219/hhhl.html")
parser.add_argument("--fixture")
args=parser.parse_args()
out=Path("artifacts");out.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={"width":1440,"height":1100})
    errors=[]
    page.on("pageerror",lambda error:errors.append(str(error)))
    if args.fixture:
        payload=Path(args.fixture).read_text(encoding="utf-8")
        page.route("**/hhhl_scan.json",lambda route:route.fulfill(status=200,body=payload,content_type="application/json"))
    page.goto(args.url,wait_until="networkidle")
    page.wait_for_function("document.querySelector('#count-ALL').textContent==='200'")
    data=json.loads(payload) if args.fixture else page.request.get(urljoin(args.url,(page.locator("body").get_attribute("data-source") or "")+"hhhl_scan.json")).json()
    picks=data["priority_watchlist"]
    assert page.locator(".priority-card").count()==len(picks)<=10
    for pick in picks:
        stock=next(r for r in data["rows"] if r["symbol"]==pick["symbol"])
        page.locator('.priority-card[data-symbol="'+stock["symbol"]+'"]').click()
        assert page.locator("#detail-title").inner_text().startswith(stock["symbol"]+" / ")
        assert page.locator(".strategy-check").count()==9
        assert page.locator(".daily-candle").count()==min(70,len(stock["chart"]))
        assert page.locator("#stock-chart svg").count()==1
        assert "NaN" not in page.locator("#stock-chart").inner_html()
        if stock["entry_plan"]:
            assert page.locator(".execution-overlay").get_attribute("data-eligible")==str(stock["entry_allowed"]).lower()
        else:
            assert page.locator(".execution-overlay").count()==0
        for level in page.locator(".confirmed-level").all():
            assert level.get_attribute("data-start-date")>=level.get_attribute("data-known-from")
    eligible=[r for r in data["rows"] if len(r.get("chart_swings",[]))>4 and len(r["chart"])>=70]
    assert eligible, "No full confirmed swing history available"
    row=next((r for r in eligible if picks and r["symbol"]==picks[0]["symbol"]),eligible[0])
    if row["symbol"] in [q["symbol"] for q in picks]:
        page.locator('.priority-card[data-symbol="'+row["symbol"]+'"]').click()
    else:
        page.locator("#search").fill(row["symbol"])
        page.locator('button.stock-name[data-symbol="'+row["symbol"]+'"]').click()
    page.locator(".swing-marker").first.wait_for()
    active=page.locator(".active-pivot").count()
    assert 0<active<=4
    assert page.locator(".swing-marker").count()==active
    assert page.locator(".strategy-check").count()==9
    assert page.locator(".daily-candle").count()==70
    assert page.locator(".volume-bar").count()==70
    if not row["entry_allowed"]:
        assert "No new entry is eligible" in page.locator("#strategy-story").inner_text()
    for level in page.locator(".confirmed-level").all():
        assert level.get_attribute("data-start-date")>=level.get_attribute("data-known-from")
    if row["entry_plan"]:
        assert page.locator(".execution-overlay").get_attribute("data-eligible")==str(row["entry_allowed"]).lower()
    page.locator(".swing-marker").last.click()
    assert "Confirmed:" in page.locator("#chart-inspect").inner_text()
    page.locator("#chart-all-pivots").check()
    assert page.locator(".swing-marker").count()>active
    assert page.locator(".structure-zigzag").count()>0
    page.locator("#chart-all-pivots").uncheck()
    page.locator("#chart-swings").uncheck()
    assert page.locator(".swing-marker").count()==0
    assert page.locator(".structure-zigzag").count()==0
    page.locator("#chart-swings").check()
    page.locator("#chart-levels").uncheck()
    assert page.locator(".chart-zone").count()==0
    page.locator("#chart-levels").check()
    page.locator("#chart-window").select_option("35")
    assert page.locator(".daily-candle").count()==35
    page.locator("#chart-window").select_option("140")
    assert page.locator(".daily-candle").count()==min(140,len(row["chart"]))
    page.locator("#chart-window").select_option("70")
    page.locator("#chart-volume").uncheck()
    assert page.locator(".volume-bar").count()==0
    page.locator("#chart-volume").check()
    page.locator("#stock-detail").screenshot(path=str(out/"hhhl-chart-desktop.png"))
    page.locator(".priority-section").screenshot(path=str(out/"hhhl-priority-desktop.png"))
    page.set_viewport_size({"width":390,"height":844})
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    assert page.locator("#stock-chart").evaluate("(el)=>el.scrollWidth>el.clientWidth")
    page.locator("#stock-chart").evaluate("(el)=>el.scrollLeft=el.scrollWidth")
    page.locator(".swing-marker").last.click()
    assert "Confirmed:" in page.locator("#chart-inspect").inner_text()
    page.locator("#stock-detail").screenshot(path=str(out/"hhhl-chart-mobile.png"))
    assert not errors,errors
    report={"url":args.url,"symbol":row["symbol"],"top_setups":len(picks),"shortlist_charts_checked":len(picks),"active_pivots":active,
            "default_candles":70,"zoom_windows":True,"strategy_checks":9,"causal_levels":True,
            "volume_panel":True,"entry_eligibility_preserved":True,"mobile_scroll":True,"errors":errors}
    (out/"hhhl-chart-report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report))
    browser.close()
