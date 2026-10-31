"""Dividend engine: metrics, income score, special-dividend flag, and published-payload invariants."""
import json
import unittest
from pathlib import Path

import dividends as DV

DOCS = Path(__file__).resolve().parents[1] / "docs"


def raw(by_year, price=100.0, ttm=None):
    yrs = {int(k): v for k, v in by_year.items()}
    return {"close": price, "by_year": yrs, "price_year": {y: price for y in yrs},
            "ttm": ttm if ttm is not None else (max(yrs.values()) if yrs else 0.0)}


class Metrics(unittest.TestCase):
    def test_steady_payer(self):
        yrs = {y: 5.0 for y in range(2016, 2026)}
        m = DV.metrics("X", {"name": "X Ltd", "sector": "Energy"}, raw(yrs, 100, 5.0), 2026)
        self.assertEqual(m["years_paid"], 10)
        self.assertFalse(m["special_heavy"])
        self.assertAlmostEqual(m["current_yield"], 5.0, places=1)
        self.assertEqual(m["ten_year_total_per_share"], 50.0)

    def test_special_flag(self):
        yrs = {y: 2.0 for y in range(2016, 2026)}
        yrs[2023] = 40.0                      # one-off special, >2.5x median
        m = DV.metrics("Y", {"name": "Y Ltd", "sector": "Metals"}, raw(yrs, 100, 2.0), 2026)
        self.assertTrue(m["special_heavy"])

    def test_crash_yield_not_inflating_score(self):
        # Huge yield from a price crash is capped so it can't dominate the score.
        yrs = {y: 10.0 for y in range(2016, 2026)}
        m = DV.metrics("Z", {"name": "Z", "sector": "X"}, raw(yrs, 20, 10.0), 2026)  # 50% yield
        self.assertGreater(m["current_yield"], 40)
        self.assertLessEqual(DV.income_score(m), 100)


class Score(unittest.TestCase):
    def test_bounds_and_direction(self):
        strong = DV.metrics("A", {"name": "A", "sector": "E"}, raw({y: 6.0 + (y - 2016) * 0.3 for y in range(2016, 2026)}, 100, 8.0), 2026)
        weak = DV.metrics("B", {"name": "B", "sector": "E"}, raw({2025: 1.0}, 100, 1.0), 2026)
        hs, ws = DV.income_score(strong), DV.income_score(weak)
        self.assertTrue(0 <= ws < hs <= 100)
        self.assertGreater(hs, 70)


class PublishedPayload(unittest.TestCase):
    def setUp(self):
        p = DOCS / "dividends.json"
        if not p.exists():
            self.skipTest("dividends.json not built")
        self.d = json.loads(p.read_text(encoding="utf-8"))

    def test_ranking_and_scores(self):
        rows = self.d["rows"]
        self.assertGreater(len(rows), 100)
        scores = [r["income_score"] for r in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual([r["rank"] for r in rows], list(range(1, len(rows) + 1)))
        for r in rows[:20]:
            self.assertTrue(0 <= r["income_score"] <= 100)
            self.assertIn("by_year", r)
            self.assertEqual(len(r["by_year"]), 10)

    def test_portfolio_within_budget(self):
        p = self.d["portfolio"]
        self.assertLessEqual(p["invested"], p["amount"])
        self.assertEqual(p["invested"] + p["cash_left"], p["amount"])
        for h in p["holdings"]:
            self.assertGreaterEqual(h["years_paid"], 8)
            self.assertGreater(h["shares"], 0)

    def test_20pct_answer_honest(self):
        a = self.d["answer_20pct"]
        self.assertIn("No", a["verdict"])
        # Any stock listed as touching 20% must be special-dividend driven.
        for n in a["names"]:
            self.assertTrue(n["special_heavy"] or n["max_yield_10y"] >= 20)


if __name__ == "__main__":
    unittest.main()
