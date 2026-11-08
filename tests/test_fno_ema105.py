"""Tests for fno_ema105.py - 2-hour candles, the EMA 105 setup per stock, published payload."""
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fno_ema105 as E  # noqa: E402
import nifty_ema as N   # noqa: E402


def hourly(days=420, start=100.0, drift=0.0008, seed=1):
    rng = np.random.default_rng(seed)
    idx = []
    for d in pd.bdate_range("2024-06-03", periods=days):
        idx += [pd.Timestamp(d.date()).tz_localize(N.IST) + pd.Timedelta(hours=9, minutes=15) + pd.Timedelta(hours=k) for k in range(7)]
    idx = pd.DatetimeIndex(idx)
    r = drift + rng.normal(0, 0.004, len(idx))
    c = start * np.exp(np.cumsum(r))
    o = np.r_[start, c[:-1]]
    h = np.maximum(o, c) * 1.002
    lo = np.minimum(o, c) * 0.998
    return pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c}, index=idx)


class TestTwoHour(unittest.TestCase):
    def test_groups_two_hours_inside_one_day(self):
        h = hourly(days=3)
        g = E.two_hour(h, datetime(2026, 1, 1, tzinfo=N.IST))
        self.assertEqual(len(g), 12)                      # 7 hourly bars -> 4 two-hour bars a day
        self.assertEqual(len(set(g.index.date)), 3)
        first = h.iloc[:2]
        self.assertAlmostEqual(g["Open"].iloc[0], first["Open"].iloc[0])
        self.assertAlmostEqual(g["High"].iloc[0], first["High"].max())
        self.assertAlmostEqual(g["Close"].iloc[0], first["Close"].iloc[-1])

    def test_drops_unfinished_candle_during_market_hours(self):
        h = hourly(days=2)
        day = h.index[-1].date()
        now = pd.Timestamp(day).tz_localize(N.IST) + pd.Timedelta(hours=11, minutes=30)
        g = E.two_hour(h[h.index < now], now.to_pydatetime())
        self.assertTrue(all(t + pd.Timedelta(hours=2) <= now for t in g.index if t.date() == day))


class TestEvaluate(unittest.TestCase):
    def test_setup_on_a_rising_stock(self):
        h = hourly(days=420, drift=0.0012)
        g = E.two_hour(h, datetime(2027, 1, 1, tzinfo=N.IST))
        daily = h["Close"].groupby(h.index.date).last()
        daily.index = pd.to_datetime(daily.index)
        res, X = E.evaluate(g, pd.DataFrame({"Close": daily}))
        self.assertIsNotNone(res)
        self.assertIn(res["state"], E.STATE_ORDER)
        self.assertEqual(len(res["chart"]["t"]), len(res["chart"]["c"]))
        self.assertEqual(len(res["chart"]["e"]), len(res["chart"]["c"]))
        self.assertEqual(res["all"]["n"], len(res["trades"]))
        # every trade is long, entered on a 2h close above EMA 105
        for t in res["trades"]:
            i = list(g.index.strftime("%Y-%m-%d %H:%M")).index(t[0])
            self.assertGreater(X["c"][i], X["ema"][i])
        self.assertEqual(len(res["checks"]), 4)

    def test_too_short_history_returns_none(self):
        h = hourly(days=30)
        g = E.two_hour(h, datetime(2027, 1, 1, tzinfo=N.IST))
        res, _ = E.evaluate(g, pd.DataFrame({"Close": h["Close"].groupby(h.index.date).last()}))
        self.assertIsNone(res)


class TestPublished(unittest.TestCase):
    def setUp(self):
        p = Path(__file__).resolve().parents[1] / "docs" / "fno_ema105.json"
        if not p.exists():
            self.skipTest("fno_ema105.json not generated")
        self.d = json.loads(p.read_text(encoding="utf-8"))

    def test_covers_the_fno_list(self):
        self.assertGreaterEqual(self.d["covered"], 200)
        self.assertEqual(self.d["covered"] + len(self.d["failures"]), self.d["universe"])
        self.assertEqual(len({r["symbol"] for r in self.d["rows"]}), self.d["covered"])

    def test_counts_and_stats_match_rows(self):
        rows = self.d["rows"]
        for k, v in self.d["counts"].items():
            self.assertEqual(v, sum(1 for r in rows if r["state"] == k))
        self.assertEqual(self.d["summary"]["trades"], sum(len(r["trades"]) for r in rows))
        for r in rows[:25]:
            net = sum(t[4] for t in r["trades"])
            self.assertAlmostEqual(net, r["all"]["net"], delta=0.05 * max(1, len(r["trades"])))

    def test_setup_is_exact(self):
        self.assertEqual(self.d["setup"], "EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 68")


if __name__ == "__main__":
    unittest.main()
