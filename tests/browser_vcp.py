"""Check the live VCP UI, full universe, charts, variants and refresh identity."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import time
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright


def verify(page, data):
    page.wait_for_function("document.querySelector('#universe-count').textContent==='200'")
    assert page.locator('#stock-rows tr').count()==200
    for mode in data['modes']:
        page.locator('#mode').select_option(mode)
        expected=[r for r in data['rows'] if r['modes'][mode]['state']=='WATCH']
        assert page.locator('#setups article').count()==len(expected)
        assert page.locator('#watch-count').inner_text()==str(len(expected))
        for row in expected:
            page.locator('#setups button[data-symbol="'+row['symbol']+'"]').click()
            assert page.locator('#detail-title').inner_text()==row['symbol']
            assert page.locator('.contraction').count()==row['modes'][mode]['pattern']['count']
            assert page.locator('#stock-chart svg').count()==1
            assert 'NaN' not in page.locator('#stock-chart').inner_html()
        for state in ('WATCH','TRIGGERED','SCREEN_ONLY','NO_SETUP','DATA'):
            page.locator('#state').select_option(state)
            count=sum(r['modes'][mode]['state']==state for r in data['rows'])
            assert page.locator('#result-count').inner_text().startswith(str(count)+' of 200')
        page.locator('#reset').click()
    page.locator('#mode').select_option(data['default_mode'])
    row=next(r for r in data['rows'] if r['symbol']=='RELIANCE')
    page.locator('#search').fill(row['symbol'])
    page.locator('#stock-rows button[data-symbol="RELIANCE"]').click()
    assert page.locator('#detail-title').inner_text()=='RELIANCE'
    for size in (26,78,52):
        page.locator('#chart-window').select_option(str(size))
        assert page.locator('[data-candle]').count()==min(size,len(row['chart']))
    page.locator('[data-candle="10"]').click()
    assert 'Open ₹' in page.locator('#candle-readout').inner_text()
    with page.expect_download() as download:
        page.locator('#download').click()
    content=Path(download.value.path()).read_text(encoding='utf-8-sig')
    assert 'RELIANCE' in content and content.count('\n')==1
    page.locator('#search').fill('no-such-stock-123')
    assert page.locator('#result-count').inner_text().startswith('0 of 200')
    page.locator('#reset').click()
    assert page.locator('#stock-rows tr').count()==200


def fixture_data(data):
    """UI-only fixture for the nonempty branch; never published as market data."""
    data=deepcopy(data)
    for row in data['rows'][:13]:
        bars=row['chart']
        points=[bars[i]['date'] for i in (-12,-10,-8,-6,-4,-2)]
        p={'id':'ui-fixture','pivot':row['close']*1.05,'final_low':row['close']*.95,
           'count':3,'depths':[.20,.10,.05],'durations':[2,2,2],
           'pivot_dates':points,'confirmation_dates':points,'pullback_volumes':[300,200,100]}
        for mode in data['modes']:
            row['modes'][mode]={'state':'WATCH','pattern':p,'event_date':None,
                'reason':'Synthetic browser test only',
                'preview':{'trigger':row['close']*1.05,'stop_at_trigger':row['close']*.97,'risk_pct':7.62,'distance_pct':5}}
    return data


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://localhost:3220/vcp.html')
    parser.add_argument('--run-id')
    parser.add_argument('--fixtures',action='store_true')
    args=parser.parse_args()
    out=Path('artifacts');out.mkdir(exist_ok=True)
    host=urlparse(args.url).hostname
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':1440,'height':1050},accept_downloads=True)
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(args.url,wait_until='networkidle')
        source=page.locator('body').get_attribute('data-source') or ''
        data=page.request.get(urljoin(args.url,source+'vcp_scan.json')+'?verify='+str(time.time())).json()
        if args.run_id:
            deadline=time.monotonic()+180
            status_url=urljoin(args.url,source+'vcp_refresh_status.json')
            status=page.request.get(status_url+'?verify='+str(time.time())).json()
            while (data.get('refresh_run_id')!=args.run_id or status.get('snapshot_run_id')!=args.run_id or status.get('run_id')!=args.run_id) and time.monotonic()<deadline:
                time.sleep(5)
                data=page.request.get(urljoin(args.url,source+'vcp_scan.json')+'?verify='+str(time.time())).json()
                status=page.request.get(status_url+'?verify='+str(time.time())).json()
            assert data['refresh_run_id']==args.run_id,(data.get('refresh_run_id'),args.run_id)
            page.reload(wait_until='networkidle')
            assert status['run_id']==args.run_id and status['snapshot_run_id']==args.run_id
            assert status['state'] in ('fresh','partial')
        assert len(data['rows'])==len({r['symbol'] for r in data['rows']})==200
        verify(page,data)
        page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
        page.screenshot(path=str(out/f'vcp-{host}-desktop.png'))
        page.locator('#stock-detail').screenshot(path=str(out/f'vcp-{host}-chart.png'))
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
        page.screenshot(path=str(out/f'vcp-{host}-mobile.png'))
        page.locator('#mode').select_option('three')
        assert page.locator('#stock-rows tr').count()==200
        for link in ('vcp-research/REPORT.md','vcp-research/comparison.csv','vcp-research/selected_trades.csv'):
            assert page.request.get(urljoin(args.url,link)).status==200
        if args.fixtures:
            fixture=fixture_data(data)
            page.route('**/vcp_scan.json*',lambda route:route.fulfill(json=fixture))
            page.set_viewport_size({'width':1440,'height':1050})
            page.reload(wait_until='networkidle')
            verify(page,fixture)
            assert page.locator('#setups article').count()>=13
            page.locator('#setups').screenshot(path=str(out/'vcp-fixture-setups.png'))
            page.route('**/vcp_scan.json*',lambda route:route.fulfill(status=503,body='unavailable'))
            page.reload(wait_until='networkidle')
            assert 'could not be loaded' in page.locator('#notice').inner_text()
            assert 'Missing data is not the same' in page.locator('#setups').inner_text()
        assert not errors,errors
        result={'url':args.url,'as_of':data['as_of'],'weekly_as_of':data['weekly_as_of'],
                'run_id':data['refresh_run_id'],'rows':200,'counts':data['counts'],'browser_errors':errors}
        (out/f'vcp-{host}-verification.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))
        browser.close()


if __name__=='__main__':
    main()
