"""Audit a specific completed session on both public sites against NSE's close file.

python scripts/verify_session_close.py --date 2026-09-24 --run-id RUN
Separates current daily prices from intentionally completed weekly/historical data.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from io import StringIO
import json
from pathlib import Path
import time

import pandas as pd
import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SITES = {"railway": ("https://nifty.up.railway.app/", "data/"),
         "pages": ("https://originaonxi.github.io/nse-value-lens/", "")}
DATASETS = ("hhhl_scan", "hhhl_refresh_status", "vcp_scan", "vcp_refresh_status", "market_brief",
            "market_brief_refresh_status", "swing_desk", "swing_evidence", "expanded_research",
            "indicator_research", "futures_research", "cross_asset_research")


def get_snapshot(task):
    name, dataset = task
    base, prefix = SITES[name]
    response = requests.get(base + prefix + dataset + ".json?v=" + str(time.time_ns()), timeout=30)
    response.raise_for_status()
    assert response.headers.get("X-Swing-Source") != "local-fallback", name + ": serving fallback for " + dataset
    return name, dataset, response.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--before", type=Path)
    args = parser.parse_args()
    target = date.fromisoformat(args.date)
    url = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_" + target.strftime("%d%m%Y") + ".csv"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    response.raise_for_status()
    official = pd.read_csv(StringIO(response.text), skipinitialspace=True)
    official.columns = official.columns.str.strip()
    official = official.loc[official.SERIES.str.strip().eq("EQ")].copy()
    official["SYMBOL"] = official.SYMBOL.str.strip()
    assert pd.to_datetime(official.DATE1.str.strip(), format="%d-%b-%Y").dt.date.eq(target).all(), "Wrong-date NSE file"
    official = official.set_index("SYMBOL")
    assert not official.index.duplicated().any(), "Ambiguous official EQ prices"
    snapshots = {s:{} for s in SITES}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for name, dataset, payload in pool.map(get_snapshot, [(s,d) for s in SITES for d in DATASETS]):
            snapshots[name][dataset] = payload
    report = {"session":args.date, "requested_run":args.run_id, "official_url":url, "sites":[]}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, (base, _) in SITES.items():
            data = snapshots[name]
            h, v, brief = (data[k] for k in ("hhhl_scan", "vcp_scan", "market_brief"))
            for key in ("hhhl_scan", "vcp_scan", "market_brief", "swing_desk", "swing_evidence"):
                assert data[key]["as_of"] == args.date, (name, key, data[key]["as_of"])
            for key in ("hhhl_refresh_status", "vcp_refresh_status", "market_brief_refresh_status"):
                assert data[key]["run_id"] == args.run_id, (name, key, "Unexpected refresh run")
            assert len(h["rows"]) == len(v["rows"]) == len(brief["rows"]) == 200
            assert h["market"]["data_date"] == args.date and h["market"]["data_ready"], (name,"Old or incomplete benchmark")
            vm = {r["symbol"]:r for r in v["rows"]}
            bm = {r["symbol"]:r for r in brief["rows"]}
            assert len(vm) == len(bm) == 200
            for row in h["rows"]:
                symbol = row["symbol"]
                assert row["complete_for_session"] and row["data_date"] == args.date, (symbol, "incomplete close")
                assert symbol in official.index, (symbol, "not in official EQ file")
                assert abs(float(row["close"]) - float(official.loc[symbol, "CLOSE_PRICE"])) <= .011, (symbol,"official close mismatch")
                candle = row["chart"][-1]
                assert candle["date"] == args.date, (symbol,"old chart candle")
                for field, column in (("open","OPEN_PRICE"),("high","HIGH_PRICE"),("low","LOW_PRICE"),("close","CLOSE_PRICE")):
                    assert abs(float(candle[field]) - float(official.loc[symbol,column])) <= .011, (symbol,field,"chart OHLC mismatch")
                assert int(candle["volume"]) == int(official.loc[symbol,"TTL_TRD_QNTY"]), (symbol,"volume mismatch")
                assert vm[symbol]["data_date"] == bm[symbol]["price_date"] == args.date
                assert abs(vm[symbol]["close"] - row["close"]) <= .011
                assert abs(bm[symbol]["close"] - row["close"]) <= .011
                assert all(pivot["confirmed_on"] <= args.date for pivot in row.get("chart_swings",[])), symbol
            page = browser.new_page(viewport={"width":1440,"height":1050})
            errors = []
            page.on("pageerror",lambda e:errors.append(str(e)))
            examples = []
            for symbol in ("RELIANCE","HDFCBANK","INFY"):
                page.goto(base + "hhhl.html?symbol=" + symbol + "&audit=" + args.run_id, wait_until="networkidle")
                page.wait_for_function("document.querySelector('#detail-title').textContent.startsWith(" + json.dumps(symbol) + ")")
                last_title = page.locator(".daily-candle title").last.text_content()
                assert last_title.startswith(args.date + " |"), (name,symbol,last_title)
                row = next(r for r in h["rows"] if r["symbol"] == symbol)
                assert page.locator(".strategy-check").count() == len(row["entry_checks"])
                examples.append({"symbol":symbol,"close":row["close"],"chart_title":last_title,"state":row["status"]})
            page.goto(base,wait_until="networkidle")
            expected_label = page.evaluate("iso=>new Date(iso+'T00:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'})", args.date)
            assert page.locator("#asof").inner_text() == expected_label, (name,"Homepage date label mismatch")
            assert not errors, errors
            page.close()
            result = {"site":name,"as_of":h["as_of"],"official_closes_matched":200,"chart_ohlcv_matched":200,
                      "daily_prices_match_across_hhhl_vcp_jev":True,"weekly_vcp_through":v["weekly_as_of"],
                      "homepage_as_of":data["swing_desk"]["as_of"],"homepage_eligible_history_count":data["swing_desk"]["fresh_count"],
                      "homepage_price_failures":data["swing_desk"].get("failures",{}),"hhhl_counts":h["counts"],"examples":examples,
                      "dated_research":{key:data[key]["as_of"] for key in ("expanded_research","indicator_research","futures_research","cross_asset_research")}}
            if args.before:
                before_path = args.before / name / "hhhl_scan.json"
                before = {r["symbol"]:r for r in json.loads(before_path.read_text(encoding="utf-8"))["rows"]}
                result["changed_since_previous_snapshot"] = {field:sum(r[field] != before[r["symbol"]][field] for r in h["rows"]) for field in ("close","atr","status","zones")}
            report["sites"].append(result)
        browser.close()
    out = ROOT / "artifacts" / ("session-close-" + args.date + ".json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
