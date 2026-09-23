import unittest
import numpy as np
import pandas as pd

from hhhl_scanner import classify, feature_frame, pivot_events, scan_stock, normalize_sessions
from indicator_research import indicators


class HHHLScannerTests(unittest.TestCase):
    def frame(self, n=140):
        rng = np.random.default_rng(61)
        close = 100 + np.cumsum(rng.normal(.08, 1.3, n))
        op = close + rng.normal(0, .2, n)
        return pd.DataFrame({
            "Open": op, "High": np.maximum(close, op)+1,
            "Low": np.minimum(close, op)-1, "Close": close, "Volume": 3e6,
        }, index=pd.bdate_range("2025-01-01", periods=n))

    def classify(self, **overrides):
        params = dict(
            fresh=True, enough=True, gaps=[], volume=1000,
            exit_condition=False, structure=True, breakout=True, above_high=True,
            market_ready=True, market_on=True, price=100, turnover=2e8, atr_pct=2,
        )
        return classify(**(params | overrides))[0]

    def test_buy_requires_complete_market_and_fresh_signal(self):
        self.assertEqual(self.classify(), "BUY")
        self.assertEqual(self.classify(market_ready=False), "CAUTION")
        self.assertEqual(self.classify(market_on=False), "CAUTION")
        self.assertEqual(self.classify(breakout=False), "CAUTION")
        self.assertEqual(self.classify(fresh=False), "CAUTION")

    def test_exit_is_not_hidden_by_entry_filters(self):
        self.assertEqual(self.classify(exit_condition=True, market_on=False, price=20), "SELL")

    def test_missing_data_cannot_become_actionable(self):
        self.assertEqual(self.classify(exit_condition=True, fresh=False), "CAUTION")
        self.assertEqual(self.classify(gaps=["2025-01-20"]), "CAUTION")
        self.assertEqual(self.classify(volume=0), "CAUTION")
        self.assertEqual(self.classify(enough=False), "CAUTION")

    def test_watch_avoid_and_screen_boundaries(self):
        self.assertEqual(self.classify(breakout=False, above_high=False), "WATCH")
        self.assertEqual(self.classify(breakout=False, structure=False), "AVOID")
        self.assertEqual(self.classify(turnover=1e8-1), "AVOID")
        self.assertEqual(self.classify(turnover=1e8), "BUY")
        self.assertEqual(self.classify(atr_pct=.49), "AVOID")
        self.assertEqual(self.classify(atr_pct=6.01), "AVOID")

    def test_holiday_placeholders_do_not_count_toward_confirmation(self):
        high = np.array([1, 2, 5, 5, 3, 2, 1], dtype=float)
        frame = pd.DataFrame({
            "Open": high-.25, "High": high, "Low": high-.5, "Close": high-.25,
            "Volume": [100, 100, 100, 0, 100, 100, 100],
        }, index=pd.bdate_range("2025-01-01", periods=7))
        calendar, normalized, removed = normalize_sessions({"A": frame, "B": frame}, minimum_symbols=2)
        self.assertNotIn(frame.index[3], calendar)
        self.assertEqual(removed, {"A": 1, "B": 1})
        event = pivot_events(normalized["A"])["high"][0]
        self.assertEqual(event["pivot_date"], str(frame.index[2].date()))
        self.assertEqual(event["confirmed_on"], str(frame.index[5].date()))

    def test_signal_definition_matches_shared_indicator_rules(self):
        frame = self.frame()
        short = feature_frame(frame)
        reference = indicators(frame)
        pd.testing.assert_series_equal(short.breakout, reference.in_hhhl, check_names=False)
        pd.testing.assert_series_equal(short.exit_condition, reference.out_hhhl, check_names=False)
        pd.testing.assert_series_equal(short.atr, reference.atr)

    def test_pivot_dates_distinguish_occurrence_from_confirmation(self):
        frame = pd.DataFrame({
            "High": [1, 2, 5, 3, 2, 1],
            "Low": [0, 1, 2, 1, 0, -1],
        }, index=pd.bdate_range("2025-01-01", periods=6))
        self.assertFalse(pivot_events(frame.iloc[:4])["high"])
        event = pivot_events(frame.iloc[:5])["high"][0]
        self.assertEqual(event["pivot_date"], str(frame.index[2].date()))
        self.assertEqual(event["confirmed_on"], str(frame.index[4].date()))
        self.assertEqual(event["price"], 5)

    def scan(self, frame, as_of, calendar=None):
        return scan_stock(
            {"Symbol": "TEST", "Company Name": "Test", "Industry": "Other"},
            frame, [], as_of,
            {"data_ready": True, "reference_filter_passed": True},
            frame.index if calendar is None else calendar,
        )

    def test_future_prices_cannot_change_the_dated_scan(self):
        frame = self.frame()
        cutoff = str(frame.index[119].date())
        expected = self.scan(frame.iloc[:120], cutoff)
        altered = frame.copy()
        altered.loc[altered.index[120:], ["Open", "High", "Low", "Close"]] *= 100
        actual = self.scan(altered, cutoff)
        self.assertEqual(actual, expected)
        self.assertTrue(all(p["confirmed_on"] <= cutoff for group in actual["pivots"].values() for p in group))

    def test_stale_stock_is_retained_with_no_price_zones(self):
        frame = self.frame()
        as_of = str((frame.index[-1] + pd.offsets.BDay()).date())
        row = self.scan(frame, as_of)
        self.assertEqual(row["symbol"], "TEST")
        self.assertEqual(row["status"], "CAUTION")
        self.assertFalse(row["complete_for_session"])
        self.assertEqual(row["zones"], {})
        self.assertIsNone(row["entry_plan"])

    def test_gap_in_recent_sessions_withholds_zones(self):
        frame = self.frame()
        row = self.scan(frame.drop(frame.index[-4]), str(frame.index[-1].date()), frame.index)
        self.assertEqual(row["status"], "CAUTION")
        self.assertEqual(row["zones"], {})
        self.assertTrue(any("Missing recent session" in x for x in row["data_warnings"]))

    def test_incomplete_history_retains_unknown_stock(self):
        frame = self.frame(10)
        row = self.scan(frame, str(frame.index[-1].date()))
        self.assertEqual(row["status"], "CAUTION")
        self.assertIsNone(row["entry_plan"])
        self.assertEqual(row["zones"], {})

    def test_chart_swings_keep_full_history_labels_and_confirmation_dates(self):
        frame = self.frame()
        row = self.scan(frame, str(frame.index[-1].date()))
        self.assertGreater(len(row["chart_swings"]), 4)
        all_pivots = pivot_events(frame)
        for event in row["chart_swings"]:
            group = all_pivots[event["kind"]]
            index = next(i for i,p in enumerate(group) if p["pivot_date"] == event["pivot_date"])
            self.assertLessEqual(event["confirmed_on"], row["data_date"])
            self.assertGreaterEqual(event["pivot_date"], row["chart"][0]["date"])
            if index:
                previous = group[index-1]["price"]
                expected = ("HH" if event["price"] > previous else "LH") if event["kind"] == "high" else ("HL" if event["price"] > previous else "LL")
                if event["price"] != previous:
                    self.assertEqual(event["label"], expected)


if __name__ == "__main__":
    unittest.main()
