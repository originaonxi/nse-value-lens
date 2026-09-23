"""Causal daily indicator definitions and a shared funded portfolio simulator."""
from pathlib import Path
import gzip, hashlib, json, math
import numpy as np
import pandas as pd
from swing_research import clean, publish
from expanded_research import metrics
ROOT=Path(__file__).resolve().parent
PLAN=json.loads((ROOT/'docs/INDICATOR_RESEARCH_PLAN.json').read_text(encoding='utf-8'))

def wilder(series,n):
    values=series.to_numpy(dtype=float);out=np.full(len(values),np.nan);seed=[];previous=np.nan
    for i,value in enumerate(values):
        if not np.isfinite(value):continue
        if not np.isfinite(previous):
            seed.append(value)
            if len(seed)<n:continue
            previous=float(np.mean(seed[-n:]))
        else:previous=(previous*(n-1)+value)/n
        out[i]=previous
    return pd.Series(out,index=series.index)

def supertrend(frame,n,multiplier):
    h,l,c=[frame[k] for k in ['High','Low','Close']]
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    atr=wilder(tr,n).to_numpy();middle=((h+l)/2).to_numpy();close=c.to_numpy()
    upper=np.full(len(c),np.nan);lower=upper.copy();line=upper.copy();direction=np.zeros(len(c),dtype=int)
    for i in range(len(c)):
        if not np.isfinite(atr[i]):continue
        bu,bl=middle[i]+multiplier*atr[i],middle[i]-multiplier*atr[i]
        if i==0 or not np.isfinite(upper[i-1]):upper[i],lower[i],direction[i]=bu,bl,-1
        else:
            upper[i]=bu if bu<upper[i-1] or close[i-1]>upper[i-1] else upper[i-1]
            lower[i]=bl if bl>lower[i-1] or close[i-1]<lower[i-1] else lower[i-1]
            direction[i]=(1 if close[i]>upper[i] else -1) if direction[i-1]==-1 else (-1 if close[i]<lower[i] else 1)
        line[i]=lower[i] if direction[i]==1 else upper[i]
    return pd.Series(direction,index=c.index),pd.Series(line,index=c.index)

def confirmed_structure(frame,width=2):
    h,l=frame.High.to_numpy(),frame.Low.to_numpy();highs=[];lows=[];rows=[]
    for t in range(len(frame)):
        pivot=t-width
        if pivot>=width:
            neighbors=np.r_[h[pivot-width:pivot],h[pivot+1:t+1]]
            if h[pivot]>neighbors.max():highs.append(float(h[pivot]))
            neighbors=np.r_[l[pivot-width:pivot],l[pivot+1:t+1]]
            if l[pivot]<neighbors.min():lows.append(float(l[pivot]))
        rising=len(highs)>=2 and len(lows)>=2 and highs[-1]>highs[-2] and lows[-1]>lows[-2]
        rows.append((highs[-1] if highs else np.nan,lows[-1] if lows else np.nan,rising))
    return pd.DataFrame(rows,index=frame.index,columns=['confirmed_high','confirmed_low','rising_structure'])

def cross(a,b):
    if np.isscalar(b):return (a>b)&(a.shift()<=b)
    return (a>b)&(a.shift()<=b.shift())

def indicators(frame):
    d=frame.copy();c,h,l,v=[d[k] for k in ['Close','High','Low','Volume']]
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    d['atr']=wilder(tr,14);d['turnover']=(c*v).rolling(20).mean();d['sma200']=c.rolling(200).mean()
    signals={};exits={}
    for key,n,m in [('st_7_2',7,2),('st_10_3',10,3),('st_14_3',14,3)]:
        direction,line=supertrend(d,n,m);d[key+'_line']=line
        signals[key]=(direction==1)&(direction.shift()==-1);exits[key]=direction==-1
        if key=='st_10_3':signals['st_state']=direction==1;exits['st_state']=direction==-1
    pivots=confirmed_structure(d);d=d.join(pivots)
    signals['hhhl']=d.rising_structure & cross(c,d.confirmed_high);exits['hhhl']=c<d.confirmed_low
    midpoint=lambda n:(h.rolling(n).max()+l.rolling(n).min())/2
    tenkan,kijun=midpoint(9),midpoint(26)
    d['cloud_a']=((tenkan+kijun)/2).shift(26);d['cloud_b']=midpoint(52).shift(26)
    top=d[['cloud_a','cloud_b']].max(axis=1,skipna=False);bottom=d[['cloud_a','cloud_b']].min(axis=1,skipna=False)
    signals['ichi_cloud']=cross(c,top)&(tenkan>kijun);exits['ichi_cloud']=c<bottom
    signals['ichi_tk']=cross(tenkan,kijun)&(c>top);exits['ichi_tk']=tenkan<kijun
    for n,low_n in [(20,10),(55,20)]:
        signals['donchian'+str(n)]=c>h.shift().rolling(n).max();exits['donchian'+str(n)]=c<l.shift().rolling(low_n).min()
    ema=lambda n:c.ewm(span=n,adjust=False,min_periods=n).mean()
    for a,b in [(9,21),(20,50)]:
        fast,slow=ema(a),ema(b);key=f'ema{a}_{b}';signals[key]=cross(fast,slow);exits[key]=fast<slow
    macd=ema(12)-ema(26);macd_signal=macd.ewm(span=9,adjust=False,min_periods=9).mean()
    signals['macd']=cross(macd,macd_signal);exits['macd']=macd<macd_signal
    up=h.diff();down=-l.diff()
    plus=100*wilder(up.where((up>down)&(up>0),0),14)/d.atr
    minus=100*wilder(down.where((down>up)&(down>0),0),14)/d.atr
    dx=100*(plus-minus).abs()/(plus+minus).replace(0,np.nan);adx=wilder(dx,14)
    signals['adx']=cross(plus,minus)&(adx>20);exits['adx']=plus<minus
    for n in [2,14]:
        gains=wilder(c.diff().clip(lower=0),n);loss=wilder((-c.diff()).clip(lower=0),n)
        rsi=100-100/(1+gains/loss.replace(0,np.nan));rsi=rsi.mask((loss==0)&(gains>0),100).mask((loss==0)&(gains==0),50)
        d['rsi'+str(n)]=rsi
    signals['rsi2']=(d.rsi2<10)&(c>d.sma200);exits['rsi2']=d.rsi2>70
    signals['rsi14']=cross(d.rsi14,30);exits['rsi14']=d.rsi14>60
    mid=c.rolling(20).mean();lower=mid-2*c.rolling(20).std(ddof=0)
    signals['bollinger']=cross(c,lower);exits['bollinger']=c>=mid
    upper=ema(20)+2*wilder(tr,20)
    signals['keltner']=cross(c,upper);exits['keltner']=c<ema(20)
    low14=l.rolling(14).min();k=(100*(c-low14)/(h.rolling(14).max()-low14).replace(0,np.nan)).rolling(3).mean();slow=k.rolling(3).mean()
    signals['stochastic']=cross(k,slow)&(k<30);exits['stochastic']=k>80
    for key in signals:d['in_'+key]=signals[key].fillna(False).astype(bool);d['out_'+key]=exits[key].fillna(False).astype(bool)
    return d

def prepare(frames,market,sectors):
    days=market.index;symbols=sorted(frames);data={};ranked={}
    for symbol in symbols:
        d=frames[symbol].reindex(days);data[symbol]={k:d[k].to_numpy() for k in d.columns}
    for family in PLAN['families']:
        key=family['id'];ranked[key]=[]
        for i in range(len(days)):
            available=[]
            for symbol in symbols:
                r=data[symbol];c,atr,turn=r['Close'][i],r['atr'][i],r['turnover'][i]
                if r['in_'+key][i]==True and np.isfinite(atr) and c>=50 and turn>=1e8 and .005<=atr/c<=.06:
                    available.append((symbol,float(turn)))
            ranked[key].append([s for s,t in sorted(available,key=lambda x:(-x[1],x[0]))])
    return {'data':data,'ranked':ranked,'days':[str(x.date()) for x in days],'sectors':sectors,
            'risk_on':(market.Close>market.Close.rolling(200).mean()).to_numpy()}

def simulate(prepared,key,hold,regime,start,end,scale=1):
    data=prepared['data'];days=prepared['days'];sectors=prepared['sectors'];capital=cash=100000.;positions={};trades=[];curve=[];missing=0
    fee=(.0005 if hold==1 else .0015)*scale;slip=.0005*scale
    active=[i for i,d in enumerate(days) if start<=d<=end and i>0]
    for i in active:
        equity=cash+sum(p['qty']*p['mark'] for p in positions.values())
        # Enter before processing today's exits: no recycling money from a later close.
        if regime=='any' or prepared['risk_on'][i-1]:
            for symbol in prepared['ranked'][key][i-1]:
                if len(positions)>=5:break
                sector=sectors.get(symbol,'Unknown')
                if symbol in positions or sum(p['sector']==sector for p in positions.values())>=2:continue
                r=data[symbol];op=r['Open'][i];atr=float(r['atr'][i-1]);prior=float(r['Close'][i-1])
                if not np.isfinite(op) or r['Volume'][i]<=0 or abs(op-prior)>atr:continue
                entry=float(op)*(1+slip);stop=entry-2*atr
                if stop<=0:continue
                qty=math.floor(min(equity*.005/(entry-stop+entry*fee+stop*(fee+slip)),equity*.2/(entry*(1+fee)),cash/(entry*(1+fee))))
                if qty<=0:continue
                cost=qty*entry*(1+fee);cash-=cost
                positions[symbol]={'qty':qty,'entry':entry,'cost':cost,'stop':stop,'age':0,'mark':entry,'entry_date':days[i],'signal_date':days[i-1],'sector':sector,'entry_index':i}
        for symbol,p in list(positions.items()):
            p['age']+=1;r=data[symbol];op,high,low,close=[r[k][i] for k in ['Open','High','Low','Close']]
            if not all(np.isfinite(x) for x in [op,high,low,close]):missing+=1;continue
            p['mark']=float(close);reason=None
            if op<=p['stop']:raw=float(op);reason='gap stop'
            elif p['entry_index']<i and r['out_'+key][i-1]==True:raw=float(op);reason='indicator exit'
            elif low<=p['stop']:raw=p['stop'];reason='stop'
            elif p['age']>=hold:raw=float(close);reason='holding limit'
            elif i==active[-1]:raw=float(close);reason='window end'
            if reason:
                price=raw*(1-slip);proceeds=p['qty']*price*(1-fee);cash+=proceeds
                trades.append({'symbol':symbol,'side':'LONG','signal_date':p['signal_date'],'entry_date':p['entry_date'],'exit_date':days[i],
                    'entry_price':round(p['entry'],4),'exit_price':round(price,4),'stop':round(p['stop'],4),'qty':p['qty'],
                    'pnl':round(proceeds-p['cost'],2),'net_return_pct':round(100*(proceeds/p['cost']-1),3),'sessions':p['age'],'reason':reason})
                del positions[symbol]
        curve.append({'date':days[i],'equity':round(cash+sum(p['qty']*p['mark'] for p in positions.values()),4)})
    if positions and curve:curve[-1]['equity']=round(cash+sum(p['qty']*p['mark']*(1-fee-slip) for p in positions.values()),4)
    result=metrics(curve,trades,capital);wins=sum(t['pnl']>0 for t in trades)
    result.update(start=start,end=end,missing_position_bars=missing,open_positions=len(positions),win_rate_pct=round(100*wins/len(trades),2) if trades else None,
                  annualized_return_pct=round(100*((curve[-1]['equity']/capital)**(252/len(curve))-1),2) if curve else 0)
    return result

def select_past(results,windows):
    choices=[]
    for key,r in results.items():
        if all(r[w]['return_pct']>0 and r[w]['closed_trades']>=30 and not r[w]['missing_position_bars'] for w in windows):
            score=min(r[w]['annualized_return_pct']/max(r[w]['max_eod_drawdown_pct'],5) for w in windows)
            choices.append((-score,key))
    return sorted(choices)[0][1] if choices else None

def compact(r):return {k:v for k,v in r.items() if k not in ['trade_log','curve']}

def enrich_report(report,full_results):
    ranking=[];always=[]
    for key,item in report['results'].items():
        periods=item['periods']
        eligible=all(periods[w]['return_pct']>0 and periods[w]['closed_trades']>=30 and not periods[w]['missing_position_bars'] for w in ['earlier','middle'])
        score=min(periods[w]['annualized_return_pct']/max(periods[w]['max_eod_drawdown_pct'],5) for w in ['earlier','middle'])
        trades=[t for w in ['earlier','middle','recent'] for t in full_results[key][w]['trade_log']]
        wins=sum(t['pnl']>0 for t in trades);losses=sum(t['pnl']<0 for t in trades)
        item['evidence_score']=round(score,5);item['past_eligible']=eligible
        item['all_base_trades']={'count':len(trades),'wins':wins,'losses':losses,'flat':len(trades)-wins-losses,'win_rate_pct':round(100*wins/len(trades),2) if trades else None}
        if len(trades)>=30 and wins==len(trades):always.append(key)
        ranking.append((not eligible,-score,key))
    report['ranking']=[key for _,_,key in sorted(ranking)]
    report['top_100']=report['ranking'][:100]
    report['historical_100pct_winners_min30']=always
    report['fundamentals_audit']={'status':'NOT_BACKTESTED_POINT_IN_TIME_HISTORY_MISSING','reviewed':['data/pre_analyzed.json','screen_output/stock_profiles.json','screen_output/universe_snapshots.json'],
        'note':'Available fundamentals are manual/current company snapshots without per-value historical publication times. They cannot be applied to historical setup dates without look-ahead bias. No fundamental strategy return is claimed.'}
    return report

def main():
    market=clean(pd.read_csv(ROOT/'.cache/swing/NSEI.csv',index_col=0,parse_dates=True))
    meta=pd.read_csv(ROOT/'nifty200.csv');sectors=meta.set_index('Symbol').Industry.to_dict();universe=set(meta.Symbol)
    frames={}
    for p in sorted((ROOT/'.cache/swing').glob('*.NS.csv')):
        symbol=p.name[:-7]
        if symbol in universe:frames[symbol]=indicators(clean(pd.read_csv(p,index_col=0,parse_dates=True)).loc[:market.index[-1]])
    if len(frames)<.9*len(universe):raise RuntimeError('Insufficient universe coverage')
    prepared=prepare(frames,market,sectors);windows=PLAN['windows']
    if str(market.index[-1].date())!=windows['recent'][1]:raise RuntimeError('Snapshot differs from fixed research windows; create an explicit new plan')
    configs={f"{f['id']}_h{h}_{r}":dict(f,hold=h,regime=r) for f in PLAN['families'] for h in PLAN['holds'] for r in PLAN['regimes']}
    results={};print('Prepared',len(frames),'stocks;',len(configs),'configurations',flush=True)
    for n,(key,cfg) in enumerate(configs.items(),1):
        results[key]={w:simulate(prepared,cfg['id'],cfg['hold'],cfg['regime'],*windows[w]) for w in ['earlier','middle']}
        if n%24==0:print('Past windows',n,'/',len(configs),flush=True)
    selection={'middle':select_past(results,['earlier']),'recent':select_past(results,['earlier','middle'])}
    selection_record={'as_of':str(market.index[-1].date()),'selection':selection,'note':'Frozen before recent simulations; retrospective market data already inspected in prior research.'}
    (ROOT/'docs/INDICATOR_SELECTION.json').write_text(json.dumps(selection_record,indent=2),encoding='utf-8')
    print('Selection frozen',selection,flush=True)
    snapshot={};summary={};passes=[]
    for n,(key,cfg) in enumerate(configs.items(),1):
        r=results[key];r['recent']=simulate(prepared,cfg['id'],cfg['hold'],cfg['regime'],*windows['recent'])
        for w in windows:r[w+'_stress']=simulate(prepared,cfg['id'],cfg['hold'],cfg['regime'],*windows[w],scale=2)
        passed=bool(all(r[w]['return_pct']>0 for w in windows) and r['recent_stress']['return_pct']>0 and r['middle_stress']['return_pct']>0 and r['recent']['closed_trades']>=30 and all(r[w]['missing_position_bars']==0 for w in windows))
        if passed:passes.append(key)
        latest=sorted([t for w in windows for t in r[w]['trade_log']],key=lambda t:(t['entry_date'],t['symbol']),reverse=True)[:10]
        summary[key]={'config':cfg,'exploratory_gate_passed':passed,'periods':{w:compact(v) for w,v in r.items()},'latest_trades':latest,'recent_curve':r['recent']['curve']}
        allowed=cfg['regime']=='any' or prepared['risk_on'][-1]
        snapshot[key]=[{'symbol':s,'signal_date':prepared['days'][-1],'close':round(float(prepared['data'][s]['Close'][-1]),2),
            'atr':round(float(prepared['data'][s]['atr'][-1]),4),'entry_low':round(float(prepared['data'][s]['Close'][-1]-prepared['data'][s]['atr'][-1]),2),
            'entry_high':round(float(prepared['data'][s]['Close'][-1]+prepared['data'][s]['atr'][-1]),2)} for s in prepared['ranked'][cfg['id']][-1][:5]] if allowed else []
        if n%24==0:print('Recent and stress',n,'/',len(configs),flush=True)
    spec=hashlib.sha256(json.dumps(PLAN,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    report={'as_of':prepared['days'][-1],'validated':False,'tested_configurations':len(configs),'universe_count':len(frames),'windows':windows,
        'rules':PLAN,'spec_sha256':spec,'selection':selection,'exploratory_candidates':passes,'results':summary,'snapshot':snapshot,
        'benchmark':json.loads((ROOT/'docs/expanded_research.json').read_text())['benchmark'],
        'benchmark_note':'Nifty price-index open-to-close window return, gross, excludes dividends and fees; different exposure from capped stock portfolio.'}
    report=enrich_report(report,results)
    full=gzip.compress(json.dumps({'as_of':report['as_of'],'spec_sha256':spec,'results':results},separators=(',',':'),allow_nan=False).encode(),mtime=0)
    for folder in ['docs','public/data']:(ROOT/folder/'indicator_trades.json.gz').write_bytes(full)
    publish('indicator_research',report)
    print('Exploratory gate passes',len(passes),passes,flush=True)
    if selection['recent']:print('Preselected recent',selection['recent'],compact(results[selection['recent']]['recent']),flush=True)
    leaders=sorted(summary,key=lambda k:summary[k]['periods']['recent']['return_pct'],reverse=True)[:8]
    for key in leaders:print(key,{w:summary[key]['periods'][w]['return_pct'] for w in ['earlier','middle','recent','recent_stress']},flush=True)
if __name__=='__main__':main()
