"""Unit tests for fno_play.py — ₹1 play desk signal engine."""
import sys, unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fno_play as F


def _ohlcv(n=300, trend="up", seed=1):
    rng = np.random.default_rng(seed)
    drift = {"up": 0.0004, "down": -0.0004, "flat": 0.0}[trend]
    log_ret = rng.normal(drift, 0.012, n)
    close  = 1000 * np.exp(np.cumsum(log_ret))
    noise  = rng.uniform(0.003, 0.010, n)
    high   = close * (1 + noise)
    low    = close * (1 - noise)
    open_p = close * (1 + rng.normal(0, 0.003, n))
    volume = rng.integers(500_000, 5_000_000, n).astype(float)
    idx    = pd.date_range("2020-01-01", periods=n, freq="B")
    return pd.DataFrame({"Open": open_p, "High": high, "Low": low,
                         "Close": close, "Volume": volume}, index=idx)


class TestComputeMetrics(unittest.TestCase):
    def test_returns_dict(self):
        df = _ohlcv(100, "up")
        m = F.compute_metrics(df)
        self.assertIsNotNone(m)
        for k in ("close","high","low","open","prev_close","adr20","dma5","dma20",
                  "pivot","r1","r2","s1","s2","range_pos","change_pct"):
            self.assertIn(k, m, f"Missing key: {k}")

    def test_pivot_formula(self):
        df = _ohlcv(100)
        m = F.compute_metrics(df)
        expected = (m["high"] + m["low"] + m["close"]) / 3
        self.assertAlmostEqual(m["pivot"], expected, places=1)

    def test_r1_above_pivot(self):
        m = F.compute_metrics(_ohlcv(100))
        self.assertGreater(m["r1"], m["pivot"])
        self.assertGreater(m["r2"], m["r1"])

    def test_s1_below_pivot(self):
        m = F.compute_metrics(_ohlcv(100))
        self.assertLess(m["s1"], m["pivot"])
        self.assertLess(m["s2"], m["s1"])

    def test_range_pos_between_0_and_1(self):
        m = F.compute_metrics(_ohlcv(100))
        self.assertGreaterEqual(m["range_pos"], 0)
        self.assertLessEqual(m["range_pos"], 1)

    def test_adr20_positive(self):
        m = F.compute_metrics(_ohlcv(100))
        self.assertGreater(m["adr20"], 0)

    def test_insufficient_data_returns_none(self):
        df = _ohlcv(10)
        self.assertIsNone(F.compute_metrics(df))


class TestSignalScore(unittest.TestCase):
    def _score(self, trend="up", **override):
        df = _ohlcv(100, trend)
        m  = F.compute_metrics(df)
        m.update(override)
        return F.signal_score(m)

    def test_score_in_range(self):
        sc, _ = self._score()
        self.assertGreaterEqual(sc, -1.0)
        self.assertLessEqual(sc, 1.0)

    def test_uptrend_positive(self):
        """Explicit bullish metrics guarantee a positive score."""
        m = {"close":1100,"dma5":1060,"dma20":1020,"range_pos":0.82,
             "open":1070,"vol_ratio":1.4,"high":1110,"low":1060,"prev_close":1080,"adr20":50}
        sc, _ = F.signal_score(m)
        self.assertGreater(sc, 0)

    def test_downtrend_negative(self):
        """Explicit bearish metrics guarantee a negative score."""
        m = {"close":900,"dma5":950,"dma20":980,"range_pos":0.18,
             "open":930,"vol_ratio":1.3,"high":935,"low":895,"prev_close":920,"adr20":40}
        sc, _ = F.signal_score(m)
        self.assertLess(sc, 0)

    def test_reasons_list_nonempty(self):
        _, reasons = self._score()
        self.assertGreater(len(reasons), 0)

    def test_high_vix_reduces_conviction(self):
        df = _ohlcv(100, "up")
        m  = F.compute_metrics(df)
        sc_normal, _ = F.signal_score(m, vix=15)
        sc_highvix, _ = F.signal_score(m, vix=28)
        self.assertLessEqual(abs(sc_highvix), abs(sc_normal) + 0.01)


class TestClassifySignal(unittest.TestCase):
    def test_high_positive_score_is_buy(self):
        sig = F.classify_signal(0.8, adr20=25)
        self.assertEqual(sig, "buy_strong")

    def test_high_negative_score_is_sell(self):
        sig = F.classify_signal(-0.8, adr20=25)
        self.assertEqual(sig, "sell_strong")

    def test_low_adr_is_avoid(self):
        sig = F.classify_signal(0.9, adr20=3)
        self.assertEqual(sig, "avoid")

    def test_high_vix_is_avoid(self):
        sig = F.classify_signal(0.8, adr20=25, vix=35)
        self.assertEqual(sig, "avoid")

    def test_near_zero_is_wait(self):
        sig = F.classify_signal(0.05, adr20=25)
        self.assertEqual(sig, "wait")

    def test_mild_positive_is_watch_buy(self):
        sig = F.classify_signal(0.15, adr20=25)
        self.assertEqual(sig, "watch_buy")


class TestBacktestRs1(unittest.TestCase):
    def test_returns_correct_keys(self):
        df = _ohlcv(300, "up")
        bt = F.backtest_rs1(df)
        for k in ("long_wr","short_wr","long_n","short_n"):
            self.assertIn(k, bt)

    def test_uptrend_long_wr_high(self):
        df = _ohlcv(400, "up", seed=7)
        bt = F.backtest_rs1(df)
        if bt["long_n"] >= 5 and bt["long_wr"] is not None:
            self.assertGreater(bt["long_wr"], 50)

    def test_insufficient_data_returns_none_wr(self):
        df = _ohlcv(30, "up")
        bt = F.backtest_rs1(df)
        self.assertEqual(bt["long_n"], 0)
        self.assertIsNone(bt["long_wr"])

    def test_win_rate_in_0_to_100(self):
        df = _ohlcv(400)
        bt = F.backtest_rs1(df)
        for k in ("long_wr","short_wr"):
            if bt[k] is not None:
                self.assertGreaterEqual(bt[k], 0)
                self.assertLessEqual(bt[k], 100)


class TestBuildOutput(unittest.TestCase):
    """Smoke tests on the payload structure (uses cached prices if available)."""
    def setUp(self):
        import json, pathlib
        p = pathlib.Path(__file__).resolve().parents[1] / "docs" / "fno-play.json"
        if p.exists():
            self.payload = json.loads(p.read_text(encoding="utf-8"))
        else:
            self.payload = None

    def test_payload_exists(self):
        if self.payload is None:
            self.skipTest("fno-play.json not yet generated")
        self.assertIn("rows", self.payload)

    def test_all_rows_have_signal(self):
        if self.payload is None:
            self.skipTest("fno-play.json not yet generated")
        valid = set(F.SIGNAL_MAP.keys())
        for r in self.payload["rows"]:
            self.assertIn(r["signal"], valid, f"{r['symbol']} has bad signal")

    def test_adr_vs_rs1_column(self):
        if self.payload is None:
            self.skipTest("fno-play.json not yet generated")
        for r in self.payload["rows"]:
            self.assertIn("adr_vs_rs1", r)
            self.assertGreater(r["adr_vs_rs1"], 0)

    def test_lot_sizes_positive(self):
        if self.payload is None:
            self.skipTest("fno-play.json not yet generated")
        for r in self.payload["rows"]:
            self.assertGreater(r["lot_size"], 0)


class TestGetVix(unittest.TestCase):
    def test_returns_float(self):
        v = F.get_vix()
        self.assertIsInstance(v, float)
        self.assertGreater(v, 0)


if __name__ == "__main__":
    unittest.main()
