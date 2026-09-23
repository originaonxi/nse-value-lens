"""Fetch official daily Nifty futures records; retain lot sizes and source dates."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import io,json,zipfile
import pandas as pd
import requests
ROOT=Path(__file__).resolve().parent
CACHE=ROOT/".cache/derivatives"
def fetch(day):
    path=CACHE/(day+".csv")
    if path.exists():return pd.read_csv(path)
    stamp=day.replace("-","")
    url=f"https://archives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{stamp}_F_0000.csv.zip"
    r=requests.get(url,timeout=20);r.raise_for_status()
    z=zipfile.ZipFile(io.BytesIO(r.content))
    d=pd.read_csv(z.open(next(n for n in z.namelist() if n.endswith(".csv"))))
    f=d[(d.TckrSymb=="NIFTY")&(d.FinInstrmTp=="IDF")].copy()
    if f.empty:raise ValueError("No Nifty futures")
    if not all(pd.to_datetime(f.TradDt).dt.strftime("%Y-%m-%d")==day):raise ValueError("Trade date mismatch")
    f.to_csv(path,index=False)
    return f
if __name__=="__main__":
    CACHE.mkdir(parents=True,exist_ok=True)
    d=pd.read_csv(ROOT/".cache/swing/NSEI.csv",index_col=0,parse_dates=True)
    days=[str(x.date()) for x in d.index[-504:]]
    rows=[];failures={}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(fetch,day):day for day in days}
        for f in as_completed(futures):
            day=futures[f]
            try: rows.append(f.result())
            except Exception as e:failures[day]=str(e)[:130]
            if (len(rows)+len(failures))%50==0:print("Futures archives",len(rows),"failed",len(failures),flush=True)
    pd.concat(rows).to_csv(CACHE/"nifty_futures.csv",index=False)
    (CACHE/"audit.json").write_text(json.dumps({"requested":len(days),"downloaded":len(rows),"failures":failures}))
    print("Futures data saved",flush=True)

