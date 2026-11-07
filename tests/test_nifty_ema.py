"""Tests for nifty_ema.py — EMA rule mechanics, session handling, costs and metrics."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nifty_ema as N


def frame(closes, per_session=None, start="2026-01-05 09:15"):
    idx = pd.date_range(start, periods=len(closes), freq="15min")
    df = pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes, "Volume": 0.0}, index=idx)
    if per_session:
        df["session"] = [f"d{i // per_session:03d}" for i in range(len(closes))]
    else:
        df["session"] = "d000"
    return df


class TestEma(unittest.TestCase):
    def test_matches_pandas_ewm(self):
        x = np.linspace(100, 200, 50)
        ref = pd.Series(x).ewm(span=9, adjust=False).mean().to_numpy()
        np.testing.assert_allclose(N.ema(x, 9), ref)

    def test_side_follows_close_vs_ema(self):
        x = np.array([100.0] * 20 + [110.0] * 20)
        s = N.side_close_vs_ema(x, 5)
        self.assertEqual(s[-1], 1)
        y = np.array([100.0] * 20 + [90.0] * 20)
        self.assertEqual(N.side_close_vs_ema(y, 5)[-1], -1)


class TestBacktest(unittest.TestCase):
    def test_uptrend_daily_one_long_trade_profit(self):
        closes = list(np.linspace(100, 200, 120))
        df = frame(closes)
        side = N.side_close_vs_ema(np.array(closes), 10)
        trades, open_pos = N.backtest(df, side, intraday=False, warm=30, cost=0)
        self.assertEqual(trades, [])          # never flips → still open
        self.assertIsNotNone(open_pos)
        self.assertEqual(open_pos[1], 1)

    def test_intraday_flat_at_session_end(self):
        closes = list(np.linspace(100, 130, 60))
        df = frame(closes, per_session=20)
        side = np.ones(len(closes))
        trades, open_pos = N.backtest(df, side, intraday=True, warm=0, cost=0)
        self.assertTrue(all(t[6] == "session_end" for t in trades))
        self.assertEqual(len(trades), 3)
        self.assertIsNone(open_pos)
        sess = df["session"].to_numpy()
        for t in trades:
            self.assertEqual(sess[t[0]], sess[t[1]])   # never carried overnight

    def test_cost_deducted_per_round_trip(self):
        closes = [100.0, 101, 102, 103, 104, 103, 102, 101]
        df = frame(closes)
        side = np.array([1, 1, 1, 1, 1, -1, -1, -1], dtype=float)
        trades, _ = N.backtest(df, side, intraday=False, warm=0, cost=2.0)
        self.assertEqual(len(trades), 1)
        self.assertAlmostEqual(trades[0][5], (103 - 100) - 2.0)

    def test_short_side_profit_sign(self):
        closes = [100.0, 99, 98, 97, 98]
        df = frame(closes)
        side = np.array([-1, -1, -1, -1, 1], dtype=float)
        trades, _ = N.backtest(df, side, intraday=False, warm=0, cost=0)
        self.assertAlmostEqual(trades[0][5], 100 - 98)


class TestMetrics(unittest.TestCase):
    def test_pf_winrate_net(self):
        df = frame([100.0] * 10)
        trades = [(0, 1, 1, 100, 110, 10.0, "flip"), (2, 3, 1, 100, 95, -5.0, "flip"), (4, 5, -1, 100, 90, 10.0, "flip")]
        m = N.metrics(trades, df, {"d000"})
        self.assertEqual(m["trades"], 3)
        self.assertAlmostEqual(m["win_rate"], 66.7)
        self.assertAlmostEqual(m["pf"], 4.0)
        self.assertAlmostEqual(m["net"], 15.0)
        self.assertAlmostEqual(m["max_dd"], 5.0)

    def test_empty_window(self):
        m = N.metrics([], frame([1.0, 2.0]), {"x"})
        self.assertEqual(m["trades"], 0)
        self.assertIsNone(m["pf"])


class TestSessionGrouping(unittest.TestCase):
    def test_two_hour_bars_never_cross_days(self):
        idx = pd.DatetimeIndex(list(pd.date_range("2026-01-05 09:15", periods=7, freq="60min")) +
                               list(pd.date_range("2026-01-06 09:15", periods=7, freq="60min")))
        df = pd.DataFrame({"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 1.0}, index=idx)
        g = N._group_session(df, 2)
        self.assertEqual(len(g), 8)           # 4 per day (2+2+2+1)
        self.assertEqual(len(set(g.index.date)), 2)


class TestPublished(unittest.TestCase):
    def setUp(self):
        p = Path(__file__).resolve().parents[1] / "docs" / "nifty.json"
        if not p.exists():
            self.skipTest("nifty.json not generated")
        import json
        self.d = json.loads(p.read_text(encoding="utf-8"))

    def test_chosen_is_top_finalist_and_eligible(self):
        self.assertEqual(self.d["chosen"]["key"], self.d["finalists"][0]["key"])
        self.assertIn(self.d["chosen"]["tf"], N.ELIGIBLE_TF)

    def test_bars_cover_all_timeframes(self):
        for tf in ("15m", "30m", "1h", "2h", "1D"):
            self.assertGreater(len(self.d["bars"][tf]), 100, tf)

    def test_asked_emas_present(self):
        emas = {r["ema"] for r in self.d["asked"]}
        self.assertTrue({5, 6, 9, 10, 11} <= emas)


if __name__ == "__main__":
    unittest.main()
