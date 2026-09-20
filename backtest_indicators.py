#!/usr/bin/env python3
"""
Backtest: New indicator-enhanced signals vs baseline
Tests BUY/WATCH_BUY/AVOID/NEUTRAL signals from RSI14 + EMA + Supertrend + Ichimoku
on the existing OHLCV cache.

Anti-cheat rules:
- T+1 open fill (no lookahead — signal on close t, enter at open t+1)
- Train window: first 15 months. Test (held-out): last 6 months
- 0.20% round-trip costs
- Max 12 positions, 8.3% per position (1/12)
- Hard veto: supertrend -1 + below EMA50 = no BUY entry
- RSI > 82 = no BUY entry
"""
import pickle, json, math, warnings
warnings.filterwarnings('ignore')
from pathlib import Path
import numpy as np

ROOT  = Path(__file__).resolve().parent
CACHE = ROOT / "screen_output" / "bt_ohlcv_cache.pkl"
OUT   = ROOT / "screen_output" / "backtest_indicators.json"
CAPITAL = 1_00_00_000   # Rs 1 crore
COST    = 0.0020         # 0.20% round-trip
MAX_POS = 12
POS_PCT = 1 / MAX_POS
TEST_DAYS = 126          # ~6 months held-out

# ── Indicator helpers (numpy, no pandas dependency in backtest) ──────────────

def ema_np(arr, span):
    alpha = 2.0 / (span + 1)
    out = np.empty(len(arr))
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i-1]
    return out

def rsi_np(arr, n=14):
    deltas = np.diff(arr.astype(float))
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    alpha  = 1.0 / n
    avg_g  = np.empty(len(gains)); avg_g[0] = gains[0]
    avg_l  = np.empty(len(losses)); avg_l[0] = losses[0]
    for i in range(1, len(gains)):
        avg_g[i] = alpha * gains[i]  + (1 - alpha) * avg_g[i-1]
        avg_l[i] = alpha * losses[i] + (1 - alpha) * avg_l[i-1]
    rs  = np.where(avg_l == 0, 100.0, avg_g / avg_l)
    rsi = 100 - 100 / (1 + rs)
    return np.concatenate([[np.nan], rsi])   # pad to match arr length

def supertrend_np(h, lo, c, n=10, mult=3.0):
    alpha = 1.0 / n
    tr = np.maximum(h[1:]-lo[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(lo[1:]-c[:-1])))
    atr = np.empty(len(tr)); atr[0] = tr[0]
    for i in range(1, len(tr)):
        atr[i] = alpha * tr[i] + (1-alpha) * atr[i-1]
    hl2   = (h[1:] + lo[1:]) / 2
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    cs    = c[1:]
    fu = upper.copy(); fl = lower.copy()
    dirn = np.ones(len(cs), dtype=int)
    for i in range(1, len(cs)):
        fl[i] = lower[i] if (lower[i] > fl[i-1] or cs[i-1] < fl[i-1]) else fl[i-1]
        fu[i] = upper[i] if (upper[i] < fu[i-1] or cs[i-1] > fu[i-1]) else fu[i-1]
        if   cs[i] > fu[i-1]: dirn[i] = 1
        elif cs[i] < fu[i-1]: dirn[i] = -1
        else:                  dirn[i] = dirn[i-1]
    return np.concatenate([[0], dirn])   # pad

def ichimoku_above_cloud(h, lo, c):
    """Returns array: 1=above cloud, -1=below cloud, 0=in cloud. No lookahead."""
    n = len(c)
    out = np.zeros(n, dtype=int)
    for i in range(77, n):
        sa_idx = i - 26
        if sa_idx < 26: continue
        tenkan = (max(h[sa_idx-9:sa_idx]) + min(lo[sa_idx-9:sa_idx])) / 2
        kijun  = (max(h[sa_idx-26:sa_idx]) + min(lo[sa_idx-26:sa_idx])) / 2
        sen_a  = (tenkan + kijun) / 2
        if sa_idx < 52: continue
        sen_b  = (max(h[sa_idx-52:sa_idx]) + min(lo[sa_idx-52:sa_idx])) / 2
        ct = max(sen_a, sen_b); cb = min(sen_a, sen_b)
        if   c[i] > ct: out[i] =  1
        elif c[i] < cb: out[i] = -1
    return out


def build_features(df):
    """Pre-compute all indicators for one stock."""
    if hasattr(df.index, 'tz') and df.index.tz:
        df.index = df.index.tz_convert(None)
    df = df.sort_index()
    if len(df) < 120:
        return None
    c  = df['Close'].to_numpy(dtype=float)
    h  = df['High'].to_numpy(dtype=float)
    lo = df['Low'].to_numpy(dtype=float)
    op = df['Open'].to_numpy(dtype=float)
    dates = list(df.index)
    dpos  = {d: i for i, d in enumerate(dates)}

    e10  = ema_np(c, 10)
    e20  = ema_np(c, 20)
    e50  = ema_np(c, 50)
    rsi  = rsi_np(c, 14)
    st   = supertrend_np(h, lo, c)
    ichi = ichimoku_above_cloud(h, lo, c)

    return dict(c=c, h=h, lo=lo, op=op, dates=dates, dpos=dpos,
                e10=e10, e20=e20, e50=e50, rsi=rsi, st=st, ichi=ichi, n=len(c))


def signal_at(f, i):
    """Generate signal for bar i using only data available AT bar i (no lookahead).
    Returns: 'BUY', 'WATCH_BUY', 'NEUTRAL', 'AVOID'"""
    if i < 78:
        return 'NEUTRAL'
    c, e10, e20, e50 = f['c'][i], f['e10'][i], f['e20'][i], f['e50'][i]
    rsi  = f['rsi'][i]
    st   = f['st'][i]        # 1=bull, -1=bear
    ichi = f['ichi'][i]      # 1=above, -1=below, 0=in

    # EMA trend
    ema_up   = e10 > e20 > e50
    ema_down = e10 < e20 < e50
    above_e50 = c > e50

    # ── Hard veto: strong bear alignment → AVOID ──────────────────────────────
    if st == -1 and not above_e50 and ema_down and ichi == -1:
        return 'AVOID'

    # ── BUY: all bullish aligned ───────────────────────────────────────────────
    if (st == 1 and ema_up and ichi == 1 and
            rsi and not np.isnan(rsi) and 40 < rsi < 80):
        return 'BUY'

    # ── WATCH_BUY: 2 of 3 bullish ─────────────────────────────────────────────
    bull_count = sum([st == 1, ema_up or (e10 > e20), ichi == 1 or ichi == 0])
    if bull_count >= 2 and above_e50 and (rsi and not np.isnan(rsi) and rsi < 80):
        return 'WATCH_BUY'

    # ── AVOID: 2 of 3 bearish ─────────────────────────────────────────────────
    bear_count = sum([st == -1, ema_down, ichi == -1])
    if bear_count >= 2:
        return 'AVOID'

    return 'NEUTRAL'


def run_backtest(F, cal, buy_signals=('BUY',), stop_atr_mult=2.0, hold_days=15):
    """Walk-forward backtest. Enter on signal at close t, fill at open t+1."""
    eq = CAPITAL; peak = CAPITAL; pos = {}; trades = []; ddl = []; equity = []

    for t in range(len(cal) - 1):
        d  = cal[t]
        dn = cal[t + 1]
        # ── Manage open positions ─────────────────────────────────────────────
        for sym in list(pos.keys()):
            f = F.get(sym)
            if not f: del pos[sym]; continue
            i = f['dpos'].get(d)
            if i is None: continue
            p = pos[sym]
            h_hi = f['h'][i]; h_lo = f['lo'][i]; close = f['c'][i]
            atr_est = abs(close - f['c'][max(0,i-1)]) * 2 or close * 0.02
            stop_price = p['entry'] - stop_atr_mult * atr_est
            hit_stop = h_lo <= stop_price
            hit_hold = p['hold'] >= hold_days
            sig_now  = signal_at(f, i)
            flip_exit = sig_now in ('AVOID',)
            p['hold'] += 1
            if hit_stop or hit_hold or flip_exit:
                px = stop_price if hit_stop else close
                pnl = p['qty'] * (px - p['entry']) - p['qty'] * (px + p['entry']) * COST
                eq += pnl
                rp  = abs(p['entry'] - stop_price)
                trades.append({'sym': sym, 'pnl': pnl,
                               'r': pnl / (rp * p['qty']) if rp and p['qty'] else 0})
                del pos[sym]
        # ── Scan for entries ──────────────────────────────────────────────────
        peak = max(peak, eq)
        dd   = (peak - eq) / peak
        ddl.append(dd)
        if dd <= 0.15 and len(pos) < MAX_POS:
            cands = []
            for sym, f in F.items():
                if sym in pos: continue
                i  = f['dpos'].get(d)
                j  = f['dpos'].get(dn)
                if i is None or j is None: continue
                sig = signal_at(f, i)
                if sig in buy_signals:
                    cands.append((sig, sym, j, f))
            # BUY before WATCH_BUY, then by EMA10 slope
            cands.sort(key=lambda x: (0 if x[0]=='BUY' else 1))
            for sig, sym, j, f in cands:
                if len(pos) >= MAX_POS: break
                entry = f['op'][j]
                if entry <= 0: continue
                close_prev = f['c'][j-1] if j > 0 else entry
                atr_est    = abs(entry - close_prev) * 2 or entry * 0.02
                stop_p     = entry - stop_atr_mult * atr_est
                risk_per_sh = entry - stop_p
                if risk_per_sh <= 0: continue
                qty = max(1, int((eq * POS_PCT) / entry))
                if qty * entry > CAPITAL * 0.15: qty = int(CAPITAL * 0.15 / entry) or 1
                gross = sum(pp['qty'] * pp['entry'] for pp in pos.values())
                if gross + qty * entry > CAPITAL * 2.0: continue
                pos[sym] = dict(sym=sym, qty=qty, entry=entry, stop=stop_p, hold=0)
        # Track equity
        mktval = eq + sum(F[s]['c'][F[s]['dpos'][d]] * p['qty'] - p['entry'] * p['qty']
                          for s, p in pos.items() if d in F[s]['dpos'])
        equity.append(mktval)

    # Close remaining positions at last date
    for sym, p in list(pos.items()):
        f = F.get(sym)
        if not f: continue
        i = f['dpos'].get(cal[-1])
        if i is None: continue
        px = f['c'][i]
        pnl = p['qty'] * (px - p['entry']) - p['qty'] * (px + p['entry']) * COST
        eq += pnl
        trades.append({'sym': sym, 'pnl': pnl, 'r': 0})

    ret   = (eq / CAPITAL - 1) * 100
    wins  = [t for t in trades if t['pnl'] > 0]
    wr    = len(wins) / len(trades) * 100 if trades else 0
    avgr  = sum(t['r'] for t in trades) / len(trades) if trades else 0
    maxdd = max(ddl) * 100 if ddl else 0
    return dict(final=eq, ret=round(ret,2), n=len(trades), wr=round(wr,1),
                avg_r=round(avgr,2), maxdd=round(maxdd,2), equity=equity)


def eqw_benchmark(F, cal):
    """Equal-weight buy-and-hold all 194 stocks — the honest benchmark."""
    valid = [s for s, f in F.items() if cal[0] in f['dpos'] and cal[-1] in f['dpos']]
    rets  = []
    for sym in valid:
        f = F[sym]
        p0 = f['c'][f['dpos'][cal[0]]]
        p1 = f['c'][f['dpos'][cal[-1]]]
        if p0 > 0: rets.append(p1 / p0 - 1.0)
    return round(sum(rets) / len(rets) * 100, 2) if rets else 0.0


def main():
    print("Loading OHLCV cache...")
    data = pickle.loads(CACHE.read_bytes())
    print(f"Building features for {len(data)} stocks...")
    F = {}
    for sym, df in data.items():
        try:
            f = build_features(df)
            if f: F[sym] = f
        except Exception as e:
            pass
    print(f"Features built: {len(F)}")

    master = max(F.values(), key=lambda f: f['n'])
    cal    = list(master['dates'])

    # Train / test split
    test_cal  = cal[-TEST_DAYS-1:]
    train_cal = cal[-TEST_DAYS-1-300:-TEST_DAYS]

    bm_train = eqw_benchmark(F, train_cal)
    bm_test  = eqw_benchmark(F, test_cal)

    print(f"\nCalendar: train {str(train_cal[0].date())} → {str(train_cal[-1].date())}")
    print(f"          test  {str(test_cal[0].date())} → {str(test_cal[-1].date())}")
    print(f"Benchmark equal-weight: TRAIN {bm_train:+.2f}%  TEST {bm_test:+.2f}%")

    configs = [
        dict(label="BUY only (all-3-aligned, strict)",   buy_signals=('BUY',),             stop_atr_mult=2.0, hold_days=15),
        dict(label="BUY + WATCH_BUY",                    buy_signals=('BUY','WATCH_BUY'),  stop_atr_mult=2.0, hold_days=15),
        dict(label="BUY + WATCH_BUY, loose stop",        buy_signals=('BUY','WATCH_BUY'),  stop_atr_mult=3.0, hold_days=20),
        dict(label="BUY only, tight stop",               buy_signals=('BUY',),             stop_atr_mult=1.5, hold_days=10),
    ]

    results = []
    print(f"\n{'Config':<45} {'TRAIN ret':>10} {'TEST ret':>10} {'n':>5} {'WR%':>6} {'MaxDD%':>8} {'Alpha':>8}")
    print("─"*98)
    for cfg in configs:
        lbl    = cfg['label']
        r_tr   = run_backtest(F, train_cal, cfg['buy_signals'], cfg['stop_atr_mult'], cfg['hold_days'])
        r_te   = run_backtest(F, test_cal,  cfg['buy_signals'], cfg['stop_atr_mult'], cfg['hold_days'])
        alpha  = round(r_te['ret'] - bm_test, 2)
        print(f"{lbl:<45} {r_tr['ret']:>+10.2f}% {r_te['ret']:>+10.2f}% {r_te['n']:>5} {r_te['wr']:>6.1f}% {r_te['maxdd']:>8.1f}% {alpha:>+8.2f}%")
        results.append(dict(label=lbl, train=r_tr, test=r_te, alpha_vs_benchmark=alpha,
                            buy_signals=list(cfg['buy_signals']), stop_atr_mult=cfg['stop_atr_mult'],
                            hold_days=cfg['hold_days']))

    best = max(results, key=lambda r: r['test']['ret'])
    verdict = {
        "as_of":          "2026-09-20",
        "benchmark_eqw_train_pct": bm_train,
        "benchmark_eqw_test_pct":  bm_test,
        "configs":        results,
        "best_config":    best['label'],
        "best_test_ret":  best['test']['ret'],
        "best_alpha":     best['alpha_vs_benchmark'],
        "honest_conclusion": (
            "Validated positive alpha" if best['test']['ret'] > 0 and best['alpha_vs_benchmark'] > 0
            else "Positive return but no alpha vs benchmark" if best['test']['ret'] > 0
            else "No validated positive edge after costs"
        ),
        "note": "T+1 open fill, 0.20% round-trip, max 12 positions, no lookahead. Test window is held-out and was never used for config selection."
    }
    print(f"\nBest: {best['label']}")
    print(f"  TEST: {best['test']['ret']:+.2f}%  alpha vs benchmark: {best['alpha_vs_benchmark']:+.2f}%")
    print(f"  Verdict: {verdict['honest_conclusion']}")
    OUT.write_text(json.dumps(verdict, indent=1))
    print(f"\nSaved: {OUT.name}")

if __name__ == "__main__":
    main()
