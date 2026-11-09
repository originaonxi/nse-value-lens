#!/usr/bin/env python3
"""Nifty 50 · EMA 105 on 2-hour candles · two-year audit against NSE bhavcopies, counted by Jev.

1. Official data: for every NSE session in the last 2 years read the F&O bhavcopy (NIFTY underlying close,
   futures lot size) and NSE's index close file ind_close_all (Nifty 50 open, high, low, close).
2. Check every day of 2-hour candles against them: first open, highest high, lowest low, last close.
3. Run the no.1 rule - EMA 105 only, no other filter - on 2-hour closes:
     a close above EMA 105 = BUY, a close below = SELL. Each signal is held until the opposite close.
   Two versions: buy and sell (always in the market) and buy only. 0.035% cost per trade.
   Done twice: on Yahoo's 2-hour closes and with each day's last close replaced by NSE's official close.
4. Jev labels every trade (on the official-close version) profit or loss on its own; the code tallies Jev's
   labels and compares them with its own count.

Run: python nifty_ema105_audit.py   -> docs/nifty_ema105_audit.json, docs/NIFTY_EMA105_AUDIT.md
"""
import json
import math
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import nifty_ema as N  # noqa: E402
import options_desk as od  # noqa: E402

DOCS, PUBLIC = ROOT / "docs", ROOT / "public" / "data"
IND_CACHE = ROOT / ".cache" / "ind_close"
EMA_N, YEARS = 105, 2
COST = N.COST_PCT
TOL = 0.0005                      # a day "matches" when every field is within 0.05%
BATCH = 20                        # trades per Jev request
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "text/csv,*/*",
           "Referer": "https://www.nseindia.com/"}


# ── official NSE data ─────────────────────────────────────────────────────────

def fo_day(day):
    """NIFTY from one F&O bhavcopy: the index close NSE used (underlying), near future close, lot size."""
    with zipfile.ZipFile(od.raw_path(date.fromisoformat(day))) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        f = pd.read_csv(z.open(name), usecols=["TckrSymb", "FinInstrmTp", "XpryDt", "ClsPric", "UndrlygPric", "NewBrdLotQty"],
                        low_memory=False)
    fut = f[(f.TckrSymb == "NIFTY") & (f.FinInstrmTp == "IDF")].sort_values("XpryDt")
    if fut.empty:
        return None
    near = fut.iloc[0]
    return {"fo_close": float(near.UndrlygPric), "fut_close": float(near.ClsPric), "lot": int(near.NewBrdLotQty)}


def ind_day(day):
    """Nifty 50 open/high/low/close from NSE's daily index file (cached on disk)."""
    stamp = datetime.strptime(day, "%Y-%m-%d").strftime("%d%m%Y")
    path = IND_CACHE / f"ind_close_all_{stamp}.csv"
    if not path.exists():
        url = f"https://nsearchives.nseindia.com/content/indices/ind_close_all_{stamp}.csv"
        for _ in range(3):
            try:
                r = requests.get(url, headers=HEADERS, timeout=15)
                if r.status_code == 200 and "Index Name" in r.text[:300]:
                    IND_CACHE.mkdir(parents=True, exist_ok=True)
                    path.write_text(r.text, encoding="utf-8")
                    break
            except requests.RequestException:
                pass
        else:
            return None
    d = pd.read_csv(StringIO(path.read_text(encoding="utf-8")))
    d.columns = d.columns.str.strip()
    row = d.loc[d["Index Name"].astype(str).str.strip().str.upper().eq("NIFTY 50")]
    if row.empty:
        return None
    row = row.iloc[0]
    val = lambda k: float(str(row[k]).replace(",", ""))
    return {"open": val("Open Index Value"), "high": val("High Index Value"), "low": val("Low Index Value"),
            "close": val("Closing Index Value")}


OFFICIAL_CSV = ROOT / "data" / "nifty" / "official_daily.csv"


def official(days):
    """Per session: NSE index OHLC + F&O underlying close + lot size. Kept in a small committed CSV so the daily run
    (which has no 2-year bhavcopy cache) only reads new sessions."""
    have = pd.read_csv(OFFICIAL_CSV, index_col=0) if OFFICIAL_CSV.exists() else pd.DataFrame()
    have.index = have.index.astype(str)
    full = lambda d: d in have.index and have.loc[d, ["ind_close", "fo_close", "lot"]].notna().all()
    todo = [d for d in days if not full(d)]

    def one(day):
        try:
            fo = fo_day(day)
        except (OSError, KeyError, ValueError, StopIteration, zipfile.BadZipFile):
            fo = None
        ind = ind_day(day)
        return day, (fo or {}) | ({"ind_" + k: v for k, v in ind.items()} if ind else {})
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = dict(pool.map(one, todo))
    new = pd.DataFrame.from_dict(rows, orient="index")
    out = pd.concat([have.drop(index=[d for d in rows if d in have.index]), new]) if len(new) else have
    out = out.sort_index()
    if len(new):
        OFFICIAL_CSV.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(OFFICIAL_CSV)
    print(f"official table: {len(todo)} sessions read, {len(out)} on file")
    return out.reindex(days)


# ── data check ────────────────────────────────────────────────────────────────

def daily_from_2h(h2):
    g = h2.groupby(h2["session"])
    return pd.DataFrame({"open": g["Open"].first(), "high": g["High"].max(), "low": g["Low"].min(),
                         "close": g["Close"].last(), "bars": g.size()})


def day_check(h2, off):
    """Every official session against the 2-hour candles of that day."""
    yd = daily_from_2h(h2)
    rows = []
    for day, o in off.iterrows():
        r = {"day": day, "bars": int(yd.bars.get(day, 0))}
        if day in yd.index:
            y = yd.loc[day]
            for k in ("open", "high", "low", "close"):
                ref = o.get("ind_" + k)
                r[k + "_diff"] = round(float(y[k] - ref), 2) if pd.notna(ref) else None
                r[k + "_pct"] = round(float((y[k] - ref) / ref * 100), 4) if pd.notna(ref) else None
            r["close_vs_fo"] = round(float(y["close"] - o["fo_close"]), 2) if pd.notna(o.get("fo_close")) else None
        r["nse_files_agree"] = (bool(abs(o["ind_close"] - o["fo_close"]) < 0.06)
                                if pd.notna(o.get("ind_close")) and pd.notna(o.get("fo_close")) else None)
        fields = [r.get(k + "_pct") for k in ("open", "high", "low", "close")]
        r["match"] = bool(r["bars"] and all(v is not None and abs(v) <= TOL * 100 for v in fields))
        rows.append(r)
    C = pd.DataFrame(rows)
    have = C[C.bars > 0]
    stat = lambda k: {"median_pts": round(float(have[k + "_diff"].abs().median()), 2),
                      "p95_pts": round(float(have[k + "_diff"].abs().quantile(.95)), 2),
                      "max_pts": round(float(have[k + "_diff"].abs().max()), 2),
                      "days_over_0.05pct": int((have[k + "_pct"].abs() > TOL * 100).sum())}
    worst = have.assign(w=have[["open_pct", "high_pct", "low_pct", "close_pct"]].abs().max(axis=1)).nlargest(10, "w")
    return {
        "sessions": int(len(C)), "with_candles": int(len(have)), "missing_days": C.loc[C.bars == 0, "day"].tolist(),
        "extra_days": sorted(set(yd.index) - set(off.index)),
        "bars_not_4": {d: int(b) for d, b in zip(have.day, have.bars) if b != 4},
        "ind_file_missing": int(off["ind_close"].isna().sum()) if "ind_close" in off else len(off),
        "nse_files_agree": int(C.nse_files_agree.fillna(False).sum()),
        "fields": {k: stat(k) for k in ("open", "high", "low", "close")},
        "days_all_match": int(have.match.sum()),
        "worst": [{k: r[k] for k in ("day", "bars", "open_diff", "high_diff", "low_diff", "close_diff")} for _, r in worst.iterrows()],
    }, C


def official_closes(h2, off):
    """Same candles, with each day's last 2-hour close set to NSE's official close."""
    x = h2.copy()
    last = x.groupby("session").tail(1).index
    ref = x.loc[last, "session"].map(off["ind_close"].fillna(off["fo_close"]))
    x.loc[last, "Close"] = ref.where(ref.notna(), x.loc[last, "Close"]).astype(float)
    return x


# ── the rule: EMA 105 only ────────────────────────────────────────────────────

def ema_trades(h2, start, lots):
    """Every signal of the EMA 105 rule from bar `start` on: buy on a close above, sell on a close below,
    held until the opposite close. The last one is still open (marked at the last close)."""
    c = h2["Close"].to_numpy(float)
    e = N.ema(c, EMA_N)
    flips, ends, dirs, gross, net, closed = N.rule_trades(c, EMA_N, start, COST)
    out = []
    for f, x, d, g, nt, cl in zip(flips, ends, dirs, gross, net, closed):
        day = h2["session"].iloc[f]
        lot = int(lots.get(day) or 0)
        out.append({"side": "BUY" if d > 0 else "SELL", "entry_time": str(h2.index[f])[:16], "entry": round(c[f], 2),
                    "ema_at_entry": round(float(e[f]), 2), "exit_time": str(h2.index[x])[:16], "exit": round(c[x], 2),
                    "bars": int(x - f), "gross": round(float(g), 2), "cost": round(float(COST * c[f]), 2),
                    "net": round(float(nt), 2), "lot": lot, "rupees": round(float(nt) * lot), "closed": bool(cl)})
    return out


def summary(tr):
    t = [x for x in tr if x["closed"]]
    if not t:
        return {"trades": 0}
    net = np.array([x["net"] for x in t])
    win, loss = net[net > 0], net[net <= 0]
    eq = np.cumsum(net)
    dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
    return {"trades": len(t), "wins": int(len(win)), "losses": int(len(loss)), "win_pct": round(len(win) / len(t) * 100, 1),
            "profit_pts": round(float(win.sum()), 1), "loss_pts": round(float(loss.sum()), 1), "net_pts": round(float(net.sum()), 1),
            "gross_pts": round(float(sum(x["gross"] for x in t)), 1), "cost_pts": round(float(sum(x["cost"] for x in t)), 1),
            "pf": round(float(win.sum() / -loss.sum()), 2) if loss.sum() < 0 else None,
            "avg_win": round(float(win.mean()), 1) if len(win) else None, "avg_loss": round(float(loss.mean()), 1) if len(loss) else None,
            "best": round(float(net.max()), 1), "worst": round(float(net.min()), 1), "max_dd_pts": round(dd, 1),
            "rupees": int(sum(x["rupees"] for x in t)), "buy_net": round(float(sum(x["net"] for x in t if x["side"] == "BUY")), 1),
            "sell_net": round(float(sum(x["net"] for x in t if x["side"] == "SELL")), 1)}


def by_month(tr):
    m = {}
    for x in tr:
        if x["closed"]:
            k = x["exit_time"][:7]
            a = m.setdefault(k, {"month": k, "trades": 0, "wins": 0, "net_pts": 0.0})
            a["trades"] += 1; a["wins"] += x["net"] > 0; a["net_pts"] = round(a["net_pts"] + x["net"], 1)
    return list(m.values())


# ── Jev counts the trades ─────────────────────────────────────────────────────

JEV_STATE = ("NIFTY 50 index, 2-hour candles, from NSE's official closes. The strategy is EMA 105 only: a 2-hour close "
             "above the 105-period EMA is a BUY, a close below is a SELL (short), and each trade is closed at the next "
             "opposite close. Each question is one finished trade with its side, entry price, exit price and the trading "
             "cost in Nifty points. A BUY makes money when the exit is higher than the entry by more than the cost. "
             "A SELL makes money when the exit is lower than the entry by more than the cost. Judge each trade on its own.")


def jev_count(trades):
    try:
        from jev_client import Client, MODEL
        client = Client()
    except Exception as e:  # pragma: no cover - needs the API key
        return {"status": f"unavailable: {e}", "model": None, "labels": {}}
    closed = [(i, t) for i, t in enumerate(trades) if t["closed"]]
    labels, errors = {}, []

    def ask(chunk):
        qs = {f"t{i:03d}": {"type": "choice", "criteria": {"profit": None, "loss": None}, "instructions": (
            f"Trade {i + 1}: {t['side']} NIFTY at {t['entry']:.2f} ({t['entry_time']}), closed at {t['exit']:.2f} "
            f"({t['exit_time']}). Trading cost {t['cost']:.2f} points. After the cost, was this trade a profit or a loss?")}
            for i, t in chunk}
        try:
            return client.ask(JEV_STATE, qs), None
        except Exception as e:  # pragma: no cover - network
            return {}, f"{type(e).__name__}: {str(e)[:80]}"

    chunks = [closed[k:k + BATCH] for k in range(0, len(closed), BATCH)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for ans, err in pool.map(ask, chunks):
            if err:
                errors.append(err)
            for key, a in ans.items():
                labels[int(key[1:])] = {"label": a["choice"], "conf": round(a["confidence"] * 100)}
    return {"status": f"labelled {len(labels)}/{len(closed)}", "model": MODEL, "errors": errors,
            "tokens": [client.input_tokens, client.output_tokens], "requests": client.calls, "labels": labels}


def jev_tally(trades, labels, side=None):
    rows = [(i, t) for i, t in enumerate(trades) if t["closed"] and (side is None or t["side"] == side)]
    got = [(i, t, labels[i]) for i, t in rows if i in labels]
    jp = [t for _, t, l in got if l["label"] == "profit"]
    jl = [t for _, t, l in got if l["label"] == "loss"]
    wrong = [{"n": i + 1, "side": t["side"], "entry_time": t["entry_time"], "entry": t["entry"], "exit": t["exit"],
              "net": t["net"], "jev": l["label"], "jev_conf": l["conf"]}
             for i, t, l in got if (l["label"] == "profit") != (t["net"] > 0)]
    return {"labelled": len(got), "of": len(rows), "profit_trades": len(jp), "loss_trades": len(jl),
            "profit_pts": round(sum(t["net"] for t in jp), 1), "loss_pts": round(sum(t["net"] for t in jl), 1),
            "net_pts": round(sum(t["net"] for t in jp + jl), 1),
            "agree_with_code": len(got) - len(wrong), "disagree": wrong}


# ── build ─────────────────────────────────────────────────────────────────────

def build(today=None):
    today = today or date.today()
    try:
        od.download(today, start=today - timedelta(days=14), pause=0.15)   # newest bhavcopies only
    except Exception as e:  # pragma: no cover - network
        print(f"warn: bhavcopy download failed ({type(e).__name__}); using the files on disk")
    since = (today - timedelta(days=365 * YEARS + 1)).isoformat()
    days = [d for d in od.sessions_available() if d >= since]
    off = official(days)
    frames = N.load_data()
    h2 = frames["2h"]
    h2 = h2[h2["session"] <= days[-1]]                      # end at the last session NSE has published
    check, C = day_check(h2[h2["session"] >= days[0]], off)
    start = int(np.argmax(h2["session"].to_numpy() >= days[0]))
    lots = off["lot"].to_dict()

    versions = {}
    for name, frame in (("yahoo", h2), ("official", official_closes(h2, off))):
        tr = ema_trades(frame, start, lots)
        versions[name] = {"buy_and_sell": summary(tr), "buy_only": summary([t for t in tr if t["side"] == "BUY"]),
                          "open_trade": next((t for t in tr if not t["closed"]), None), "trades": tr}
    tr = versions["official"]["trades"]
    jev = jev_count(tr)
    labels = jev.pop("labels")
    jev["buy_and_sell"] = jev_tally(tr, labels)
    jev["buy_only"] = jev_tally(tr, labels, side="BUY")
    for i, t in enumerate(tr):
        if i in labels:
            t["jev"], t["jev_conf"] = labels[i]["label"], labels[i]["conf"]

    payload = {
        "version": 1, "name": "Nifty 50 · EMA 105 · 2-hour · two-year bhavcopy audit",
        "generated_at": datetime.now(N.IST).isoformat(timespec="minutes"),
        "window": {"from": days[0], "to": days[-1], "sessions": len(days), "candles": int((h2["session"] >= days[0]).sum())},
        "rule": "EMA 105 only on 2-hour Nifty 50 closes: close above = BUY, close below = SELL, held until the opposite close",
        "cost_pct": COST * 100, "tolerance_pct": TOL * 100, "data_check": check,
        "yahoo": {k: v for k, v in versions["yahoo"].items() if k != "trades"},
        "official": {k: v for k, v in versions["official"].items() if k != "trades"},
        "months": by_month(tr), "trades": tr, "jev": jev,
        "limits": [
            "NSE bhavcopies are end-of-day files: they give one open, high, low and close per day, not 2-hour candles. "
            "The 2-hour candles come from Yahoo Finance hourly data and are checked against NSE day by day.",
            "The official-close version replaces only each day's last 2-hour close; the three earlier closes of the day stay Yahoo's.",
            "Index points, not futures fills. Rupees = net points x the NIFTY lot size in the F&O bhavcopy on the entry day.",
            "Jev labels each trade on its own from the prices given; the code's count is exact arithmetic and is the reference.",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
    }
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for out in (DOCS / "nifty_ema105_audit.json", PUBLIC / "nifty_ema105_audit.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    (DOCS / "NIFTY_EMA105_AUDIT.md").write_text(markdown(payload), encoding="utf-8")
    o = payload["official"]["buy_and_sell"]
    print(f"nifty_ema105_audit.json {days[0]} -> {days[-1]} ({len(days)} sessions) | days matching NSE {check['days_all_match']}/"
          f"{check['with_candles']} | buy+sell {o['trades']} trades {o['wins']}W/{o['losses']}L net {o['net_pts']} | Jev {jev['status']}")
    return payload


# ── markdown ──────────────────────────────────────────────────────────────────

def _f(v, d=1, sign=False):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-"
    s = f"{v:+,.{d}f}" if sign else f"{v:,.{d}f}"
    return s


def markdown(P):
    ck, w = P["data_check"], P["window"]
    O, Y, J = P["official"], P["yahoo"], P["jev"]
    L = [f"# Nifty 50 · EMA 105 on 2-hour candles · two-year audit", "",
         f"Generated {P['generated_at']} by `nifty_ema105_audit.py`. Every number below is computed from the files, "
         "none typed by hand. Paper research, not advice.", "",
         f"**Window:** {w['from']} -> {w['to']}, {w['sessions']} NSE sessions, {w['candles']} two-hour candles.  ",
         f"**Rule (no.1, nothing else):** {P['rule']}.  ",
         f"**Cost:** {P['cost_pct']:.3f}% of price per trade (about 9 points at 25,000).", "",
         "## 1. Profit and loss (official NSE closes)", "",
         "| | Buy and sell | Buy only |", "|---|---|---|"]
    a, b = O["buy_and_sell"], O["buy_only"]
    for lab, k, d, sg in (("Trades", "trades", 0, False), ("Winning trades", "wins", 0, False), ("Losing trades", "losses", 0, False),
                          ("Win %", "win_pct", 1, False), ("Points won (winners)", "profit_pts", 1, True),
                          ("Points lost (losers)", "loss_pts", 1, True), ("**Net points after costs**", "net_pts", 1, True),
                          ("Gross points before costs", "gross_pts", 1, True), ("Costs paid (points)", "cost_pts", 1, False),
                          ("Profit factor (won ÷ lost)", "pf", 2, False), ("Average winner", "avg_win", 1, True),
                          ("Average loser", "avg_loss", 1, True), ("Best trade", "best", 1, True), ("Worst trade", "worst", 1, True),
                          ("Worst drawdown (points)", "max_dd_pts", 1, False), ("Rupees per 1 lot", "rupees", 0, True)):
        L.append(f"| {lab} | {_f(a.get(k), d, sg)} | {_f(b.get(k), d, sg)} |")
    ot = O["open_trade"]
    if ot:
        L += ["", f"Still open on {w['to']}: **{ot['side']}** from {ot['entry_time']} at {_f(ot['entry'], 2)}, "
                  f"marked at {_f(ot['exit'], 2)} = {_f(ot['net'], 1, True)} points (not counted above)."]
    L += ["", "## 2. Jev's count", "",
          f"Jev ({J.get('model')}) was given each finished trade on its own (side, entry, exit, cost) and asked: profit or loss? "
          f"Status: {J['status']}, {J.get('requests', 0)} requests.", "",
          "| | Code: buy and sell | Jev: buy and sell | Code: buy only | Jev: buy only |", "|---|---|---|---|---|"]
    jb, jo = J["buy_and_sell"], J["buy_only"]
    L += [f"| Profit trades | {a['wins']} | {jb['profit_trades']} | {b['wins']} | {jo['profit_trades']} |",
          f"| Loss trades | {a['losses']} | {jb['loss_trades']} | {b['losses']} | {jo['loss_trades']} |",
          f"| Points in profit trades | {_f(a['profit_pts'], 1, True)} | {_f(jb['profit_pts'], 1, True)} | {_f(b['profit_pts'], 1, True)} | {_f(jo['profit_pts'], 1, True)} |",
          f"| Points in loss trades | {_f(a['loss_pts'], 1, True)} | {_f(jb['loss_pts'], 1, True)} | {_f(b['loss_pts'], 1, True)} | {_f(jo['loss_pts'], 1, True)} |",
          f"| Net points | {_f(a['net_pts'], 1, True)} | {_f(jb['net_pts'], 1, True)} | {_f(b['net_pts'], 1, True)} | {_f(jo['net_pts'], 1, True)} |",
          f"| Jev agrees with the code | | {jb['agree_with_code']} of {jb['labelled']} | | {jo['agree_with_code']} of {jo['labelled']} |", ""]
    if jb["disagree"]:
        L += ["Trades Jev labelled differently from the arithmetic:", "", "| # | Side | Entry time | Entry | Exit | Net pts | Jev said |", "|---|---|---|---|---|---|---|"]
        L += [f"| {x['n']} | {x['side']} | {x['entry_time']} | {_f(x['entry'], 2)} | {_f(x['exit'], 2)} | {_f(x['net'], 1, True)} | {x['jev']} ({x['jev_conf']}%) |"
              for x in jb["disagree"]]
        L.append("")
    fl = ck["fields"]
    L += ["## 3. Data check: 2-hour candles vs NSE bhavcopy", "",
          f"- **Sessions in the bhavcopies:** {ck['sessions']}. Days with 2-hour candles: {ck['with_candles']}. "
          f"Missing days: {', '.join(ck['missing_days']) or 'none'}. Extra days not in NSE files: {', '.join(ck['extra_days']) or 'none'}.",
          f"- **Days without 4 candles:** {', '.join(f'{d} ({n})' for d, n in ck['bars_not_4'].items()) or 'none'}.",
          f"- **NSE's two files agree** (index file close = F&O underlying close) on {ck['nse_files_agree']} of {ck['sessions']} days.",
          f"- **Days where open, high, low and close are all within {P['tolerance_pct']:.2f}%:** {ck['days_all_match']} of {ck['with_candles']}.", "",
          "| Field | Median gap (pts) | 95% of days within (pts) | Largest gap (pts) | Days over 0.05% |", "|---|---|---|---|---|"]
    L += [f"| {k.title()} | {fl[k]['median_pts']} | {fl[k]['p95_pts']} | {fl[k]['max_pts']} | {fl[k]['days_over_0.05pct']} |" for k in fl]
    L += ["", "Largest gaps (Yahoo minus NSE, points):", "", "| Day | Candles | Open | High | Low | Close |", "|---|---|---|---|---|---|"]
    L += [f"| {r['day']} | {r['bars']} | {_f(r['open_diff'], 2, True)} | {_f(r['high_diff'], 2, True)} | {_f(r['low_diff'], 2, True)} | {_f(r['close_diff'], 2, True)} |" for r in ck["worst"]]
    ya, yb = Y["buy_and_sell"], Y["buy_only"]
    L += ["", "## 4. Does the data source change the answer?", "",
          "| | Trades | Win % | Net points | PF | Rupees per lot |", "|---|---|---|---|---|---|",
          f"| Buy and sell, Yahoo closes | {ya['trades']} | {ya['win_pct']} | {_f(ya['net_pts'], 1, True)} | {_f(ya['pf'], 2)} | {_f(ya['rupees'], 0, True)} |",
          f"| Buy and sell, official closes | {a['trades']} | {a['win_pct']} | {_f(a['net_pts'], 1, True)} | {_f(a['pf'], 2)} | {_f(a['rupees'], 0, True)} |",
          f"| Buy only, Yahoo closes | {yb['trades']} | {yb['win_pct']} | {_f(yb['net_pts'], 1, True)} | {_f(yb['pf'], 2)} | {_f(yb['rupees'], 0, True)} |",
          f"| Buy only, official closes | {b['trades']} | {b['win_pct']} | {_f(b['net_pts'], 1, True)} | {_f(b['pf'], 2)} | {_f(b['rupees'], 0, True)} |",
          "", "## 5. Month by month (buy and sell, official closes)", "", "| Month | Trades | Winners | Net points |", "|---|---|---|---|"]
    L += [f"| {m['month']} | {m['trades']} | {m['wins']} | {_f(m['net_pts'], 1, True)} |" for m in P["months"]]
    L += ["", "## 6. Every trade (official closes)", "",
          "| # | Side | Entry time | Entry | EMA 105 | Exit time | Exit | Candles | Gross | Cost | Net pts | Lot | Rupees | Jev |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, t in enumerate(P["trades"]):
        jv = f"{t['jev']} ({t['jev_conf']}%)" if t.get("jev") else ("open" if not t["closed"] else "-")
        L.append(f"| {i + 1} | {t['side']} | {t['entry_time']} | {_f(t['entry'], 2)} | {_f(t['ema_at_entry'], 2)} | {t['exit_time']} | "
                 f"{_f(t['exit'], 2)} | {t['bars']} | {_f(t['gross'], 1, True)} | {_f(t['cost'], 1)} | {_f(t['net'], 1, True)} | {t['lot']} | "
                 f"{_f(t['rupees'], 0, True)} | {jv} |")
    L += ["", "## Limits", ""] + [f"- {x}" for x in P["limits"]] + [""]
    return "\n".join(L)


if __name__ == "__main__":
    build()
