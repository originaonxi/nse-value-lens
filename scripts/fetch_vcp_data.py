"""Download an isolated, auditable price snapshot for the VCP experiment."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

import pandas as pd
import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache' / 'vcp'
START = '2014-01-01'
END = '2026-09-24'


def fetch(symbol):
    path = CACHE / (symbol.replace('^', '') + '.csv')
    if path.exists():
        d = pd.read_csv(path, index_col=0, parse_dates=True)
        source = 'isolated VCP cache'
    else:
        d = yf.Ticker(symbol).history(start=START, end=END, auto_adjust=False,
                                     actions=True, timeout=25)
        if d.empty:
            raise ValueError('No downloaded history')
        d.index = pd.to_datetime([str(x.date()) for x in d.index])
        d = d.loc[(d.index >= START) & (d.index < END)]
        d.to_csv(path, index_label='Date')
        source = 'Yahoo Finance via yfinance; auto_adjust=False, actions=True'
    return {'symbol': symbol, 'source': source, 'rows': len(d),
            'first': str(d.index.min().date()), 'last': str(d.index.max().date()),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'columns': list(d.columns)}


def probe_official():
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.niftyindices.com/'}
    urls = [
        'https://www.niftyindices.com/reports/historical-data',
        'https://www.niftyindices.com/Indices_-_Market_Capitalisation_and_Weightage/indices_dataSep2022.zip',
        'https://www.niftyindices.com/Indices_-_Market_Capitalisation_and_Weightage/indices_dataAug2026.zip',
    ]
    results = []
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=18)
            info = {'url': url, 'status': r.status_code, 'bytes': len(r.content)}
            if r.ok and url.endswith('.zip') and zipfile.is_zipfile(io.BytesIO(r.content)):
                p = CACHE / url.rsplit('/', 1)[-1]
                p.write_bytes(r.content)
                info['files'] = zipfile.ZipFile(io.BytesIO(r.content)).namelist()[:30]
            elif r.ok and 'historical-data' in url:
                (CACHE / 'nifty_historical.html').write_text(r.text, encoding='utf-8')
                info['scripts'] = re.findall(r'<script[^>]+src=[\"\x27]([^\"\x27]+)', r.text)[-15:]
            results.append(info)
        except Exception as exc:
            results.append({'url': url, 'error': str(exc)[:200]})
        print(json.dumps(results[-1]), flush=True)
    (CACHE / 'official_probe.json').write_text(json.dumps(results, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', action='store_true')
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    symbols = ['RELIANCE.NS', '^CNX200', '^NSEI'] if args.probe else (
        [s + '.NS' for s in pd.read_csv(ROOT / 'nifty200.csv').Symbol] + ['^CNX200', '^NSEI'])
    results = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fetch, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({'symbol': futures[future], 'error': str(exc)[:220]})
            if args.probe or len(results) % 20 == 0 or 'error' in results[-1]:
                print(json.dumps({'complete': len(results), 'last': results[-1]}), flush=True)
    manifest = {'downloaded_at': datetime.now(timezone.utc).isoformat(),
                'requested_start': START, 'requested_end_exclusive': END,
                'files': sorted(results, key=lambda r: r['symbol'])}
    (CACHE / ('probe_manifest.json' if args.probe else 'manifest.json')).write_text(
        json.dumps(manifest, indent=2), encoding='utf-8')
    if args.probe:
        probe_official()


if __name__ == '__main__':
    main()
