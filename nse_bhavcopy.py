#!/usr/bin/env python3
"""
NSE Cash-Market Bhavcopy downloader + NSE quote API fallback.

Priority for LATEST EOD close:
  1. NSE CM Bhavcopy (official OHLCV zip, published ~18:00–18:30 IST)
  2. NSE quote API  (real-time JSON; requires a session cookie obtained by
                     visiting the homepage first)
  3. Returns {} so caller falls back to yfinance.

Usage:
    from nse_bhavcopy import load_latest_bhavcopy, get_nse_quote

    bhav, bhav_date = load_latest_bhavcopy()   # {SYMBOL: {open,high,low,close,volume,date}}
    quote = get_nse_quote("RELIANCE")           # {open,high,low,close,volume} or {}
"""

import io
import json
import time
import zipfile
from datetime import datetime, date, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import urlopen, Request
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# ── 1. NSE CM Bhavcopy ────────────────────────────────────────────────────────

_CM_URL = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{date}_F_0000.csv.zip"
)

# Column aliases: newer UDiFF format vs older legacy format
_COL_MAP = {
    "symbol":  ("TckrSymb", "SYMBOL"),
    "series":  ("SctySrs",  "SERIES"),
    "open":    ("OpnPric",  "OPEN"),
    "high":    ("HghPric",  "HIGH"),
    "low":     ("LwPric",   "LOW"),
    "close":   ("ClsPric",  "CLOSE"),
    "volume":  ("TtlTradgVol", "TOTTRDQTY"),
}


def _pick(row, *keys):
    for k in keys:
        v = row.get(k, "").strip()
        if v:
            return v
    return ""


def _fetch_bhavcopy_for(d: date) -> dict:
    """Download and parse CM bhavcopy for date `d`. Returns {} on any error."""
    import csv as csvmod

    ds = d.strftime("%Y%m%d")
    url = _CM_URL.format(date=ds)
    try:
        req = Request(url, headers={"User-Agent": _UA})
        resp = urlopen(req, timeout=20)
        raw = resp.read()
    except (HTTPError, URLError, OSError):
        return {}

    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        csv_name = next((n for n in z.namelist() if n.endswith(".csv")), None)
        if not csv_name:
            return {}
        content = z.read(csv_name).decode("utf-8", errors="replace")
    except Exception:
        return {}

    out = {}
    try:
        reader = csvmod.DictReader(io.StringIO(content))
        sym_keys = _COL_MAP["symbol"]
        ser_keys = _COL_MAP["series"]
        for row in reader:
            series = _pick(row, *ser_keys)
            if series != "EQ":
                continue
            sym = _pick(row, *sym_keys)
            if not sym:
                continue
            try:
                entry = {
                    "open":   float(_pick(row, *_COL_MAP["open"])  or 0),
                    "high":   float(_pick(row, *_COL_MAP["high"])  or 0),
                    "low":    float(_pick(row, *_COL_MAP["low"])   or 0),
                    "close":  float(_pick(row, *_COL_MAP["close"]) or 0),
                    "volume": float(_pick(row, *_COL_MAP["volume"]) or 0),
                    "date":   d,
                }
                if entry["close"] > 0:
                    out[sym] = entry
            except (ValueError, TypeError):
                continue
    except Exception:
        return {}

    return out


def load_latest_bhavcopy(lookback: int = 5):
    """
    Try today then up to `lookback` previous weekdays.
    Returns (data_dict, trading_date) or ({}, None) if unavailable.
    """
    today = datetime.now(IST).date()
    for i in range(lookback + 1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:   # skip Sat/Sun
            continue
        data = _fetch_bhavcopy_for(d)
        if data:
            print(f"[bhavcopy] ✅ loaded {len(data)} EQ stocks for {d}")
            return data, d
    print("[bhavcopy] ❌ no bhavcopy available (too early or network error)")
    return {}, None


# ── 2. NSE Quote API (real-time) ─────────────────────────────────────────────

_NSE_HOME = "https://www.nseindia.com"
_NSE_QUOTE = "https://www.nseindia.com/api/quote-equity?symbol={symbol}"

_nse_session_cookies: str = ""
_nse_session_ts: float = 0.0
_NSE_SESSION_TTL = 300   # refresh cookie every 5 min


def _nse_headers(extra: dict = None) -> dict:
    h = {
        "User-Agent": _UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
        "X-Requested-With": "XMLHttpRequest",
    }
    if _nse_session_cookies:
        h["Cookie"] = _nse_session_cookies
    if extra:
        h.update(extra)
    return h


def _refresh_nse_session():
    """Visit NSE homepage to obtain session cookies."""
    global _nse_session_cookies, _nse_session_ts
    try:
        req = Request(_NSE_HOME, headers={"User-Agent": _UA})
        resp = urlopen(req, timeout=10)
        set_cookie = resp.headers.get("Set-Cookie", "")
        # Parse multiple Set-Cookie values from the response headers object
        if hasattr(resp.headers, "get_all"):
            cookies = resp.headers.get_all("Set-Cookie") or []
        else:
            raw = str(resp.info())
            cookies = [l.split(":", 1)[1].strip()
                       for l in raw.splitlines()
                       if l.lower().startswith("set-cookie:")]
        parts = []
        for c in cookies:
            parts.append(c.split(";")[0].strip())
        _nse_session_cookies = "; ".join(parts)
        _nse_session_ts = time.monotonic()
    except Exception:
        pass   # session refresh failed; proceed without cookies


def get_nse_quote(symbol: str) -> dict:
    """
    Fetch real-time quote for `symbol` from NSE API.
    Returns {open, high, low, close, volume} or {} on failure.
    """
    global _nse_session_cookies, _nse_session_ts

    if time.monotonic() - _nse_session_ts > _NSE_SESSION_TTL:
        _refresh_nse_session()

    url = _NSE_QUOTE.format(symbol=symbol.upper())
    try:
        req = Request(url, headers=_nse_headers())
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read())
        pd = data.get("priceInfo", {})
        return {
            "open":   float(pd.get("open", 0)),
            "high":   float(pd.get("intraDayHighLow", {}).get("max", 0)),
            "low":    float(pd.get("intraDayHighLow", {}).get("min", 0)),
            "close":  float(pd.get("lastPrice", 0)),
            "volume": 0.0,   # not in this endpoint
        }
    except Exception:
        return {}


# ── 3. Helper: patch a yfinance DataFrame with one bhavcopy/quote row ─────────

def patch_df_with_bhavcopy(df, symbol: str, bhav_data: dict, bhav_date):
    """
    Append a bhavcopy row to a yfinance OHLCV DataFrame if it is more recent
    than the last row. Returns the (possibly extended) DataFrame.

    `df`        — pandas DataFrame with DatetimeIndex (yfinance output)
    `symbol`    — NSE ticker WITHOUT '.NS'
    `bhav_data` — dict returned by load_latest_bhavcopy()
    `bhav_date` — date object for the bhavcopy data
    """
    import pandas as pd

    if df.empty or symbol not in bhav_data:
        return df

    last_date = df.index[-1].date() if hasattr(df.index[-1], "date") else None
    if last_date is None or last_date >= bhav_date:
        return df   # yfinance is already up to date

    bhav = bhav_data[symbol]
    if bhav["close"] <= 0:
        return df

    # Build new row with timezone-aware index matching yfinance's tz
    tz = df.index.tz
    new_ts = pd.Timestamp(bhav_date).tz_localize("Asia/Kolkata")
    if tz is not None and str(tz) != "Asia/Kolkata":
        new_ts = new_ts.tz_convert(tz)

    new_row = pd.DataFrame(
        {
            "Open":   [bhav["open"]],
            "High":   [bhav["high"]],
            "Low":    [bhav["low"]],
            "Close":  [bhav["close"]],
            "Volume": [bhav["volume"]],
        },
        index=[new_ts],
    )
    patched = pd.concat([df, new_row])
    print(f"[bhavcopy] {symbol}: patched {last_date} → {bhav_date} "
          f"(close {bhav['close']:.2f})")
    return patched


# ── CLI self-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Testing NSE CM Bhavcopy ===")
    data, d = load_latest_bhavcopy()
    if data:
        sample = list(data.items())[:5]
        for sym, v in sample:
            print(f"  {sym:<15} close={v['close']:.2f}  vol={v['volume']:,.0f}  date={v['date']}")
    else:
        print("  Bhavcopy not available — trying NSE quote API...")
        for sym in ["RELIANCE", "INFY", "TCS"]:
            q = get_nse_quote(sym)
            print(f"  {sym:<15} {q}")
