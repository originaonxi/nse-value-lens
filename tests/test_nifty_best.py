"""Tests for nifty_best.py - the simulator's exits, no-look-ahead order-flow features and the published payload."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nifty_best as B  # noqa: E402


def fake(c, ema, atr=10.0, rsi=50.0):
    c = np.asarray(c, float)
    n = len(c)
    e = np.asarray(ema, float) if np.ndim(ema) else np.full(n, float(ema))
    return {"c": c, "ema": e, "atr": np.full(n, atr), "rsi": np.full(n, rsi) if np.ndim(rsi) == 0 else np.asarray(rsi, float),
            "dist": (c - e) / atr}


class TestSimulate(unittest.TestCase):
    def test_exit_on_close_through_ema(self):
        X = fake([90, 110, 120, 95, 90], 100)
        tr = B.simulate(X, np.ones(5, bool), 1, start=0)
        self.assertEqual((tr[0][0], tr[0][1], tr[0][3]), (1, 3, "ema"))
        self.assertAlmostEqual(tr[0][2], ((95 - 110) - B.COST * 110) / 110 * 100)

    def test_target_and_stop_in_atr(self):
        X = fake([90, 110, 116, 125, 130], 100, atr=10)
        tr = B.simulate(X, np.ones(5, bool), 1, tp=1.5, start=0)
        self.assertEqual((tr[0][1], tr[0][3]), (3, "target"))      # +15 = 1.5 ATR reached at bar 3
        X = fake([90, 130, 112, 108, 140], 100, atr=10)
        tr = B.simulate(X, np.ones(5, bool), 1, sl=1.5, start=0)
        self.assertEqual((tr[0][1], tr[0][3]), (2, "stop"))        # -18 <= -15

    def test_no_reentry_until_back_near_ema(self):
        X = fake([90, 110, 125, 130, 132, 104, 111], 100, atr=10)
        tr = B.simulate(X, np.ones(7, bool), 1, tp=1.0, start=0)
        self.assertEqual(tr[0][3], "target")
        self.assertEqual(tr[1][0], 5)                              # waits until within 1 ATR of EMA 105

    def test_short_side(self):
        X = fake([110, 90, 80, 105], 100)
        tr = B.simulate(X, np.ones(4, bool), -1, start=0)
        self.assertEqual((tr[0][0], tr[0][1]), (1, 3))
        self.assertGreater(tr[0][2], -100)

    def test_rsi_top(self):
        X = fake([90, 110, 120, 125, 124], 100, rsi=[50, 60, 72, 70, 64])
        tr = B.simulate(X, np.ones(5, bool), 1, rsi=70, start=0)
        self.assertEqual((tr[0][1], tr[0][3]), (4, "top"))


class TestStats(unittest.TestCase):
    def test_numbers(self):
        s = B.stats([(0, 1, 2.0, "x"), (1, 2, -1.0, "x"), (2, 3, 1.0, "x")])
        self.assertEqual((s["n"], s["win"], s["pf"], s["net"], s["dd"]), (3, 66.7, 3.0, 2.0, 1.0))
        self.assertEqual(B.bayes(s), 60.0)


class TestPublished(unittest.TestCase):
    def setUp(self):
        p = Path(__file__).resolve().parents[1] / "docs" / "nifty_best.json"
        if not p.exists():
            self.skipTest("nifty_best.json not generated")
        self.d = json.loads(p.read_text(encoding="utf-8"))

    def test_at_least_200_sessions(self):
        self.assertGreaterEqual(self.d["period"]["sessions"], 200)

    def test_best_is_profitable_in_every_third(self):
        b = self.d["best"]
        self.assertTrue(b["every_third"])
        self.assertTrue(all(t["pf"] > 1 for t in b["thirds"]))
        self.assertGreaterEqual(b["all"]["n"], B.MIN_TRADES)
        self.assertEqual(len(self.d["trades"]), b["all"]["n"])

    def test_win80_counts(self):
        w = self.d["win80"]
        self.assertTrue(all(r["all"]["win"] >= 80 for r in w["rules"]))
        self.assertTrue(all(r["every_third"] for r in w["robust_rules"]))
        self.assertLessEqual(w["every_third"], w["count"])


if __name__ == "__main__":
    unittest.main()
