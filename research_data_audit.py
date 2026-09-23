"""Publish opening-volume coverage; do not invent returns from missing data."""
from pathlib import Path
import json
import pandas as pd
from swing_research import publish
ROOT=Path(__file__).resolve().parent
if __name__=="__main__":
    manifest=json.loads((ROOT/".cache/intraday/manifest.json").read_text())
    usable=[r for r in manifest.values() if "error" not in r]
    total=sum(r["sessions"] for r in usable)
    positive=sum(r["positive_opening_volume"] for r in usable)
    sufficient=sum(r["positive_opening_volume"]>=21 for r in usable)
    market=pd.read_csv(ROOT/".cache/swing/NSEI.csv",index_col=0,parse_dates=True)
    report={"as_of":str(market.index[-1].date()),"orb_status":"BLOCKED_OPENING_VOLUME_QUALITY" if not sufficient else "REQUIRES_EXECUTION_REVIEW",
        "symbols":len(usable),"opening_bars":total,"positive_opening_volume_bars":positive,
        "usable_opening_volume_pct":round(100*positive/total,2) if total else 0,
        "symbols_with_21_positive_openings":sufficient,
        "intraday_note":"The fixed strategy requires 20 prior valid opening-volume observations plus the current opening. Zero-volume opening bars cannot supply those observations. No ORB performance claimed. Only about 60 trading days of history were requested.",
        "options_status":"NOT_BACKTESTED_EXECUTION_DATA_MISSING",
        "options_note":"Official end-of-day option candles are available. Synchronized leg bid/ask, historical margin and intraday execution are not present. No options profitability claim made.",
        "sources":["https://www.alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content","https://www.nseindia.com/all-reports-derivatives"]}
    publish("research_data_audit",report)
    print({k:v for k,v in report.items() if k not in ["sources","intraday_note","options_note"]})
