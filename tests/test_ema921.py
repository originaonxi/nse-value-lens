"""EMA 9/21 1-hour page: Pine-identical EMA, 09:15-anchored hourly candles, next-open fills, buy only,
P&L adds up, and the published payload is consistent."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ema921 as E  # noqa: E402


def synthetic(days=60, seed=3):
    rng = np.random.default_rng(seed)
    idx = []
    for d in pd.bdate_range("2025-01-01", periods=days):
        idx += list(pd.date_range(d + pd.Timedelta(hours=9, minutes=15), periods=25, freq="15min"))
    c = 20000 * np.exp(np.cumsum(rng.normal(0, 0.002, len(idx))))
    o = np.r_[c[0], c[:-1]]
    h, l = np.maximum(o, c) * 1.0005, np.minimum(o, c) * 0.9995
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c}, index=pd.DatetimeIndex(idx))


class Mechanics(unittest.TestCase):
    def test_pine_ema_seed_and_recursion(self):
        x = np.arange(1, 31, dtype=float)
        e = E.pine_ema(x, 9)
        self.assertTrue(np.isnan(e[7]))
        self.assertAlmostEqual(e[8], x[:9].mean())
        self.assertAlmostEqual(e[9], 0.2 * x[9] + 0.8 * e[8])

    def test_hourly_anchored_at_0915_never_across_days(self):
        h = E.hourly(synthetic(3))
        self.assertEqual([str(t.time())[:5] for t in h.index[:7]], ["09:15", "10:15", "11:15", "12:15", "13:15", "14:15", "15:15"])
        self.assertEqual(list(h["bars"][:7]), [4, 4, 4, 4, 4, 4, 1])

    def test_exit_price_puts_ema9_on_ema21(self):
        ef, es = 25000.0, 24700.0
        p = E.exit_price(ef, es)
        a, b = 2 / 10, 2 / 22
        self.assertAlmostEqual(a * p + (1 - a) * ef, b * p + (1 - b) * es, places=6)

    def test_replay_fills_next_open_buy_only_and_adds_up(self):
        h = E.hourly(synthetic(80))
        lots = {str(d): 65 for d in sorted(set(h.index.date))}
        trades, eq_pts, eq_rs, ef, es, bull, _ = E.replay(h, lots, 30)
        self.assertTrue(trades)
        t = list(h.index.strftime("%Y-%m-%d %H:%M"))
        o = h["Open"].to_numpy()
        for x in trades:
            i = t.index(x["entry_time"])
            self.assertEqual(t[i - 1], x["signal_time"])                 # signal on the previous close
            self.assertTrue(bull[i - 1])
            self.assertAlmostEqual(x["entry"], round(o[i], 2), places=2)  # filled at this candle's open
            if not x["open"]:
                j = t.index(x["exit_time"])
                self.assertFalse(bull[j - 1])
                self.assertAlmostEqual(x["exit"], round(o[j], 2), places=2)
                self.assertAlmostEqual(x["net_pts"], x["gross_pts"] - x["cost_pts"], places=1)
        closed = [x for x in trades if not x["open"]]
        for a, b in zip(trades, trades[1:]):                             # never two positions at once
            self.assertLessEqual(a["exit_time"], b["entry_time"])
        op = trades[-1]["rupees"] if trades[-1]["open"] else 0
        self.assertAlmostEqual(eq_rs[-1], sum(x["rupees"] for x in closed) + op, delta=len(trades) + 2)


class Published(unittest.TestCase):
    def test_payload(self):
        p = ROOT / "docs" / "ema921.json"
        if not p.exists():
            self.skipTest("ema921.json not generated")
        d = json.loads(p.read_text(encoding="utf-8"))
        s, tr = d["summary"], d["trades"]
        closed = [x for x in tr if not x["open"]]
        self.assertEqual(s["trades"], len(closed))
        self.assertEqual(s["realised_rs"], sum(x["rupees"] for x in closed))
        self.assertEqual(s["total_rs"], s["realised_rs"] + s["open_rs"])
        self.assertEqual(sum(y["trades"] for y in d["years"]), s["trades"])
        self.assertEqual(sum(m["rupees"] for m in d["months"]), s["realised_rs"])
        self.assertLessEqual(sum(x["open"] for x in tr), 1)
        self.assertEqual(len(d["chart"]["bars"]), len(d["chart"]["ema9"]))
        self.assertEqual(d["chart"]["bars"][-1][0], d["last_candle"])
        self.assertGreaterEqual(d["from"], str((pd.Timestamp(d["as_of"]) - pd.Timedelta(days=731)).date()))
        self.assertTrue(all(x["entry_time"] >= d["from"] for x in tr))


if __name__ == "__main__":
    unittest.main()
