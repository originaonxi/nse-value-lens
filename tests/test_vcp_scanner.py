import unittest
from unittest.mock import patch
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from test_vcp import price_frame
from vcp_research import daily_features, weekly_features, prepare_symbol
from vcp_scanner import scan_stock, pattern_state, MODES, run

META = {'Symbol':'TEST', 'Company Name':'Test company', 'Industry':'Test industry'}


class VCPScannerTests(unittest.TestCase):
    def test_failed_price_refresh_retains_scan_and_publishes_failure_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'docs').mkdir()
            source={'scan_as_of':'2026-09-23','target_session':'2026-09-24','run_id':'test','state':'failed'}
            (root/'docs/hhhl_refresh_status.json').write_text(json.dumps(source))
            with patch('vcp_scanner.ROOT',root), patch('vcp_scanner.publish') as pub, patch('vcp_scanner.build') as build, contextlib.redirect_stdout(io.StringIO()):
                result=run()
            self.assertEqual(result['state'],'failed')
            build.assert_not_called()
            self.assertEqual(pub.call_count,1)
            self.assertEqual(pub.call_args.args[0],'vcp_refresh_status')

    def test_missing_refresh_status_is_reported_as_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('vcp_scanner.ROOT',Path(directory)), patch('vcp_scanner.publish') as pub, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run()['state'],'failed')
            self.assertEqual(pub.call_args.args[0],'vcp_refresh_status')

    def test_daily_break_does_not_trigger_before_weekly_confirmation(self):
        d = daily_features(price_frame(70))
        d[['Open','Close','Low','High']] = [100.,100.,99.,100.05]
        d['atr20'] = 2.
        p = {'pivot':101., 'final_low':90., 'id':'base'}
        d.loc[d.index[60],'High'] = 110.
        self.assertEqual(pattern_state(d, p, {60:p}, [60]), ('WATCH',None))
        d.loc[d.index[61],'High'] = 102.
        self.assertEqual(pattern_state(d, p, {60:p}, [60]), ('TRIGGERED',str(d.index[61].date())))

    def test_previously_triggered_pattern_is_not_recycled_next_week(self):
        d = daily_features(price_frame(70))
        d[['Open','Close','Low','High']] = [100.,100.,99.,100.05]
        d['atr20'] = 2.
        p = {'pivot':101., 'final_low':90., 'id':'base'}
        d.loc[d.index[61],'High'] = 102.
        self.assertEqual(pattern_state(d, p, {60:p,65:p}, [60,65])[0], 'TRIGGERED')

    def test_failed_low_and_close_beyond_pivot_block_pending_entry(self):
        d = daily_features(price_frame(70))
        d[['Open','Close','Low','High']] = [100.,100.,99.,100.05]
        d['atr20'] = 2.
        p = {'pivot':101., 'final_low':90., 'id':'base'}
        d.loc[d.index[62],'Low'] = 89.
        self.assertEqual(pattern_state(d, p, {60:p}, [60])[0], 'INVALIDATED')
        d.loc[d.index[62],'Low'] = 99.
        d.loc[d.index[62],['Close','High']] = [101.02,101.03]
        self.assertEqual(pattern_state(d, p, {60:p}, [60])[0], 'EXPIRED')

    def test_missing_latest_and_short_history_never_give_entry_levels(self):
        for count, missing in [(100,False),(800,True)]:
            d = price_frame(count)
            if missing:
                d.iloc[-1] = np.nan
            row = scan_stock(META,d,str(d.index[-1].date()))
            self.assertFalse(row['data_ready'])
            for result in row['modes'].values():
                self.assertEqual(result['state'],'DATA')
                self.assertIsNone(result.get('preview'))

    def test_gap_and_suspect_adjustment_are_visible_and_blocked(self):
        for mode in ('gap','jump'):
            d = price_frame(800)
            if mode == 'gap':
                d.iloc[-40] = np.nan
            else:
                d.iloc[-40:,d.columns.get_indexer(['Open','High','Low','Close','QuoteClose'])] *= 2
            row = scan_stock(META,d,str(d.index[-1].date()))
            self.assertFalse(row['data_ready'])
            self.assertTrue(row['audit']['missing_sessions' if mode=='gap' else 'large_jumps'])

    def test_scanner_matches_research_weekly_patterns(self):
        # Real daily chronology, same rule functions, and a midweek cutoff.
        frame=price_frame(800)
        for n in (710,753,800):
            d=frame.iloc[:n]
            date=str(d.index[-1].date())
            _,patterns,ends,_=prepare_symbol(d,date)
            row=scan_stock(META,d,date)
            for mode in MODES:
                self.assertEqual(row['modes'][mode]['pattern'],patterns[mode].get(ends[-1]))
            self.assertTrue(all(b['date']<=date for b in row['chart']))

    def test_watch_preview_uses_latest_daily_atr_and_caps_risk(self):
        # Exercise the live WATCH branch even when no real current stock qualifies.
        d=price_frame(800)
        date=str(d.index[-1].date())
        weekly=weekly_features(daily_features(d),date)
        weekly['screen']=False
        weekly.iloc[-1,weekly.columns.get_loc('screen')]=True
        pivot=float(d.High.max()*2)
        pattern={'pivot':pivot,'final_low':.01,'id':'fixture','count':3,'depths':[.2,.1,.05]}
        with patch('vcp_scanner.weekly_features',return_value=weekly), patch('vcp_scanner.pattern_at',return_value=pattern):
            row=scan_stock(META,d,date)
        for state in row['modes'].values():
            self.assertEqual(state['state'],'WATCH')
            self.assertGreater(state['preview']['trigger'],row['close'])
            self.assertLessEqual(state['preview']['risk_pct'],10)
            self.assertAlmostEqual(state['preview']['stop_at_trigger'],
                state['preview']['trigger']-min(2*row['atr20'],.1*state['preview']['trigger']),places=3)


if __name__=='__main__':
    unittest.main()
