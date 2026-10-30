"""Fund engine rules: weights add to 100%, caps hold, no look-ahead, exits fire, payload is consistent."""
import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import fund as F

DOCS = Path(__file__).resolve().parents[1] / "docs"


def synthetic(n_stocks=60, days=400, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-03", periods=days)
    drift = np.linspace(-0.0005, 0.0015, n_stocks)
    rets = rng.normal(drift, 0.015, size=(days, n_stocks))
    px = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=idx, columns=[f"S{i}" for i in range(n_stocks)])
    nifty = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, days))), index=idx)
    sectors = {c: f"Sector{i % 6}" for i, c in enumerate(px.columns)}
    return px, nifty, sectors


class Weights(unittest.TestCase):
    def test_round_to_100_is_exact(self):
        for seed in range(20):
            w = pd.Series(np.random.default_rng(seed).random(37))
            r = F.round_to_100(w)
            self.assertAlmostEqual(float(r.sum()), 100.0, places=6)
            self.assertTrue((r >= 0).all())

    def test_caps_hold(self):
        # 30 stocks: 10 in one sector (capped at 30% together) + 20 others at most 6% each = feasible.
        raw = pd.Series([50.0] + [1.0] * 29, index=[f"S{i}" for i in range(30)])
        sectors = {f"S{i}": ("Big" if i < 10 else f"Other{i}") for i in range(30)}
        w = F.cap_weights(raw, sectors, max_w=0.06, max_s=0.30)
        self.assertAlmostEqual(float(w.sum()), 1.0, places=9)
        self.assertLessEqual(float(w.max()), 0.06 + 1e-9)
        big = sum(w[s] for s in w.index if sectors[s] == "Big")
        self.assertLessEqual(big, 0.30 + 1e-6)


class NoLookAhead(unittest.TestCase):
    def test_future_prices_do_not_change_todays_score(self):
        px, _, _ = synthetic()
        i = 300
        base = F.score_universe(px, i)
        future = px.copy()
        future.iloc[i + 1:] *= 3.0
        self.assertTrue(base.equals(F.score_universe(future, i)))

    def test_month_end_rows_skip_running_month(self):
        idx = pd.bdate_range("2024-01-01", "2024-03-14")
        rows = F.month_end_rows(idx)
        self.assertEqual([str(idx[r].date()) for r in rows], ["2024-01-31", "2024-02-29"])

    def test_holiday_on_last_weekday_keeps_month_end(self):
        # NSE was shut on Tue 31 Mar 2026, so Mon 30 Mar was March's last session.
        idx = pd.bdate_range("2026-01-01", "2026-03-30")
        rows = F.month_end_rows(idx, holidays={"2026-03-31"})
        self.assertEqual(str(idx[rows[-1]].date()), "2026-03-30")
        self.assertEqual(len(F.month_end_rows(idx, holidays=set())), 2)


class Backtest(unittest.TestCase):
    def setUp(self):
        self.px, self.nifty, self.sectors = synthetic()

    def test_weights_and_exits(self):
        dma = self.px.rolling(F.DMA, min_periods=F.DMA).mean()
        bt = F.backtest(self.px, self.nifty, self.sectors, holdings=20, exit_sig=self.px < dma)
        self.assertGreater(len(bt["history"]), 2)
        for h in bt["history"]:
            pub = F.published(h["weights"], h["cash_pct"])
            self.assertAlmostEqual(float(pub.sum()), 100.0, places=6)
            self.assertLessEqual(len(h["weights"]), 20)
            for e in h["exits"]:
                self.assertIn(e["symbol"], h["weights"])
        self.assertTrue(np.isfinite(bt["nav"]).all())
        self.assertGreater(float(bt["nav"].iloc[-1]), 0)

    def test_exit_rule_sells_more_than_none(self):
        dma = self.px.rolling(F.DMA, min_periods=F.DMA).mean()
        with_exit = F.backtest(self.px, self.nifty, self.sectors, holdings=20, exit_sig=self.px < dma)
        without = F.backtest(self.px, self.nifty, self.sectors, holdings=20, exit_sig=None)
        self.assertGreaterEqual(with_exit["exits_per_year"], without["exits_per_year"])
        self.assertEqual(without["exits_per_year"], 0)

    def test_supertrend_direction_values(self):
        c = self.px["S5"]
        d = F.supertrend_dir(c * 1.01, c * 0.99, c)
        self.assertTrue(set(np.unique(d[~np.isnan(d)])) <= {-1.0, 1.0})


class PublishedFund(unittest.TestCase):
    def setUp(self):
        p = DOCS / "fund.json"
        if not p.exists():
            self.skipTest("fund.json not built")
        self.d = json.loads(p.read_text(encoding="utf-8"))

    def test_today_adds_to_100(self):
        p = self.d["portfolio"]
        total = sum(h["weight_pct"] for h in self.d["holdings"]) + p["cash_pct"]
        self.assertAlmostEqual(total, 100.0, places=2)
        self.assertLessEqual(p["holdings_count"], F.HOLDINGS)

    def test_every_month_adds_to_100(self):
        for m in self.d["history"]:
            self.assertAlmostEqual(sum(m["weights"].values()), 100.0, places=2, msg=m["date"])

    def test_all_100_ranked_with_jev_fields(self):
        rows = self.d["all100"]
        self.assertEqual(len(rows), 100)
        self.assertEqual(len({r["symbol"] for r in rows}), 100)
        for r in rows:
            for k in ("jev_score", "jev_rank100", "jev_direction", "momentum_rank", "status"):
                self.assertIn(k, r)
        held = {h["symbol"] for h in self.d["holdings"] if h["status"] == "held"}
        self.assertEqual(held, {r["symbol"] for r in rows if r["in_fund"]})

    def test_holdings_carry_jev_and_exit_level(self):
        for h in self.d["holdings"]:
            for k in ("jev_score", "jev_rank", "jev_direction", "dma200", "plan_side"):
                self.assertIn(k, h)

    def test_live_variant_matches_headline(self):
        live = [v for v in self.d["variants"] if v["live"]]
        self.assertEqual(len(live), 1)
        self.assertAlmostEqual(live[0]["cagr"], self.d["stats"]["cagr"]["fund"], places=2)


if __name__ == "__main__":
    unittest.main()
