"""5 methods daily race: replay mechanics on synthetic candles, a real (non-degenerate) Supertrend,
and a consistent published payload: plus + minus + open = net, the race ends on the leaderboard
numbers, and the page is wired."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import methods5 as M  # noqa: E402


def synthetic(days=40, seed=11):
    rng = np.random.default_rng(seed)
    idx = []
    for d in pd.bdate_range("2025-02-03", periods=days):
        idx += list(pd.date_range(d + pd.Timedelta(hours=9, minutes=15), periods=25, freq="15min"))
    c = 22000 * np.exp(np.cumsum(rng.normal(0, 0.002, len(idx))))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"Open": o, "High": np.maximum(o, c) * 1.0005, "Low": np.minimum(o, c) * 0.9995, "Close": c},
                        index=pd.DatetimeIndex(idx))


class Mechanics(unittest.TestCase):
    def test_replay_always_in_next_open_and_pnl_split(self):
        df = synthetic()
        up, valid = M.sig_psma100(df)
        trades, day = M.replay(df, up, valid)
        self.assertGreater(len(trades), 5)
        o = df["Open"].to_numpy()
        tmap = {str(x)[:16]: i for i, x in enumerate(df.index)}
        for a, b in zip(trades, trades[1:]):
            self.assertNotEqual(a["side"], b["side"])
            self.assertEqual(a["exit_time"] or b["entry_time"], b["entry_time"])
        for x in trades:
            self.assertAlmostEqual(x["entry"], round(o[tmap[x["entry_time"]]], 2), places=2)
        closed = [x for x in trades if not x["open"]]
        op = trades[-1]["net_pts"] if trades[-1]["open"] else 0.0
        self.assertAlmostEqual(float(day.iloc[-1]), sum(x["net_pts"] for x in closed) + op, delta=1.0)

    def test_supertrend_is_not_degenerate(self):
        df = synthetic(days=60)
        up, valid = M.supertrend_up(df, 10, 1.5)
        flips = int((np.diff(up[valid].astype(int)) != 0).sum())
        self.assertGreater(flips, 10, "the ratcheting bands must produce real flips (NaN-poisoning regression)")


class Published(unittest.TestCase):
    def test_payload(self):
        p = ROOT / "docs" / "methods.json"
        if not p.exists():
            self.skipTest("methods.json not generated")
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(len(d["methods"]), 10)
        self.assertGreaterEqual(d["total_closed_trades"], 300)
        keys = {m["key"] for m in d["methods"]}
        self.assertEqual(keys, {"sma5200", "st1015", "psma100", "don55", "ema21105",
                                "f_council", "f_twinpulse", "f_quorum", "f_heartbeat", "f_centreline"})
        nets = {}
        for m in d["methods"]:
            s = m["summary"]
            self.assertAlmostEqual(s["plus_pts"] + s["minus_pts"] + s["open_pts"], s["net_pts"], delta=0.5)
            self.assertAlmostEqual(s["net_rs"], s["net_pts"] * d["lot"], delta=0.05 * d["lot"] + 1)   # points published to 0.1
            closed = [x for x in m["trades"] if not x["open"]]
            self.assertEqual(s["trades"], len(closed))
            self.assertAlmostEqual(s["plus_pts"], sum(x["net_pts"] for x in closed if x["net_pts"] > 0), delta=0.5)
            self.assertAlmostEqual(s["minus_pts"], sum(x["net_pts"] for x in closed if x["net_pts"] <= 0), delta=0.5)
            self.assertLessEqual(sum(x["open"] for x in m["trades"]), 1)
            self.assertAlmostEqual(sum(y["pts"] for y in m["years"]), s["net_pts"], delta=1.0)
            nets[m["key"]] = s["net_pts"]
        self.assertEqual(d["ranking"], sorted(nets, key=lambda k: -nets[k]))
        last = d["race"][-1]
        for j, m in enumerate(d["methods"]):
            self.assertAlmostEqual(last[1 + j], m["summary"]["net_pts"], delta=0.5)
        html = (ROOT / "docs" / "methods.html").read_text(encoding="utf-8")
        for need in ('id="m5-board"', 'id="m5-pies"', 'id="m5-race"', 'id="m5-trades"', "methods.js"):
            self.assertIn(need, html)

    def test_charts_formulas_diary_and_pages(self):
        p = ROOT / "docs" / "methods.json"
        if not p.exists():
            self.skipTest("methods.json not generated")
        d = json.loads(p.read_text(encoding="utf-8"))
        for m in d["methods"]:
            self.assertTrue(m.get("formula"), m["key"])
            cf = ROOT / "docs" / m["chart"]
            self.assertTrue(cf.exists(), m["chart"])
            c = json.loads(cf.read_text(encoding="utf-8"))
            self.assertEqual(c["tf"], m["tf"])
            n = len(c["bars"])
            self.assertGreater(n, 200)
            for ln in c["lines"] + c["aux"]:
                self.assertEqual(len(ln["values"]), n, m["key"] + "/" + ln["name"])
            times = [b[0] for b in c["bars"]]
            self.assertEqual(times, sorted(times))
            self.assertTrue(c["lines"] or c["aux"], m["key"] + " must show the series its formula watches")
        ev = json.loads((ROOT / "docs" / "methods_events.json").read_text(encoding="utf-8"))
        self.assertIsInstance(ev, list)
        page = (ROOT / "docs" / "method.html").read_text(encoding="utf-8")
        for need in ('id="mp-chart"', 'id="mp-formula"', 'id="mp-trades"', 'id="mp-jev"', "method.js"):
            self.assertIn(need, page)
        hub = (ROOT / "docs" / "methods.html").read_text(encoding="utf-8")
        for need in ('id="m5-jev"', 'id="m5-diary"'):
            self.assertIn(need, hub)


if __name__ == "__main__":
    unittest.main()
