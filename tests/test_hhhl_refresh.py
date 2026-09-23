import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import numpy as np
import pandas as pd

import hhhl_refresh as refresh


class RefreshTests(unittest.TestCase):
    def frame(self, close=100, day="2026-09-23"):
        return pd.DataFrame({"Open":[close], "High":[close+2], "Low":[close-2],
                             "Close":[close], "Volume":[1000]}, index=pd.to_datetime([day]), dtype=float)

    def test_before_and_after_1600_ist_cutoff(self):
        self.assertEqual(str(refresh.cutoff_date(datetime(2026,9,23,10,29,tzinfo=timezone.utc))), "2026-09-22")
        self.assertEqual(str(refresh.cutoff_date(datetime(2026,9,23,10,30,tzinfo=timezone.utc))), "2026-09-23")
        self.assertEqual(str(refresh.cutoff_date(datetime(2026,9,23,23,0,tzinfo=timezone.utc))), "2026-09-23")

    def test_weekend_holiday_and_future_year_have_no_fixed_expiry(self):
        self.assertEqual(refresh.expected_session(datetime(2026,9,27).date()), "2026-09-25")
        self.assertEqual(refresh.expected_session(datetime(2026,9,23).date(), ["2026-09-23"]), "2026-09-22")
        self.assertTrue(refresh.expected_session(datetime(2126,9,23).date()).startswith("2126"))

    def test_invalid_or_unclosed_candle_excluded(self):
        a = self.frame()
        b = self.frame(day="2026-09-24")
        c = self.frame(day="2026-09-22")
        c.loc[:, "High"] = 90
        d = self.frame(day="2026-09-21")
        d.loc[:, "Close"] = np.nan
        got = refresh.valid_frame(pd.concat([a,b,c,d]), "2026-09-23")
        self.assertEqual(len(got), 1)
        self.assertEqual(str(got.index[0].date()), "2026-09-23")

    def test_adjustment_change_detected_before_merging(self):
        self.assertTrue(refresh.history_changed(self.frame(100), self.frame(50)))
        self.assertFalse(refresh.history_changed(self.frame(100), self.frame(100)))

    def test_vendor_failure_preserves_history_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"TEST.NS.csv"
            self.frame().to_csv(path)
            before = path.read_bytes()
            with patch.object(refresh, "PRICES", Path(tmp)), patch.object(refresh.yf, "Ticker") as ticker, patch.object(refresh.time, "sleep"):
                ticker.return_value.history.side_effect = RuntimeError("vendor offline")
                result = refresh.fetch_one("TEST.NS", "2026-09-23")
            self.assertEqual(before, path.read_bytes())
            self.assertEqual(result["latest"], "2026-09-23")
            self.assertIsNone(result["fetched_through"])
            self.assertIn("vendor offline", result["error"])

    def test_partial_latest_does_not_destroy_complete_cached_candle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"TEST.NS.csv"
            self.frame().to_csv(path)
            latest = self.frame()
            latest.loc[:, "Close"] = np.nan
            recent = pd.concat([self.frame(day="2026-09-22"), latest])
            with patch.object(refresh, "PRICES", Path(tmp)), patch.object(refresh.yf, "Ticker") as ticker:
                ticker.return_value.history.return_value = recent
                result = refresh.fetch_one("TEST.NS", "2026-09-23")
            self.assertEqual(result["fetched_through"], "2026-09-22")
            self.assertEqual(result["latest"], "2026-09-23")
            self.assertEqual(pd.read_csv(path).iloc[-1].Close, 100)

    def test_corporate_action_replaces_entire_old_scale(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.frame(100).to_csv(Path(tmp)/"TEST.NS.csv")
            with patch.object(refresh, "PRICES", Path(tmp)), patch.object(refresh.yf, "Ticker") as ticker:
                ticker.return_value.history.side_effect = [self.frame(50), self.frame(50)]
                result = refresh.fetch_one("TEST.NS", "2026-09-23")
            self.assertIsNone(result["error"])
            self.assertEqual(pd.read_csv(Path(tmp)/"TEST.NS.csv").iloc[-1].Close, 50)
            self.assertEqual(ticker.return_value.history.call_args.kwargs["period"], "5y")

    def test_missing_universe_member_rejected(self):
        universe = pd.read_csv(refresh.UNIVERSE)
        refresh.validate_universe(universe)
        with self.assertRaises(ValueError):
            refresh.validate_universe(universe.iloc[:199])
        broken = universe.copy()
        broken.loc[1,"Symbol"] = broken.loc[0,"Symbol"]
        with self.assertRaises(ValueError):
            refresh.validate_universe(broken)

    def test_fresh_label_requires_all_checks(self):
        scan = {"as_of":"2026-09-23","complete_count":200,"market":{"data_ready":True}}
        self.assertEqual(refresh.choose_state(scan,"2026-09-23",True,200),"fresh")
        self.assertEqual(refresh.choose_state(scan,"2026-09-23",False,200),"partial")
        self.assertEqual(refresh.choose_state(scan,"2026-09-23",True,199),"partial")
        self.assertEqual(refresh.choose_state(scan,"2026-09-24",True,200),"waiting")

    def test_refresh_failure_publishes_status_not_a_fabricated_scan(self):
        with patch.dict(refresh.os.environ, {"GITHUB_STEP_SUMMARY": ""}), patch("builtins.print"), patch.object(refresh, "holidays_for", return_value=([],False)), patch.object(refresh, "refresh_universe", side_effect=RuntimeError("offline")), patch.object(refresh, "publish") as publish:
            result = refresh.run(datetime(2026,9,23,12,tzinfo=timezone.utc))
        self.assertEqual(result["state"], "failed")
        self.assertEqual(publish.call_count, 1)
        self.assertEqual(publish.call_args.args[0], "hhhl_refresh_status")

    def test_official_bar_requires_matching_scale_and_no_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"TEST.NS.csv"
            self.frame(100, "2026-09-22").to_csv(path)
            row={"PREV_CLOSE":100,"OPEN_PRICE":101,"HIGH_PRICE":104,"LOW_PRICE":99,"CLOSE_PRICE":103,"TTL_TRD_QNTY":500}
            with patch.object(refresh,"PRICES",Path(tmp)):
                before=path.read_bytes()
                self.assertFalse(refresh.apply_official_bar("TEST",row,"2026-09-23",{"TEST"})[0])
                self.assertEqual(path.read_bytes(),before)
                self.assertFalse(refresh.apply_official_bar("TEST",row|{"PREV_CLOSE":50},"2026-09-23",set())[0])
                self.assertEqual(path.read_bytes(),before)
                self.assertTrue(refresh.apply_official_bar("TEST",row,"2026-09-23",set())[0])
                self.assertEqual(pd.read_csv(path).iloc[-1].Close,103)


if __name__ == "__main__":
    unittest.main()
