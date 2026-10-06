"""Check the options desk UI against a served snapshot or a local fixture.

Usage:
  py -3 tests/browser_options.py --url http://127.0.0.1:8765/options.html \
      --data tests/fixtures/options_desk_fixture.json
"""
import argparse
import json
from pathlib import Path
import time
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright, expect

BUCKETS = ['BUY_CALL', 'BUY_PUT', 'SELL', 'VOLATILITY', 'UNPROVEN', 'NO_SIGNAL']
ROWS_SEL = '#option-rows tr[data-symbol]'


def verify(page, data):
    rows = data['rows']
    total = data['universe_count']

    # 1. row count equals universe_count
    expect(page.locator(ROWS_SEL)).to_have_count(total)

    # 2. each picker's count equals counts
    for bucket in BUCKETS:
        shown = page.locator(f'#pick-count-{bucket}').inner_text().strip()
        assert shown == str(data['counts'][bucket]), (bucket, shown, data['counts'][bucket])

    # 3. selecting one symbol from every non-empty bucket shows #detail-title == symbol
    #    4. #oi-chart svg renders when oi_profile is not null (and the OI/change toggle works).
    for bucket in BUCKETS:
        members = [r for r in rows if r['bucket'] == bucket]
        if not members:
            assert page.locator(f'#pick-{bucket}').is_disabled(), bucket
            continue
        row = members[0]
        symbol = row['symbol']
        page.locator(f'#pick-{bucket}').select_option(symbol)
        expect(page.locator('#detail-title')).to_have_text(symbol)
        if row.get('oi_profile') is not None:
            expect(page.locator('#oi-chart svg')).to_have_count(1)
            page.locator('#oi-mode').select_option('chg')
            expect(page.locator('#oi-chart svg')).to_have_count(1)
            page.locator('#oi-mode').select_option('oi')

    # 5. no 'NaN' anywhere in the rendered body
    body = page.locator('body').inner_html()
    assert 'NaN' not in body, 'NaN found in rendered HTML'

    # 6. search and filters change the result count correctly
    assert page.locator('#result-count').inner_text().strip() == f'{total} of {total} underlyings shown'

    # pick a symbol that is NOT a substring of any other symbol, so search is deterministic
    uniq = next(r['symbol'] for r in rows
                if not any(o['symbol'] != r['symbol'] and r['symbol'] in o['symbol'] for o in rows))
    page.locator('#search').fill(uniq)
    expect(page.locator(ROWS_SEL)).to_have_count(1)
    assert page.locator('#result-count').inner_text().startswith('1 of')

    page.locator('#search').fill('no-such-underlying-xyz')
    expect(page.locator(ROWS_SEL)).to_have_count(0)
    assert page.locator('#result-count').inner_text().startswith('0 of')
    page.locator('#reset').click()
    expect(page.locator(ROWS_SEL)).to_have_count(total)

    # bucket filter narrows to that bucket's members
    non_empty = next(b for b in BUCKETS if data['counts'][b] > 0)
    page.locator('#bucket').select_option(non_empty)
    expect(page.locator(ROWS_SEL)).to_have_count(data['counts'][non_empty])
    page.locator('#bucket').select_option('ALL')
    expect(page.locator(ROWS_SEL)).to_have_count(total)

    # kind filter
    index_count = len([r for r in rows if r['kind'] == 'index'])
    if index_count:
        page.locator('#kind').select_option('index')
        expect(page.locator(ROWS_SEL)).to_have_count(index_count)
    page.locator('#reset').click()
    expect(page.locator(ROWS_SEL)).to_have_count(total)

    # 7. CSV download works
    with page.expect_download() as download:
        page.locator('#download').click()
    content = Path(download.value.path()).read_text(encoding='utf-8-sig')
    assert uniq in content, 'symbol missing from CSV'
    assert content.count('\n') >= total, 'CSV should have a header plus one line per visible row'

    # 8. #rule-rows rule count is at least the number of rules
    assert page.locator('#rule-rows tr.rule-row').count() >= len(data['rules'])

    # 9. tipsheet market context: cards render, score matches data, events are clickable, no NaN.
    ctx = data.get('context') or {}
    if ctx.get('state') == 'ok':
        fg = ctx['fear_greed']
        if fg.get('score') is not None:
            assert page.locator('#fg-score').inner_text().strip() == str(round(fg['score'])), page.locator('#fg-score').inner_text()
        expect(page.locator('#context-froth tr[data-froth]')).to_have_count(len(ctx.get('froth') or []))
        market = (ctx.get('events') or {}).get('market') or []
        if market:
            expect(page.locator('#market-events li')).to_have_count(len(market))
        with_events = [r for r in rows if r.get('events')]
        assert page.locator('#event-stock-count').inner_text().strip() == str(len(with_events))
        if with_events:
            sym = with_events[0]['symbol']
            page.locator(f'#context-events button[data-symbol="{sym}"]').click()
            expect(page.locator('#detail-title')).to_have_text(sym)
            expect(page.locator('#stock-events')).to_be_visible()
            assert page.locator('#stock-events li').count() == len(with_events[0]['events'])
        assert 'NaN' not in page.locator('#market-context').inner_html()
    else:
        assert page.locator('#context-fg').inner_text().strip(), 'missing-context message should be visible'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8765/options.html')
    parser.add_argument('--data', help='Local JSON served in place of options_desk.json')
    args = parser.parse_args()

    out = Path('artifacts')
    out.mkdir(exist_ok=True)
    host = urlparse(args.url).hostname or 'local'

    data = json.loads(Path(args.data).read_text(encoding='utf-8')) if args.data else None

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1050}, accept_downloads=True)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))

        # Route interception MUST be installed before navigation so the first
        # load of options_desk.json is served from the fixture, not a 404.
        if data is not None:
            page.route('**/options_desk.json*', lambda route: route.fulfill(
                status=200, content_type='application/json', body=json.dumps(data)))

        page.goto(args.url, wait_until='networkidle')

        if data is None:
            source = page.locator('body').get_attribute('data-source') or ''
            data = page.request.get(
                urljoin(args.url, source + 'options_desk.json') + '?verify=' + str(time.time())).json()

        verify(page, data)

        page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
        page.screenshot(path=str(out / f'options-{host}-desktop.png'))

        # 9. an invalid dataset (counts mismatch) shows a visible error instead of the table.
        broken = json.loads(json.dumps(data))
        for b in BUCKETS:
            if broken['counts'].get(b) is not None:
                broken['counts'][b] = broken['counts'][b] + 7
                break
        page.route('**/options_desk.json*', lambda route: route.fulfill(
            status=200, content_type='application/json', body=json.dumps(broken)))
        page.reload(wait_until='networkidle')
        notice = page.locator('#notice').inner_text()
        assert 'could not be loaded' in notice or 'integrity' in notice, notice
        expect(page.locator(ROWS_SEL)).to_have_count(0)

        assert not errors, errors

        result = {
            'url': args.url,
            'data_source': args.data or 'served',
            'as_of': data['as_of'],
            'universe_count': data['universe_count'],
            'counts': data['counts'],
            'rules': len(data['rules']),
            'browser_errors': errors,
        }
        (out / f'options-{host}-verification.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        browser.close()


if __name__ == '__main__':
    main()
