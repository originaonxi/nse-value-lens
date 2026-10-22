"""Exercise the real Kronos page and cross-check displayed data against source CSVs.

Run after inference: python tests/browser_kronos.py --url <kronos.html URL>
No synthetic model fixtures are used by this acceptance test.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:3219/kronos.html')
    parser.add_argument('--min-forecasts', type=int, default=1)
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1100})
        errors = []
        page.on('pageerror', lambda err: errors.append(str(err)))
        page.goto(args.url + '?symbol=NSEI', wait_until='networkidle')
        scan = page.request.get(urljoin(args.url, 'hhhl_scan.json')).json()
        forecast = page.request.get(urljoin(args.url, 'kronos_forecast.json')).json()
        expected = {'NSEI'} | {r['symbol'] for r in scan['rows']}
        page.wait_for_function("document.querySelector('#kro-symbol').options.length > 1")
        options = set(page.locator('#kro-symbol option').evaluate_all('(els)=>els.map(e=>e.value)'))
        assert options == expected, (len(options), len(expected), expected - options)
        assert page.locator('#kro-symbol').input_value() == 'NSEI'
        assert forecast['model'] == 'NeoQuasar/Kronos-small'
        assert forecast['provenance']['kind'] == 'kronos-neural'
        symbols = forecast['symbols']
        assert len(symbols) >= args.min_forecasts, len(symbols)
        assert 'NSEI' in symbols
        histories_checked = 0
        for symbol, result in symbols.items():
            assert result['provenance']['kind'] == 'kronos-neural', symbol
            assert result['provenance']['model'] == forecast['model'], symbol
            assert result['data_as_of'] == scan['as_of'], (symbol, result['data_as_of'])
            path = ROOT / 'data/hhhl_prices' / ('NSEI.csv' if symbol == 'NSEI' else symbol + '.NS.csv')
            assert hashlib.sha256(path.read_bytes()).hexdigest() == result['input_sha256'], symbol
            with path.open(encoding='utf-8-sig', newline='') as stream:
                reader = csv.DictReader(stream)
                rows = list(reader)
                date_key = reader.fieldnames[0]
                source = {row[date_key][:10]: {k.lower(): v for k, v in row.items()} for row in rows}
            for candle in result['history']:
                row = source[candle['d']]
                for short, long in [('o', 'open'), ('h', 'high'), ('l', 'low'), ('c', 'close')]:
                    assert abs(candle[short] - float(row[long])) <= .0051, (symbol, candle, long)
                histories_checked += 1
            assert len(result['paths']) == result['config']['n_samples'], symbol
            assert all(len(path) == forecast['pred_len'] for path in result['paths']), symbol
            for predicted_path in result['paths']:
                dates = [bar['d'] for bar in predicted_path]
                assert dates == sorted(set(dates)) and dates[0] > result['data_as_of'], symbol
                assert all(set(bar) == {'d', 'c'} and math.isfinite(bar['c']) and bar['c'] > 0
                           for bar in predicted_path), (symbol, 'Forecasts must be genuine close paths, not fabricated candles')
        for symbol in ['NSEI', next(s for s in symbols if s != 'NSEI')]:
            page.locator('#kro-symbol').select_option(symbol)
            assert page.locator('#kro-interp').inner_text().strip(), symbol
            assert page.locator('#kro-stats').inner_text().strip(), symbol
            assert page.locator('#kronos-chart path, #kronos-chart polyline').count() > 0, symbol
        missing = expected - set(symbols)
        for symbol in missing:
            page.locator('#kro-symbol').select_option(symbol)
            text = page.locator('#kro-forecast').inner_text().lower()
            assert 'unavailable' in text or 'stale' in text, (symbol, text)
            assert page.locator('#kro-interp').inner_text().strip(), symbol
        artifacts = ROOT / 'artifacts'
        artifacts.mkdir(exist_ok=True)
        page.locator('#kro-symbol').select_option('NSEI')
        page.screenshot(path=str(artifacts / 'kronos-desktop.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        page.screenshot(path=str(artifacts / 'kronos-mobile.png'), full_page=True)
        assert not errors, errors
        report = {'url': args.url, 'source_date': scan['as_of'], 'selector_symbols': len(options),
                  'real_forecasts': len(symbols), 'unavailable_symbols': sorted(missing),
                  'source_candles_verified': histories_checked, 'page_errors': errors,
                  'mobile_layout': 'passed'}
        (artifacts / 'kronos-live-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report))
        browser.close()


if __name__ == '__main__':
    main()
