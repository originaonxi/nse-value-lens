import importlib.util
from pathlib import Path
import unittest
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('social_minute',ROOT/'research/social_nifty/minute/check.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ExecutionTests(unittest.TestCase):
    def test_gap_stop_loses_more_than_trigger(self):
        self.assertEqual(m.exit_fill(1,95,110,{'Open':90,'High':100,'Low':89}), (90.,'gap stop'))
        self.assertEqual(m.exit_fill(-1,105,90,{'Open':110,'High':111,'Low':100}), (110.,'gap stop'))
    def test_ambiguous_minute_uses_stop(self):
        self.assertEqual(m.exit_fill(1,95,110,{'Open':100,'High':111,'Low':94}), (95,'stop'))
        self.assertEqual(m.exit_fill(-1,105,90,{'Open':100,'High':106,'Low':89}), (105,'stop'))
    def test_target_requires_trade_through_not_just_touch(self):
        self.assertEqual(m.exit_fill(1,95,110,{'Open':100,'High':110,'Low':96}), (None,None))
        self.assertEqual(m.exit_fill(1,95,110,{'Open':100,'High':110.1,'Low':96}), (110,'target'))
    def test_open_price_precedes_intrabar_range(self):
        self.assertEqual(m.exit_fill(1,95,110,{'Open':112,'High':113,'Low':94}), (110,'target'))
    def test_flat_price_loses_after_costs_for_both_directions(self):
        day=pd.Timestamp('2019-01-02')
        for side in [-1,1]:
            candidate={'date':'2019-01-02','side':side,'entry_raw':10000.,'exit_raw':10000.,'stop':10000-side*50,'missing_held_minutes':0,'entry_zero_volume':False}
            r=m.simulate({day:candidate},[day],'2019-01-01','2019-01-31',{'fee_per_side':.0005,'slippage_per_side':.0002})
            self.assertEqual(r['closed_trades'],1)
            trade=r['trade_log'][0]
            self.assertLess(trade['pnl'],0)
            self.assertLessEqual(trade['planned_risk_pct'],.5)
            self.assertEqual(trade['qty']%75,0)
            self.assertAlmostEqual(trade['pnl']+trade['friction'],0.)
if __name__=='__main__':unittest.main()
