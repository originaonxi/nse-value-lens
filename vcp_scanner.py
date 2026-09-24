"""Publish a dated, complete-universe VCP watchlist using the research rules.

Run after hhhl_refresh.py; both scanners share the maintained adjusted OHLCV cache.
No orders are placed. Partial weeks never enter the weekly screen.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from hhhl_scanner import read_prices, number
from swing_research import publish
from vcp_research import daily_features, weekly_features, update_pivots, pattern_at, make_orders

ROOT = Path(__file__).resolve().parent
MODES = {
    'three': 'Strict: three contractions',
    'three_or_two_70': 'Three, or two with 70% tightening',
    'three_or_two_smaller': 'Exploratory: three, or two smaller contractions',
}
DEFAULT_MODE = 'three_or_two_70'


def pattern_state(d, pattern, by_week, ends):
    """A previously touched trigger is not advertised again as a fresh entry.

    Reuse the research order schedule, which only exposes completed weekly
    patterns on the following session. A touch is an observation, not a fill.
    """
    trigger = pattern['pivot'] * 1.001
    for order in make_orders('', d, by_week, ends, 'intraday_pivot'):
        if order['pattern']['id'] != pattern['id']:
            continue
        bar = d.iloc[order['day']]
        if np.isfinite(bar.High) and bar.High >= trigger:
            return 'TRIGGERED', str(d.index[order['day']].date())
    after_screen = d.iloc[ends[-1]+1:]
    if (after_screen.Low < pattern['final_low']).any():
        date = after_screen.index[after_screen.Low < pattern['final_low']][0]
        return 'INVALIDATED', str(date.date())
    if (after_screen.Close > pattern['pivot']).any():
        date = after_screen.index[after_screen.Close > pattern['pivot']][0]
        return 'EXPIRED', str(date.date())
    if d.Close.iloc[-1] <= pattern['final_low']:
        return 'INVALIDATED', str(d.index[-1].date())
    return 'WATCH', None


def scan_stock(meta, frame, as_of, invalid_dates=()):
    d = daily_features(frame)
    w = weekly_features(d, as_of)
    valid = d.Close.notna() & d.Volume.gt(0)
    last_date = str(d.index[valid][-1].date()) if valid.any() else None
    last = d.loc[valid].iloc[-1] if valid.any() else None
    # Two years cover the year-long recurring-high screen and its 252-day warmup.
    enough = int(valid.sum()) >= 512
    recent = d.iloc[-520:]
    after_first = recent.loc[recent.index >= d.index[valid].min()] if valid.any() else recent
    missing = [str(t.date()) for t in after_first.index[after_first.Close.isna()]]
    jumps = [str(t.date()) for t in recent.index[recent.Close.pct_change(fill_method=None).abs() > .4]]
    ready = last_date == as_of and enough and not missing and not jumps and not w.empty
    checks = []
    def check(key, label, passed, detail):
        checks.append({'key': key, 'label': label, 'pass': bool(passed), 'detail': detail})
    check('data', 'Complete, current history', ready,
          f"Last candle: {last_date or 'missing'}; {int(valid.sum())} sessions; "
          f"{len(missing)} recent gaps; {len(jumps)} large price jumps under review.")
    row = {'symbol': meta['Symbol'], 'name': meta['Company Name'], 'sector': meta['Industry'],
           'data_date': last_date, 'data_ready': ready, 'close': number(last.Close) if last is not None else None,
           'weekly_date': str(w.index[-1].date()) if not w.empty else None,
           'atr20': number(last.atr20) if last is not None else None,
           'daily_volume_ratio': number(last.Volume / last.volume50_prior) if last is not None else None,
           'checks': checks, 'modes': {}, 'chart': [], 'pivots': [],
           'audit': {'missing_sessions': missing, 'large_jumps': jumps, 'invalid_dates': list(invalid_dates)}}
    if w.empty:
        for mode in MODES:
            row['modes'][mode] = {'state': 'DATA', 'pattern': None, 'reason': 'No complete weekly history.'}
        return row
    weekly = w.iloc[-1]
    pct_high = number((weekly.Close / weekly.high252 - 1)*100)
    pct_low = number((weekly.Close / weekly.low252 - 1)*100)
    check('price', 'Price at least ₹30', weekly.QuoteClose >= 30, f'Weekly adjusted close ₹{number(weekly.QuoteClose)}')
    check('high', 'Within 25% of the 52-week high', weekly.Close >= .75*weekly.high252, f'{pct_high}% from high')
    check('low', 'At least 100% above the 52-week low', weekly.Close >= 2*weekly.low252, f'{pct_low}% above low')
    check('trend', 'Close > 50 DMA > 200 DMA', weekly.Close > weekly.sma50 > weekly.sma200,
          f'Close {number(weekly.Close)} · 50 DMA {number(weekly.sma50)} · 200 DMA {number(weekly.sma200)}')
    check('rising', '200 DMA rising for 13 weekly readings', weekly.rising200, 'Each of the last 13 weekly changes must be positive.')
    check('high_frequency', 'Recurring 52-week highs', weekly.high_frequency, 'A new high in both halves of the past year; no gap longer than 26 weeks.')
    check('liquidity', 'At least ₹1 crore average daily turnover', weekly.turnover20 >= 1e7,
          f'20-session average ₹{number(weekly.turnover20/1e7)} crore')
    row.update({'screen_pass': bool(weekly.screen), 'from_high_pct': pct_high, 'above_low_pct': pct_low,
                'weekly_exit_reference': number(weekly.sma10)})
    by_mode = {mode: {} for mode in MODES}
    points = []
    arrays = (w.High.to_numpy(), w.Low.to_numpy(), w.complete.to_numpy())
    for i in range(len(w)):
        points = update_pivots(points, w, i, arrays)
        if not w.screen.iloc[i]:
            continue
        three = pattern_at(w, points, i, 3)
        for mode, pattern in [('three', three),
                              ('three_or_two_70', three or pattern_at(w, points, i, 2, '70')),
                              ('three_or_two_smaller', three or pattern_at(w, points, i, 2))]:
            if pattern:
                by_mode[mode][int(w.end_pos.iloc[i])] = pattern
    ends = list(w.end_pos.astype(int))
    for mode in MODES:
        pattern = by_mode[mode].get(ends[-1])
        state, event_date = ('SCREEN_ONLY' if weekly.screen else 'NO_SETUP'), None
        reason = ('Weekly stock filters pass; no confirmed VCP under this definition.' if weekly.screen
                  else 'Weekly stock filters do not all pass.')
        preview = None
        if pattern:
            state, event_date = pattern_state(d, pattern, by_mode[mode], ends)
            reason = {'WATCH': 'Confirmed weekly VCP; awaiting a new daily trigger.',
                      'TRIGGERED': f'Trigger already touched on {event_date}; not a fresh pending entry.',
                      'INVALIDATED': f'Final contraction low failed on {event_date}.',
                      'EXPIRED': f'Close passed the pivot on {event_date}; weekly watch expired.'}[state]
            if state == 'WATCH' and ready and np.isfinite(last.atr20):
                trigger = pattern['pivot']*1.001
                distance = min(2*last.atr20, .1*trigger)
                preview = {'trigger': number(trigger), 'stop_at_trigger': number(trigger-distance),
                           'risk_pct': number(100*distance/trigger),
                           'distance_pct': number(100*(trigger/last.Close-1))}
        if not ready:
            state, preview, reason = 'DATA', None, 'Incomplete, stale or suspect history; setup eligibility is blocked.'
        row['modes'][mode] = {'state': state, 'pattern': pattern, 'event_date': event_date,
                              'reason': reason, 'preview': preview}
    row['chart'] = [{'date': str(t.date()), **{k.lower(): number(v[k]) for k in ['Open','High','Low','Close','Volume']},
                     'sma10': number(v.sma10)} for t, v in w.iloc[-78:].iterrows()]
    row['pivots'] = [{'kind': p['kind'], 'price': number(p['price']), 'date': str(w.index[p['week']].date()),
                      'confirmed_on': str(w.index[p['confirmed_week']].date())} for p in points]
    return row


def build(as_of, cache_dir=ROOT/'data/hhhl_prices', universe_path=ROOT/'nifty200.csv'):
    meta = pd.read_csv(universe_path)
    if len(meta) != 200 or meta.Symbol.nunique() != 200:
        raise ValueError('Expected exactly 200 unique Nifty 200 constituents')
    frames, invalid, failures = {}, {}, {}
    for symbol in meta.Symbol:
        try:
            d, invalid[symbol] = read_prices(cache_dir/(symbol+'.NS.csv'), as_of)
            frames[symbol] = d.loc[d.Volume > 0]
        except (FileNotFoundError, ValueError, KeyError, pd.errors.EmptyDataError) as exc:
            failures[symbol] = type(exc).__name__
            frames[symbol] = pd.DataFrame(columns=['Open','High','Low','Close','Volume'], index=pd.DatetimeIndex([]))
    counts = Counter(t for frame in frames.values() for t in frame.index)
    calendar = pd.DatetimeIndex(sorted(t for t, n in counts.items() if n >= 100))
    # An absent target session is kept as missing, never silently backdated.
    calendar = calendar.union(pd.DatetimeIndex([pd.Timestamp(as_of)]))
    rows = []
    for record in meta.to_dict('records'):
        d = frames[record['Symbol']].reindex(calendar).astype(float)
        d['QuoteClose'] = d.Close  # Current-scale price floor; see published methodology.
        rows.append(scan_stock(record, d, as_of, invalid.get(record['Symbol'], [])))
    return {'version': 1, 'as_of': as_of, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'universe_count': 200, 'complete_count': sum(r['data_date'] == as_of for r in rows),
            'ready_count': sum(r['data_ready'] for r in rows),
            'weekly_as_of': max((r['weekly_date'] for r in rows if r['weekly_date']), default=None),
            'default_mode': DEFAULT_MODE, 'modes': MODES, 'rows': rows,
            'counts': {m: dict(Counter(r['modes'][m]['state'] for r in rows)) for m in MODES},
            'source_errors': failures,
            'methodology': [
                'End-of-day data. Weekly filters update only after a completed Friday-labelled week; daily candles track entry levels in between.',
                'The ₹30 screen uses the maintained dividend/split-adjusted price scale. This is a current scan, not an exact historical nominal-price reconstruction.',
                'Confirmed weekly pivots need one complete later week. Bases span 4–26 weeks; the last contraction must be within 8 weeks. Pullbacks shrink in price and do not lengthen in time.',
                'Final pullback volume must be lower than the previous pullback, preceding rally and prior 10-week average. Up-week volume must exceed down-week volume over the base.',
                'Entry reference is the final swing high plus 0.1%. An intraday touch is not proof of an executable fill. Do not chase already-triggered patterns or gaps above 5% of the pivot.',
                'Initial stop: 2 × prior completed daily ATR20, capped at 10% of actual entry. Displayed stop assumes a fill at the trigger; gaps and costs can increase loss.',
                'Weekly exit reference: after a weekly close below the 10-week SMA, exit at the next session open, subject to the initial stop. The website does not track holdings or place orders.',
                'No market-index gate or earnings/sales filter. The book image’s fundamental analysis is not modeled. All variants remain exploratory; the backtest did not establish a reliable profitable edge.',
            ]}


def run():
    run_id = os.getenv('GITHUB_RUN_ID', 'local-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    status = {'version': 1, 'as_of': datetime.now(timezone.utc).date().isoformat(),
              'run_id': run_id, 'state': 'failed', 'attempted_at': datetime.now(timezone.utc).isoformat()}
    try:
        source = json.loads((ROOT/'docs/hhhl_refresh_status.json').read_text(encoding='utf-8'))
        as_of = source['scan_as_of']
        status.update({'as_of': as_of, 'target_session': source['target_session'], 'source_run_id': source['run_id']})
        if os.getenv('GITHUB_RUN_ID') and source['run_id'] != run_id:
            raise ValueError('Current price-refresh status was not published by this workflow run')
        if source['state'] in ('failed', 'waiting'):
            raise ValueError('Price refresh is '+source['state']+'; retaining previous dated VCP scan')
        snapshot = build(as_of)
        previous_path = ROOT/'docs/vcp_scan.json'
        if previous_path.exists() and json.loads(previous_path.read_text())['as_of'] > as_of:
            raise ValueError('Refusing to move the published scan backwards')
        if snapshot['complete_count'] < 190:
            raise ValueError('Fewer than 190 current prices; retaining previous dated VCP scan')
        snapshot['refresh_run_id'] = run_id
        snapshot['source_run_id'] = source['run_id']
        snapshot['universe_note'] = source.get('universe_note', 'Cached Nifty 200 membership')
        status.update({'state': 'fresh' if source['state'] == 'fresh' and snapshot['complete_count'] == 200 else 'partial',
                       'snapshot_run_id': run_id, 'scan_as_of': as_of,
                       'message': f"{snapshot['complete_count']}/200 current prices; {snapshot['ready_count']}/200 with sufficient, clean VCP history.",
                       'counts': snapshot['counts']})
        publish('vcp_scan', snapshot)
    except Exception as exc:
        status['message'] = type(exc).__name__+': '+str(exc)[:300]
    publish('vcp_refresh_status', status)
    print(json.dumps(status, indent=2))
    return status


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    raise SystemExit(1 if run()['state'] == 'failed' else 0)
