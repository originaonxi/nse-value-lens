"""Fixed equity/gold/cash research, compared with each ETF buy-and-hold."""
from pathlib import Path
import hashlib,json,math
import pandas as pd
from swing_research import clean,publish
from expanded_research import metrics
ROOT=Path(__file__).resolve().parent
def allocation(prior,mode):
    if mode=="dual_momentum":
        valid=[(float(r.ret126),s) for s,r in prior.items() if pd.notna(r.ret126) and r.ret126>0]
        return {max(valid)[1]:1.} if valid else {}
    if mode=="diversified_trend":
        return {s:.5 for s,r in prior.items() if r.Close>r.sma200}
    return {mode:1.}
def simulate(frames,market,mode,start,end,scale=1):
    fee,slip=.0015*scale,.0005*scale
    cash=100000.;positions={};trades=[];curve=[];missing=0
    days=list(market.index);active=[(i,d) for i,d in enumerate(days) if start<=str(d.date())<=end and i>0]
    baseline=mode in frames
    for n,(i,day) in enumerate(active):
        prior={s:d.loc[days[i-1]] for s,d in frames.items() if days[i-1] in d.index}
        today={s:d.loc[day] for s,d in frames.items() if day in d.index}
        equity=cash+sum(p["qty"]*p["mark"] for p in positions.values())
        if (n==0 if baseline else n%20==0) and not positions:
            for symbol,weight in allocation(prior,mode).items():
                if symbol not in today:missing+=1;continue
                entry=float(today[symbol].Open)*(1+slip)
                qty=math.floor(min(cash,equity*weight)/(entry*(1+fee)))
                if qty<=0:continue
                cost=qty*entry*(1+fee);cash-=cost
                positions[symbol]={"qty":qty,"entry":entry,"cost":cost,"date":str(day.date()),"signal_date":str(days[i-1].date()),"age":0,"mark":entry}
        for symbol,p in list(positions.items()):
            p["age"]+=1
            if symbol not in today:missing+=1;continue
            p["mark"]=float(today[symbol].Close)
            if (not baseline and p["age"]>=20) or n==len(active)-1:
                exit_price=float(today[symbol].Close)*(1-slip)
                proceeds=p["qty"]*exit_price*(1-fee);cash+=proceeds
                trades.append({"symbol":symbol,"side":"LONG","signal_date":p["signal_date"],"entry_date":p["date"],
                    "exit_date":str(day.date()),"entry_price":p["entry"],"exit_price":exit_price,
                    "qty":p["qty"],"pnl":round(proceeds-p["cost"],2),"sessions":p["age"],
                    "reason":"window end" if n==len(active)-1 else "20-session exit"})
                del positions[symbol]
        curve.append({"date":str(day.date()),"equity":cash+sum(p["qty"]*p["mark"] for p in positions.values())})
    result=metrics(curve,trades)
    result.update(start=start,end=end,missing_position_bars=missing)
    return result
def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--download",action="store_true")
    args=parser.parse_args()
    if args.download:
        import yfinance as yf
        folder=ROOT/".cache/cross_asset"
        folder.mkdir(parents=True,exist_ok=True)
        for symbol in ["NIFTYBEES","GOLDBEES"]:
            frame=clean(yf.Ticker(symbol+".NS").history(period="5y",auto_adjust=True))
            if len(frame)<1000: raise RuntimeError("Insufficient ETF history: "+symbol)
            frame.to_csv(folder/(symbol+".csv"))
    frames={}
    for symbol in ["NIFTYBEES","GOLDBEES"]:
        d=clean(pd.read_csv(ROOT/".cache/cross_asset"/(symbol+".csv"),index_col=0,parse_dates=True))
        d["ret126"]=d.Close.pct_change(126);d["sma200"]=d.Close.rolling(200).mean();frames[symbol]=d
    market=clean(pd.read_csv(ROOT/".cache/swing/NSEI.csv",index_col=0,parse_dates=True))
    prior=json.loads((ROOT/"docs/expanded_research.json").read_text())
    windows=prior["windows"]
    plan_path=ROOT/"docs/CROSS_ASSET_RESEARCH_PLAN.json"
    out={"as_of":str(market.index[-1].date()),"validated":False,"windows":windows,
        "rules":json.loads(plan_path.read_text(encoding="utf-8-sig")),"spec_sha256":hashlib.sha256(json.dumps(json.loads(plan_path.read_text(encoding="utf-8-sig")),sort_keys=True,separators=(",",":")).encode()).hexdigest(),"results":{}}
    for mode in ["dual_momentum","diversified_trend","NIFTYBEES","GOLDBEES"]:
        r={w:simulate(frames,market,mode,*dates) for w,dates in windows.items()}
        r["stress"]=simulate(frames,market,mode,*windows["recent"],scale=2)
        r["stress_by_window"]={w:simulate(frames,market,mode,*dates,scale=2) for w,dates in windows.items()}
        r["historically_positive"]=bool(all(r[w]["return_pct"]>0 for w in windows) and r["stress"]["return_pct"]>0)
        out["results"][mode]=r
        print(mode,{w:r[w]["return_pct"] for w in list(windows)+["stress"]},
            "losing days",r["recent"]["losing_days"],"of",r["recent"]["trading_sessions"],
            "drawdown",r["recent"]["max_eod_drawdown_pct"],flush=True)
    publish("cross_asset_research",out)
if __name__=="__main__":main()

