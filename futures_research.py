"""Actual Nifty futures contract experiments. No synthetic options returns."""
from pathlib import Path
import hashlib,json,math
import pandas as pd
from swing_engine import features
from swing_research import clean,publish
from expanded_research import metrics
ROOT=Path(__file__).resolve().parent
def simulate(raw,spot,mode,start,end,scale=1):
    fee,slip=.0005*scale,.0002*scale
    capital=cash=2000000.;pos=None;trades=[];curve=[];missing=0
    byday={d:g.set_index("FinInstrmId") for d,g in raw.groupby("day")}
    days=list(spot.index)
    for i,day in enumerate(days):
        if i==0 or not start<=str(day.date())<=end:continue
        today=byday.get(day);prior=byday.get(days[i-1]);s=spot.iloc[i-1]
        if today is None:
            missing+=1
        elif pos is None and prior is not None and pd.notna(s.sma50) and pd.notna(s.atr):
            eligible=prior[(prior.expiry>day+pd.Timedelta(days=3))&(prior.TtlTradgVol>100)]
            eligible=eligible.sort_values(["TtlTradgVol"],ascending=False)
            if len(eligible):
                contract=eligible.index[0]
                if contract in today.index:
                    bar=today.loc[contract];side=1 if s.Close>s.sma50 else -1
                    lot=int(bar.NewBrdLotQty)
                    entry=float(bar.OpnPric)*(1+side*slip)
                    if lot>0 and entry>0 and bar.TtlTradgVol>0:
                        lots=math.floor(cash/(lot*entry*(1+fee)))
                        if lots>0:
                            qty=lots*lot;reserved=qty*entry*(1+fee);cash-=reserved
                            pos={"contract":int(contract),"expiry":bar.expiry,"side":side,"entry":entry,
                                "stop":entry-side*float(s.atr)*(1 if mode=="futures_intraday" else 2),
                                "qty":qty,"lot_size":lot,"lots":lots,"reserved":reserved,"mark":entry,
                                "age":0,"entry_date":str(day.date()),"signal_date":str(days[i-1].date())}
        if pos is not None:
            pos["age"]+=1
            if today is None or pos["contract"] not in today.index:
                missing+=1
            else:
                bar=today.loc[pos["contract"]];pos["mark"]=float(bar.ClsPric)
                stopped=bar.LwPric<=pos["stop"] if pos["side"]==1 else bar.HghPric>=pos["stop"]
                timed=(mode=="futures_intraday" or pos["age"]>=20 or (pos["expiry"]-day).days<=3)
                if stopped or timed:
                    raw_exit=(min(float(bar.OpnPric),pos["stop"]) if pos["side"]==1 else max(float(bar.OpnPric),pos["stop"])) if stopped else float(bar.ClsPric)
                    price=raw_exit*(1-pos["side"]*slip)
                    pnl=pos["qty"]*(pos["side"]*(price-pos["entry"])-fee*(pos["entry"]+price))
                    cash+=pos["reserved"]+pnl
                    trades.append({"symbol":"NIFTY FUT","contract":pos["contract"],"expiry":str(pos["expiry"].date()),
                        "side":"LONG" if pos["side"]==1 else "SHORT","entry_date":pos["entry_date"],
                        "signal_date":pos["signal_date"],"exit_date":str(day.date()),"entry_price":pos["entry"],
                        "exit_price":price,"lots":pos["lots"],"lot_size":pos["lot_size"],"pnl":round(pnl,2),
                        "reason":"stop" if stopped else "time/expiry","sessions":pos["age"]})
                    pos=None
        equity=cash+(pos["qty"]*(pos["entry"]+pos["side"]*(pos["mark"]-pos["entry"])) if pos else 0)
        curve.append({"date":str(day.date()),"equity":equity})
    if pos and curve:curve[-1]["equity"]-=pos["qty"]*pos["mark"]*(fee+slip)
    result=metrics(curve,trades,capital)
    result.update(start=start,end=end,missing_bars=missing,open_positions=int(pos is not None),capital_rs=capital)
    return result
def main():
    raw=pd.read_csv(ROOT/".cache/derivatives/nifty_futures.csv")
    raw["day"]=pd.to_datetime(raw.TradDt).dt.normalize()
    raw["expiry"]=pd.to_datetime(raw.FininstrmActlXpryDt).dt.normalize()
    raw=raw.drop_duplicates(["day","FinInstrmId"])
    spot=features(clean(pd.read_csv(ROOT/".cache/swing/NSEI.csv",index_col=0,parse_dates=True)))
    windows=json.loads((ROOT/"docs/expanded_research.json").read_text())["windows"]
    windows={k:v for k,v in windows.items() if k!="earlier"}
    plan=ROOT/"docs/FUTURES_RESEARCH_PLAN.json"
    report={"as_of":str(spot.index[-1].date()),"validated":False,"windows":windows,
        "rules":json.loads(plan.read_text(encoding="utf-8-sig")),"spec_sha256":hashlib.sha256(json.dumps(json.loads(plan.read_text(encoding="utf-8-sig")),sort_keys=True,separators=(",",":")).encode()).hexdigest(),
        "data_audit":json.loads((ROOT/".cache/derivatives/audit.json").read_text()),"results":{}}
    for mode in ["futures_swing","futures_intraday"]:
        result={w:simulate(raw,spot,mode,*dates) for w,dates in windows.items()}
        result["stress"]=simulate(raw,spot,mode,*windows["recent"],scale=2)
        report["results"][mode]=result
        print(mode,{w:result[w]["return_pct"] for w in list(windows)+["stress"]},
            "losing days",result["recent"]["losing_days"],"missing",result["recent"]["missing_bars"],flush=True)
    publish("futures_research",report)
if __name__=="__main__":main()

