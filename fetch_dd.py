#!/usr/bin/env python3
"""
Fetch 5d / 1m / 52w-high drawdowns for all Nifty 200 symbols
Saves to screen_output/price_dd.json — merged into build_value_dn.py
Price damage metrics (all as negative %):
  drop_5d   = (today - 5d_ago) / 5d_ago * 100   — recent selloff
  drop_1m   = (today - 1m_ago) / 1m_ago * 100  — monthly selloff
  dd_52wh   = (today / 52w_high - 1) * 100      — how far below peak (more negative = more beaten down)
"""
import csv
import json
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

warnings.filterwarnings('ignore')
import yfinance as yf

HERE = Path(__file__).resolve().parent
OUT = HERE / "screen_output"
UNIVERSE = HERE / "nifty200.csv"


def fetch_one(symbol):
    try:
        t = yf.Ticker(symbol + '.NS')
        h = t.history(period='1y', interval='1d', actions=False)
        if h.empty or len(h) < 10:
            return symbol, {}
        closes = h['Close'].dropna()
        today = float(closes.iloc[-1])
        hi52w = float(closes.max())
        # 5d and 1m ago
        def ret(n):
            if len(closes) > n:
                return round((today / float(closes.iloc[-(n+1)]) - 1) * 100, 2)
            return None
        return symbol, {
            'price': round(today, 2),
            'hi52w': round(hi52w, 2),
            'dd_52wh_pct': round((today / hi52w - 1) * 100, 2),   # negative = below peak
            'drop_5d_pct': ret(5),
            'drop_1m_pct': ret(21),
            'drop_2m_pct': ret(42),
            'n_sessions': len(closes),
        }
    except Exception:
        return symbol, {}


def main():
    rows = list(csv.DictReader(open(UNIVERSE, newline='', encoding='utf-8-sig')))
    syms = [r['Symbol'].strip() for r in rows if r.get('Series','EQ').strip()=='EQ']
    print(f"Fetching 1y price history for {len(syms)} symbols...")

    out = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(fetch_one, s): s for s in syms}
        done = 0
        for f in as_completed(futures):
            sym, data = f.result()
            if data:
                out[sym] = data
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(syms)}...", flush=True)

    # Summary stats
    dd_vals = [v['dd_52wh_pct'] for v in out.values() if 'dd_52wh_pct' in v]
    d5 = [v['drop_5d_pct'] for v in out.values() if v.get('drop_5d_pct') is not None]
    d1m = [v['drop_1m_pct'] for v in out.values() if v.get('drop_1m_pct') is not None]
    print(f"\n{len(out)}/{len(syms)} stocks fetched")
    print(f"52w-high drawdown:  min={min(dd_vals):.1f}%  median={sorted(dd_vals)[len(dd_vals)//2]:.1f}%  max={max(dd_vals):.1f}%")
    if d5:  print(f"5d return:          min={min(d5):.1f}%  median={sorted(d5)[len(d5)//2]:.1f}%  max={max(d5):.1f}%")
    if d1m: print(f"1m return:          min={min(d1m):.1f}%  median={sorted(d1m)[len(d1m)//2]:.1f}%  max={max(d1m):.1f}%")

    (OUT / 'price_dd.json').write_text(json.dumps(out, indent=2))
    print(f"\nSaved: screen_output/price_dd.json")
    # Top 10 most-beaten-down
    by_dd = sorted(out.items(), key=lambda x: x[1]['dd_52wh_pct'])
    print("\nTop 10 most beaten-down (52w-high drawdown):")
    for sym, d in by_dd[:10]:
        print(f"  {sym:<15}  dd_52wh={d['dd_52wh_pct']:+.1f}%  5d={d.get('drop_5d_pct','?'):+.1f}%  1m={d.get('drop_1m_pct','?'):+.1f}%")


if __name__ == '__main__':
    main()
