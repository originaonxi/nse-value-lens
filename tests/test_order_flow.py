"""Tests for order_flow.py (maths ported from MrChartist/order-flow) and quant_math.py (quantbot-math formulas)."""
import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import order_flow as F  # noqa: E402
import quant_math as Q  # noqa: E402

DOCS = Path(__file__).resolve().parents[1] / "docs"


class TestBuildUp(unittest.TestCase):
    def test_four_build_ups_by_sign(self):
        p = np.array([1, -1, 1, -1, 0, 1])
        oi = np.array([5, 5, -5, -5, 5, 0])
        self.assertEqual(list(F.build_up(p, oi)),
                         ["LONG_BUILD", "SHORT_BUILD", "SHORT_COVER", "LONG_UNWIND", "NEUTRAL", "NEUTRAL"])

    def test_percentile_matches_repo(self):
        # percentile(): share of the list a value sits above, ties sharing a rank, 1 for a single item
        np.testing.assert_allclose(F.pct_rank([1, 2, 2, 4]), [0, 1 / 3, 1 / 3, 1])
        np.testing.assert_allclose(F.pct_rank([7]), [1])


def table(rows):
    T = pd.DataFrame(rows)
    for c in ("put_oi", "call_oi", "support", "resistance", "support2", "resistance2", "lot", "fut_vol", "o0", "h0", "l0", "o1"):
        if c not in T.columns:
            T[c] = np.nan
    return T


class TestReadings(unittest.TestCase):
    def setUp(self):
        base = dict(e0=pd.Timestamp("2026-01-27"), e1=pd.Timestamp("2026-02-24"), c1=0.0)
        rows = []
        for i, (d, c, p, spot, oi, chg, pa, ca) in enumerate([
            ("2026-01-05", 100.0, 99.0, 100.0, 1000, 0, 0, 0),
            ("2026-01-06", 102.0, 100.0, 102.0, 1100, 100, 50, 10),      # +2%, OI up -> long build-up, puts added
            ("2026-01-07", 100.0, 102.0, 100.0, 1000, -100, 5, 20),      # -1.96%, OI down -> long unwinding
            ("2026-01-08", 100.2, 100.0, 100.2, 1000, 0, 0, 0),          # +0.2% -> rangebound
        ]):
            rows.append(dict(base, symbol="ABC", date=d, c0=c, p0=p, spot=spot, oi=oi, oi_chg=chg, put_add=pa, call_add=ca))
        self.T = F.readings(table(rows), {"ABC": "Tech"}).set_index("date")

    def test_side_floor_and_build_up(self):
        self.assertEqual(self.T.loc["2026-01-06", "side"], "bullish")
        self.assertEqual(self.T.loc["2026-01-06", "buildup"], "LONG_BUILD")
        self.assertEqual(self.T.loc["2026-01-07", "side"], "bearish")
        self.assertEqual(self.T.loc["2026-01-07", "buildup"], "LONG_UNWIND")
        self.assertEqual(self.T.loc["2026-01-08", "side"], "rangebound")

    def test_checks_and_conviction(self):
        r = self.T.loc["2026-01-06"]
        self.assertEqual(r.chk_fresh, 1)          # long build-up with a bullish move
        self.assertEqual(r.chk_spot, 1)
        self.assertEqual(r.chk_options, 1)        # puts added 50 > calls 10
        self.assertAlmostEqual(r.conviction, 10.0)  # OI +10% opened: full
        u = self.T.loc["2026-01-07"]
        self.assertEqual(u.chk_fresh, 0)          # positions closed, not opened
        self.assertAlmostEqual(u.conviction, 100 / 1100 * 100 / 2, places=4)  # closing counts half


class TestForward(unittest.TestCase):
    def test_next_session_return_and_roll(self):
        base = dict(symbol="ABC", oi=1, oi_chg=0, put_add=0, call_add=0, spot=100)
        rows = [
            dict(base, date="2026-01-26", e0=pd.Timestamp("2026-01-27"), c0=100.0, p0=99.0, o0=100.0, e1=pd.Timestamp("2026-02-24"), c1=101.0, o1=100.5),
            dict(base, date="2026-01-27", e0=pd.Timestamp("2026-01-27"), c0=103.0, p0=100.0, o0=101.0, e1=pd.Timestamp("2026-02-24"), c1=104.0, o1=102.0),
            dict(base, date="2026-01-28", e0=pd.Timestamp("2026-02-24"), c0=106.0, p0=104.0, o0=105.0, e1=pd.Timestamp("2026-03-30"), c1=107.0, o1=106.0),
        ]
        T = F.add_forward(F.readings(table(rows), {})).set_index("date")
        self.assertAlmostEqual(T.loc["2026-01-26", "r_cc"], 3.0)                 # same month, 100 -> 103
        self.assertAlmostEqual(T.loc["2026-01-27", "r_cc"], (106 / 104 - 1) * 100)  # expiry day: next month 104 -> 106
        self.assertAlmostEqual(T.loc["2026-01-27", "r_oc"], (106 / 105 - 1) * 100)
        self.assertTrue(math.isnan(T.loc["2026-01-28", "r_cc"]))


class TestQuantMath(unittest.TestCase):
    def test_hurst_random_walk_near_half(self):
        r = np.random.default_rng(1).normal(0, 0.01, 4000)
        self.assertAlmostEqual(Q.hurst(r), 0.5, delta=0.1)

    def test_dickey_fuller_on_reverting_series(self):
        rng = np.random.default_rng(2)
        y = np.zeros(800)
        for i in range(1, 800):
            y[i] = 0.9 * y[i - 1] + rng.normal()
        g, t, hl = Q.dickey_fuller(y)
        self.assertLess(t, -2.86)
        self.assertAlmostEqual(hl, -math.log(2) / g)
        self.assertAlmostEqual(hl, math.log(2) / 0.1, delta=3)

    def test_strategy_formulas(self):
        s = Q.strategy_stats("x", [2, 2, 2, -1, -1], years=1.0, n_tested=100)
        self.assertAlmostEqual(s["win"], 60.0)
        self.assertAlmostEqual(s["ev"], 0.6 * 2 - 0.4 * 1, places=3)            # 4.1
        self.assertAlmostEqual(s["breakeven_win"], 100 / 3, places=1)            # 4.2
        self.assertAlmostEqual(s["pf"], 3.0)                                     # 4.4
        self.assertAlmostEqual(s["win_bayes"], 4 / 7 * 100, places=1)             # 4.5
        self.assertAlmostEqual(s["kelly"], (0.6 - 0.4 / 2) * 100, places=1)       # 5.2
        self.assertAlmostEqual(s["p_false"], (1 - 0.95 ** 100) * 100, places=1)   # 8.3
        self.assertAlmostEqual(s["best_of_n_sr"], math.sqrt(2 * math.log(100)), places=2)   # 8.4


class TestPublished(unittest.TestCase):
    def test_order_flow_json(self):
        p = DOCS / "order_flow.json"
        if not p.exists():
            self.skipTest("order_flow.json not generated")
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(d["rows"]), 200)
        self.assertEqual(sum(d["counts"].values()), len(d["rows"]))
        self.assertIn("Required Notice", d["upstream"]["notice"])
        self.assertGreater(d["backtest"]["span"]["sessions"], 100)
        for r in d["rows"]:
            # no change on either side is no build-up: NEUTRAL when the futures price is unchanged
            # (BPCL 9 Nov 2026: 317.55 both days) or the open interest is unchanged (ANGELONE 9 Nov 2026)
            if r["buildup"] == "NEUTRAL":
                self.assertTrue(r["fut"] == r["fut_prev"] or (r["oi_chg"] or 0) == 0, r["symbol"])
                continue
            if r["side"] == "bullish":
                self.assertIn(r["buildup"], ("LONG_BUILD", "SHORT_COVER"))
            if r["side"] == "bearish":
                self.assertIn(r["buildup"], ("SHORT_BUILD", "LONG_UNWIND"))

    def test_quant_math_json(self):
        p = DOCS / "quant_math.json"
        if not p.exists():
            self.skipTest("quant_math.json not generated")
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(len(d["catalogue"]), 48)
        self.assertEqual(sum(d["counts"].values()), 48)
        self.assertGreaterEqual(d["summary"]["stocks"], 200)

    def test_vendored_licence_kept(self):
        lic = Path(__file__).resolve().parents[1] / "vendor" / "order-flow" / "LICENSE"
        self.assertTrue(lic.exists())
        self.assertIn("Required Notice: Copyright (c) 2026 Mr. Chartist", lic.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
