import unittest
from unittest.mock import patch
from datetime import datetime
import numpy as np
import pandas as pd
from swing_engine import features, setup, fill, exit_price, backtest
from swing_research import clean, IST

class SwingTests(unittest.TestCase):
    def plan(self):
        return dict(entry_low=99, entry_high=101, stop=96, hold=5, relative_strength=.1)
    def test_gap_entry_cancelled(self):
        self.assertIsNone(fill(self.plan(), 105, 100000, 100000))
        self.assertIsNone(fill(self.plan(), 95, 100000, 100000))
    def test_risk_cash_and_capital_limits(self):
        p = fill(self.plan(), 100, 100000, 100000)
        self.assertLessEqual(p["cost"], 20000)
        self.assertLessEqual(p["risk_cash"], 500)
        self.assertIsNone(fill(self.plan(), 100, 100000, 1))
        self.assertLessEqual(fill(self.plan(), 100, 100000, 2000)["cost"], 2000)
    def test_stop_before_target(self):
        p = dict(stop=96, target=108, age=1, hold=5)
        self.assertEqual(exit_price(p, pd.Series(dict(Open=100, Low=95, High=110, Close=107)), 0), (96, "stop"))
    def test_gap_stop_worse_than_stop(self):
        p = dict(stop=96, target=108, age=1, hold=5)
        self.assertEqual(exit_price(p, pd.Series(dict(Open=90, Low=89, High=99, Close=97)), 0), (90, "gap stop"))
    def test_time_exit(self):
        p = dict(stop=96, target=108, age=5, hold=5)
        self.assertEqual(exit_price(p, pd.Series(dict(Open=100, Low=99, High=103, Close=102)), 0), (102, "time exit"))
    def test_features_do_not_see_future(self):
        index = pd.bdate_range("2023-01-01", periods=300)
        close = np.linspace(100, 180, 300)+np.sin(np.arange(300))
        d = pd.DataFrame(dict(Open=close,High=close+2,Low=close-2,Close=close,Volume=2e6), index=index)
        pd.testing.assert_frame_equal(features(d).iloc[:250], features(d.iloc[:250]))
        self.assertEqual(features(d).iloc[249].prior_high, d.High.iloc[229:249].max())
    def test_market_gate_blocks_every_strategy(self):
        row = pd.Series(dict(Close=110,atr=2,sma50=100,sma200=90,ema20=105,ret63=.2,turnover=1e9,vol_ratio=2))
        market = pd.Series(dict(Close=90,sma50=100,sma200=95,ret63=.1))
        for strategy in ["breakout","pullback","reversion"]:
            self.assertIsNone(setup(row,market,strategy))
    def test_next_day_entry_and_five_session_exit(self):
        days = pd.bdate_range("2025-01-01", periods=8)
        d = pd.DataFrame(dict(Open=100.,High=101.,Low=99.,Close=100.,Volume=1e6), index=days)
        with patch("swing_engine.setup", return_value=self.plan()):
            result = backtest({"A":d},d,{"A":"X"},"breakout","2025-01-01","2025-01-10")
        first = result["trade_log"][0]
        self.assertEqual(first["signal_date"], "2025-01-01")
        self.assertEqual(first["entry_date"], "2025-01-02")
        self.assertEqual(first["direction"], "LONG")
        self.assertEqual(first["status"], "CLOSED")
        self.assertGreater(first["entry_price"], 100)
        self.assertLess(first["exit_price"], 100)
        self.assertAlmostEqual(first["pnl"], first["quantity"]*(first["exit_price"]*.9985-first["entry_price"]*1.0015), places=2)
        self.assertLess(first["return_pct"], 0)
        self.assertEqual(result["open_trade_log"][0]["status"], "OPEN")
        self.assertIsNone(result["open_trade_log"][0]["exit_price"])
        self.assertEqual(first["exit_date"], "2025-01-08")
        self.assertEqual(first["sessions"], 5)
        self.assertLess(first["pnl"], 0)
    def test_partial_candle_removed(self):
        d = pd.DataFrame(dict(Open=[100,101],High=[102,103],Low=[99,100],Close=[101,102],Volume=[100,100]),
                         index=pd.to_datetime(["2026-09-22","2026-09-23"]))
        self.assertEqual(len(clean(d,datetime(2026,9,23,14,tzinfo=IST))),1)
        self.assertEqual(len(clean(d,datetime(2026,9,23,17,tzinfo=IST))),2)
    def test_impossible_bar_removed(self):
        d = pd.DataFrame(dict(Open=[100],High=[90],Low=[80],Close=[99],Volume=[100]), index=pd.to_datetime(["2026-09-22"]))
        self.assertTrue(clean(d).empty)

if __name__ == "__main__":
    unittest.main()
