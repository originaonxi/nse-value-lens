"""Exercise all new market charts; optionally compare every stock with /before/."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument('--url',default='http://127.0.0.1:3224/global-markets.html')
parser.add_argument('--compare-stocks',action='store_true')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
out=root/'artifacts/global-markets';out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(args.url)
    page.wait_for_selector('#stock-chart svg')
    data=page.evaluate("async()=>await (await fetch((document.body.dataset.source||'')+'global_markets.json')).json()")
    assert len(data['rows'])==26
    for row in data['rows']:
        page.locator('#'+row['group']+'-picker').select_option(row['symbol'])
        assert page.evaluate('scrollY')==0
        assert page.locator('#detail-title').inner_text()==row['name']
        assert row['unit'] in page.locator('#detail-subtitle').inner_text()
        assert page.locator('#selection-reason').inner_text().startswith('WHY '+row['status']+': ')
        assert page.locator('#selection-reason').evaluate('el=>Number(getComputedStyle(el).fontWeight)>=700')
        assert page.locator('.stock-picker.selected').count()==1
        if row['chart']:
            assert page.locator('#stock-chart .daily-candle').count()==min(70,len(row['chart']))
            assert 'NaN' not in page.locator('#stock-chart').inner_html()
            assert page.locator('#stock-chart .volume-bar').count()==(0 if row['group']=='forex' else min(70,len(row['chart'])))
            labels=page.locator('.active-pivot').evaluate_all('(els)=>els.map(el=>el.getAttribute("aria-label"))')
            assert all('undefined' not in text for text in labels)
    page.locator('#forex-picker').select_option('EURUSD=X')
    assert '₹' not in page.locator('#chart-price').inner_text()
    for size in ['35','140','70']:
        page.locator('#chart-window').select_option(size)
        assert page.locator('.daily-candle').count()==int(size)
    page.locator('#chart-swings').uncheck();assert page.locator('.swing-marker').count()==0
    page.locator('#chart-swings').check()
    page.locator('#chart-all-pivots').check();assert page.locator('.swing-marker').count()>4
    page.locator('#chart-all-pivots').uncheck()
    page.locator('#chart-levels').uncheck();assert page.locator('.price-level-label').count()==0
    page.locator('#chart-levels').check()
    page.screenshot(path=str(out/'forex.png'))
    page.locator('#commodity-picker').select_option('GC=F')
    page.screenshot(path=str(out/'commodity.png'))
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert page.locator('#stock-chart').evaluate('el=>el.scrollWidth>el.clientWidth')
    page.screenshot(path=str(out/'mobile.png'))
    assert not errors,errors
    print('26 market dropdowns/charts, controls, precision, bold reasons and mobile layout passed.',flush=True)
    fallback=browser.new_page()
    fallback.add_init_script('window.setInterval=(fn)=>{window.__refresh=fn;return 1;}')
    fallback.goto(args.url);fallback.wait_for_selector('#stock-chart svg')
    fallback.route('**/global_markets.json',lambda route:route.fulfill(status=503,body='Temporarily unavailable'))
    fallback.evaluate('window.__refresh()')
    fallback.wait_for_function("document.querySelector('#selection-reason').textContent.includes('latest refresh failed')")
    fallback.locator('#forex-picker').select_option('EURUSD=X')
    assert fallback.locator('#detail-badge').inner_text()=='CAUTION'
    assert fallback.locator('#data-warning').is_visible()
    assert fallback.locator('#stock-chart svg').count()==1
    fallback.unroute('**/global_markets.json')
    fallback.evaluate('window.__refresh()')
    expected=next(r['status'] for r in data['rows'] if r['symbol']=='EURUSD=X')
    fallback.wait_for_function('(state)=>document.querySelector("#detail-badge").textContent===state',arg=expected)
    stale=browser.new_page()
    old={**data,'generated_at':'2020-01-01T00:00:00+00:00'}
    stale.route('**/global_markets.json',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(old)))
    stale.goto(args.url);stale.wait_for_selector('#stock-chart svg')
    assert stale.locator('#detail-badge').inner_text()=='CAUTION'
    assert 'overdue' in stale.locator('#selection-reason').inner_text()
    print('Failed refresh, recovery and overdue data all preserve charts with accurate Caution labels.',flush=True)
    if args.compare_stocks:
        after=browser.new_page(viewport={'width':1440,'height':1100})
        before=browser.new_page(viewport={'width':1440,'height':1100})
        after.goto('http://127.0.0.1:3224/hhhl.html');before.goto('http://127.0.0.1:3224/before/hhhl.html')
        for site in [after,before]:site.wait_for_selector('#stock-chart svg')
        stocks=after.evaluate("async()=>await (await fetch('hhhl_scan.json')).json()")
        for i,row in enumerate(stocks['rows']):
            for site in [after,before]:site.locator('#pick-'+row['status']).select_option(row['symbol'])
            assert after.locator('#stock-chart svg').evaluate('el=>el.outerHTML')==before.locator('#stock-chart svg').evaluate('el=>el.outerHTML'),row['symbol']
            assert after.locator('#selection-reason').inner_text()==before.locator('#selection-reason').inner_text(),row['symbol']
            if (i+1)%50==0:print(f'{i+1}/200 stock charts and reasons remain identical.',flush=True)
        assert after.locator('a[href="global-markets.html"]').count()==1
    browser.close()
