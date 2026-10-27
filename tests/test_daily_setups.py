"""Indicator maths, category rules and plan invariants for daily_setups.py (no network)."""
import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import daily_setups as ds  # noqa: E402


def bars_from(closes, spread=1.0, volume=1000):
    out = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        out.append({"date": f"2026-01-{i + 1:03d}", "open": o, "high": max(o, c) + spread, "low": min(o, c) - spread,
                    "close": c, "volume": volume})
    return out


def scan_row(closes, **over):
    chart = bars_from(closes)
    close = closes[-1]
    row = {
        "symbol": "TEST", "name": "Test Ltd", "sector": "X", "data_date": chart[-1]["date"], "complete_for_session": True,
        "data_warnings": [], "close": close, "atr": 2.0, "structure": "HH / HL", "status": "WATCH",
        "fresh_breakout": False, "exit_condition": False, "sell_triggered_today": False,
        "zones": {"breakout_above": close + 1, "structure_exit_below": close - 6},
        "chart": chart, "chart_swings": [{"price": close + 1, "kind": "high", "pivot_date": chart[-5]["date"], "label": "HH"},
                                         {"price": close - 6, "kind": "low", "pivot_date": chart[-8]["date"], "label": "HL"}],
    }
    row.update(over)
    return row


class IndicatorMaths(unittest.TestCase):
    def test_rsi_extremes(self):
        up = ds.rsi([float(i) for i in range(1, 40)])
        down = ds.rsi([float(40 - i) for i in range(1, 40)])
        self.assertEqual(up[-1], 100.0)
        self.assertAlmostEqual(down[-1], 0.0, places=6)
        self.assertIsNone(up[5])

    def test_rsi_known_value(self):
        # Wilder: first RSI = 100 - 100 / (1 + mean(gains of 14 changes) / mean(losses of 14 changes))
        c = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
        ch = [b - a for a, b in zip(c, c[1:])]
        g, l = sum(max(x, 0) for x in ch) / 14, sum(max(-x, 0) for x in ch) / 14
        self.assertAlmostEqual(ds.rsi(c)[14], 100 - 100 / (1 + g / l), places=9)
        self.assertAlmostEqual(ds.rsi(c)[14], 70.46, delta=0.01)

    def test_supertrend_follows_trend(self):
        line, d = ds.supertrend(bars_from([100 + i for i in range(60)]))
        self.assertEqual(d[-1], 1)
        self.assertLess(line[-1], 159)
        line, d = ds.supertrend(bars_from([200 - i for i in range(60)]))
        self.assertEqual(d[-1], -1)
        self.assertGreater(line[-1], 141)

    def test_adx_strong_trend_and_di_order(self):
        a, p, m = ds.adx(bars_from([100 + 2 * i for i in range(80)]))
        self.assertGreater(a[-1], 25)
        self.assertGreater(p[-1], m[-1])

    def test_bollinger_flat_and_obv(self):
        mid, up, lo = ds.bollinger([10.0] * 25)
        self.assertEqual((mid[-1], up[-1], lo[-1]), (10.0, 10.0, 10.0))
        self.assertEqual(ds.obv(bars_from([1, 2, 3, 2], volume=10)), [0.0, 10.0, 20.0, 10.0])

    def test_vwap_constant_price(self):
        self.assertAlmostEqual(ds.vwap_rolling(bars_from([50.0] * 25, spread=0))[-1], 50.0)

    def test_black_scholes_parity(self):
        s, k, t, v = 100, 105, 30 / 365, 0.3
        c, p = ds.bs_price(s, k, t, v, "CE"), ds.bs_price(s, k, t, v, "PE")
        self.assertAlmostEqual(c - p, s - k * math.exp(-ds.RISK_FREE * t), places=6)


class Categories(unittest.TestCase):
    def reads(self, closes):
        return ds.indicator_pack(bars_from(closes))[0]

    def test_breakout_and_exit_today(self):
        closes = [100 + i * 0.5 for i in range(80)]
        r = self.reads(closes)
        self.assertEqual(ds.classify(scan_row(closes, fresh_breakout=True), r), "breakout_today")
        self.assertEqual(ds.classify(scan_row(closes, sell_triggered_today=True, exit_condition=True), r), "exit_today")

    def test_ready_vs_uptrend_vs_below(self):
        closes = [100 + i * 0.5 for i in range(80)]
        r = self.reads(closes)
        self.assertEqual(ds.classify(scan_row(closes), r), "ready_to_break")
        far = scan_row(closes)
        far["zones"]["breakout_above"] = closes[-1] + 10
        self.assertEqual(ds.classify(far, r), "uptrend")
        self.assertEqual(ds.classify(scan_row(closes, structure="MIXED", exit_condition=True), r), "below_structure")
        self.assertEqual(ds.classify(scan_row(closes, structure="LH / LL"), r), "downtrend")

    def test_incomplete_data(self):
        closes = [100.0] * 80
        self.assertEqual(ds.classify(scan_row(closes, complete_for_session=False), self.reads(closes)), "data_check")


class Plans(unittest.TestCase):
    def test_long_plan_ordering_and_rr(self):
        closes = [100 + i * 0.5 for i in range(80)]
        row = scan_row(closes)
        reads = ds.indicator_pack(row["chart"])[0]
        entry, stop, targets, _ = ds.long_plan(row, "ready_to_break", reads)
        self.assertLess(stop, entry)
        self.assertTrue(all(t > entry for t in targets))
        self.assertGreaterEqual((targets[0] - entry) / (entry - stop), 1.0 - 1e-9)   # T1 at least 1R

    def test_short_plan_ordering(self):
        closes = [200 - i * 0.5 for i in range(80)]
        row = scan_row(closes, structure="LH / LL")
        reads = ds.indicator_pack(row["chart"])[0]
        entry, stop, targets, _ = ds.short_plan(row, "downtrend", reads)
        self.assertGreater(stop, entry)
        self.assertTrue(all(t < entry for t in targets))

    def test_sizing_respects_risk_and_cap(self):
        s = ds.sizing(100.0, 98.0, "long")
        self.assertLessEqual(s["max_loss"], ds.CAPITAL * ds.RISK_PCT / 100)
        self.assertLessEqual(s["value"], ds.CAPITAL * ds.MAX_POSITION_PCT / 100)


class PublishedFile(unittest.TestCase):
    """If a generated file exists, every stock has one known category and coherent levels."""
    path = Path(__file__).resolve().parents[1] / "docs" / "daily_setups.json"

    @unittest.skipUnless(path.exists(), "daily_setups.json not generated")
    def test_generated_invariants(self):
        d = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len({s["symbol"] for s in d["stocks"]}), len(d["stocks"]))
        self.assertEqual(sum(c["count"] for c in d["categories"]), len(d["stocks"]))
        for s in d["stocks"]:
            self.assertIn(s["category"], ds.CATEGORIES)
            p = s.get("plan") or {}
            if p.get("stop") is None:
                continue
            if p["side"] == "long":
                self.assertLess(p["stop"], p["entry"], s["symbol"])
                self.assertTrue(all(t > p["entry"] for t in p["targets"]), s["symbol"])
            else:
                self.assertGreater(p["stop"], p["entry"], s["symbol"])
                self.assertTrue(all(t < p["entry"] for t in p["targets"]), s["symbol"])
            h = s.get("hedge") or {}
            if h.get("available"):
                self.assertTrue(s["fno"])
                self.assertGreater(h["max_loss"], 0, s["symbol"])


if __name__ == "__main__":
    unittest.main()
