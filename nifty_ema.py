#!/usr/bin/env python3
"""Nifty 50 EMA Lab — which EMA period on which candle timeframe best tells you Nifty's direction.

Rule tested (exactly what a trader means by "close above the EMA"):
    LONG  when a candle CLOSES above EMA(n)      SHORT when a candle CLOSES below EMA(n)
    Positions flip on the opposite close. Intraday timeframes are flat at each session's last
    candle (no overnight risk); the next session starts on whichever side its first close says.
    Every round trip pays COST_PTS Nifty points (spread + brokerage + slippage).

Grid: EMA 3..50 plus 55, 60, 89, 100, 144, 200  x  timeframes 5m (reference), 15m, 30m, 1h, 2h, 1D.
Also: two-EMA crossovers (fast 5/8/9/10/13 vs slow 20/21/26/34/50) on every timeframe.

Windows per combination: full history, the last 60 sessions (same window for every timeframe, so
they are comparable) and the last 10 sessions. Ranking arithmetic stays in code; Jev then judges
the top finalists' reliability and whether the recent edge is improving, stable or degrading.
The chosen EMA = 60% code score + 40% Jev score. Jev failures are reported, never invented.

Output: docs/nifty.json (+ public/data) for docs/nifty.html. Paper research, not advice.
"""
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
PUBLIC = ROOT / "public" / "data"
CACHE = ROOT / "data" / "nifty"
IST = ZoneInfo("Asia/Kolkata")
SYMBOL = "^NSEI"

COST_PTS = 1.5                      # Nifty points per round trip
EMA_PERIODS = list(range(3, 51)) + [55, 60, 89, 100, 144, 200]
PAIR_FAST = [5, 8, 9, 10, 13]
PAIR_SLOW = [20, 21, 26, 34, 50]
TF_MIN = {"5m": 5, "15m": 15, "30m": 30, "1h": 60, "2h": 120, "1D": None}
ELIGIBLE_TF = ["15m", "30m", "1h", "2h", "1D"]   # 5m shown as a reference only
COMMON_SESSIONS = 60
RECENT_SESSIONS = 10
MIN_TRADES_COMMON = 8
FINALISTS = 10
EXPORT_BARS = {"5m": 900, "15m": 1600, "30m": 800, "1h": 900, "2h": 500, "1D": 700}


# ── data ──────────────────────────────────────────────────────────────────────

def _flatten(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[[c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]]


def _fetch(interval, period):
    import yfinance as yf
    df = yf.download(SYMBOL, period=period, interval=interval, progress=False, auto_adjust=False)
    return _flatten(df).dropna(subset=["Close"])


def _merge_cache(name, fresh):
    """Keep every bar we have ever downloaded, so short intraday histories grow over time."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{name}.csv"
    old = pd.DataFrame()
    if path.exists():
        old = pd.read_csv(path, index_col=0)
        old.index = pd.to_datetime(old.index, utc=True)
    if fresh is not None and not fresh.empty:
        idx = fresh.index
        fresh.index = (idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC"))
        old = pd.concat([old, fresh])
    if old.empty:
        raise SystemExit(f"No Nifty data for {name} (download failed and no cache).")
    old = old[~old.index.duplicated(keep="last")].sort_index()
    old.to_csv(path)
    return old


def load_data(now=None):
    now = now or datetime.now(IST)
    raw = {}
    for name, interval, period in (("5m", "5m", "60d"), ("15m", "15m", "60d"),
                                   ("60m", "60m", "730d"), ("1d", "1d", "10y")):
        try:
            fresh = _fetch(interval, period)
        except Exception as e:  # network/vendor errors fall back to the cache
            print(f"warn: {name} download failed ({type(e).__name__}); using cache")
            fresh = None
        raw[name] = _merge_cache(name, fresh)

    frames = {}
    for name, tf in (("5m", "5m"), ("15m", "15m"), ("60m", "1h")):
        df = raw[name].copy()
        df.index = df.index.tz_convert(IST)
        t = df.index.time
        df = df[(t >= datetime.strptime("09:15", "%H:%M").time()) &
                (t < datetime.strptime("15:30", "%H:%M").time())]
        frames[tf] = _drop_forming(df, TF_MIN[tf], now)
    frames["30m"] = _group_session(frames["15m"], 2)
    frames["2h"] = _group_session(frames["1h"], 2)

    d = raw["1d"].copy()
    d.index = d.index.tz_convert(IST).normalize().tz_localize(None)
    if now.hour * 60 + now.minute < 15 * 60 + 35:          # today's daily bar still forming
        d = d[d.index.date < now.date()]
    frames["1D"] = d[~d.index.duplicated(keep="last")]

    for tf, df in frames.items():
        df = df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
        if "Volume" not in df:
            df["Volume"] = 0.0
        df["session"] = [str(x.date()) for x in df.index]
        frames[tf] = df
    return frames


def _drop_forming(df, minutes, now):
    if df.empty:
        return df
    ends = df.index + pd.Timedelta(minutes=minutes)
    return df[ends <= pd.Timestamp(now)]


def _group_session(df, k):
    """Merge every k consecutive bars inside one session (09:15-anchored, never across days)."""
    if df.empty:
        return df
    g = df.copy()
    g["_d"] = g.index.date
    g["_n"] = g.groupby("_d").cumcount() // k
    rows, idx = [], []
    for _, grp in g.groupby(["_d", "_n"], sort=True):
        idx.append(grp.index[0])
        rows.append({"Open": grp["Open"].iloc[0], "High": grp["High"].max(), "Low": grp["Low"].min(),
                     "Close": grp["Close"].iloc[-1], "Volume": grp["Volume"].sum()})
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx))


# ── indicators & backtest ─────────────────────────────────────────────────────

def ema(values, period):
    return pd.Series(values).ewm(span=period, adjust=False).mean().to_numpy()


def side_close_vs_ema(close, period):
    s = np.sign(close - ema(close, period))
    return _ffill_zero(s)


def side_cross(close, fast, slow):
    return _ffill_zero(np.sign(ema(close, fast) - ema(close, slow)))


def _ffill_zero(s):
    s = s.astype(float).copy()
    for i in range(1, len(s)):
        if s[i] == 0:
            s[i] = s[i - 1]
    return s


def backtest(df, side, intraday, warm, cost=COST_PTS):
    """Trades: [entry_i, exit_i, side, entry, exit, pts_net, reason]. Open position returned too."""
    close = df["Close"].to_numpy()
    sess = df["session"].to_numpy()
    n = len(close)
    trades, pos, ei = [], 0, None
    for i in range(warm, n):
        last_of_session = intraday and (i == n - 1 or sess[i + 1] != sess[i])
        s = side[i]
        if pos != 0 and s != pos:
            trades.append((ei, i, pos, close[ei], close[i], (close[i] - close[ei]) * pos - cost, "flip"))
            pos = 0
        if pos == 0 and s != 0 and not (intraday and last_of_session):
            pos, ei = int(s), i
        if intraday and last_of_session and pos != 0:
            trades.append((ei, i, pos, close[ei], close[i], (close[i] - close[ei]) * pos - cost, "session_end"))
            pos = 0
    open_pos = (ei, pos) if pos != 0 else None
    return trades, open_pos


def metrics(trades, df, sessions):
    close = df["Close"].to_numpy()
    sess = df["session"].to_numpy()
    sel = [t for t in trades if sess[t[0]] in sessions]
    n = len(sel)
    if n == 0:
        return {"trades": 0, "win_rate": None, "pf": None, "net": 0.0, "avg": None, "max_dd": 0.0,
                "per_session": 0.0, "follow": None, "long_net": 0.0, "short_net": 0.0, "avg_bars": None}
    pts = np.array([t[5] for t in sel])
    wins = pts[pts > 0].sum()
    losses = -pts[pts < 0].sum()
    pf = float(wins / losses) if losses > 0 else (10.0 if wins > 0 else 0.0)
    eq = np.cumsum(pts)
    dd = float((np.maximum.accumulate(np.concatenate([[0], eq])) - np.concatenate([[0], eq])).max())
    follow = []
    for t in sel:
        j = t[0] + 1
        if j < len(close):
            follow.append((close[j] - close[t[0]]) * t[2] > 0)
    return {
        "trades": n,
        "win_rate": round(float((pts > 0).mean() * 100), 1),
        "pf": round(min(pf, 10.0), 2),
        "net": round(float(pts.sum()), 1),
        "avg": round(float(pts.mean()), 2),
        "max_dd": round(dd, 1),
        "per_session": round(n / max(1, len(sessions)), 2),
        "follow": round(float(np.mean(follow) * 100), 1) if follow else None,
        "long_net": round(float(sum(t[5] for t in sel if t[2] > 0)), 1),
        "short_net": round(float(sum(t[5] for t in sel if t[2] < 0)), 1),
        "avg_bars": round(float(np.mean([t[1] - t[0] for t in sel])), 1),
    }


def per_session_net(trades, df, sessions):
    sess = df["session"].to_numpy()
    out = {s: 0.0 for s in sessions}
    for t in trades:
        s = sess[t[0]]
        if s in out:
            out[s] += t[5]
    return [round(out[s], 1) for s in sessions]


def evaluate(frames, common_dates, recent_dates):
    rows, pair_rows, trade_book = [], [], {}
    for tf, df in frames.items():
        if len(df) < 120:
            continue
        intraday = TF_MIN[tf] is not None
        close = df["Close"].to_numpy()
        all_sessions = sorted(set(df["session"]))
        tf_common = [s for s in common_dates if s in set(all_sessions)]
        tf_recent = [s for s in recent_dates if s in set(all_sessions)]
        for p in EMA_PERIODS:
            warm = 3 * p
            if warm >= len(df) - 60:
                continue
            trades, open_pos = backtest(df, side_close_vs_ema(close, p), intraday, warm)
            key = f"{tf}|{p}"
            trade_book[key] = (trades, open_pos)
            rows.append({
                "key": key, "tf": tf, "ema": p, "eligible": tf in ELIGIBLE_TF,
                "full": metrics(trades, df, set(all_sessions)),
                "common": metrics(trades, df, set(tf_common)),
                "recent": metrics(trades, df, set(tf_recent)),
                "recent_by_session": per_session_net(trades, df, tf_recent),
                "sessions_full": len(all_sessions),
            })
        for f in PAIR_FAST:
            for s in PAIR_SLOW:
                warm = 3 * s
                if warm >= len(df) - 60:
                    continue
                trades, _ = backtest(df, side_cross(close, f, s), intraday, warm)
                pair_rows.append({
                    "key": f"{tf}|{f}/{s}", "tf": tf, "fast": f, "slow": s,
                    "common": metrics(trades, df, set(tf_common)),
                    "recent": metrics(trades, df, set(tf_recent)),
                    "full": metrics(trades, df, set(all_sessions)),
                })
    return rows, pair_rows, trade_book


def _bars_per_session(df):
    return max(1, int(round(len(df) / max(1, df["session"].nunique()))))


def score_rows(rows):
    """Code score 0-100 from percentile ranks among eligible combos with enough trades."""
    elig = [r for r in rows if r["eligible"] and r["common"]["trades"] >= MIN_TRADES_COMMON]
    if not elig:
        return rows
    frame = pd.DataFrame({
        "pf60": [r["common"]["pf"] or 0 for r in elig],
        "wr60": [r["common"]["win_rate"] or 0 for r in elig],
        "net60": [r["common"]["net"] for r in elig],
        "net10": [r["recent"]["net"] for r in elig],
        "pffull": [r["full"]["pf"] or 0 for r in elig],
    })
    ranks = frame.rank(pct=True)
    for i, r in enumerate(elig):
        s = 100 * (0.25 * ranks.pf60[i] + 0.15 * ranks.wr60[i] + 0.20 * ranks.net60[i]
                   + 0.25 * ranks.net10[i] + 0.15 * ranks.pffull[i])
        if r["common"]["net"] <= 0 or (r["common"]["pf"] or 0) < 1:
            s *= 0.5
        r["code_score"] = round(float(s), 1)
    for r in rows:
        r.setdefault("code_score", None)
    return rows


# ── Jev ───────────────────────────────────────────────────────────────────────

JEV_QUESTIONS = {
    "reliability": {
        "type": "choice",
        "instructions": (
            "You are judging a mechanical trend-following rule on the NIFTY 50 index: go long when a candle of the "
            "given timeframe closes above the given EMA, go short when it closes below, flip on the opposite close, "
            "intraday positions closed at session end, costs already deducted. Using ONLY the numbers (trade count, "
            "win rate, profit factor, net points, max drawdown, trades per session, next-candle follow-through) across "
            "full history, the last 60 sessions and the last 10 sessions, how reliable is this rule as a direction "
            "signal? Penalise few trades, whipsaw (many trades per session with thin edge), large drawdown relative "
            "to net points, and disagreement between windows."),
        "criteria": {"weak": None, "fair": None, "good": None, "strong": None},
    },
    "recent_edge": {
        "type": "choice",
        "instructions": (
            "Compare the last 10 sessions (including per-session net points) with the last 60 sessions and full "
            "history for this same rule. Is its edge degrading, stable or improving right now?"),
        "criteria": {"degrading": None, "stable": None, "improving": None},
    },
}
REL_W = {"weak": 0.0, "fair": 1 / 3, "good": 2 / 3, "strong": 1.0}
EDGE_W = {"degrading": 0.0, "stable": 0.5, "improving": 1.0}


def jev_state(r):
    def m(x):
        return {k: x[k] for k in ("trades", "win_rate", "pf", "net", "max_dd", "per_session", "follow")}
    return {
        "instrument": "NIFTY 50 index",
        "rule": f"long when a {r['tf']} candle closes above EMA {r['ema']}, short when it closes below",
        "timeframe": r["tf"], "ema_period": r["ema"],
        "cost_points_per_round_trip": COST_PTS,
        "full_history": {**m(r["full"]), "sessions": r["sessions_full"]},
        "last_60_sessions": m(r["common"]),
        "last_10_sessions": {**m(r["recent"]), "net_points_by_session": r["recent_by_session"]},
    }


def jev_judge(finalists):
    try:
        sys.path.insert(0, str(ROOT))
        from jev_client import Client, JevError, MODEL
        client = Client()
    except Exception as e:
        return {"status": f"unavailable: {e}", "model": None}, {}

    def one(r):
        try:
            a = client.ask(jev_state(r), JEV_QUESTIONS)
            rel, edge = a["reliability"], a["recent_edge"]
            score = 100 * (0.7 * sum(REL_W[k] * v for k, v in rel["probabilities"].items())
                           + 0.3 * sum(EDGE_W[k] * v for k, v in edge["probabilities"].items()))
            return r["key"], {"reliability": rel["choice"], "reliability_conf": round(rel["confidence"] * 100),
                              "reliability_p": {k: round(v * 100) for k, v in rel["probabilities"].items()},
                              "recent_edge": edge["choice"], "recent_edge_conf": round(edge["confidence"] * 100),
                              "recent_edge_p": {k: round(v * 100) for k, v in edge["probabilities"].items()},
                              "jev_score": round(score, 1)}
        except Exception as e:  # fail closed per finalist
            return r["key"], {"error": type(e).__name__ + ": " + str(e)[:80]}

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = dict(pool.map(one, finalists))
    ok = sum(1 for v in results.values() if "jev_score" in v)
    return {"status": f"judged {ok}/{len(finalists)}", "model": MODEL,
            "tokens": [client.input_tokens, client.output_tokens]}, results


# ── export ────────────────────────────────────────────────────────────────────

def chart_time(ts, tf):
    ts = pd.Timestamp(ts)
    if tf == "1D":
        return ts.strftime("%Y-%m-%d")
    # Lightweight Charts renders UTC; pass IST wall-clock as if UTC so the axis reads market time.
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return int(ts.value // 1_000_000_000)


def export_bars(df, tf):
    df = df.iloc[-EXPORT_BARS[tf]:]
    return [[chart_time(ts, tf), round(float(r.Open), 2), round(float(r.High), 2), round(float(r.Low), 2),
             round(float(r.Close), 2), round(float(r.Volume or 0), 0)] for ts, r in df.iterrows()]


def build(now=None):
    now = now or datetime.now(IST)
    frames = load_data(now)
    daily_dates = list(frames["1D"]["session"])
    intraday_dates = sorted(set(frames["15m"]["session"]) | set(frames["1h"]["session"]))
    ref_dates = sorted(set(daily_dates) | set(intraday_dates))
    common_dates = ref_dates[-COMMON_SESSIONS:]
    recent_dates = ref_dates[-RECENT_SESSIONS:]
    print("coverage:", {tf: (len(df), str(df.index[0])[:16], str(df.index[-1])[:16]) for tf, df in frames.items()})

    rows, pair_rows, book = evaluate(frames, common_dates, recent_dates)
    rows = score_rows(rows)
    ranked = sorted([r for r in rows if r["code_score"] is not None], key=lambda r: -r["code_score"])
    finalists = ranked[:FINALISTS]
    print("finalists:", [(r["key"], r["code_score"]) for r in finalists])

    jev_meta, jev = jev_judge(finalists)
    judged = [k for k, v in jev.items() if "jev_score" in v]
    use_jev = len(judged) >= max(1, int(0.8 * len(finalists)))
    for r in finalists:
        j = jev.get(r["key"], {})
        r["jev"] = j or None
        r["final"] = round(0.6 * r["code_score"] + 0.4 * j.get("jev_score", 50.0), 1) if use_jev else r["code_score"]
    finalists.sort(key=lambda r: -r["final"])
    chosen = finalists[0]
    jev_meta["blended"] = use_jev

    # Current signal of the chosen rule
    tf, p = chosen["tf"], chosen["ema"]
    df = frames[tf]
    close = df["Close"].to_numpy()
    e = ema(close, p)
    side = side_close_vs_ema(close, p)
    flip = len(side) - 1
    while flip > 0 and side[flip - 1] == side[-1]:
        flip -= 1
    trades, open_pos = book[chosen["key"]]
    intraday = TF_MIN[tf] is not None
    captured = sum(tr[5] for tr in trades if tr[0] >= flip)
    if open_pos:
        captured += (close[-1] - close[open_pos[0]]) * open_pos[1]
    current = {
        "side": "LONG" if side[-1] > 0 else "SHORT",
        "close": round(float(close[-1]), 2), "ema": round(float(e[-1]), 2),
        "distance": round(float(close[-1] - e[-1]), 2),
        "since": str(df.index[flip])[:16], "since_close": round(float(close[flip]), 2),
        "points_since": round(float((close[-1] - close[flip]) * side[-1]), 1),
        "rule_points_since": round(float(captured), 1),
        "open_position": bool(open_pos),
        "bar_time": str(df.index[-1])[:16],
        "note": ("Intraday rule: flat at the session's last candle; next session opens on the side its first "
                 "candle closes." if intraday else "Daily rule: positions held overnight."),
    }
    exported_from = df.index[-EXPORT_BARS[tf]:][0]
    chosen_trades = [[chart_time(df.index[t[0]], tf), int(t[2]), round(float(t[3]), 2),
                      chart_time(df.index[t[1]], tf), round(float(t[4]), 2), round(float(t[5]), 1), t[6]]
                     for t in trades if df.index[t[0]] >= exported_from]

    def slim(r):
        return {k: r[k] for k in ("key", "tf", "ema", "eligible", "code_score", "common", "recent", "full",
                                  "recent_by_session", "sessions_full") if k in r} | (
            {"jev": r.get("jev"), "final": r.get("final")} if "final" in r else {})

    heat = {}
    for r in rows:
        heat.setdefault(r["tf"], {})[str(r["ema"])] = r["code_score"]
    by_tf = {}
    for r in ranked:
        by_tf.setdefault(r["tf"], slim(r))
    last10 = sorted([r for r in rows if r["eligible"] and r["recent"]["trades"] > 0],
                    key=lambda r: (-r["recent"]["net"], -(r["recent"]["win_rate"] or 0)))[:25]
    pair_ranked = sorted([p for p in pair_rows if p["tf"] in ELIGIBLE_TF and p["common"]["trades"] >= MIN_TRADES_COMMON],
                         key=lambda p: (-(p["common"]["pf"] or 0) * (1 if p["common"]["net"] > 0 else 0.3)))[:20]
    ref5 = sorted([r for r in rows if r["tf"] == "5m" and r["common"]["trades"] >= MIN_TRADES_COMMON],
                  key=lambda r: -(r["common"]["pf"] or 0))[:5]

    d = frames["1D"]
    payload = {
        "version": 1, "name": "Nifty 50 EMA Lab",
        "as_of": str(d.index[-1].date()), "generated_at": now.isoformat(timespec="minutes"),
        "last_close": round(float(d["Close"].iloc[-1]), 2),
        "change_pct": round(float(d["Close"].iloc[-1] / d["Close"].iloc[-2] * 100 - 100), 2),
        "cost_points": COST_PTS,
        "windows": {"common_sessions": common_dates[0] + " to " + common_dates[-1],
                    "recent_sessions": recent_dates},
        "coverage": {tf: {"bars": len(f), "from": str(f.index[0])[:16], "to": str(f.index[-1])[:16],
                          "sessions": int(f["session"].nunique())} for tf, f in frames.items()},
        "tested": {"ema_periods": EMA_PERIODS, "timeframes": list(TF_MIN), "eligible": ELIGIBLE_TF,
                   "combinations": len(rows), "pair_combinations": len(pair_rows)},
        "chosen": slim(chosen) | {"current": current, "trades": chosen_trades},
        "finalists": [slim(r) for r in finalists],
        "leaderboard": [slim(r) for r in ranked[:40]],
        "last10_leaderboard": [slim(r) for r in last10],
        "by_timeframe": by_tf,
        "heatmap": heat,
        "pairs": pair_ranked,
        "asked": [slim(r) for r in rows if r["ema"] in (5, 6, 9, 10, 11) and r["tf"] in ELIGIBLE_TF],
        "reference_5m": [slim(r) for r in ref5],
        "jev": jev_meta,
        "bars": {tf: export_bars(f, tf) for tf, f in frames.items()},
        "limits": [
            "Backtests use the same history that picked the winner (in-sample). Expect live results to be weaker.",
            f"Costs: {COST_PTS} Nifty points per round trip. Real slippage on fast moves can be larger.",
            "15-minute and 30-minute history is about 60 sessions (Yahoo limit); hourly ~2 years; daily 10 years. "
            "The page keeps every new bar, so intraday history grows each day.",
            "Index candles, not futures: futures add a basis and gaps that the index does not show.",
            "A trend-following EMA rule loses in sideways markets; it is a direction filter, not a guarantee.",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
    }
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for out in (DOCS / "nifty.json", PUBLIC / "nifty.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    c = payload["chosen"]
    print(f"nifty.json {payload['as_of']}: {len(rows)} EMA combos + {len(pair_rows)} pairs | "
          f"chosen {c['tf']} EMA {c['ema']} (code {c['code_score']}, final {c['final']}) | "
          f"60s: {c['common']['trades']} trades, {c['common']['win_rate']}% win, PF {c['common']['pf']}, "
          f"net {c['common']['net']} pts | last10 net {c['recent']['net']} | now {current['side']} | "
          f"Jev {jev_meta['status']} | {len(text)//1024}KB")
    return payload


if __name__ == "__main__":
    build()
