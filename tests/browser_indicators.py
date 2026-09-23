from pathlib import Path
import json
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1080})
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://localhost:3219/indicator-lab.html',wait_until='networkidle')
    assert page.locator('#ranking-rows tr').count()==100
    assert page.locator('#rule option').count()==144
    assert page.locator('#profitable').inner_text()=='6'
    assert page.locator('#always').inner_text()=='0'
    assert page.locator('#rule').input_value()=='st_7_2_h20_any'
    assert '-4.83%' in page.locator('#selection').inner_text()
    page.locator('#scope').select_option('all')
    assert page.locator('#ranking-rows tr').count()==144
    page.locator('#family').select_option('Supertrend')
    assert page.locator('#ranking-rows tr').count()==32
    page.locator('#hold').select_option('20')
    assert page.locator('#ranking-rows tr').count()==8
    page.locator('#family').select_option('all');page.locator('#hold').select_option('all')
    page.locator('#scope').select_option('always')
    assert 'No tested rules' in page.locator('#ranking-rows').inner_text()
    page.locator('#scope').select_option('100')
    page.locator('#rule').select_option('hhhl_h10_nifty_above_200')
    assert '6.29%' in page.locator('#rule-metrics').inner_text()
    assert page.locator('#trade-rows tr').count()==10
    dates=[v[:10] for v in page.locator('#trade-rows td:nth-child(3)').all_text_contents()]
    assert dates==sorted(dates,reverse=True)
    assert page.locator('#equity-chart svg').count()==1
    page.screenshot(path=str(root/'artifacts/indicator-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(root/'artifacts/indicator-mobile.png'),full_page=True)
    page.route('**/indicator_research.json',lambda route:route.fulfill(status=503,body='unavailable'))
    page.reload(wait_until='networkidle')
    assert 'could not be loaded' in page.locator('#status').inner_text()
    assert page.locator('#rule option').count()==0
    assert not errors,errors
    browser.close()
print('PASS: 100/144 rankings, indicator/hold filters, no-false-winners state, dates, chart, mobile, failed fetch, no JS errors')
