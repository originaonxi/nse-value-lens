"""Frozen, exploratory minute-bar tests. Run from this folder or repo root."""
from pathlib import Path
from io import BytesIO
from collections import Counter
import hashlib,json,math,sys,zipfile
import numpy as np
import pandas as pd
FOLDER=Path(__file__).resolve().parent
ROOT=FOLDER.parents[2]
sys.path.insert(0,str(ROOT))
from expanded_research import metrics
PLAN=json.loads((FOLDER/'plan.json').read_text())
COLS=['symbol','date','time','Open','High','Low','Close','Volume','extra']

def load():
    path=ROOT/'.cache/social_nifty/spot_futures.zip'
    assert hashlib.md5(path.read_bytes()).hexdigest()==PLAN['md5']
    parts={'NIFTY':[],'NIFTY_F1':[]}
    with zipfile.ZipFile(path) as outer:
        for member in outer.namelist():
            with zipfile.ZipFile(BytesIO(outer.read(member))) as inner:
                for name in inner.namelist():
                    if name.endswith('.csv'):
                        with inner.open(name) as file:
                            d=pd.read_csv(file,header=None,names=COLS)
                        parts[str(d.symbol.iloc[0])].append(d)
    frames={};audit={}
    for key,items in parts.items():
        d=pd.concat(items,ignore_index=True)
        d['timestamp']=pd.to_datetime(d.date+' '+d.time)
        duplicates=int(d.timestamp.duplicated().sum())
        assert not duplicates,'Duplicate bars require investigation'
        normal=d[(d.time>='09:16')&(d.time<='15:30')].copy().sort_values('timestamp')
        normal['day']=normal.timestamp.dt.normalize()
        bad=(normal.High<normal[['Open','Close','Low']].max(axis=1))|(normal.Low>normal[['Open','Close','High']].min(axis=1))|(normal[['Open','High','Low','Close']]<=0).any(axis=1)
        assert not bad.any(),'Invalid OHLC; no silent repair'
        gaps=normal.groupby('day').timestamp.diff().dt.total_seconds()/60
        jump=normal.groupby('day').Close.pct_change().abs()
        audit[key]={'raw_rows':len(d),'normal_rows':len(normal),'days':int(normal.day.nunique()),'outside_session_rows':len(d)-len(normal),'duplicates':duplicates,'invalid_ohlc':int(bad.sum()),'intraday_gaps_over_one_minute':int((gaps>1).sum()),'zero_volume_normal_bars':int((normal.Volume<=0).sum()),'first_date':str(normal.day.min().date()),'last_date':str(normal.day.max().date()),'largest_intraday_close_move_pct':float(jump.max()*100),'largest_move_timestamp':str(normal.loc[jump.idxmax(),'timestamp'])}
        frames[key]=normal
    return frames,audit

def exit_fill(side,stop,target,bar):
    # bar is an OHLC dictionary. A favorable open fills the target limit at its
    # stated price; ambiguous minute ranges always assign the stop first.
    if (side==1 and bar['Open']<=stop) or (side==-1 and bar['Open']>=stop):
        return float(bar['Open']),'gap stop'
    if (side==1 and bar['Open']>=target+.05) or (side==-1 and bar['Open']<=target-.05):
        return target,'target'
    stop_hit=bar['Low']<=stop if side==1 else bar['High']>=stop
    target_hit=bar['High']>=target+.05 if side==1 else bar['Low']<=target-.05
    if stop_hit:return stop,'stop'
    if target_hit:return target,'target'
    return None,None

def build_candidates(frames):
    spot=frames['NIFTY'];future=frames['NIFTY_F1']
    daily=spot.groupby('day').agg(Open=('Open','first'),High=('High','max'),Low=('Low','min'),Close=('Close','last'),first=('time','first'),last=('time','last'))
    pc=daily.Close.shift()
    tr=pd.concat([daily.High-daily.Low,(daily.High-pc).abs(),(daily.Low-pc).abs()],axis=1).max(axis=1)
    daily['prior_atr']=tr.rolling(14).mean().shift()
    daily['prior_close']=pc
    daily['prior_date']=pd.Series(daily.index,index=daily.index).shift()
    sg={day:g.set_index('time') for day,g in spot.groupby('day')}
    fg={day:g.set_index('time') for day,g in future.groupby('day')}
    candidates={k:{} for k in PLAN['rules']};exclusions={k:Counter() for k in PLAN['rules']}
    for day,g in fg.items():
        s=sg.get(day);row=daily.loc[day] if day in daily.index else None
        for mode in PLAN['rules']:
            side=0;signal=None;entry_time=None;stop=None;target=None
            if mode.startswith('gap_fade'):
                if s is None or row is None or not np.isfinite(row.prior_atr) or row.prior_atr<=0 or '09:16' not in s.index or '09:20' not in s.index or row.prior_date not in daily.index or daily.loc[row.prior_date,'last']!='15:30':
                    exclusions[mode]['missing_signal_or_warmup']+=1;continue
                op=float(s.loc['09:16','Open']);close=float(s.loc['09:20','Close']);gap=op/float(row.prior_close)-1
                if abs(gap)<.005:continue
                if mode=='gap_fade_confirmed' and not min(op,row.prior_close)<close<max(op,row.prior_close):continue
                side=-1 if gap>0 else 1;signal='09:20';entry_time='09:22'
                if entry_time not in g.index:exclusions[mode]['missing_entry']+=1;continue
                entry=float(g.loc[entry_time,'Open']);stop=entry-side*.5*row.prior_atr;target=entry+side*row.prior_atr
            else:
                required=[f'09:{m:02d}' for m in range(16,31)]
                if any(t not in g.index for t in required):exclusions[mode]['missing_opening_range']+=1;continue
                opening=g.loc[required];hi=float(opening.High.max());lo=float(opening.Low.min())
                if hi<=lo:continue
                for t,b in g.loc[(g.index>'09:30')&(g.index<='12:00')].iterrows():
                    if b.Close>hi or b.Close<lo:
                        side=1 if b.Close>hi else -1;signal=t
                        entry_time=(day+pd.Timedelta(hours=int(t[:2]),minutes=int(t[3:])+2)).strftime('%H:%M')
                        break
                if not side:continue
                if entry_time not in g.index:exclusions[mode]['missing_entry']+=1;continue
                entry=float(g.loc[entry_time,'Open'])
                if (side==1 and entry<=hi) or (side==-1 and entry>=lo):exclusions[mode]['entry_reentered_range']+=1;continue
                stop=lo if side==1 else hi;target=entry+side*2*abs(entry-stop)
            exit_price=None;exit_time=None;reason=None;held=[]
            for t,b in g.loc[g.index>=entry_time].iterrows():
                held.append(t)
                if t>='15:15':exit_price=float(b.Open);reason='time';exit_time=t;break
                exit_price,reason=exit_fill(side,float(stop),float(target),b)
                if exit_price is not None:exit_time=t;break
            if exit_price is None:
                exclusions[mode]['no_exit_bar']+=1;continue
            begin=pd.Timestamp(str(day.date())+' '+entry_time);end=pd.Timestamp(str(day.date())+' '+exit_time)
            missing=int((end-begin).total_seconds()/60+1-len(held))
            candidates[mode][day]={'date':str(day.date()),'side':side,'signal_label':signal,'entry_label':entry_time,'exit_label':exit_time,'entry_raw':entry,'exit_raw':exit_price,'stop':float(stop),'target':float(target),'reason':reason,'missing_held_minutes':missing,'entry_zero_volume':bool(g.loc[entry_time,'Volume']<=0)}
    return candidates,{k:dict(v) for k,v in exclusions.items()},list(fg)

def simulate(candidates,days,start,end,cost):
    capital=cash=float(PLAN['capital']);fee=cost['fee_per_side'];slip=cost['slippage_per_side'];lot=PLAN['lot_size']
    curve=[];trades=[];size_skipped=0
    for day in days:
        if not start<=str(day.date())<=end:continue
        c=candidates.get(day)
        if c:
            side=c['side'];entry=c['entry_raw']*(1+side*slip);exit_price=c['exit_raw']*(1-side*slip)
            stop_fill=c['stop']*(1-side*slip)
            unit_risk=side*(entry-stop_fill)+fee*(entry+abs(stop_fill))
            assert unit_risk>0
            lots=math.floor(min(cash/(lot*entry*(1+fee)),cash*.005/(lot*unit_risk)))
            if lots<=0:size_skipped+=1
            else:
                qty=lots*lot;gross=qty*side*(c['exit_raw']-c['entry_raw'])
                fees=qty*fee*(entry+exit_price);pnl=qty*side*(exit_price-entry)-fees
                t={**c,'entry_date':c['date'],'exit_date':c['date'],'entry_price':entry,'exit_price':exit_price,'qty':qty,'pnl':pnl,'gross_pnl':gross,'fees':fees,'friction':gross-pnl,'planned_risk_pct':100*qty*unit_risk/cash}
                trades.append(t);cash+=pnl
        curve.append({'date':str(day.date()),'equity':cash})
    result=metrics(curve,trades,capital)
    result.update({'gross_pnl_same_executed_trades':sum(t['gross_pnl'] for t in trades),'total_friction':sum(t['friction'] for t in trades),'win_rate_pct':100*sum(t['pnl']>0 for t in trades)/len(trades) if trades else None,'size_skipped':size_skipped,'trades_with_missing_held_bars':sum(t['missing_held_minutes']>0 for t in trades),'trades_with_zero_entry_volume':sum(t['entry_zero_volume'] for t in trades),'mean_net_rupees_per_trade':sum(t['pnl'] for t in trades)/len(trades) if trades else None})
    assert abs(cash-capital-sum(t['pnl'] for t in trades))<1e-6
    assert all(t['qty']%lot==0 and t['planned_risk_pct']<=.5000001 for t in trades)
    return result

def main():
    frames,audit=load();print('AUDIT',json.dumps(audit),flush=True)
    candidates,exclusions,days=build_candidates(frames)
    out={'validated':False,'plan':PLAN,'audit':audit,'exclusions':exclusions,'results':{}}
    for mode,items in candidates.items():
        out['results'][mode]={}
        for window,(start,end) in PLAN['windows'].items():
            for scenario,cost in PLAN['cost_scenarios'].items():
                result=simulate(items,days,start,end,cost);out['results'][mode][window+'_'+scenario]=result
                print(mode,window,scenario,{k:result[k] for k in ['return_pct','closed_trades','profit_factor','win_rate_pct','max_eod_drawdown_pct','trades_with_missing_held_bars','gross_pnl_same_executed_trades']},flush=True)
    (ROOT/'artifacts/social_nifty/minute').mkdir(parents=True,exist_ok=True)
    (ROOT/'artifacts/social_nifty/minute/results.json').write_text(json.dumps(out,allow_nan=False,separators=(',',':')))
    print('EXCLUSIONS',exclusions)

if __name__=='__main__':main()
