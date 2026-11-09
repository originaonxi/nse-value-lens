"""₹1 crore whole-share replay of the fund: cash never goes negative, whole shares only, the books balance,
rebalances trade at the next close, 200-day exits sell at the next close, and the published payload is consistent."""
import json
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import fund as F  # noqa: E402
import fund_crore as C  # noqa: E402
from test_fund import synthetic  # noqa: E402


class Replay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.px, cls.nifty, cls.sectors = synthetic(n_stocks=60, days=420)
        dma = cls.px.rolling(F.DMA, min_periods=F.DMA).mean()
        cls.exit_sig = cls.px < dma
        cls.start = F.decision_rows(cls.px)[0]
        cls.out = C.replay(cls.px, cls.nifty, cls.sectors, cls.exit_sig, cls.start)

    def test_whole_shares_and_cash_never_negative(self):
        trades, _, daily, held, cash, _, _ = self.out
        self.assertTrue(trades)
        for t in trades:
            self.assertIsInstance(t["shares"], int)
            self.assertGreater(t["shares"], 0)
        for _, _, c in daily:
            self.assertGreaterEqual(c, -1.0)
        self.assertGreaterEqual(cash, -1.0)

    def test_books_balance(self):
        trades, _, daily, held, cash, fees, _ = self.out
        last = self.px.iloc[-1]
        self.assertAlmostEqual(daily[-1][1], cash + sum(h["shares"] * float(last[h["symbol"]]) for h in held), delta=1.0)
        self.assertAlmostEqual(fees, sum(t["amount"] * F.COST_PER_SIDE for t in trades), delta=len(trades))
        # every share bought is either still held or was sold
        net = {}
        for t in trades:
            net[t["symbol"]] = net.get(t["symbol"], 0) + (t["shares"] if t["side"] == "BUY" else -t["shares"])
        held_q = {h["symbol"]: h["shares"] for h in held}
        self.assertEqual({k: v for k, v in net.items() if v}, held_q)

    def test_rebalance_trades_at_next_close(self):
        _, rebal, _, _, _, _, _ = self.out
        dates = [str(d.date()) for d in self.px.index]
        self.assertTrue(rebal)
        for r in rebal:
            self.assertEqual(dates.index(r["executed"]), dates.index(r["decided"]) + 1)
            self.assertLessEqual(r["holdings"], F.HOLDINGS)

    def test_exits_sell_at_next_close_after_signal(self):
        trades = self.out[0]
        dates = list(self.px.index)
        for t in trades:
            if t["why"].startswith("closed below"):
                i = dates.index(pd.Timestamp(t["date"]))
                self.assertTrue(bool(self.exit_sig.iloc[i - 1][t["symbol"]]), t)


class Published(unittest.TestCase):
    def test_payload(self):
        p = ROOT / "docs" / "fund_crore.json"
        if not p.exists():
            self.skipTest("fund_crore.json not generated")
        d = json.loads(p.read_text(encoding="utf-8"))
        s = d["summary"]
        self.assertEqual(d["capital"], 10_000_000)
        self.assertEqual(s["profit"], s["end"] - d["capital"])
        self.assertEqual(s["trades"], len(d["trades"]))
        self.assertEqual(s["buys"] + s["sells"], s["trades"])
        self.assertEqual(s["rebalances"], len(d["rebalances"]))
        self.assertEqual(s["stocks_now"], len(d["held"]))
        self.assertEqual(d["curve"][0][1], d["capital"])
        self.assertEqual(d["curve"][-1][1], s["end"])
        self.assertEqual(d["curve"][-1][0], d["as_of"])
        self.assertAlmostEqual(s["end"], s["cash_now"] + sum(h["value"] for h in d["held"]), delta=len(d["held"]) + 2)
        # the whole-share replay tracks the fund's own NAV over the same days
        self.assertLess(abs(s["return_pct"] - s["fund_nav_return_pct"]), 3.0)


if __name__ == "__main__":
    unittest.main()
