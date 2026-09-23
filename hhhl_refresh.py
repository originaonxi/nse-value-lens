"""Refresh the complete HH/HL universe; retain dated, valid data on vendor failure."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
import os
from pathlib import Path
import time
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf

from hhhl_scanner import ROOT, OHLCV, build, read_prices
from swing_research import publish

IST = ZoneInfo("Asia/Kolkata")
PRICES = ROOT / "data/hhhl_prices"
UNIVERSE = ROOT / "nifty200.csv"
UNIVERSE_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "text/csv,application/json,*/*"}


def cutoff_date(now):
    local = now.astimezone(IST)
    return (local.date() if (local.hour, local.minute) >= (16, 0)
            else local.date() - timedelta(days=1))


def expected_session(cutoff, holidays=()):
    day = cutoff
    while day.weekday() >= 5 or day.isoformat() in holidays:
        day -= timedelta(days=1)
    return day.isoformat()


def validate_universe(frame):
    required = {"Symbol", "Series", "Company Name", "Industry", "ISIN Code"}
    if not required.issubset(frame.columns):
        raise ValueError("Constituent columns missing")
    if len(frame) != 200 or frame.Symbol.nunique() != 200 or not frame.Series.eq("EQ").all():
        raise ValueError("Expected exactly 200 unique EQ constituents")
    if not frame.Symbol.astype(str).str.fullmatch(r"[A-Z0-9&_-]+").all():
        raise ValueError("Invalid symbol")
    return frame


def refresh_universe():
    errors = []
    for url in (UNIVERSE_URL, UNIVERSE_URL.replace("www.", "")):
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            frame = validate_universe(pd.read_csv(StringIO(response.text)))
            frame.to_csv(UNIVERSE, index=False, lineterminator="\n")
            return frame, True, "Official Nifty Indices constituent CSV checked during this run."
        except Exception as exc:
            errors.append(type(exc).__name__)
    frame = validate_universe(pd.read_csv(UNIVERSE))
    return frame, False, "Saved 200-stock membership retained; official refresh unavailable (" + ", ".join(errors) + ")."


def holidays_for(year):
    path = ROOT / "data/hhhl_calendar.json"
    saved = json.loads(path.read_text()) if path.exists() else {}
    # Download once per IST day; API failure never turns a weekday into a holiday.
    today = datetime.now(IST).date().isoformat()
    if saved.get("checked_on") == today and saved.get("year") == year:
        return saved.get("holidays", []), saved.get("verified", False)
    try:
        response = requests.get("https://www.nseindia.com/api/holiday-master?type=trading",
                                headers=HEADERS, timeout=10)
        response.raise_for_status()
        rows = response.json()["CM"]
        dates = [pd.to_datetime(r["tradingDate"], format="%d-%b-%Y").date().isoformat() for r in rows]
        dates = [d for d in dates if d.startswith(str(year))]
        if not dates:
            raise ValueError("Calendar year unavailable")
        saved = {"year": year, "holidays": dates, "verified": True, "checked_on": today,
                 "source": "https://www.nseindia.com/api/holiday-master?type=trading"}
        path.write_text(json.dumps(saved, indent=2)+"\n", encoding="utf-8")
        return dates, True
    except Exception:
        return (saved.get("holidays", []), True) if saved.get("year") == year and saved.get("verified") else ([], False)


def valid_frame(frame, cutoff):
    if frame.empty:
        return pd.DataFrame(columns=OHLCV)
    frame = frame[OHLCV].copy()
    frame.index = pd.to_datetime([str(pd.Timestamp(x).date()) for x in frame.index])
    frame = frame.loc[frame.index <= pd.Timestamp(cutoff)]
    for column in OHLCV:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    valid = (frame.notna().all(axis=1) & (frame[OHLCV[:4]] > 0).all(axis=1)
             & (frame.High >= frame[["Open", "Low", "Close"]].max(axis=1))
             & (frame.Low <= frame[["Open", "High", "Close"]].min(axis=1))
             & (frame.Volume >= 0))
    return frame.loc[valid].sort_index().loc[lambda x: ~x.index.duplicated(keep="last")]


def history_changed(old, new):
    overlap = old.index.intersection(new.index)
    if not len(overlap):
        return False
    return bool(((old.loc[overlap, "Close"] / new.loc[overlap, "Close"] - 1).abs() > .00001).any())


def fetch_one(symbol, cutoff):
    file = PRICES / ("NSEI.csv" if symbol == "^NSEI" else symbol + ".csv")
    old = read_prices(file, cutoff)[0] if file.exists() else pd.DataFrame(columns=OHLCV)
    period = "5y" if old.empty or (pd.Timestamp(cutoff)-old.index[-1]).days > 20 else "1mo"
    error = None
    for attempt in range(2):
        try:
            raw = yf.Ticker(symbol).history(period=period, auto_adjust=True, actions=False,
                                            timeout=15)
            new = valid_frame(raw, cutoff)
            if symbol != "^NSEI":
                new = new.loc[new.Volume > 0]
            if new.empty:
                raise ValueError("No valid completed vendor candles")
            # A split/dividend/revision requires the entire adjusted history to be refreshed.
            # Do not splice differently adjusted old and new price scales.
            changed = history_changed(old, new)
            if changed and period != "5y":
                new = valid_frame(yf.Ticker(symbol).history(period="5y", auto_adjust=True,
                                  actions=False, timeout=20), cutoff)
                if symbol != "^NSEI":
                    new = new.loc[new.Volume > 0]
                if new.empty or (not old.empty and len(new) < min(len(old), 210)):
                    raise ValueError("Adjusted-history replacement incomplete")
            if changed:
                merged = new
            else:
                merged = pd.concat([old, new]) if not old.empty else new
                merged = merged.loc[~merged.index.duplicated(keep="last")].sort_index()
            merged.tail(1500).to_csv(file, index_label="Date", lineterminator="\n")
            return {"symbol": symbol, "fetched_through": str(new.index[-1].date()),
                    "latest": str(merged.index[-1].date()), "error": None}
        except Exception as exc:
            error = type(exc).__name__ + ": " + str(exc)[:150]
            if attempt == 0:
                time.sleep(1)
    return {"symbol": symbol, "fetched_through": None,
            "latest": str(old.index[-1].date()) if len(old) else None, "error": error}


def repair_index(dates):
    """Use exact official index OHLC, never a futures/ETF price, for missing sessions."""
    file = PRICES / "NSEI.csv"
    frame = pd.read_csv(file, index_col=0, parse_dates=True)
    repaired = []
    for day in dates[-3:]:
        try:
            stamp = datetime.strptime(day, "%Y-%m-%d").strftime("%d%m%Y")
            url = f"https://nsearchives.nseindia.com/content/indices/ind_close_all_{stamp}.csv"
            response = requests.get(url, headers=HEADERS, timeout=8)
            response.raise_for_status()
            data = pd.read_csv(StringIO(response.text))
            data.columns = data.columns.str.strip()
            row = data.loc[data["Index Name"].str.strip().str.upper().eq("NIFTY 50")].iloc[0]
            values = {"Open": float(row["Open Index Value"]), "High": float(row["High Index Value"]),
                      "Low": float(row["Low Index Value"]), "Close": float(row["Closing Index Value"]), "Volume": 0}
            patch = valid_frame(pd.DataFrame([values], index=[pd.Timestamp(day)]), day)
            if len(patch):
                frame = pd.concat([frame.drop(pd.Timestamp(day), errors="ignore"), patch]).sort_index()
                repaired.append({"date": day, "url": url})
        except Exception:
            pass
    if repaired:
        frame.to_csv(file, index_label="Date", lineterminator="\n")
    return repaired


def apply_official_bar(symbol, row, day, actions):
    """Append only a same-scale, complete official candle with no ex-date action."""
    if symbol in actions:
        return False, "Corporate action on this date; wait for adjusted vendor prices"
    file = PRICES / (symbol + ".NS.csv")
    if not file.exists():
        return False, "No adjusted history"
    old = read_prices(file, day)[0]
    prior = old.loc[old.index < pd.Timestamp(day)]
    if prior.empty:
        return False, "No prior close for scale check"
    previous = float(row["PREV_CLOSE"])
    if previous <= 0 or abs(float(prior.Close.iloc[-1])/previous-1) > .0001:
        return False, "Previous close does not match the adjusted history"
    values = {dest: float(row[source]) for dest, source in [
        ("Open","OPEN_PRICE"),("High","HIGH_PRICE"),("Low","LOW_PRICE"),
        ("Close","CLOSE_PRICE"),("Volume","TTL_TRD_QNTY")]}
    bar = valid_frame(pd.DataFrame([values], index=[pd.Timestamp(day)]), day)
    if bar.empty or bar.Volume.iloc[0] <= 0:
        return False, "Invalid official candle"
    merged = pd.concat([old.drop(pd.Timestamp(day), errors="ignore"), bar]).sort_index()
    merged.to_csv(file, index_label="Date", lineterminator="\n")
    return True, None


def official_stock_close(universe, day):
    stamp = datetime.strptime(day, "%Y-%m-%d")
    url = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_"+stamp.strftime("%d%m%Y")+".csv"
    result = {"date": day, "url": url, "symbols": [], "skipped": {}, "error": None}
    try:
        response = requests.get(url, headers=HEADERS, timeout=12)
        response.raise_for_status()
        data = pd.read_csv(StringIO(response.text), skipinitialspace=True)
        data.columns = data.columns.str.strip()
        data = data.loc[data.SERIES.str.strip().eq("EQ")].copy()
        dates = pd.to_datetime(data.DATE1.str.strip(), format="%d-%b-%Y").dt.strftime("%Y-%m-%d")
        if not dates.eq(day).all() or data.SYMBOL.duplicated().any():
            raise ValueError("Wrong-date or duplicate official closing rows")
        action_url = "https://www.nseindia.com/api/corporates-corporateActions"
        response = requests.get(action_url, params={"index":"equities", "from_date":stamp.strftime("%d-%m-%Y"),
                                                     "to_date":stamp.strftime("%d-%m-%Y")},
                                headers=HEADERS, timeout=12)
        response.raise_for_status()
        action_rows = response.json()
        if not isinstance(action_rows, list):
            raise ValueError("Corporate-action feed unavailable")
        actions = {r["symbol"] for r in action_rows
                   if pd.to_datetime(r["exDate"], format="%d-%b-%Y").date() == stamp.date()}
        result["corporate_action_symbols"] = sorted(actions)
        data = data.set_index("SYMBOL")
        for symbol in universe.Symbol:
            if symbol not in data.index:
                result["skipped"][symbol] = "No EQ row in official file"
                continue
            ok, reason = apply_official_bar(symbol, data.loc[symbol], day, actions)
            if ok:
                result["symbols"].append(symbol)
            else:
                result["skipped"][symbol] = reason
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)[:180]
    return result


def choose_state(scan, target, universe_verified, fetched_count):
    if scan["as_of"] != target:
        return "waiting"
    if (scan["complete_count"] == 200 and scan["market"]["data_ready"]
            and universe_verified and fetched_count == 200):
        return "fresh"
    return "partial"


def run(now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = cutoff_date(now).isoformat()
    calendar, calendar_verified = holidays_for(int(cutoff[:4]))
    target = expected_session(datetime.fromisoformat(cutoff).date(), calendar)
    run_id = os.getenv("GITHUB_RUN_ID", "local-" + now.strftime("%Y%m%dT%H%M%S"))
    status = {"version": 1, "as_of": target, "target_session": target, "attempted_at": now.isoformat(),
              "run_id": run_id, "run_url": "https://github.com/originaonxi/nse-value-lens/actions/runs/"+run_id,
              "schedule_ist": ["16:00", "16:25", "17:25", "19:25", "22:25", "08:25 next morning"],
              "calendar_verified": calendar_verified, "state": "failed"}
    previous = json.loads((ROOT/"docs/hhhl_scan.json").read_text(encoding="utf-8"))
    try:
        universe, verified, membership_note = refresh_universe()
        PRICES.mkdir(parents=True, exist_ok=True)
        symbols = [s+".NS" for s in universe.Symbol] + ["^NSEI"]
        results = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(fetch_one, symbol, cutoff) for symbol in symbols]
            for future in as_completed(futures):
                results.append(future.result())
        status["vendor_errors"] = [r for r in results if r["error"]]
        status["universe_verified"] = verified
        # Positive-volume breadth can establish a special Saturday/Sunday/holiday session.
        latest_counts = {}
        for result in results:
            if result["symbol"] != "^NSEI" and result["latest"]:
                latest_counts[result["latest"]] = latest_counts.get(result["latest"], 0)+1
        observed = max((d for d, count in latest_counts.items() if count >= 100), default="")
        target = max(target, observed)
        official = official_stock_close(universe, cutoff)
        if len(official["symbols"]) >= 100:
            target = max(target, cutoff)
        if target != cutoff:
            official = official_stock_close(universe, target)
        status["official_stock_close"] = official
        status["as_of"] = status["target_session"] = target
        scan = build(target, cache_dir=PRICES)
        missing = list(scan["market"]["missing_sessions"])
        if scan["market"]["data_date"] != target:
            missing.append(target)
        repaired = repair_index(sorted(set(missing))) if missing else []
        if repaired:
            scan = build(target, cache_dir=PRICES)
        verified_symbols = {r["symbol"].removesuffix(".NS") for r in results
                            if r["symbol"] != "^NSEI" and r["fetched_through"] == target}
        if official["date"] == target:
            verified_symbols.update(official["symbols"])
        fetched_count = len(verified_symbols)
        status.update({"fetched_target_count": fetched_count, "universe_note": membership_note,
                       "official_index_repairs": repaired})
        # Never move a published snapshot backwards or publish a market-wide outage as a new session.
        if target < previous["as_of"] or scan["complete_count"] < 190:
            status["state"] = "waiting"
            status["message"] = "Closing data is not ready for at least 190 stocks. Previous dated scan retained."
            scan = previous
        else:
            status["state"] = choose_state(scan, target, verified, fetched_count)
            status["message"] = (f'{scan["complete_count"]}/200 complete prices; {fetched_count}/200 rechecked for this session. '
                                 + ("Benchmark complete. " if scan["market"]["data_ready"] else "Benchmark incomplete; new BUY entries blocked. ")
                                 + membership_note)
            scan["refresh_run_id"] = run_id
            scan["data_audit"].update({
                "price_source": "Yahoo adjusted daily history plus official NSE closing candles when ex-date and prior-close scale checks pass; exact official index OHLC fills missing benchmark sessions.",
                "latest_recheck": status["message"], "universe_source": membership_note,
                "fetch_results": results, "official_index_repairs": repaired, "official_stock_close": official})
            for row in scan["rows"]:
                row["data_source"] = ("Official NSE closing candle; adjusted Yahoo history with ex-date and price-scale checks." if row["symbol"] in official["symbols"] else "Dated Yahoo adjusted daily OHLCV; see the refresh audit for the latest successful check.")
            scan["limitations"][0] = "End-of-day analysis through "+scan["as_of"]+"; this is not an intraday feed."
            scan["limitations"][2] = "Missing stock candles remain visible as CAUTION; incomplete prices never become new BUY entries."
            scan["limitations"][3] = "Membership refresh and adjusted-price sources can be delayed; check the visible refresh status."
            publish("hhhl_scan", scan)
        status.update({"scan_as_of": scan["as_of"], "complete_count": scan["complete_count"],
                       "benchmark_ready": scan["market"]["data_ready"], "snapshot_generated_at": scan["generated_at"],
                       "snapshot_run_id": scan.get("refresh_run_id")})
    except Exception as exc:
        status.update({"state": "failed", "message": type(exc).__name__+": "+str(exc)[:400],
                       "scan_as_of": previous["as_of"], "complete_count": previous["complete_count"],
                       "snapshot_generated_at": previous["generated_at"],
                       "snapshot_run_id": previous.get("refresh_run_id")})
    publish("hhhl_refresh_status", status)
    print(json.dumps({k: v for k, v in status.items() if k != "vendor_errors"}, indent=2))
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("## HH/HL refresh\n\nState: **"+status["state"]+"**\n\n"+status["message"]+
                         "\n\nTarget: "+target+"; published scan: "+status["scan_as_of"]+
                         "\n\n[Scanner](https://originaonxi.github.io/nse-value-lens/hhhl.html)\n")
    return status


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    result = run()
    raise SystemExit(1 if result["state"] == "failed" else 0)
