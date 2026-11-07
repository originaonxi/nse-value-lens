"""Tests for nifty_ema.py - the one-EMA rule: close above = up, close below = down."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nifty_ema as N


class TestEma(unittest.TestCase):
    def test_matches_pandas_ewm(self):
        x = np.linspace(100, 200, 50)
        ref = pd.Series(x).ewm(span=9, adjust=False).mean().to_numpy()
        np.testing.assert_allclose(N.ema(x, 9), ref)

    def test_side_follows_close_vs_ema(self):
        x = np.array([100.0] * 20 + [110.0] * 20)
        self.assertEqual(N.side_of(x, 5)[-1], 1)
        y = np.array([100.0] * 20 + [90.0] * 20)
        self.assertEqual(N.side_of(y, 5)[-1], -1)


class TestRule(unittest.TestCase):
    def setUp(self):
        self.close = np.array([100.0] * 20 + [110.0] * 10 + [130.0] * 10 + [90.0] * 20)
        self.flips, self.ends, self.dirs, self.gross, self.net, self.closed = N.rule_trades(self.close, 5, 0)

    def test_signal_on_each_side_switch(self):
        self.assertEqual(list(self.flips), [20, 40])
        self.assertEqual(list(self.dirs), [1, -1])
        self.assertEqual(list(self.ends), [40, 59])

    def test_held_until_opposite_close(self):
        # long from 110 (close above) to 90 (first close below)
        self.assertAlmostEqual(self.gross[0], 90 - 110)
        self.assertFalse(self.closed[-1])      # the last signal is still running

    def test_cost_is_percent_of_price(self):
        np.testing.assert_allclose(self.net, self.gross - N.COST_PCT * self.close[self.flips])


class TestMetrics(unittest.TestCase):
    def test_up_and_down_halves(self):
        m = N.metrics([10, -5, 20], [8, -7, 18], [1, -1, 1], [1, -1, np.nan], 3)
        self.assertEqual(m["trades"], 3)
        self.assertAlmostEqual(m["pf"], round(26 / 7, 2))
        self.assertAlmostEqual(m["net"], 19)
        self.assertEqual((m["up_n"], m["up_hit"], m["up_net"]), (2, 100.0, 26.0))
        self.assertEqual((m["down_n"], m["down_hit"], m["down_net"]), (1, 0.0, -7.0))
        self.assertEqual(m["fwd_hit"], 50.0)

    def test_empty(self):
        m = N.metrics([], [], [], [], 5)
        self.assertEqual(m["trades"], 0)
        self.assertIsNone(m["pf"])


def fake_rule(tf, ema, up_net, down_net, pf=1.5, nps=10.0):
    m = {"trades": 20, "sessions": 60, "up_n": 10, "down_n": 10, "up_net": up_net, "down_net": down_net,
         "net": up_net + down_net, "net_ps": nps, "pf": pf, "blocks_pos": 4, "blocks": 6, "fwd_hit_s": 55.0}
    return {"key": f"{tf}|{ema}", "tf": tf, "ema": ema, "main": m, "w140": dict(m), "full": dict(m),
            "recent": {"net": 50.0}}


class TestScore(unittest.TestCase):
    def test_rule_must_work_both_ways(self):
        both = fake_rule("15m", 50, 300.0, 200.0)
        one = fake_rule("15m", 51, 900.0, -400.0)
        N.score([both, one])
        self.assertTrue(both["two_sided"])
        self.assertFalse(one["two_sided"])
        self.assertGreater(both["code_score"], one["code_score"])

    def test_too_few_signals_not_ranked(self):
        few = fake_rule("1D", 9, 100.0, 100.0)
        few["main"]["trades"] = 3
        ok = fake_rule("1D", 10, 100.0, 100.0)
        N.score([few, ok])
        self.assertIsNone(few["code_score"])
        self.assertIsNotNone(ok["code_score"])


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
        self.d = json.loads(p.read_text(encoding="utf-8"))
        if self.d.get("version") != 2:
            self.skipTest("old nifty.json")

    def test_chosen_is_top_finalist(self):
        self.assertEqual(self.d["chosen"]["key"], self.d["finalists"][0]["key"])

    def test_chosen_chart_has_one_ema_line(self):
        c = self.d["charts"][self.d["chosen"]["tf"]]
        self.assertEqual(c["ema"], self.d["chosen"]["ema"])
        self.assertEqual(len(c["bars"]), len(c["ema_values"]))
        self.assertGreater(len(c["bars"]), 100)

    def test_every_timeframe_tested(self):
        self.assertEqual(set(self.d["heatmap"]), set(N.TIMEFRAMES))
        self.assertEqual(self.d["tested"]["ema_from"], 3)
        self.assertEqual(self.d["tested"]["ema_to"], 200)

    def test_asked_emas_present(self):
        emas = {r["ema"] for r in self.d["asked"]}
        self.assertTrue({5, 6, 9, 10, 11} <= emas)


if __name__ == "__main__":
    unittest.main()
