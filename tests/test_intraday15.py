"""Tests for intraday15.py: no overnight positions, fills at the next open, stops, costs and rupee maths."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import intraday15 as I  # noqa: E402

DOCS = ROOT / "docs"


def frame(days=4, seed=3):
    """Synthetic 15-minute candles: 25 a day, 09:15 to 15:15."""
    rng = np.random.default_rng(seed)
    idx = []
    for d in pd.bdate_range("2026-01-05", periods=days):
        idx += list(pd.date_range(d + pd.Timedelta(hours=9, minutes=15), periods=25, freq="15min"))
    n = len(idx)
    c = 25000 + np.cumsum(rng.normal(0, 20, n))
    o = np.r_[c[0], c[:-1]] + rng.normal(0, 3, n)
    df = pd.DataFrame({"Open": o, "High": np.maximum(o, c) + 5, "Low": np.minimum(o, c) - 5, "Close": c}, index=pd.DatetimeIndex(idx))
    return df


R = {"sig": ("px", 3), "side": "both", "filt": "none", "start": "09:30", "flat": "15:15", "sl": None, "tp": None}


class Mechanics(unittest.TestCase):
    def setUp(self):
        self.df = frame()
        self.X = I.features(self.df)

    def test_never_overnight(self):
        s, e, side, g, ep = I.trades_vec(self.X, I.desired(self.X, R))
        did = self.X["did"]
        self.assertTrue(len(s) > 0)
        for a, b in zip(s, e):
            self.assertEqual(did[a], did[b], "trade held across days")
            self.assertLessEqual(self.X["hhmm"][b], 1515)

    def test_decision_at_close_fill_next_open(self):
        p = I.desired(self.X, R)
        sig = np.sign(self.X["C"] - self.X["ema"][3])
        k = int(np.flatnonzero(p != 0)[0])
        self.assertEqual(p[k], sig[k - 1])                         # held during k, decided at the close of k-1
        s, e, side, g, ep = I.trades_vec(self.X, p)
        self.assertAlmostEqual(ep[0], self.X["O"][s[0]])
        self.assertTrue(np.allclose(g, side * (self.X["O"][e] - self.X["O"][s])))

    def test_no_trade_before_start_or_in_first_candle(self):
        p = I.desired(self.X, dict(R, start="10:30"))
        self.assertFalse(np.any(p[self.X["hhmm"] < 1030]))
        self.assertFalse(np.any(p[self.X["newday"]]))

    def test_sell_only_never_buys(self):
        s, e, side, g, ep = I.simulate(self.X, dict(R, side="sell", sl=1.0))
        self.assertTrue(np.all(side < 0))

    def test_stop_caps_the_loss_at_the_level_when_no_gap(self):
        s, e, side, g, ep = I.simulate(self.X, dict(R, sl=0.5))
        atr = self.X["atr"]
        for a, b, sd, gr in zip(s, e, side, g):
            if b > a and gr < 0:
                o = self.X["O"][b]
                gap_loss = sd * (o - self.X["O"][a])
                self.assertGreaterEqual(gr, min(-0.5 * atr[a - 1] - 1e-6, gap_loss - 1e-6))

    def test_cost_and_stats(self):
        tr = (np.array([1, 5]), np.array([3, 7]), np.array([1.0, -1.0]), np.array([10.0, -4.0]), np.array([25000.0, 25000.0]))
        X = {"did": np.zeros(10, int)}
        st = I.stats(X, tr, 0)
        self.assertEqual(st["n"], 2)
        self.assertAlmostEqual(st["net"], round(10 - 4 - 2 * I.COST_RT * 25000, 1))
        self.assertEqual(st["buy"], round(10 - I.COST_RT * 25000, 1))

    def test_money_whole_lots_no_leverage(self):
        tr = I.simulate(self.X, R)
        lots = {d: 65 for d in self.X["days"]}
        rows, sm = I.money(self.X, tr, 0, lots, capital=1_00_00_000)
        self.assertGreater(len(rows), 0)
        for r in rows:
            self.assertLessEqual(r["lots"] * r["lot"] * r["in"], 1_00_00_000 + sm["made"] + 1)
        self.assertEqual(sm["made"] + sm["lost"], sum(r["pnl"] for r in rows))
        self.assertAlmostEqual(sm["profit"], sum(r["pnl"] for r in rows), delta=len(rows))


class Published(unittest.TestCase):
    def test_payload(self):
        p = DOCS / "intraday.json"
        if not p.exists():
            self.skipTest("intraday.json not built")
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertGreaterEqual(d["data"]["sessions"], 400)
        self.assertGreater(d["rules_tried"], 1000)
        for pf in d["portfolios"]:
            self.assertEqual(pf["start"], 1_00_00_000)
            self.assertAlmostEqual(pf["made"] + pf["lost"], pf["profit"], delta=pf["trades"] + 2)
            self.assertEqual(pf["end"] - pf["start"], pf["profit"])
        w = d["portfolios"][0]
        self.assertEqual(len(d["trades"]), w["trades"])
        self.assertTrue(d["next"]["lines"])


if __name__ == "__main__":
    unittest.main()
