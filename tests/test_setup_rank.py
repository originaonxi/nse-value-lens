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

    def test_final_order_is_jev_first_then_unscored_by_chart(self):
        st, block = self.build()
        L = block["lists"]
        self.assertEqual(L["buy"]["final_order"], ["UP2", "UP1"])        # Jev 80 beats Jev 40
        self.assertEqual(L["sell"]["final_order"], ["DN1", "DN2"])       # sell score 100-10=90 beats 100-30=70
        self.assertEqual(L["watch"]["final_order"], ["SW1"])            # unscored, follows by chart
        self.assertEqual(L["watch"]["not_jev_count"], 1)
        s = {x["symbol"]: x for x in st}
        self.assertEqual(s["DN1"]["rank"]["jev"]["list_score"], 90.0)
        self.assertEqual(s["UP2"]["rank"]["final_rank"], 1)
        self.assertIsNone(s["SW1"]["rank"]["jev"])
        self.assertIn("no Jev score", s["SW1"]["rank"]["words"])

    def test_accounting_counts_every_stock_once(self):
        st, block = self.build()
        a = block["accounting"]
        self.assertEqual((a["total"], a["ranked"], a["jev_scored"]), (6, 5, 4))
        self.assertEqual([u["symbol"] for u in a["unranked"]], ["BAD"])
        self.assertEqual(sum(v["count"] for v in a["by_list"].values()) + len(a["unranked"]), a["total"])
        self.assertIn("6 stocks = 2 Buy + 2 Sell + 1 Watch + 1 not ranked", a["words"])


class JevScore(unittest.TestCase):
    def s(self, sq, ft, rr, comp):
        return {"jev": {"composite": comp, "setup_quality": sq, "follow_through": ft, "risk_reward": rr,
                        "direction": "up", "confidence": 0.7, "rank": 3, "of": 200}}

    def test_points_sum_to_score_out_of_100(self):
        b = rk.jev_breakdown(self.s(3.42, 3.61, 2.23, 0.7651), "buy")
        self.assertEqual([p["weight"] for p in b["points"]], [35, 30, 35])
        self.assertAlmostEqual(b["points"][0]["points"], 35 * 3.42 / 4, places=2)
        self.assertAlmostEqual(b["points"][1]["points"], 30 * 3.61 / 4, places=2)
        self.assertAlmostEqual(b["points"][2]["points"], 35 * 2.23 / 4, places=2)
        self.assertAlmostEqual(b["score"], sum(p["points"] for p in b["points"]), places=1)
        self.assertAlmostEqual(b["score"], 76.5, places=1)               # = Jev composite 0.7651 x 100
        self.assertEqual(b["list_score"], b["score"])

    def test_extremes_and_sell_inversion(self):
        self.assertEqual(rk.jev_breakdown(self.s(4, 4, 4, 1.0), "buy")["score"], 100.0)
        self.assertEqual(rk.jev_breakdown(self.s(0, 0, 0, 0.0), "buy")["score"], 0.0)
        b = rk.jev_breakdown(self.s(0.41, 0.99, 0.47, 0.1512), "sell")
        self.assertAlmostEqual(b["list_score"], round(100 - b["score"], 1), places=6)
        self.assertIsNone(rk.jev_breakdown({"jev": {}}, "buy"))


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
