import unittest
import pandas as pd
from cross_asset_research import allocation,simulate
class CrossAssetTests(unittest.TestCase):
    def test_negative_momentum_stays_cash(self):
        self.assertEqual(allocation({"A":pd.Series(dict(ret126=-.1))},"dual_momentum"),{})
    def test_selects_stronger_asset(self):
        p={"A":pd.Series(dict(ret126=.2)),"B":pd.Series(dict(ret126=.1))}
        self.assertEqual(allocation(p,"dual_momentum"),{"A":1.})
    def test_half_allocation_not_reallocated(self):
        p={"A":pd.Series(dict(Close=110,sma200=100)),"B":pd.Series(dict(Close=90,sma200=100))}
        self.assertEqual(allocation(p,"diversified_trend"),{"A":.5})
    def test_twenty_day_exit_and_costs(self):
        days=pd.bdate_range("2025-01-01",periods=22)
        d=pd.DataFrame(dict(Open=100.,High=101.,Low=99.,Close=100.,ret126=.1,sma200=90.),index=days)
        r=simulate({"A":d},d,"dual_momentum","2025-01-02","2025-01-31")
        self.assertEqual(r["trade_log"][0]["sessions"],20)
        self.assertEqual(r["trade_log"][0]["signal_date"],"2025-01-01")
        self.assertLess(r["return_pct"],0)
if __name__=="__main__":unittest.main()

