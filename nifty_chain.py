"""Nifty 50 option chain desk: Greeks, sigma bands, positioning, HH/HL structure, backtested setups and Jev.

Adds one page (docs/nifty-chain.html) and its data file (docs/nifty_chain.json). It only READS the
files that the existing desks maintain; it never writes them:
  - official NSE UDiFF F&O bhavcopies (the same cache options_desk.py downloads into .cache/fo_bhavcopy)
  - NSE participant-wise open interest (FII / DII / Pro / Client) and NSE's daily index close file
  - data/hhhl_prices/NSEI.csv (Nifty OHLC kept by the HH/HL refresh), docs/hhhl_scan.json, docs/options_desk.json
  - docs/nifty_research.json (static, cited research on how institutions trade index options)

Pipeline (no look-ahead):
1. For every session since 2024-01-01, extract the NIFTY option and futures rows from the official bhavcopy.
2. Per session t, from session t alone: spot, futures OI, put/call OI ratio, the trade expiry (first expiry at
   least MIN_DTE days away), ATM implied volatility, 20/25-delta strikes, OI walls, max pain.
   Trailing features (5-session move in sigma, 20-session realised vol, IV percentile, HH/HL swing structure
   from confirmed pivots, FII futures long share) use sessions <= t only.
3. Fixed rules (written before any result was seen) trigger on session-t features. Entry at the NEXT
   session's official open of each chosen contract; exit at the close of the 5th session held.
4. The same validation as the options desk: VALIDATED needs >= 60 trades, date-clustered t-stat >= 2,
   positive in both halves and a better mean than the same structure taken every session (baseline).
5. Jev reviews the index state and every Nifty 50 constituent from the supplied numbers only. The first
   review of each session is archived in data/nifty_chain_history and scored as the 5-session window matures.
"""
import argparse
import csv
import datetime as dt
import io
import json
import math
import os
import pickle
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

import options_desk as od
from indicator_research import cross

ROOT = Path(__file__).resolve().parent
NDAYS = ROOT / ".cache" / "nifty_days"
PART = ROOT / ".cache" / "participant_oi"
INDEX_CACHE = ROOT / ".cache" / "index_close"
OUT = ROOT / "docs" / "nifty_chain.json"
RESEARCH = ROOT / "docs" / "nifty_research.json"
HIST = ROOT / "data" / "nifty_chain_history"
NSEI = ROOT / "data" / "hhhl_prices" / "NSEI.csv"
HHHL = ROOT / "docs" / "hhhl_scan.json"
DESK = ROOT / "docs" / "options_desk.json"
N50_CACHE = ROOT / ".cache" / "nifty50_list.csv"
PART_URL = "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{d}.csv"
INDEX_URL = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{d}.csv"
N50_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv"
VERSION = "nifty-chain-v1"
DAY_VERSION = 1
SYMBOL = "NIFTY"
HOLD = od.HOLD
MIN_DTE = od.MIN_DTE
CHAIN_EXPIRIES = 4
CHAIN_WIDTH = 20
HISTORY = 120
PARTICIPANTS = ("FII", "DII", "Pro", "Client")
OHLC = ["Open", "High", "Low", "Close", "Volume"]


def num(v, digits=2):
    return od._num(v, digits)


# ---------------------------------------------------------------- downloads (read-only sources)
def fetch(url, timeout=30, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # 404 = not published; other errors are retried
            if getattr(exc, "code", None) == 404:
                return None
            time.sleep(2 * (attempt + 1))
    return None


def cached(folder, name, url, offline, valid):
    """Read a cached official file, or download it once. Failures are never cached."""
    path = folder / name
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    if offline:
        return None
    body = fetch(url)
    if not body:
        return None
    text = body.decode("utf-8", errors="replace")
    if not valid(text):
        return None
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


PART_COLS = {"Future Index Long": "fut_long", "Future Index Short": "fut_short",
             "Option Index Call Long": "call_long", "Option Index Put Long": "put_long",
             "Option Index Call Short": "call_short", "Option Index Put Short": "put_short",
             "Future Stock Long": "stock_fut_long", "Future Stock Short": "stock_fut_short"}


def parse_participants(text):
    rows = [r for r in csv.reader(io.StringIO(text)) if r and any(c.strip() for c in r)]
    head = next(i for i, r in enumerate(rows) if r[0].strip() == "Client Type")
    cols = [c.strip() for c in rows[head]]
    out = {}
    for r in rows[head + 1:]:
        name = r[0].strip()
        if name not in PARTICIPANTS + ("TOTAL",):
            continue
        out[name] = {PART_COLS[c]: int(float(v.strip())) for c, v in zip(cols[1:], r[1:]) if c in PART_COLS and v.strip()}
    if not set(PARTICIPANTS) <= set(out) or any(len(out[p]) != len(PART_COLS) for p in PARTICIPANTS):
        raise ValueError("participant file incomplete")
    return out


def participants(day, offline):
    stamp = dt.date.fromisoformat(day).strftime("%d%m%Y")

    def ok(text):
        try:
            parse_participants(text)
            return True
        except (ValueError, StopIteration):
            return False
    text = cached(PART, f"{day}.csv", PART_URL.format(d=stamp), offline, ok)
    return parse_participants(text) if text else None


def _float(v):
    try:
        x = float(str(v).strip())
        return x if math.isfinite(x) else None
    except ValueError:
        return None


def parse_index_close(text):
    out = {}
    for r in csv.DictReader(io.StringIO(text)):
        name = (r.get("Index Name") or "").strip()
        if not name:
            continue
        out[name] = dict(open=_float(r.get("Open Index Value")), high=_float(r.get("High Index Value")),
                         low=_float(r.get("Low Index Value")), close=_float(r.get("Closing Index Value")),
                         change=_float(r.get("Points Change")), change_pct=_float(r.get("Change(%)")),
                         pe=_float(r.get("P/E")), pb=_float(r.get("P/B")), div_yield=_float(r.get("Div Yield")))
    if "Nifty 50" not in out or out["Nifty 50"]["close"] is None:
        raise ValueError("Nifty 50 missing from index close file")
    return out


def index_close(day, offline):
    stamp = dt.date.fromisoformat(day).strftime("%d%m%Y")

    def ok(text):
        try:
            parse_index_close(text)
            return True
        except ValueError:
            return False
    text = cached(INDEX_CACHE, f"{day}.csv", INDEX_URL.format(d=stamp), offline, ok)
    return parse_index_close(text) if text else None


def nifty50_list(offline):
    """Official constituent list; the last good copy is kept in the cache if NSE cannot be reached."""
    text = None if offline else (fetch(N50_URL) or b"").decode("utf-8", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text))) if text else []
    if len(rows) >= 45:
        N50_CACHE.parent.mkdir(parents=True, exist_ok=True)
        N50_CACHE.write_text(text, encoding="utf-8")
        source = "live"
    elif N50_CACHE.exists():
        rows, source = list(csv.DictReader(io.StringIO(N50_CACHE.read_text(encoding="utf-8")))), "cached"
    else:
        return [], "unavailable"
    return [dict(symbol=r["Symbol"].strip(), name=r["Company Name"].strip(), industry=r["Industry"].strip()) for r in rows], source


# ---------------------------------------------------------------- pricing maths (Black-Scholes, same rate as the desk)
def npdf(x):
    return np.exp(-0.5 * np.asarray(x, dtype=float) ** 2) / math.sqrt(2 * math.pi)


def greeks(s, k, t, sigma, call):
    """Delta, gamma (per point), theta (per calendar day), vega (per 1 vol point), model P(ITM at expiry)."""
    s, k, t, sigma, call = (np.asarray(v, dtype=float) for v in (s, k, t, sigma, call))
    root = sigma * np.sqrt(t)
    d1 = (np.log(s / k) + (od.RATE + 0.5 * sigma * sigma) * t) / root
    d2 = d1 - root
    disc = k * np.exp(-od.RATE * t)
    pdf = npdf(d1)
    decay = -s * pdf * sigma / (2 * np.sqrt(t))
    return dict(delta=np.where(call > 0, od.ncdf(d1), od.ncdf(d1) - 1.0), gamma=pdf / (s * root),
                theta=np.where(call > 0, decay - od.RATE * disc * od.ncdf(d2), decay + od.RATE * disc * od.ncdf(-d2)) / 365.0,
                vega=s * pdf * np.sqrt(t) / 100.0, prob_itm=np.where(call > 0, od.ncdf(d2), od.ncdf(-d2)))


def strike_table(chain, spot, dte):
    """CE/PE side by side for one expiry with implied vol and Greeks for every live contract."""
    if chain.empty or not dte or dte <= 0:
        return pd.DataFrame()
    t = dte / 365.0
    cols = ["mark", "OpnIntrst", "ChngInOpnIntrst", "TtlTradgVol", "NewBrdLotQty", "ClsPric"]
    ce = chain[chain.OptnTp == "CE"].groupby("StrkPric")[cols].first().add_prefix("ce_")
    pe = chain[chain.OptnTp == "PE"].groupby("StrkPric")[cols].first().add_prefix("pe_")
    tab = ce.join(pe, how="outer").sort_index()
    tab.index.name = "strike"
    tab = tab.reset_index()
    k = tab.strike.to_numpy(float)
    for side, call in (("ce", 1.0), ("pe", 0.0)):
        mark = tab[f"{side}_mark"].to_numpy(float)
        live = (mark > 0) & (tab[f"{side}_OpnIntrst"].fillna(0).to_numpy(float) > 0)
        iv = od.implied_vol(np.where(live, mark, 0.0), np.full(len(k), spot), k, np.full(len(k), t), np.full(len(k), call))
        tab[f"{side}_live"] = live
        tab[f"{side}_iv"] = iv
    return tab


def _nearest_row(tab, mask, target, col="strike"):
    cand = tab[mask]
    if cand.empty:
        return None
    return cand.loc[(cand[col] - target).abs().idxmin()]


def picks(tab, spot, dte):
    """Strikes the setups use, chosen from session-t data only."""
    out = {}
    if tab.empty:
        return out
    both = tab.ce_live & tab.pe_live
    atm = _nearest_row(tab, both, spot)
    if atm is None:
        return out
    out.update(atm=atm.strike, atm_ce=atm.ce_mark, atm_pe=atm.pe_mark)
    ivs = [v for v in (atm.ce_iv, atm.pe_iv) if np.isfinite(v)]
    out["atm_iv"] = 100.0 * float(np.mean(ivs)) if ivs else np.nan
    sigma = out["atm_iv"] / 100.0 if np.isfinite(out["atm_iv"]) else np.nan
    t = dte / 365.0
    if np.isfinite(sigma):
        k = tab.strike.to_numpy(float)
        tab = tab.assign(ce_delta=greeks(spot, k, t, np.where(np.isfinite(tab.ce_iv), tab.ce_iv, sigma), 1.0)["delta"],
                         pe_delta=greeks(spot, k, t, np.where(np.isfinite(tab.pe_iv), tab.pe_iv, sigma), 0.0)["delta"])
        calls = tab.ce_live & (tab.strike > spot)
        puts = tab.pe_live & (tab.strike < spot)
        for key, side, mask, target in (("c20", "ce", calls, 0.20), ("p20", "pe", puts, -0.20),
                                       ("c25", "ce", calls, 0.25), ("p25", "pe", puts, -0.25)):
            row = _nearest_row(tab, mask, target, col=f"{side}_delta")
            if row is not None:
                out[key] = row.strike
                out[f"{key}_{side}"] = row[f"{side}_mark"]
                out[f"{key}_iv"] = row[f"{side}_iv"]
        if "c20" in out:
            row = _nearest_row(tab, tab.ce_live & (tab.strike > out["c20"]), out["c20"] + 0.02 * spot)
            if row is not None:
                out.update(cw=row.strike, cw_ce=row.ce_mark)
        if "p20" in out:
            row = _nearest_row(tab, tab.pe_live & (tab.strike < out["p20"]), out["p20"] - 0.02 * spot)
            if row is not None:
                out.update(pw=row.strike, pw_pe=row.pe_mark)
        if np.isfinite(out.get("c25_iv", np.nan)) and np.isfinite(out.get("p25_iv", np.nan)):
            out["skew25"] = 100.0 * (out["p25_iv"] - out["c25_iv"])
    row = _nearest_row(tab, tab.ce_live & (tab.strike > out["atm"]), spot * 1.02)
    if row is not None:
        out.update(bcs=row.strike, bcs_ce=row.ce_mark)
    row = _nearest_row(tab, tab.pe_live & (tab.strike < out["atm"]), spot * 0.98)
    if row is not None:
        out.update(bps=row.strike, bps_pe=row.pe_mark)
    ce_oi, pe_oi = tab.ce_OpnIntrst.fillna(0), tab.pe_OpnIntrst.fillna(0)
    if ce_oi.max() > 0:
        out["call_wall"] = tab.strike[ce_oi.idxmax()]
    if pe_oi.max() > 0:
        out["put_wall"] = tab.strike[pe_oi.idxmax()]
    return out


# ---------------------------------------------------------------- per-session NIFTY extraction and features
def nifty_day(day):
    NDAYS.mkdir(parents=True, exist_ok=True)
    path = NDAYS / f"{day}_v{DAY_VERSION}.pkl"
    if path.exists():
        return pickle.loads(path.read_bytes())
    raw = od.read_raw(day)
    keep = ["FinInstrmTp", "exp", "StrkPric", "OptnTp", "OpnPric", "ClsPric", "SttlmPric", "UndrlygPric", "OpnIntrst",
            "ChngInOpnIntrst", "TtlTradgVol", "NewBrdLotQty", "mark", "fill_open"]
    frame = raw[raw.TckrSymb == SYMBOL][keep].reset_index(drop=True)
    path.write_bytes(pickle.dumps(frame))
    return frame


def dte_of(exp, day):
    return (pd.Timestamp(exp) - pd.Timestamp(day)).days


def session_features(day, chain):
    opt = chain[chain.FinInstrmTp == "IDO"]
    fut = chain[chain.FinInstrmTp == "IDF"]
    if opt.empty:
        return None
    spot = float(opt.UndrlygPric.median())
    exps = sorted(e for e in opt.exp.unique() if dte_of(e, day) > 0)
    texp = next((e for e in exps if dte_of(e, day) >= MIN_DTE), None)
    live_fut = fut[fut.exp.map(lambda e: dte_of(e, day) >= 0)]
    near_fut = live_fut[live_fut.exp == live_fut.exp.min()] if not live_fut.empty else live_fut
    rec = dict(date=day, spot=spot, lot=int(opt.NewBrdLotQty.max()), foi=float(fut.OpnIntrst.sum()),
               fut_close=float(near_fut.ClsPric.iloc[0]) if not near_fut.empty else np.nan,
               ce_oi=float(opt[opt.OptnTp == "CE"].OpnIntrst.sum()), pe_oi=float(opt[opt.OptnTp == "PE"].OpnIntrst.sum()),
               texp=texp, dte=dte_of(texp, day) if texp else np.nan)
    if texp:
        ch = opt[opt.exp == texp]
        rec.update(picks(strike_table(ch, spot, rec["dte"]), spot, rec["dte"]))
        rec["max_pain"] = od.max_pain(ch)
    return rec


def load_features(sessions, log=print):
    rows, books = [], {}
    for i, day in enumerate(sessions):
        chain = nifty_day(day)
        opt = chain[chain.FinInstrmTp == "IDO"]
        books[day] = {(e, round(float(k), 2), o): (m, f) for e, k, o, m, f in
                      zip(opt.exp, opt.StrkPric, opt.OptnTp, opt.mark, opt.fill_open)}
        rec = session_features(day, chain)
        if rec:
            rows.append(rec)
        if i % 100 == 0:
            log(f"nifty features {day} ({i + 1}/{len(sessions)})")
    return pd.DataFrame(rows), books


def swing_structure(frame, width=2):
    """Same confirmed pivots as indicator_research.confirmed_structure, plus the falling (LH/LL) side.

    A pivot at bar p is only known at bar p + width, so every value at bar t uses bars <= t."""
    h, l = frame.High.to_numpy(float), frame.Low.to_numpy(float)
    highs, lows, out = [], [], []
    for t in range(len(frame)):
        p = t - width
        if p >= width:
            if h[p] > np.r_[h[p - width:p], h[p + 1:t + 1]].max():
                highs.append(float(h[p]))
            if l[p] < np.r_[l[p - width:p], l[p + 1:t + 1]].min():
                lows.append(float(l[p]))
        two_h, two_l = len(highs) >= 2, len(lows) >= 2
        hh, lh = two_h and highs[-1] > highs[-2], two_h and highs[-1] < highs[-2]
        hl, ll = two_l and lows[-1] > lows[-2], two_l and lows[-1] < lows[-2]
        label = ("HH" if hh else "LH" if lh else "EH" if two_h else "--") + " / " + ("HL" if hl else "LL" if ll else "EL" if two_l else "--")
        out.append((highs[-1] if highs else np.nan, lows[-1] if lows else np.nan, hh and hl, lh and ll, label))
    return pd.DataFrame(out, index=frame.index, columns=["confirmed_high", "confirmed_low", "rising", "falling", "structure"])


def index_ohlc(sessions, offline):
    """Nifty OHLC from the HH/HL price file, with today's official NSE close appended if that file lags."""
    if NSEI.exists():
        raw = pd.read_csv(NSEI, index_col=0)
        raw.index = pd.to_datetime([str(d)[:10] for d in raw.index])
        raw = raw[OHLC].apply(pd.to_numeric, errors="coerce").dropna(subset=["Open", "High", "Low", "Close"])
        raw = raw[~raw.index.duplicated(keep="last")].sort_index()
        raw = raw[raw.index <= pd.Timestamp(sessions[-1])]
    else:
        raw = pd.DataFrame(columns=OHLC, dtype=float)
    last = raw.index.max() if len(raw) else pd.Timestamp("1900-01-01")
    extra, appended = [], []
    for day in sessions[-15:]:
        if pd.Timestamp(day) > last:
            ic = index_close(day, offline)
            n = ic.get("Nifty 50") if ic else None
            if n and all(n[k] for k in ("open", "high", "low", "close")):
                extra.append(dict(Date=pd.Timestamp(day), Open=n["open"], High=n["high"], Low=n["low"], Close=n["close"], Volume=0.0))
                appended.append(day)
    if extra:
        raw = pd.concat([raw, pd.DataFrame(extra).set_index("Date")]).sort_index()
    return raw, appended


def participant_frame(sessions, offline, log=print):
    rows, fetched = [], 0
    for day in sessions:
        before = (PART / f"{day}.csv").exists()
        p = participants(day, offline)
        fetched += int(p is not None and not before)
        if not p:
            continue
        rec = dict(date=day)
        for who in PARTICIPANTS:
            for k, v in p[who].items():
                rec[f"{who.lower()}_{k}"] = v
        rows.append(rec)
    log(f"participant OI: {len(rows)}/{len(sessions)} sessions ({fetched} downloaded this run)")
    return pd.DataFrame(rows)


def pct_rank(values):
    x = values[~np.isnan(values)]
    if len(x) < 60 or np.isnan(values[-1]):
        return np.nan
    return 100.0 * (x <= values[-1]).mean()


def derive(feat, ohlc, part, sessions):
    """Trailing features. Every value at session t uses sessions <= t only."""
    f = feat.copy()
    f["sidx"] = f.date.map({d: i for i, d in enumerate(sessions)})
    f = f.sort_values("sidx").reset_index(drop=True)

    def lag(col, n):
        return f[col].shift(n).where(f.sidx - f.sidx.shift(n) == n)

    f["ret1"] = f.spot / lag("spot", 1) - 1
    f["ret5"] = f.spot / lag("spot", 5) - 1
    logret = np.log1p(f.ret1)
    f["sig5"] = logret.rolling(20, min_periods=15).std() * math.sqrt(5)
    f["z5"] = f.ret5 / f.sig5
    f["rv20"] = logret.rolling(20, min_periods=15).std() * math.sqrt(252) * 100
    f["pcr"] = f.pe_oi / f.ce_oi.replace(0, np.nan)
    f["pcr_chg5"] = f.pcr - lag("pcr", 5)
    f["foi5"] = f.foi / lag("foi", 5) - 1
    for col in ("atm_iv", "skew25", "atm", "atm_ce", "atm_pe"):
        if col not in f:
            f[col] = np.nan
    f["iv_pct"] = f.atm_iv.rolling(250, min_periods=1).apply(pct_rank, raw=True)
    f["vrp"] = f.atm_iv - f.rv20
    if len(ohlc):
        st = swing_structure(ohlc)
        st["close_idx"] = ohlc.Close
        st["sma20"] = ohlc.Close.rolling(20).mean()
        st["sma50"] = ohlc.Close.rolling(50).mean()
        st["breakout"] = (st.rising & cross(ohlc.Close, st.confirmed_high)).fillna(False)
        st.index = [str(d.date()) for d in st.index]
        f = f.join(st, on="date")
    for col in ("confirmed_high", "confirmed_low", "close_idx", "sma20", "sma50"):
        if col not in f:
            f[col] = np.nan
    for col in ("rising", "falling", "breakout"):
        f[col] = f[col].astype("boolean").fillna(False).astype(bool) if col in f else False
    if "structure" not in f:
        f["structure"] = None
    if not part.empty:
        f = f.merge(part, on="date", how="left")
    for who in ("fii", "client", "pro", "dii"):
        if f"{who}_fut_long" not in f:
            for k in PART_COLS.values():
                f[f"{who}_{k}"] = np.nan
        f[f"{who}_ratio"] = f[f"{who}_fut_long"] / (f[f"{who}_fut_long"] + f[f"{who}_fut_short"]).replace(0, np.nan)
        f[f"{who}_ratio_chg5"] = f[f"{who}_ratio"] - lag(f"{who}_ratio", 5)
    f["valid"] = (f.atm.notna() & (f.atm_ce > 0) & (f.atm_pe > 0) & f.sig5.notna() & (f.sig5 > 0) & (f.dte >= MIN_DTE))
    return f


# ---------------------------------------------------------------- fixed rules
def _rule(id_, label, action, legs, basis, view, condition, cond, catalog=None, baseline=False):
    return dict(id=id_, label=label, action=action, legs=legs, basis=basis, view=view, condition=condition,
                cond=cond, catalog=catalog, baseline=baseline)


BULL = [("CE", "atm", "BUY"), ("CE", "bcs", "SELL")]
BEAR = [("PE", "atm", "BUY"), ("PE", "bps", "SELL")]
CONDOR = [("CE", "c20", "SELL"), ("CE", "cw", "BUY"), ("PE", "p20", "SELL"), ("PE", "pw", "BUY")]
SHORT_STRADDLE = [("CE", "atm", "SELL"), ("PE", "atm", "SELL")]
LONG_STRADDLE = [("CE", "atm", "BUY"), ("PE", "atm", "BUY")]
ALWAYS = lambda f: pd.Series(True, index=f.index)

# Written before any backtest result was inspected. Thresholds are round numbers, not fitted.
RULES = [
    _rule("hhhl_bull_call_spread", "HH/HL trend: bull call spread", "BULL CALL SPREAD", BULL, "debit", "bullish",
          "Nifty's confirmed swing structure is HH/HL (two rising swing highs and two rising swing lows) and the close is above its 20-session average.",
          lambda f: f.rising & (f.close_idx > f.sma20), "trend_with_tail_hedge"),
    _rule("lhll_bear_put_spread", "LH/LL trend: bear put spread", "BEAR PUT SPREAD", BEAR, "debit", "bearish",
          "Nifty's confirmed swing structure is LH/LL (two falling swing highs and two falling swing lows) and the close is below its 20-session average.",
          lambda f: f.falling & (f.close_idx < f.sma20), "put_spread_hedge"),
    _rule("hhhl_breakout_call", "HH/HL breakout: buy call", "BUY CALL", [("CE", "atm", "BUY")], "debit", "bullish",
          "Fresh close above the last confirmed swing high while the structure is HH/HL (the HH/HL page's breakout rule applied to the index).",
          lambda f: f.breakout),
    _rule("vrp_iron_condor", "Volatility risk premium: iron condor", "IRON CONDOR", CONDOR, "defined", "neutral",
          "ATM implied volatility is in the top half of its year and at least 2 vol points above 20-session realised volatility. Sell the 20-delta call and put, buy wings about 2% further out.",
          lambda f: (f.iv_pct >= 50) & (f.vrp >= 2), "iron_condor"),
    _rule("rich_iv_short_straddle", "Very rich IV: short straddle", "SHORT STRADDLE", SHORT_STRADDLE, "margin", "neutral",
          "ATM implied volatility is in the top 20% of its year. Undefined risk: shown for evidence, not as a retail trade.",
          lambda f: f.iv_pct >= 80, "short_atm_straddle_weekly"),
    _rule("cheap_iv_long_straddle", "Cheap IV: long straddle", "LONG STRADDLE", LONG_STRADDLE, "debit", "volatility",
          "ATM implied volatility is in the bottom 20% of its year and at or below 20-session realised volatility.",
          lambda f: (f.iv_pct <= 20) & (f.vrp <= 0), "long_straddle"),
    _rule("fii_short_bear_put_spread", "FII futures short build-up: bear put spread", "BEAR PUT SPREAD", BEAR, "debit", "bearish",
          "FIIs hold 35% or less of their index-futures contracts long and that share fell over the last 5 sessions (NSE participant-wise OI).",
          lambda f: (f.fii_ratio <= 0.35) & (f.fii_ratio_chg5 < 0)),
    _rule("fii_long_bull_call_spread", "FII futures long build-up: bull call spread", "BULL CALL SPREAD", BULL, "debit", "bullish",
          "FIIs hold 60% or more of their index-futures contracts long and that share rose over the last 5 sessions.",
          lambda f: (f.fii_ratio >= 0.60) & (f.fii_ratio_chg5 > 0)),
    _rule("put_heavy_pcr_bull_call_spread", "Put-heavy PCR (contrarian): bull call spread", "BULL CALL SPREAD", BULL, "debit", "bullish",
          "All-expiry Nifty put/call open-interest ratio is 1.3 or higher (puts heavily written or bought).",
          lambda f: f.pcr >= 1.3),
    _rule("base_bull_call_spread", "Baseline: bull call spread every session", "BULL CALL SPREAD", BULL, "debit", "bullish",
          "Unconditional: the same spread taken whenever no position is open.", ALWAYS, baseline=True),
    _rule("base_bear_put_spread", "Baseline: bear put spread every session", "BEAR PUT SPREAD", BEAR, "debit", "bearish",
          "Unconditional.", ALWAYS, baseline=True),
    _rule("base_buy_call", "Baseline: buy ATM call every session", "BUY CALL", [("CE", "atm", "BUY")], "debit", "bullish",
          "Unconditional.", ALWAYS, baseline=True),
    _rule("base_iron_condor", "Baseline: iron condor every session", "IRON CONDOR", CONDOR, "defined", "neutral",
          "Unconditional.", ALWAYS, baseline=True),
    _rule("base_short_straddle", "Baseline: short straddle every session", "SHORT STRADDLE", SHORT_STRADDLE, "margin", "neutral",
          "Unconditional.", ALWAYS, baseline=True),
    _rule("base_long_straddle", "Baseline: long straddle every session", "LONG STRADDLE", LONG_STRADDLE, "debit", "volatility",
          "Unconditional.", ALWAYS, baseline=True),
]
BASELINE_FOR = {"BULL CALL SPREAD": "base_bull_call_spread", "BEAR PUT SPREAD": "base_bear_put_spread",
                "BUY CALL": "base_buy_call", "IRON CONDOR": "base_iron_condor", "SHORT STRADDLE": "base_short_straddle",
                "LONG STRADDLE": "base_long_straddle"}
RULE_BY_ID = {r["id"]: r for r in RULES}


def mark_key(opt, key):
    return f"{key}_{opt.lower()}"


def signals(f, rules=RULES):
    out = []
    for rule in rules:
        mask = (rule["cond"](f).astype("boolean").fillna(False).astype(bool) & f.valid)
        for opt, key, _ in rule["legs"]:
            if key not in f or mark_key(opt, key) not in f:
                mask &= False
                continue
            mask &= f[key].notna() & (f[mark_key(opt, key)] > 0)
        hit = f[mask]
        if hit.empty:
            continue
        frame = hit[["date", "sidx", "spot", "lot", "texp"]].copy()
        frame["symbol"], frame["kind"], frame["rule"], frame["nlegs"] = SYMBOL, "index", rule["id"], len(rule["legs"])
        for j, (opt, key, side) in enumerate(rule["legs"]):
            frame[f"l{j}_opt"], frame[f"l{j}_strike"], frame[f"l{j}_side"] = opt, hit[key], side
            frame[f"l{j}_ref"] = hit[mark_key(opt, key)]
        out.append(frame)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def capital(basis, legs, spot, lot):
    """Capital the return is measured on: net debit, max loss of a defined-risk credit, or approximate margin."""
    debit = sum(l["entry"] if l["side"] == "BUY" else -l["entry"] for l in legs)
    if basis == "debit":
        return debit * lot if debit > 0 else None
    if basis == "defined":
        calls = sorted(l["strike"] for l in legs if l["opt"] == "CE")
        puts = sorted(l["strike"] for l in legs if l["opt"] == "PE")
        width = max(calls[-1] - calls[0] if len(calls) == 2 else 0, puts[-1] - puts[0] if len(puts) == 2 else 0)
        risk = width + debit  # debit is negative for a credit
        return risk * lot if risk > 0 else None
    return od.MARGIN["index"] * spot * lot


def simulate(sig, books, sessions):
    if sig.empty:
        return pd.DataFrame()
    last, rows = sessions[-1], []
    for s in sig.itertuples(index=False):
        if s.entry_date is None:
            continue
        exit_day = s.exit_date or last
        legs, unit_pnl, filled = [], 0.0, True
        for j in range(int(s.nlegs)):
            opt, side = getattr(s, f"l{j}_opt"), getattr(s, f"l{j}_side")
            strike = round(float(getattr(s, f"l{j}_strike")), 2)
            entry = books.get(s.entry_date, {}).get((s.texp, strike, opt), (None, None))[1]
            mark = books.get(exit_day, {}).get((s.texp, strike, opt), (None, None))[0]
            if entry is None or not entry > 0 or mark is None or not mark >= 0:
                filled = False
                break
            close_side = "SELL" if side == "BUY" else "BUY"
            cost = float(od.leg_costs(np.array(entry), np.array(side), np.array("index")) +
                         od.leg_costs(np.array(mark), np.array(close_side), np.array("index")))
            unit_pnl += (mark - entry if side == "BUY" else entry - mark) - cost
            legs.append(dict(name=f"{SYMBOL} {s.texp} {strike:g} {opt}", opt=opt, strike=strike, side=side,
                             entry=round(float(entry), 2), exit=round(float(mark), 2)))
        if not filled:
            continue
        rule = RULE_BY_ID[s.rule]
        lot = float(s.lot)
        cap = capital(rule["basis"], legs, float(s.spot), lot)
        if not cap:
            continue
        pnl_lot = unit_pnl * lot - od.BROKERAGE * 2 * len(legs) * (1 + od.GST)
        rows.append(dict(rule=s.rule, symbol=SYMBOL, kind="index", signal_date=s.date, entry_date=s.entry_date,
                         exit_date=s.exit_date, closed=s.exit_date is not None,
                         legs=[{k: l[k] for k in ("name", "side", "entry", "exit")} for l in legs],
                         return_pct=100.0 * pnl_lot / cap, pnl_per_lot=pnl_lot,
                         basis={"debit": "premium", "defined": "max loss", "margin": "margin"}[rule["basis"]]))
    return pd.DataFrame(rows)


def evaluate_rules(trades):
    stats = {r["id"]: od.rule_stats(trades, r["id"]) if not trades.empty else None for r in RULES}
    out = []
    for r in RULES:
        base = stats.get(BASELINE_FOR[r["action"]]) if not r["baseline"] else None
        status = od.classify(stats[r["id"]], None if r["baseline"] or not base else base["mean_return_pct"])
        recent = []
        if not trades.empty:
            done = trades[(trades.rule == r["id"]) & trades.closed].sort_values("exit_date", ascending=False).head(15)
            recent = [dict(signal_date=t.signal_date, entry_date=t.entry_date, exit_date=t.exit_date, legs=t.legs,
                           return_pct=num(t.return_pct), pnl_per_lot=num(t.pnl_per_lot)) for t in done.itertuples()]
        empty = dict(trades=0, win_rate=None, mean_return_pct=None, median_return_pct=None, t_stat=None, worst_return_pct=None,
                     best_return_pct=None, avg_pnl_per_lot=None,
                     return_basis={"debit": "premium", "defined": "max loss", "margin": "margin"}[r["basis"]],
                     first_half=dict(trades=0, mean_return_pct=None, win_rate=None), second_half=dict(trades=0, mean_return_pct=None, win_rate=None))
        out.append(dict(id=r["id"], label=r["label"], action=r["action"], view=r["view"], baseline=r["baseline"],
                        condition=r["condition"], catalog=r["catalog"], status=status,
                        legs=[dict(option_type=o, strike_key=k, side=s) for o, k, s in r["legs"]],
                        baseline_id=None if r["baseline"] else BASELINE_FOR[r["action"]],
                        stats=stats[r["id"]] or empty, recent_trades=recent))
    return out


# ---------------------------------------------------------------- today's chain, sigma and payoff
def payoff_profile(legs, spot, lot, sigma, dte):
    """Expiry payoff per lot on a price grid, plus breakevens, max profit/loss and the model P(profit)."""
    grid = np.linspace(spot * 0.85, spot * 1.15, 241)
    pay = np.zeros_like(grid)
    for l in legs:
        intrinsic = np.maximum(grid - l["strike"], 0) if l["option_type"] == "CE" else np.maximum(l["strike"] - grid, 0)
        pay += (intrinsic - l["ref_close"]) * (1 if l["side"] == "BUY" else -1)
    pay *= lot
    slope_lo, slope_hi = pay[1] - pay[0], pay[-1] - pay[-2]
    max_profit = None if slope_hi > 1e-9 or slope_lo < -1e-9 else float(pay.max())
    max_loss = None if slope_hi < -1e-9 or slope_lo > 1e-9 else float(pay.min())
    sign = np.sign(pay)
    cross_at = np.where(np.diff(sign) != 0)[0]
    breakevens = [float(grid[i] - pay[i] * (grid[i + 1] - grid[i]) / (pay[i + 1] - pay[i])) for i in cross_at if pay[i + 1] != pay[i]]
    prob = None
    if sigma and np.isfinite(sigma) and dte and dte > 0:
        t = dte / 365.0
        edges = np.r_[grid[0] - (grid[1] - grid[0]) / 2, (grid[1:] + grid[:-1]) / 2, grid[-1] + (grid[1] - grid[0]) / 2]
        z = (np.log(edges / spot) - (od.RATE - 0.5 * sigma * sigma) * t) / (sigma * math.sqrt(t))
        cdf = od.ncdf(z)
        mass = np.diff(cdf)
        mass[0] += cdf[0]
        mass[-1] += 1 - cdf[-1]
        prob = float(100.0 * mass[pay > 0].sum())
    step = max(1, len(grid) // 60)
    return dict(max_profit=num(max_profit), max_loss=num(max_loss), breakevens=[num(b) for b in breakevens],
                prob_profit_model=num(prob, 1), curve=dict(price=[num(x) for x in grid[::step]], pnl=[num(y) for y in pay[::step]]))


def chain_snapshot(raw_nifty, as_of, spot):
    opt = raw_nifty[raw_nifty.FinInstrmTp == "IDO"]
    exps = sorted(e for e in opt.exp.unique() if dte_of(e, as_of) > 0)
    texp = next((e for e in exps if dte_of(e, as_of) >= MIN_DTE), None)
    chosen = exps[:CHAIN_EXPIRIES] + ([texp] if texp and texp not in exps[:CHAIN_EXPIRIES] else [])
    monthly = sorted({max(e for e in exps if e[:7] == m) for m in {e[:7] for e in exps}})
    out, books = [], {}
    for exp in chosen:
        dte = dte_of(exp, as_of)
        ch = opt[opt.exp == exp]
        tab = strike_table(ch, spot, dte)
        pk = picks(tab, spot, dte)
        if tab.empty or "atm" not in pk:
            continue
        sigma = pk["atm_iv"] / 100.0 if np.isfinite(pk.get("atm_iv", np.nan)) else np.nan
        t = dte / 365.0
        k = tab.strike.to_numpy(float)
        rows = []
        live = tab[(tab.ce_live | tab.pe_live)].reset_index(drop=True)
        centre = int((live.strike - spot).abs().idxmin()) if not live.empty else 0
        window = live.iloc[max(0, centre - CHAIN_WIDTH): centre + CHAIN_WIDTH + 1]
        # Smile from the liquid out-of-the-money side: puts below spot, calls above. Deep in-the-money closes are often
        # stale settlement prices whose implied vol is meaningless; by put-call parity both sides share one smile.
        otm = np.where(k < spot, tab.pe_iv, tab.ce_iv)
        other = np.where(k < spot, tab.ce_iv, tab.pe_iv)
        smile = np.where(np.isfinite(otm), otm, np.where(np.isfinite(other), other, sigma))
        tab["smile_iv"] = smile
        tab["smile_estimated"] = ~np.isfinite(otm)
        for side, call in (("ce", 1.0), ("pe", 0.0)):
            g = greeks(spot, k, t, smile, call) if np.isfinite(sigma) else {}
            for name, arr in g.items():
                tab[f"{side}_{name}"] = arr
        tab = tab.set_index("strike")
        for strike in window.strike:
            r = tab.loc[strike]
            row = dict(strike=float(strike))
            for side in ("ce", "pe"):
                lot = r[f"{side}_NewBrdLotQty"]
                oi = r[f"{side}_OpnIntrst"]
                row[side] = dict(
                    close=num(r[f"{side}_mark"]), oi=num(oi / lot, 0) if lot and np.isfinite(lot) and np.isfinite(oi) else None,
                    oi_chg=num(r[f"{side}_ChngInOpnIntrst"] / lot, 0) if lot and np.isfinite(lot) and np.isfinite(r[f"{side}_ChngInOpnIntrst"]) else None,
                    volume=num(r[f"{side}_TtlTradgVol"] / lot, 0) if lot and np.isfinite(lot) and np.isfinite(r[f"{side}_TtlTradgVol"]) else None,
                    iv=num(100 * r["smile_iv"], 2), iv_estimated=bool(r["smile_estimated"]),
                    iv_own=num(100 * r[f"{side}_iv"], 2),
                    delta=num(r.get(f"{side}_delta"), 3), gamma=num(r.get(f"{side}_gamma"), 6), theta=num(r.get(f"{side}_theta"), 2),
                    vega=num(r.get(f"{side}_vega"), 2), prob_itm=num(100 * r.get(f"{side}_prob_itm", np.nan), 1))
            rows.append(row)
        books[exp] = tab
        em = spot * sigma * math.sqrt(t) if np.isfinite(sigma) else np.nan
        straddle = pk["atm_ce"] + pk["atm_pe"]
        ce_oi, pe_oi = ch[ch.OptnTp == "CE"].OpnIntrst.sum(), ch[ch.OptnTp == "PE"].OpnIntrst.sum()
        out.append(dict(
            expiry=exp, days_to_expiry=int(dte), kind="monthly" if exp in monthly else "weekly", trade_expiry=exp == texp,
            atm=num(pk["atm"]), atm_iv=num(pk.get("atm_iv"), 2), straddle=num(straddle), straddle_pct=num(100 * straddle / spot, 2),
            expected_move=num(em), sigma_1=[num(spot - em), num(spot + em)], sigma_2=[num(spot - 2 * em), num(spot + 2 * em)],
            skew25=num(pk.get("skew25"), 2), call25_strike=num(pk.get("c25")), put25_strike=num(pk.get("p25")),
            pcr=num(pe_oi / ce_oi if ce_oi else np.nan, 3), call_wall=num(pk.get("call_wall")), put_wall=num(pk.get("put_wall")),
            max_pain=num(od.max_pain(ch)), oi_profile=od.oi_profile(ch, spot), rows=rows))
    return out, texp, books


def stock_greeks(raw, symbols, as_of):
    """ATM implied vol and Greeks for each constituent's trade expiry, from today's official bhavcopy."""
    opt = raw[(raw.FinInstrmTp == "STO") & raw.TckrSymb.isin(symbols)]
    out = {}
    for sym, ch in opt.groupby("TckrSymb"):
        spot = float(ch.UndrlygPric.median())
        exps = sorted(e for e in ch.exp.unique() if dte_of(e, as_of) >= MIN_DTE)
        if not exps or not spot > 0:
            continue
        dte = dte_of(exps[0], as_of)
        tab = strike_table(ch[ch.exp == exps[0]], spot, dte)
        pk = picks(tab, spot, dte) if not tab.empty else {}
        if "atm" not in pk or not np.isfinite(pk.get("atm_iv", np.nan)):
            continue
        sigma = pk["atm_iv"] / 100.0
        t = dte / 365.0
        gc = greeks(spot, pk["atm"], t, sigma, 1.0)
        gp = greeks(spot, pk["atm"], t, sigma, 0.0)
        out[sym] = dict(expiry=exps[0], days_to_expiry=int(dte), atm=num(pk["atm"]), atm_ce=num(pk["atm_ce"]), atm_pe=num(pk["atm_pe"]),
                        atm_iv=num(pk["atm_iv"], 2), call_delta=num(gc["delta"], 3), put_delta=num(gp["delta"], 3),
                        gamma=num(gc["gamma"], 6), call_theta=num(gc["theta"], 2), put_theta=num(gp["theta"], 2), vega=num(gc["vega"], 2),
                        lot=int(ch.NewBrdLotQty.max()),
                        expected_move_expiry=num(spot * sigma * math.sqrt(t)), expected_move_5d=num(spot * sigma * math.sqrt(7 / 365.0)),
                        skew25=num(pk.get("skew25"), 2))
    return out


# ---------------------------------------------------------------- Jev
DIRECTION = {"bullish": "The supplied structure, positioning and option data point to a rising Nifty over the next 5 sessions",
             "bearish": "The supplied facts point to a falling Nifty over the next 5 sessions",
             "range_bound": "The supplied facts point to Nifty staying inside its expected 1-sigma range",
             "insufficient": "The supplied facts are too thin or contradictory to judge"}
VOLATILITY = {"rich": "Implied volatility is high against realised volatility and its own year: option sellers are paid more than usual",
              "fair": "Implied volatility is close to realised volatility and its usual range",
              "cheap": "Implied volatility is low against realised volatility and its year: option buyers pay less than usual",
              "insufficient": "Key volatility facts are missing"}
POSITIONING = {"institutions_bullish": "FII/Pro futures and option positions supplied are net bullish",
               "institutions_bearish": "FII/Pro futures and option positions supplied are net bearish",
               "mixed": "Institutional positions point both ways",
               "insufficient": "Participant positions are missing"}
STANCE = {"bullish": "Supplied structure and option positioning favour upside over the next 5 sessions",
          "bearish": "Supplied facts favour downside over the next 5 sessions",
          "neutral": "Supplied facts are balanced or range-bound",
          "insufficient": "Facts too thin to judge"}
PLAY = {"buy_calls_or_call_spread": "A defined-risk bullish option position (long call or bull call spread) fits the supplied facts",
        "buy_puts_or_put_spread": "A defined-risk bearish option position (long put or bear put spread) fits the supplied facts",
        "sell_premium_defined_risk": "Rich implied volatility with no clear direction: a defined-risk premium sale (iron condor / credit spread) fits",
        "no_trade": "No option position is justified by the supplied facts"}


def _setup_criteria(rules):
    crit = {r["id"]: f"{r['label']} ({r['action']}); status {r['status']}" for r in rules if not r["baseline"]}
    crit["no_trade"] = "No setup in the supplied list both triggered today and has validated history: stay flat"
    return crit


def jev_review(index_state, rules, constituents, log=print):
    try:
        from jev_client import Client, JevError, MODEL
    except ImportError:
        return dict(state="failed", model="", assessed=0, message="jev_client unavailable"), None
    if not os.environ.get("TYPESAFE_API_KEY"):
        return dict(state="skipped", model=MODEL, assessed=0, message="TYPESAFE_API_KEY not configured; Jev not run"), None
    client, index_answer, done = Client(), None, 0
    try:
        questions = {
            "direction": od._choice("Assess Nifty 50's likely direction over the next 5 sessions from the supplied swing structure, "
                                    "futures and option positioning and participant open interest.", DIRECTION),
            "volatility": od._choice("Assess whether Nifty option implied volatility is rich, fair or cheap from the supplied ATM IV, "
                                     "IV percentile, realised volatility, India VIX and skew.", VOLATILITY),
            "positioning": od._choice("Assess the net stance of institutional participants (FII and Pro) from the supplied "
                                      "participant-wise open interest and its 5-session change.", POSITIONING),
            "setup": od._choice("Choose the one setup that best fits the supplied facts today. Only a setup listed as triggered today "
                                "can be chosen as a trade; a setup that is not VALIDATED or has a non-positive historical mean "
                                "should weigh toward no_trade.", _setup_criteria(rules)),
            "risk": od._choice("Assess position-specific risk for a Nifty option position opened at the next open and held 5 "
                               "sessions, from supplied facts only (expiry distance, IV level, distance to OI walls, VIX).", od.RISK),
        }
        a = client.ask(index_state, questions)
        index_answer = {k: dict(choice=v["choice"], confidence=num(v["confidence"], 3),
                                probabilities={c: num(p, 3) for c, p in v["probabilities"].items()}) for k, v in a.items()}
        done += 1
        for start in range(0, len(constituents), 5):
            batch = constituents[start:start + 5]
            state, qs = {"session": index_state["session"], "nifty": index_state["summary"], "stocks": []}, {}
            for i, c in enumerate(batch):
                state["stocks"].append(c["jev_state"])
                prefix = f"For stock {c['symbol']} in state.stocks[{i}]: "
                qs[f"d{i}"] = od._choice(prefix + "Assess the 5-session stance from its HH/HL swing status, futures build-up, put/call "
                                         "ratio, implied volatility and the option desk's rule result.", STANCE)
                qs[f"p{i}"] = od._choice(prefix + "Choose the option approach that fits the supplied facts. A desk rule that is not "
                                         "VALIDATED is information only, not evidence of edge.", PLAY)
                qs[f"r{i}"] = od._choice(prefix + "Assess position-specific risk from supplied facts only (IV level, expiry distance, "
                                         "distance to OI walls, any supplied events).", od.RISK)
            ans = client.ask(state, qs)
            for i, c in enumerate(batch):
                c["jev"] = dict(stance=ans[f"d{i}"]["choice"], stance_confidence=num(ans[f"d{i}"]["confidence"], 3),
                                play=ans[f"p{i}"]["choice"], play_confidence=num(ans[f"p{i}"]["confidence"], 3),
                                risk=ans[f"r{i}"]["choice"], risk_confidence=num(ans[f"r{i}"]["confidence"], 3))
                done += 1
    except JevError as exc:
        log(f"Jev stopped: {exc}")
        state = "failed" if index_answer is None else "partial"
        return dict(state=state, model=MODEL, assessed=done, message=f"Jev stopped after {done} reviews: {exc}"), index_answer
    return dict(state="ok", model=MODEL, assessed=done,
                message=f"Jev reviewed the index and {done - 1} constituents ({client.calls} requests, {client.input_tokens} input tokens)."), index_answer


def archive(as_of, jev, index_answer, constituents, today_setups, force=False):
    HIST.mkdir(parents=True, exist_ok=True)
    path = HIST / f"{as_of}.json"
    if path.exists() and not force:
        old = json.loads(path.read_text(encoding="utf-8"))
        if old.get("jev_state") == "ok" or jev.get("state") != "ok":
            return old
    record = dict(version=VERSION, as_of=as_of, archived_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                  jev_state=jev.get("state"), index=index_answer, setups=[s["rule"] for s in today_setups],
                  stocks={c["symbol"]: c.get("jev") for c in constituents if c.get("jev")})
    path.write_text(json.dumps(od.clean(record), separators=(",", ":"), allow_nan=False), encoding="utf-8")
    return record


def calibration(f):
    """Score archived Jev index direction calls once their 5-session window has closed."""
    out = {k: dict(n=0, hits=0) for k in DIRECTION}
    stock = dict(n=0, hits=0)
    spot = dict(zip(f.date, f.spot))
    dates = list(f.date)
    for path in sorted(HIST.glob("*.json")) if HIST.exists() else []:
        rec = json.loads(path.read_text(encoding="utf-8"))
        day = rec.get("as_of")
        if day not in spot or dates.index(day) + HOLD >= len(dates) or not rec.get("index"):
            continue
        ret = spot[dates[dates.index(day) + HOLD]] / spot[day] - 1
        call = (rec["index"].get("direction") or {}).get("choice")
        if call in out:
            out[call]["n"] += 1
            out[call]["hits"] += int((call == "bullish" and ret > 0) or (call == "bearish" and ret < 0)
                                     or (call == "range_bound" and abs(ret) < 0.015))
    matured = sum(v["n"] for v in out.values())
    return dict(matured=matured, by_call=out, stocks=stock,
                note="Bullish counts a hit if Nifty is higher 5 sessions later, bearish if lower, range-bound if within 1.5%.")


# ---------------------------------------------------------------- build
def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def participant_today(f, as_of):
    row = f[f.date == as_of]
    if row.empty or pd.isna(row.iloc[0].get("fii_fut_long")):
        return None
    r = row.iloc[0]
    hist = f[f.sidx > r.sidx - 5]
    prev = f[f.sidx == r.sidx - 5]
    p0 = prev.iloc[0] if not prev.empty else None
    out = []
    for who in PARTICIPANTS:
        w = who.lower()
        g = lambda k, src=r: src.get(f"{w}_{k}") if src is not None else None
        net = lambda src: (None if src is None or pd.isna(src.get(f"{w}_fut_long")) else dict(
            futures=int(src[f"{w}_fut_long"] - src[f"{w}_fut_short"]),
            calls=int(src[f"{w}_call_long"] - src[f"{w}_call_short"]),
            puts=int(src[f"{w}_put_long"] - src[f"{w}_put_short"])))
        now, then = net(r), net(p0)
        out.append(dict(participant=who, fut_long=int(g("fut_long")), fut_short=int(g("fut_short")),
                        call_long=int(g("call_long")), call_short=int(g("call_short")),
                        put_long=int(g("put_long")), put_short=int(g("put_short")),
                        fut_long_share=num(100 * r[f"{w}_ratio"], 1), fut_long_share_chg5=num(100 * r[f"{w}_ratio_chg5"], 1),
                        net=now, net_chg5={k: now[k] - then[k] for k in now} if then else None,
                        read=read_participant(who, now, r[f"{w}_ratio"])))
    del hist
    return out


def read_participant(who, net, ratio):
    if not net:
        return ""
    bias = []
    bias.append(f"index futures {net['futures']:+,} contracts net ({100 * ratio:.0f}% long)" if np.isfinite(ratio) else f"index futures {net['futures']:+,} net")
    bias.append(f"calls {net['calls']:+,} net ({'net buyers' if net['calls'] > 0 else 'net writers'})")
    bias.append(f"puts {net['puts']:+,} net ({'net buyers' if net['puts'] > 0 else 'net writers'})")
    return f"{who}: " + "; ".join(bias) + "."


def build(offline=False, use_jev=True, end=None, if_new=False, force_archive=False, log=print):
    end = end or dt.date.today()
    if not offline:
        fetched, missing = od.download(end)
        log(f"bhavcopies: {len(fetched)} new; {len(missing)} weekdays without a file")
    sessions = od.sessions_available(end)
    if len(sessions) < 80:
        raise SystemExit(f"Only {len(sessions)} sessions available; need at least 80")
    as_of = sessions[-1]
    desk, hhhl = read_json(DESK), read_json(HHHL)
    if if_new and OUT.exists():
        cur = read_json(OUT)
        src = cur.get("inputs", {})
        if (cur.get("as_of") == as_of and cur.get("model_version") == VERSION and cur.get("jev", {}).get("state") == "ok"
                and src.get("options_desk_as_of") == desk.get("as_of") and src.get("hhhl_as_of") == hhhl.get("as_of")):
            log(f"nifty chain {as_of} already built with a Jev review and current inputs; nothing to do")
            return None
    feat, books = load_features(sessions, log=log)
    ohlc, appended = index_ohlc(sessions, offline)
    part = participant_frame(sessions, offline, log=log)
    f = derive(feat, ohlc, part, sessions)
    sig = od.non_overlapping(signals(f), sessions)
    trades = simulate(sig, books, sessions)
    rules = evaluate_rules(trades)
    rule_info = {r["id"]: r for r in rules}
    skip = od.holidays()
    nxt = od.next_sessions(as_of, HOLD, skip)
    today = f[f.date == as_of]
    if today.empty:
        raise SystemExit(f"No NIFTY option chain for {as_of}")
    t0 = today.iloc[0]

    raw_today = od.read_raw(as_of)
    raw_nifty = nifty_day(as_of)
    spot = float(t0.spot)
    expiries, texp, chain_books = chain_snapshot(raw_nifty, as_of, spot)
    trade_tab = chain_books.get(texp)

    # Setups that fire today (non-baseline), with legs, Greeks per lot and the expiry payoff.
    today_sig = sig[sig.date == as_of] if not sig.empty else pd.DataFrame()
    fired_today = signals(today, [r for r in RULES if not r["baseline"]]) if t0.valid else pd.DataFrame()
    setups = []
    sigma_t = float(t0.atm_iv) / 100.0 if np.isfinite(t0.atm_iv) else np.nan
    for s in fired_today.itertuples(index=False) if not fired_today.empty else []:
        info = rule_info[s.rule]
        legs, pos = [], dict(delta=0.0, gamma=0.0, theta=0.0, vega=0.0)
        for j in range(int(s.nlegs)):
            opt, side, strike = getattr(s, f"l{j}_opt"), getattr(s, f"l{j}_side"), float(getattr(s, f"l{j}_strike"))
            leg = dict(name=f"{SYMBOL} {s.texp} {strike:g} {opt}", option_type=opt, strike=strike, expiry=s.texp, side=side,
                       ref_close=num(getattr(s, f"l{j}_ref")), lot=int(s.lot))
            if trade_tab is not None and strike in trade_tab.index:
                col = "ce" if opt == "CE" else "pe"
                sgn = 1 if side == "BUY" else -1
                for g in pos:
                    v = trade_tab.loc[strike].get(f"{col}_{g}")
                    leg[g] = num(v, 6 if g == "gamma" else 3)
                    if v is not None and np.isfinite(v):
                        pos[g] += sgn * float(v) * int(s.lot)
            legs.append(leg)
        setups.append(dict(rule=s.rule, label=info["label"], action=info["action"], view=info["view"], status=info["status"],
                           condition=info["condition"], legs=legs,
                           position_greeks_per_lot={k: num(v, 4 if k == "gamma" else 2) for k, v in pos.items()},
                           payoff=payoff_profile(legs, spot, int(s.lot), sigma_t, int(t0.dte)),
                           plan=dict(entry="Next session's official open; skip any leg that does not trade",
                                     exit_after_sessions=HOLD, exit_by=nxt[-1],
                                     payoff_note="The payoff, breakevens and model probability use today's closing premium as a "
                                                 "proxy for the next-open entry; the backtest uses the actual official open.")))
    validated = sorted([s for s in setups if s["status"] == "VALIDATED"],
                       key=lambda s: -(rule_info[s["rule"]]["stats"]["t_stat"] or 0))
    best = dict(rule=validated[0]["rule"], label=validated[0]["label"],
                reason="Triggered today and VALIDATED on official contract prices (highest t-stat among today's validated setups).") if validated else dict(
        rule=None, label="No validated setup today",
        reason=("Setups fired today but none has validated history, so they are information only." if setups
                else "No setup's trigger condition is met today.") + " Staying flat is a position.")

    # Rule conditions as they stand today, so a reader can see how close each trigger is.
    def val(col, digits=2):
        return num(t0.get(col), digits) if col in t0 else None
    state_now = dict(structure=t0.get("structure"), rising=bool(t0.rising), falling=bool(t0.falling), breakout=bool(t0.breakout),
                     close=val("close_idx"), sma20=val("sma20"), sma50=val("sma50"), confirmed_high=val("confirmed_high"),
                     confirmed_low=val("confirmed_low"), iv_pct=val("iv_pct", 0), vrp=val("vrp"), pcr=val("pcr", 3),
                     fii_long_share=num(100 * t0.fii_ratio, 1) if pd.notna(t0.get("fii_ratio")) else None,
                     fii_long_share_chg5=num(100 * t0.fii_ratio_chg5, 1) if pd.notna(t0.get("fii_ratio_chg5")) else None)

    # Index snapshot from NSE's official index file.
    ic = index_close(as_of, offline) or {}
    n50, vix, bank = ic.get("Nifty 50") or {}, ic.get("India VIX") or {}, ic.get("Nifty Bank") or {}
    fut_close = float(t0.fut_close) if np.isfinite(t0.fut_close) else None
    index = dict(
        close=num(n50.get("close") or spot), open=num(n50.get("open")), high=num(n50.get("high")), low=num(n50.get("low")),
        change=num(n50.get("change")), change_pct=num(n50.get("change_pct")), pe=num(n50.get("pe")), pb=num(n50.get("pb")),
        div_yield=num(n50.get("div_yield")), option_spot=num(spot), vix=num(vix.get("close")), vix_change_pct=num(vix.get("change_pct")),
        bank_nifty=num(bank.get("close")), bank_nifty_change_pct=num(bank.get("change_pct")),
        futures_close=num(fut_close), basis=num(fut_close - spot if fut_close else None),
        ret5_pct=num(100 * t0.ret5 if pd.notna(t0.ret5) else None), z5=num(t0.z5), rv20=num(t0.rv20), atm_iv=num(t0.atm_iv),
        iv_pct=num(t0.iv_pct, 0), vrp=num(t0.vrp), pcr=num(t0.pcr, 3), pcr_chg5=num(t0.pcr_chg5, 3),
        fut_oi5_pct=num(100 * t0.foi5 if pd.notna(t0.foi5) else None, 1),
        buildup=od.buildup(num(100 * t0.ret5) if pd.notna(t0.ret5) else None, num(100 * t0.foi5, 1) if pd.notna(t0.foi5) else None),
        lot=int(t0.lot), trade_expiry=texp, official_close_file=bool(n50), structure=state_now)

    # HH/HL swing chart for the index (confirmed pivots only).
    import hhhl_scanner as hs
    recent = ohlc.iloc[-HISTORY:]
    pivots = hs.pivot_events(ohlc)
    swings = [p for p in hs.chart_swings(pivots, str(recent.index[0].date())) if p["confirmed_on"] <= as_of] if len(recent) else []
    hhhl_chart = dict(dates=[str(d.date()) for d in recent.index], open=[num(v) for v in recent.Open], high=[num(v) for v in recent.High],
                      low=[num(v) for v in recent.Low], close=[num(v) for v in recent.Close],
                      sma20=[num(v) for v in ohlc.Close.rolling(20).mean().iloc[-HISTORY:]], swings=swings,
                      appended_official_sessions=appended)

    hist = f[f.sidx > f.sidx.max() - HISTORY]
    vix_hist = []
    for d in hist.date.tolist()[-60:]:
        v = (index_close(d, offline) or {}).get("India VIX") or {}
        vix_hist.append(num(v.get("close")))
    history = dict(dates=hist.date.tolist(), spot=[num(v) for v in hist.spot], atm_iv=[num(v) for v in hist.atm_iv],
                   rv20=[num(v) for v in hist.rv20], pcr=[num(v, 3) for v in hist.pcr],
                   fii_long_share=[num(100 * v, 1) for v in hist.fii_ratio], client_long_share=[num(100 * v, 1) for v in hist.client_ratio],
                   fii_net_calls=[num(a - b, 0) for a, b in zip(hist.fii_call_long, hist.fii_call_short)],
                   fii_net_puts=[num(a - b, 0) for a, b in zip(hist.fii_put_long, hist.fii_put_short)],
                   vix_dates=hist.date.tolist()[-60:], vix=vix_hist)
    part_today = participant_today(f, as_of)

    # Nifty 50 constituents: HH/HL status, option-desk positioning, Greeks, then Jev.
    members, list_source = nifty50_list(offline)
    desk_rows = {r["symbol"]: r for r in desk.get("rows", [])}
    hhhl_rows = {r["symbol"]: r for r in hhhl.get("rows", [])}
    sg = stock_greeks(raw_today, [m["symbol"] for m in members], as_of)
    constituents = []
    for m in members:
        sym = m["symbol"]
        d, h, g = desk_rows.get(sym, {}), hhhl_rows.get(sym, {}), sg.get(sym, {})
        fired = [dict(rule=s["rule"], action=s["action"], status=s["status"]) for s in d.get("signals", [])]
        c = dict(symbol=sym, name=m["name"], industry=m["industry"],
                 hhhl_status=h.get("status"), structure=h.get("structure"), hhhl_reason=h.get("reason"),
                 distance_to_breakout_pct=h.get("distance_to_breakout_pct"), last_breakout_date=h.get("last_breakout_date"),
                 spot=d.get("spot"), ret5_pct=d.get("ret5_pct"), z5=d.get("z5"), buildup=d.get("buildup"), pcr=d.get("pcr"),
                 pcr_chg5=d.get("pcr_chg5"), iv_pct=d.get("iv_pct"), call_wall=d.get("call_wall"), put_wall=d.get("put_wall"),
                 max_pain=d.get("max_pain"), desk_bucket=d.get("bucket"), desk_action=d.get("action"), desk_signals=fired,
                 greeks=g or None, jev=None)
        c["jev_state"] = dict(
            symbol=sym, sector=m["industry"], hhhl_status=c["hhhl_status"], swing_structure=c["structure"],
            hhhl_reason=c["hhhl_reason"], distance_to_breakout_pct=c["distance_to_breakout_pct"], spot=c["spot"],
            return_5d_pct=c["ret5_pct"], move_in_sigma=c["z5"], futures_buildup=c["buildup"], put_call_oi_ratio=c["pcr"],
            put_call_ratio_change_5d=c["pcr_chg5"], atm_iv_pct=g.get("atm_iv"), iv_percentile_1y=c["iv_pct"],
            call_wall=c["call_wall"], put_wall=c["put_wall"], max_pain=c["max_pain"], days_to_expiry=g.get("days_to_expiry"),
            expected_move_5d=g.get("expected_move_5d"), skew25_vol_points=g.get("skew25"),
            option_desk_rules_fired=fired, company_events_in_hold_window=d.get("events") or [])
        constituents.append(c)

    rule_summary = [dict(id=r["id"], label=r["label"], action=r["action"], status=r["status"], triggered_today=any(s["rule"] == r["id"] for s in setups),
                         history={k: r["stats"].get(k) for k in ("trades", "win_rate", "mean_return_pct", "t_stat", "worst_return_pct", "return_basis")})
                    for r in rules if not r["baseline"]]
    trade_exp = next((e for e in expiries if e["trade_expiry"]), expiries[0] if expiries else {})
    near_exp = expiries[0] if expiries else {}
    summary = dict(close=index["close"], change_pct=index["change_pct"], return_5d_pct=index["ret5_pct"], move_in_sigma=index["z5"],
                   swing_structure=state_now["structure"], close_vs_sma20=state_now["close"] and state_now["sma20"] and num(100 * (state_now["close"] / state_now["sma20"] - 1)),
                   atm_iv_pct=index["atm_iv"], iv_percentile_1y=index["iv_pct"], realised_vol_20d=index["rv20"], india_vix=index["vix"],
                   put_call_oi_ratio=index["pcr"], futures_buildup=index["buildup"])
    index_state = dict(
        session=as_of, summary=summary,
        index=dict(**summary, confirmed_swing_high=state_now["confirmed_high"], confirmed_swing_low=state_now["confirmed_low"],
                   vol_risk_premium_points=index["vrp"], futures_basis_points=index["basis"], put_call_ratio_change_5d=index["pcr_chg5"],
                   futures_oi_change_5d_pct=index["fut_oi5_pct"]),
        trade_expiry={k: trade_exp.get(k) for k in ("expiry", "days_to_expiry", "atm_iv", "straddle", "expected_move", "sigma_1", "skew25",
                                                    "pcr", "call_wall", "put_wall", "max_pain")},
        nearest_expiry={k: near_exp.get(k) for k in ("expiry", "days_to_expiry", "atm_iv", "expected_move", "call_wall", "put_wall", "max_pain")},
        participants=[{k: p[k] for k in ("participant", "fut_long_share", "fut_long_share_chg5", "net", "net_chg5")} for p in part_today or []],
        setups=rule_summary)

    jev, index_answer = (jev_review(index_state, rules, constituents, log=log) if use_jev
                         else (dict(state="skipped", model="", assessed=0, message="Jev disabled for this run"), None))
    record = archive(as_of, jev, index_answer, constituents, setups, force=force_archive)
    if jev["state"] != "ok" and record.get("jev_state") == "ok":
        index_answer = record.get("index")
        for c in constituents:
            c["jev"] = c["jev"] or (record.get("stocks") or {}).get(c["symbol"])
        jev = dict(state="ok", model=jev.get("model", ""), assessed=1 + len(record.get("stocks") or {}),
                   message="Reused this session's archived Jev review")
    jev["index"] = index_answer
    jev["calibration"] = calibration(f)
    for c in constituents:
        c.pop("jev_state", None)

    research = read_json(RESEARCH)
    breadth = dict(total=len(constituents),
                   hhhl={s: sum(c["hhhl_status"] == s for c in constituents) for s in ("BUY", "WATCH", "SELL", "CAUTION", "AVOID")},
                   structure_hh_hl=sum((c["structure"] or "").startswith("HH / HL") for c in constituents),
                   buildup={b: sum(c["buildup"] == b for c in constituents) for b in ("Long build-up", "Short build-up", "Short covering", "Long unwinding")},
                   jev_stance={s: sum((c["jev"] or {}).get("stance") == s for c in constituents) for s in STANCE})
    weekdays = pd.bdate_range(sessions[0], sessions[-1]).strftime("%Y-%m-%d")
    data = dict(
        version=1, model_version=VERSION, symbol=SYMBOL, as_of=as_of,
        generated_at=dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat(timespec="seconds"),
        next_session=nxt[0],
        source=dict(name="NSE UDiFF F&O bhavcopy, NSE participant-wise OI and NSE index close file (official end-of-day files)",
                    bhavcopy_url=od.URL.replace("{d}", "YYYYMMDD"), participant_url=PART_URL.replace("{d}", "DDMMYYYY"),
                    index_url=INDEX_URL.replace("{d}", "DDMMYYYY"), constituents_url=N50_URL, constituents_source=list_source,
                    sessions=len(sessions), first_session=sessions[0], last_session=as_of,
                    participant_sessions=int(f.fii_fut_long.notna().sum()),
                    missing_sessions=[d for d in weekdays if d not in set(sessions) and d not in skip]),
        inputs=dict(options_desk_as_of=desk.get("as_of"), hhhl_as_of=hhhl.get("as_of"),
                    stale=[n for n, v in (("options desk", desk.get("as_of")), ("HH/HL scan", hhhl.get("as_of"))) if v != as_of]),
        method=dict(
            hold_sessions=HOLD,
            greeks="Black-Scholes on the official closing premium and the underlying price in the bhavcopy, risk-free rate 6.5%. Theta is per calendar day, vega per 1 volatility point. Contracts whose close cannot be inverted use the expiry's ATM IV (marked estimated).",
            sigma="Expected move = spot x ATM IV x sqrt(days to expiry / 365). About 68% of outcomes fall inside 1 sigma and 95% inside 2 sigma if prices were lognormal; real markets have fatter tails.",
            entry="Signal on the session close; entry at the next session's official open of every leg. No fill if a leg did not trade.",
            exit=f"Close of the {HOLD}th session held (settlement price if untraded). Contracts expire at least {MIN_DTE} days after the signal.",
            cost_model="Same as the options desk: slippage max(Rs 0.05, 0.5% of premium) per transaction, NSE charges + 18% GST, 0.1% STT on sold premium, stamp duty, Rs 20 brokerage per order.",
            return_basis="Debit structures: return on net premium paid. Iron condor: return on maximum loss. Short straddle: return on approximate margin of 12% of notional.",
            validation="VALIDATED needs at least 60 closed trades, a date-clustered t-stat of at least 2, a positive mean in both halves and a higher mean than the same structure taken every session. WEAK: positive but fails a test. NO_EDGE: mean at or below zero. INSUFFICIENT: under 30 trades.",
            no_lookahead="Every trigger uses data published up to the signal session; swing pivots count only once confirmed two sessions later; strikes are fixed from that session's chain."),
        index=index, expiries=expiries, hhhl=hhhl_chart, history=history, participants=part_today,
        rules=rules, setups=setups, best_setup=best, constituents=constituents, constituents_count=len(constituents),
        breadth=breadth, jev=jev, research=research,
        limitations=[
            "End-of-day data only: no intraday prices, bid-ask spreads or order book. Real fills, especially in far strikes, can be worse than the modelled slippage.",
            "Greeks are model values from closing prices; they move continuously during the session.",
            "Participant-wise OI is published after the close and counts contracts, not premium or delta.",
            "Sold options can lose far more than the premium received; a single gap can erase many winning trades.",
            f"{sum(not r['baseline'] for r in RULES)} rules were tested; one passing by chance is possible. Historical edge can disappear.",
            "Jev classifies the supplied numbers only. Its confidence is not a probability of profit; its calls are scored as they mature.",
            "Paper research. Not investment advice. No orders are placed."],
    )
    data = od.clean(data)
    temp = OUT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, separators=(",", ":"), allow_nan=False, ensure_ascii=False), encoding="utf-8")
    temp.replace(OUT)
    log(f"nifty chain {as_of}: spot {spot:.2f}; {len(expiries)} expiries; {len(trades)} backtest trades; "
        f"rules {[(r['id'], r['status']) for r in rules if not r['baseline']]}; setups today {[s['rule'] for s in setups]}; "
        f"{len(constituents)} constituents; jev {jev['state']} ({jev.get('assessed')})")
    return data


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--offline", action="store_true", help="use cached files only")
    p.add_argument("--no-jev", action="store_true")
    p.add_argument("--if-new", action="store_true", help="skip when this session is already built with Jev and current inputs")
    p.add_argument("--force-archive", action="store_true")
    p.add_argument("--end", help="YYYY-MM-DD")
    a = p.parse_args()
    build(offline=a.offline, use_jev=not a.no_jev, end=dt.date.fromisoformat(a.end) if a.end else None,
          if_new=a.if_new, force_archive=a.force_archive)


if __name__ == "__main__":
    main()
