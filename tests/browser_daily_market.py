"""Desktop/mobile and failure checks for daily NSE data and the stock filter."""
import json
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/daily-market';OUT.mkdir(parents=True,exist_ok=True)
URL='http://127.0.0.1:3232/'
data=json.loads((ROOT/'docs/daily_market.json').read_text(encoding='utf-8'))

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(URL+'daily-market.html');page.wait_for_selector('#index-cards .index-item')
    assert page.locator('#daily-session').inner_text()==data['as_of']
    assert page.locator('#daily-status').inner_text().startswith('All four official reports checked')
    for scope in ['exchange','nifty200','fno','all']:
        page.locator('#market-universe').select_option(scope)
        assert page.locator('#market-leaders tr').count()==15
        for rank in ['gainers','losers','turnover','volume']:page.locator('#market-ranking').select_option(rank)
    page.locator('#market-universe').select_option('exchange')
    for scope in ['all','nifty200','fno','exchange']:
        for period in ['latest','recent','month']:
            for kind in ['all','bulk','block']:
                page.locator('#deal-universe').select_option(scope)
                page.locator('#deal-period').select_option(period)
                page.locator('#deal-kind').select_option(kind)
                assert 'disclosure rows' in page.locator('#deal-status').inner_text()
    page.locator('#deal-universe').select_option('all');page.locator('#deal-period').select_option('recent');page.locator('#deal-kind').select_option('all')
    page.locator('#deal-search').fill('BSE');assert page.locator('#deal-rows tr').count()>0
    with page.expect_download() as download:page.locator('#deals-download').click()
    csv=Path(download.value.path()).read_text(encoding='utf-8-sig');assert 'BSE' in csv and 'value_crore' in csv
    page.locator('#deal-search').fill('');page.evaluate("scrollTo({top:0,behavior:'instant'})");page.screenshot(path=str(OUT/'desktop.png'))
    page.set_viewport_size({'width':390,'height':844});page.evaluate("scrollTo({top:0,behavior:'instant'})")
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'Market page overflows mobile'
    page.screenshot(path=str(OUT/'mobile.png'))
    page.goto(URL+'hhhl.html');page.wait_for_selector('#stock-chart svg')
    page.wait_for_function("document.querySelector('#daily-deal-note').textContent.includes('NSE reports:')")
    page.locator('#daily-deal-filter').select_option('recent')
    cutoff=(date.fromisoformat(data['as_of'])-timedelta(days=6)).isoformat()
    expected={r['symbol'] for r in data['recent_deals'] if r['membership'].get('nifty200') and cutoff<=r['date']<=data['as_of']}
    shown=set(page.locator('#stock-rows tr[data-symbol]').evaluate_all('(rows)=>rows.map(r=>r.dataset.symbol)'))
    assert shown==expected,(shown,expected)
    expected_bulk={r['symbol'] for r in data['bulk']['rows'] if r['membership'].get('nifty200')}
    page.locator('#daily-deal-filter').select_option('bulk');assert page.locator('#stock-rows tr[data-symbol]').count()==len(expected_bulk)
    page.locator('#reset').click();assert page.locator('#stock-rows tr[data-symbol]').count()==200
    assert page.locator('#stock-chart svg').count()==1
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'Scanner overflows mobile'
    page.screenshot(path=str(OUT/'scanner-mobile.png'))
    failed=browser.new_page();failed.route('**/daily_market.json',lambda route:route.fulfill(status=503,body='Unavailable'))
    failed.goto(URL+'hhhl.html');failed.wait_for_selector('#stock-chart svg');failed.wait_for_function("document.querySelector('#daily-deal-note').textContent.includes('unavailable')")
    assert failed.locator('#stock-rows tr[data-symbol]').count()==200
    failed.locator('#daily-deal-filter').select_option('bulk');assert failed.locator('#stock-rows tr[data-symbol]').count()==0
    stale=json.loads(json.dumps(data));stale['attempted_at']='2026-09-01T00:00:00+00:00'
    late=browser.new_page();late.route('**/daily_market.json',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(stale)))
    late.goto(URL+'daily-market.html');late.wait_for_selector('#index-cards .index-item')
    assert 'overdue' in late.locator('#daily-status').inner_text()
    assert not errors,errors
    browser.close()
    print('Passed desktop/mobile, 36 disclosure filter combinations, market controls, CSV, scanner filters and failure states.')
