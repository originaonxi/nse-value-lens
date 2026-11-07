"""Tests for nifty_combo.py - EMA 105 + confirmation indicators, TOP exits, split honesty."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nifty_combo as K


def frame(closes, freq="120min"):
    c = np.asarray(closes, float)
    idx = pd.date_range("2025-01-06 09:15", periods=len(c), freq=freq)
    return pd.DataFrame({"Open": c, "High": c + 2, "Low": c - 2, "Close": c}, index=idx)


def X_from(closes, ema_n=5):
    X = K.indicators(frame(closes), ema_n)
    return X


class TestIndicators(unittest.TestCase):
    def test_rsi_bounds_and_direction(self):
        up = K.rsi(np.linspace(100, 200, 100))
        self.assertGreater(up[-1], 90)
        self.assertTrue(((up >= 0) & (up <= 100)).all())

    def test_supertrend_follows_trend(self):
        X = X_from(np.r_[np.linspace(100, 200, 80), np.linspace(200, 100, 80)])
        self.assertEqual(X["st"][79], 1)
        self.assertEqual(X["st"][-1], -1)

    def test_daily_filter_uses_yesterday(self):
        df = frame(np.linspace(100, 110, 8), "60min")
        days = pd.date_range("2024-01-01", periods=300, freq="D")
        daily = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0,
                              "Close": np.r_[np.full(299, 100.0), 1000.0]}, index=days)
        daily.index = list(days[:-1]) + [pd.Timestamp(df.index[0].date())]
        X = K.indicators(df, 5, daily)
        # the spike happens ON the 2-hour bars' own day: it must not be visible yet
        self.assertNotEqual(X["d50"][0], 1)


class TestSimulate(unittest.TestCase):
    def test_cross_entry_and_exit_with_cost(self):
        c = np.r_[np.full(20, 100.0), np.full(10, 110.0), np.full(10, 90.0)]
        X = X_from(c)
        T = np.ones(len(c), bool)
        tr = K.simulate(X, T, T, "cross", None, shorts=False, start=1)
        self.assertEqual(tr[0][0], 20)
        self.assertEqual(tr[0][4], "cross")
        self.assertAlmostEqual(tr[0][3], (c[tr[0][1]] - 110) - K.COST * 110)

    def test_filter_blocks_entry(self):
        c = np.r_[np.full(20, 100.0), np.full(10, 110.0)]
        X = X_from(c)
        none = np.zeros(len(c), bool)
        self.assertEqual(K.simulate(X, none, none, "cross", None, shorts=True, start=1), [])

    def test_top_exit_then_wait_for_pullback(self):
        c = np.r_[np.full(30, 100.0), np.linspace(101, 200, 40), np.full(10, 200.0)]
        X = X_from(c, 20)
        T = np.ones(len(c), bool)
        tr = K.simulate(X, T, T, "stretch", 3, shorts=False, start=25)
        self.assertEqual(tr[0][4], "top")
        # stays far above the EMA afterwards: no re-entry right after the TOP
        self.assertLessEqual(len(tr), 2)
        if len(tr) == 2:
            self.assertLessEqual(abs(X["dist"][tr[1][0]]), K.RE_ENTRY_ATR + 1e-9)


class TestStats(unittest.TestCase):
    def test_numbers(self):
        s = K.stats([(0, 1, 1, 30.0, "x"), (1, 2, 1, -10.0, "x"), (2, 3, -1, 20.0, "x")])
        self.assertEqual((s["n"], s["win"], s["pf"], s["net"], s["dd"]), (3, 66.7, 5.0, 40.0, 10.0))
        self.assertEqual((s["long_net"], s["short_net"]), (20.0, 20.0))

    def test_half_score_zero_when_empty(self):
        self.assertEqual(K.half_score(K.stats([])), 0.0)


class TestPublished(unittest.TestCase):
    def setUp(self):
        p = Path(__file__).resolve().parents[1] / "docs" / "nifty_combo.json"
        if not p.exists():
            self.skipTest("nifty_combo.json not generated")
        self.d = json.loads(p.read_text(encoding="utf-8"))

    def test_winner_is_robust_both_halves(self):
        w = self.d["winner"]
        self.assertGreater(w["is"]["pf"], 1)
        self.assertGreater(w["os"]["pf"], 1)
        self.assertEqual(w["id"], self.d["finalists"][0]["id"])

    def test_winner_beats_ema_alone_on_win_rate(self):
        self.assertGreater(self.d["winner"]["all"]["win"], self.d["base"]["long_only"]["all"]["win"])

    def test_chart_and_trades(self):
        ch = self.d["chart"]
        self.assertEqual(len(ch["bars"]), len(ch["ema"]))
        self.assertGreater(len(ch["bars"]), 300)
        self.assertEqual(len(self.d["trades"]), self.d["winner"]["all"]["n"])

    def test_every_combination_recorded(self):
        self.assertGreater(self.d["tested"], 5000)
        self.assertTrue(self.d["filters"] and self.d["exits"])


if __name__ == "__main__":
    unittest.main()
