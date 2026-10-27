"""Zigzag, auto-Fibonacci, event detection and per-stock history (no network)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import setup_signals as sig  # noqa: E402

inr = lambda v: "-" if v is None else f"{v:.2f}"


def bars(closes, spread=0.5):
    out = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        out.append({"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": o, "high": max(o, c) + spread,
                    "low": min(o, c) - spread, "close": c, "volume": 1000, "volume_average20": 1000})
    return out


def up_then_pullback():
    # 100 -> 150 rally, then a 50% pullback to 125, then a bounce at that level.
    return [100 + i for i in range(51)] + [150 - i for i in range(1, 26)] + [125 + (i % 3) for i in range(10)]


class Zigzag(unittest.TestCase):
    def test_alternates_and_finds_extremes(self):
        piv = sig.zigzag(bars(up_then_pullback()), threshold=10)
        kinds = [k for _, _, k in piv]
        self.assertTrue(all(a != b for a, b in zip(kinds, kinds[1:])), kinds)
        hi = [p for p in piv if p[2] == "H"]
        self.assertAlmostEqual(hi[0][1], 150.5)

    def test_too_short(self):
        self.assertEqual(sig.zigzag(bars([1.0]), 1), [])


class Fibonacci(unittest.TestCase):
    def test_levels_up_leg(self):
        ret, ext = sig.fib_levels(100, 200, up=True)
        p = {l["r"]: l["price"] for l in ret}
        self.assertEqual((p[0.0], p[0.5], p[0.618], p[1.0]), (200, 150, 138.2, 100))
        self.assertEqual([e["price"] for e in ext], [227.2, 261.8])

    def test_levels_down_leg(self):
        ret, ext = sig.fib_levels(100, 200, up=False)
        p = {l["r"]: l["price"] for l in ret}
        self.assertEqual((p[0.0], p[0.618], p[1.0]), (100, 161.8, 200))
        self.assertEqual(ext[0]["price"], 72.8)

    def test_auto_anchor_and_words(self):
        b = bars(up_then_pullback())
        f = sig.fibonacci(b, b[-1]["close"], inr)
        self.assertIsNotNone(f)
        self.assertIn(f["auto"], {a["method"] for a in f["anchors"]})
        a = next(x for x in f["anchors"] if x["method"] == f["auto"])
        self.assertEqual(a["dir"], "up")
        self.assertTrue(40 <= a["retrace_pct"] <= 60, a["retrace_pct"])
        self.assertIn("retraced", a["words"])
        best = max(x["score"] for x in f["anchors"])
        self.assertEqual(a["score"], best)


class Events(unittest.TestCase):
    order = {"breakout_today": 1, "ready_to_break": 2, "sideways": 5, "downtrend": 8}

    def run_events(self, b, prev, cat="sideways", series=None):
        series = series or {"supertrend_dir": [1, 1], "rsi": [50, 50], "bb_upper": [999, 999], "bb_lower": [0, 0]}
        return sig.detect_events(b, series, {}, None, cat, prev, self.order)[0]

    def test_long_target_needs_entry(self):
        b = bars([100.0] * 25 + [104.0])            # today: high 104.5, low 99.5
        b[-1]["high"] = 110
        prev = {"category": "ready_to_break", "side": "long", "entry": 102, "stop": 97, "next_target": 108}
        self.assertIn("target_hit", self.run_events(b, prev))
        prev_far = {**prev, "entry": 115, "next_target": 120}   # trigger never crossed -> no trade, no hit
        b[-1]["high"] = 121
        b[-1]["low"] = 96
        ev = self.run_events(b, {**prev_far, "stop": 97})
        self.assertIn("target_hit", ev)                       # crossed 115 and reached 120
        b[-1]["high"] = 112
        ev = self.run_events(b, {**prev_far, "stop": 97})
        self.assertNotIn("stop_hit", ev)                      # low hit 96 but entry 115 never filled

    def test_short_stop(self):
        b = bars([100.0] * 25 + [99.0])
        b[-1]["high"] = 106
        prev = {"category": "downtrend", "side": "short", "entry": 100, "stop": 105, "next_target": 90}
        self.assertIn("stop_hit", self.run_events(b, prev, cat="downtrend"))

    def test_category_change_and_flips(self):
        b = bars([100.0] * 25 + [101.0])
        prev = {"category": "downtrend", "side": "short", "entry": None, "stop": None, "next_target": None}
        ev = self.run_events(b, prev, cat="ready_to_break",
                             series={"supertrend_dir": [-1, 1], "rsi": [50, 60], "bb_upper": [999, 999], "bb_lower": [0, 0]})
        for k in ("upgraded", "st_flip_up", "momentum_up"):
            self.assertIn(k, ev)

    def test_20d_high_and_volume(self):
        b = bars([100.0] * 25 + [110.0])
        b[-1]["volume"] = 2500
        ev = self.run_events(b, None)
        self.assertIn("high_20d", ev)
        self.assertIn("volume_spike", ev)


class History(unittest.TestCase):
    def test_breakout_follow_through(self):
        b = bars([100 + i for i in range(40)])
        b[5]["structure_breakout"] = True
        h = sig.history_stats(b, horizon=10)
        self.assertEqual(h["breakouts"]["count"], 1)
        self.assertEqual(h["breakouts"]["worked"], 1)
        self.assertGreater(h["breakouts"]["avg_pct"], 0)
        self.assertEqual(h["exits"]["count"], 0)


if __name__ == "__main__":
    unittest.main()
