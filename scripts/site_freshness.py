#!/usr/bin/env python3
"""Which session each live page is built from. Read-only: fetches the published JSON files from GitHub Pages.

Run: python scripts/site_freshness.py 2026-11-09   -> one line per page, then SITE_FRESH_OK if every daily page is on that session
"""
import json
import sys
import time
import urllib.request

SITE = "https://originaonxi.github.io/nse-value-lens/"
# (page, file, field reader, needs the F&O bhavcopy)
PAGES = [
    ("HH/HL scanner", "hhhl_refresh_status.json", lambda d: d.get("as_of"), False),
    ("VCP", "vcp_refresh_status.json", lambda d: d.get("as_of"), False),
    ("Jev brief", "market_brief_refresh_status.json", lambda d: d.get("as_of"), False),
    ("Daily setups", "daily_setups.json", lambda d: d.get("as_of"), False),
    ("S&R / Jev rank", "jev_rank.json", lambda d: d.get("as_of"), False),
    ("Swing desk", "swing_desk.json", lambda d: d.get("as_of"), False),
    ("Daily market", "daily_market.json", lambda d: d.get("as_of"), False),
    ("DMA", "dma.json", lambda d: d.get("as_of"), False),
    ("Top Picks", "confluence.json", lambda d: d.get("as_of"), False),
    ("₹1 Play", "fno-play.json", lambda d: d.get("as_of"), False),
    ("F&O EMA 105", "fno_ema105.json", lambda d: d.get("as_of"), False),
    ("F&O coverage", "hhhl_fno.json", lambda d: d.get("as_of"), False),
    ("Kronos", "kronos_forecast.json", lambda d: d.get("as_of"), False),
    ("Nifty 50 chart", "nifty.json", lambda d: (d.get("as_of") or "")[:10], False),
    ("Nifty best setup (home)", "nifty_best.json", lambda d: (d.get("as_of") or "")[:10], False),
    ("₹1 crore test", "crore.json", lambda d: ((d.get("windows") or {}).get("2y") or {}).get("to"), False),
    ("EMA 105 audit", "nifty_ema105_audit.json", lambda d: (d.get("window") or {}).get("to"), True),
    ("Order Flow", "order_flow.json", lambda d: d.get("as_of"), True),
    ("Options desk", "options_desk.json", lambda d: d.get("as_of"), True),
    ("Nifty chain", "nifty_chain.json", lambda d: d.get("as_of"), True),
]


def get(name):
    url = f"{SITE}{name}?fresh={time.time_ns()}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Cache-Control": "no-cache"}), timeout=40) as r:
        return json.load(r)


def main(day, fo_out):
    behind, rows = [], []
    for page, name, read, needs_fo in PAGES:
        try:
            got = read(get(name))
        except Exception as e:  # pragma: no cover - network
            got = f"error {type(e).__name__}"
        ok = got == day
        waiting = needs_fo and not fo_out and not ok
        rows.append((page, got, "ok" if ok else ("waiting for NSE F&O file" if waiting else "BEHIND")))
        if not ok and not waiting:
            behind.append(page)
    for p, g, s in rows:
        print(f"{p:<26} {str(g):<12} {s}")
    print(f"{len(rows) - len(behind)}/{len(rows)} pages on {day} or waiting on NSE; behind: {', '.join(behind) or 'none'}")
    return not behind


if __name__ == "__main__":
    d = sys.argv[1]
    fo = len(sys.argv) > 2 and sys.argv[2] == "fo-out"
    ok = main(d, fo)
    print("SITE_FRESH_OK" if ok else "SITE_FRESH_FAIL")
    sys.exit(0 if ok else 1)
