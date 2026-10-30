"""Invariants for the Retirement 2031 engine: selection, goal math and data integrity."""
import json
import unittest
from pathlib import Path

import retirement as R

DOCS = Path(__file__).resolve().parents[1] / "docs"


class GoalMath(unittest.TestCase):
    def test_fv_formulas_monotonic(self):
        # Higher return -> higher corpus; SIP of 0 months -> 0.
        self.assertEqual(R.fv_sip(100000, 0.12, 0), 0.0)
        self.assertLess(R.fv_lump(1e7, 0.10, 4), R.fv_lump(1e7, 0.20, 4))
        self.assertLess(R.fv_sip(4e5, 0.10, 52), R.fv_sip(4e5, 0.18, 52))

    def test_required_cagr_reaches_target(self):
        r = R.required_cagr(R.LUMP_RUPEES, R.MONTHLY_SIP, 52, 52 / 12, R.TARGET_RUPEES)
        v = R.fv_lump(R.LUMP_RUPEES, r, 52 / 12) + R.fv_sip(R.MONTHLY_SIP, r, 52)
        self.assertAlmostEqual(v, R.TARGET_RUPEES, delta=R.TARGET_RUPEES * 0.01)

    def test_months_between(self):
        from datetime import date
        self.assertEqual(R.months_between(date(2026, 10, 30), date(2031, 2, 15)), 52)


class Scoring(unittest.TestCase):
    def test_score_bounds_and_direction(self):
        strong = {"rank": {"net": 80}, "jev": {"composite": 0.9, "agrees": True},
                  "category": "breakout", "structure": "HH / HL", "change_pct": 3,
                  "volume_ratio": 1.5, "plan": {"reward_risk": [1, 3]}}
        weak = {"rank": {"net": -80}, "jev": {"composite": 0.1, "agrees": False},
                "category": "downtrend", "structure": "LL", "change_pct": -3,
                "volume_ratio": 0.5, "plan": {"reward_risk": [1, 0.3]}}
        hs, _ = R.score_stock(strong)
        ws, _ = R.score_stock(weak)
        self.assertTrue(0 <= ws < hs <= 100)
        self.assertGreater(hs, 60)
        self.assertLess(ws, 40)

    def test_action_mapping(self):
        self.assertEqual(R.action_for({"category": "downtrend", "jev": {}}, 70), "EXIT")
        self.assertEqual(R.action_for({"category": "breakout", "jev": {}}, 70), "ADD")
        self.assertEqual(R.action_for({"category": "sideways", "jev": {}}, 70), "TRIM")


class PublishedPayload(unittest.TestCase):
    """If the page has been built, its invariants must hold."""
    def setUp(self):
        p = DOCS / "retirement.json"
        if not p.exists():
            self.skipTest("retirement.json not built yet")
        self.d = json.loads(p.read_text(encoding="utf-8"))

    def test_fund_size_and_uniqueness(self):
        picks = self.d["picks"]
        self.assertLessEqual(len(picks), R.FUND_SIZE)
        syms = [p["symbol"] for p in picks]
        self.assertEqual(len(syms), len(set(syms)), "duplicate holdings")

    def test_ranked_descending_by_score(self):
        scores = [p["retire_score"] for p in self.d["picks"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        ranks = [p["fund_rank"] for p in self.d["picks"]]
        self.assertEqual(ranks, list(range(1, len(ranks) + 1)))

    def test_every_pick_has_chart_series(self):
        series = json.loads((DOCS / "daily_setups_series.json").read_text(encoding="utf-8"))["series"]
        for p in self.d["picks"]:
            self.assertIn(p["symbol"], series, f"{p['symbol']} has no chart series")
            self.assertTrue(series[p["symbol"]].get("c"), f"{p['symbol']} empty candles")

    def test_goal_and_dates_consistent(self):
        g = self.d["goal"]
        self.assertEqual(g["target"], 5_00_00_000)
        self.assertEqual(g["target_date"], "2031-02-15")
        self.assertGreaterEqual(g["months_left"], 0)
        self.assertEqual(self.d["universe"]["name"], "Nifty 100 (Nifty 50 + Next 50)")


if __name__ == "__main__":
    unittest.main()
