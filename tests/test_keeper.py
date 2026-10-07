import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import keeper as k  # noqa: E402

HOLIDAYS = {"2026-10-02", "2026-10-20"}
IST = k.IST
LABELS = [p[0] for p in k.PAGES]


def at(day, hh, mm=0):
    return datetime(2026, 10, day, hh, mm, tzinfo=IST)


def view(now, target, current=(), eq=True, fo=True, **over):
    """All pages show `target` except labels not in `current` (which show the day before)."""
    t, old = target.isoformat(), (target - timedelta(days=1)).isoformat()
    current = set(LABELS) if current == "all" else set(current)
    live = {label: (t if label in current else old) for label in LABELS}
    v = dict(now=now, target=target, eq=eq, fo=fo, live=live, master={}, live_official=eq, master_official=eq,
             active={}, attempts={}, last_dispatch={}, last_done={}, publishing=False, stuck_runs=[],
             stale_since={}, global_stale=False, pretend=set())
    v.update(over)
    return v


def dispatched(result):
    return [a[1] for a in result["actions"] if a[0] == "dispatch"]


class CalendarTests(unittest.TestCase):
    def test_target_session(self):
        self.assertEqual(k.target_session(at(7, 16, 10), HOLIDAYS), date(2026, 10, 7))   # after the close
        self.assertEqual(k.target_session(at(7, 15, 0), HOLIDAYS), date(2026, 10, 6))    # market still open
        self.assertEqual(k.target_session(at(8, 8, 0), HOLIDAYS), date(2026, 10, 7))     # next morning
        self.assertEqual(k.target_session(at(10, 12, 0), HOLIDAYS), date(2026, 10, 9))   # Saturday -> Friday
        self.assertEqual(k.target_session(at(12, 9, 0), HOLIDAYS), date(2026, 10, 9))    # Monday before close
        self.assertEqual(k.target_session(at(20, 18, 0), HOLIDAYS), date(2026, 10, 19))  # holiday
        self.assertEqual(k.target_session(at(3, 11, 0), HOLIDAYS), date(2026, 10, 1))    # Sat after Fri holiday

    def test_next_ready_skips_weekends_and_holidays(self):
        self.assertEqual(k.next_ready(at(7, 9, 0), HOLIDAYS), at(7, 16, 5))
        self.assertEqual(k.next_ready(at(9, 17, 0), HOLIDAYS), at(12, 16, 5))
        self.assertEqual(k.next_ready(at(19, 17, 0), HOLIDAYS), at(21, 16, 5))


class PlanTests(unittest.TestCase):
    T = date(2026, 10, 7)

    def test_everything_current_is_done(self):
        r = k.plan(view(at(7, 22), self.T, "all"))
        self.assertEqual(r["actions"], [])
        self.assertTrue(r["done"])

    def test_stale_pages_dispatch_their_workflows(self):
        r = k.plan(view(at(7, 22), self.T, ()))
        self.assertIn("hhhl", dispatched(r))
        self.assertIn("options", dispatched(r))
        self.assertFalse(r["done"])

    def test_shared_queue_starts_one_workflow_at_a_time(self):
        r = k.plan(view(at(7, 22), self.T, ()))
        self.assertEqual(len([w for w in dispatched(r) if w in ("hhhl", "sr", "swing")]), 1)
        busy = k.plan(view(at(7, 22), self.T, (), active={"hhhl": True}))
        self.assertFalse(set(dispatched(busy)) & {"hhhl", "sr", "swing"})
        self.assertTrue(any("shared refresh queue" in n for n in busy["notes"]))

    def test_options_waits_for_fo_file_and_sr_for_equity_file(self):
        r = k.plan(view(at(7, 18), self.T, set(LABELS) - {"Options desk", "Daily S&R", "Momentum30"}, eq=False, fo=False))
        self.assertNotIn("options", dispatched(r))
        self.assertNotIn("sr", dispatched(r))
        late = k.plan(view(at(7, 21, 45), self.T, set(LABELS) - {"Daily S&R", "Momentum30"}, eq=False, fo=False))
        self.assertIn("sr", dispatched(late))                     # yfinance fallback after 21:30 IST

    def test_hhhl_reruns_once_official_file_is_out(self):
        r = k.plan(view(at(7, 21), self.T, "all", live_official=False, master_official=False))
        self.assertIn("hhhl", dispatched(r))

    def test_attempt_cap_and_spacing(self):
        capped = k.plan(view(at(7, 22), self.T, set(LABELS) - {"Options desk"}, attempts={"options": 3}))
        self.assertNotIn("options", dispatched(capped))
        self.assertTrue(capped["gaps"])
        recent = k.plan(view(at(7, 22), self.T, set(LABELS) - {"Options desk"},
                             last_dispatch={"options": at(7, 21, 40)}))
        self.assertNotIn("options", dispatched(recent))

    def test_unpublished_data_is_republished_after_grace(self):
        stale_live = view(at(7, 22), self.T, set(LABELS) - {"Swing desk"}, master={"Swing desk": "2026-10-07"},
                          stale_since={"Swing desk": at(7, 21, 55)})
        self.assertNotIn("pages", dispatched(k.plan(stale_live)))
        stale_live["stale_since"] = {"Swing desk": at(7, 21, 40)}
        self.assertIn("pages", dispatched(k.plan(stale_live)))

    def test_stuck_publish_is_cancelled_and_pages_redeployed(self):
        v = view(at(7, 22), self.T, set(LABELS) - {"HH/HL"}, master={"HH/HL": "2026-10-07"},
                 publishing=True, stuck_runs=[123], stale_since={"HH/HL": at(7, 21, 58)})
        r = k.plan(v)
        self.assertIn(("cancel", 123, "publish job stuck waiting for GitHub Pages"), r["actions"])
        self.assertIn("pages", dispatched(r))

    def test_fno_and_market_wait_for_hhhl(self):
        v = view(at(7, 22), self.T, set(LABELS) - {"F&O stocks", "Deals & breadth", "HH/HL"}, active={"hhhl": True})
        r = k.plan(v)
        self.assertNotIn("fno", dispatched(r))
        self.assertNotIn("market", dispatched(r))

    def test_pretend_forces_a_dispatch(self):
        r = k.plan(view(at(7, 22), self.T, "all", pretend={"swing"}))
        self.assertEqual(dispatched(r), ["swing"])

    def test_waits_for_official_files_but_gives_up_next_morning(self):
        self.assertFalse(k.plan(view(at(7, 18), self.T, "all", eq=False, fo=False))["done"])
        morning = k.plan(view(at(8, 9, 30), self.T, "all", eq=False, fo=False))
        self.assertTrue(morning["done"])
        self.assertTrue(morning["gaps"])


if __name__ == "__main__":
    unittest.main()
