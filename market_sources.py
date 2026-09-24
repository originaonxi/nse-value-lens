"""Dated public evidence. Missing feeds stay missing; no AI-generated market facts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone, time
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urlparse, quote
from zoneinfo import ZoneInfo
import re
import xml.etree.ElementTree as ET

import pandas as pd
import requests
import yfinance as yf

UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")
NY = ZoneInfo("America/New_York")
FEEDS = {
    "fed_policy": ("US", "Federal Reserve monetary policy", "https://www.federalreserve.gov/feeds/press_monetary.xml"),
    "fed_speeches": ("US", "Federal Reserve speeches", "https://www.federalreserve.gov/feeds/speeches.xml"),
    "rbi_policy": ("India", "RBI press releases", "https://rbi.org.in/pressreleases_rss.xml"),
    "rbi_speeches": ("India", "RBI speeches", "https://rbi.org.in/speeches_rss.xml"),
}
QUOTES = {
    "nifty": ("Nifty 50", "^NSEI", "India", "INR"),
    "nifty200": ("Nifty 200", "^CNX200", "India", "INR"),
    "sp500": ("S&P 500", "^GSPC", "US", "USD"),
    "nasdaq": ("Nasdaq Composite", "^IXIC", "US", "USD"),
    "vix": ("US VIX", "^VIX", "US", "index"),
    "dollar": ("US Dollar Index", "DX-Y.NYB", "global", "index"),
    "treasury": ("US 10-year nominal yield", "^TNX", "US", "%"),
    "rupee": ("USD / INR", "INR=X", "global", "INR per USD"),
    "oil": ("Brent front-month futures", "BZ=F", "global", "USD per barrel"),
    "gold": ("Gold front-month futures", "GC=F", "global", "USD per oz"),
}
CALENDAR_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
NSE_ROOT = "https://www.nseindia.com"


def clean(value, limit=220):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]*>", " ", str(value or "")))).strip()[:limit]


def safe_url(value):
    p = urlparse(str(value or ""))
    if p.scheme == "http" and p.hostname in ("rbi.org.in", "www.rbi.org.in", "www.federalreserve.gov"):
        return "https://" + str(value)[7:]
    return str(value) if p.scheme == "https" and p.hostname and not p.username and not p.password else None


def get(url, session=None):
    r = (session or requests).get(url, timeout=(8, 18), headers={"User-Agent": "Mozilla/5.0 (compatible; NSEValueLens/1.0)"})
    r.raise_for_status()
    if len(r.content) > 8000000:
        raise ValueError("Source exceeds size limit")
    return r


def failure(exc):
    code = getattr(getattr(exc, "response", None), "status_code", None)
    return "HTTP " + str(code) if code else type(exc).__name__


def parse_rss(text, now, source, region):
    root = ET.fromstring(text)
    rows = []
    for item in root.findall(".//item"):
        try:
            stamp = parsedate_to_datetime(item.findtext("pubDate", ""))
            if stamp.tzinfo is None:
                # RBI publishes local clock times without an offset in its RSS feed.
                if source.startswith("RBI"):
                    stamp = stamp.replace(tzinfo=IST)
                else:
                    continue
            stamp = stamp.astimezone(UTC)
            title = clean(item.findtext("title"))
            url = safe_url(item.findtext("link"))
            if title and url and now - timedelta(days=14) <= stamp <= now:
                rows.append({"title": title, "summary": clean(item.findtext("description"), 500), "url": url, "published_at": stamp.isoformat(), "source": source, "region": region})
        except (TypeError, ValueError, OverflowError):
            continue
    return sorted(rows, key=lambda r: r["published_at"], reverse=True)[:6]


def rss_source(key, now):
    region, name, url = FEEDS[key]
    try:
        rows = parse_rss(get(url).content, now, name, region)
        return {"id": key, "name": name, "url": url, "state": "available" if rows else "no_recent_items", "items": rows}
    except Exception as exc:
        return {"id": key, "name": name, "url": url, "state": "unavailable", "error": failure(exc), "items": []}


def quote_source(key, now):
    label, symbol, region, unit = QUOTES[key]
    base = {"id": key, "name": label, "symbol": symbol, "region": region, "unit": unit,
            "url": "https://finance.yahoo.com/quote/" + quote(symbol, safe="") + "/history/"}
    try:
        frame = yf.Ticker(symbol).history(period="3mo", auto_adjust=True, timeout=18)
        local = now.astimezone(IST if region == "India" else NY if region == "US" else UTC)
        # Global FX/futures sessions cross midnight; use only prior UTC dates.
        end_time = time(16, 15) if region == "US" else time(15, 45)
        cutoff = local.date() if region != "global" and local.time().replace(tzinfo=None) >= end_time else local.date() - timedelta(days=1)
        frame = frame.loc[[d.date() <= cutoff for d in frame.index]].dropna(subset=["Close"])
        frame = frame.loc[frame.Close > 0]
        if len(frame) < 21:
            raise ValueError("Insufficient completed bars")
        last = frame.iloc[-1]
        date = frame.index[-1].date()
        return {**base, "state": "available" if (cutoff - date).days <= 4 else "stale", "observed_date": date.isoformat(),
                "value": round(float(last.Close), 4), "change_1d_pct": round((float(last.Close / frame.Close.iloc[-2]) - 1) * 100, 3),
                "change_5d_pct": round((float(last.Close / frame.Close.iloc[-6]) - 1) * 100, 3),
                "prior_20d_high": round(float(frame.High.iloc[-21:-1].max()), 4),
                "prior_20d_low": round(float(frame.Low.iloc[-21:-1].min()), 4),
                "note": "Completed daily bars. Futures are rolling contracts; changes can include roll effects." if symbol.endswith("=F") else "Completed daily bars; not streaming prices."}
    except Exception as exc:
        return {**base, "state": "unavailable", "error": failure(exc)}


def parse_ics(text, now):
    unfolded = re.sub(r"\r?\n[ \t]", "", text)
    rows = []
    for event in unfolded.split("BEGIN:VEVENT")[1:]:
        fields = {}
        for line in event.split("END:VEVENT")[0].splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key] = value.strip()
        dates = [(k, v) for k, v in fields.items() if k.startswith("DTSTART")]
        if not dates:
            continue
        key, value = dates[0]
        try:
            date_only = "VALUE=DATE" in key or len(value) == 8
            zone = ZoneInfo(key.split("TZID=")[1].split(";")[0]) if "TZID=" in key else NY
            stamp = datetime.strptime(value.rstrip("Z"), "%Y%m%d" if date_only else "%Y%m%dT%H%M%S").replace(tzinfo=UTC if value.endswith("Z") else zone)
            # A date-only item remains relevant throughout its date, with no invented time.
            relevant = now.astimezone(zone).date() <= stamp.date() <= (now + timedelta(days=8)).date() if date_only else now <= stamp <= now + timedelta(days=8)
            if relevant:
                rows.append({"title": clean(fields.get("SUMMARY", "BLS release").replace("\\,", ",")), "region": "US", "source": "Bureau of Labor Statistics",
                             "date": stamp.date().isoformat(), "time": None if date_only else stamp.astimezone(UTC).isoformat(), "url": CALENDAR_URL})
        except (ValueError, KeyError):
            continue
    return sorted(rows, key=lambda r: (r["date"], r["time"] or ""))[:25]


def calendar_source(now):
    base = {"id": "bls_calendar", "name": "US BLS release calendar", "url": CALENDAR_URL}
    try:
        rows = parse_ics(get(CALENDAR_URL).text, now)
        return {**base, "state": "available", "items": rows}
    except Exception as exc:
        return {**base, "state": "unavailable", "error": failure(exc), "items": []}


def nse_sources(now, symbols):
    today = now.astimezone(IST).date()
    start, end = (today - timedelta(days=7)).strftime("%d-%m-%Y"), today.strftime("%d-%m-%Y")
    endpoints = {
        "nse_announcements": ("NSE corporate announcements", f"/api/corporate-announcements?index=equities&from_date={start}&to_date={end}"),
        "nse_meetings": ("NSE board meetings", "/api/corporate-board-meetings?index=equities"),
        "nse_flows": ("NSE provisional FII / DII cash activity", "/api/fiidiiTradeReact"),
    }
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": NSE_ROOT + "/"})
    try:
        get(NSE_ROOT, session)
    except requests.RequestException:
        pass
    result = []
    for key, (name, path) in endpoints.items():
        base = {"id": key, "name": name, "url": NSE_ROOT + path}
        try:
            raw = get(base["url"], session).json()
            if not isinstance(raw, list):
                raise ValueError("Unexpected source schema")
            rows = []
            for item in raw:
                if key == "nse_flows":
                    date = pd.to_datetime(item.get("date"), dayfirst=True, errors="coerce")
                    if pd.isna(date) or not today - timedelta(days=7) <= date.date() <= today:
                        continue
                    rows.append({"category": clean(item.get("category")), "date": date.date().isoformat(), "net_crore": float(str(item.get("netValue")).replace(",", ""))})
                    continue
                symbol = item.get("symbol", item.get("bm_symbol", item.get("sm_symbol")))
                if symbol not in symbols:
                    continue
                if key == "nse_announcements":
                    stamp = pd.to_datetime(item.get("an_dt"), dayfirst=True, errors="coerce")
                    if pd.isna(stamp):
                        continue
                    stamp = stamp.to_pydatetime().replace(tzinfo=IST)
                    if not now - timedelta(days=7) <= stamp <= now:
                        continue
                    rows.append({"symbol": symbol, "title": clean(item.get("desc")), "summary":clean(item.get("attchmntText"), 350), "published_at": stamp.isoformat(),
                                 "url": safe_url(item.get("attchmntFile")) or NSE_ROOT + "/companies-listing/corporate-filings-announcements", "source": name})
                else:
                    date = pd.to_datetime(item.get("bm_date"), dayfirst=True, errors="coerce")
                    if pd.isna(date) or not today <= date.date() <= today + timedelta(days=14):
                        continue
                    published = pd.to_datetime(item.get("bm_timestamp"), dayfirst=True, errors="coerce")
                    if pd.isna(published) or published.to_pydatetime().replace(tzinfo=IST) > now:
                        continue
                    rows.append({"symbol": symbol, "title": clean(item.get("bm_purpose")), "summary":clean(item.get("bm_desc"), 350), "date": date.date().isoformat(), "time": None,
                                 "url": NSE_ROOT + "/companies-listing/corporate-filings-board-meetings", "source": name, "region": "India"})
            if raw and not rows and key == "nse_flows":
                raise ValueError("No dated flow records")
            result.append({**base, "state": "available", "items": rows})
        except Exception as exc:
            result.append({**base, "state": "unavailable", "error": failure(exc), "items": []})
    return result


def collect(now, symbols):
    # Independent public downloads, never an API credential on these sessions.
    with ThreadPoolExecutor(max_workers=6) as pool:
        feeds = [pool.submit(rss_source, k, now) for k in FEEDS]
        quotes = [pool.submit(quote_source, k, now) for k in QUOTES]
        calendar = pool.submit(calendar_source, now)
        nse = pool.submit(nse_sources, now, set(symbols))
        sources = [f.result() for f in feeds] + [calendar.result()] + nse.result()
        prices = [f.result() for f in quotes]
    return {"retrieved_at": now.isoformat(), "sources": sources, "quotes": prices,
            "headlines": [r for s in sources if s["id"] in FEEDS for r in s["items"]],
            "events": [r for s in sources if s["id"] in ("bls_calendar", "nse_meetings") for r in s["items"]]}


if __name__ == "__main__":
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent
    symbols = pd.read_csv(root / "nifty200.csv").Symbol.tolist()
    evidence = collect(datetime.now(UTC), symbols)
    dest = root / ".cache" / "market-evidence.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(evidence, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps({"sources": [{k:v for k,v in s.items() if k != "items"} | {"items":len(s["items"])} for s in evidence["sources"]], "quotes":evidence["quotes"]}, indent=2))
