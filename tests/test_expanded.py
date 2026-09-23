import unittest
import pandas as pd
from expanded_research import day_exit, simulate, metrics, picks

class ExpandedResearchTests(unittest.TestCase):
    def row(self, **kwargs):
        data=dict(Open=100.,High=100.5,Low=99.5,Close=100.,Volume=1e6,
            atr=2.,sma50=105.,sma200=110.,ret126=.1,ret63=.1,ret20=-.1,
            ret5=-.02,ret1=-.01,vol63=.02,turnover=1e9)
        data.update(kwargs)
        return pd.Series(data)
    def test_short_stop_first_and_gap(self):
        self.assertEqual(day_exit(-1,100,102,97,self.row(Open=100,High=103,Low=96),0),(102,"stop"))
        self.assertEqual(day_exit(-1,100,102,97,self.row(Open=104,High=105,Low=96),0),(104.,"stop"))
    def test_long_stop_first_and_gap(self):
        self.assertEqual(day_exit(1,100,98,103,self.row(Open=96,High=105,Low=95),0),(96.,"stop"))
    def test_short_profit_accounting(self):
        days=pd.bdate_range("2025-01-01",periods=2)
        rows={days[0]:{"A":self.row()},days[1]:{"A":self.row(Open=100,High=101,Low=98,Close=99)}}
        market=pd.DataFrame([self.row(),self.row()],index=days)
        result=simulate(rows,market,{"A":"X"},"intraday_short","2025-01-02","2025-01-02")
        trade=result["trade_log"][0]
        expected=trade["qty"]*((trade["entry_price"]-trade["exit_price"])-.0005*(trade["entry_price"]+trade["exit_price"]))
        self.assertAlmostEqual(trade["pnl"],expected,places=2)
        self.assertGreater(trade["pnl"],0)
        self.assertEqual(trade["entry_date"],trade["exit_date"])
        self.assertEqual(trade["signal_date"],"2025-01-01")
    def test_selection_uses_previous_data(self):
        chosen=picks({"A":self.row()},self.row(),"intraday_short",{"A":"X"})
        self.assertEqual(chosen,[("A",-1,2.)])
    def test_losing_days_visible(self):
        r=metrics([{"date":"2025-01-01","equity":101000},{"date":"2025-01-02","equity":99000},{"date":"2025-01-03","equity":98000}],[])
        self.assertEqual(r["losing_days"],2)
        self.assertEqual(r["longest_losing_streak"],2)
        self.assertLess(r["return_pct"],0)

if __name__=="__main__":unittest.main()

