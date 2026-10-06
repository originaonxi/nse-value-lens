import math
import unittest

import numpy as np
import pandas as pd

import options_desk as od


class PricingTests(unittest.TestCase):
    def test_implied_vol_round_trip(self):
        s, k, t = np.array([100.0, 100.0, 2500.0]), np.array([100.0, 95.0, 2600.0]), np.array([0.05, 0.1, 0.06])
        call = np.array([1.0, 0.0, 1.0])
        sigma = np.array([0.2, 0.35, 0.28])
        price = od.bs_price(s, k, t, sigma, call)
        iv = od.implied_vol(price, s, k, t, call)
        np.testing.assert_allclose(iv, sigma, atol=1e-4)

    def test_implied_vol_rejects_impossible_prices(self):
        # Below intrinsic value and zero price have no implied volatility.
        iv = od.implied_vol(np.array([1.0, 0.0]), np.array([120.0, 100.0]), np.array([100.0, 100.0]),
                            np.array([0.1, 0.1]), np.array([1.0, 1.0]))
        self.assertTrue(np.isnan(iv).all())

    def test_costs_are_positive_and_stt_only_on_sells(self):
        buy = float(od.leg_costs(np.array(100.0), np.array("BUY"), np.array("stock")))
        sell = float(od.leg_costs(np.array(100.0), np.array("SELL"), np.array("stock")))
        self.assertGreater(buy, 1.5)            # 1.5% stock slippage dominates
        self.assertAlmostEqual(sell - buy, 100 * (od.STT_SELL - od.STAMP_BUY), places=6)
        tiny = float(od.leg_costs(np.array(0.5), np.array("BUY"), np.array("index")))
        self.assertGreaterEqual(tiny, od.TICK)  # never cheaper than one tick


def features(symbol="ABC", n=40, spot=None, foi=None):
    days = pd.bdate_range("2026-01-01", periods=n).strftime("%Y-%m-%d").tolist()
    spot = spot if spot is not None else [100 + i for i in range(n)]
    foi = foi if foi is not None else [1000 + 10 * i for i in range(n)]
    f = pd.DataFrame(dict(date=days, symbol=symbol, kind="stock", spot=spot, foi=foi, lot=100, pcr=0.8,
                          atm=100.0, atm_ce=5.0, atm_pe=5.0, atm_iv=30.0, dte=20, texp="2026-12-31"))
    return f, days


class NoLookaheadTests(unittest.TestCase):
    def test_trailing_features_use_only_past_sessions(self):
        f, days = features()
        d = od.derive(f, days)
        row = d[d.date == days[10]].iloc[0]
        self.assertAlmostEqual(row.ret5, 110 / 105 - 1)
        self.assertAlmostEqual(row.foi5, 1100 / 1050 - 1)
        # Changing a future price must not change today's features.
        f2 = f.copy()
        f2.loc[f2.date == days[11], "spot"] = 1e6
        d2 = od.derive(f2, days)
        a, b = d[d.date == days[10]].iloc[0], d2[d2.date == days[10]].iloc[0]
        for col in ("ret5", "foi5", "sig5", "z5", "iv_pct"):
            self.assertTrue((pd.isna(a[col]) and pd.isna(b[col])) or a[col] == b[col], col)

    def test_gap_in_history_blocks_lagged_values(self):
        f, days = features()
        f = f[f.date != days[7]]               # the stock was missing on one session
        d = od.derive(f, days)
        self.assertTrue(pd.isna(d[d.date == days[10]].iloc[0].ret5))

    def test_corporate_action_jump_invalidates_signal(self):
        spot = [100.0] * 30 + [50.0] * 10       # 50% one-day jump = split/bonus, not a signal
        f, days = features(spot=spot)
        d = od.derive(f, days)
        self.assertFalse(bool(d[d.date == days[31]].iloc[0].valid))


class TradeTests(unittest.TestCase):
    def test_non_overlapping_and_entry_next_session(self):
        days = [f"2026-01-{i:02d}" for i in range(1, 21)]
        sig = pd.DataFrame(dict(rule="r", symbol="ABC", sidx=[0, 2, 5, 6], date=[days[i] for i in (0, 2, 5, 6)]))
        out = od.non_overlapping(sig, days)
        self.assertEqual(out.sidx.tolist(), [0, 5])
        self.assertEqual(out.entry_date.tolist(), [days[1], days[6]])
        self.assertEqual(out.exit_date.tolist(), [days[5], days[10]])

    def test_simulated_buy_and_sell_returns_include_costs(self):
        days = ["2026-01-01", "2026-01-02", "2026-01-09"]
        base = dict(sidx=0, date=days[0], symbol="ABC", kind="stock", spot=100.0, lot=100, texp="2026-01-29",
                    entry_date=days[1], exit_date=days[2], nlegs=1, l0_opt="CE", l0_strike=100.0, l0_ref=5.0)
        sig = pd.DataFrame([dict(base, rule="buy", l0_side="BUY"), dict(base, rule="sell", l0_side="SELL")])
        prices = pd.DataFrame([
            dict(date=days[1], symbol="ABC", exp="2026-01-29", strike=100.0, opt="CE", mark=5.2, fill_open=5.0),
            dict(date=days[2], symbol="ABC", exp="2026-01-29", strike=100.0, opt="CE", mark=7.0, fill_open=6.9),
        ]).set_index(["date", "symbol", "exp", "strike", "opt"])
        t = od.simulate(sig, prices, days).set_index("rule")
        gross = (7.0 - 5.0) * 100
        self.assertLess(t.loc["buy", "pnl_per_lot"], gross)
        self.assertLess(t.loc["sell", "pnl_per_lot"], -gross)
        self.assertEqual(t.loc["buy", "basis"], "premium")
        self.assertEqual(t.loc["sell", "basis"], "margin")
        self.assertAlmostEqual(t.loc["buy", "return_pct"], 100 * t.loc["buy", "pnl_per_lot"] / (5.0 * 100))
        self.assertAlmostEqual(t.loc["sell", "return_pct"], 100 * t.loc["sell", "pnl_per_lot"] / (0.20 * 100 * 100))

    def test_untraded_entry_contract_is_skipped(self):
        days = ["2026-01-01", "2026-01-02", "2026-01-09"]
        sig = pd.DataFrame([dict(rule="r", sidx=0, date=days[0], symbol="ABC", kind="stock", spot=100.0, lot=100,
                                 texp="2026-01-29", entry_date=days[1], exit_date=days[2], nlegs=1, l0_opt="CE",
                                 l0_strike=100.0, l0_side="BUY", l0_ref=5.0)])
        prices = pd.DataFrame([
            dict(date=days[1], symbol="ABC", exp="2026-01-29", strike=100.0, opt="CE", mark=5.0, fill_open=np.nan),
            dict(date=days[2], symbol="ABC", exp="2026-01-29", strike=100.0, opt="CE", mark=6.0, fill_open=6.0),
        ]).set_index(["date", "symbol", "exp", "strike", "opt"])
        self.assertTrue(od.simulate(sig, prices, days).empty)


class ClassificationTests(unittest.TestCase):
    def stats(self, trades=100, mean=2.0, t=3.0, first=1.0, second=1.0):
        half = lambda m: dict(trades=trades // 2, mean_return_pct=m, win_rate=55)
        return dict(trades=trades, mean_return_pct=mean, t_stat=t, first_half=half(first), second_half=half(second))

    def test_validated_needs_every_test(self):
        self.assertEqual(od.classify(self.stats(), baseline_mean=0.5), "VALIDATED")
        self.assertEqual(od.classify(self.stats(t=1.5), baseline_mean=0.5), "WEAK")
        self.assertEqual(od.classify(self.stats(second=-0.1), baseline_mean=0.5), "WEAK")
        self.assertEqual(od.classify(self.stats(), baseline_mean=2.5), "WEAK")
        self.assertEqual(od.classify(self.stats(trades=50), baseline_mean=0.5), "WEAK")
        self.assertEqual(od.classify(self.stats(mean=-0.2), baseline_mean=-1), "NO_EDGE")
        self.assertEqual(od.classify(self.stats(trades=20)), "INSUFFICIENT")
        self.assertEqual(od.classify(None), "INSUFFICIENT")

    def test_rule_set_is_fixed_and_has_baselines(self):
        ids = [r["id"] for r in od.RULES]
        self.assertEqual(len(ids), len(set(ids)))
        for rule in od.RULES:
            self.assertIn(od.BASELINE_FOR[rule["action"]], ids)
            self.assertIn(rule["action"], od.BUCKET_OF)

    def test_buildup_labels(self):
        self.assertEqual(od.buildup(1, 1), "Long build-up")
        self.assertEqual(od.buildup(-1, 1), "Short build-up")
        self.assertEqual(od.buildup(1, -1), "Short covering")
        self.assertEqual(od.buildup(-1, -1), "Long unwinding")
        self.assertEqual(od.buildup(None, 1), "n/a")

    def test_clean_removes_non_finite_numbers(self):
        out = od.clean({"a": float("nan"), "b": [np.float64(1.5), np.int64(2), math.inf]})
        self.assertEqual(out, {"a": None, "b": [1.5, 2, None]})


def tipsheet_bundles(score=35.2):
    stat = lambda latest: {"as_of": "2026-09-30", "latest": latest, "value_ago": {"1m": latest * 0.9, "1y": latest * 1.1},
                           "history": {"start": "2009-04-29", "percentile_full_history": 61.0}}
    bands = [["Fear", 25.0, 45.0, 63, 1305, 62, 2.16, -4.8, 8.5, 57.2, -5.2, 0, 0, 0, 0, 0, 0, False, False],
             ["Neutral", 45.0, 55.0, 63, 702, 57, 2.38, -4.3, 8.1, 57.3, -3.6, 0, 0, 0, 0, 0, 0, True, False],
             ["All sessions", None, None, 63, 4819, 77, 3.71, -2.9, 9.5, 64.7, -3.8, None, None, None, None, None, None, None, None]]
    cols = ["band", "lo", "hi", "horizon", "sessions", "independent", "median_pct", "p25_pct", "p75_pct", "hit_rate_pct",
            "median_worst_pct", "median_lo90_pct", "median_hi90_pct", "hit_lo90_pct", "hit_hi90_pct",
            "diff_vs_all_lo90_pp", "diff_vs_all_hi90_pp", "inside_noise", "too_few"]
    return {
        # tipsheet nests the score fields under meta; the parser must find them there.
        "fg_now": {"as_of": "2026-10-06", "meta": {"score": score, "rank": 29.0, "week_ago": 31.9, "month_ago": 58.5, "year_ago": 48.2},
                   "columns": ["key", "label", "raw", "pctile", "contribution", "from"],
                   "rows": [["momentum", "Momentum", -2.9, 22.8, -4.5, "2001-11-05"]]},
        "fg_next": {"columns": cols, "rows": bands},
        "fg_tests": {"tests": {"FG-H1": {"result": "fail"}, "FG-H4a": {"result": "pass"}}},
        "pcr_index_options": stat(0.98), "options_premium_to_cash": stat(0.45),
        "options_share_of_premium_pct": stat(30.7), "index_opt_premium_adt": stat(44858.0),
        "daily": {"dates": ["2026-09-30", "2026-10-01"], "series": {"pcr_index_options": [1.0, 1.01], "pcr_stock_options": [0.57, 0.63],
                                                                  "options_premium_to_cash": [0.36, float("nan")]}},
        "events": {"as_of": "2026-10-06", "columns": ["d", "kind", "symbol", "name", "detail", "rank", "sme"], "rows": [
            ["2026-10-07", "rbi", None, "RBI policy decision", "Decision day", None, False],
            ["2026-10-08", "results", "TCS", "Tata Consultancy Services", "Results, dividend", 10.0, False],
            ["2026-10-08", "results", "TINYSME", "Not an F&O stock", "Results", None, True],
            ["2026-10-20", "results", "INFY", "Infosys", "Results", 5.0, False],      # outside the window
            ["2026-10-09", "agm", "INFY", "Infosys", "AGM", 5.0, False]]},
    }


class TipsheetTests(unittest.TestCase):
    def test_parses_score_band_froth_and_window_events(self):
        ctx, per = od.parse_tipsheet("2026-10-06T18:05:19Z", tipsheet_bundles(), ("2026-10-07", "2026-10-13"), ["TCS", "INFY", "NIFTY"])
        fg = ctx["fear_greed"]
        self.assertEqual((fg["score"], fg["band"], fg["week_ago"]), (35.2, "Fear", 31.9))
        self.assertEqual(fg["next_63"]["band_median_pct"], 2.16)
        self.assertEqual(fg["next_63"]["all_median_pct"], 3.71)
        self.assertEqual((fg["tests_passed"], fg["tests_total"]), (1, 2))
        self.assertEqual([f["latest"] for f in ctx["froth"]], [0.98, 0.45, 30.7, 44858.0])
        self.assertEqual(ctx["daily_pcr"]["premium_to_cash"], [0.36, None])     # NaN never reaches the page
        self.assertEqual([e["kind"] for e in ctx["events"]["market"]], ["rbi"])
        self.assertEqual(set(per), {"TCS", "INFY"})                             # non-F&O and out-of-window events dropped
        self.assertEqual([e["kind"] for e in per["INFY"]], ["agm"])
        self.assertEqual(ctx["events"]["results_in_window"], 1)

    def test_score_outside_bands_gives_no_band(self):
        ctx, _ = od.parse_tipsheet(None, tipsheet_bundles(score=90.0), ("2026-10-07", "2026-10-13"), [])
        self.assertIsNone(ctx["fear_greed"]["band"])
        self.assertIsNone(ctx["fear_greed"]["next_63"]["band_median_pct"])

    def test_unreachable_tipsheet_fails_safe(self):
        def boom():
            raise od.TipsheetError("URLError: offline")
        original = od.fetch_tipsheet
        od.fetch_tipsheet = boom
        try:
            ctx, per = od.tipsheet_context(("2026-10-07", "2026-10-13"), ["TCS"], log=lambda *_: None)
        finally:
            od.fetch_tipsheet = original
        self.assertEqual(ctx["state"], "failed")
        self.assertEqual(per, {})

    def test_refresh_context_rewrites_only_when_tipsheet_changes(self):
        import tempfile
        from pathlib import Path
        current = {"as_of": "2026-10-06", "rows": [{"symbol": "TCS", "events": []}],
                   "context": {"state": "ok", "updated_at": "2026-10-06T18:05:19Z"}}
        bundles = tipsheet_bundles()
        original_fetch, original_out = od.fetch_tipsheet, od.OUT
        with tempfile.TemporaryDirectory() as tmp:
            od.OUT = Path(tmp) / "options_desk.json"
            try:
                od.fetch_tipsheet = lambda: ("2026-10-06T18:05:19Z", bundles)
                same = od.refresh_context(dict(current), log=lambda *_: None)
                self.assertFalse(od.OUT.exists())                               # unchanged: nothing written
                self.assertEqual(same["rows"][0]["events"], [])
                od.fetch_tipsheet = lambda: ("2026-10-07T18:05:00Z", bundles)
                new = od.refresh_context(dict(current), log=lambda *_: None)
                self.assertTrue(od.OUT.exists())
                self.assertEqual(new["context"]["updated_at"], "2026-10-07T18:05:00Z")
                self.assertTrue(new["context"]["refreshed_after_jev"])
            finally:
                od.fetch_tipsheet, od.OUT = original_fetch, original_out



if __name__ == "__main__":
    unittest.main()
