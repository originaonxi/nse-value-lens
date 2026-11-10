#!/usr/bin/env python3
"""Kotak tick bridge - READ ONLY, LOCAL ONLY.

Logs in once via kotak_live (TOTP -> MPIN, quotes only - that module has no order functions),
then serves the live Nifty 50 price to YOUR OWN browser:

    GET http://127.0.0.1:8745/nifty  ->  {"ltp": 25044.65, "chg": ..., "at": "...", "age_s": 1.4}

Open https://originaonxi.github.io/nse-value-lens/best5200.html?kotak=1 (or best15.html?kotak=1)
while this runs and the page merges Kotak ticks into the forming 15-minute candle every ~2 seconds.
Credentials stay in .env on this machine; the website never sees them. Trading signals still come
only from CLOSED candles, exactly like the backtest - the ticks are for the live feeling.

Run: py -3 kotak_ticker.py            (Ctrl+C to stop)
     py -3 kotak_ticker.py --once     (one snapshot, prints the LTP, no server)
"""
import argparse
import datetime as dt
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import kotak_live as kl  # noqa: E402

STATE = {"ltp": None, "chg": None, "at": None, "ts": 0.0, "error": None}
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def snapshot(sess):
    rows = kl.quotes(["nse_cm|Nifty 50"], sess=sess)
    q = kl._one(rows.get("data") or rows.get("message") or rows, "Nifty 50") if isinstance(rows, dict) else None
    if q is None and isinstance(rows, dict):
        for v in rows.values():
            if isinstance(v, list):
                q = kl._one(v, "Nifty 50")
                if q:
                    break
    return q


def poll_loop(interval):
    sess = kl.login()
    print("Kotak login OK (read-only session). Polling every", interval, "s")
    while True:
        try:
            q = snapshot(sess)
            ltp = kl._f((q or {}).get("ltp"))
            if ltp:
                STATE.update(ltp=ltp, chg=kl._f((q or {}).get("chg")),
                             at=dt.datetime.now(IST).isoformat(timespec="seconds"), ts=time.time(), error=None)
        except Exception as e:  # keep serving the last good tick; try to re-login on the next pass
            STATE["error"] = type(e).__name__
            try:
                sess = kl.login(force=True)
            except Exception:
                pass
        time.sleep(interval)


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] != "/nifty":
            self.send_response(404); self.end_headers(); return
        body = json.dumps({**{k: STATE[k] for k in ("ltp", "chg", "at", "error")},
                           "age_s": round(time.time() - STATE["ts"], 1) if STATE["ts"] else None}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # quiet
        pass


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", type=int, default=8745)
    p.add_argument("--interval", type=float, default=2.0)
    p.add_argument("--once", action="store_true", help="one snapshot, print, exit")
    a = p.parse_args()
    if a.once:
        q = snapshot(kl.login())
        print(json.dumps({"ltp": kl._f((q or {}).get("ltp")), "chg": kl._f((q or {}).get("chg"))}))
        return
    threading.Thread(target=poll_loop, args=(max(1.0, a.interval),), daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"Serving http://127.0.0.1:{a.port}/nifty  (local only; Ctrl+C to stop)")
    print("Now open best5200.html?kotak=1 or best15.html?kotak=1 in your browser.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
