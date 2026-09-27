"""Isolated daily commodity/FX history and confirmed price structure.

Never reads or writes the Nifty price cache or stock scan outputs.
Forex OHLC is aggregated from provider hourly bars into 17:00 New York
sessions. No daily exchange-rate observations are turned into fake candles.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf

from hhhl_scanner import feature_frame

ROOT = Path(__file__).resolve().parent
UTC = timezone.utc
NY = ZoneInfo('America/New_York')
PRICE_COLUMNS = ['Open', 'High', 'Low', 'Close']


def commodity(symbol, name, unit, digits=2):
    return {'symbol': symbol, 'name': name, 'group': 'commodity', 'unit': unit,
            'digits': digits, 'kind': 'Rolling commodity futures', 'minimum_hours': 0}


def forex(symbol, name, digits=5, minimum_hours=20):
    base, counter = name.split('/')
    return {'symbol': symbol, 'name': name, 'group': 'forex', 'unit': f'{counter} per {base}',
            'digits': digits, 'kind': 'Indicative spot FX', 'minimum_hours': minimum_hours}


INSTRUMENTS = [
    commodity('GC=F', 'Gold', 'USD per troy ounce'),
    commodity('SI=F', 'Silver', 'USD per troy ounce', 3),
    commodity('HG=F', 'Copper', 'USD per pound', 4),
    commodity('PL=F', 'Platinum', 'USD per troy ounce'),
    commodity('PA=F', 'Palladium', 'USD per troy ounce'),
    commodity('CL=F', 'WTI crude oil', 'USD per barrel'),
    commodity('BZ=F', 'Brent crude oil', 'USD per barrel'),
    commodity('NG=F', 'Natural gas', 'USD per million Btu', 3),
    commodity('ZC=F', 'Corn', 'US cents per bushel'),
    commodity('ZW=F', 'Wheat', 'US cents per bushel'),
    commodity('ZS=F', 'Soybeans', 'US cents per bushel'),
    commodity('KC=F', 'Coffee', 'US cents per pound'),
    commodity('CC=F', 'Cocoa', 'USD per metric tonne'),
    commodity('SB=F', 'Sugar', 'US cents per pound'),
    commodity('CT=F', 'Cotton', 'US cents per pound'),
    forex('EURUSD=X', 'EUR/USD'), forex('GBPUSD=X', 'GBP/USD'),
    forex('JPY=X', 'USD/JPY', 3), forex('CHF=X', 'USD/CHF'),
    forex('AUDUSD=X', 'AUD/USD'), forex('CAD=X', 'USD/CAD'),
    forex('NZDUSD=X', 'NZD/USD'), forex('EURGBP=X', 'EUR/GBP'),
    forex('EURJPY=X', 'EUR/JPY', 3), forex('GBPJPY=X', 'GBP/JPY', 3),
    forex('INR=X', 'USD/INR', 4, 8),
]


def finite(value):
    return value is not None and np.isfinite(float(value))


def num(value, digits=8):
    return round(float(value), digits) if finite(value) else None


def previous_weekday(day):
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def expected_date(now):
    # Deliberately exclude the current UTC date for overnight global sessions.
    return previous_weekday(now.astimezone(UTC).date() - timedelta(days=1))


def valid_ohlc(frame):
    prices = frame[PRICE_COLUMNS]
    return (prices.notna().all(axis=1) & np.isfinite(prices).all(axis=1)
            & (prices > 0).all(axis=1)
            & (frame.High >= prices.max(axis=1)) & (frame.Low <= prices.min(axis=1)))


def prepare_prices(raw, instrument, now):
    """Validate provider bars and return genuine elapsed daily candles + audit."""
    if raw is None or raw.empty:
        raise ValueError('Provider returned no prices')
    frame = raw.copy()
    for column in PRICE_COLUMNS + ['Volume']:
        if column not in frame:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    frame = frame.loc[~frame.index.duplicated(keep='last')].sort_index()
    cutoff = expected_date(now)
    audit = {'invalid_dates': [], 'partial_dates': [], 'hour_counts': {}}
    if instrument['group'] == 'forex':
        if frame.index.tz is None:
            raise ValueError('Hourly forex prices have no timezone')
        # An hourly timestamp denotes the beginning of that hour.
        frame = frame.loc[frame.index.tz_convert(UTC) + pd.Timedelta(hours=1) <= now]
        local = frame.index.tz_convert(NY)
        labels = [d.date() + timedelta(days=int(d.hour >= 17)) for d in local]
        frame['session'] = labels
        frame = frame.loc[(frame.session <= cutoff) & frame.session.map(lambda d: d.weekday() < 5)]
        frame['valid'] = valid_ohlc(frame)
        daily = []
        for day, group in frame.groupby('session', sort=True):
            audit['hour_counts'][day.isoformat()] = len(group)
            if not group.valid.all():
                audit['invalid_dates'].append(day.isoformat())
                continue
            if len(group) < instrument['minimum_hours']:
                audit['partial_dates'].append(day.isoformat())
                continue
            daily.append({'Date': day, 'Open': group.Open.iloc[0], 'High': group.High.max(),
                          'Low': group.Low.min(), 'Close': group.Close.iloc[-1], 'Volume': np.nan})
        if not daily:
            raise ValueError('No valid completed forex sessions')
        result = pd.DataFrame(daily).set_index('Date')
    else:
        frame.index = pd.to_datetime([d.date() for d in frame.index])
        frame = frame.loc[(frame.index.date <= cutoff) & (frame.index.dayofweek < 5)]
        valid = valid_ohlc(frame) & frame.Volume.notna() & (frame.Volume > 0)
        audit['invalid_dates'] = [d.date().isoformat() for d in frame.index[~valid & (frame.Volume > 0)]]
        result = frame.loc[valid, PRICE_COLUMNS + ['Volume']]
    result.index = pd.to_datetime(result.index)
    result.index.name = 'Date'
    if len(result) < 70:
        raise ValueError('Fewer than 70 valid completed sessions')
    return result, audit


def pivots(frame):
    result = {'high': [], 'low': []}
    for kind, column in [('high', 'High'), ('low', 'Low')]:
        values = frame[column].to_numpy()
        previous = None
        for i in range(2, len(frame)-2):
            neighbors = np.r_[values[i-2:i], values[i+1:i+3]]
            confirmed = values[i] > neighbors.max() if kind == 'high' else values[i] < neighbors.min()
            if not confirmed:
                continue
            value = float(values[i])
            label = ('H' if kind == 'high' else 'L') if previous is None else (
                ('EH' if kind == 'high' else 'EL') if value == previous else
                ('HH' if value > previous else 'LH') if kind == 'high' else
                ('HL' if value > previous else 'LL'))
            result[kind].append({'kind': kind, 'label': label, 'price': num(value),
                                 'pivot_date': frame.index[i].date().isoformat(),
                                 'confirmed_on': frame.index[i+2].date().isoformat()})
            previous = value
    return result


def scan(instrument, frame, audit, now):
    work = frame.copy()
    # Price structure never uses FX volume. Zero is internal to the shared
    # indicator math; the published FX volume remains null, never fabricated.
    work['Volume'] = work.Volume.fillna(0)
    features = feature_frame(work)
    last = features.iloc[-1]
    events = pivots(frame)
    pairs = {kind: rows[-2:] for kind, rows in events.items()}
    day = frame.index[-1].date()
    enough = all(len(rows) == 2 for rows in pairs.values()) and finite(last.atr)
    rising = enough and pairs['high'][1]['price'] > pairs['high'][0]['price'] and pairs['low'][1]['price'] > pairs['low'][0]['price']
    falling = enough and pairs['high'][1]['price'] < pairs['high'][0]['price'] and pairs['low'][1]['price'] < pairs['low'][0]['price']
    structure = 'HH / HL' if rising else 'LH / LL' if falling else 'MIXED' if enough else 'UNCONFIRMED'
    invalid_recent = [d for d in audit['invalid_dates'] if d >= (day-timedelta(days=95)).isoformat()]
    partial_recent = [d for d in audit['partial_dates'] if d >= (day-timedelta(days=10)).isoformat()]
    fresh = day == expected_date(now)
    state = 'ready' if fresh and not invalid_recent and not partial_recent else 'delayed' if not fresh else 'limited'
    trigger, support = num(last.confirmed_high), num(last.confirmed_low)
    if state != 'ready' or not enough:
        status, reason = 'CAUTION', ('The latest expected weekday candle has not been supplied yet.' if not fresh else
                                    'Some recent sessions did not pass the price-coverage checks.' if invalid_recent or partial_recent else
                                    'There are not yet two confirmed highs and lows to compare.')
    elif bool(last.exit_condition):
        status, reason = 'BELOW LOW', 'The close is below the last confirmed low.'
    elif bool(last.breakout):
        status, reason = 'BREAKOUT', 'Higher highs and higher lows, with a fresh close above the confirmed high.'
    elif rising and last.Close > last.confirmed_high:
        status, reason = 'CAUTION', 'Price is already above the confirmed high, but there is no fresh crossing this session.'
    elif rising:
        status, reason = 'WATCH', 'Confirmed highs and lows are rising; a fresh close above the high is still needed.'
    else:
        status, reason = 'NO SETUP', 'The last two confirmed highs and lows are not both rising.'
    bars = []
    for stamp, r in features.tail(140).iterrows():
        bars.append({'date': stamp.date().isoformat(), **{c.lower(): num(r[c]) for c in PRICE_COLUMNS},
                     'volume': num(r.Volume, 0) if instrument['group'] == 'commodity' else None,
                     'volume_average20': num(r.volume_average20, 0) if instrument['group'] == 'commodity' else None,
                     'confirmed_high': num(r.confirmed_high), 'confirmed_low': num(r.confirmed_low),
                     'structure_breakout': bool(r.breakout), 'structure_exit': bool(r.exit_trigger)})
    return {**instrument, 'status': status, 'reason': reason, 'structure': structure,
            'data_state': state, 'data_date': day.isoformat(), 'expected_date': expected_date(now).isoformat(),
            'retrieved_at': now.isoformat(), 'close': num(last.Close), 'atr': num(last.atr),
            'fresh_breakout': bool(last.breakout), 'entry_plan': None,
            'zones': {'breakout_above': trigger, 'structure_exit_below': support,
                      'watch_band': [num(max(support, trigger-last.atr)), trigger] if rising and support < trigger else None},
            'pivots': pairs, 'chart': bars,
            'chart_swings': sorted([p for rows in events.values() for p in rows if p['pivot_date'] >= bars[0]['date']], key=lambda p: (p['pivot_date'], p['kind'])),
            'source': 'Yahoo Finance via yfinance',
            'source_url': 'https://finance.yahoo.com/quote/'+quote(instrument['symbol'], safe='')+'/history/',
            'session': '17:00 New York close; aggregated provider hourly prices' if instrument['group'] == 'forex' else 'Provider daily futures session; current UTC date excluded',
            'note': 'Indicative spot quotes, not an executable broker rate. No centralized trading volume is supplied.' if instrument['group'] == 'forex' else 'Rolling futures history; changing contracts can create gaps and affect HH/HL. Provider close is not guaranteed to be the exchange settlement.',
            'audit': {**audit, 'history_sessions': len(frame), 'invalid_recent': invalid_recent, 'partial_recent': partial_recent}}


def unavailable(instrument, previous, now, error):
    if previous and previous.get('chart'):
        result = deepcopy(previous)
        result.update(status='CAUTION', data_state='cached', reason='The latest download failed; this is the last saved chart.',
                      expected_date=expected_date(now).isoformat(), last_attempt_at=now.isoformat(), refresh_error=error)
        return result
    return {**instrument, 'status': 'CAUTION', 'reason': 'Price history is temporarily unavailable.',
            'data_state': 'unavailable', 'data_date': None, 'expected_date': expected_date(now).isoformat(),
            'chart': [], 'pivots': {'high': [], 'low': []}, 'zones': {}, 'chart_swings': [],
            'entry_plan': None, 'structure': 'UNKNOWN', 'close': None, 'retrieved_at': None,
            'last_attempt_at': now.isoformat(), 'refresh_error': error}


def refresh_one(instrument, previous, now, root):
    try:
        raw = yf.Ticker(instrument['symbol']).history(period='1y', interval='1h' if instrument['group']=='forex' else '1d',
                                                      auto_adjust=False, actions=False, timeout=25)
        frame, audit = prepare_prices(raw, instrument, now)
        path = root/'data/global_prices'/(instrument['symbol'].replace('=', '_')+'.csv')
        if path.exists():
            old = pd.read_csv(path, index_col=0, parse_dates=True)
            # Replace only verified overlapping sessions; retain earlier history.
            frame = pd.concat([old, frame]).loc[lambda d: ~d.index.duplicated(keep='last')].sort_index()
        result = scan(instrument, frame, audit, now)
        if previous and previous.get('data_date') and result['data_date'] < previous['data_date']:
            raise ValueError('Provider history regressed')
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        frame.to_csv(temporary, float_format='%.8f')
        temporary.replace(path)
        return result
    except Exception as exc:
        return unavailable(instrument, previous, now, type(exc).__name__+': '+str(exc)[:160])


def write_snapshot(root, snapshot):
    encoded = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, separators=(',', ':'))+'\n'
    for relative in ['docs/global_markets.json', 'public/data/global_markets.json']:
        path = root/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(encoded, encoding='utf-8')
        temporary.replace(path)


def refresh(root=ROOT, now=None):
    now = now or datetime.now(UTC)
    previous_path = root/'docs/global_markets.json'
    old = json.loads(previous_path.read_text(encoding='utf-8')) if previous_path.exists() else {}
    by_symbol = {r['symbol']: r for r in old.get('rows', [])}
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(lambda instrument: refresh_one(instrument, by_symbol.get(instrument['symbol']), now, root), INSTRUMENTS))
    snapshot = {'schema_version': 1, 'generated_at': now.isoformat(), 'expected_date': expected_date(now).isoformat(),
                'source_project': 'https://github.com/ranaroussi/yfinance', 'instrument_count': len(rows),
                'available_count': sum(bool(r['chart']) for r in rows),
                'ready_count': sum(r['data_state']=='ready' for r in rows), 'rows': rows,
                'scope': 'Widely followed benchmarks and currency pairs; not a live ranking by global trading volume.',
                'refresh_schedule': 'Automatic checks at 04:35, 07:35 and 10:35 UTC, Monday to Saturday.',
                'signal_scope': 'Price structure only. Nifty gates and stock price/turnover screens do not apply. These labels are not a backtested commodity or forex trading system.'}
    write_snapshot(root, snapshot)
    return snapshot


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, default=ROOT)
    args = parser.parse_args()
    result = refresh(args.output_root.resolve())
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))
    for row in result['rows']:
        print(row['symbol'], row['data_state'], row['data_date'], row['status'], row.get('refresh_error', ''))
