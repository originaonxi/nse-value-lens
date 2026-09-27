"""Verify stock-list views, every chart/reason, exports and failed refresh behavior."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument('--url',default='http://127.0.0.1:3224/hhhl.html')
parser.add_argument('--compare-stocks',action='store_true')
args=parser.parse_args()
out=Path(__file__).resolve().parents[1]/'artifacts/fno';out.mkdir(parents=True,exist_ok=True)

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(args.url)
    page.wait_for_function("!document.querySelector('#universe option[value=all]').disabled")
    base=page.evaluate("async()=>await (await fetch((document.body.dataset.source||'')+'hhhl_scan.json')).json()")
    extra=page.evaluate("async()=>await (await fetch((document.body.dataset.source||'')+'hhhl_fno.json')).json()")
    original={row['symbol']:row for row in base['rows']}
    combined={**original,**{r['symbol']:r for r in extra['rows'] if r['symbol'] not in original}}
    members={m['symbol'] for m in extra['membership']['members']}
    before=None
    if args.compare_stocks:
        before=browser.new_page(viewport={'width':1440,'height':1100})
        before.goto('http://127.0.0.1:3224/before/hhhl.html')
        before.wait_for_selector('#stock-chart svg')
    for mode,symbols in [('nifty200',set(original)),('fno',members),('all',set(combined))]:
        page.locator('#universe').select_option(mode)
        shown=page.locator('[data-pick-state] option[value]:not([value=""])').evaluate_all('(els)=>els.map(el=>el.value)')
        assert len(shown)==len(symbols) and set(shown)==symbols,(mode,len(shown))
        assert page.locator('#count-ALL').inner_text()==str(len(symbols))
        assert page.evaluate('scrollY')==0
    for i,row in enumerate(combined.values()):
        page.locator('#pick-'+row['status']).select_option(row['symbol'])
        assert page.evaluate('scrollY')==0,row['symbol']
        assert page.locator('#detail-title').inner_text().startswith(row['symbol']+' / ')
        assert page.locator('#selection-reason').inner_text().startswith('WHY '+row['status']+': ')
        assert page.locator('#selection-reason').evaluate('el=>Number(getComputedStyle(el).fontWeight)>=700')
        assert page.locator('.stock-picker.selected').count()==1
        assert page.locator('.daily-candle').count()==min(70,len(row['chart']))
        assert 'NaN' not in page.locator('#stock-chart').inner_html()
        if before and row['symbol'] in original:
            before.locator('#pick-'+row['status']).select_option(row['symbol'])
            assert page.locator('#stock-chart svg').evaluate('el=>el.outerHTML')==before.locator('#stock-chart svg').evaluate('el=>el.outerHTML'),row['symbol']
            assert page.locator('#selection-reason').inner_text()==before.locator('#selection-reason').inner_text(),row['symbol']
        if (i+1)%50==0:print(f'{i+1}/{len(combined)} charts and bold reasons passed.',flush=True)
    selected=extra['rows'][0]
    page.locator('#pick-'+selected['status']).select_option(selected['symbol'])
    for size in ['35','140','70']:
        page.locator('#chart-window').select_option(size)
        assert page.locator('.daily-candle').count()==min(int(size),len(selected['chart']))
    page.locator('#chart-swings').uncheck();assert page.locator('.swing-marker').count()==0
    page.locator('#chart-swings').check()
    page.locator('#chart-levels').uncheck();assert page.locator('.price-level-label').count()==0
    page.locator('#chart-levels').check()
    page.screenshot(path=str(out/'desktop.png'))
    page.locator('#universe').select_option('fno')
    with page.expect_download() as download:
        page.locator('#download-json').click()
    exported=json.loads(Path(download.value.path()).read_text(encoding='utf-8'))
    assert {r['symbol'] for r in exported['rows']}==members
    page.evaluate('scrollTo(0,0)')
    page.set_viewport_size({'width':390,'height':844})
    page.evaluate('document.activeElement.blur();scrollTo(0,0)')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(out/'mobile.png'))
    page.locator('#universe').select_option('nifty200')
    assert page.locator('#detail-title').inner_text().split(' / ')[0] in original
    assert not errors,errors
    print(f'All {len(combined)} charts, all three filters, exports and mobile layout passed.',flush=True)
    if before:print('All 200 original chart SVGs and bold reasons are identical.',flush=True)

    failed=browser.new_page()
    failed.route('**/hhhl_fno.json',lambda route:route.fulfill(status=503,body='Unavailable'))
    failed.goto(args.url);failed.wait_for_selector('#stock-chart svg')
    failed.wait_for_function("document.querySelector('#universe-note').textContent.includes('temporarily unavailable')")
    assert failed.locator('#count-ALL').inner_text()=='200'
    assert failed.locator('#universe option[value=fno]').evaluate('el=>el.disabled'), failed.locator('#universe').inner_html()
    recover=browser.new_page()
    recover.add_init_script('window.setInterval=(fn)=>{window.__refresh=fn;return 1;}')
    recover.goto(args.url);recover.wait_for_function("!document.querySelector('#universe option[value=all]').disabled")
    recover.locator('#universe').select_option('all')
    recover.locator('#pick-'+selected['status']).select_option(selected['symbol'])
    recover.route('**/hhhl_fno.json',lambda route:route.fulfill(status=503,body='Unavailable'))
    recover.evaluate('window.__refresh()')
    recover.wait_for_function("document.querySelector('#selection-reason').textContent.includes('could not be checked')")
    assert recover.locator('#stock-chart svg').count()==1
    assert recover.locator('#detail-badge').inner_text()=='CAUTION'
    recover.unroute('**/hhhl_fno.json');recover.evaluate('window.__refresh()')
    recover.wait_for_function('(state)=>document.querySelector("#detail-badge").textContent===state',arg=selected['status'])
    empty=browser.new_page();changed=json.loads(json.dumps(extra))
    changed['membership']['members'].append({'symbol':'NEWSTOCK','name':'New Stock'});changed['fno_count']+=1
    empty.route('**/hhhl_fno.json',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(changed)))
    empty.goto(args.url);empty.wait_for_function("!document.querySelector('#universe option[value=all]').disabled")
    empty.locator('#universe').select_option('fno');empty.locator('#pick-CAUTION').select_option('NEWSTOCK')
    assert empty.locator('#detail-badge').inner_text()=='CAUTION'
    assert 'Price history is unavailable' in empty.locator('#selection-reason').inner_text()
    assert empty.locator('#candle-readout').inner_text()==''
    assert 'null' not in empty.locator('#chart-price').inner_text()
    invalid=browser.new_page()
    invalid.route('**/hhhl_scan.json',lambda route:route.fulfill(status=503,body='Unavailable'))
    invalid.goto(args.url);invalid.wait_for_function("document.querySelector('#coverage').textContent==='Data check failed'")
    assert invalid.locator('#universe').is_disabled()
    assert not invalid.locator('#stock-detail').is_visible()
    print('Missing feed, saved-chart recovery and newly listed stocks passed.',flush=True)
    browser.close()
