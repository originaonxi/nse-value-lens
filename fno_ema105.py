#!/usr/bin/env python3
"""EMA 105 setup on every NSE F&O stock - the Nifty 50 setup #1 applied stock by stock.

Setup (unchanged from nifty_combo.py, the Nifty research winner):
  BUY   a 2-hour candle closes above EMA 105 AND ADX(14) > 20 AND Supertrend(10,3) is up AND yesterday's daily close
        is above the daily EMA 50.
  TOP   RSI(14) reaches 68 and then falls 5 points -> sell; buy again only after price is back within 1 ATR of EMA 105
        (or a fresh cross).
  EXIT  a 2-hour candle closes below EMA 105.
  Long only. Every trade pays 0.035% of price (same cost as the Nifty test).

Data: 2-hour candles are built from Yahoo hourly candles (about 2 years, refetched every run, 09:15-anchored, never
across days). The daily EMA 50 uses the same daily price files the HH/HL scanner keeps (data/hhhl_prices, then
data/fno_prices), falling back to daily closes built from the hourly candles.
Universe: the verified NSE F&O list in docs/hhhl_fno.json.
Honesty: first 2/3 of each stock's history = tested part, last 1/3 = unseen part (same split rule as the Nifty test).
Output: docs/fno_ema105.json (+ public/data). Paper research, not advice.
"""
import json
import sys
from datetime import datetime, time as dtime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import nifty_ema as N      # noqa: E402
import nifty_combo as K    # noqa: E402

DOCS, PUBLIC = ROOT / "docs", ROOT / "public" / "data"
DAILY_DIRS = (ROOT / "data" / "hhhl_prices", ROOT / "data" / "fno_prices")
ADX_MIN, RSI_TOP, EMA_N = 20, 68, 105
CHART_SESSIONS = 60
BATCH = 40
SETUP = "EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 68"


# ── data ──────────────────────────────────────────────────────────────────────

def universe():
    fno = json.loads((DOCS / "hhhl_fno.json").read_text(encoding="utf-8"))
    members = fno["membership"]["members"]
    meta = {}
    for f in ("hhhl_scan.json", "hhhl_fno.json"):
        try:
            for r in json.loads((DOCS / f).read_text(encoding="utf-8")).get("rows", []):
                meta[r["symbol"]] = {"name": r.get("name"), "sector": r.get("sector")}
        except (OSError, ValueError, KeyError):
            pass
    out = []
    for m in members:
        s = m["symbol"]
        out.append({"symbol": s, "name": (meta.get(s) or {}).get("name") or m.get("name") or s,
                    "sector": (meta.get(s) or {}).get("sector") or "", "lot": m.get("lot_size")})
    return out, fno["membership"].get("contract_month")


def fetch_hourly(symbols):
    """{symbol: hourly OHLC DataFrame in IST}. Missing symbols are simply absent."""
    import yfinance as yf
    out = {}
    for i in range(0, len(symbols), BATCH):
        part = symbols[i:i + BATCH]
        tick = [s + ".NS" for s in part]
        for attempt in range(2):
            try:
                df = yf.download(tick, period="730d", interval="60m", progress=False, auto_adjust=False,
                                 group_by="ticker", threads=True)
                break
            except Exception as e:  # pragma: no cover - network
                print(f"warn: batch {i // BATCH} attempt {attempt + 1} failed ({type(e).__name__})")
                df = None
        if df is None or df.empty:
            continue
        lvl0 = set(df.columns.get_level_values(0)) if isinstance(df.columns, pd.MultiIndex) else set()
        for s, t in zip(part, tick):
            if t not in lvl0:
                continue
            x = df[t][["Open", "High", "Low", "Close"]].dropna()
            if len(x):
                idx = x.index
                x.index = (idx.tz_localize("UTC") if idx.tz is None else idx).tz_convert(N.IST)
                out[s] = x
    return out


def two_hour(h, now):
    """Hourly -> 2-hour candles, anchored at 09:15, never across days, completed candles only."""
    t = h.index.time
    h = h[(t >= dtime(9, 15)) & (t < dtime(15, 30))]
    h = N._drop_forming(h, 60, now)
    if h.empty:
        return h
    day = h.index.date
    grp = pd.Series(range(len(h)), index=h.index).groupby(day).cumcount().to_numpy() // 2
    key = pd.MultiIndex.from_arrays([day, grp])
    g = h.groupby(key, sort=True)
    out = pd.DataFrame({"Open": g["Open"].first(), "High": g["High"].max(), "Low": g["Low"].min(),
                        "Close": g["Close"].last(), "n": g["Close"].size()})
    first = pd.Series(h.index, index=key).groupby(level=[0, 1]).first()
    out.index = pd.DatetimeIndex(first.to_numpy())
    if len(out) and out["n"].iloc[-1] < 2 and out.index[-1].date() == now.date() and now.time() < dtime(15, 30):
        out = out.iloc[:-1]
    return out.drop(columns="n")


def daily_prices(symbol, hourly):
    for d in DAILY_DIRS:
        p = d / f"{symbol}.NS.csv"
        if p.exists():
            try:
                x = pd.read_csv(p, index_col=0, parse_dates=True)
                if "Close" in x and len(x) > 60:
                    x.index = pd.to_datetime(x.index).normalize()
                    return x[["Close"]].dropna(), str(p.relative_to(ROOT)).replace("\\", "/")
            except (OSError, ValueError):
                pass
    c = hourly["Close"].groupby(hourly.index.date).last()
    c.index = pd.to_datetime(c.index)
    return pd.DataFrame({"Close": c}), "hourly closes"


# ── one stock ─────────────────────────────────────────────────────────────────

def pct_stats(trades, c):
    if not trades:
        return {"net_pct": 0.0, "dd_pct": 0.0, "avg_pct": None}
    r = np.array([t[3] / c[t[0]] * 100 for t in trades])
    eq = np.r_[0.0, np.cumsum(r)]
    return {"net_pct": round(float(r.sum()), 1), "dd_pct": round(float((np.maximum.accumulate(eq) - eq).max()), 1),
            "avg_pct": round(float(r.mean()), 2)}


def evaluate(df2, daily, now_date=None):
    """Run the setup on one stock's 2-hour candles. Returns (result dict, X)."""
    X = K.indicators(df2, EMA_N, daily)
    n = len(X["c"])
    if n < K.WARM + 60:
        return None, X
    F = K.filters(X)
    T = np.ones(n, bool)
    lok = (X["adx"] > ADX_MIN) & (X["d50"] == 1) & F["Supertrend"][0]
    trades = K.simulate(X, lok, T, "rsi", RSI_TOP, False)
    split = K.WARM + int((n - K.WARM) * K.IS_FRAC)
    a = K.stats([t for t in trades if t[0] < split])
    b = K.stats([t for t in trades if t[0] >= split])
    al = K.stats(trades)
    c = X["c"]
    res = {"all": al | pct_stats(trades, c), "is": a, "os": b,
           "from": str(df2.index[K.WARM])[:10], "split": str(df2.index[split])[:10], "to": str(df2.index[-1])[:16]}

    i = n - 1
    open_trade = bool(trades and trades[-1][4] == "open")
    checks = [
        {"k": "ema", "name": "2h close above EMA 105", "ok": bool(c[i] > X["ema"][i]), "v": f"{c[i]:,.2f} vs {X['ema'][i]:,.2f}"},
        {"k": "adx", "name": "ADX(14) above 20", "ok": bool(X["adx"][i] > ADX_MIN), "v": f"{X['adx'][i]:.1f}"},
        {"k": "st", "name": "Supertrend(10,3) up", "ok": bool(X["st"][i] == 1), "v": "up" if X["st"][i] == 1 else "down"},
        {"k": "d50", "name": "Yesterday's daily close above daily EMA 50", "ok": bool(X["d50"][i] == 1),
         "v": "above" if X["d50"][i] == 1 else "below"},
    ]
    all_ok = all(ch["ok"] for ch in checks)
    last = trades[-1] if trades else None
    top_armed = False
    if open_trade:
        top_armed = bool((X["rsi"][last[0]:i + 1] >= RSI_TOP).any())
        state = "BUY" if last[0] == i else "HOLD"
        gain = c[i] - c[last[0]]
        note = (f"Bought {str(df2.index[last[0]])[:16]} at {c[last[0]]:,.2f} ({gain / c[last[0]] * 100:+.1f}% now). "
                + (f"TOP armed: RSI touched {RSI_TOP}; sell when RSI falls below {RSI_TOP - 5}." if top_armed else
                   f"Sell on a TOP (RSI {RSI_TOP} then -5) or a 2h close below EMA 105 ({X['ema'][i]:,.2f})."))
    elif last is not None and last[1] == i and last[4] == "top":
        state, note = "TOP", f"TOP today: RSI turned down from above {RSI_TOP}. Sold at {c[i]:,.2f} ({last[3]:+,.2f}/share)."
    elif last is not None and last[1] == i:
        state, note = "EXIT", f"Closed below EMA 105 today. Sold at {c[i]:,.2f} ({last[3]:+,.2f}/share)."
    elif c[i] <= X["ema"][i]:
        state, note = "OUT", f"Below EMA 105 ({X['ema'][i]:,.2f}). Stay out; a 2h close above it is the first condition."
    elif all_ok:
        state = "WAIT"
        note = (f"All checks pass but a TOP was taken: buy again only when price is within 1 ATR of EMA 105 "
                f"(now {X['dist'][i]:.1f} ATR away).")
    else:
        state = "WAIT"
        bad = [ch["name"] for ch in checks if not ch["ok"]]
        note = "Above EMA 105 but not confirmed: " + "; ".join(bad) + "."
    res.update({"state": state, "note": note, "checks": checks, "top_armed": top_armed,
                "close": round(float(c[i]), 2), "ema": round(float(X["ema"][i]), 2),
                "rsi": round(float(X["rsi"][i]), 1), "adx": round(float(X["adx"][i]), 1),
                "atr_from_ema": round(float(X["dist"][i]), 2), "bar": str(df2.index[i])[:16],
                "open_pct": round(float((c[i] - c[last[0]]) / c[last[0]] * 100), 2) if open_trade else None})
    res["trades"] = [[str(df2.index[eb])[:16], round(float(c[eb]), 2), str(df2.index[xb])[:16], round(float(c[xb]), 2),
                      round(float(pts), 2), round(float(pts / c[eb] * 100), 2), why] for eb, xb, _d, pts, why in trades]

    # chart: last CHART_SESSIONS sessions of 2-hour candles, EMA 105 and the setup's markers
    days = pd.Index(df2.index.date)
    uniq = days.unique()
    start = int(np.argmax(days >= uniq[max(0, len(uniq) - CHART_SESSIONS)]))
    tt = [str(t)[:16] for t in df2.index]
    res["chart"] = {"t": tt[start:], "o": [round(float(v), 2) for v in X["o"][start:]],
                    "h": [round(float(v), 2) for v in X["h"][start:]], "l": [round(float(v), 2) for v in X["l"][start:]],
                    "c": [round(float(v), 2) for v in c[start:]], "e": [round(float(v), 2) for v in X["ema"][start:]]}
    mk = []
    for eb, xb, _d, pts, why in trades:
        if eb >= start:
            mk.append([tt[eb], "buy", round(float(c[eb]), 2), None])
        if xb >= start and why != "open":
            mk.append([tt[xb], "top" if why == "top" else "exit", round(float(c[xb]), 2), round(float(pts), 2)])
    res["markers"] = mk
    return res, X


# ── build ─────────────────────────────────────────────────────────────────────

STATE_ORDER = {"BUY": 0, "TOP": 1, "HOLD": 2, "EXIT": 3, "WAIT": 4, "OUT": 5}


def summarise(rows):
    ok = [r for r in rows if r.get("all")]
    pooled = [t for r in ok for t in r["trades"]]
    wins = sum(1 for t in pooled if t[4] > 0)
    gw = sum(t[5] for t in pooled if t[5] > 0)
    gl = -sum(t[5] for t in pooled if t[5] <= 0)
    pfs = [r["all"]["pf"] for r in ok if r["all"]["n"] >= 5 and r["all"]["pf"] is not None]
    wr = [r["all"]["win"] for r in ok if r["all"]["n"] >= 5 and r["all"]["win"] is not None]
    rob = [r for r in ok if r["all"]["n"] >= 8 and (r["is"]["pf"] or 0) > 1 and (r["os"]["pf"] or 0) > 1]
    os_tr = [t for r in ok for t in r["trades"] if t[0][:10] >= r["split"]]
    return {
        "stocks": len(ok), "trades": len(pooled), "win": round(wins / len(pooled) * 100, 1) if pooled else None,
        "pf_pct": round(gw / gl, 2) if gl > 0 else None,
        "avg_trade_pct": round(sum(t[5] for t in pooled) / len(pooled), 2) if pooled else None,
        "median_pf": round(float(np.median(pfs)), 2) if pfs else None,
        "median_win": round(float(np.median(wr)), 1) if wr else None,
        "pf_above_1": sum(1 for p in pfs if p > 1), "with_5_trades": len(pfs),
        "win_60": sum(1 for w in wr if w >= 60), "win_70": sum(1 for w in wr if w >= 70),
        "robust": len(rob),
        "unseen_trades": len(os_tr),
        "unseen_win": round(sum(1 for t in os_tr if t[4] > 0) / len(os_tr) * 100, 1) if os_tr else None,
    }


def build(now=None, hourly=None):
    now = now or datetime.now(N.IST)
    members, contract = universe()
    hourly = hourly if hourly is not None else fetch_hourly([m["symbol"] for m in members])
    rows, failures = [], []
    for m in members:
        s = m["symbol"]
        h = hourly.get(s)
        if h is None or len(h) < 600:
            failures.append({"symbol": s, "reason": "no hourly data from Yahoo" if h is None else f"only {len(h)} hourly candles"})
            continue
        try:
            df2 = two_hour(h, now)
            daily, dsrc = daily_prices(s, h)
            res, _ = evaluate(df2, daily)
        except Exception as e:  # keep the other stocks
            failures.append({"symbol": s, "reason": f"{type(e).__name__}: {str(e)[:80]}"})
            continue
        if res is None:
            failures.append({"symbol": s, "reason": f"only {len(df2)} two-hour candles (needs {K.WARM + 60})"})
            continue
        lot = m.get("lot") or 0
        res.update({"symbol": s, "name": m["name"], "sector": m["sector"], "lot": lot, "daily_source": dsrc,
                    "per_lot": round(res["all"]["net"] * lot, 0) if lot else None})
        rows.append(res)

    rows.sort(key=lambda r: (STATE_ORDER.get(r["state"], 9), -(r["all"]["pf"] or 0), -(r["all"]["win"] or 0)))
    latest = max((r["bar"] for r in rows), default=None)
    stale = [r["symbol"] for r in rows if latest and r["bar"][:10] < latest[:10]]
    counts = {k: sum(1 for r in rows if r["state"] == k) for k in STATE_ORDER}
    nifty = None
    try:
        w = json.loads((DOCS / "nifty_combo.json").read_text(encoding="utf-8"))["winner"]
        nifty = {"all": w["all"], "is": w["is"], "os": w["os"], "label": w["label"]}
    except (OSError, ValueError, KeyError):
        pass
    payload = {
        "version": 1, "name": "EMA 105 setup on every F&O stock", "setup": SETUP,
        "as_of": latest[:10] if latest else None, "last_candle": latest, "generated_at": now.isoformat(timespec="minutes"),
        "contract_month": contract, "universe": len(members), "covered": len(rows), "failures": failures, "stale": stale,
        "counts": counts, "summary": summarise(rows), "nifty_reference": nifty,
        "cost_pct": K.COST * 100, "chart_sessions": CHART_SESSIONS,
        "rules": [
            "BUY: a 2-hour candle closes above EMA 105 with ADX(14) > 20, Supertrend(10,3) up and yesterday's daily close above the daily EMA 50.",
            f"TOP: RSI(14) reaches {RSI_TOP} and then falls 5 points - sell. Buy again only when price is back within 1 ATR of EMA 105.",
            "EXIT: a 2-hour candle closes below EMA 105.",
            "Long only. 0.035% of price is taken off every trade. Points are rupees per share.",
        ],
        "states": {
            "BUY": "All four checks passed at the latest 2-hour close: new buy.",
            "TOP": "RSI turned down from above 68 at the latest close: sell / book the gain.",
            "HOLD": "In a trade from an earlier BUY.",
            "EXIT": "Closed below EMA 105 at the latest close: sell.",
            "WAIT": "Above EMA 105 but a check fails, or waiting for a pull-back after a TOP.",
            "OUT": "Below EMA 105: no position.",
        },
        "limits": [
            "The setup was chosen on the Nifty 50 index. Each stock here is an independent test of it, not a re-fit.",
            "About 2 years of 2-hour candles (Yahoo's hourly limit). The unseen third holds only a few trades per stock.",
            "Stock prices, not futures. Gaps, results days and circuit limits are inside the candles.",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
        "rows": rows,
    }
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for out in (DOCS / "fno_ema105.json", PUBLIC / "fno_ema105.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    sm = payload["summary"]
    print(f"fno_ema105.json {payload['as_of']}: {len(rows)}/{len(members)} F&O stocks | states {counts} | "
          f"pooled {sm['trades']} trades win {sm['win']}% PF(%) {sm['pf_pct']} | median win {sm['median_win']}% "
          f"median PF {sm['median_pf']} | PF>1 {sm['pf_above_1']}/{sm['with_5_trades']} | robust {sm['robust']} | "
          f"failures {len(failures)} | stale {len(stale)} | {len(text) // 1024}KB")
    return payload


if __name__ == "__main__":
    build()
