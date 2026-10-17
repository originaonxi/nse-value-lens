"""Exit-horizon maths and Jev priority-fingerprint safety for the Nifty chain desk.

Synthetic data only: no bhavcopy cache, no network, and no generated files are touched
(the archive test redirects nc.HIST to a throwaway temporary directory)."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

import nifty_chain as nc
import options_desk as od

BULL_CALL = [dict(option_type="CE", strike=23000.0, side="BUY", ref_close=250.0),
             dict(option_type="CE", strike=23300.0, side="SELL", ref_close=120.0)]
SPOT, LOT, SIGMA, DTE = 23000.0, 75, 0.14, 20


class ExitHorizonTests(unittest.TestCase):
    def test_five_trading_sessions_span_seven_calendar_days(self):
        # The plan holds HOLD trading sessions; exit_by is HOLD sessions ahead, which is ~7
        # calendar days -- the span the diffusion horizon must use, not HOLD days.
        for day in ("2026-01-05", "2026-01-09"):           # a Monday and a Friday, no holidays
            nxt = od.next_sessions(day, nc.HOLD, set())
            self.assertEqual(len(nxt), nc.HOLD)
            horizon = (dt.date.fromisoformat(nxt[-1]) - dt.date.fromisoformat(day)).days
            self.assertEqual(horizon, 7, f"{nc.HOLD} sessions from {day} should be 7 calendar days, got {horizon}")

    def test_profile_uses_calendar_horizon_not_session_count(self):
        p = nc.exit_payoff_profile(BULL_CALL, SPOT, LOT, SIGMA, DTE, nc.HOLD, horizon_days=7)
        self.assertEqual(p["horizon_calendar_days"], 7)
        self.assertEqual(p["hold_sessions"], nc.HOLD)
        self.assertEqual(p["remaining_dte"], DTE - 7)              # option life left at exit, calendar days
        self.assertEqual(p["model"]["horizon_source"], "plan_exit_by_calendar_days")
        self.assertFalse(p["model"]["exit_at_or_after_expiry"])
        self.assertTrue(np.isfinite(p["exp_pnl_per_lot"]))
        self.assertTrue(np.isfinite(p["p_profit"]))

    def test_calendar_horizon_differs_from_the_biased_session_horizon(self):
        # The real exit (7 calendar days) and the old buggy horizon (5 "days" == HOLD sessions)
        # leave different option life, so the expected exit P&L genuinely differs.
        true_days = nc.exit_payoff_profile(BULL_CALL, SPOT, LOT, SIGMA, DTE, nc.HOLD, horizon_days=7)
        biased = nc.exit_payoff_profile(BULL_CALL, SPOT, LOT, SIGMA, DTE, nc.HOLD, horizon_days=5)
        self.assertEqual(true_days["remaining_dte"], DTE - 7)
        self.assertEqual(biased["remaining_dte"], DTE - 5)
        self.assertNotEqual(true_days["exp_pnl_per_lot"], biased["exp_pnl_per_lot"])

    def test_legacy_caller_falls_back_to_sessions_as_days(self):
        legacy = nc.exit_payoff_profile(BULL_CALL, SPOT, LOT, SIGMA, DTE)        # no horizon_days
        self.assertEqual(legacy["horizon_calendar_days"], nc.HOLD)              # old, biased behaviour preserved
        self.assertEqual(legacy["hold_sessions"], nc.HOLD)
        self.assertEqual(legacy["remaining_dte"], DTE - nc.HOLD)
        self.assertEqual(legacy["model"]["horizon_source"], "legacy_sessions_as_days")
        self.assertTrue(np.isfinite(legacy["exp_pnl_per_lot"]))

    def test_rejects_negative_zero_nan_and_non_numeric_horizons(self):
        for bad in (-1, 0, float("nan"), float("inf"), "seven"):
            with self.assertRaises(ValueError):
                nc.exit_payoff_profile(BULL_CALL, SPOT, LOT, SIGMA, DTE, nc.HOLD, horizon_days=bad)

    def test_rejects_horizon_shorter_than_sessions_held(self):
        # Calendar days to exit can never be fewer than the number of trading sessions held.
        with self.assertRaises(ValueError):
            nc.exit_payoff_profile(BULL_CALL, SPOT, LOT, SIGMA, DTE, nc.HOLD, horizon_days=nc.HOLD - 1)

    def test_never_prices_a_leg_past_expiry(self):
        p = nc.exit_payoff_profile(BULL_CALL, SPOT, LOT, SIGMA, 6, nc.HOLD, horizon_days=10)   # exit after expiry
        self.assertEqual(p["remaining_dte"], 0)
        self.assertEqual(p["horizon_calendar_days"], 6)                # clamped to dte, never beyond expiry
        self.assertTrue(p["model"]["exit_at_or_after_expiry"])
        self.assertTrue(np.isfinite(p["exp_pnl_per_lot"]))

    def test_invalid_sigma_or_dte_returns_none(self):
        self.assertIsNone(nc.exit_payoff_profile(BULL_CALL, SPOT, LOT, float("nan"), DTE, nc.HOLD, horizon_days=7))
        self.assertIsNone(nc.exit_payoff_profile(BULL_CALL, SPOT, LOT, SIGMA, 0, nc.HOLD, horizon_days=7))


class JevFingerprintTests(unittest.TestCase):
    def test_fingerprint_is_stable_and_order_sensitive(self):
        rs1 = [dict(id="base_buy_call"), dict(id="base_bull_call_spread")]
        rs2 = [dict(id="base_bull_call_spread"), dict(id="base_buy_call")]
        self.assertEqual(nc._setup_fingerprint(rs1), nc._setup_fingerprint(rs1))
        self.assertNotEqual(nc._setup_fingerprint(rs1), nc._setup_fingerprint(rs2))   # order matters
        self.assertNotEqual(nc._setup_fingerprint(rs1),
                            nc._setup_fingerprint(rs1 + [dict(id="base_short_straddle")]))  # membership matters
        self.assertTrue(nc._setup_fingerprint(rs1).startswith(nc.VERSION + "|"))
        self.assertTrue(nc._setup_fingerprint([]).startswith(nc.VERSION + "|exit-calendar-v2|"))
        self.assertNotEqual(nc._setup_fingerprint([dict(id="a", expected_exit_pnl=10)]),
                            nc._setup_fingerprint([dict(id="a", expected_exit_pnl=20)]))

    def test_archive_stores_fingerprint_and_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            orig = nc.HIST
            nc.HIST = Path(tmp)
            try:
                fp = nc._setup_fingerprint([dict(id="base_buy_call")])
                rec = nc.archive("2026-01-05", dict(state="ok", model="m"),
                                 {"prio_0": {"choice": "top", "confidence": 0.9}},
                                 [], [dict(rule="base_buy_call")], setup_fingerprint=fp)
                self.assertEqual(rec["setup_fingerprint"], fp)
                on_disk = json.loads((Path(tmp) / "2026-01-05.json").read_text(encoding="utf-8"))
                self.assertEqual(on_disk["setup_fingerprint"], fp)                 # non-destructive, persisted
            finally:
                nc.HIST = orig

    def test_reused_priorities_only_trusted_on_fingerprint_match(self):
        # Mirrors the fail-closed gate in build(): archived per-setup priorities are reattached
        # only when the stored fingerprint equals today's; a changed setup set or a legacy
        # archive with no fingerprint is suppressed rather than silently remapped.
        today_fp = nc._setup_fingerprint([dict(id="a"), dict(id="b")])
        matching = {"setup_fingerprint": today_fp}
        changed = {"setup_fingerprint": nc._setup_fingerprint([dict(id="a"), dict(id="c")])}
        legacy = {}                                                   # old archive, no fingerprint field
        self.assertTrue(matching.get("setup_fingerprint") == today_fp)
        self.assertFalse(changed.get("setup_fingerprint") == today_fp)
        self.assertFalse(legacy.get("setup_fingerprint") == today_fp)


if __name__ == "__main__":
    unittest.main()
