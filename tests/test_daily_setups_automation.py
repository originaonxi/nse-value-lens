"""No-network publication gates: date, Jev coverage and source consistency."""
import copy
import unittest
from pathlib import Path

from scripts.verify_daily_setups import validate_inputs, validate_snapshot


class PublicationGate(unittest.TestCase):
    def setUp(self):
        self.day = "2026-10-27"
        self.scan = {"as_of": self.day, "rows": [
            {"symbol": f"S{i}", "data_date": self.day, "close": 100.0} for i in range(200)]}
        self.jev = {"as_of": self.day, "judged": 200, "of_universe": 200,
                    "ranking": [{"symbol": r["symbol"], "composite": 0.5} for r in self.scan["rows"]]}

    def test_current_complete_jev_passes(self):
        self.assertEqual(validate_inputs(self.scan, self.jev, True), self.day)

    def test_missing_stale_partial_or_wrong_universe_block_publication(self):
        for change in ("missing", "stale", "partial", "duplicate", "wrong_symbol", "invalid_score", "stale_row"):
            with self.subTest(change=change):
                j = copy.deepcopy(self.jev)
                if change == "missing":
                    j = {}
                elif change == "stale":
                    j["as_of"] = "2026-10-26"
                elif change == "partial":
                    j["ranking"].pop()
                    j["judged"] = 199
                elif change == "duplicate":
                    j["ranking"][0] = j["ranking"][1]
                elif change == "wrong_symbol":
                    j["ranking"][0]["symbol"] = "OTHER"
                elif change == "invalid_score":
                    j["ranking"][0]["composite"] = None
                else:
                    j["ranking"][0]["data_date"] = "2026-10-26"
                with self.assertRaises(AssertionError):
                    validate_inputs(self.scan, j, True)
    def test_incomplete_or_duplicate_hhhl_universe_is_rejected(self):
        for rows in (self.scan["rows"][:150], self.scan["rows"][:199],
                     self.scan["rows"] + [self.scan["rows"][0]]):
            with self.subTest(count=len(rows)):
                with self.assertRaisesRegex(AssertionError, "exactly 200"):
                    validate_inputs({"as_of": self.day, "rows": rows}, self.jev, True)


    def snapshot(self):
        stocks = [{**r, "category": "data_check", "rank": None, "plan": None,
                   "jev": {}} for r in self.scan["rows"]]
        data = {"as_of": self.day, "generated_at": self.day + "T15:00:00Z", "universe_count": 200,
                "inputs": {"hhhl_scan": self.day, "hhhl_fno": self.day, "jev_rank": self.day},
                "stocks": stocks, "ranking": {"lists": {k: {"count": 0, "jev_count": 0,
                    "chart_order": [], "jev_order": [], "combined_order": []} for k in ("buy", "sell", "watch")}}}
        return data, {"as_of": self.day, "rows": []}, {"as_of": self.day, "series": {}}

    def test_output_preserves_prices_dates_and_source_universe(self):
        data, fno, series = self.snapshot()
        validate_snapshot(data, self.scan, fno, self.jev, series, True)
        for change in ("close", "data_date", "as_of", "duplicate", "stale_jev", "source_changed"):
            with self.subTest(change=change):
                d, f, s = copy.deepcopy((data, fno, series))
                if change == "close":
                    d["stocks"][0]["close"] = 101.0
                elif change == "data_date":
                    d["stocks"][0]["data_date"] = "2026-10-26"
                elif change == "as_of":
                    s["as_of"] = "2026-10-26"
                elif change == "duplicate":
                    d["stocks"][0] = d["stocks"][1]
                elif change == "stale_jev":
                    d["stocks"][0]["jev"] = {"composite": 0.9}
                else:
                    f["as_of"] = "2026-10-26"
                with self.assertRaises(AssertionError):
                    validate_snapshot(d, self.scan, f, self.jev, s, True)

    def test_stale_price_cannot_have_plan_or_rank(self):
        data, fno, series = self.snapshot()
        self.scan["rows"][0]["data_date"] = "2026-10-26"
        data["stocks"][0]["data_date"] = "2026-10-26"
        validate_snapshot(data, self.scan, fno, self.jev, series, True)
        data["stocks"][0]["plan"] = {"entry": 100}
        with self.assertRaisesRegex(AssertionError, "stale price ranked"):
            validate_snapshot(data, self.scan, fno, self.jev, series, True)

    def test_workflow_dependencies_and_strict_gate_including_retry(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/daily_setups.yml").read_text(encoding="utf-8")
        for name in ("HHHL daily refresh", "F&O stock coverage refresh", "Daily S&R Refresh", "Options desk refresh"):
            self.assertIn(name, workflow)
        self.assertEqual(workflow.count("python scripts/verify_daily_setups.py --inputs-only --require-jev"), 2)
        self.assertEqual(workflow.count("python scripts/verify_daily_setups.py --require-jev"), 2)
        self.assertIn("--timeout 180 --require-jev", workflow)
        sr = (root / ".github/workflows/daily_sr.yml").read_text(encoding="utf-8")
        self.assertIn('[ "$JEV_READY" = "true" ]', sr)
        self.assertIn("python scripts/verify_daily_setups.py --inputs-only --require-jev", sr)
        self.assertIn("group: market-data-refresh", workflow)
        self.assertIn("ref: ${{ needs.refresh.outputs.commit }}", workflow.split("  verify:")[1])


if __name__ == "__main__":
    unittest.main()
