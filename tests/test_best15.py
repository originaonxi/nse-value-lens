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

    def test_replay_book_matches_always_in_when_booking_never_triggers(self):
        df = synthetic()
        a = B.replay(df, 200)
        b = B.replay_book(df, 200, 0.5, 1e9)
        self.assertEqual([(x["side"], x["entry_time"], x["exit_time"], x["net_pts"]) for x in a[0]],
                         [(x["side"], x["entry_time"], x["exit_time"], x["net_pts"]) for x in b[0]])
        self.assertTrue(np.allclose(a[1], b[1]))

    def test_replay_book_fib_booking_and_wait_for_next_cross(self):
        df = synthetic(days=90, seed=11)
        trades, eq, ef, es, up, st = B.replay_book(df, 200, 0.5, 0.3, slip=5.0)
        t = list(df.index.strftime("%Y-%m-%d %H:%M"))
        o, c = df["Open"].to_numpy(), df["Close"].to_numpy()
        booked = [x for x in trades if x["exit_reason"] == "book"]
        self.assertGreater(len(booked), 0, "the synthetic path must exercise a booking")
        for x in trades:                                               # every entry is a crossover (or the first signal)
            i = t.index(x["entry_time"])
            self.assertEqual(up[i - 1], x["side"] == "BUY")
            self.assertTrue(i == 201 or up[i - 1] != up[i - 2], f"entry {x['entry_time']} is not on a crossover")
        for x in booked:
            p = 1 if x["side"] == "BUY" else -1
            g = p * (x["best"] - x["entry"])
            self.assertGreaterEqual(g, x["entry"] * 0.003 - 0.02)      # booking only after the trade was up 0.3%
            self.assertAlmostEqual(x["book_level"], x["best"] - p * 0.5 * g, delta=0.02)
            j = t.index(x["exit_signal_time"])
            self.assertTrue(c[j] <= x["book_level"] + 0.01 if p > 0 else c[j] >= x["book_level"] - 0.01)
            self.assertAlmostEqual(x["exit"], round(o[j + 1] - p * 5.0, 2), places=2)
            self.assertAlmostEqual(x["net_pts"], p * (x["exit"] - x["entry"]) - B.COST * (x["entry"] + x["exit"]), delta=0.02)
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

    def test_live_block_for_the_browser(self):
        d = json.loads((ROOT / "docs" / "best15.json").read_text(encoding="utf-8"))
        L = d["live"]
        self.assertEqual(L["time"], d["last_candle"])
        self.assertAlmostEqual(L["ema21"], d["now"]["ema21"], delta=0.01)
        self.assertAlmostEqual(L["ema105"], d["now"]["ema105"], delta=0.01)
        self.assertIn(L["side"], ("BUY", "SELL"))
        self.assertTrue(L["feed"].startswith("https://api.upstox.com/"))
        self.assertGreaterEqual(L["poll_s"], 15)
        if L["entry"] is not None:
            self.assertEqual(L["entry"], d["trades"][-1]["entry"])
        html = (ROOT / "docs" / "best15.html").read_text(encoding="utf-8")
        self.assertIn('id="b5-live"', html)

    def test_best5200_payload_and_live_window(self):
        p = ROOT / "docs" / "best5200.json"
        if not p.exists():
            self.skipTest("best5200.json not generated")
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual((d["kind"], d["fast"], d["slow"]), ("sma", 5, 200))
        self.assertEqual((d["fast_label"], d["slow_label"]), ("SMA 5", "SMA 200"))
        s, tr = d["summary"], d["trades"]
        closed = [x for x in tr if not x["open"]]
        self.assertEqual(s["trades"], len(closed))
        self.assertAlmostEqual(s["total_pts"], s["realised_pts"] + s["open_pts"], delta=1)
        self.assertAlmostEqual(sum(y["pts"] for y in d["years_mtm"]), s["total_pts"], delta=1)
        self.assertTrue(all(y["pts"] > 0 for y in d["years_mtm"]), "zero losing years is the whole claim")
        self.assertEqual(len(d["chart"]["bars"]), len(d["chart"]["ema21"]))
        L = d["live"]
        self.assertEqual(L["kind"], "sma")
        self.assertEqual(len(L["closes"]), d["slow"] - 1)
        self.assertAlmostEqual(L["closes"][-1], d["now"]["close"], delta=0.01)
        self.assertAlmostEqual(sum(L["closes"][-d["fast"]:]) / d["fast"], L["ema21"], delta=0.01,
                               msg="the published fast SMA must equal the mean of the last `fast` closes")
        # the published flip price really puts SMA 5 on SMA 200
        w = L["closes"]
        x = d["now"]["flip"]
        f5 = (sum(w[-4:]) + x) / 5
        f200 = (sum(w[-199:]) + x) / 200
        self.assertAlmostEqual(f5, f200, delta=0.05)
        html = (ROOT / "docs" / "best5200.html").read_text(encoding="utf-8")
        self.assertIn('data-src="best5200.json"', html)
        self.assertIn('data-pine="best5200.pine"', html)
        self.assertIn('href="best5200.pine"', html)

    def test_pine_scripts_are_paste_safe_and_match_the_rules(self):
        cases = [("best15.pine", ('input.int(21, "Fast EMA"', 'input.int(105, "Slow EMA"'), "best15.html", "best15.pine"),
                 ("best5200.pine", ('input.int(5, "Fast SMA"', 'input.int(200, "Slow SMA"'), "best5200.html", "best5200.pine")]
        for fname, pair_settings, page, pine_href in cases:
            src = (ROOT / "docs" / fname).read_text(encoding="utf-8")
            lines = src.split("\n")
            self.assertTrue(lines[0].startswith("//@version=6"), fname)
            for i, line in enumerate(lines, 1):
                self.assertLessEqual(len(line), 72, f"{fname} line {i} too long to copy safely")
                self.assertTrue(all(ord(ch) < 127 for ch in line), f"{fname} line {i} has a non-ASCII character")
                body = "" if line.lstrip().startswith("//") else line.split("//")[0]
                self.assertEqual(body.count('"') % 2, 0, f"{fname} line {i}: string not closed on the same line")
            for setting in pair_settings + ("default_qty_value = 65", "commission_value = 0.035",
                                            "process_orders_on_close = false", "03 Jul 2023 00:00 +0530"):
                self.assertIn(setting, src, fname)
            html = (ROOT / "docs" / page).read_text(encoding="utf-8")
            self.assertIn('id="b5-pine"', html)
            self.assertIn('href="' + pine_href + '"', html)

    def test_best6200fib_payload_booking_and_page(self):
        p = ROOT / "docs" / "best6200fib.json"
        if not p.exists():
            self.skipTest("best6200fib.json not generated")
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual((d["kind"], d["fast"], d["slow"], d["from"]), ("sma", 6, 200, "2023-01-12"))
        self.assertEqual((d["book"]["frac"], d["book"]["act_pct"], d["book"]["slip_pts"]), (0.5, 1.0, 5.0))
        s, tr, cmp_ = d["summary"], d["trades"], d["compare"]
        closed = [x for x in tr if not x["open"]]
        self.assertEqual(s["trades"], len(closed))
        self.assertAlmostEqual(s["total_pts"], s["realised_pts"] + s["open_pts"], delta=1)
        self.assertAlmostEqual(sum(y["pts"] for y in d["years_mtm"]), s["total_pts"], delta=1)
        self.assertEqual(cmp_["booked_exits"] + cmp_["crossover_exits"], len(closed))
        self.assertAlmostEqual(cmp_["book"]["total_pts"], s["total_pts"], delta=0.1)
        a = json.loads((ROOT / "docs" / "best6200.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(cmp_["always_in"]["total_pts"], a["summary"]["total_pts"], delta=0.1,
                               msg="the comparison must be against the published always-in 6/200 page")
        for x in closed:
            if x["exit_reason"] == "book":
                q = 1 if x["side"] == "BUY" else -1
                self.assertAlmostEqual(x["book_level"], x["best"] - q * 0.5 * q * (x["best"] - x["entry"]), delta=0.02)
        L, nb = d["live"], d["now"]["book"]
        self.assertEqual(L["book"]["pos"], nb["position"])
        if nb["position"]:
            self.assertEqual(L["entry"], tr[-1]["entry"])
            self.assertEqual(L["book"]["best"], nb["best"])
            if nb["armed"]:
                q = 1 if nb["position"] == "BUY" else -1
                self.assertAlmostEqual(nb["level"], nb["best"] - q * 0.5 * q * (nb["best"] - L["entry"]), delta=0.02)
        html = (ROOT / "docs" / "best6200fib.html").read_text(encoding="utf-8")
        for s_ in ('data-src="best6200fib.json"', 'data-pine="best6200fib.pine"', 'href="best6200fib.pine"', 'id="b5-book-cmp"',
                   'id="b5-book-now"', 'id="b5-chart"', 'id="b5-live"'):
            self.assertIn(s_, html)
        src = (ROOT / "docs" / "best6200fib.pine").read_text(encoding="utf-8")
        lines = src.split("\n")
        self.assertTrue(lines[0].startswith("//@version=6"))
        for i, line in enumerate(lines, 1):
            self.assertLessEqual(len(line), 72, f"best6200fib.pine line {i} too long to copy safely")
            self.assertTrue(all(ord(ch) < 127 for ch in line), f"best6200fib.pine line {i} has a non-ASCII character")
            body = "" if line.lstrip().startswith("//") else line.split("//")[0]
            self.assertEqual(body.count('"') % 2, 0, f"best6200fib.pine line {i}: string not closed on the same line")
        for setting in ('input.int(6, "Fast SMA"', 'input.int(200, "Slow SMA"', 'input.float(1.0, "Booking', 'input.float(0.5, "Give-back',
                        "default_qty_value = 65", "commission_value = 0.035", "process_orders_on_close = false", "12 Jan 2023 00:00 +0530",
                        'strategy.close("BUY", comment = "BOOK")'):
            self.assertIn(setting, src)


if __name__ == "__main__":
    unittest.main()
