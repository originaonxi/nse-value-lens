"""Causal weekly VCP experiment. Price/volume proxy, current-member universe.

The frozen specification is research/vcp/plan.json. No live scanner is changed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import hashlib
import itertools
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'research' / 'vcp'
CACHE = ROOT / '.cache' / 'vcp'
PLAN = json.loads((OUT / 'plan.json').read_text(encoding='utf-8'))
OHLC = ['Open', 'High', 'Low', 'Close']


def json_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')


def wilder(values, n=20):
    values = np.asarray(values, float)
    result = np.full(len(values), np.nan)
    previous = np.nan
    seed = []
    for i, value in enumerate(values):
        if not np.isfinite(value):
            previous, seed = np.nan, []
            continue
        if not np.isfinite(previous):
            seed.append(value)
            if len(seed) < n:
                continue
            previous = float(np.mean(seed))
        else:
            previous = (previous * (n - 1) + value) / n
        result[i] = previous
    return result


def load_prices(path, as_of):
    raw = pd.read_csv(path, index_col=0, parse_dates=True).sort_index()
    raw = raw.loc[raw.index <= as_of]
    if raw.index.has_duplicates:
        raise ValueError(f'Duplicate dates in {path.name}')
    valid = (raw[OHLC + ['Volume']].notna().all(axis=1)
             & (raw[OHLC] > 0).all(axis=1)
             & (raw.High >= raw[OHLC].max(axis=1) - 1e-8)
             & (raw.Low <= raw[OHLC].min(axis=1) + 1e-8)
             & (raw.Volume >= 0))
    factor = raw['Adj Close'] / raw.Close
    valid &= np.isfinite(factor) & (factor > 0)
    d = raw.loc[valid, OHLC + ['Volume']].copy()
    d[OHLC] = d[OHLC].mul(factor[valid], axis=0)
    # Yahoo unadjusted OHLC is still split-adjusted. Undo subsequent splits ONLY
    # for the nominal-price screen. Relative indicators use consistent adj OHLC.
    splits = raw['Stock Splits'].replace(0, 1).fillna(1)
    future_splits = splits.iloc[::-1].cumprod().iloc[::-1] / splits
    d['QuoteClose'] = raw.Close[valid] * future_splits[valid]
    audit = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
             'raw_rows': len(raw), 'invalid_rows': int((~valid).sum()),
             'zero_volume_rows': int((d.Volume == 0).sum()),
             'first': str(d.index[0].date()), 'last': str(d.index[-1].date()),
             'large_adjusted_jumps': [str(t.date()) for t in
                                      d.index[d.Close.pct_change(fill_method=None).abs() > .4]]}
    return d, audit


def load_universe(as_of):
    meta = pd.read_csv(ROOT / 'nifty200.csv')
    if len(meta) != 200 or meta.Symbol.nunique() != 200:
        raise ValueError('Expected all 200 unique members')
    loaded, audit = {}, {}
    for symbol in meta.Symbol:
        path = CACHE / (symbol + '.NS.csv')
        if not path.exists():
            raise ValueError(f'Missing {symbol}; do not silently omit it')
        loaded[symbol], audit[symbol] = load_prices(path, as_of)
    frequency = Counter(t for d in loaded.values() for t in d.index[d.Volume > 0])
    calendar = pd.DatetimeIndex(sorted(t for t, count in frequency.items() if count >= 100))
    for symbol, d in loaded.items():
        good = d.index.isin(calendar) & (d.Volume > 0)
        audit[symbol]['removed_nontrading'] = int((~good).sum())
        d = d.loc[good]
        audit[symbol]['missing_sessions_after_first'] = int(
            ((calendar >= d.index.min()) & (calendar <= d.index.max())).sum() - len(d))
        loaded[symbol] = d.reindex(calendar)
    market, market_audit = load_prices(CACHE / 'CNX200.csv', as_of)
    market = market.reindex(calendar)
    repair_path = CACHE/'index_price_repairs.json'
    if repair_path.exists():
        repairs = json.loads(repair_path.read_text())
        market, applied = repair_market(market,repairs['rows'])
        market_audit['official_repairs'] = applied
        market_audit['official_repair_source'] = repairs['url']
        market_audit['official_repair_sha256'] = hashlib.sha256(repair_path.read_bytes()).hexdigest()
    market['sma200'] = market.Close.rolling(200).mean()
    market['gate'] = (market.Close > market.sma200).fillna(False)
    audit_report = {'as_of': as_of, 'universe_count': len(meta),
                    'universe_sha256': hashlib.sha256((ROOT/'nifty200.csv').read_bytes()).hexdigest(),
                    'calendar_first': str(calendar[0].date()), 'calendar_last': str(calendar[-1].date()),
                    'calendar_sessions': len(calendar), 'calendar_rule': 'Positive volume in >=100 stocks',
                    'benchmark': market_audit, 'benchmark_missing': [str(t.date()) for t in market.index[market.Close.isna()]],
                    'stocks': audit, 'historical_membership': 'Unavailable; current-member cohort only'}
    return loaded, market, dict(zip(meta.Symbol, meta.Industry)), audit_report


def repair_market(market, rows):
    """Only fill genuinely missing index candles from validated official records."""
    market = market.copy()
    applied = []
    for row in rows:
        if row['INDEX_NAME'].upper() != 'NIFTY 200':
            raise ValueError('Wrong index in official repair')
        date = pd.to_datetime(row['HistoricalDate'],format='%d %b %Y')
        if date not in market.index:
            continue
        values = np.array([float(row[k.upper()]) for k in OHLC])
        op,high,low,close = values
        if not np.isfinite(values).all() or min(values)<=0 or high<max(values) or low>min(values):
            raise ValueError('Invalid official index candle')
        if np.isfinite(market.loc[date,'Close']):
            if abs(close/market.loc[date,'Close']-1) > .005:
                raise ValueError(f'Index sources disagree near gap: {date}')
            continue
        market.loc[date,OHLC] = values
        market.loc[date,'Volume'] = 0
        market.loc[date,'QuoteClose'] = close
        applied.append(str(date.date()))
    return market,applied


def daily_features(d):
    d = d.copy()
    c, h, l = d.Close, d.High, d.Low
    tr = np.maximum(h-l, np.maximum((h-c.shift()).abs(), (l-c.shift()).abs()))
    # First valid bar seeds ATR with its range; a later missing predecessor resets.
    if c.first_valid_index() is not None:
        tr.loc[c.first_valid_index()] = (h-l).loc[c.first_valid_index()]
    d['atr20'] = wilder(tr, 20)
    d['sma50'] = c.rolling(50).mean()
    d['sma200'] = c.rolling(200).mean()
    d['high252'] = h.rolling(252).max()
    d['low252'] = l.rolling(252).min()
    d['new_high'] = (h > h.shift().rolling(252).max()).astype(float).where(c.notna())
    d['turnover20'] = (c*d.Volume).rolling(20).mean()
    d['volume50_prior'] = d.Volume.rolling(50).mean().shift()
    return d


def weekly_features(d, as_of):
    source = d.copy()
    source['valid'] = d[OHLC + ['Volume']].notna().all(axis=1)
    source['end_pos'] = np.arange(len(d))
    source['actual_date'] = d.index
    rules = {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum',
             'valid':'min','new_high':'max','end_pos':'last','actual_date':'last'}
    rules.update({k:'last' for k in ['sma50','sma200','QuoteClose','high252','low252','turnover20']})
    w = source.resample('W-FRI').agg(rules)
    w = w.loc[(w.index <= pd.Timestamp(as_of)) & w.end_pos.notna()].copy()
    w['complete'] = w.pop('valid').astype(bool)
    w.index = pd.DatetimeIndex(w.pop('actual_date'))
    w.index.name = None
    w['new_high'] = w.new_high.eq(1)
    w.loc[~w.complete, OHLC + ['Volume','sma50','sma200']] = np.nan
    w['sma10'] = w.Close.rolling(10).mean()
    w['rising200'] = w.sma200.diff().gt(0).rolling(13).sum().eq(13)
    w['volume10_prior'] = w.Volume.rolling(10).mean().shift()
    frequency = []
    complete_values, high_values = w.complete.to_numpy(), w.new_high.to_numpy()
    for i in range(len(w)):
        if i < 51 or not complete_values[i-51:i+1].all():
            frequency.append(False)
            continue
        high_weeks = np.flatnonzero(high_values[i-51:i+1])
        okay = (len(high_weeks) >= 2 and np.any(high_weeks < 26)
                and np.any(high_weeks >= 26)
                and np.diff(np.r_[-1, high_weeks, 51]).max() <= 26)
        frequency.append(bool(okay))
    w['high_frequency'] = frequency
    w['screen'] = (w.complete & (w.QuoteClose >= 30) & (w.Close >= .75*w.high252)
                   & (w.Close >= 2*w.low252) & (w.Close > w.sma50)
                   & (w.sma50 > w.sma200) & w.rising200 & w.high_frequency
                   & (w.turnover20 >= 1e7)).fillna(False)
    return w


def update_pivots(points, w, i, arrays=None):
    """At weekly close i, only pivot i-1 can become confirmed."""
    p = i-1
    highs, lows, complete = arrays if arrays is not None else (w.High.to_numpy(),w.Low.to_numpy(),w.complete.to_numpy())
    if p < 1 or not complete[p-1:i+1].all():
        return [] if p >= 1 else points
    high = highs[p] > max(highs[p-1], highs[i])
    low = lows[p] < min(lows[p-1], lows[i])
    if high and low:
        return []  # Daily order of two extremes inside a week is unknowable.
    if not high and not low:
        return points
    kind = 'H' if high else 'L'
    price = float(highs[p] if high else lows[p])
    point = {'kind': kind, 'week': p, 'price': price, 'confirmed_week': i}
    points = [dict(x) for x in points]
    if points and points[-1]['kind'] == kind:
        more_extreme = price > points[-1]['price'] if high else price < points[-1]['price']
        if more_extreme:
            points[-1] = point
    else:
        points.append(point)
    return points[-12:]


def pattern_at(w, points, i, count, two_rule='smaller', max_age=26):
    if len(points) < 2*count or points[-1]['kind'] != 'L':
        return None
    p = points[-2*count:]
    if [x['kind'] for x in p] != ['H', 'L']*count:
        return None
    highs, lows = p[::2], p[1::2]
    age = i-highs[0]['week']
    if not 4 <= age <= max_age or i-lows[-1]['week'] > 8:
        return None
    if not w.complete.iloc[highs[0]['week']:i+1].all():
        return None
    depths = np.array([1-l['price']/h['price'] for h, l in zip(highs, lows)])
    durations = np.array([l['week']-h['week'] for h, l in zip(highs, lows)])
    if (np.any(depths <= 0) or not np.all(np.diff(depths) < 0)
            or not np.all(np.diff([l['price'] for l in lows]) > 0)
            or not np.all(np.diff(durations) <= 0)):
        return None
    if count == 2 and two_rule == '70' and depths[1] > .30*depths[0] + 1e-12:
        return None
    pivot = highs[-1]['price']
    final_low = lows[-1]['price']
    since_low = w.iloc[lows[-1]['week']+1:i+1]
    if since_low.empty or (since_low.Close > pivot).any() or (since_low.Low < final_low).any():
        return None
    pull_volume = [float(w.Volume.iloc[h['week']+1:l['week']+1].mean()) for h, l in zip(highs,lows)]
    rally = w.Volume.iloc[lows[-2]['week']+1:highs[-1]['week']+1]
    if rally.empty or pull_volume[-1] >= rally.mean() or pull_volume[-1] >= pull_volume[-2]:
        return None
    base = w.iloc[highs[0]['week']:i+1]
    changes = w.Close.diff().iloc[highs[0]['week']:i+1]
    up_volume = base.Volume[changes > 0].sum()
    down_volume = base.Volume[changes < 0].sum()
    if up_volume <= down_volume or pull_volume[-1] >= w.volume10_prior.iloc[i]:
        return None
    return {'pivot': pivot, 'final_low': final_low, 'depth': float(depths[-1]),
            'depths': depths.tolist(), 'durations': durations.tolist(),
            'pullback_volumes': pull_volume, 'rally_volume': float(rally.mean()),
            'count': count, 'age_weeks': int(age),
            'id': f"{w.index[highs[0]['week']].date()}_{w.index[lows[-1]['week']].date()}_{count}",
            'pivot_dates': [str(w.index[x['week']].date()) for x in p],
            'confirmation_dates': [str(w.index[x['confirmed_week']].date()) for x in p]}


def prepare_symbol(d, as_of, max_age=26):
    d = daily_features(d)
    w = weekly_features(d, as_of)
    patterns = {name: {} for name in PLAN['variants']['pattern']}
    points, diagnostics = [], Counter()
    piv_arrays = (w.High.to_numpy(),w.Low.to_numpy(),w.complete.to_numpy())
    screens = w.screen.to_numpy()
    diagnostics['completed_weeks'] = int(w.complete.sum())
    diagnostics['trend_weeks'] = int((w.rising200 & (w.Close > w.sma50) & (w.sma50 > w.sma200)).sum())
    diagnostics['double_low_weeks'] = int((w.Close >= 2*w.low252).sum())
    for i in range(len(w)):
        points = update_pivots(points, w, i, piv_arrays)
        if not screens[i]:
            continue
        diagnostics['screen_weeks'] += 1
        three = pattern_at(w, points, i, 3, max_age=max_age)
        two70 = pattern_at(w, points, i, 2, '70', max_age=max_age)
        two = pattern_at(w, points, i, 2, max_age=max_age)
        for name, pattern in [('three', three), ('three_or_two_70', three or two70),
                              ('three_or_two_smaller', three or two)]:
            if pattern:
                patterns[name][int(w.end_pos.iloc[i])] = pattern
                diagnostics[name+'_weeks'] += 1
    d['weekly_exit'] = False
    for row in w.itertuples():
        if np.isfinite(row.sma10) and row.Close < row.sma10:
            d.iloc[row.end_pos, d.columns.get_loc('weekly_exit')] = True
    end_positions = list(w.end_pos.astype(int))
    return d, patterns, end_positions, dict(diagnostics)


@dataclass(frozen=True)
class Config:
    pattern: str
    entry: str
    exit: str
    market_filter: bool
    pyramid: bool

    @property
    def id(self):
        return f'{self.pattern}__{self.entry}__{self.exit}__m{int(self.market_filter)}__a{int(self.pyramid)}'


def configurations():
    v = PLAN['variants']
    return [Config(*values) for values in itertools.product(
        v['pattern'], v['entry'], v['exit'], v['market_filter'], v['pyramid'])]


def make_orders(symbol, d, patterns, end_positions, entry):
    """Weekly watchlist is available starting the NEXT trading session."""
    orders = []
    active = None
    weekly_ends = set(end_positions)
    previous_signal = None
    values = d.to_dict('records')
    for i, row in enumerate(values):
        if entry == 'close_volume_next_open' and previous_signal is not None:
            orders.append(previous_signal | {'day': i})
            previous_signal = None
        if i > 0 and active:
            prev = values[i-1]
            if np.isfinite(prev['Close']) and np.isfinite(prev['atr20']):
                common = {'symbol': symbol, 'pattern': active,
                          'signal_day': i-1, 'atr': prev['atr20'],
                          'turnover': prev['turnover20']}
                if entry == 'intraday_pivot':
                    trigger = active['pivot']*1.001
                    if prev['Close'] <= trigger and prev['Close'] > active['final_low']:
                        orders.append(common | {'day': i, 'trigger': trigger})
                elif (prev['Close'] <= active['pivot'] < row['Close']
                      and row['Volume'] >= 1.5*row['volume50_prior']
                      and row['Close'] > active['final_low']):
                    previous_signal = common | {'signal_day': i, 'atr': row['atr20'],
                                                'turnover': row['turnover20'], 'trigger': active['pivot']}
            if row['Low'] < active['final_low'] or row['Close'] > active['pivot']:
                active = None
        if i in weekly_ends:
            active = patterns.get(i)
    return orders


def prepare_all(frames, as_of, max_age=26):
    import inspect
    functions = [daily_features,weekly_features,update_pivots,pattern_at,prepare_symbol,make_orders]
    digest = hashlib.sha256((''.join(inspect.getsource(f) for f in functions)+str(max_age)+as_of).encode())
    for s,d in frames.items():
        digest.update(s.encode())
        digest.update(pd.util.hash_pandas_object(d,index=True).values.tobytes())
    stem = CACHE/('prepared_'+digest.hexdigest()[:20])
    if stem.with_suffix('.json').exists() and stem.with_suffix('.npz').exists():
        meta = json.loads(stem.with_suffix('.json').read_text())
        with np.load(stem.with_suffix('.npz'),allow_pickle=False) as data:
            arrays = {s:data[s] for s in data.files}
        books = {(p,e):{int(day):v for day,v in book.items()} for p,e,book in meta['books']}
        print('Loaded verified feature cache',flush=True)
        return {},arrays,books,meta['diagnostic']
    prepared, diagnostic, orderbooks = {}, {}, defaultdict(lambda: defaultdict(list))
    for n, (symbol, frame) in enumerate(frames.items(), 1):
        d, patterns, ends, diagnostic[symbol] = prepare_symbol(frame, as_of, max_age)
        prepared[symbol] = d
        for pattern, by_week in patterns.items():
            for entry in PLAN['variants']['entry']:
                for order in make_orders(symbol, d, by_week, ends, entry):
                    orderbooks[(pattern, entry)][order['day']].append(order)
        if n % 50 == 0:
            print(f'Prepared {n}/200 stocks', flush=True)
    # Float arrays avoid expensive pandas indexing inside the event loop.
    columns = OHLC + ['Volume', 'atr20', 'weekly_exit']
    arrays = {s: d[columns].to_numpy(dtype=float) for s, d in prepared.items()}
    np.savez_compressed(stem.with_suffix('.npz'),**arrays)
    json_write(stem.with_suffix('.json'),{'diagnostic':diagnostic,
               'books':[[p,e,dict(book)] for (p,e),book in orderbooks.items()]})
    return prepared, arrays, orderbooks, diagnostic


def stop_execution(open_price, low, stop, slip):
    if open_price <= stop:
        return open_price*(1-slip), 'gap_stop'
    if low <= stop:
        return stop*(1-slip), 'stop'
    return None


def portfolio_metrics(curve, trades, initial, dates, diagnostics):
    equity = np.array([initial] + [r['equity'] for r in curve])
    drawdown = equity / np.maximum.accumulate(equity) - 1
    years = max((dates[-1]-dates[0]).days / 365.25, 1/365.25)
    pnl = np.array([t['net_pnl'] for t in trades])
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    rs = [t['net_r'] for t in trades]
    annual, base = {}, initial
    for year in sorted({pd.Timestamp(r['date']).year for r in curve}):
        rows = [r for r in curve if pd.Timestamp(r['date']).year == year]
        annual[str(year)] = 100*(rows[-1]['equity']/base-1)
        base = rows[-1]['equity']
    return {
        'start': str(dates[0].date()), 'end': str(dates[-1].date()),
        'initial_cash': initial, 'ending_equity': equity[-1],
        'total_return_pct': 100*(equity[-1]/initial-1),
        'cagr_pct': 100*((equity[-1]/initial)**(1/years)-1),
        'max_drawdown_pct': -100*drawdown.min(), 'closed_trades': len(trades),
        'win_rate_pct': 100*len(wins)/len(trades) if trades else None,
        'profit_factor': float(wins.sum()/-losses.sum()) if len(losses) else None,
        'average_win_pct': float(np.mean([t['net_return_pct'] for t in trades if t['net_pnl'] > 0])) if len(wins) else None,
        'average_loss_pct': float(np.mean([t['net_return_pct'] for t in trades if t['net_pnl'] < 0])) if len(losses) else None,
        'mean_net_r': float(np.mean(rs)) if rs else None,
        'mean_holding_sessions': float(np.mean([t['holding_sessions'] for t in trades])) if trades else None,
        'average_exposure_pct': float(np.mean([r['exposure_pct'] for r in curve])),
        'fees_and_fixed_charges': float(sum(t['fees'] for t in trades)),
        'annual_returns_pct': annual, 'diagnostics': dict(diagnostics),
    }


def simulate(arrays, calendar, market_gate, sectors, orders, config, start, end, cost_scale=1,
             initial_cash=None):
    selected = np.flatnonzero((calendar >= start) & (calendar <= end))
    first, last = int(selected[0]), int(selected[-1])
    fee = PLAN['costs']['fee_tax_per_side']*cost_scale
    slip = PLAN['costs']['slippage_per_side']*cost_scale
    dp = PLAN['costs']['fixed_exit_charge_rupees']*cost_scale
    initial = PLAN['portfolio']['initial_cash'] if initial_cash is None else initial_cash
    cash = float(initial)
    positions, trades, curve, used = {}, [], [], set()
    counters = Counter()

    def sell(symbol, price, day, reason):
        nonlocal cash
        p = positions.pop(symbol)
        proceeds = p['qty']*price*(1-fee)-dp
        cash += proceeds
        pnl = proceeds-p['cost']
        trades.append({
            'symbol': symbol, 'entry_date': str(calendar[p['entry_day']].date()),
            'exit_date': str(calendar[day].date()), 'entry_price': p['entry_price'],
            'exit_price': price, 'initial_stop': p['initial_stop'], 'exit_stop': p['stop'],
            'target': p['target'], 'quantity': p['qty'], 'entry_cost': p['cost'],
            'exit_proceeds': proceeds, 'net_pnl': pnl, 'net_return_pct': 100*pnl/p['cost'],
            'planned_risk_rupees': p['risk'], 'net_r': pnl/p['risk'],
            'fees': p['entry_fees'] + p['qty']*price*fee + dp,
            'holding_sessions': day-p['entry_day']+1, 'reason': reason,
            'adds': p['adds'], 'pattern': p['pattern'], 'fills': p['fills'],
        })

    for i in range(first, last+1):
        # All sizing uses cash and marks known before this session opens.
        equity_before = cash + sum(p['qty']*p['mark'] for p in positions.values())
        cash_before = cash
        for symbol, p in list(positions.items()):
            bar = arrays[symbol][i]
            if not np.isfinite(bar[:5]).all() or bar[4] <= 0:
                counters['missing_held_bars'] += 1
                continue
            op = bar[0]
            if op <= p['stop']:
                sell(symbol, op*(1-slip), i, 'gap_stop')
            elif p['pending_weekly_exit']:
                sell(symbol, op*(1-slip), i, 'weekly_sma10')
            elif p['target'] is not None and op >= p['target']:
                sell(symbol, p['target']*(1-slip), i, 'target_3r_gap_capped')

        # Reserve slots/cash for ranked orders BEFORE observing today's high.
        # An untriggered high-priority stop order still ties up its reserved cash.
        reserved_cash = min(cash_before, cash)
        reserved_symbols = set(positions)
        industry_counts = Counter(sectors.get(s, 'Unknown') for s in reserved_symbols)
        todays = sorted(orders.get(i, []), key=lambda x: (x['pattern']['depth'], -x['turnover'], x['symbol']))
        if i == last or (config.market_filter and (i == 0 or not market_gate[i-1])):
            counters['market_or_terminal_orders_blocked'] += len(todays)
            todays = []
        for order in todays:
            symbol, pattern = order['symbol'], order['pattern']
            key = (symbol, pattern['id'])
            if key in used:
                continue
            existing = positions.get(symbol)
            if existing:
                prev_close = arrays[symbol][i-1, 3]
                if (not config.pyramid or existing['adds'] >= 1
                        or not np.isfinite(prev_close)
                        or prev_close < existing['entry_price']+existing['initial_distance']
                        or pattern['pivot'] <= existing['pattern']['pivot']
                        or order['signal_day'] <= existing['entry_day']):
                    continue
            else:
                industry = sectors.get(symbol, 'Unknown')
                if len(reserved_symbols) >= 5 or industry_counts[industry] >= 2:
                    counters['capacity_orders_blocked'] += 1
                    continue
            bar = arrays[symbol][i]
            if not np.isfinite(bar[:5]).all() or bar[4] <= 0 or not np.isfinite(order['atr']):
                counters['unexecutable_entry_bars'] += 1
                continue
            op, high, low, close = bar[:4]
            raw_entry = max(op, order['trigger']) if config.entry == 'intraday_pivot' else op
            if raw_entry < pattern['pivot'] or raw_entry > 1.05*pattern['pivot']:
                counters['gap_orders_rejected'] += 1
                continue
            entry = raw_entry*(1+slip)
            distance = min(2*order['atr'], .10*entry)
            if not distance > 0:
                continue
            stop = entry-distance
            qty_existing = existing['qty'] if existing else 0
            if existing:
                stop = max(stop, existing['stop'])
            per_share_risk = entry*(1+fee)-stop*(1-slip)*(1-fee)
            risk_budget = equity_before*(.0025 if existing else .005)
            if existing:
                old_open_risk = max(0, existing['cost']-qty_existing*stop*(1-slip)*(1-fee))
                risk_budget = min(risk_budget, .005*equity_before-old_open_risk)
            allocation = min(reserved_cash, .2*equity_before-qty_existing*entry)
            qty = max(0, math.floor(min((risk_budget-dp)/per_share_risk, allocation/(entry*(1+fee)))))
            if qty <= 0:
                counters['size_orders_rejected'] += 1
                continue
            cost = qty*entry*(1+fee)
            reserved_cash -= cost
            if not existing:
                reserved_symbols.add(symbol)
                industry_counts[sectors.get(symbol, 'Unknown')] += 1
            if config.entry == 'intraday_pivot' and high < order['trigger']:
                counters['reserved_untriggered_orders'] += 1
                continue
            cash -= cost
            if cash < -1e-7:
                raise AssertionError('Portfolio borrowed cash')
            used.add(key)
            fill = {'date': str(calendar[i].date()), 'price': entry, 'quantity': qty,
                    'signal_date': str(calendar[order['signal_day']].date()), 'stop': stop,
                    'pattern_id': pattern['id'], 'type': 'add' if existing else 'initial'}
            if existing:
                existing['qty'] += qty
                existing['cost'] += cost
                existing['entry_fees'] += qty*entry*fee
                existing['risk'] += qty*per_share_risk
                existing['stop'] = stop
                existing['adds'] += 1
                existing['fills'].append(fill)
                counters['add_fills'] += 1
            else:
                positions[symbol] = {
                    'entry_day': i, 'entry_price': entry, 'initial_stop': stop,
                    'initial_distance': distance, 'stop': stop,
                    'target': entry+3*distance if config.exit == 'target_3r' else None,
                    'qty': qty, 'cost': cost, 'entry_fees': qty*entry*fee,
                    'risk': qty*per_share_risk+dp, 'mark': entry, 'high_close': entry,
                    'adds': 0, 'pattern': pattern, 'pending_weekly_exit': False, 'fills': [fill],
                }
                counters['initial_fills'] += 1

        for symbol, p in list(positions.items()):
            bar = arrays[symbol][i]
            if not np.isfinite(bar[:5]).all() or bar[4] <= 0:
                if i == last:
                    raise ValueError(f'Cannot invent terminal liquidation for missing {symbol}')
                continue
            op, high, low, close, volume, atr, weekly_exit = bar
            # A pre-entry open cannot be a gap exit on an intraday entry/add.
            just_filled = p['fills'][-1]['date'] == str(calendar[i].date())
            effective_open = max(op, p['fills'][-1]['price']/(1+slip)) if just_filled else op
            stopped = stop_execution(effective_open, low, p['stop'], slip)
            if stopped:
                # If entry was an intraday stop, an earlier low may have occurred;
                # taking the stop anyway is the pessimistic daily-OHLC convention.
                sell(symbol, stopped[0], i, stopped[1])
                continue
            if p['target'] is not None and high >= p['target']:
                sell(symbol, p['target']*(1-slip), i, 'target_3r')
                continue
            p['mark'] = close
            if i == last:
                sell(symbol, close*(1-slip), i, 'period_end')
                continue
            p['high_close'] = max(p['high_close'], close)
            if config.exit == 'atr_trail' and np.isfinite(atr):
                p['stop'] = max(p['stop'], p['high_close']-2*atr)
            p['pending_weekly_exit'] = config.exit == 'weekly_sma10' and bool(weekly_exit)
        gross_holdings = sum(p['qty']*p['mark'] for p in positions.values())
        # Mark to a conservative liquidation value, including estimated exit fees.
        net_holdings = sum(p['qty']*p['mark']*(1-slip)*(1-fee)-dp for p in positions.values())
        equity = cash+net_holdings
        curve.append({'date': str(calendar[i].date()), 'equity': equity,
                      'cash': cash, 'positions': len(positions),
                      'exposure_pct': 100*gross_holdings/(cash+gross_holdings) if cash+gross_holdings else 0})
    if positions:
        raise AssertionError('Open positions at terminal date')
    if abs(cash-initial-sum(t['net_pnl'] for t in trades)) > 1e-6:
        raise AssertionError('Cash and trade P/L fail reconciliation')
    return {'metrics': portfolio_metrics(curve, trades, initial, calendar[selected], counters),
            'trades': trades, 'curve': curve}


def selection_key(row):
    a, b = row['development'], row['validation']
    adequate = all(x['closed_trades'] >= 20 and x['total_return_pct'] > 0 for x in [a,b])
    score = min(x['cagr_pct']/max(x['max_drawdown_pct'], 5) for x in [a,b])
    return (-int(adequate), -score, row['id'])


def benchmark_metrics(market, start, end):
    d = market.loc[start:end]
    valid = d.Close.notna()
    if not valid.all():
        # Return endpoints remain observable; explicitly report internal holes.
        gaps = [str(t.date()) for t in d.index[~valid]]
    else:
        gaps = []
    d = d.loc[valid]
    start_price = float(d.Open.iloc[0])
    curve = [{'date': str(t.date()), 'equity': 100000*row.Close/start_price,
              'exposure_pct': 100} for t, row in d.iterrows()]
    metrics = portfolio_metrics(curve, [], 100000, d.index, Counter())
    return {'label': 'Nifty 200 price index, no dividends or fund costs',
            'missing_dates': gaps, 'metrics': metrics, 'curve': curve}


def total_return_benchmark(start, end):
    path = CACHE/'nifty200_tri_raw.csv'
    if not path.exists():
        return {'available': False, 'reason': 'Official TRI download unavailable'}
    d = pd.read_csv(path)
    if not d['Index Name'].str.upper().eq('NIFTY 200').all():
        raise ValueError('Wrong TRI index')
    d['Date'] = pd.to_datetime(d.Date, format='%d %b %Y')
    d = d.set_index('Date').sort_index()
    if d.index.has_duplicates:
        raise ValueError('Duplicate TRI dates')
    prior = d.loc[d.index < pd.Timestamp(start)]
    period = d.loc[start:end]
    if prior.empty or period.empty:
        return {'available': False, 'reason': 'Benchmark endpoints missing'}
    reference = float(prior.TotalReturnsIndex.iloc[-1])
    curve = [{'date':str(t.date()), 'equity':100000*float(row.TotalReturnsIndex)/reference,
              'exposure_pct':100} for t,row in period.iterrows()]
    return {'available':True, 'label':'Official Nifty 200 total-return index, gross dividends reinvested; no fund costs',
            'source':'https://www.niftyindices.com/reports/historical-data',
            'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'baseline_date':str(prior.index[-1].date()), 'baseline_value':reference,
            'metrics':portfolio_metrics(curve,[],100000,period.index,Counter()), 'curve':curve}


def uncertainty(result, seed=20260923, draws=5000):
    """Entry-month cluster bootstrap; diagnostics, not multiple-test correction."""
    trades = result['trades']
    groups = defaultdict(list)
    for t in trades:
        groups[t['entry_date'][:7]].append(t['net_r'])
    if len(groups) < 5:
        return {'entry_month_clusters': len(groups), 'mean_r_95pct_interval': None,
                'note': 'Fewer than five entry-month clusters; too little evidence for a useful interval'}
    sums = np.array([sum(v) for v in groups.values()])
    counts = np.array([len(v) for v in groups.values()])
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(groups), size=(draws, len(groups)))
    means = sums[indices].sum(axis=1)/counts[indices].sum(axis=1)
    return {'entry_month_clusters': len(groups), 'bootstrap_draws': draws,
            'mean_r_95pct_interval': np.percentile(means, [2.5,97.5]).tolist(),
            'note': 'Resamples entry-month clusters, conditional on observed current-survivor trades; no correction for rule selection or missing past constituents'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['prepare', 'select', 'evaluate', 'all'], default='all')
    parser.add_argument('--max-pattern-weeks', type=int, default=26)
    args = parser.parse_args()
    plan_hash = hashlib.sha256(json.dumps(PLAN, sort_keys=True).encode()).hexdigest()
    frames, market, sectors, audit = load_universe(PLAN['as_of'])
    prepared, arrays, books, diagnostic = prepare_all(frames, PLAN['as_of'], args.max_pattern_weeks)
    json_write(OUT / 'data_audit.json', audit)
    json_write(OUT / 'signal_diagnostics.json', diagnostic)
    calendar, gate = market.index, market.gate.to_numpy(bool)
    total = Counter()
    for d in diagnostic.values():
        total.update(d)
    print('Signal funnel:', dict(total), flush=True)
    if args.phase == 'prepare':
        return
    configs = configurations()
    rows = []
    if args.phase in ('select', 'all'):
        for j, config in enumerate(configs, 1):
            row = {'id': config.id, 'config': asdict(config)}
            for period in ['development', 'validation']:
                start, end = PLAN['periods'][period]
                result = simulate(arrays, calendar, gate, sectors, books.get((config.pattern, config.entry), {}), config, start, end)
                row[period] = result['metrics']
            rows.append(row)
            if j % 18 == 0:
                print(f'Earlier-period evaluation {j}/72', flush=True)
        ranked = sorted(rows, key=selection_key)
        eligible = sum(selection_key(r)[0] == -1 for r in rows)
        selection = {'plan_sha256': plan_hash, 'max_pattern_weeks': args.max_pattern_weeks,
                     'selected_id': ranked[0]['id'], 'qualified_earlier_variants': eligible,
                     'selected_on_earlier_data_only': True,
                     'warning': None if eligible else 'No variant meets the minimum earlier-period evidence requirement; selection is exploratory only',
                     'ranking': [r['id'] for r in ranked], 'earlier_results': rows}
        json_write(OUT / 'selection.json', selection)
        print('Selection written BEFORE later-period evaluation:', selection['selected_id'], 'qualified:', eligible, flush=True)
    else:
        selection = json.loads((OUT/'selection.json').read_text())
        if selection['plan_sha256'] != plan_hash or selection['max_pattern_weeks'] != args.max_pattern_weeks:
            raise ValueError('Frozen selection does not match this plan')
        rows = selection['earlier_results']
    if args.phase == 'select':
        return
    selection_hash = hashlib.sha256((OUT/'selection.json').read_bytes()).hexdigest()
    evidence = {}
    for j, (config, row) in enumerate(zip(configs, rows), 1):
        if config.id != row['id']:
            raise AssertionError('Configuration order mismatch')
        evidence[config.id] = {}
        for period in ['later', 'full']:
            start, end = PLAN['periods'][period]
            for scale, suffix in [(1,''), (2,'_stress')]:
                result = simulate(arrays, calendar, gate, sectors, books.get((config.pattern, config.entry), {}), config, start, end, scale)
                row[period+suffix] = result['metrics']
                evidence[config.id][period+suffix] = result
        if j % 18 == 0:
            print(f'Later/full evaluation {j}/72', flush=True)
    selected = evidence[selection['selected_id']]
    hindsight = max(rows, key=lambda r: r['later']['total_return_pct'])
    summary = {'plan_sha256': plan_hash, 'selection_sha256': selection_hash,
               'as_of': PLAN['as_of'], 'variant_count': len(rows), 'signal_funnel': dict(total),
               'selected_id': selection['selected_id'], 'qualified_earlier_variants': selection['qualified_earlier_variants'],
               'hindsight_best_later_id': hindsight['id'],
               'hindsight_warning': 'Highest later-period return is chosen after seeing later results; not a validated selection',
               'selected_later_uncertainty': uncertainty(selected['later']),
               'selected_full_uncertainty': uncertainty(selected['full']),
               'benchmarks': {p: benchmark_metrics(market, *dates) for p, dates in PLAN['periods'].items()},
               'total_return_benchmarks': {p: total_return_benchmark(*dates) for p, dates in PLAN['periods'].items()},
               'results': rows, 'limitations': PLAN['limits']}
    json_write(OUT/'results.json', summary)
    import gzip
    with gzip.open(OUT/'evidence.json.gz', 'wt', encoding='utf-8') as f:
        json.dump(evidence, f, allow_nan=False, separators=(',',':'))
    table = []
    for row in rows:
        for period in ['development','validation','later','later_stress','full','full_stress']:
            table.append({'id': row['id'], **row['config'], 'period': period,
                          **{k:v for k,v in row[period].items() if not isinstance(v,dict)}})
    pd.DataFrame(table).to_csv(OUT/'comparison.csv', index=False)
    pd.DataFrame(selected['full']['trades']).drop(columns=['pattern','fills'], errors='ignore').to_csv(OUT/'selected_trades.csv', index=False)
    json_write(OUT/'selected_evidence.json', selected)
    print(json.dumps({'selected': next(r for r in rows if r['id'] == selection['selected_id']),
                      'hindsight_best': hindsight, 'uncertainty': summary['selected_later_uncertainty']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
