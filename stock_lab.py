#!/usr/bin/env python3
"""Top-30 Nifty 50 stocks · 1-hour candles · every formula · BUY rule and SELL (short) rule chosen separately.

Universe  the 30 largest Nifty 50 stocks by estimated index weight (free-float market cap), all in F&O.
Candles   stock_data.py: Upstox 1-hour candles (09:15-anchored), split-adjusted, each day checked against the
          adjusted daily close; lot size from the NSE F&O bhavcopy (docs/fno_ema105.json, current lot).
Books     BUY book : long while the buy formula is "up", flat otherwise.
          SELL book: short while the sell formula is "down", flat otherwise.
          The two are separate (each 1 lot). Signal on a candle close, order at the next candle's open, 0.035% cost
          on every buy and every sell.
Formulas  EMA crosses, price vs EMA, Supertrend, UT Bot, MACD, RSI, Donchian, each also with an ADX(14) > 20 filter.
Honest    one BUY formula and one SELL formula for all 30 stocks, picked on the first half of the dates only
          (TRAIN) and then scored on the second half (TEST), which the pick never saw. The best formula per stock is
          also shown, but it is chosen after seeing all the data (look-ahead) and is labelled so.
Run: python stock_lab.py   -> docs/stock_lab.json + docs/stocklab/<SYMBOL>.json
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import stock_data as SD  # noqa: E402

DOCS, PUBLIC = ROOT / "docs", ROOT / "public" / "data"
PER = DOCS / "stocklab"
COST = 0.00035
IST = SD.IST


# ---------- indicators ----------
def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def rma(x, n):
    return pd.Series(x).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def atr(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]
    return rma(np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc))), n)


def rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up, dn = rma(np.clip(d, 0, None), n), rma(np.clip(-d, 0, None), n)
    return 100 - 100 / (1 + up / np.where(dn == 0, 1e-12, dn))


def adx(h, l, c, n=14):
    up, dn = np.diff(h, prepend=h[0]), -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(h, l, c, n)
    pdi, ndi = 100 * rma(pdm, n) / np.where(a == 0, 1e-12, a), 100 * rma(ndm, n) / np.where(a == 0, 1e-12, a)
    dx = 100 * np.abs(pdi - ndi) / np.where(pdi + ndi == 0, 1e-12, pdi + ndi)
    return rma(dx, n)


def supertrend(h, l, c, n, m):
    a = atr(h, l, c, n)
    hl2 = (h + l) / 2
    ub, lb = hl2 + m * a, hl2 - m * a
    fu, fl, d = ub.copy(), lb.copy(), np.ones(len(c))
    for i in range(1, len(c)):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        d[i] = 1 if c[i] > fu[i - 1] else (-1 if c[i] < fl[i - 1] else d[i - 1])
    return d


def utbot(h, l, c, key, n=10):
    loss = key * atr(h, l, c, n)
    t, d = np.zeros(len(c)), np.ones(len(c))
    t[0] = c[0]
    for i in range(1, len(c)):
        p = t[i - 1]
        if c[i] > p and c[i - 1] > p:
            t[i] = max(p, c[i] - loss[i])
        elif c[i] < p and c[i - 1] < p:
            t[i] = min(p, c[i] + loss[i])
        else:
            t[i] = c[i] - loss[i] if c[i] > p else c[i] + loss[i]
        d[i] = 1 if c[i] > t[i] else -1
    return d


def donchian(h, l, c, n):
    hh = pd.Series(h).rolling(n).max().shift(1).to_numpy()
    ll = pd.Series(l).rolling(n).min().shift(1).to_numpy()
    d, cur = np.zeros(len(c)), 0
    for i in range(len(c)):
        if c[i] > hh[i]:
            cur = 1
        elif c[i] < ll[i]:
            cur = -1
        d[i] = cur
    return d


def formulas(df):
    """name -> direction array (+1 up, -1 down), plus the warm-up length."""
    h, l, c = (df[k].to_numpy(float) for k in ("High", "Low", "Close"))
    F = {}
    for a, b in ((5, 13), (9, 21), (12, 26), (20, 50), (50, 200)):
        F[f"EMA {a} / EMA {b} cross"] = (np.where(ema(c, a) > ema(c, b), 1, -1), b)
    for n in (20, 50, 105, 200):
        F[f"Close vs EMA {n}"] = (np.where(c > ema(c, n), 1, -1), n)
    for n, m in ((10, 2), (10, 3), (14, 3)):
        F[f"Supertrend {n},{m}"] = (supertrend(h, l, c, n, m), n)
    for k in (1, 2, 3):
        F[f"UT Bot key {k}"] = (utbot(h, l, c, k), 10)
    line = ema(c, 12) - ema(c, 26)
    sig = ema(line, 9)
    F["MACD line vs signal"] = (np.where(line > sig, 1, -1), 35)
    F["MACD above / below 0"] = (np.where(line > 0, 1, -1), 26)
    F["RSI 14 above / below 50"] = (np.where(rsi(c) > 50, 1, -1), 14)
    for n in (20, 55):
        F[f"Donchian {n} breakout"] = (donchian(h, l, c, n), n)
    trend = adx(h, l, c) > 20
    out = {}
    for k, (d, w) in F.items():
        out[k] = (d.astype(float), w)
        out[k + " + ADX>20"] = (np.where(trend, d, 0).astype(float), max(w, 28))
    return out


# ---------- one book ----------
def book(df, want, side, start, lot):
    """want[i] True = be in the trade after candle i closes (filled at i+1 open). Returns closed+open trades."""
    o, c = df["Open"].to_numpy(float), df["Close"].to_numpy(float)
    t = df.index
    w = np.asarray(want, bool).copy()
    w[:start] = False
    held = np.r_[False, w[:-1]]                       # position during candle j
    ent = np.flatnonzero(held & ~np.r_[False, held[:-1]])
    ext = np.flatnonzero(~held & np.r_[False, held[:-1]])
    trades = []
    for k, e in enumerate(ent):
        x = ext[ext > e]
        if len(x):
            j = int(x[0])
            px, open_, xt = float(o[j]), False, str(t[j])[:16]
        else:
            px, open_, xt = float(c[-1]), True, None
        en = float(o[e])
        pts = side * (px - en) - COST * (en + px)
        trades.append({"side": "BUY" if side > 0 else "SELL", "in": str(t[e])[:16], "entry": round(en, 2), "out": xt,
                       "exit": round(px, 2), "pts": round(pts, 2), "rs": round(pts * lot), "pct": round(pts / en * 100, 3),
                       "open": open_})
    return trades


def stats(tr, a=None, b=None):
    x = [z for z in tr if (a is None or z["in"] >= a) and (b is None or z["in"] < b)]
    closed = [z for z in x if not z["open"]]
    rs = np.array([z["rs"] for z in x], float)
    rc = np.array([z["rs"] for z in closed], float)
    pc = np.array([z["pct"] for z in x], float)
    w, lo = rc[rc > 0].sum(), -rc[rc <= 0].sum()
    eq = np.cumsum(rs) if len(rs) else np.zeros(1)
    return {"n": len(x), "closed": len(closed), "win": round(float((rc > 0).mean() * 100), 1) if len(rc) else 0.0,
            "rs": int(rs.sum()), "pct": round(float(pc.sum()), 1), "pf": round(float(w / lo), 2) if lo else None,
            "dd": int((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())}


def build(refresh=True):
    data, meta = SD.load_all(refresh=refresh)
    syms = [s for s in data if len(data[s]) > 600]
    t0 = max(data[s].index[0] for s in syms)
    t1 = min(data[s].index[-1] for s in syms)
    dates = sorted({d for s in syms for d in data[s].index.normalize() if t0 <= d <= t1})
    split = str(dates[len(dates) // 2].date())
    frm = str(dates[0].date())

    per = {}
    names = None
    for s in syms:
        df = data[s][data[s].index >= dates[0]]
        F = formulas(data[s])
        off = len(data[s]) - len(df)
        lot = meta[s]["lot"]
        per[s] = {}
        for k, (d, warm) in F.items():
            d = d[off:]
            st = max(0, warm - off)
            per[s][k] = {"buy": book(df, d > 0, 1, st, lot), "sell": book(df, d < 0, -1, st, lot)}
        names = list(F)

    def pooled(side, a=None, b=None):
        rows = []
        for k in names:
            ss = [stats(per[s][k][side], a, b) for s in syms]
            all_tr = [z for s in syms for z in per[s][k][side] if (a is None or z["in"] >= a) and (b is None or z["in"] < b)]
            st = stats(all_tr)
            rows.append({"formula": k, "rs": sum(x["rs"] for x in ss), "pct": round(sum(x["pct"] for x in ss), 1), "n": sum(x["n"] for x in ss),
                         "win": st["win"], "pf": st["pf"], "stocks_up": sum(x["rs"] > 0 for x in ss)})
        return rows

    table = {}
    for side in ("buy", "sell"):
        tr_, te, al = pooled(side, None, split), pooled(side, split, None), pooled(side)
        table[side] = [{"formula": a["formula"], "train": a, "test": b, "all": c} for a, b, c in zip(tr_, te, al)]
    pick = {side: max(table[side], key=lambda r: r["train"]["pct"])["formula"] for side in ("buy", "sell")}
    best_all = {side: max(table[side], key=lambda r: r["all"]["rs"])["formula"] for side in ("buy", "sell")}

    PER.mkdir(parents=True, exist_ok=True)
    stocks = []
    for s in syms:
        df = data[s][data[s].index >= dates[0]]
        b, se = per[s][pick["buy"]]["buy"], per[s][pick["sell"]]["sell"]
        bb = max(names, key=lambda k: stats(per[s][k]["buy"])["rs"])
        bs = max(names, key=lambda k: stats(per[s][k]["sell"])["rs"])
        sb, ss_ = stats(b), stats(se)
        row = {"symbol": s, "lot": meta[s]["lot"], "weight_pct": meta[s]["weight_pct"], "close": round(float(df["Close"].iloc[-1]), 2),
               "buy": sb, "sell": ss_, "buy_test": stats(b, split), "sell_test": stats(se, split),
               "total_rs": sb["rs"] + ss_["rs"], "trades": sb["n"] + ss_["n"],
               "hold_rs": int((df["Close"].iloc[-1] - df["Open"].iloc[0]) * meta[s]["lot"]),
               "best_buy": {"formula": bb, **stats(per[s][bb]["buy"])}, "best_sell": {"formula": bs, **stats(per[s][bs]["sell"])},
               "open_buy": next((z for z in b if z["open"]), None), "open_sell": next((z for z in se if z["open"]), None),
               "check": meta[s]["check"], "splits": meta[s]["splits"], "source": meta[s]["source"]}
        stocks.append(row)
        dir_b, wb = formulas(data[s])[pick["buy"]]
        dir_s, ws = formulas(data[s])[pick["sell"]]
        off = len(data[s]) - len(df)
        detail = {"symbol": s, "lot": meta[s]["lot"], "buy_formula": pick["buy"], "sell_formula": pick["sell"],
                  "bars": [[str(t)[:16], round(float(r.Open), 2), round(float(r.High), 2), round(float(r.Low), 2), round(float(r.Close), 2)]
                           for t, r in df.iterrows()],
                  "state_buy": [int(x) for x in dir_b[off:]], "state_sell": [int(x) for x in dir_s[off:]],
                  "trades": sorted(b + se, key=lambda z: z["in"]),
                  "per_formula": [{"formula": k, "buy": stats(per[s][k]["buy"]), "sell": stats(per[s][k]["sell"])} for k in names]}
        (PER / f"{s}.json").write_text(json.dumps(detail, separators=(",", ":")), encoding="utf-8")
    stocks.sort(key=lambda r: -r["total_rs"])

    def combo(a=None, b=None):
        x = [stats(per[s][pick["buy"]]["buy"], a, b)["rs"] + stats(per[s][pick["sell"]]["sell"], a, b)["rs"] for s in syms]
        return int(sum(x))

    payload = {
        "version": 1, "name": "Top 30 Nifty 50 stocks · 1-hour · every formula", "generated_at": datetime.now(IST).isoformat(timespec="minutes"),
        "as_of": str(t1.date()), "last_candle": str(t1)[:16], "from": frm, "split": split, "cost_side_pct": COST * 100,
        "universe": [{"symbol": s, "weight_pct": meta[s]["weight_pct"], "lot": meta[s]["lot"]} for s in syms],
        "missing": [s for s in meta if s not in syms],
        "formulas": names, "table": table, "pick": pick, "best_all": best_all,
        "combo": {"train": combo(None, split), "test": combo(split, None), "all": combo()},
        "hold": {"rs": int(sum(r["hold_rs"] for r in stocks))},
        "stocks": stocks,
        "rules": [
            "BUY book: buy 1 lot when the buy formula turns up on a 1-hour close; sell it when the formula turns down. Orders fill at the next candle's open.",
            "SELL book: short 1 lot (futures) when the sell formula turns down on a 1-hour close; buy it back when it turns up.",
            "The buy formula and the sell formula can be different. Each book is 1 lot per stock, run separately.",
            f"{COST * 100:.3f}% is charged on every buy and every sell. Rupees use the current NSE F&O lot size of each stock.",
            f"The formula pair was picked on {frm} to {split} only (TRAIN) and then tested on {split} onward (TEST).",
        ],
        "limits": [
            "Rupees use today's lot size for the whole period; NSE changed lot sizes during these years.",
            "Stock prices, not futures: futures add a carry cost, roll every month and short futures need margin.",
            "Upstox 1-hour candles; splits and bonuses are adjusted from the daily price history. Each day's close is checked below.",
            "Results days, gaps and circuit limits are inside the candles; a stop order can fill far away on a gap.",
            "Many formulas were tried. The best one on all the data is usually luck; read the TEST column.",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
    }
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for out in (DOCS / "stock_lab.json", PUBLIC / "stock_lab.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(f"stock_lab.json {frm} -> {payload['last_candle']} | split {split} | {len(syms)} stocks x {len(names)} formulas x 2 sides | "
          f"pick BUY '{pick['buy']}' SELL '{pick['sell']}' | combo train Rs {payload['combo']['train']:,} test Rs {payload['combo']['test']:,} | "
          f"{len(text) // 1024}KB")
    return payload


if __name__ == "__main__":
    build(refresh="--cache" not in sys.argv)
