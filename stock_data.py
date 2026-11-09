#!/usr/bin/env python3
"""1-hour candles for the top-30 Nifty 50 stocks (by estimated index weight), from Upstox's public API.

Universe   data/nifty50_weights.csv: free-float market cap estimate per Nifty 50 stock (float shares x price),
           top 30 by weight; lot = current NSE F&O lot size.
Candles    Upstox v3 historical candles, 1-hour (09:15-anchored), NSE_EQ|<ISIN> (ISIN from NSE's EQUITY_L.csv).
           Cached in data/stock_1h/<SYMBOL>.csv; each run re-fetches only the last ~3 months plus today.
Splits     Upstox prices are as traded. A step of more than 30% in the ratio between our daily close and the
           adjusted daily history (data/hhhl_prices) is a split / bonus; earlier candles are divided by it.
Check      the last 15 sessions of candles vs NSE's CM bhavcopy (sec_bhavdata_full): open, high, low, last price.
"""
import io
import json
import time
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "data" / "stock_1h"
WEIGHTS = ROOT / "data" / "nifty50_weights.csv"
ISINS = ROOT / "data" / "nse_isin.csv"
DAILY = ROOT / "data" / "hhhl_prices"
BHAV = ROOT / "data" / "bhav_cm"
IST = ZoneInfo("Asia/Kolkata")
API = "https://api.upstox.com/v3/historical-candle/{key}/hours/1/{to}/{frm}"
API_TODAY = "https://api.upstox.com/v3/historical-candle/intraday/{key}/hours/1"
BHAV_URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv"
FIRST = date(2024, 4, 1)
TOP = 30
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://www.nseindia.com/"}


def universe():
    """Top 30 by estimated weight; lot sizes from today's F&O file (docs/fno_ema105.json, from the NSE bhavcopy) when present."""
    rows = pd.read_csv(WEIGHTS).head(TOP).to_dict("records")
    p = ROOT / "docs" / "fno_ema105.json"
    if p.exists():
        lots = {r["symbol"]: r["lot"] for r in json.loads(p.read_text(encoding="utf-8")).get("rows", []) if r.get("lot")}
        for r in rows:
            r["lot"] = int(lots.get(r["symbol"], r["lot"]))
    return rows

def isin_map():
    if not ISINS.exists() or (time.time() - ISINS.stat().st_mtime) > 30 * 86400:
        r = requests.get("https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv", headers=H, timeout=30)
        r.raise_for_status()
        eq = pd.read_csv(io.StringIO(r.text))
        eq.columns = [c.strip() for c in eq.columns]
        eq[["SYMBOL", "ISIN NUMBER"]].rename(columns={"SYMBOL": "symbol", "ISIN NUMBER": "isin"}).to_csv(ISINS, index=False)
    m = pd.read_csv(ISINS)
    return dict(zip(m["symbol"], m["isin"]))


def _get(url):
    for i in range(4):
        try:
            r = requests.get(url, headers={"Accept": "application/json"}, timeout=30)
            if r.status_code == 200:
                return (r.json().get("data") or {}).get("candles") or []
            if r.status_code in (400, 404):
                return []
        except requests.RequestException:
            pass
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"Upstox failed: {url}")


def _frame(c):
    if not c:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    f = pd.DataFrame(c, columns=["t", "Open", "High", "Low", "Close", "Volume", "oi"])
    f.index = pd.to_datetime(f.t).dt.tz_localize(None)
    return f[["Open", "High", "Low", "Close", "Volume"]].astype(float)


def quarters(start, end):
    q = date(start.year, 3 * ((start.month - 1) // 3) + 1, 1)
    while q <= end:
        nxt = date(q.year + (q.month + 2) // 12, (q.month + 2) % 12 + 1, 1)
        yield q, min(nxt - timedelta(days=1), end)
        q = nxt


def fetch(symbol, isin, today=None):
    today = today or datetime.now(IST).date()
    key = urllib.parse.quote(f"NSE_EQ|{isin}", safe="")
    path = CACHE / f"{symbol}.csv"
    have = pd.read_csv(path, index_col=0, parse_dates=True) if path.exists() else pd.DataFrame()
    start = (have.index.max().date() - timedelta(days=95)) if len(have) else FIRST
    parts = [have]
    for a, b in quarters(start, today):
        parts.append(_frame(_get(API.format(key=key, to=b.isoformat(), frm=a.isoformat()))))
        time.sleep(0.25)
    parts.append(_frame(_get(API_TODAY.format(key=key))))
    df = pd.concat([p for p in parts if len(p)])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    now = datetime.now(IST).replace(tzinfo=None)
    length = np.where(df.index.time == pd.Timestamp("15:15").time(), 15, 60)
    df = df[df.index + pd.to_timedelta(length, unit="min") <= now]          # finished candles only
    CACHE.mkdir(parents=True, exist_ok=True)
    df.round(2).to_csv(path)
    return df


def daily_ref(symbol):
    p = DAILY / f"{symbol}.NS.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p)
    d["Date"] = pd.to_datetime(d["Date"].astype(str).str[:10])
    return d.set_index("Date")["Close"].astype(float)


def adjust(df, ref):
    """Divide candles before a split / bonus by its ratio (a >30% step against the adjusted daily close)."""
    if ref is None or df.empty:
        return df, []
    last = df["Close"].groupby(df.index.normalize()).last()
    j = pd.concat([last.rename("ours"), ref.rename("ref")], axis=1, join="inner").dropna()
    if len(j) < 2:
        return df, []
    ratio = (j.ours / j.ref).to_numpy()
    out, events = df.copy(), []
    for k in range(1, len(ratio)):
        step = ratio[k - 1] / ratio[k]
        if step > 1.3 or step < 1 / 1.3:
            day = j.index[k]
            mask = out.index < day
            out.loc[mask, ["Open", "High", "Low", "Close"]] = out.loc[mask, ["Open", "High", "Low", "Close"]] / step
            out.loc[mask, "Volume"] = out.loc[mask, "Volume"] * step
            events.append({"date": str(day.date()), "factor": round(float(step), 3)})
    return out, events


def bhavcopy(day):
    """NSE CM bhavcopy for one session (cached). SYMBOL -> open / high / low / last / close for the EQ series."""
    BHAV.mkdir(parents=True, exist_ok=True)
    p = BHAV / f"{day:%Y-%m-%d}.csv"
    if not p.exists():
        r = requests.get(BHAV_URL.format(d=day), headers=H, timeout=30)
        if r.status_code != 200 or b"SYMBOL" not in r.content[:300]:
            return None
        p.write_bytes(r.content)
    b = pd.read_csv(p, skipinitialspace=True)
    b.columns = [c.strip() for c in b.columns]
    b = b[b["SERIES"].astype(str).str.strip() == "EQ"].copy()
    b["SYMBOL"] = b["SYMBOL"].astype(str).str.strip()
    return b.set_index("SYMBOL")[["OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "LAST_PRICE", "CLOSE_PRICE"]].astype(float)


def bhav_days(sessions, n=15):
    out = {}
    for d in sorted(sessions)[-n:]:
        try:
            b = bhavcopy(d)
        except requests.RequestException:                    # pragma: no cover - network
            b = None
        if b is not None:
            out[d] = b
        time.sleep(0.2)
    return out


def check(symbol, df, bhav):
    """Our candles for each bhavcopy session vs NSE's official open / high / low / last traded price."""
    rows = []
    for d, b in bhav.items():
        if symbol not in b.index:
            continue
        x = df[df.index.normalize() == pd.Timestamp(d)]
        if x.empty:
            continue
        n = b.loc[symbol]
        ours = (x["Open"].iloc[0], x["High"].max(), x["Low"].min(), x["Close"].iloc[-1])
        nse = (n.OPEN_PRICE, n.HIGH_PRICE, n.LOW_PRICE, n.LAST_PRICE)
        rows.append([abs(a / c - 1) * 100 for a, c in zip(ours, nse)])
    if not rows:
        return {"days": 0}
    g = np.array(rows)
    return {"days": len(rows), "max_gap_pct": {k: round(float(v), 3) for k, v in zip(("open", "high", "low", "last"), g.max(axis=0))},
            "days_within_0_1pct": int((g.max(axis=1) <= 0.1).sum()), "last_day": str(max(bhav))}


def load_all(today=None, refresh=True):
    isins = isin_map()
    out, meta, raws = {}, {}, {}
    for u in universe():
        s = u["symbol"]
        path = CACHE / f"{s}.csv"
        try:
            raw = fetch(s, isins[s], today) if refresh else pd.read_csv(path, index_col=0, parse_dates=True)
            note = "refreshed" if refresh else "cache"
        except Exception as e:                                  # pragma: no cover - network
            raw = pd.read_csv(path, index_col=0, parse_dates=True) if path.exists() else pd.DataFrame()
            note = f"cache (refresh failed: {type(e).__name__})"
        raws[s] = (raw, note, u)
    sessions = sorted({d.date() for raw, _, _ in raws.values() for d in raw.index.normalize()})
    bhav = bhav_days(sessions)
    for s, (raw, note, u) in raws.items():
        if raw.empty:
            meta[s] = {"error": "no candles"}
            continue
        adj, events = adjust(raw, daily_ref(s))
        out[s] = adj
        meta[s] = {"candles": int(len(adj)), "from": str(adj.index[0])[:16], "to": str(adj.index[-1])[:16], "source": note,
                   "splits": events, "check": check(s, raw, bhav), "lot": int(u["lot"]), "weight_pct": float(u["weight_pct"]),
                   "isin": isins[s]}
    return out, meta


if __name__ == "__main__":
    data, meta = load_all(refresh="--cache" not in __import__("sys").argv)
    for s, m in meta.items():
        print(s, json.dumps(m))
