import unittest
from copy import deepcopy

import numpy as np
import pandas as pd

from vcp_research import (Config, daily_features, weekly_features, update_pivots,
                          pattern_at, prepare_symbol, make_orders, simulate,
                          stop_execution, wilder, selection_key, configurations, repair_market)


def price_frame(n=800):
    rng = np.random.default_rng(618)
    close = 100*np.exp(np.cumsum(rng.normal(.001, .018, n)))
    op = close*np.exp(rng.normal(0,.002,n))
    return pd.DataFrame({'Open':op, 'High':np.maximum(op,close)*1.01,
                         'Low':np.minimum(op,close)*.99, 'Close':close,
                         'Volume':rng.integers(100000,2000000,n), 'QuoteClose':close},
                        index=pd.bdate_range('2018-01-01', periods=n))


def order(symbol='A', day=1, depth=.05, trigger=100):
    return {'symbol':symbol, 'day':day, 'signal_day':day-1, 'atr':2.,
            'turnover':1e8, 'trigger':trigger,
            'pattern': {'pivot':trigger/1.001, 'final_low':90., 'id':symbol+'base', 'depth':depth,
                        'count':3, 'depths':[.20,.10,.05]}}


class VCPMechanicsTests(unittest.TestCase):
    def test_official_index_repairs_only_missing_valid_same_index(self):
        d = price_frame(3)
        day = d.index[1]
        d.loc[day,['Open','High','Low','Close']] = np.nan
        row = {'INDEX_NAME':'Nifty 200','HistoricalDate':day.strftime('%d %b %Y'),
               'OPEN':'100','HIGH':'103','LOW':'99','CLOSE':'102'}
        repaired,applied = repair_market(d,[row])
        self.assertEqual(repaired.loc[day,'Close'],102)
        self.assertEqual(applied,[str(day.date())])
        self.assertTrue(np.isnan(d.loc[day,'Close']))
        with self.assertRaises(ValueError):
            repair_market(d,[row|{'INDEX_NAME':'Nifty 50'}])
        with self.assertRaises(ValueError):
            repair_market(d,[row|{'HIGH':'90'}])
        with self.assertRaises(ValueError):
            repair_market(repaired,[row|{'CLOSE':'80','LOW':'79'}])
    def pattern_fixture(self):
        w = pd.DataFrame({'High':[96,100,90,86,99,105,99,108,110,108,109],
                          'Low':[90,95,83,80,92,99,94.5,100,106,104.5,106],
                          'Close':[94,99,85,82,95,103,96,105,109,106,108],
                          'Volume':[200,400,100,100,300,300,80,300,300,30,150],
                          'complete':[True]*11, 'volume10_prior':[250]*11},
                         index=pd.date_range('2024-01-05',periods=11,freq='W-FRI'))
        points = [{'kind':k,'week':i,'price':price,'confirmed_week':i+1}
                  for k,i,price in [('H',1,100),('L',3,80),('H',5,105),
                                    ('L',6,94.5),('H',8,110),('L',9,104.5)]]
        return w,points

    def test_three_contracting_pullbacks_and_volume(self):
        w,p = self.pattern_fixture()
        result = pattern_at(w,p,10,3)
        self.assertIsNotNone(result)
        np.testing.assert_allclose(result['depths'],[.2,.1,.05])
        w.loc[w.index[9],'Volume'] = 500
        self.assertIsNone(pattern_at(w,p,10,3))

    def test_two_pullbacks_seventy_percent_reduction_is_distinct(self):
        w,p = self.pattern_fixture()
        self.assertIsNotNone(pattern_at(w,p,10,2,'smaller'))
        self.assertIsNone(pattern_at(w,p,10,2,'70'))
        p[-1]['price'] = 107.25
        w.loc[w.index[10],'Low'] = 108
        self.assertIsNotNone(pattern_at(w,p,10,2,'70'))

    def test_time_expansion_and_broken_low_rejected(self):
        w,p = self.pattern_fixture()
        p[1]['week'] = 2
        p[3]['week'] = 7
        self.assertIsNone(pattern_at(w,p,10,3))
        w,p = self.pattern_fixture()
        w.loc[w.index[10],'Low'] = 103
        self.assertIsNone(pattern_at(w,p,10,3))

    def sim(self, bars, orders=None, exit='target_3r', entry='intraday_pivot', market=False,
            gate=None, scale=1, pyramid=False):
        arrays = {s:np.array(b,float) for s,b in bars.items()}
        dates = pd.bdate_range('2025-01-06',periods=len(next(iter(arrays.values()))))
        config = Config('three',entry,exit,market,pyramid)
        return simulate(arrays,dates,np.ones(len(dates),bool) if gate is None else gate,
                        {s:s for s in bars},orders or {1:[order()]},config,
                        str(dates[0].date()),str(dates[-1].date()),scale)

    def test_wilder_seed_and_gap_reset(self):
        r = wilder([1,2,3,6,np.nan,4,4,4],3)
        self.assertTrue(np.isnan(r[1]))
        self.assertEqual(r[2],2)
        self.assertAlmostEqual(r[3],10/3)
        self.assertTrue(np.isnan(r[6]))
        self.assertEqual(r[7],4)

    def test_weekly_does_not_use_incomplete_week(self):
        d = daily_features(price_frame(800))
        cut = pd.Timestamp('2020-12-16')  # Wednesday.
        w = weekly_features(d.loc[:cut],str(cut.date()))
        self.assertLess(w.index[-1],pd.Timestamp('2020-12-14'))

    def test_missing_session_invalidates_week(self):
        d = price_frame(800)
        day = d.index[-8]
        d.loc[day,['Open','High','Low','Close','Volume']] = np.nan
        w = weekly_features(daily_features(d),str(d.index[-1].date()))
        affected = w.loc[w.index.to_period('W-FRI') == day.to_period('W-FRI')]
        self.assertFalse(affected.complete.any())
        self.assertFalse(affected.screen.any())

    def test_pivot_needs_next_completed_week(self):
        w = pd.DataFrame({'High':[10,15,12], 'Low':[8,10,9], 'complete':[True]*3})
        self.assertEqual(update_pivots([],w,1),[])
        p = update_pivots([],w,2)
        self.assertEqual(p[0]['week'],1)
        self.assertEqual(p[0]['confirmed_week'],2)
        self.assertEqual(p[0]['kind'],'H')

    def test_ambiguous_outside_week_resets_pivots(self):
        w = pd.DataFrame({'High':[10,15,12], 'Low':[8,4,9], 'complete':[True]*3})
        self.assertEqual(update_pivots([{'kind':'H','week':0,'price':10}],w,2),[])

    def test_weekly_features_and_patterns_prefix_invariant(self):
        d = price_frame()
        full, patterns, ends, _ = prepare_symbol(d,str(d.index[-1].date()))
        for cutoff in [520,645,710]:
            part, pp, ee, _ = prepare_symbol(d.iloc[:cutoff],str(d.index[cutoff-1].date()))
            pd.testing.assert_frame_equal(full.loc[part.index].drop(columns=['weekly_exit']),
                                          part.drop(columns=['weekly_exit']))
            for name in patterns:
                for pos in ee:
                    self.assertEqual(patterns[name].get(pos),pp[name].get(pos))

    def test_weekly_watchlist_only_starts_next_day(self):
        d = daily_features(price_frame(70))
        d['Close'] = 100.
        d['atr20'] = 2.
        p = {'pivot':101.,'final_low':90.,'depth':.05,'id':'test'}
        orders = make_orders('A',d,{50:p},[50,55,60,65],'intraday_pivot')
        self.assertEqual(orders[0]['day'],51)
        self.assertNotIn(50,[o['day'] for o in orders])

    def test_daily_high_does_not_choose_prior_orders(self):
        d = daily_features(price_frame(70))
        d['Close'] = 100.
        d['Low'] = 99.
        d['High'] = 100.5
        d['atr20'] = 2.
        p = {'pivot':101.,'final_low':90.,'depth':.05,'id':'test'}
        before = make_orders('A',d,{50:p},[50,55,60,65],'intraday_pivot')
        d.iloc[51,d.columns.get_loc('High')] = 103
        after = make_orders('A',d,{50:p},[50,55,60,65],'intraday_pivot')
        self.assertEqual(before[0],after[0])

    def test_close_and_volume_confirmation_fills_next_day(self):
        d = daily_features(price_frame(70))
        d['Close'],d['Low'],d['High'],d['atr20'] = 100.,99.,101.,2.
        d['Volume'],d['volume50_prior'] = 100.,100.
        d.loc[d.index[51],['Close','High','Volume']] = [103.,104.,200.]
        p = {'pivot':102.,'final_low':90.,'depth':.05,'id':'test'}
        orders = make_orders('A',d,{50:p},[50,55,60,65],'close_volume_next_open')
        self.assertEqual(len(orders),1)
        self.assertEqual(orders[0]['signal_day'],51)
        self.assertEqual(orders[0]['day'],52)

    def test_add_requires_winner_and_new_higher_pattern(self):
        bars = [[99,101,98,99,1e6,2,0],[100,104,99,103,1e6,2,0],
                [104,110,103,109,1e6,2,0],[109,111,108,110,1e6,2,0],
                [111,114,110,113,1e6,2,0]]
        add = order(day=3,trigger=110)
        add['pattern']['id'] = 'higher-base'
        r = self.sim({'A':bars},{1:[order()],3:[add]},pyramid=True,exit='weekly_sma10')
        self.assertEqual(r['trades'][0]['adds'],1)
        self.assertEqual(len(r['trades'][0]['fills']),2)
        bars[2][3] = 102
        r = self.sim({'A':bars},{1:[order()],3:[add]},pyramid=True,exit='weekly_sma10')
        self.assertEqual(r['trades'][0]['adds'],0)

    def test_gap_through_stop_is_worse_than_stop(self):
        self.assertEqual(stop_execution(85,80,95,0),(85,'gap_stop'))

    def test_same_bar_stop_precedes_target(self):
        bars = [[99,101,98,99,1e6,2,0],[100,120,90,110,1e6,2,0],[110,111,109,110,1e6,2,0]]
        r = self.sim({'A':bars})
        self.assertEqual(r['trades'][0]['reason'],'stop')
        self.assertLess(r['trades'][0]['net_pnl'],0)

    def test_intraday_entry_cannot_exit_at_preentry_open(self):
        bars = [[95,96,94,95,1e6,2,0],[90,102,89,101,1e6,2,0],[101,102,100,101,1e6,2,0]]
        t = self.sim({'A':bars})['trades'][0]
        self.assertEqual(t['reason'],'stop')
        self.assertGreater(t['exit_price'],95)

    def test_trailing_stop_only_changes_for_next_day(self):
        bars = [[99,101,98,99,1e6,2,0],[100,112,99,111,1e6,2,0],
                [108,110,106,109,1e6,2,0],[109,110,108,109,1e6,2,0]]
        t = self.sim({'A':bars},exit='atr_trail')['trades'][0]
        self.assertEqual(t['exit_date'],'2025-01-08')
        self.assertEqual(t['reason'],'stop')

    def test_weekly_exit_at_next_open(self):
        bars = [[99,101,98,99,1e6,2,0],[100,104,99,103,1e6,2,1],
                [102,104,101,103,1e6,2,0],[103,104,102,103,1e6,2,0]]
        t = self.sim({'A':bars},exit='weekly_sma10')['trades'][0]
        self.assertEqual(t['exit_date'],'2025-01-08')
        self.assertEqual(t['reason'],'weekly_sma10')
        self.assertAlmostEqual(t['exit_price'],102*.9995)

    def test_market_uses_prior_close(self):
        bars = [[99,101,98,99,1e6,2,0],[100,104,99,103,1e6,2,0],[103,104,102,103,1e6,2,0]]
        r = self.sim({'A':bars},market=True,gate=np.array([False,True,True]))
        self.assertEqual(r['metrics']['closed_trades'],0)

    def test_initial_risk_includes_fees_and_fixed_charge(self):
        bars = [[99,101,98,99,1e6,2,0],[100,104,99,103,1e6,2,0],[103,104,102,103,1e6,2,0]]
        t = self.sim({'A':bars})['trades'][0]
        self.assertLessEqual(t['planned_risk_rupees'],500)
        self.assertGreater(t['planned_risk_rupees'],t['quantity']*(t['entry_price']-t['initial_stop']))

    def test_cash_reconciles_with_trade_log_and_cost_stress(self):
        bars = [[99,101,98,99,1e6,2,0],[100,104,99,103,1e6,2,0],[103,104,102,103,1e6,2,0]]
        a,b = [self.sim({'A':bars},scale=x) for x in [1,2]]
        self.assertAlmostEqual(a['metrics']['ending_equity'],100000+sum(t['net_pnl'] for t in a['trades']))
        self.assertLess(b['metrics']['total_return_pct'],a['metrics']['total_return_pct'])

    def test_reserved_untriggered_orders_keep_slots(self):
        bars = {}
        orders = []
        for i,s in enumerate('ABCDEF'):
            high = 99 if s != 'F' else 110
            bars[s] = [[98,99,97,98,1e6,2,0],[98,high,97,98,1e6,2,0],[98,99,97,98,1e6,2,0]]
            orders.append(order(s,depth=.01*(i+1)))
        r = self.sim(bars,{1:orders})
        self.assertEqual(r['metrics']['closed_trades'],0)
        self.assertEqual(r['metrics']['diagnostics']['reserved_untriggered_orders'],5)

    def test_terminal_day_has_no_new_entries(self):
        bars = [[99,101,98,99,1e6,2,0],[100,104,99,103,1e6,2,0],[103,104,102,103,1e6,2,0]]
        r = self.sim({'A':bars},{2:[order(day=2)]})
        self.assertEqual(r['metrics']['closed_trades'],0)

    def test_large_open_gap_rejected(self):
        bars = [[99,101,98,99,1e6,2,0],[120,124,119,123,1e6,2,0],[123,124,122,123,1e6,2,0]]
        self.assertEqual(self.sim({'A':bars})['metrics']['closed_trades'],0)

    def test_all_72_configs_unique_and_selection_ignores_later(self):
        self.assertEqual(len({c.id for c in configurations()}),72)
        m = {'closed_trades':25,'total_return_pct':10,'cagr_pct':5,'max_drawdown_pct':4}
        row = {'id':'a','development':m,'validation':m,'later':{'total_return_pct':100}}
        key = selection_key(row)
        row['later']['total_return_pct'] = -100
        self.assertEqual(selection_key(row),key)


if __name__ == '__main__':
    unittest.main()
