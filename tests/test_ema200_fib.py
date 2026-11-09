"""EMA 200 desk: TradingView EMA seed, Fibonacci grids, double-fib zones, signals use closes up to the candle only,
fills at the next open, and a consistent published payload."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ema200_fib as E  # noqa: E402


class Maths(unittest.TestCase):
    def test_ema_seed(self):
        x = np.arange(1, 301, dtype=float)
        e = E.ema(x)
        self.assertTrue(np.isnan(e[198]))
        self.assertAlmostEqual(e[199], x[:200].mean())
        self.assertAlmostEqual(e[200], (2 / 201) * x[200] + (199 / 201) * e[199])

    def test_grid_direction_and_levels(self):
        h = np.array([10, 12, 20, 18, 15], float)
        l = np.array([8, 9, 16, 14, 11], float)
        g = E.grid(h, l, 4, 5)
        self.assertEqual((g["high"], g["low"]), (20.0, 8.0))
        self.assertTrue(g["up"])                               # low (bar 0) came before the high (bar 2)
        self.assertAlmostEqual(g["levels"][0.618], 20 - 0.618 * 12)

    def test_double_zone_needs_two_grids_and_skips_shared_extremes(self):
        big = {"levels": {0.0: 100.0, 0.382: 80.0, 0.618: 70.0, 1.0: 50.0}}
        small = {"levels": {0.0: 100.0, 0.5: 80.2, 1.0: 60.0}}
        zs = E.double_zones(big, small, 90.0, e200=80.1)
        self.assertEqual(len(zs), 1)                            # 100/100 shared high is ignored
        self.assertAlmostEqual(zs[0]["lo"], 80.0)
        self.assertAlmostEqual(zs[0]["hi"], 80.2)
        self.assertTrue(zs[0]["ema200"])

    def test_cross_signal_uses_only_closed_candles(self):
        n = 420
        c = np.r_[np.full(300, 100.0), np.linspace(100, 130, 60), np.linspace(130, 80, 60)]
        o, h, l = c.copy(), c + 1, c - 1
        e, a = E.ema(c), E.atr(h, l, c)
        s = E.signals(o, h, l, c, e, a, "cross", 0)
        ups, dns = np.flatnonzero(s > 0), np.flatnonzero(s < 0)
        self.assertTrue(len(ups) and len(dns))
        for i in ups:
            self.assertTrue(c[i] > e[i] and not c[i - 1] > e[i - 1])
        for i in dns:
            self.assertTrue(c[i] < e[i] and c[i - 1] > e[i - 1])
        c2 = c.copy(); c2[-1] = 500.0                           # changing the future does not change earlier signals
        s2 = E.signals(o, h, l, c2, E.ema(c2), E.atr(h, l, c2), "cross", 0)
        self.assertTrue(np.array_equal(s[:-1], s2[:-1]))

    def test_simulate_next_open_and_always_in(self):
        t = pd.date_range("2026-01-01", periods=6)
        o = np.array([100, 101, 102, 103, 104, 105], float)
        c = o + 0.5
        sig = np.array([1, 0, -1, 0, 0, 0], float)
        tr, pnl = E.simulate(o, c, t, sig, 0, lambda px: 10, 0.0, True)
        self.assertEqual(tr[0]["side"], "BUY")
        self.assertEqual(tr[0]["entry"], 101.0)                 # BUY signal at close 0 -> open 1
        self.assertEqual(tr[0]["exit"], 103.0)                  # SELL signal at close 2 -> open 3
        self.assertEqual(tr[1]["side"], "SELL")
        self.assertTrue(tr[1]["open"])
        self.assertAlmostEqual(pnl.sum(), sum(x["rs"] for x in tr), delta=1)

    def test_long_only_goes_flat_on_sell(self):
        t = pd.date_range("2026-01-01", periods=5)
        o = np.array([100, 101, 102, 103, 104], float)
        tr, _ = E.simulate(o, o, t, np.array([1, 0, -1, 0, 0], float), 0, lambda px: 1, 0.0, False)
        self.assertEqual([x["side"] for x in tr], ["BUY"])


class Published(unittest.TestCase):
    def test_payload(self):
        p = ROOT / "docs" / "ema200.json"
        if not p.exists():
            self.skipTest("ema200.json not generated")
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(sum(d["counts"].values()), len(d["rows"]))
        self.assertGreaterEqual(len(d["rows"]), 150)
        self.assertEqual(d["window"]["sessions"], 200)
        best = max(d["stocks"]["rows"], key=lambda r: r["stats"]["h1"])["label"]
        self.assertEqual(best, d["stocks"]["pick"])
        self.assertEqual(max(d["nifty"]["rows"], key=lambda r: r["stats"]["h1"])["label"], d["nifty"]["pick"])
        for r in d["stocks"]["rows"] + d["nifty"]["rows"]:
            s = r["stats"]
            self.assertLessEqual(abs(s["h1"] + s["h2"] - s["total"]), 2)
        for r in d["rows"]:
            x = r["dist_atr"]                                     # published to 2 decimals
            self.assertTrue({"ABOVE": x >= 0.495, "ON": abs(x) <= 0.505, "BELOW": x <= -0.495}[r["zone"]], (r["symbol"], r["zone"], x))
            self.assertTrue((ROOT / "docs" / "ema200" / f"{r['symbol']}.json").exists())
        self.assertTrue((ROOT / "docs" / "ema200" / "NIFTY.json").exists())


if __name__ == "__main__":
    unittest.main()
