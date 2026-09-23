"""Visual and interactive checks for confirmed HH/HL chart overlays."""
import argparse
import json
from pathlib import Path
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

    from urllib.parse import urljoin
    data=json.loads(payload) if args.fixture else page.request.get(urljoin(args.url,(page.locator("body").get_attribute("data-source") or "")+"hhhl_scan.json")).json()
    eligible=[r for r in data["rows"] if len(r.get("chart_swings",[]))>4 and len(r["chart"])==70]
    assert eligible, "No full confirmed swing history available"
    row=next((r for r in eligible if r["structure"]=="HH / HL"),eligible[0])
    page.locator("#search").fill(row["symbol"])
    page.locator('button.stock-name[data-symbol="'+row["symbol"]+'"]').click()
    page.locator(".swing-marker").first.wait_for()
    assert page.locator(".swing-marker").count()>4, "Full confirmed swing history missing"
    assert page.locator(".structure-zigzag").count()>0
    assert page.locator(".daily-candle").count()==70
    page.locator(".swing-marker").last.click()
    assert "Confirmed:" in page.locator("#chart-inspect").inner_text()
    page.locator("#chart-swings").uncheck()
    assert page.locator(".swing-marker").count()==0
    assert page.locator(".structure-zigzag").count()==0
    page.locator("#chart-swings").check()
    page.locator("#chart-levels").uncheck()
    assert page.locator(".chart-zone").count()==0
    page.locator("#chart-levels").check()
    page.locator("#stock-detail").screenshot(path=str(out/"hhhl-chart-desktop.png"))
    page.set_viewport_size({"width":390,"height":844})
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    assert page.locator("#stock-chart").evaluate("(el)=>el.scrollWidth>el.clientWidth")
    page.locator("#stock-chart").evaluate("(el)=>el.scrollLeft=el.scrollWidth")
    page.locator(".swing-marker").last.click()
    assert "Confirmed:" in page.locator("#chart-inspect").inner_text()
    page.locator("#stock-detail").screenshot(path=str(out/"hhhl-chart-mobile.png"))
    assert not errors,errors
    print(json.dumps({"url":args.url,"candles":70,"labels":page.locator(".swing-marker").count(),"zigzag":True,"toggle_controls":True,"confirmation_details":True,"mobile_scroll":True,"errors":errors}))
    browser.close()
