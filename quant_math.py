#!/usr/bin/env python3
"""The 48 formulas of "The math inside a trading bot" (https://quantbot-math.netlify.app/) checked against Nifty 50,
every F&O stock and the strategies on this site.

For each formula: APPLIED (computed here on our data), ADAPTED (same idea on the nearest Indian equivalent), or
NOT POSSIBLE (needs data we do not have: order book, bid/ask, own fills). Nothing is estimated where data is missing.

Data: Nifty 50 daily (data/nifty/1d.csv, 10 years), each F&O stock's daily candles (data/hhhl_prices, data/fno_prices),
the strategy trade lists in docs/nifty_combo.json, docs/fno_ema105.json, docs/order_flow.json, and the NSE F&O
bhavcopy table built by order_flow.py (futures basis and lots).
Output: docs/quant_math.json (+ public/data). Paper research, not advice.
"""
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import nifty_ema as N      # noqa: E402
import nifty_combo as K    # noqa: E402

DOCS, PUBLIC = ROOT / "docs", ROOT / "public" / "data"
DAILY_DIRS = (ROOT / "data" / "hhhl_prices", ROOT / "data" / "fno_prices")
FLOW_STORE = ROOT / "data" / "order_flow" / "flow_daily.csv.gz"
BARS_YEAR = 252
LAMBDA = 0.94
EQUITY = 1_000_000           # ₹10 lakh account for the sizing formulas
RISK_PCT = 0.01
VOL_TARGET = 0.15
MARGIN = {"index": 0.12, "stock": 0.20}   # approximate SPAN + exposure share of contract value
RNG = np.random.default_rng(7)


def j(name):
    p = DOCS / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def r2(v, d=2):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), d)


# ── per-series measures (stage 1-3, 5, 7) ─────────────────────────────────────

def wilder(x, n):
    return pd.Series(x, dtype=float).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def hurst(r):
    """Rescaled-range Hurst exponent on returns (formula 3.4)."""
    r = np.asarray(r, float)
    ns = [n for n in (8, 16, 32, 64, 128, 256) if n <= len(r) // 2]
    if len(ns) < 3:
        return None
    pts = []
    for n in ns:
        k = len(r) // n
        rs = []
        for i in range(k):
            x = r[i * n:(i + 1) * n]
            y = np.cumsum(x - x.mean())
            s = x.std(ddof=0)
            if s > 0:
                rs.append((y.max() - y.min()) / s)
        if rs:
            pts.append((math.log(n), math.log(np.mean(rs))))
    a = np.array(pts)
    return float(np.polyfit(a[:, 0], a[:, 1], 1)[0])


def dickey_fuller(y):
    """Δy_t = α + γ·y_{t-1} + ε (formula 3.2, no lags). Returns (γ, t-stat of γ, half-life in bars)."""
    y = np.asarray(y, float)
    y = y[np.isfinite(y)]
    if len(y) < 30:
        return None, None, None
    dy, x = np.diff(y), y[:-1]
    X = np.column_stack([np.ones_like(x), x])
    beta, *_ = np.linalg.lstsq(X, dy, rcond=None)
    resid = dy - X @ beta
    s2 = resid @ resid / (len(dy) - 2)
    se = math.sqrt(s2 * np.linalg.inv(X.T @ X)[1, 1])
    g = float(beta[1])
    hl = -math.log(2) / g if g < 0 else None          # formula 3.3 (λ = γ)
    return g, g / se if se > 0 else None, hl


def series_stats(df, lot=None, kind="stock"):
    """Every per-series formula on one daily OHLCV frame (oldest first)."""
    c, h, l = (df[k].to_numpy(float) for k in ("Close", "High", "Low"))
    v = df["Volume"].to_numpy(float) if "Volume" in df else np.full(len(c), np.nan)
    lr = np.diff(np.log(c))                                            # 1.1 log return
    last = lr[-BARS_YEAR:]
    sig_d = float(last.std(ddof=1))
    out = {"bars": int(len(c)), "from": str(df.index[0])[:10], "to": str(df.index[-1])[:10], "close": r2(c[-1])}
    out["vol_year"] = r2(sig_d * math.sqrt(BARS_YEAR) * 100, 1)       # 1.2
    ew = 0.0
    for x in lr[-500:]:                                                # 1.3 EWMA (RiskMetrics λ = 0.94)
        ew = LAMBDA * ew + (1 - LAMBDA) * x * x
    out["ewma_vol_year"] = r2(math.sqrt(ew) * math.sqrt(BARS_YEAR) * 100, 1)
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    atr = wilder(tr, 14)                                               # 1.4 ATR
    out["atr"], out["atr_pct"] = r2(atr[-1]), r2(atr[-1] / c[-1] * 100)
    z = (lr - lr.mean()) / lr.std(ddof=1)
    out["bad_ticks"] = int((np.abs(z) > 6).sum())                      # 1.5 flagged, not deleted
    out["bad_tick_dates"] = [str(df.index[i + 1])[:10] for i in np.flatnonzero(np.abs(z) > 6)][-3:]
    w = 20
    m, s = pd.Series(c).rolling(w).mean().to_numpy(), pd.Series(c).rolling(w).std().to_numpy()
    out["zscore20"] = r2((c[-1] - m[-1]) / s[-1])                      # 2.1
    e = N.ema(c, 50)
    out["ema50"], out["above_ema50"] = r2(e[-1]), bool(c[-1] > e[-1])  # 2.2
    out["mom_12_1"] = r2((c[-22] / c[-253] - 1) * 100, 1) if len(c) > 253 else None   # 2.3
    out["rsi"] = r2(float(K.rsi(c)[-1]), 1)                            # 2.4
    t = last.mean() / (last.std(ddof=1) / math.sqrt(len(last)))       # 3.1 (daily, non-overlapping)
    out["t_stat_1y"] = r2(t)
    g, tg, _ = dickey_fuller(np.log(c[-750:]))                         # 3.2 on the price: almost never passes
    out["df_price_t"], out["df_price_pass"] = r2(tg), bool(tg is not None and tg < -2.86)
    gap = np.log(c) - np.log(pd.Series(c).rolling(50).mean().to_numpy())
    g2, tg2, hl = dickey_fuller(gap[-750:])                            # 3.2 + 3.3 on the gap to the 50-day average
    out["df_gap_t"], out["df_gap_pass"], out["half_life"] = r2(tg2), bool(tg2 is not None and tg2 < -2.86), r2(hl, 1)
    out["hurst"] = r2(hurst(lr[-1000:]), 3)                            # 3.4
    s20 = lr[-20:].std(ddof=1)
    out["regime_ratio"] = r2(s20 / sig_d)                              # 3.6
    out["regime"] = "high-vol" if s20 / sig_d > 1.5 else "normal"
    k = min(750, len(c))
    eq = c[-k:] / c[-k]
    peak = np.maximum.accumulate(eq)
    dd = float(((peak - eq) / peak).max())                             # 7.1
    out["max_dd_3y"] = r2(dd * 100, 1)
    out["recovery_needed"] = r2(dd / (1 - dd) * 100, 1)                # 7.2
    out["vol_target_w"] = r2(min(2.0, VOL_TARGET / (sig_d * math.sqrt(BARS_YEAR))))   # 5.4, capped at 2x
    out["inv_vol"] = 1 / sig_d                                         # 5.5 (normalised later)
    if lot:
        val = lot * c[-1]
        out["lot"], out["contract_value"] = int(lot), r2(val, 0)
        out["var95_lot"] = r2(1.645 * sig_d * val, 0)                  # 7.3 one-day VaR for one lot
        mg = MARGIN[kind]
        out["margin_wipe_move"] = r2(mg * 100, 1)                      # 5.6 adapted: move that wipes the margin
        out["margin_wipe_atr"] = r2(mg * c[-1] / atr[-1], 1)
        adv = float(np.nanmean(v[-20:])) if np.isfinite(v[-20:]).any() else float("nan")
        if adv and adv > 0:                                            # 6.3 square-root impact
            out["impact_1lot_bp"] = r2(sig_d * math.sqrt(lot / adv) * 1e4, 1)
            out["impact_10lot_bp"] = r2(sig_d * math.sqrt(10 * lot / adv) * 1e4, 1)
    return out, lr


def load_daily(sym):
    for d in DAILY_DIRS:
        p = d / f"{sym}.NS.csv"
        if p.exists():
            x = pd.read_csv(p, index_col=0, parse_dates=True)
            x = x[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
            return x[x.Close > 0]
    return None


def load_nifty():
    p = ROOT / "data" / "nifty" / "1d.csv"
    x = pd.read_csv(p, index_col=0)
    x.index = pd.to_datetime(x.index, utc=True).tz_convert(N.IST).normalize().tz_localize(None)
    x = x[~x.index.duplicated(keep="last")].sort_index()
    x["Volume"] = np.nan
    return x[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])


# ── strategy validation (stage 4, 5, 7, 8) ────────────────────────────────────

def strategy_stats(name, ret_pct, years, n_tested=1, note="", pooled_groups=None):
    """Every edge / size / risk / validation formula on a list of per-trade returns in % (after costs).
    pooled_groups: list of per-stock return lists. Stocks trade side by side, so a drawdown of the pooled list
    would add up % from different stocks as if one after another; drawdowns are then the median per stock."""
    r = np.asarray([x for x in ret_pct if x is not None and math.isfinite(x)], float)
    n = len(r)
    if n < 3:
        return {"name": name, "n": n}
    w = r[r > 0]
    lo = -r[r <= 0]
    p = len(w) / n
    W = float(w.mean()) if len(w) else 0.0
    L = float(lo.mean()) if len(lo) else 0.0
    out = {"name": name, "note": note, "n": n, "years": r2(years, 2), "tested": n_tested}
    out["win"] = r2(p * 100, 1)
    out["avg_win"], out["avg_loss"] = r2(W), r2(L)
    out["ev"] = r2(p * W - (1 - p) * L, 3)                                        # 4.1
    out["breakeven_win"] = r2(100 / (1 + W / L), 1) if L > 0 else None            # 4.2
    out["expectancy_R"] = r2(p * (W / L) - (1 - p), 3) if L > 0 else None         # 4.3 (1R = the average loss)
    out["pf"] = r2(w.sum() / lo.sum(), 2) if lo.sum() > 0 else None               # 4.4
    out["win_bayes"] = r2((1 + len(w)) / (2 + n) * 100, 1)                         # 4.5, Beta(1,1) prior
    out["kelly"] = r2((p - (1 - p) / (W / L)) * 100, 1) if L > 0 and W > 0 else None   # 5.2
    out["half_kelly"] = r2(out["kelly"] / 2, 1) if out["kelly"] is not None else None
    mu, sd = r.mean() / 100, r.std(ddof=1) / 100
    out["kelly_cont"] = r2(mu / (sd * sd), 2) if sd > 0 else None                 # 5.3 (per trade)
    tpy = n / years if years > 0 else None
    sr = (mu / sd) * math.sqrt(tpy) if sd > 0 and tpy else None                   # 8.1 (per trade, annualised by trades a year)
    out["trades_per_year"] = r2(tpy, 1)
    out["sharpe"] = r2(sr)
    out["sharpe_t"] = r2(sr * math.sqrt(years)) if sr is not None else None       # 8.2
    out["t_stat"] = r2(r.mean() / (r.std(ddof=1) / math.sqrt(n)))                  # 3.1
    out["p_false"] = r2((1 - 0.95 ** n_tested) * 100, 1)                          # 8.3
    se_sr = 1 / math.sqrt(years) if years > 0 else None                           # SR standard error ≈ 1/√years
    out["best_of_n_sr"] = r2(se_sr * math.sqrt(2 * math.log(n_tested)), 2) if n_tested > 1 and se_sr else 0.0   # 8.4
    out["sharpe_beats_noise"] = bool(sr is not None and sr > (out["best_of_n_sr"] or 0))
    if pooled_groups:
        dd1, mc1 = [], []
        for g in pooled_groups:
            g = np.asarray(g, float)
            if len(g) < 3:
                continue
            e1 = np.r_[0, np.cumsum(g)]
            dd1.append((np.maximum.accumulate(e1) - e1).max())
            sims = []
            for _ in range(200):
                e2 = np.r_[0, np.cumsum(RNG.permutation(g))]
                sims.append((np.maximum.accumulate(e2) - e2).max())
            mc1.append(np.percentile(sims, 95))
        out["max_dd_pts_pct"] = r2(float(np.median(dd1)), 1)
        out["mc_dd95"] = r2(float(np.median(mc1)), 1)
        out["mc_dd50"] = None
        out["dd_note"] = "median per stock"
        out["sum"] = r2(float(np.median([np.sum(g) for g in pooled_groups if len(g)])), 1)
        out["sum_note"] = "median per stock"
    else:
        eq = np.cumsum(r)
        out["max_dd_pts_pct"] = r2(float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()), 1)   # 7.1 (sum of %)
        dds = []
        for _ in range(1000):                                                     # 8.6 Monte Carlo shuffle
            e2 = np.r_[0, np.cumsum(RNG.permutation(r))]
            dds.append((np.maximum.accumulate(e2) - e2).max())
        out["mc_dd95"] = r2(float(np.percentile(dds, 95)), 1)
        out["mc_dd50"] = r2(float(np.percentile(dds, 50)), 1)
        out["sum"] = r2(float(r.sum()), 1)
    out["ruin_10"] = r2(((1 - p) / p) ** 10 * 100, 3) if p > 0.5 else None        # 7.5 (even-money bets only)
    out["var95_trade"] = r2(1.645 * r.std(ddof=1), 2)                             # 7.3 per trade, %
    return out


def next_open_check(frames):
    """Formula 1.6: re-price the Nifty setup #1 trades at the NEXT candle's open instead of the signal candle's close."""
    X = K.indicators(frames["2h"], K.EMA_N, frames["1D"])
    F = K.filters(X)
    T = np.ones(len(X["c"]), bool)
    lok = (X["adx"] > 20) & (X["d50"] == 1) & F["Supertrend"][0]
    tr = K.simulate(X, lok, T, "rsi", 68, False)
    c, o = X["c"], X["o"]
    same, nxt = [], []
    for eb, xb, d, net, why in tr:
        same.append(net / c[eb] * 100)
        if eb + 1 < len(o) and xb + 1 < len(o) and why != "open":
            ep, xp = o[eb + 1], o[xb + 1]
        else:
            ep, xp = (o[eb + 1] if eb + 1 < len(o) else c[eb]), c[xb]
        nxt.append((d * (xp - ep) - K.COST * ep) / ep * 100)
    sa, na = np.array(same), np.array(nxt)
    pts_same = [t[3] for t in tr]
    pts_next = [(na[i] / 100) * (o[t[0] + 1] if t[0] + 1 < len(o) else c[t[0]]) for i, t in enumerate(tr)]
    return {"trades": len(tr), "same_close": {"win": r2((sa > 0).mean() * 100, 1), "sum_pct": r2(sa.sum(), 1), "pts": r2(sum(pts_same), 0)},
            "next_open": {"win": r2((na > 0).mean() * 100, 1), "sum_pct": r2(na.sum(), 1), "pts": r2(sum(pts_next), 0)},
            "trade_pct_next": [r2(x, 3) for x in na], "years": (frames["2h"].index[-1] - frames["2h"].index[K.WARM]).days / 365.25}


# ── formula catalogue ─────────────────────────────────────────────────────────

CATALOGUE = [
    ("1.1", "Log return", "r = ln(Pₜ / Pₜ₋₁)", "APPLIED", "Every series below runs on daily log returns."),
    ("1.2", "Annualized volatility", "σ_year = σ_bar · √252", "APPLIED", "NSE trades about 252 sessions a year (not 365)."),
    ("1.3", "EWMA volatility", "σ²ₜ = λσ²ₜ₋₁ + (1−λ)r²", "APPLIED", "λ = 0.94 (RiskMetrics)."),
    ("1.4", "ATR", "avg₁₄(max(H−L, |H−Cₚ|, |L−Cₚ|))", "APPLIED", "Wilder 14; already used by the EMA 105 setup for its re-entry rule."),
    ("1.5", "Bad tick filter", "|r − μ| / σ > 6 → flag", "APPLIED", "Flagged and listed, never deleted (results days and splits are real)."),
    ("1.6", "No lookahead", "positionₜ = f(data ≤ t−1)", "APPLIED", "Daily filters use yesterday's close. The EMA 105 setup fills at the signal candle's close; re-run at the next open below."),
    ("2.1", "Z-score", "z = (x − μₙ) / σₙ", "APPLIED", "Close vs its 20-day mean."),
    ("2.2", "EMA", "α = 2/(n+1)", "APPLIED", "The site's EMA 105 and EMA 50 use exactly this."),
    ("2.3", "Momentum 12-1", "P(t−21) / P(t−252) − 1", "APPLIED", "Needs 1 year of history."),
    ("2.4", "RSI", "100 − 100/(1 + avg gain/avg loss)", "APPLIED", "Wilder 14; the EMA 105 TOP exit is RSI 68."),
    ("2.5", "Order book imbalance", "(Q_bid − Q_ask)/(Q_bid + Q_ask)", "NOT POSSIBLE", "Needs live bid/ask quantities (a broker feed); the closest end-of-day signal is the order-flow build-up."),
    ("2.6", "Funding carry", "funding × 3 × 365", "ADAPTED", "India has no perpetual funding; the futures basis is the carry: (future − spot)/spot × 365/days to expiry."),
    ("3.1", "t-stat of returns", "mean / (σ/√n)", "APPLIED", "On daily returns (non-overlapping) and on each strategy's trades."),
    ("3.2", "ADF test", "Δy = α + γ·yₜ₋₁ + ε", "APPLIED", "Dickey-Fuller without lags; on the price (almost never passes) and on the gap to the 50-day average."),
    ("3.3", "Half-life", "−ln 2 / λ", "APPLIED", "Sessions for the gap to the 50-day average to close halfway."),
    ("3.4", "Hurst exponent", "E[R/S] ∝ nᴴ", "APPLIED", "Rescaled range on up to 1,000 daily returns (not 200)."),
    ("3.5", "Correlation", "cov(x,y)/(σₓσᵧ)", "APPLIED", "Each stock vs Nifty 50, and the average pair inside the F&O list."),
    ("3.6", "Regime switch", "σ₂₀/σ₂₅₂ > 1.5", "APPLIED", "Per stock today."),
    ("4.1", "Expected value", "p·W − (1−p)·L", "APPLIED", "On every strategy, after costs."),
    ("4.2", "Breakeven win rate", "1/(1 + W/L)", "APPLIED", ""),
    ("4.3", "Expectancy in R", "p·R − (1−p)·1R", "APPLIED", "1R = the average losing trade."),
    ("4.4", "Profit factor", "gross wins / gross losses", "APPLIED", ""),
    ("4.5", "Bayesian win rate", "(α + wins)/(α + β + n)", "APPLIED", "Flat Beta(1,1) prior: 22 of 32 becomes 67.6%, not 68.8%."),
    ("4.6", "Net edge", "gross − 2·(fee + slippage)", "APPLIED", "Every backtest on the site takes 0.035% of price off each round trip."),
    ("5.1", "Risk-based size", "equity · risk% / |entry − stop|", "APPLIED", "₹10 lakh, 1% risk, stop = EMA 105 for every stock holding the EMA 105 setup."),
    ("5.2", "Kelly criterion", "p − (1−p)/b", "APPLIED", "Shown with half Kelly; backtest p is optimistic."),
    ("5.3", "Continuous Kelly", "μ/σ²", "APPLIED", "Per trade."),
    ("5.4", "Volatility target", "σ_target / σ_realized", "APPLIED", "15% a year target, capped at 2×."),
    ("5.5", "Risk parity", "wᵢ ∝ 1/σᵢ", "APPLIED", "Across all F&O stocks."),
    ("5.6", "Liquidation price", "P·(1 − 1/L + mmr)", "ADAPTED", "NSE futures use margin, not liquidation: the move that wipes the margin (~20% stocks, ~12% indices) in ATRs."),
    ("6.1", "Spread cost", "(ask − bid)/mid", "NOT POSSIBLE", "No bid/ask in any free end-of-day file."),
    ("6.2", "Microprice", "(P_b·Q_a + P_a·Q_b)/(Q_a + Q_b)", "NOT POSSIBLE", "Needs the live order book."),
    ("6.3", "Square-root impact", "σ·√(Q/V)", "APPLIED", "Q = 1 and 10 lots, V = 20-day average daily volume."),
    ("6.4", "VWAP", "Σpq/Σq", "NOT POSSIBLE", "Needs intraday volume; the Nifty index has no volume on Yahoo."),
    ("6.5", "Slippage", "(fill − expected)/expected", "NOT POSSIBLE", "Needs your own fills; log them when you trade."),
    ("6.6", "Maker vs taker", "round trip = 2 × fee", "ADAPTED", "Included in the 0.035% round-trip cost."),
    ("7.1", "Max drawdown", "(peak − equity)/peak", "APPLIED", "3 years per stock, and on every strategy."),
    ("7.2", "Recovery math", "DD/(1 − DD)", "APPLIED", ""),
    ("7.3", "Value at Risk", "1.645·σ·V", "APPLIED", "One day, one lot."),
    ("7.4", "Portfolio volatility", "√(wᵀΣw)", "APPLIED", "Equal weight vs risk parity across all F&O stocks, last 252 days."),
    ("7.5", "Risk of ruin", "((1−p)/p)^N", "APPLIED", "Only meaningful for even-money bets with p > 50%; shown for N = 10 units."),
    ("7.6", "Kill switch", "equity < peak·(1 − DD_max)", "APPLIED", "Set at the Monte Carlo 95th-percentile drawdown of each strategy."),
    ("8.1", "Sharpe ratio", "mean/σ · √(per year)", "APPLIED", "Per trade, annualised by trades a year."),
    ("8.2", "Sharpe t-stat", "SR · √years", "APPLIED", ""),
    ("8.3", "Multiple testing", "1 − (1−α)^N", "APPLIED", "N = combinations tried before picking."),
    ("8.4", "Best of N noise", "σ_SR · √(2 ln N)", "APPLIED", "σ_SR ≈ 1/√years."),
    ("8.5", "Walk-forward", "train → test → roll", "APPLIED", "Every setup on the site is picked on the first 2/3 and judged on the unseen last 1/3."),
    ("8.6", "Monte Carlo", "shuffle trades ×1,000 → 95th pct DD", "APPLIED", ""),
]


def build():
    now = datetime.now(N.IST)
    frames = N.load_data(now)
    nifty_df = frames["1D"][["Open", "High", "Low", "Close"]].copy()
    nifty_df["Volume"] = np.nan
    nifty, nlr = series_stats(nifty_df, lot=75, kind="index")
    fno = j("hhhl_fno.json")
    members = fno["membership"]["members"]
    meta = {}
    for f in ("hhhl_scan.json", "hhhl_fno.json"):
        for r in (j(f) or {}).get("rows", []):
            meta[r["symbol"]] = {"name": r.get("name"), "sector": r.get("sector")}

    # futures basis (2.6 adapted) from the order-flow bhavcopy table
    basis = {}
    if FLOW_STORE.exists():
        fl = pd.read_csv(FLOW_STORE, parse_dates=["e0"])
        last = fl[fl.date == fl.date.max()]
        for _, r in last.iterrows():
            dte = (r.e0 - pd.Timestamp(r.date)).days
            if r.spot and r.spot > 0 and dte > 0:
                basis[r.symbol] = {"basis_pct": r2((r.c0 / r.spot - 1) * 100, 3), "dte": int(dte),
                                   "carry_apr": r2((r.c0 / r.spot - 1) * 365 / dte * 100, 2)}
    nifty.update(basis.get("NIFTY", {}))

    rows, rets = [], {}
    for m in members:
        s = m["symbol"]
        df = load_daily(s)
        if df is None or len(df) < 300:
            continue
        st, lr = series_stats(df.tail(1100), lot=m.get("lot_size"), kind="stock")
        st.update({"symbol": s, "name": (meta.get(s) or {}).get("name") or m.get("name"), "sector": (meta.get(s) or {}).get("sector")})
        st.update(basis.get(s, {}))
        rows.append(st)
        rets[s] = pd.Series(lr, index=df.tail(1100).index[1:])

    # 3.5 correlation, 5.5 risk parity, 7.4 portfolio vol
    R = pd.DataFrame(rets).iloc[-BARS_YEAR:].dropna(axis=1, thresh=int(BARS_YEAR * 0.9)).fillna(0)
    nr = pd.Series(nlr, index=nifty_df.index[1:]).reindex(R.index).fillna(0)
    corr_n = R.corrwith(nr)
    C = R.corr().to_numpy()
    avg_pair = float((C.sum() - len(C)) / (len(C) * (len(C) - 1)))
    cov = R.cov().to_numpy() * BARS_YEAR
    ew = np.full(len(R.columns), 1 / len(R.columns))
    inv = 1 / R.std().to_numpy()
    rp = inv / inv.sum()
    port = {"stocks": int(len(R.columns)), "avg_pair_corr": r2(avg_pair, 3),
            "equal_weight_vol": r2(math.sqrt(ew @ cov @ ew) * 100, 1), "risk_parity_vol": r2(math.sqrt(rp @ cov @ rp) * 100, 1),
            "avg_stock_vol": r2(float(np.sqrt(np.diag(cov)).mean() * 100), 1)}
    rpw = dict(zip(R.columns, rp))
    for r in rows:
        r["corr_nifty"] = r2(corr_n.get(r["symbol"]), 2)
        r["risk_parity_w"] = r2(rpw.get(r["symbol"], 0) * 100, 3)
        r.pop("inv_vol", None)
    nifty.pop("inv_vol", None)

    # 5.1 risk-based size on the EMA 105 open trades (stop = EMA 105)
    e105 = j("fno_ema105.json") or {"rows": []}
    sizing = []
    for r in e105["rows"]:
        if r["state"] in ("BUY", "HOLD") and r["close"] > r["ema"]:
            risk_per_share = r["close"] - r["ema"]
            shares = EQUITY * RISK_PCT / risk_per_share
            lot = r.get("lot") or 0
            sizing.append({"symbol": r["symbol"], "state": r["state"], "close": r["close"], "stop": r["ema"],
                           "risk_per_share": r2(risk_per_share), "risk_pct": r2(risk_per_share / r["close"] * 100, 1),
                           "shares": int(shares), "lots": r2(shares / lot, 2) if lot else None,
                           "one_lot_risk": r2(lot * risk_per_share, 0) if lot else None,
                           "one_lot_risk_pct_equity": r2(lot * risk_per_share / EQUITY * 100, 2) if lot else None})
    sizing.sort(key=lambda x: x["risk_pct"])

    # strategies (stage 4, 5, 7, 8)
    strategies = []
    combo = j("nifty_combo.json")
    noc = next_open_check(frames)
    if combo:
        tr = combo["trades"]
        pct = [t[5] / t[2] * 100 for t in tr]
        strategies.append(strategy_stats("Nifty 50 · EMA 105 setup #1 (fill at signal close)", pct, noc["years"], combo["tested"],
                                         "32 trades on 2-hour candles; picked from 8,056 combinations"))
        strategies.append(strategy_stats("Nifty 50 · EMA 105 setup #1 (fill at NEXT open, formula 1.6)", noc["trade_pct_next"],
                                         noc["years"], combo["tested"], "same trades, entered and exited at the next candle's open"))
    if e105.get("rows"):
        pooled = [t[5] for r in e105["rows"] for t in r["trades"]]
        yrs = (pd.Timestamp(e105["rows"][0]["to"][:10]) - pd.Timestamp(e105["rows"][0]["from"])).days / 365.25
        groups = [[t[5] for t in r["trades"]] for r in e105["rows"]]
        strategies.append(strategy_stats(f"All F&O stocks · EMA 105 setup #1 ({len(e105['rows'])} stocks pooled)", pooled,
                                         yrs * len(e105["rows"]), 1, "setup fixed on Nifty, not re-fitted: N = 1 per stock; years = stock-years",
                                         pooled_groups=groups))
    of = j("order_flow.json")
    if of:
        span = of["backtest"]["span"]
        yrs = span["sessions"] / BARS_YEAR
        for rule in of["backtest"]["rules"][:3]:
            pass
        strategies.append({"name": "Order flow · next-session follow (see order-flow tables)", "from_order_flow": True,
                           "n_rules": len(of["backtest"]["rules"]), "sessions": span["sessions"]})
    for s in strategies:
        if s.get("mc_dd95") is not None:
            s["kill_switch_dd"] = s["mc_dd95"]                                   # 7.6

    hurst_vals = [r["hurst"] for r in rows if r.get("hurst") is not None]
    gap_pass = sum(1 for r in rows if r.get("df_gap_pass"))
    price_pass = sum(1 for r in rows if r.get("df_price_pass"))
    summary = {
        "stocks": len(rows),
        "median_vol": r2(float(np.median([r["vol_year"] for r in rows])), 1),
        "median_hurst": r2(float(np.median(hurst_vals)), 3),
        "trending_hurst": sum(1 for h in hurst_vals if h > 0.55), "reverting_hurst": sum(1 for h in hurst_vals if h < 0.45),
        "df_price_pass": price_pass, "df_gap_pass": gap_pass,
        "median_half_life": r2(float(np.median([r["half_life"] for r in rows if r.get("half_life")])), 1),
        "high_vol_regime": sum(1 for r in rows if r.get("regime") == "high-vol"),
        "bad_tick_stocks": sum(1 for r in rows if r["bad_ticks"] > 0),
        "positive_t": sum(1 for r in rows if (r.get("t_stat_1y") or 0) > 2),
        "median_corr_nifty": r2(float(np.nanmedian([r["corr_nifty"] for r in rows if r.get("corr_nifty") is not None])), 2),
    }
    counts = {k: sum(1 for c in CATALOGUE if c[3] == k) for k in ("APPLIED", "ADAPTED", "NOT POSSIBLE")}
    payload = {
        "version": 1, "name": "The math inside a trading bot - applied to Nifty 50 and every F&O stock",
        "source": "https://quantbot-math.netlify.app/", "as_of": nifty["to"], "generated_at": now.isoformat(timespec="minutes"),
        "settings": {"bars_year": BARS_YEAR, "lambda": LAMBDA, "equity": EQUITY, "risk_pct": RISK_PCT * 100,
                     "vol_target": VOL_TARGET * 100, "margin": MARGIN},
        "catalogue": [{"id": a, "name": b, "formula": c, "status": d, "how": e} for a, b, c, d, e in CATALOGUE],
        "counts": counts, "nifty": nifty, "summary": summary, "portfolio": port, "rows": rows,
        "sizing": sizing, "strategies": strategies, "next_open": {k: v for k, v in noc.items() if k != "trade_pct_next"},
        "limits": [
            "Formulas marked NOT POSSIBLE need live order-book or fill data; nothing is estimated in their place.",
            "Strategy Sharpe is per trade, annualised by trades a year - a rough figure for strategies that are often flat.",
            "Paper research. Not SEBI-registered advice. No orders are placed by this website.",
        ],
    }
    text = json.dumps(payload, separators=(",", ":"), default=str)
    for out in (DOCS / "quant_math.json", PUBLIC / "quant_math.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(f"quant_math.json {payload['as_of']}: formulas {counts} | {len(rows)} F&O stocks + Nifty | summary {summary} | "
          f"portfolio {port} | next-open check {payload['next_open']} | {len(text)//1024}KB")
    for s in strategies:
        if "win" in s:
            print(f"  {s['name']}: n {s['n']} win {s['win']}% bayes {s['win_bayes']}% EV {s['ev']}% PF {s['pf']} kelly {s['kelly']}% "
                  f"SR {s['sharpe']} t {s['sharpe_t']} best-of-N {s['best_of_n_sr']} beats {s['sharpe_beats_noise']} MC DD95 {s['mc_dd95']}%")
    return payload


if __name__ == "__main__":
    build()
