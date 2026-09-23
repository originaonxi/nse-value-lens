from pathlib import Path
import sys,json,math
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import pandas as pd
from swing_engine import features
from swing_research import clean
from expanded_research import metrics
FOLDER=Path(__file__).resolve().parent;PLAN=json.loads((FOLDER/'plan.json').read_text())
s=features(clean(pd.read_csv(ROOT/'.cache/swing/NSEI.csv',index_col=0,parse_dates=True)))
priorhigh=s.High.shift().rolling(20).max();priorlow=s.Low.shift().rolling(20).min()
long=(s.Low<priorlow)&(s.Close>priorlow);short=(s.High>priorhigh)&(s.Close<priorhigh)
s['failed_breakout']=long.astype(int)-short.astype(int)
span=s.High-s.Low;nr7=span<span.shift().rolling(6).min()
inside=(s.High<s.High.shift())&(s.Low>s.Low.shift())
for key,condition in [('nr7_confirmation',nr7),('inside_confirmation',inside)]:
 s[key]=((condition.shift(fill_value=False))&(s.Close>s.High.shift())).astype(int)-((condition.shift(fill_value=False))&(s.Close<s.Low.shift())).astype(int)
raw=pd.read_csv(ROOT/'.cache/derivatives/nifty_futures.csv');raw['day']=pd.to_datetime(raw.TradDt).dt.normalize();raw['expiry']=pd.to_datetime(raw.FininstrmActlXpryDt).dt.normalize();raw=raw.drop_duplicates(['day','FinInstrmId'])
byday={day:g.set_index('FinInstrmId') for day,g in raw.groupby('day')};days=list(s.index)
def simulate(mode,start,end,scale=1):
 cash=capital=2000000.;p=None;trades=[];curve=[];fee=.0005*scale;slip=.0002*scale;missing=0
 active=[i for i,day in enumerate(days) if i>0 and start<=str(day.date())<=end]
 for i in active:
  day=days[i];today=byday.get(day);prior=byday.get(days[i-1]);signal=s.iloc[i-1]
  if p is None and int(signal[mode])!=0 and today is not None and prior is not None:
   eligible=prior[(prior.expiry>day+pd.Timedelta(days=3))&(prior.TtlTradgVol>100)].sort_values('TtlTradgVol',ascending=False)
   if len(eligible):
    contract=eligible.index[0]
    if contract in today.index:
     b=today.loc[contract];side=int(signal[mode]);atr=float(signal.atr);op=float(b.OpnPric);lot=int(b.NewBrdLotQty)
     if lot>0 and b.TtlTradgVol>0 and abs(op-float(prior.loc[contract].ClsPric))<=atr:
      entry=op*(1+side*slip);lots=math.floor(cash/(lot*entry*(1+fee)));qty=lot*lots
      if qty>0:
       reserved=qty*entry*(1+fee);cash-=reserved;p={'contract':int(contract),'expiry':b.expiry,'qty':qty,'lot':lot,'entry':entry,'stop':entry-side*atr,'side':side,'reserved':reserved,'age':0,'mark':entry,'signal_date':str(days[i-1].date()),'entry_date':str(day.date())}
  if p:
   p['age']+=1
   if today is None or p['contract'] not in today.index:missing+=1
   else:
    b=today.loc[p['contract']];p['mark']=float(b.ClsPric)
    stop=b.LwPric<=p['stop'] if p['side']==1 else b.HghPric>=p['stop']
    timed=p['age']>=5 or (p['expiry']-day).days<=3 or i==active[-1]
    if stop or timed:
     raw_exit=(min(float(b.OpnPric),p['stop']) if p['side']==1 else max(float(b.OpnPric),p['stop'])) if stop else float(b.ClsPric)
     exit_price=raw_exit*(1-p['side']*slip);pnl=p['qty']*(p['side']*(exit_price-p['entry'])-fee*(p['entry']+exit_price));cash+=p['reserved']+pnl
     trades.append({'contract':p['contract'],'expiry':str(p['expiry'].date()),'signal_date':p['signal_date'],'entry_date':p['entry_date'],'exit_date':str(day.date()),'side':'LONG' if p['side']==1 else 'SHORT','qty':p['qty'],'entry_price':p['entry'],'exit_price':exit_price,'pnl':round(pnl,2),'reason':'stop' if stop else 'time/expiry/window end','sessions':p['age']});p=None
  curve.append({'date':str(day.date()),'equity':cash+(p['qty']*(p['entry']+p['side']*(p['mark']-p['entry'])) if p else 0)})
 r=metrics(curve,trades,capital);r['missing_bars']=missing;r['win_rate_pct']=round(100*sum(t['pnl']>0 for t in trades)/len(trades),2) if trades else None;return r
if __name__=='__main__':
 out={'as_of':str(days[-1].date()),'validated':False,'plan':PLAN,'results':{}}
 for mode in PLAN['rules']:
  out['results'][mode]={}
  for window,(start,end) in PLAN['windows'].items():
   for suffix,scale in [('',1),('_stress',2)]:out['results'][mode][window+suffix]=simulate(mode,start,end,scale)
  print(mode,{w:{k:r[k] for k in ['return_pct','closed_trades','profit_factor','win_rate_pct','max_eod_drawdown_pct','missing_bars']} for w,r in out['results'][mode].items()},flush=True)
 (ROOT/'artifacts/social_nifty').mkdir(parents=True,exist_ok=True)
 (ROOT/'artifacts/social_nifty/results.json').write_text(json.dumps(out,allow_nan=False,separators=(',',':')))
