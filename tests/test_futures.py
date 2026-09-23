import unittest
import pandas as pd
from futures_research import simulate
class FuturesTests(unittest.TestCase):
    def fixture(self, gap=False):
        days=pd.bdate_range("2025-01-01",periods=3 if gap else 2)
        spot=pd.DataFrame(dict(Close=90.,sma50=100.,atr=2.),index=days)
        rows=[]
        for i,d in enumerate(days):
            rows.append(dict(day=d,expiry=pd.Timestamp("2025-02-01"),FinInstrmId=1,TtlTradgVol=1000,
                NewBrdLotQty=10,OpnPric=106. if gap and i==2 else 100.,
                HghPric=107. if gap and i==2 else 101.,LwPric=105. if gap and i==2 else 98.,
                ClsPric=106. if gap and i==2 else 99.))
        return pd.DataFrame(rows),spot
    def test_actual_lot_and_short_net_pnl(self):
        raw,spot=self.fixture()
        r=simulate(raw,spot,"futures_intraday","2025-01-02","2025-01-02")
        t=r["trade_log"][0]
        self.assertEqual(t["lot_size"],10)
        self.assertLessEqual(t["lots"]*10*t["entry_price"]*1.0005,2000000)
        expected=t["lots"]*10*(t["entry_price"]-t["exit_price"]-.0005*(t["entry_price"]+t["exit_price"]))
        self.assertAlmostEqual(t["pnl"],expected,places=2)
        self.assertGreater(t["pnl"],0)
        self.assertEqual(t["signal_date"],"2025-01-01")
    def test_gap_stop_uses_worse_open(self):
        raw,spot=self.fixture(True)
        r=simulate(raw,spot,"futures_swing","2025-01-02","2025-01-03")
        t=r["trade_log"][0]
        self.assertGreater(t["exit_price"],106)
        self.assertLess(t["pnl"],0)
        self.assertEqual(t["reason"],"stop")
if __name__=="__main__":unittest.main()

