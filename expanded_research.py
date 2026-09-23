"""Fixed expanded experiments. All outputs are exploratory, never validated."""
from pathlib import Path
import hashlib, json, math
from collections import defaultdict
import numpy as np
import pandas as pd
from swing_engine import features
from swing_research import clean, publish

ROOT=Path(__file__).resolve().parent
PLAN=json.loads((ROOT/"docs/EXPANDED_RESEARCH_PLAN.json").read_text(encoding="utf-8-sig"))
CONFIGS={x["id"]:x for x in PLAN["daily_candidates"]}

def load_inputs():
    frames={}
    for p in sorted((ROOT/".cache/swing").glob("*.NS.csv")):
        d=features(clean(pd.read_csv(p,index_col=0,parse_dates=True)))
        for n in [1,5,20,126]: d["ret"+str(n)]=d.Close.pct_change(n)
        d["vol63"]=d.Close.pct_change().rolling(63).std()
        frames[p.name[:-7]]=d
    m=features(clean(pd.read_csv(ROOT/".cache/swing/NSEI.csv",index_col=0,parse_dates=True)))
    meta=pd.read_csv(ROOT/"nifty200.csv").set_index("Symbol")
    sectors=meta.Industry.to_dict()
    by_day=defaultdict(dict)
    for symbol,d in frames.items():
        for day,row in d.iterrows(): by_day[day][symbol]=row
    return frames,m,sectors,by_day

def picks(rows, market, key, sectors):
    """Only previous complete session rows are passed to this selector."""
    candidates=[]
    for symbol,r in rows.items():
        need=[r.Close,r.atr,r.sma50,r.sma200,r.ret126,r.vol63,r.turnover,r.ret1]
        if not all(math.isfinite(float(x)) for x in need): continue
        if not (r.Close>=50 and r.turnover>=1e8 and .005<=r.atr/r.Close<=.06 and r.vol63>0): continue
        side=1
        if key=="rotation_momentum":
            ok=r.Close>r.sma200 and r.ret126>0; rank=r.ret126/r.vol63
        elif key=="rotation_lowvol":
            ok=r.Close>r.sma200 and r.ret63>0; rank=-r.vol63
        elif key=="weekly_reversal":
            ok=market.Close>market.sma50 and r.Close>r.sma200 and r.ret5<0; rank=-r.ret5
        elif key=="intraday_long":
            ok=market.Close>market.sma50 and r.Close>r.sma50>r.sma200 and r.ret20>0; rank=r.ret20
        elif key=="intraday_short":
            ok=market.Close<market.sma50 and r.Close<r.sma50<r.sma200 and r.ret20<0; rank=-r.ret20;side=-1
        elif key=="intraday_reversal":
            ok=abs(r.ret1)>=.03;rank=abs(r.ret1);side=-1 if r.ret1>0 else 1
        else: raise ValueError(key)
        if ok: candidates.append((float(rank),symbol,side,float(r.atr)))
    candidates.sort(key=lambda x:(-x[0],x[1]))
    chosen=[];counts=defaultdict(int)
    for rank,symbol,side,atr in candidates:
        sector=sectors.get(symbol,"Unknown")
        if counts[sector]>=2: continue
        counts[sector]+=1;chosen.append((symbol,side,atr))
        if len(chosen)==5:break
    return chosen

def day_exit(side,entry,stop,target,bar,slip):
    """Conservative stop-first OHLC execution for positions held from the open."""
    if side==1:
        raw=min(float(bar.Open),stop) if bar.Low<=stop else target if target is not None and bar.High>=target else float(bar.Close)
        reason="stop" if bar.Low<=stop else "target" if target is not None and bar.High>=target else "time"
    else:
        raw=max(float(bar.Open),stop) if bar.High>=stop else target if target is not None and bar.Low<=target else float(bar.Close)
        reason="stop" if bar.High>=stop else "target" if target is not None and bar.Low<=target else "time"
    return raw*(1-side*slip),reason

def metrics(curve,trades,capital=100000):
    values=np.array([capital]+[p["equity"] for p in curve],dtype=float)
    daily=values[1:]/values[:-1]-1
    peaks=np.maximum.accumulate(values)
    losing=daily < -1e-10;winning=daily>1e-10
    streak=longest=0
    for loss in losing:
        streak=streak+1 if loss else 0;longest=max(longest,streak)
    months={}
    if curve:
        series=pd.Series(values[1:],index=pd.to_datetime([p["date"] for p in curve]))
        ends=series.groupby(series.index.strftime("%Y-%m")).last()
        prev=capital
        for month,value in ends.items():
            months[month]=round(100*(value/prev-1),2);prev=value
    gains=sum(max(t["pnl"],0) for t in trades);losses=-sum(min(t["pnl"],0) for t in trades)
    return {"return_pct":round(100*(values[-1]/capital-1),2),
        "max_eod_drawdown_pct":round(100*max(1-values/peaks),2),"closed_trades":len(trades),
        "profit_factor":round(gains/losses,3) if losses else None,
        "trading_sessions":len(daily),"profitable_days":int(winning.sum()),"losing_days":int(losing.sum()),
        "flat_days":int((~losing & ~winning).sum()),
        "profitable_day_pct":round(float(winning.mean()*100),2) if len(daily) else None,
        "worst_day_pct":round(float(daily.min()*100),2) if len(daily) else None,
        "longest_losing_streak":longest,"monthly_returns":months,
        "curve":curve,"trade_log":trades}

def simulate(by_day,market,sectors,key,start,end,scale=1):
    intraday=key.startswith("intraday")
    fee=(.0005 if intraday else .0015)*scale;slip=.0005*scale
    hold=CONFIGS[key]["hold"]
    capital=cash=100000.
    positions={};curve=[];trades=[];missing=0
    days=list(market.index)
    active=[(i,d) for i,d in enumerate(days) if start<=str(d.date())<=end and i>0]
    for day_number,(i,day) in enumerate(active):
        today=by_day.get(day,{})
        yesterday=by_day.get(days[i-1],{})
        equity=cash+sum(p["qty"]*p["mark"] for p in positions.values())
        if day_number%hold==0 and not positions:
            for symbol,side,atr in picks(yesterday,market.iloc[i-1],key,sectors):
                bar=today.get(symbol)
                if bar is None or bar.Volume<=0: continue
                # Reserve FULL notional for short exposure: no leverage or reuse of short proceeds.
                entry=float(bar.Open)*(1+side*slip)
                distance=atr*(1 if intraday else 2)
                stop=entry-side*distance
                if stop<=0:continue
                qty=math.floor(min(equity*.005/(distance+entry*(2*fee+slip)),
                                   equity*.2/(entry*(1+fee)),cash/(entry*(1+fee))))
                if qty<1:continue
                reserved=qty*entry*(1+fee)
                cash-=reserved
                positions[symbol]={"entry":entry,"qty":qty,"reserved":reserved,"stop":stop,
                    "side":side,"target":entry+side*1.5*atr if intraday else None,
                    "age":0,"entry_date":str(day.date()),"signal_date":str(days[i-1].date()),"mark":entry}
        for symbol,p in list(positions.items()):
            p["age"]+=1;bar=today.get(symbol)
            if bar is None:
                missing+=1;continue
            if intraday:
                price,reason=day_exit(p["side"],p["entry"],p["stop"],p["target"],bar,slip)
            elif bar.Low<=p["stop"]:
                price=min(float(bar.Open),p["stop"])*(1-slip);reason="stop"
            elif p["age"]>=hold:
                price=float(bar.Close)*(1-slip);reason="time"
            else:
                p["mark"]=float(bar.Close);continue
            pnl=p["qty"]*(p["side"]*(price-p["entry"])-fee*(p["entry"]+price))
            cash+=p["reserved"]+pnl
            trades.append({"symbol":symbol,"side":"LONG" if p["side"]==1 else "SHORT",
                "signal_date":p["signal_date"],"entry_date":p["entry_date"],"exit_date":str(day.date()),
                "entry_price":p["entry"],"exit_price":price,"qty":p["qty"],
                "pnl":round(pnl,2),"reason":reason,"sessions":p["age"]})
            del positions[symbol]
        # All residual positions are swing longs; unspent capital remains cash.
        equity=cash+sum(p["qty"]*p["mark"] for p in positions.values())
        curve.append({"date":str(day.date()),"equity":round(equity,4)})
    if positions and curve:
        curve[-1]["equity"]=round(cash+sum(p["qty"]*p["mark"]*(1-fee-slip) for p in positions.values()),4)
    result=metrics(curve,trades)
    result.update(start=start,end=end,missing_position_bars=missing,open_positions=len(positions))
    return result

def main():
    frames,market,sectors,by_day=load_inputs()
    days=market.index
    windows={"earlier":(str(days[210].date()),str(days[-505].date())),
        "middle":(str(days[-504].date()),str(days[-253].date())),
        "recent":(str(days[-252].date()),str(days[-1].date()))}
    manifest_path=ROOT/"docs/EXPANDED_RESEARCH_PLAN.json"
    out={"as_of":str(days[-1].date()),"validated":False,"spec_sha256":hashlib.sha256(json.dumps(json.loads(manifest_path.read_text(encoding="utf-8-sig")),sort_keys=True,separators=(",",":")).encode()).hexdigest(),
        "tested_configurations":len(CONFIGS),"windows":windows,"rules":PLAN,
        "universe_count":len(frames),"results":{},"exploratory_candidates":[]}
    for key in CONFIGS:
        result={}
        for name,(start,end) in windows.items():
            result[name]=simulate(by_day,market,sectors,key,start,end)
        result["stress"]=simulate(by_day,market,sectors,key,*windows["recent"],scale=2)
        passed=(all(result[w]["return_pct"]>0 for w in windows)
            and result["stress"]["return_pct"]>0 and result["recent"]["closed_trades"]>=30
            and result["recent"]["trading_sessions"]>=252)
        result["exploratory_gate_passed"]=passed
        if passed:out["exploratory_candidates"].append(key)
        out["results"][key]=result
        print(key,{w:result[w]["return_pct"] for w in list(windows)+["stress"]},"candidate",passed,flush=True)
    out["benchmark"]={w:round(100*(market.loc[end].Close/market.loc[start].Open-1),2)
                      for w,(start,end) in windows.items()}
    publish("expanded_research",out)
    print("Expanded experiments published. No live strategy selected.",flush=True)

if __name__=="__main__":main()

