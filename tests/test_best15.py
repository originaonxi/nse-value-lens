"""Nifty best setup (EMA 21 / EMA 105, 15-minute, always in): next-open fills, always in after the first signal,
flip level maths, P&L adds up, and a consistent published payload."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import nifty_best15 as B  # noqa: E402


def synthetic(days=60, seed=5):
    rng = np.random.default_rng(seed)
    idx = []
    for d in pd.bdate_range("2025-01-01", periods=days):
        idx += list(pd.date_range(d + pd.Timedelta(hours=9, minutes=15), periods=25, freq="15min"))
    c = 20000 * np.exp(np.cumsum(rng.normal(0, 0.0015, len(idx))))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"Open": o, "High": np.maximum(o, c) * 1.0004, "Low": np.minimum(o, c) * 0.9996, "Close": c}, index=pd.DatetimeIndex(idx))


class Mechanics(unittest.TestCase):
    def test_flip_price_puts_ema21_on_ema105(self):
        ef, es = 25000.0, 24500.0
        p = B.flip_price(ef, es)
        a, b = 2 / 22, 2 / 106
        self.assertAlmostEqual(a * p + (1 - a) * ef, b * p + (1 - b) * es, places=6)

    def test_replay_always_in_next_open(self):
        df = synthetic()
        start = 200
        trades, eq, ef, es, up = B.replay(df, start)
        self.assertGreater(len(trades), 3)
        t = list(df.index.strftime("%Y-%m-%d %H:%M"))
        o = df["Open"].to_numpy()
        for a, b in zip(trades, trades[1:]):
            self.assertNotEqual(a["side"], b["side"])                 # always flips, never flat
            self.assertEqual(a["exit_time"], b["entry_time"])         # exit and new entry on the same open
        for x in trades:
            i = t.index(x["entry_time"])
            self.assertEqual(t[i - 1], x["signal_time"])
            self.assertAlmostEqual(x["entry"], round(o[i], 2), places=2)
            self.assertEqual(up[i - 1], x["side"] == "BUY")
        closed = [x for x in trades if not x["open"]]
        op = trades[-1]["net_pts"] if trades[-1]["open"] else 0.0
        self.assertAlmostEqual(eq[-1], sum(x["net_pts"] for x in closed) + op, delta=0.05 * len(trades) + 0.5)


class Published(unittest.TestCase):
    def test_payload(self):
        p = ROOT / "docs" / "best15.json"
        if not p.exists():
            self.skipTest("best15.json not generated")
        d = json.loads(p.read_text(encoding="utf-8"))
        s, tr = d["summary"], d["trades"]
        closed = [x for x in tr if not x["open"]]
        self.assertEqual(s["trades"], len(closed))
        self.assertAlmostEqual(s["realised_pts"], sum(x["net_pts"] for x in closed), delta=1)
        self.assertAlmostEqual(s["total_pts"], s["realised_pts"] + s["open_pts"], delta=1)
        self.assertAlmostEqual(sum(y["pts"] for y in d["years_mtm"]), s["total_pts"], delta=1)
        self.assertAlmostEqual(s["total_rs_10"], s["total_pts"] * d["lot"] * d["lots"], delta=0.05 * d["lot"] * d["lots"] + 1)   # points published to 0.1
        self.assertEqual(len(d["chart"]["bars"]), len(d["chart"]["ema21"]))
        self.assertEqual(d["chart"]["bars"][-1][0], d["last_candle"])
        self.assertEqual(s["buy"]["trades"] + s["sell"]["trades"], s["trades"])
        self.assertLessEqual(sum(x["open"] for x in tr), 1)
        self.assertEqual(d["now"]["side"] == "BUY", d["now"]["ema21"] > d["now"]["ema105"])


if __name__ == "__main__":
    unittest.main()
