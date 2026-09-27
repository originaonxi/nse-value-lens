"""Add NSE stock F&O coverage without changing the Nifty 200 scan or prices."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
from io import StringIO
import json
from pathlib import Path
import re

from curl_cffi import requests
import numpy as np
import pandas as pd
import yfinance as yf

from hhhl_scanner import OHLCV, normalize_sessions, read_prices, scan_stock

ROOT = Path(__file__).resolve().parent
SOURCE = 'https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv'
SECTORS = 'https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv'


def parse_membership(text, today):
    rows = list(csv.reader(StringIO(text)))
    if not rows or rows[0][0].strip().upper() != 'UNDERLYING':
        raise ValueError('NSE F&O CSV header missing')
    months = []
    for i, cell in enumerate(rows[0][2:], 2):
        try:
            stamp = datetime.strptime(cell.strip(), '%b-%y').date()
            if stamp >= today.replace(day=1):
                months.append((stamp, i))
        except ValueError:
            pass
    if not months:
        raise ValueError('No current F&O contract month in source')
    month, column = min(months)
    if (month.year - today.year)*12 + month.month - today.month > 1:
        raise ValueError('F&O file has no nearby contract month')
    members = []
    for row in rows[1:]:
        if len(row) <= column:
            continue
        name, symbol, lot = row[0].strip(), row[1].strip(), row[column].strip()
        # The file has separate index and stock sections and repeated headers.
        if name.upper().startswith('NIFTY') or not re.fullmatch(r'[A-Z0-9&_-]+', symbol):
            continue
        if not lot.isdigit() or int(lot) <= 0:
            continue
        members.append({'symbol': symbol, 'name': name, 'lot_size': int(lot)})
    symbols = [row['symbol'] for row in members]
    if not 100 <= len(symbols) <= 500 or len(set(symbols)) != len(symbols):
        raise ValueError('Incomplete or duplicate NSE stock F&O list')
    return sorted(members, key=lambda r: r['symbol']), month.strftime('%b-%y').upper()


def get_text(url):
    response = requests.get(url, impersonate='chrome', timeout=20)
    response.raise_for_status()
    return response.text


def membership(previous, now):
    try:
        text = get_text(SOURCE)
        rows, month = parse_membership(text, now.date())
        return {'members': rows, 'verified': True, 'verified_at': now.isoformat(),
                'attempted_at': now.isoformat(), 'contract_month': month,
                'source': SOURCE, 'sha256': hashlib.sha256(text.encode()).hexdigest()}
    except Exception as exc:
        if not previous or not previous.get('members'):
            raise ValueError('No verified F&O membership available') from exc
        saved = deepcopy(previous)
        saved.update(verified=False, attempted_at=now.isoformat(), error=str(exc)[:180])
        return saved


def caution(row, reason):
    result = deepcopy(row)
    result.update(status='CAUTION', reason=reason, entry_allowed=False, fresh_breakout=False,
                  entry_plan=None, zones={}, refresh_warning=reason)
    result['data_warnings'] = list(result.get('data_warnings', [])) + [reason]
    result['entry_checks'] = [dict(check, state='fail') if check['key'] == 'data' else check
                              for check in result.get('entry_checks', [])]
    return result


def fetch_stock(meta, base, calendar, prices, now):
    path = prices/(meta['Symbol']+'.NS.csv')
    old, invalid = read_prices(path, base['as_of']) if path.exists() else (pd.DataFrame(columns=OHLCV), [])
    error = None
    try:
        # Replace a full adjusted history together, never splice different split scales.
        raw = yf.Ticker(meta['Symbol']+'.NS').history(period='5y', auto_adjust=True, actions=False, timeout=25)
        frame = raw[OHLCV].copy()
        frame.index = pd.to_datetime([stamp.date() for stamp in frame.index])
        frame = frame.loc[frame.index <= pd.Timestamp(base['as_of'])]
        frame = frame.loc[~frame.index.duplicated(keep='last')].sort_index()
        for col in OHLCV:
            frame[col] = pd.to_numeric(frame[col], errors='coerce')
        valid = (np.isfinite(frame).all(axis=1) & (frame[OHLCV[:4]] > 0).all(axis=1)
                 & (frame.High >= frame[OHLCV[:4]].max(axis=1))
                 & (frame.Low <= frame[OHLCV[:4]].min(axis=1)) & (frame.Volume > 0))
        invalid = [str(day.date()) for day in frame.index[~valid & (frame.Volume > 0)]]
        frame = frame.loc[valid & frame.index.isin(calendar)]
        if len(frame) < 20 or (len(old) and (len(frame) < min(len(old), 210) or frame.index[-1] < old.index[-1])):
            raise ValueError('Incomplete or regressed adjusted history')
        prices.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        frame.to_csv(temporary, index_label='Date', lineterminator='\n')
        temporary.replace(path)
    except Exception as exc:
        frame = old.loc[old.index.isin(calendar) & (old.Volume > 0)]
        error = type(exc).__name__+': '+str(exc)[:160]
    row = scan_stock(meta, frame, invalid, base['as_of'], base['market'], calendar)
    row['data_source'] = 'Yahoo adjusted daily stock OHLCV. F&O membership comes from NSE; these are underlying share prices, not futures or options premiums.'
    row['retrieved_at'] = now.isoformat() if error is None else None
    if error:
        row = caution(row, 'The latest price download failed; any visible candles are the last saved prices.')
        row['refresh_error'] = error
    return row


def stock_calendar(root, base):
    loaded = {}
    for row in base['rows']:
        path = root/'data/hhhl_prices'/(row['symbol']+'.NS.csv')
        try:
            loaded[row['symbol']] = read_prices(path, base['as_of'])[0]
        except (OSError, ValueError, KeyError):
            pass
    calendar, _, _ = normalize_sessions(loaded)
    if len(calendar) < 200 or pd.Timestamp(base['as_of']) not in calendar:
        raise ValueError('Shared Nifty stock trading calendar is incomplete')
    return calendar


def write_snapshot(root, payload):
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':'))+'\n'
    for relative in ('docs/hhhl_fno.json', 'public/data/hhhl_fno.json'):
        path = root/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(encoded, encoding='utf-8')
        temporary.replace(path)


def refresh(root=ROOT, now=None):
    now = now or datetime.now(timezone.utc)
    base = json.loads((root/'docs/hhhl_scan.json').read_text(encoding='utf-8'))
    if len(base['rows']) != 200 or len({r['symbol'] for r in base['rows']}) != 200:
        raise ValueError('The original Nifty 200 snapshot must be complete')
    path = root/'docs/hhhl_fno.json'
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    listing = membership(previous.get('membership'), now)
    existing = {r['symbol'] for r in base['rows']}
    extras = [m for m in listing['members'] if m['symbol'] not in existing]
    metadata = {r['symbol']: {'Company Name': r['name'], 'Industry': r['sector']} for r in previous.get('rows', [])}
    try:
        for row in csv.DictReader(StringIO(get_text(SECTORS))):
            if row.get('Symbol'):
                metadata[row['Symbol']] = row
    except Exception:
        pass
    calendar = stock_calendar(root, base)
    def work(member):
        meta = metadata.get(member['symbol'], {})
        return fetch_stock({'Symbol': member['symbol'], 'Company Name': meta.get('Company Name', member['name']),
                            'Industry': meta.get('Industry', 'Sector unavailable')},
                           base, calendar, root/'data/fno_prices', now)
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(work, extras))
    payload = {'version': 1, 'as_of': base['as_of'], 'generated_at': now.isoformat(),
               'base_generated_at': base['generated_at'], 'market': base['market'],
               'membership': listing, 'rows': rows, 'extra_count': len(rows),
               'complete_count': sum(r['complete_for_session'] for r in rows),
               'fno_count': len(listing['members']), 'combined_count': len(existing | {m['symbol'] for m in listing['members']}),
               'price_scope': 'Daily underlying stock candles; no derivative contract prices.',
               'schedule': 'After the Nifty 200 daily refresh, plus a daily backup check at 18:00 IST.'}
    write_snapshot(root, payload)
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, default=ROOT)
    args = parser.parse_args()
    result = refresh(args.output_root.resolve())
    print(json.dumps({k: result[k] for k in ('as_of', 'generated_at', 'fno_count', 'extra_count', 'combined_count', 'complete_count')}, indent=2))
    print('Membership verified:', result['membership']['verified'])
    for row in result['rows']:
        print(row['symbol'], row['data_date'], row['status'], row.get('refresh_error', ''))
