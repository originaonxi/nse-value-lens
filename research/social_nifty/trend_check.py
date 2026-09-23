from pathlib import Path
import sys,json,math
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import pandas as pd
from indicator_research import indicators
from swing_research import clean
from expanded_research import metrics
FOLDER=Path(__file__).resolve().parent;PLAN=json.loads((FOLDER/'trend_plan.json').read_text())
s=indicators(clean(pd.read_csv(ROOT/'.cache/swing/NSEI.csv',index_col=0,parse_dates=True)));s['sma5']=s.Close.rolling(5).mean();s['sma50']=s.Close.rolling(50).mean()
raw=pd.read_csv(ROOT/'.cache/derivatives/nifty_futures.csv');raw['day']=pd.to_datetime(raw.TradDt).dt.normalize();raw['expiry']=pd.to_datetime(raw.FininstrmActlXpryDt).dt.normalize();raw=raw.drop_duplicates(['day','FinInstrmId'])
byday={day:g.set_index('FinInstrmId') for day,g in raw.groupby('day')};days=list(s.index)
def simulate(mode,start,end,scale=1):
 cash=capital=2000000.;p=None;trades=[];curve=[];fee=.0005*scale;slip=.0002*scale;missing=0
 active=[i for i,day in enumerate(days) if i>0 and start<=str(day.date())<=end]
 for i in active:
  day=days[i];today=byday.get(day);prior=byday.get(days[i-1]);signal=s.iloc[i-1]
  enter=signal.sma5>signal.sma50 if mode=='sma5_50' else bool(signal.in_rsi2)
  exit_signal=signal.sma5<signal.sma50 if mode=='sma5_50' else bool(signal.out_rsi2);hold=20 if mode=='sma5_50' else 5
  if p is None and enter and today is not None and prior is not None:
   eligible=prior[(prior.expiry>day+pd.Timedelta(days=3))&(prior.TtlTradgVol>100)].sort_values('TtlTradgVol',ascending=False)
   if len(eligible):
    contract=eligible.index[0]
    if contract in today.index:
     b=today.loc[contract];atr=float(signal.atr);op=float(b.OpnPric);lot=int(b.NewBrdLotQty)
     if lot>0 and b.TtlTradgVol>0 and abs(op-float(prior.loc[contract].ClsPric))<=atr:
      entry=op*(1+slip);qty=lot*math.floor(cash/(lot*entry*(1+fee)))
      if qty>0:
       reserved=qty*entry*(1+fee);cash-=reserved;p={'contract':int(contract),'expiry':b.expiry,'qty':qty,'entry':entry,'stop':entry-2*atr,'reserved':reserved,'age':0,'mark':entry,'signal_date':str(days[i-1].date()),'entry_date':str(day.date()),'entry_i':i}
  if p:
   p['age']+=1
   if today is None or p['contract'] not in today.index:missing+=1
   else:
    b=today.loc[p['contract']];p['mark']=float(b.ClsPric);reason=None;op=float(b.OpnPric)
    if op<=p['stop']:raw_exit=op;reason='gap stop'
    elif p['entry_i']<i and exit_signal:raw_exit=op;reason='signal exit'
    elif b.LwPric<=p['stop']:raw_exit=p['stop'];reason='stop'
    elif p['age']>=hold or (p['expiry']-day).days<=3 or i==active[-1]:raw_exit=float(b.ClsPric);reason='time/expiry/window end'
    if reason:
     exit_price=raw_exit*(1-slip);pnl=p['qty']*((exit_price-p['entry'])-fee*(p['entry']+exit_price));cash+=p['reserved']+pnl
     trades.append({'contract':p['contract'],'expiry':str(p['expiry'].date()),'signal_date':p['signal_date'],'entry_date':p['entry_date'],'exit_date':str(day.date()),'side':'LONG','qty':p['qty'],'entry_price':p['entry'],'exit_price':exit_price,'pnl':pnl,'reason':reason,'sessions':p['age']});p=None
  curve.append({'date':str(day.date()),'equity':cash+(p['qty']*p['mark'] if p else 0)})
 r=metrics(curve,trades,capital);r['missing_bars']=missing;r['win_rate_pct']=round(100*sum(t['pnl']>0 for t in trades)/len(trades),2) if trades else None
 assert abs(curve[-1]['equity']-capital-sum(t['pnl'] for t in trades))<1e-5
 return r
if __name__=='__main__':
 out={'as_of':str(days[-1].date()),'validated':False,'plan':PLAN,'results':{}}
 for mode in PLAN['rules']:
  out['results'][mode]={}
  for window,(start,end) in PLAN['windows'].items():
   for suffix,scale in [('',1),('_stress',2)]:out['results'][mode][window+suffix]=simulate(mode,start,end,scale)
  print(mode,{w:{k:r[k] for k in ['return_pct','closed_trades','profit_factor','win_rate_pct','max_eod_drawdown_pct','missing_bars']} for w,r in out['results'][mode].items()},flush=True)
 (ROOT/'artifacts/social_nifty').mkdir(parents=True,exist_ok=True)
 (ROOT/'artifacts/social_nifty/trend_results.json').write_text(json.dumps(out,allow_nan=False,separators=(',',':')))
