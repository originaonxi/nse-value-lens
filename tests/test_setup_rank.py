"""Chart-fact ranking: factor points, list membership and rank orders (no network)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import setup_rank as rk  # noqa: E402


def bars(closes):
    return [{"date": f"d{i:03d}", "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 100} for i, c in enumerate(closes)]


def stock(sym, cat, structure, state, rsi, jev=None, close=100.0):
    return {
        "symbol": sym, "category": cat, "structure": structure, "close": close, "atr": 2.0,
        "trigger": close + 1, "structure_exit": close - 5, "events": [], "volume_ratio": 1.0,
        "indicators": {
            "supertrend": {"state": state, "label": "Up" if state == "bull" else "Down", "value": close - 3},
            "adx": {"value": 30, "plus_di": 30 if state == "bull" else 10, "minus_di": 10 if state == "bull" else 30},
            "rsi": {"value": rsi}, "bollinger": {"value": 85 if state == "bull" else 10},
            "obv": {"state": state, "label": "x"}, "vwap20": {"value": close * (0.98 if state == "bull" else 1.02)},
        },
        "jev": {"composite": jev} if jev is not None else {},
    }


class Factors(unittest.TestCase):
    def test_points_add_to_at_most_100(self):
        self.assertEqual(rk.MAX, 100)
        s = stock("A", "uptrend", "HH / HL", "bull", 70)
        fs = rk.chart_factors(s, bars([90 + i * 0.5 for i in range(30)]))
        self.assertEqual({f["key"] for f in fs}, {f["key"] for f in rk.FACTORS})
        caps = {f["key"]: f["max"] for f in rk.FACTORS}
        for f in fs:
            self.assertLessEqual(max(f["bull"], f["bear"]), caps[f["key"]], f)
            self.assertTrue(f["bull"] == 0 or f["bear"] == 0, f)          # a fact scores for one side only
        self.assertEqual(sum(f["bear"] for f in fs), 0)

    def test_bearish_mirror(self):
        s = stock("B", "downtrend", "LH / LL", "bear", 30)
        fs = rk.chart_factors(s, bars([110 - i * 0.5 for i in range(30)]))
        self.assertEqual(sum(f["bull"] for f in fs), 0)
        self.assertGreater(sum(f["bear"] for f in fs), 60)


class Lists(unittest.TestCase):
    def build(self):
        st = [stock("UP1", "uptrend", "HH / HL", "bull", 70, jev=0.4),
              stock("UP2", "ready_to_break", "HH / HL", "bull", 58, jev=0.8),
              stock("DN1", "downtrend", "LH / LL", "bear", 25, jev=0.1),
              stock("DN2", "below_structure", "MIXED", "bear", 44, jev=0.3),
              stock("SW1", "sideways", "MIXED", "bull", 52),
              stock("BAD", "data_check", "MIXED", "bull", 50)]
        b = {s["symbol"]: bars([100.0] * 30) for s in st}
        return st, rk.rank_all(st, b)

    def test_membership_and_order(self):
        st, block = self.build()
        L = block["lists"]
        self.assertEqual(set(L["buy"]["chart_order"]), {"UP1", "UP2"})
        self.assertEqual(set(L["sell"]["chart_order"]), {"DN1", "DN2"})
        self.assertEqual(L["watch"]["chart_order"], ["SW1"])
        s = {x["symbol"]: x for x in st}
        self.assertIsNone(s["BAD"]["rank"])
        self.assertEqual(L["buy"]["chart_order"][0], "UP1")              # RSI 70 beats RSI 58
        self.assertEqual(L["sell"]["chart_order"][0], "DN1")             # LH/LL + RSI 25 is the weakest
        self.assertEqual(L["buy"]["jev_order"], ["UP2", "UP1"])          # Jev: highest composite first
        self.assertEqual(L["sell"]["jev_order"], ["DN1", "DN2"])         # Jev SELL: lowest composite first
        self.assertEqual(L["watch"]["jev_order"], [])                    # no Jev score -> no Jev rank
        self.assertIsNone(s["SW1"]["rank"]["jev_rank"])
        for k in ("buy", "sell"):
            self.assertEqual(sorted(L[k]["combined_order"]), sorted(L[k]["chart_order"]))
        self.assertEqual(s["UP1"]["rank"]["all_buy_rank"], 1)
        self.assertEqual(s["DN1"]["rank"]["all_sell_rank"], 1)


class PublishedRanking(unittest.TestCase):
    path = Path(__file__).resolve().parents[1] / "docs" / "daily_setups.json"

    @unittest.skipUnless(path.exists(), "daily_setups.json not generated")
    def test_every_ranked_stock_once_and_scores_trace_to_factors(self):
        d = json.loads(self.path.read_text(encoding="utf-8"))
        lists = d["ranking"]["lists"]
        listed = [sym for L in lists.values() for sym in L["chart_order"]]
        self.assertEqual(len(listed), len(set(listed)))
        ranked = [s for s in d["stocks"] if s.get("rank")]
        self.assertEqual(len(listed), len(ranked))
        for s in ranked:
            r = s["rank"]
            self.assertAlmostEqual(r["bull"], sum(f["bull"] for f in r["factors"]), places=1)
            self.assertAlmostEqual(r["bear"], sum(f["bear"] for f in r["factors"]), places=1)
            self.assertAlmostEqual(r["net"], r["bull"] - r["bear"], places=1)
        nets = [next(x for x in d["stocks"] if x["symbol"] == sym)["rank"]["net"] for sym in lists["buy"]["chart_order"]]
        self.assertEqual(nets, sorted(nets, reverse=True))
        nets = [next(x for x in d["stocks"] if x["symbol"] == sym)["rank"]["net"] for sym in lists["sell"]["chart_order"]]
        self.assertEqual(nets, sorted(nets))


if __name__ == "__main__":
    unittest.main()
