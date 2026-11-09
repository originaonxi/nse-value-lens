"""Tests for cross_lab.py: cross state, confirm mode, point stops, cross price, 10% capital stop, published payload."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import cross_lab as C  # noqa: E402
from test_intraday15 import frame  # noqa: E402

DOCS = ROOT / "docs"


class Mechanics(unittest.TestCase):
    def setUp(self):
        self.X = C.features(frame(days=5), 15)

    def test_cross_state_is_side_of_fast_ema(self):
        st = C.state(self.X, 5, 9, "cross")
        self.assertTrue(np.array_equal(st, np.sign(self.X["ema"][5] - self.X["ema"][9])))

    def test_confirm_mode_waits_for_close_beyond_both(self):
        st = C.state(self.X, 5, 9, "cross + close")
        f, s, c = self.X["ema"][5], self.X["ema"][9], self.X["C"]
        k = int(np.flatnonzero(st != 0)[0])
        # at the first confirmed candle the close is beyond both EMAs on the cross side
        self.assertTrue((st[k] > 0 and c[k] > max(f[k], s[k])) or (st[k] < 0 and c[k] < min(f[k], s[k])))

    def test_intraday_only_and_point_stop(self):
        r = {"tf": 15, "a": 3, "b": 9, "mode": "cross", "side": "both", "flat": "15:00", "sl": 30, "tp": None}
        s, e, side, g, ep = C.run(self.X, r)
        self.assertGreater(len(s), 0)
        for a, b, gr in zip(s, e, g):
            self.assertEqual(self.X["did"][a], self.X["did"][b])
            gap = side[list(s).index(a)] * (self.X["O"][b] - self.X["O"][a])
            self.assertGreaterEqual(gr, min(-30 - 1e-6, gap - 1e-6))

    def test_cross_price_makes_emas_equal(self):
        ef, es, a, b = 25010.0, 24990.0, 9, 14
        p = C.cross_price(ef, es, a, b)
        fa, fb = 2 / (a + 1), 2 / (b + 1)
        self.assertAlmostEqual(ef + fa * (p - ef), es + fb * (p - es), places=6)

    def test_capital_stop_scales_with_leverage(self):
        tr = (np.array([1]), np.array([3]), np.array([1.0]), np.array([-400.0]), np.array([25000.0]))
        X = {"H": np.full(5, 25000.0), "L": np.array([25000, 25000, 24500, 24600, 25000.0])}
        (_, _, _, g1, _), h1 = C.cap_stop(X, tr, 1)
        (_, _, _, g5, _), h5 = C.cap_stop(X, tr, 5)
        self.assertEqual(h1, 0)                       # 10% of 25,000 = 2,500 pts never touched
        self.assertEqual(g1[0], -400.0)
        self.assertEqual(h5, 1)                       # 2% = 500 pts, low went 500 below
        self.assertAlmostEqual(g5[0], -500.0)


class Published(unittest.TestCase):
    def test_payload(self):
        p = DOCS / "cross.json"
        if not p.exists():
            self.skipTest("cross.json not built")
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertGreater(d["rules_tried"], 1000)
        self.assertIn(d["chosen"], [f["id"] for f in d["finalists"]])
        for f in d["finalists"]:
            self.assertEqual(f["year"]["start"], 1_00_00_000)
            self.assertAlmostEqual(f["year"]["made"] + f["year"]["lost"], f["year"]["profit"], delta=f["year"]["trades"] + 2)
            self.assertEqual([l["lev"] for l in f["ladder"]], d["levs"])
        self.assertEqual(len(d["user_pairs"]), 9)
        self.assertTrue(d["next"]["lines"])


if __name__ == "__main__":
    unittest.main()
