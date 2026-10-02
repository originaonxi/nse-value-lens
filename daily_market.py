"""Dated NSE disclosures and EOD breadth. Never changes prices or scanner rules."""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import time
import zipfile
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent
IST = ZoneInfo('Asia/Kolkata')
ARCHIVE = 'https://nsearchives.nseindia.com'
HISTORY = 'https://www.nseindia.com/api/historicalOR/bulk-block-short-deals'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Accept': 'text/csv,application/json,*/*',
           'Referer': 'https://www.nseindia.com/'}
SYMBOL = re.compile(r'^[A-Z0-9&_.-]+$')


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n', encoding='utf-8')
    temp.replace(path)


def number(value, positive=False):
    result = float(str(value).replace(',', '').strip())
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError('Invalid numeric value')
    return result


def iso_date(value):
    for fmt in ('%Y-%m-%d', '%d-%b-%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(str(value).strip(), fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError('Invalid report date')


def rows_csv(raw):
    text = raw.decode('utf-8-sig').strip()
    if not text or '<html' in text[:300].lower() or '<!doctype' in text[:300].lower():
        raise ValueError('Expected CSV report')
    reader = csv.DictReader(io.StringIO(text))
    reader.fieldnames = [s.strip() for s in (reader.fieldnames or [])]
    return reader


def parse_deals(raw, kind, requested=None, historical=False):
    if historical:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
            raise ValueError('Invalid NSE historical response')
        aliases = {'Date': 'BD_DT_DATE', 'Symbol': 'BD_SYMBOL', 'Security Name': 'BD_SCRIP_NAME',
                   'Client Name': 'BD_CLIENT_NAME', 'Buy/Sell': 'BD_BUY_SELL',
                   'Quantity Traded': 'BD_QTY_TRD', 'Trade Price / Wght. Avg. Price': 'BD_TP_WATP',
                   'Remarks': 'BD_REMARKS'}
        rows = [{k: row.get(v) for k, v in aliases.items()} for row in payload['data']]
    else:
        reader = rows_csv(raw)
        needed = {'Date', 'Symbol', 'Security Name', 'Client Name', 'Buy/Sell',
                  'Quantity Traded', 'Trade Price / Wght. Avg. Price'}
        if not needed.issubset(reader.fieldnames):
            raise ValueError('Disclosure columns missing')
        rows = list(reader)
    result = []
    for row in rows:
        day = iso_date(row['Date'])
        if requested and day != requested:
            raise ValueError('NSE returned a different disclosure session')
        symbol = str(row['Symbol']).strip().upper()
        side = str(row['Buy/Sell']).strip().upper()
        client = str(row['Client Name'] or '').strip()
        qty = number(row['Quantity Traded'], positive=True)
        price = number(row['Trade Price / Wght. Avg. Price'], positive=True)
        if not SYMBOL.fullmatch(symbol) or side not in ('BUY', 'SELL') or not client or qty != int(qty):
            raise ValueError('Invalid disclosure row')
        result.append({'date': day, 'kind': kind, 'symbol': symbol,
                       'name': str(row['Security Name'] or '').strip(), 'client': client,
                       'side': side, 'quantity': int(qty), 'price': price,
                       'value_crore': round(qty * price / 1e7, 6),
                       'remarks': str(row.get('Remarks') or '').strip()})
    if not result:
        # An undated, empty endpoint response cannot prove a completed zero-deal report.
        raise ValueError('Empty NSE response has no dated publication confirmation')
    return result


def parse_bhavcopy(raw, expected):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith('.csv')]
        if len(names) != 1 or archive.getinfo(names[0]).file_size > 40_000_000:
            raise ValueError('Unexpected bhavcopy archive')
        reader = rows_csv(archive.read(names[0]))
        required = {'TradDt', 'TckrSymb', 'SctySrs', 'ClsPric', 'PrvsClsgPric', 'TtlTradgVol', 'TtlTrfVal'}
        if not required.issubset(reader.fieldnames):
            raise ValueError('Bhavcopy columns missing')
        rows, seen, excluded = [], set(), 0
        for row in reader:
            if iso_date(row['TradDt']) != expected:
                raise ValueError('Bhavcopy session mismatch')
            if row['SctySrs'].strip() != 'EQ':
                continue
            symbol = row['TckrSymb'].strip()
            if symbol in seen or not SYMBOL.fullmatch(symbol):
                raise ValueError('Duplicate or invalid EQ symbol')
            seen.add(symbol)
            try:
                close, previous = number(row['ClsPric'], True), number(row['PrvsClsgPric'], True)
                volume, turnover = number(row['TtlTradgVol']), number(row['TtlTrfVal'])
                if volume <= 0 or turnover < 0:
                    raise ValueError('Non-traded security')
            except (ValueError, TypeError):
                excluded += 1
                continue
            rows.append({'symbol': symbol, 'name': row.get('FinInstrmNm', symbol).strip(),
                         'close': close, 'previous_close': previous,
                         'change_pct': round((close / previous - 1) * 100, 4),
                         'volume': int(volume), 'turnover_crore': round(turnover / 1e7, 4)})
    if not rows:
        raise ValueError('Bhavcopy has no usable EQ rows')
    return rows, excluded


def breadth(rows):
    advances = sum(r['close'] > r['previous_close'] for r in rows)
    declines = sum(r['close'] < r['previous_close'] for r in rows)
    up = sum(r['volume'] for r in rows if r['close'] > r['previous_close'])
    down = sum(r['volume'] for r in rows if r['close'] < r['previous_close'])
    return {'count': len(rows), 'advances': advances, 'declines': declines,
            'unchanged': len(rows) - advances - declines,
            'ad_ratio': round(advances / declines, 3) if declines else None,
            'up_volume': up, 'down_volume': down,
            'up_volume_pct': round(100 * up / (up + down), 2) if up + down else None,
            'turnover_crore': round(sum(r['turnover_crore'] for r in rows), 2)}


def parse_indices(raw, expected):
    reader = rows_csv(raw)
    if not {'Index Name', 'Index Date', 'Closing Index Value', 'Change(%)'}.issubset(reader.fieldnames):
        raise ValueError('Index columns missing')
    rows = []
    for row in reader:
        if iso_date(row['Index Date']) != expected:
            raise ValueError('Index session mismatch')
        try:
            close, change = number(row['Closing Index Value'], True), number(row['Change(%)'])
        except ValueError:
            continue  # Some index variants publish a dash; never invent their values.
        rows.append({'name': row['Index Name'].strip(), 'close': close, 'change_pct': change})
    if not rows or not any(r['name'] == 'Nifty 50' for r in rows):
        raise ValueError('Empty index report')
    return rows


def membership(root):
    members = {}
    with (root / 'nifty200.csv').open(encoding='utf-8-sig', newline='') as stream:
        for r in csv.DictReader(stream):
            members[r['Symbol']] = {'name': r['Company Name'], 'sector': r['Industry'],
                                     'nifty200': True, 'fno': False}
    extra = read_json(root / 'docs/hhhl_fno.json', {})
    sectors = {r['symbol']: r.get('sector', 'Unknown') for r in extra.get('rows', [])}
    for r in extra.get('membership', {}).get('members', []):
        members.setdefault(r['symbol'], {'name': r.get('name', r['symbol']),
                                          'sector': sectors.get(r['symbol'], 'Unknown'), 'nifty200': False})['fno'] = True
    return members, {'nifty200': sum(m['nifty200'] for m in members.values()),
                     'fno': sum(m['fno'] for m in members.values()), 'all': len(members),
                     'fno_checked_at': extra.get('membership', {}).get('retrieved_at'),
                     'source_note': 'Membership from the existing site snapshots; historical membership is not reconstructed.'}


def moving_average_breadth(root, members, day):
    values = {}
    for symbol in members:
        paths = [root / 'data/hhhl_prices' / (symbol + '.NS.csv'), root / 'data/fno_prices' / (symbol + '.NS.csv')]
        path = next((p for p in paths if p.exists()), None)
        if path is None:
            continue
        with path.open(encoding='utf-8-sig') as stream:
            bars = [r for r in csv.DictReader(stream) if r['Date'][:10] <= day and float(r.get('Volume', 0)) > 0]
        if not bars or bars[-1]['Date'][:10] != day:
            continue
        closes = [number(r['Close'], True) for r in bars]
        values[symbol] = {str(n): closes[-1] > sum(closes[-n:]) / n for n in (20, 50, 200) if len(closes) >= n}
    return values


def expected_session(now, calendar):
    local = now.astimezone(IST)
    cutoff = local.date() if (local.hour, local.minute) >= (16, 0) else local.date() - timedelta(days=1)
    holidays = set(calendar.get('holidays', [])) if calendar.get('year') == cutoff.year else set()
    special = set(calendar.get('special_sessions', []))
    while (cutoff.weekday() >= 5 and cutoff.isoformat() not in special) or cutoff.isoformat() in holidays:
        cutoff -= timedelta(days=1)
    return cutoff.isoformat()


class Downloader:
    def __init__(self, root):
        self.root = root

    def get(self, url):
        last = None
        for attempt in range(2):
            try:
                r = requests.get(url, headers=HEADERS, timeout=20)
                r.raise_for_status()
                if len(r.content) > 40_000_000:
                    raise ValueError('Unexpected response size')
                sha = hashlib.sha256(r.content).hexdigest()
                path = self.root / '.cache/daily-market' / sha
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(r.content)
                return r.content, {'url': url, 'sha256': sha, 'retrieved_at': datetime.now(timezone.utc).isoformat()}
            except (requests.RequestException, ValueError) as exc:
                last = exc
                if attempt == 0:
                    time.sleep(1)
        raise last


def retain(previous, expected, error):
    value = dict(previous or {})
    value.update(state='unavailable' if not value.get('as_of') else 'stale', error=str(error)[:240], expected_session=expected)
    return value


def refresh_deals(kind, expected, previous, download, root, members):
    error = None
    for url, historical in [(f'{ARCHIVE}/content/equities/{kind}.csv', False),
                            (HISTORY + f'?optionType={kind}_deals&from={date.fromisoformat(expected):%d-%m-%Y}&to={date.fromisoformat(expected):%d-%m-%Y}', True)]:
        try:
            raw, source = download.get(url)
            rows = parse_deals(raw, kind, requested=expected, historical=historical)
            for row in rows:
                row['membership'] = members.get(row['symbol'], {'nifty200': False, 'fno': False})
            result = {'as_of': expected, 'state': 'fresh', 'expected_session': expected,
                      'source': source, 'rows': rows, 'count': len(rows),
                      'tracked_symbols': sorted({r['symbol'] for r in rows if r['symbol'] in members})}
            write_json(root / 'data/daily_market_history' / f'{expected}-{kind}.json', result)
            return result
        except (ValueError, KeyError, TypeError, requests.RequestException) as exc:
            error = exc
    return retain(previous, expected, error)


def refresh_market(expected, previous, download, root, members):
    stamp = date.fromisoformat(expected).strftime('%Y%m%d')
    url = f'{ARCHIVE}/content/cm/BhavCopy_NSE_CM_0_0_0_{stamp}_F_0000.csv.zip'
    try:
        raw, source = download.get(url)
        rows, excluded = parse_bhavcopy(raw, expected)
        if len(rows) < 1000:
            raise ValueError('Incomplete NSE-wide EQ coverage')
        averages = moving_average_breadth(root, members, expected)
        for row in rows:
            row['membership'] = members.get(row['symbol'], {'nifty200': False, 'fno': False})
            row['above_sma'] = averages.get(row['symbol'], {})
        return {'as_of': expected, 'state': 'fresh', 'expected_session': expected, 'source': source,
                'rows': rows, 'breadth': breadth(rows), 'excluded_eq_rows': excluded,
                'scope': 'Traded NSE EQ securities with valid previous closes. Not all BSE/NSE listings.',
                'ma_scope': 'Existing adjusted daily stock histories dated to this session; stale/short histories excluded.'}
    except (ValueError, KeyError, TypeError, zipfile.BadZipFile, requests.RequestException) as exc:
        return retain(previous, expected, exc)


def refresh_indices(expected, previous, download):
    stamp = date.fromisoformat(expected).strftime('%d%m%Y')
    try:
        raw, source = download.get(f'{ARCHIVE}/content/indices/ind_close_all_{stamp}.csv')
        return {'as_of': expected, 'state': 'fresh', 'expected_session': expected,
                'source': source, 'rows': parse_indices(raw, expected)}
    except (ValueError, KeyError, TypeError, requests.RequestException) as exc:
        return retain(previous, expected, exc)


def refresh(root=ROOT, now=None):
    now = now or datetime.now(timezone.utc)
    previous = read_json(root / 'docs/daily_market.json', {})
    calendar = read_json(root / 'data/hhhl_calendar.json', {})
    download = Downloader(root)
    calendar_error = None
    # Independent calendar refresh: this job need not wait for a scanner job.
    try:
        raw, calendar_source = download.get('https://www.nseindia.com/api/holiday-master?type=trading')
        holidays = [iso_date(r['tradingDate']) for r in json.loads(raw)['CM']]
        holidays = [d for d in holidays if d.startswith(str(now.astimezone(IST).year))]
        if not holidays:
            raise ValueError('Current holiday calendar missing')
        calendar = {'year': now.astimezone(IST).year, 'holidays': holidays, 'verified': True,
                    'checked_on': now.astimezone(IST).date().isoformat(), 'source': calendar_source['url']}
        write_json(root / 'data/daily_market_calendar.json', calendar)
    except (ValueError, KeyError, requests.RequestException) as exc:
        saved = read_json(root / 'data/daily_market_calendar.json', calendar)
        if saved.get('year') == now.astimezone(IST).year:
            calendar = saved
        calendar_error = str(exc)[:200]
    expected = expected_session(now, calendar)
    members, coverage = membership(root)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {'bulk': pool.submit(refresh_deals, 'bulk', expected, previous.get('bulk'), download, root, members),
                'block': pool.submit(refresh_deals, 'block', expected, previous.get('block'), download, root, members),
                'market': pool.submit(refresh_market, expected, previous.get('market'), download, root, members),
                'indices': pool.submit(refresh_indices, expected, previous.get('indices'), download)}
        parts = {name: job.result() for name, job in jobs.items()}
    # Bounded catch-up of missed disclosures; old reports keep their original dates.
    history_errors = []
    cursor = date.fromisoformat(expected) - timedelta(days=1)
    for _ in range(7):
        day = cursor.isoformat()
        cursor -= timedelta(days=1)
        if date.fromisoformat(day).weekday() >= 5 or day in calendar.get('holidays', []):
            continue
        for kind in ('bulk', 'block'):
            path = root / 'data/daily_market_history' / f'{day}-{kind}.json'
            if path.exists():
                continue
            url = HISTORY + f'?optionType={kind}_deals&from={date.fromisoformat(day):%d-%m-%Y}&to={date.fromisoformat(day):%d-%m-%Y}'
            try:
                raw, source = download.get(url)
                rows = parse_deals(raw, kind, requested=day, historical=True)
                write_json(path, {'as_of': day, 'state': 'archived', 'source': source, 'rows': rows})
            except (ValueError, KeyError, TypeError, requests.RequestException) as exc:
                history_errors.append({'date': day, 'kind': kind, 'error': str(exc)[:120]})
    recent = []
    for path in sorted((root / 'data/daily_market_history').glob('*.json'))[-60:]:
        record = read_json(path, {})
        if expected >= record.get('as_of', '') >= (date.fromisoformat(expected) - timedelta(days=30)).isoformat():
            for row in record.get('rows', []):
                row['membership'] = members.get(row['symbol'], {'nifty200': False, 'fno': False})
                recent.append(row)
    payload = {'version': 1, 'as_of': expected, 'attempted_at': now.isoformat(),
               'calendar': {**calendar, 'refresh_error': calendar_error}, 'coverage': coverage,
               'state': 'fresh' if all(p['state'] == 'fresh' for p in parts.values()) else 'partial',
               'schedule': 'Every calendar day at 19:15, 21:15, 00:15 and 08:15 IST; plus a Railway backup.',
               'recent_deals': recent, 'history_errors': history_errors, **parts}
    for path in (root / 'docs/daily_market.json', root / 'public/data/daily_market.json'):
        write_json(path, payload)
    print(json.dumps({'as_of': expected, 'state': payload['state'],
                      'components': {k: v['state'] for k, v in parts.items()},
                      'tracked_bulk': parts['bulk'].get('tracked_symbols', []),
                      'tracked_block': parts['block'].get('tracked_symbols', []),
                      'eq_securities': parts['market'].get('breadth', {}).get('count'),
                      'history_gaps': len(history_errors)}), flush=True)
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--strict', action='store_true', help='Fail job after publishing status if current reports are incomplete')
    args = parser.parse_args()
    data = refresh()
    if args.strict and data['state'] != 'fresh':
        raise SystemExit(1)
