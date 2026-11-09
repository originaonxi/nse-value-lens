"""Stock formula lab: next-open fills, long and short P&L with costs, split adjustment, and a consistent payload."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import stock_data as SD  # noqa: E402
import stock_lab as L  # noqa: E402


def frame(close):
    c = np.asarray(close, float)
    o = np.r_[c[0], c[:-1]]
    idx = pd.date_range("2025-01-01 09:15", periods=len(c), freq="h")
    return pd.DataFrame({"Open": o, "High": np.maximum(o, c) + 1, "Low": np.minimum(o, c) - 1, "Close": c}, index=idx)


class Book(unittest.TestCase):
    def test_long_fills_next_open_with_cost(self):
        df = frame([100, 101, 102, 103, 104, 103, 102])
        want = np.array([0, 1, 1, 1, 0, 0, 0], bool)            # signal at close of candle 1, exit signal at close of 4
        tr = L.book(df, want, 1, 0, lot=10)
        self.assertEqual(len(tr), 1)
        t = tr[0]
        o = df["Open"].to_numpy()
        self.assertEqual(t["in"], str(df.index[2])[:16])
        self.assertEqual(t["out"], str(df.index[5])[:16])
        self.assertAlmostEqual(t["pts"], (o[5] - o[2]) - L.COST * (o[2] + o[5]), places=2)
        self.assertEqual(t["rs"], round(t["pts"] * 10))

    def test_short_profits_when_price_falls(self):
        df = frame([100, 99, 97, 95, 93, 94, 96])
        tr = L.book(df, np.array([0, 1, 1, 1, 0, 0, 0], bool), -1, 0, lot=1)
        self.assertEqual(tr[0]["side"], "SELL")
        self.assertGreater(tr[0]["pts"], 0)

    def test_open_trade_marked_at_last_close(self):
        df = frame([100, 101, 102, 103])
        tr = L.book(df, np.array([0, 1, 1, 1], bool), 1, 0, lot=1)
        self.assertTrue(tr[-1]["open"])
        self.assertEqual(tr[-1]["exit"], 103.0)

    def test_warmup_blocks_early_trades(self):
        df = frame([100, 101, 102, 103, 104, 105])
        tr = L.book(df, np.ones(6, bool), 1, 3, lot=1)
        self.assertEqual(tr[0]["in"], str(df.index[4])[:16])

    def test_formulas_are_directions(self):
        df = frame(100 + np.cumsum(np.random.default_rng(1).normal(0, 1, 400)))
        F = L.formulas(df)
        self.assertGreaterEqual(len(F), 30)
        for k, (d, w) in F.items():
            self.assertEqual(len(d), len(df), k)
            self.assertTrue(set(np.unique(d)) <= {-1.0, 0.0, 1.0}, k)


class Splits(unittest.TestCase):
    def test_split_divides_earlier_candles(self):
        idx = pd.date_range("2025-01-01 09:15", periods=6, freq="D")
        raw = pd.DataFrame({"Open": [200, 202, 204, 100, 101, 102.0], "High": [201, 203, 205, 101, 102, 103.0],
                            "Low": [199, 201, 203, 99, 100, 101.0], "Close": [200, 202, 204, 100, 101, 102.0], "Volume": [1.0] * 6}, index=idx)
        ref = pd.Series([100, 101, 102, 100, 101, 102.0], index=idx.normalize())
        adj, ev = SD.adjust(raw, ref)
        self.assertEqual(len(ev), 1)
        self.assertAlmostEqual(adj["Close"].iloc[0], 100.0, places=6)
        self.assertAlmostEqual(adj["Close"].iloc[-1], 102.0, places=6)


class Published(unittest.TestCase):
    def test_payload(self):
        p = ROOT / "docs" / "stock_lab.json"
        if not p.exists():
            self.skipTest("stock_lab.json not generated")
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(len(d["universe"]), len(d["stocks"]))
        self.assertGreaterEqual(len(d["stocks"]), 25)
        for side in ("buy", "sell"):
            self.assertEqual(len(d["table"][side]), len(d["formulas"]))
            best = max(d["table"][side], key=lambda r: r["train"]["pct"])["formula"]
            self.assertEqual(best, d["pick"][side])               # the pick uses the first half only
        for s in d["stocks"]:
            self.assertEqual(s["total_rs"], s["buy"]["rs"] + s["sell"]["rs"])
            self.assertGreaterEqual(s["trades"], 100, s["symbol"])
            q = ROOT / "docs" / "stocklab" / f"{s['symbol']}.json"
            self.assertTrue(q.exists(), s["symbol"])
        self.assertLess(d["from"], d["split"])


if __name__ == "__main__":
    unittest.main()
