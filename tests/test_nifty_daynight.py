"""Tests for nifty_daynight.py - night/day split, trade maths, opening-range breakout without look-ahead."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nifty_daynight as DN


class TestSplit(unittest.TestCase):
    def test_night_plus_day_is_close_to_close(self):
        idx = pd.date_range("2026-01-05", periods=5, freq="B")
        d = pd.DataFrame({"Open": [100, 103, 101, 108, 107.0], "High": [105, 106, 104, 110, 109.0],
                          "Low": [99, 100, 98, 104, 103.0], "Close": [102, 100, 107, 106, 108.0]}, index=idx)
        t = DN.daily_table(d)
        self.assertEqual(list(t["night"].iloc[1:]), [1.0, 1.0, 1.0, 1.0])     # open - previous close
        self.assertEqual(list(t["day"]), [2.0, -3.0, 6.0, -2.0, 1.0])          # close - open
        np.testing.assert_allclose((t["night"] + t["day"]).iloc[1:], t["cc"].iloc[1:])


class TestLeg(unittest.TestCase):
    def test_buy_and_sell_with_cost(self):
        pts = pd.Series([10.0, -4.0, 6.0])
        entry = pd.Series([1000.0, 1000.0, 1000.0])
        cost = DN.COST * 1000
        b = DN.leg(pts, entry, None, 1)
        self.assertEqual(b["n"], 3)
        self.assertAlmostEqual(b["gross"], 12.0)
        self.assertAlmostEqual(b["net"], 12 - 3 * cost, delta=0.06)
        s = DN.leg(pts, entry, None, -1)
        self.assertAlmostEqual(s["gross"], -12.0)

    def test_mask_selects_sessions(self):
        r = DN.leg(pd.Series([5.0, 5.0, 5.0]), pd.Series([100.0] * 3), [True, False, True], 1)
        self.assertEqual(r["n"], 2)


def bars(day, rows):
    idx = pd.date_range(f"{day} 09:15", periods=len(rows), freq="60min")
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx)


class TestOrb(unittest.TestCase):
    def test_enters_on_first_break_and_holds_to_close(self):
        x = bars("2026-01-05", [[100, 105, 95, 102], [102, 104, 101, 103], [103, 110, 102, 109], [109, 112, 108, 111]])
        tr = DN.orb([("2026-01-05", x)], 1)
        self.assertEqual(tr[0][1], 1)                                    # long: high 105 broken on bar 3
        self.assertAlmostEqual(tr[0][2], (111 - 105) - DN.COST * 105)

    def test_bar_breaking_both_sides_is_a_loss(self):
        x = bars("2026-01-06", [[100, 105, 95, 100], [100, 106, 94, 104]])
        tr = DN.orb([("2026-01-06", x)], 1)
        self.assertEqual(tr[0][1], 0)
        self.assertLess(tr[0][2], -9.9)

    def test_no_break_no_trade(self):
        x = bars("2026-01-07", [[100, 105, 95, 100], [100, 104, 96, 101]])
        self.assertEqual(DN.orb([("2026-01-07", x)], 1), [])


class TestPublished(unittest.TestCase):
    def setUp(self):
        p = Path(__file__).resolve().parents[1] / "docs" / "nifty_daynight.json"
        if not p.exists():
            self.skipTest("nifty_daynight.json not generated")
        self.d = json.loads(p.read_text(encoding="utf-8"))

    def test_identity_and_totals(self):
        self.assertLessEqual(self.d["checks"]["identity_max_error"], 0.01)
        t = self.d["totals"]
        self.assertAlmostEqual(t["night"] + t["day"], t["cc"], delta=0.5)
        s = self.d["series"]
        self.assertEqual(len(s), self.d["sessions"])
        self.assertAlmostEqual(sum(r[3] for r in s), t["night"], delta=0.5)

    def test_at_least_ten_ideas_with_buy_and_sell(self):
        ideas = {r["idea"].split(" ")[0] for r in self.d["rules"]}
        self.assertGreaterEqual(len(ideas), 10)
        sides = {r["side"] for r in self.d["rules"]}
        self.assertTrue({"BUY", "SELL"} <= sides)

    def test_holds_flag_matches_halves(self):
        for r in self.d["rules"]:
            if r.get("h1") is not None and r.get("h2") is not None:
                self.assertEqual(r["holds"], r["h1"] > 0 and r["h2"] > 0, r["rule"])


if __name__ == "__main__":
    unittest.main()
