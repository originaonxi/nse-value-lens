"""Tests for the ₹1 crore engine, the EMA 105 bhavcopy audit and the grouped site menu."""
import json
import re
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import crore as C  # noqa: E402
import nifty_ema105_audit as A  # noqa: E402
import site_nav as S  # noqa: E402

DOCS = ROOT / "docs"


def frame(closes, day0="2026-01-01"):
    n = len(closes)
    idx = pd.date_range(day0 + " 09:15", periods=n, freq="2h")
    df = pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes}, index=idx)
    df["session"] = [str(t.date()) for t in idx]
    return df


class Money(unittest.TestCase):
    def setUp(self):
        self.c = np.array([100.0, 100, 110, 120, 90, 90, 100, 100])
        self.df = frame(self.c)
        self.X = {"c": self.c}
        self.lots = {d: 10 for d in self.df["session"].unique()}

    def test_whole_lots_cost_and_compounding(self):
        # capital 5,000: one lot = 100 x 10 = 1,000 -> 5 lots; buy at 100, sell at 120
        rows, v = C.run_money(self.X, self.df, [(1, 3, 1, "ema")], 5000, self.lots, 0, "t")
        r = rows[0]
        self.assertEqual(r["lots"], 5)
        self.assertEqual(r["qty"], 50)
        cost = C.COST * 50 * 100
        self.assertAlmostEqual(r["pnl"], round(50 * 20 - cost))
        self.assertAlmostEqual(v[-1], 5000 + 50 * 20 - cost)
        # second trade uses the grown cash: 5,000 + 1,000 - cost -> floor(5,998.25 / 900) = 6 lots at 90
        rows, v = C.run_money(self.X, self.df, [(1, 3, 1, "ema"), (4, 6, 1, "ema")], 5000, self.lots, 0, "t")
        self.assertEqual(rows[1]["lots"], int((5000 + 1000 - cost) // 900))

    def test_short_profits_when_price_falls(self):
        rows, _ = C.run_money(self.X, self.df, [(3, 4, -1, "ema")], 5000, self.lots, 0, "t")
        self.assertEqual(rows[0]["side"], "SELL")
        self.assertGreater(rows[0]["pnl"], 0)
        self.assertAlmostEqual(rows[0]["points"], 30.0)

    def test_skips_when_cash_below_one_lot(self):
        rows, v = C.run_money(self.X, self.df, [(1, 3, 1, "ema")], 500, self.lots, 0, "t")
        self.assertIn("skipped", rows[0])
        self.assertEqual(v[-1], 500)

    def test_no_overlap_inside_a_sleeve(self):
        with self.assertRaises(ValueError):
            C.run_money(self.X, self.df, [(1, 4, 1, "ema"), (2, 5, -1, "ema")], 5000, self.lots, 0, "t")

    def test_summary_counts_and_drawdown(self):
        df = self.df.copy()
        df["session"] = [f"2026-01-{i + 1:02d}" for i in range(len(df))]     # one bar per session
        lots = {d: 10 for d in df["session"]}
        rows, v = C.run_money(self.X, df, [(1, 3, 1, "ema"), (3, 4, 1, "ema")], 5000, lots, 0, "t")
        s = C.summary("t", "x", [("t", v, rows)], df, 0, 5000)
        self.assertEqual(s["trades"], 2)
        self.assertEqual(s["wins"] + s["losses"], 2)
        self.assertGreater(s["max_dd_pct"], 0)
        self.assertEqual(s["end"], round(v[-1]))

    def test_overlap_measure(self):
        a = np.array([1, 1, 0, 0]); b = np.array([1, 0, 0, -1])
        self.assertAlmostEqual(C.overlap(a, b), 1 / 3)
        self.assertEqual(C.overlap(a, a), 1.0)


class Audit(unittest.TestCase):
    def test_summary_profit_loss_split(self):
        tr = [{"net": 10.0, "gross": 12.0, "cost": 2.0, "rupees": 650, "side": "BUY", "closed": True},
              {"net": -5.0, "gross": -3.0, "cost": 2.0, "rupees": -325, "side": "SELL", "closed": True},
              {"net": 99.0, "gross": 99.0, "cost": 0.0, "rupees": 0, "side": "BUY", "closed": False}]
        s = A.summary(tr)
        self.assertEqual((s["trades"], s["wins"], s["losses"]), (2, 1, 1))
        self.assertEqual(s["net_pts"], 5.0)
        self.assertEqual(s["pf"], 2.0)
        self.assertEqual(s["buy_net"], 10.0)
        self.assertEqual(s["sell_net"], -5.0)

    def test_jev_tally_compares_with_code(self):
        tr = [{"net": 10.0, "side": "BUY", "closed": True, "entry_time": "a", "entry": 1, "exit": 2},
              {"net": -5.0, "side": "BUY", "closed": True, "entry_time": "b", "entry": 2, "exit": 1}]
        labels = {0: {"label": "profit", "conf": 99}, 1: {"label": "profit", "conf": 60}}
        t = A.jev_tally(tr, labels)
        self.assertEqual(t["profit_trades"], 2)
        self.assertEqual(t["agree_with_code"], 1)
        self.assertEqual(t["disagree"][0]["n"], 2)

    def test_official_close_replaces_only_last_bar_of_each_day(self):
        df = frame([1.0, 2, 3, 4, 5, 6], "2026-01-01")
        df["session"] = ["2026-01-01"] * 3 + ["2026-01-02"] * 3
        off = pd.DataFrame({"ind_close": [30.0, 60.0], "fo_close": [30.0, 60.0]}, index=["2026-01-01", "2026-01-02"])
        x = A.official_closes(df, off)
        self.assertEqual(list(x["Close"]), [1, 2, 30, 4, 5, 60])

    def test_published_audit(self):
        p = DOCS / "nifty_ema105_audit.json"
        if not p.exists():
            self.skipTest("audit not built")
        d = json.loads(p.read_text(encoding="utf-8"))
        o = d["official"]["buy_and_sell"]
        self.assertEqual(o["wins"] + o["losses"], o["trades"])
        self.assertAlmostEqual(o["profit_pts"] + o["loss_pts"], o["net_pts"], delta=0.2)
        self.assertAlmostEqual(o["gross_pts"] - o["cost_pts"], o["net_pts"], delta=0.2)
        closed = [t for t in d["trades"] if t["closed"]]
        self.assertEqual(len(closed), o["trades"])
        self.assertAlmostEqual(sum(t["net"] for t in closed), o["net_pts"], delta=0.5)
        self.assertGreaterEqual(d["window"]["sessions"], 450)


class Published(unittest.TestCase):
    def test_crore_payload(self):
        p = DOCS / "crore.json"
        if not p.exists():
            self.skipTest("crore.json not built")
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(d["capital"], 1_00_00_000)
        self.assertGreater(d["rules_tried"], 100_000)
        for w in d["windows"].values():
            for pf in w["portfolios"]:
                self.assertEqual(pf["start"], 1_00_00_000)
                self.assertEqual(pf["end"], pf["curve"][-1][1])
                self.assertEqual(pf["profit"], pf["end"] - pf["start"])
                self.assertAlmostEqual(sum(s["end"] for s in pf["sleeves"]), pf["end"], delta=len(pf["sleeves"]))
                for t in pf.get("trade_rows", []):
                    if "pnl" in t:
                        self.assertEqual(t["qty"], t["lots"] * t["lot_size"])
                        self.assertAlmostEqual(t["notional"], t["qty"] * t["entry"], delta=1)
                        # no leverage: the position never exceeds the sleeve it came from
                        self.assertLessEqual(t["notional"], pf["end"] * 50)
            self.assertTrue(any(pf["kind"] == "benchmark" for pf in w["portfolios"]))
        self.assertEqual(len(d["honest"]), 2)


class Menu(unittest.TestCase):
    def test_every_menu_link_exists_and_is_unique(self):
        hrefs = [h for _, links in S.GROUPS for h, _, _ in links]
        self.assertEqual(len(hrefs), len(set(hrefs)))
        for h in hrefs:
            self.assertTrue((DOCS / h).exists(), h)

    def test_pages_use_the_grouped_menu(self):
        for p in DOCS.glob("*.html"):
            t = p.read_text(encoding="utf-8")
            if "<header" not in t:
                continue
            self.assertEqual(t.count('class="sn"'), 1, p.name)
            self.assertEqual(t.count("site-nav.js"), 1, p.name)
            here = re.findall(r'<a href="([^"]+)" aria-current="page">', t)
            if any(p.name == h for _, links in S.GROUPS for h, _, _ in links):
                self.assertEqual(here, [p.name], p.name)


if __name__ == "__main__":
    unittest.main()
