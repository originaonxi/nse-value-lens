#!/usr/bin/env python3.12
"""
Full NIFTY 500 systematic screen — runs the whole universe, not a curated list.

Stage 1: download constituents from niftyindices.com
Stage 2: batch OHLCV via yfinance -> technicals (RSI14, MACD, DMAs, returns)
Stage 3: yfinance info for the technical+size pass -> valuation pre-filter
Output:  scratch JSON + ranked candidate table for manual screener.in verification.
"""
import io
import json
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd
import yfinance as yf

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "universe_screen.json")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
CSV_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"


def rsi14(close):
    diff = close.diff()
    gain = diff.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-diff.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-9)
    return float((100 - 100 / (1 + rs)).iloc[-1])


def macd_state(close):
    e12 = close.ewm(span=12, adjust=False).mean()
    e26 = close.ewm(span=26, adjust=False).mean()
    macd = e12 - e26
    sig = macd.ewm(span=9, adjust=False).mean()
    hist = macd - sig
    return round(float(macd.iloc[-1]), 2), round(float(sig.iloc[-1]), 2), round(float(hist.iloc[-1]), 2)


print("Stage 1: universe list...", flush=True)
req = urllib.request.Request(CSV_URL, headers=UA)
csv_text = urllib.request.urlopen(req, timeout=30).read().decode()
uni = pd.read_csv(io.StringIO(csv_text))
symbols = uni["Symbol"].tolist()
industry = dict(zip(uni["Symbol"], uni["Industry"]))
print(f"  {len(symbols)} constituents", flush=True)

print("Stage 2: batch prices (chunks of 50)...", flush=True)
tech = {}
for i in range(0, len(symbols), 50):
    chunk = symbols[i:i + 50]
    try:
        data = yf.download([s + ".NS" for s in chunk], period="1y", auto_adjust=True,
                           progress=False, group_by="ticker", threads=True)
    except Exception as e:
        print(f"  chunk {i}: {e}", flush=True)
        continue
    for s in chunk:
        try:
            df = data[s + ".NS"].dropna()
            close = df["Close"]
            if len(close) < 120:
                continue
            last = float(close.iloc[-1])
            d200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
            d50 = float(close.rolling(50).mean().iloc[-1])
            n = len(close)
            macd, sig, hist = macd_state(close)
            tech[s] = {
                "price": round(last, 1),
                "ret_6m": round((last / float(close.iloc[max(0, n - 126)]) - 1) * 100, 1),
                "ret_12m": round((last / float(close.iloc[0]) - 1) * 100, 1),
                "above_200dma": round((last / d200 - 1) * 100, 1) if d200 else None,
                "dma50_gt_dma200": bool(d200 and d50 > d200),
                "off_52w_high": round((last / float(close.max()) - 1) * 100, 1),
                "rsi14": round(rsi14(close), 1),
                "macd_hist": hist,
                "macd_bull": hist > 0,
            }
        except Exception:
            continue
    print(f"  {min(i+50,len(symbols))}/{len(symbols)} done, {len(tech)} usable", flush=True)
    time.sleep(2)

# Technical pre-filter: not a falling knife, not overbought, liquid enough to have data
pre = {s: t for s, t in tech.items()
       if t["above_200dma"] is not None and t["above_200dma"] > -8
       and t["rsi14"] < 72 and t["off_52w_high"] < -5}
print(f"Stage 3: fundamentals for {len(pre)} technical survivors...", flush=True)

cands = []
for j, (s, t) in enumerate(sorted(pre.items())):
    try:
        info = yf.Ticker(s + ".NS").info
        pe = info.get("trailingPE")
        pb = info.get("priceToBook")
        roe = info.get("returnOnEquity")
        de = info.get("debtToEquity")
        dy = info.get("dividendYield")
        mc = info.get("marketCap")
        epg = info.get("earningsGrowth")
        if not pe or not mc:
            continue
        roe_pct = round(roe * 100, 1) if roe else None
        # Value pre-filter: cheap vs quality
        if pe < 16 and (roe_pct or 0) > 12 and mc > 15e9:
            cands.append({
                "symbol": s, "industry": industry.get(s, ""),
                "pe": round(pe, 1), "pb": round(pb, 2) if pb else None,
                "roe": roe_pct, "de": round(de / 100, 2) if de else None,
                "div_yield": round(dy * 100, 2) if dy and dy < 1 else (round(dy, 2) if dy else None),
                "mcap_cr": round(mc / 1e7),
                "earnings_growth_pct": round(epg * 100, 1) if epg else None,
                **t,
            })
    except Exception:
        pass
    if j % 25 == 0:
        print(f"  {j}/{len(pre)} info-checked, {len(cands)} candidates", flush=True)
        time.sleep(1)

cands.sort(key=lambda c: (c["pe"] or 99))
OUT.write_text(json.dumps({"universe": len(symbols), "tech_ok": len(pre), "candidates": cands}, indent=1))
print(f"\nDONE: {len(cands)} value+trend candidates -> {OUT}", flush=True)
for c in cands[:40]:
    print(f"  {c['symbol']:<14} PE {c['pe']:>5} ROE {c['roe'] or '—':>5} DY {c['div_yield'] or '—':>4} "
          f"6m {c['ret_6m']:>6}% 200dma {c['above_200dma']:>5}% RSI {c['rsi14']:>4} {c['industry'][:24]}", flush=True)
