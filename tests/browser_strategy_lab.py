from pathlib import Path
import json
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={"width":1440,"height":1080})
    page.on("pageerror",lambda e:errors.append(str(e)))
    page.goto('http://localhost:3218/strategy-lab.html',wait_until='networkidle')
    assert page.locator('#comparisons tbody tr').count()==12
    assert page.locator('#experiment option').count()==12
    assert '424 of 11800' in page.locator('#audit').inner_text()
    for key in ['intraday_short','diversified_trend','futures_swing','GOLDBEES']:
        page.locator('#experiment').select_option(key)
        rows=page.locator('#trade-rows tr')
        assert 1<=rows.count()<=10
        dates=[x[:10] for x in page.locator('#trade-rows td:nth-child(4)').all_text_contents()]
        assert dates==sorted(dates,reverse=True)
        assert 'NaN' not in page.locator('#trade-rows').inner_text()
    page.locator('#experiment').select_option('futures_swing')
    page.screenshot(path=str(root/'artifacts/strategy-lab-desktop.png'),full_page=True)
    page.set_viewport_size({"width":390,"height":844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(root/'artifacts/strategy-lab-mobile.png'),full_page=True)
    page.route('**/expanded_research.json',lambda r:r.fulfill(status=503,body='unavailable'))
    page.reload(wait_until='networkidle')
    assert page.locator('#comparisons tbody tr').count()==6
    assert 'Dataset unavailable' in page.locator('#comparisons').inner_text()
    assert page.locator('#experiment option').count()==6
    assert not errors,errors
    browser.close()
print('PASS: 12 result rows, dated long/short trades, mobile width, independent failure handling, no browser errors')
