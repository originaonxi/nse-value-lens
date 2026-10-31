"""Unit tests for dma_desk.py — DMA crossover classification, backtest, scoring, portfolio."""
import math, sys, unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dma_desk as D


def _prices(n=500, trend="up", noise=0.01, seed=42):
    """Synthetic daily close prices."""
    rng = np.random.default_rng(seed)
    drift = {"up": 0.0005, "down": -0.0005, "flat": 0.0}[trend]
    log_ret = rng.normal(drift, noise, n)
    px = 1000 * np.exp(np.cumsum(log_ret))
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    return pd.Series(px, index=idx, name="TEST")


def _make_dmas(series, windows=None):
    px = series.to_frame()
    return D.compute_dmas(px)


class TestComputeDMAs(unittest.TestCase):
    def test_shape_and_nan_head(self):
        s = _prices(500)
        dmas = _make_dmas(s)
        for w in D.DMA_WINDOWS:
            self.assertIn(w, dmas)
            # First (w-1) values must be NaN
            self.assertTrue(dmas[w]["TEST"].iloc[:w - 1].isna().all())
            # After w values we have a number
            self.assertTrue(math.isfinite(float(dmas[w]["TEST"].iloc[w])))

    def test_200dma_lags_price(self):
        """With a perfect monotonic uptrend the 200-DMA must be below close."""
        idx = pd.date_range("2019-01-01", periods=600, freq="B")
        s = pd.Series(np.linspace(1000, 3000, 600), index=idx, name="TEST")
        dmas = _make_dmas(s)
        close = float(s.iloc[-1])
        d200 = float(dmas[200]["TEST"].dropna().iloc[-1])
        self.assertGreater(close, d200)


class TestClassifyCrossover(unittest.TestCase):
    def _classify(self, series):
        px = series.to_frame()
        dmas = D.compute_dmas(px)
        return D.classify_crossover("TEST", series, dmas)

    def test_platinum_uptrend(self):
        cross_type, align_sc, gates, dv = self._classify(_prices(600, "up"))
        self.assertIn(cross_type, ("platinum", "watch", "golden"))  # strong uptrend
        self.assertGreater(align_sc, 0)

    def test_bear_downtrend(self):
        cross_type, align_sc, gates, dv = self._classify(_prices(600, "down"))
        self.assertIn(cross_type, ("bear", "death", "neutral"))

    def test_insufficient_data(self):
        cross_type, align_sc, gates, dv = self._classify(_prices(50, "up"))
        self.assertEqual(cross_type, "neutral")
        self.assertEqual(align_sc, 0)

    def test_alignment_score_range(self):
        cross_type, align_sc, gates, dv = self._classify(_prices(600, "up"))
        self.assertGreaterEqual(align_sc, 0)
        self.assertLessEqual(align_sc, 35)

    def test_gates_keys(self):
        cross_type, align_sc, gates, dv = self._classify(_prices(400, "flat"))
        for k in ("close_gt_200", "close_gt_50", "d100_gt_200", "d20_gt_50"):
            self.assertIn(k, gates)


class TestDetectCross(unittest.TestCase):
    def _cross_type(self, series):
        px = series.to_frame()
        dmas = D.compute_dmas(px)
        return D._detect_cross("TEST", series, dmas)

    def test_uptrend_is_not_death(self):
        t = self._cross_type(_prices(600, "up"))
        self.assertNotEqual(t, "death")

    def test_downtrend_is_not_platinum(self):
        t = self._cross_type(_prices(600, "down"))
        self.assertNotEqual(t, "platinum")

    def test_flat_returns_valid_type(self):
        t = self._cross_type(_prices(500, "flat"))
        self.assertIn(t, ("platinum","golden","silver","bronze","watch","neutral","bear","death"))


class TestBacktest(unittest.TestCase):
    def _bt(self, trend="up"):
        s = _prices(700, trend)
        px = s.to_frame()
        dmas = D.compute_dmas(px)
        return D.backtest_golden_cross("TEST", s, dmas)

    def test_returns_required_keys(self):
        bt = self._bt()
        for k in ("events", "win_rate_3m", "avg_ret_3m", "win_rate_6m", "avg_ret_6m"):
            self.assertIn(k, bt)

    def test_uptrend_events_nonnegative(self):
        bt = self._bt("up")
        self.assertGreaterEqual(bt["events"], 0)

    def test_win_rate_range(self):
        bt = self._bt("up")
        if bt["win_rate_3m"] is not None:
            self.assertGreaterEqual(bt["win_rate_3m"], 0)
            self.assertLessEqual(bt["win_rate_3m"], 100)

    def test_insufficient_data_returns_zero_events(self):
        s = _prices(100, "up")
        px = s.to_frame()
        dmas = D.compute_dmas(px)
        bt = D.backtest_golden_cross("TEST", s, dmas)
        self.assertEqual(bt["events"], 0)

    def test_bt_score_range(self):
        bt = self._bt()
        sc = D.bt_score(bt)
        self.assertGreaterEqual(sc, 0)
        self.assertLessEqual(sc, 20)

    def test_empty_bt_gives_neutral_score(self):
        bt = D._empty_bt()
        self.assertEqual(D.bt_score(bt), 10)


class TestScoreUniverse(unittest.TestCase):
    def _make_px(self):
        stocks = {"ALPHA": _prices(600, "up"), "BETA": _prices(600, "down"),
                  "GAMMA": _prices(400, "flat"), "DELTA": _prices(50, "up")}
        return pd.concat(stocks, axis=1)

    def test_returns_list(self):
        px = self._make_px()
        dmas = D.compute_dmas(px)
        rows = D.score_universe(px, dmas, {}, {})
        self.assertIsInstance(rows, list)

    def test_scores_in_range(self):
        px = self._make_px()
        dmas = D.compute_dmas(px)
        rows = D.score_universe(px, dmas, {}, {})
        for r in rows:
            self.assertGreaterEqual(r["total_score"], 0)
            self.assertLessEqual(r["total_score"], 100)

    def test_sorted_descending(self):
        px = self._make_px()
        dmas = D.compute_dmas(px)
        rows = D.score_universe(px, dmas, {}, {})
        scores = [r["total_score"] for r in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_uptrend_ranks_above_downtrend(self):
        px = self._make_px()
        dmas = D.compute_dmas(px)
        rows = D.score_universe(px, dmas, {}, {})
        syms = [r["symbol"] for r in rows]
        if "ALPHA" in syms and "BETA" in syms:
            self.assertLess(syms.index("ALPHA"), syms.index("BETA"))

    def test_required_keys_present(self):
        px = self._make_px()
        dmas = D.compute_dmas(px)
        rows = D.score_universe(px, dmas, {}, {})
        for r in rows:
            for k in ("symbol","total_score","crossover_type","close","dma200","above_200dma","rank"):
                self.assertIn(k, r)

    def test_short_stock_excluded(self):
        px = self._make_px()
        dmas = D.compute_dmas(px)
        rows = D.score_universe(px, dmas, {}, {})
        syms = {r["symbol"] for r in rows}
        # DELTA has only 50 days — should be excluded
        self.assertNotIn("DELTA", syms)


class TestBuildPortfolio(unittest.TestCase):
    def _scored(self):
        stocks = {f"S{i:02d}": _prices(600, "up", seed=i) for i in range(40)}
        px = pd.concat(stocks, axis=1)
        dmas = D.compute_dmas(px)
        return D.score_universe(px, dmas, {}, {})

    def test_returns_correct_structure(self):
        scored = self._scored()
        holdings, cash_pct, stock_pct = D.build_portfolio(scored, guard_on=False)
        self.assertIsInstance(holdings, list)
        self.assertAlmostEqual(cash_pct + stock_pct, 100.0)

    def test_max_holdings(self):
        scored = self._scored()
        holdings, _, _ = D.build_portfolio(scored, guard_on=False)
        self.assertLessEqual(len(holdings), D.HOLDINGS)

    def test_weights_sum_to_stock_pct(self):
        scored = self._scored()
        holdings, cash_pct, stock_pct = D.build_portfolio(scored, guard_on=False)
        total_w = sum(h["weight_pct"] for h in holdings)
        self.assertAlmostEqual(total_w, stock_pct, places=0)

    def test_guard_on_halves_stock_allocation(self):
        scored = self._scored()
        h_on, cash_on, stock_on = D.build_portfolio(scored, guard_on=True)
        h_off, cash_off, stock_off = D.build_portfolio(scored, guard_on=False)
        self.assertAlmostEqual(cash_on, 50.0)
        self.assertAlmostEqual(cash_off, 0.0)
        self.assertAlmostEqual(stock_on + stock_off, 150.0)

    def test_no_weight_exceeds_cap(self):
        scored = self._scored()
        holdings, _, stock_pct = D.build_portfolio(scored, guard_on=False)
        cap = D.MAX_WEIGHT * stock_pct  # e.g. 6% of 100% = 6%
        for h in holdings:
            self.assertLessEqual(h["weight_pct"], cap + 0.1)

    def test_shares_nonnegative(self):
        scored = self._scored()
        holdings, _, _ = D.build_portfolio(scored, guard_on=False)
        for h in holdings:
            self.assertGreaterEqual(h["shares"], 0)

    def test_alloc_within_budget(self):
        scored = self._scored()
        holdings, _, _ = D.build_portfolio(scored, guard_on=False)
        sip = 1_000_000
        total_alloc = sum(h["alloc_rs"] for h in holdings)
        self.assertLessEqual(total_alloc, sip + 100)


class TestLoadDivBonus(unittest.TestCase):
    """Smoke test that load_universe and load_prices handle missing data gracefully."""
    def test_load_prices_empty_symbols(self):
        px = D.load_prices([])
        self.assertTrue(px.empty)

    def test_get_nifty50_guard_returns_bool(self):
        result = D.get_nifty50_guard()
        self.assertIsInstance(result, bool)

    def test_load_hhhl_returns_dict(self):
        result = D.load_hhhl()
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main()
