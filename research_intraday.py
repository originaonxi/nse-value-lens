"""Download minute-data candidates, without backtest optimization."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv, json
import yfinance as yf
ROOT=Path(__file__).resolve().parent
CACHE=ROOT/".cache"/"intraday"
def fetch(symbol):
    d=yf.Ticker(symbol+".NS").history(period="60d",interval="5m",auto_adjust=True,actions=False,timeout=30)
    if d.empty: raise ValueError("No five-minute data")
    d.to_csv(CACHE/(symbol+".csv"))
    opening=d.between_time("09:15","09:15")
    return {"bars":len(d),"sessions":len(opening),"positive_opening_volume":int((opening.Volume>0).sum()),
            "start":str(d.index[0]),"end":str(d.index[-1])}
if __name__=="__main__":
    CACHE.mkdir(parents=True,exist_ok=True)
    symbols=[r["Symbol"] for r in csv.DictReader((ROOT/"nifty200.csv").open(encoding="utf-8-sig"))]
    out={}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(fetch,s):s for s in symbols}
        for f in as_completed(futures):
            s=futures[f]
            try: out[s]=f.result()
            except Exception as e: out[s]={"error":str(e)[:150]}
            if len(out)%25==0: print("Intraday downloaded:",len(out),flush=True)
    (CACHE/"manifest.json").write_text(json.dumps(out,indent=2))
    print("Intraday data audit saved",flush=True)

