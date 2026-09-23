import unittest
import numpy as np
import pandas as pd
from indicator_research import indicators,supertrend,confirmed_structure,simulate,select_past,wilder
class IndicatorTests(unittest.TestCase):
 def frame(self,n=300):
  rng=np.random.default_rng(28);close=100+np.cumsum(rng.normal(.08,1,n));op=close+rng.normal(0,.2,n)
  return pd.DataFrame({'Open':op,'High':np.maximum(close,op)+1,'Low':np.minimum(close,op)-1,'Close':close,'Volume':2e6},index=pd.bdate_range('2024-01-01',periods=n))
 def test_all_indicators_are_prefix_invariant(self):
  frame=self.frame();full=indicators(frame);prefix=indicators(frame.iloc[:220])
  pd.testing.assert_frame_equal(full.loc[prefix.index],prefix)
 def test_ichimoku_visible_cloud_is_shifted_forward(self):
  frame=self.frame();d=indicators(frame);t=200
  expected=(frame.High.iloc[t-26-51:t-26+1].max()+frame.Low.iloc[t-26-51:t-26+1].min())/2
  self.assertAlmostEqual(d.cloud_b.iloc[t],expected)
 def test_pivots_not_visible_until_confirmation(self):
  f=pd.DataFrame({'High':[1,2,5,3,2,1],'Low':[0,1,2,1,0,-1]})
  d=confirmed_structure(f)
  self.assertTrue(pd.isna(d.confirmed_high.iloc[3]));self.assertEqual(d.confirmed_high.iloc[4],5)
 def test_wilder_uses_sma_seed(self):
  r=wilder(pd.Series([1.,2.,3.,4.]),3)
  self.assertTrue(pd.isna(r.iloc[1]));self.assertEqual(r.iloc[2],2);self.assertAlmostEqual(r.iloc[3],8/3)
 def test_supertrend_constant_range_is_initially_bearish(self):
  f=pd.DataFrame({'High':[101.]*30,'Low':[99.]*30,'Close':[100.]*30})
  direction,line=supertrend(f,10,3)
  self.assertTrue((direction.iloc[9:]==-1).all());self.assertAlmostEqual(line.iloc[-1],106)
 def prepared(self):
  r={k:np.array(v,dtype=float) for k,v in {'Open':[100,100,100,100],'High':[101,101,101,101],'Low':[99,99,99,99],'Close':[100,100,100,100],'Volume':[1e6]*4,'atr':[2]*4,'turnover':[1e9]*4}.items()}
  r['out_x']=np.array([False]*4)
  return {'days':['2025-01-01','2025-01-02','2025-01-03','2025-01-06'],'risk_on':np.array([True]*4),'data':{'A':r},'ranked':{'x':[['A'],[],[],[]]},'sectors':{'A':'S'}}
 def test_next_open_entry_and_two_sided_costs(self):
  p=self.prepared();r=simulate(p,'x',1,'any',p['days'][1],p['days'][1]);t=r['trade_log'][0]
  self.assertEqual(t['signal_date'],'2025-01-01');self.assertEqual(t['entry_date'],t['exit_date']);self.assertLess(t['pnl'],0)
  expected=t['qty']*(t['exit_price']*(1-.0005)-t['entry_price']*(1+.0005))
  self.assertAlmostEqual(t['pnl'],expected,places=2);self.assertLessEqual(t['qty']*t['entry_price'],20000)
 def test_signal_exit_uses_next_open_not_previous_close(self):
  p=self.prepared();p['data']['A']['out_x'][1]=True;p['data']['A']['Open'][2]=99
  r=simulate(p,'x',20,'any',p['days'][1],p['days'][-1]);t=r['trade_log'][0]
  self.assertEqual(t['exit_date'],'2025-01-03');self.assertEqual(t['reason'],'indicator exit');self.assertAlmostEqual(t['exit_price'],99*(1-.0005),places=4)
 def test_overnight_gap_stop_fills_worse_open(self):
  p=self.prepared();p['data']['A']['Open'][2]=90;p['data']['A']['Low'][2]=89
  t=simulate(p,'x',20,'any',p['days'][1],p['days'][-1])['trade_log'][0]
  self.assertEqual(t['reason'],'gap stop');self.assertLess(t['exit_price'],t['stop'])
 def test_market_gate_and_entry_gap(self):
  p=self.prepared();p['risk_on'][:]=False
  self.assertEqual(simulate(p,'x',1,'nifty_above_200',p['days'][1],p['days'][-1])['closed_trades'],0)
  p['data']['A']['Open'][1]=110
  self.assertEqual(simulate(p,'x',1,'any',p['days'][1],p['days'][-1])['closed_trades'],0)
 def test_selector_cannot_use_recent_returns(self):
  good={'return_pct':5,'annualized_return_pct':5,'max_eod_drawdown_pct':5,'closed_trades':40,'missing_position_bars':0}
  results={'A':{'earlier':good,'middle':good,'recent':dict(good,return_pct=-99)},'B':{'earlier':dict(good,return_pct=-1),'middle':good,'recent':dict(good,return_pct=999)}}
  self.assertEqual(select_past(results,['earlier','middle']),'A')
if __name__=='__main__':unittest.main()
