"""Predeclared timing and labelled capital/data-quality sensitivity checks.

Keeps the original model selection and results intact. No new winner selection.
"""
from collections import Counter
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import vcp_research as v


def main():
    results = json.loads((v.OUT/'results.json').read_text())
    selection = json.loads((v.OUT/'selection.json').read_text())
    chosen_row = next(r for r in results['results'] if r['id'] == selection['selected_id'])
    config = v.Config(**chosen_row['config'])
    frames,market,sectors,audit = v.load_universe(v.PLAN['as_of'])
    _,arrays,books,_ = v.prepare_all(frames,v.PLAN['as_of'])
    calendar,gate = market.index,market.gate.to_numpy(bool)
    book = books[(config.pattern,config.entry)]
    sensitivity = {'selected_id':config.id, 'note':'Diagnostics of the previously selected rule; no reselection on later data'}
    for initial in [100000,1000000]:
        for period in ['later','full']:
            for scale in [1,2]:
                key = f'capital_{initial}_{period}_cost{scale}'
                r = v.simulate(arrays,calendar,gate,sectors,book,config,*v.PLAN['periods'][period],scale,initial_cash=initial)
                sensitivity[key] = r['metrics']
    # Avoid relying on ANY security with a flagged >40% adjusted daily jump.
    # This is a deliberately severe retrospective data-quality sensitivity,
    # NOT a deployable stock filter and NOT the main performance estimate.
    flagged = {s for s,d in audit['stocks'].items() if d['large_adjusted_jumps']}
    filtered_book = {day:[o for o in orders if o['symbol'] not in flagged] for day,orders in book.items()}
    sensitivity['flagged_securities'] = sorted(flagged)
    for period in ['later','full']:
        r = v.simulate(arrays,calendar,gate,sectors,filtered_book,config,*v.PLAN['periods'][period])
        sensitivity['exclude_flagged_'+period] = r['metrics']
    all_evidence = json.load(gzip.open(v.OUT/'evidence.json.gz','rt'))
    jump_overlap = set()
    for periods in all_evidence.values():
        for result in periods.values():
            for t in result['trades']:
                for day in audit['stocks'][t['symbol']]['large_adjusted_jumps']:
                    if t['entry_date'] <= day <= t['exit_date']:
                        jump_overlap.add((t['symbol'],day,t['entry_date'],t['exit_date']))
    sensitivity['trades_crossing_flagged_jumps'] = sorted(jump_overlap)
    selected = all_evidence[config.id]
    for period in ['later','full']:
        trades = selected[period]['trades']
        winners = sorted(trades,key=lambda t:t['net_pnl'],reverse=True)
        sensitivity['profit_concentration_'+period] = {
            'net_pnl':sum(t['net_pnl'] for t in trades),
            'top_three':[{'symbol':t['symbol'],'entry_date':t['entry_date'],'net_pnl':t['net_pnl']} for t in winners[:3]],
            'arithmetic_pnl_without_best_trade':sum(t['net_pnl'] for t in trades)-winners[0]['net_pnl'] if winners else 0,
            'note':'Arithmetic contribution diagnostic; does not replay different sizing/capital after deleting a trade'}
    # Tighter 4-8-week base: compare same selected rule and report all 72 later
    # variants as sensitivity, never use these to replace the original selection.
    _,short_arrays,short_books,diag = v.prepare_all(frames,v.PLAN['as_of'],max_age=8)
    totals = Counter()
    for d in diag.values():
        totals.update(d)
    sensitivity['four_to_eight_week_funnel'] = dict(totals)
    sensitivity['four_to_eight_week_all_variants_later'] = []
    for c in v.configurations():
        r = v.simulate(short_arrays,calendar,gate,sectors,short_books.get((c.pattern,c.entry),{}),c,*v.PLAN['periods']['later'])
        sensitivity['four_to_eight_week_all_variants_later'].append({'id':c.id,**r['metrics']})
    for period in ['later','full']:
        r = v.simulate(short_arrays,calendar,gate,sectors,short_books.get((config.pattern,config.entry),{}),config,*v.PLAN['periods'][period])
        sensitivity['four_to_eight_weeks_'+period] = r['metrics']
    # Point-in-time prefix comparison on real histories from actual fills.
    prefix_checks = []
    for trade in sorted(selected['full']['trades'],key=lambda t:t['entry_date'])[:6]:
        symbol = trade['symbol']
        cutoff = trade['entry_date']
        full = v.prepare_symbol(frames[symbol],v.PLAN['as_of'])
        partframe = frames[symbol].loc[:cutoff]
        part = v.prepare_symbol(partframe,cutoff)
        for name in full[1]:
            for pos in part[2]:
                if full[1][name].get(pos) != part[1][name].get(pos):
                    raise AssertionError(f'Future data changes historical pattern: {symbol} {cutoff}')
        prefix_checks.append({'symbol':symbol,'cutoff':cutoff,'passed':True})
    sensitivity['real_history_prefix_checks'] = prefix_checks
    v.json_write(v.OUT/'sensitivity.json',sensitivity)
    print(json.dumps({k:val for k,val in sensitivity.items() if k not in ['four_to_eight_week_all_variants_later']},indent=2))


if __name__ == '__main__':
    main()
