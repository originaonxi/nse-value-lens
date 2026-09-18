#!/usr/bin/env python3
"""
NSE 200 — Daily Support, Resistance & Breakout Screener
========================================================
Run DAILY after market close. Fetches real OHLCV from yfinance (.NS) for
all 194 Nifty 200 EQ stocks and computes 5 independent S/R methods:

METHOD 1 — Swing High / Low (fractal, N=5 bars each side)            [Velasquez 2025]
  A swing high at bar i: high[i] = max of surrounding N bars
  A swing low at bar i: low[i]  = min of surrounding N bars
  Keeps the most recent 5 swing highs and 5 swing lows as levels.

METHOD 2 — Classic Pivot Points (yesterday OHLC)                    [StockeZee / classic]
  PP  = (H + L + C) / 3
  R1  = 2*PP - L   |  S1 = 2*PP - H
  R2  = PP + (H-L) |  S2 = PP - (H-L)
  R3  = R2 + (H-L) |  S3 = S2 - (H-L)

METHOD 3 — 52-week High / Low (institutional anchor)
  The single strongest S/R: 52w_high = resistance, 52w_low = support.

METHOD 4 — K-means clustering on 90-day H+L price data             [Tengelin/Sopasakis, Lund 2020]
  Input : all daily highs and lows from last 90 sessions (≈180 values)
  K     : floor(sqrt(n_prices / 2)) ≈ 7 clusters
  Output: cluster centroids = S/R zones (deduplicated within 0.5 ATR)

METHOD 5 — Volume-at-Price POC / Value Area                        [Murtazin 2025, LuxAlgo]
  Divide 90-session price range into 50 bins. For each candle distribute
  its volume proportionally across the bins it spans (Low→High).
  POC = bin with highest accumulated volume (stickiest price level).
  VAH / VAL = upper/lower bounds of 70% Value Area around POC.
  Donchian 20d High/Low used only for BREAKOUT trigger, not as S/R level.

PROXIMITY (ATR-based, not fixed %):                                 [Murtazin 2025, medium]
  ATR = 14-session Average True Range
  "AT"   level  : |close - level| / ATR <= 0.50
  "NEAR" level  : |close - level| / ATR <= 1.50

BREAKOUT (confirmed with volume):                                   [Velasquez 2025]
  Bullish breakout : close > 20d_high_prev  AND vol > 1.5 × vol20ma
  Bearish breakdown: close < 20d_low_prev   AND vol > 1.5 × vol20ma
  Breakout strength: (close - level) / ATR  (in ATR units)

Signal priority: BREAKOUT_UP > BREAKOUT_DN > AT_RESISTANCE > AT_SUPPORT
               > NEAR_RESISTANCE > NEAR_SUPPORT > NEUTRAL

OUTPUT: screen_output/sr_levels.json
"""
import csv, json, statistics, warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

warnings.filterwarnings('ignore')
import yfinance as yf

HERE  = Path(__file__).resolve().parent
OUT   = HERE / "screen_output"
UNIV  = HERE / "nifty200.csv"

SWING_N  = 5      # fractal lookback each side
ATR_N    = 14     # ATR period
VOL_N    = 20     # volume MA period
LOOK_90  = 90     # sessions for K-means
LOOK_52W = 252    # sessions for 52w high/low
AT_ATR   = 0.5    # within 0.5 ATR = "AT" level
NEAR_ATR = 1.5    # within 1.5 ATR = "NEAR" level
VOL_MUL  = 1.5    # breakout volume multiplier
FETCH_PD = "1y"   # yfinance period (≥252 sessions)


def atr14(df):
    """14-session Average True Range (Wilder smoothing approximation via EMA)."""
    tr = []
    for i in range(1, len(df)):
        h, l, pc = df['High'].iloc[i], df['Low'].iloc[i], df['Close'].iloc[i-1]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(tr) < ATR_N:
        return None
    # Simple mean of first N, then Wilder smooth
    atr = sum(tr[:ATR_N]) / ATR_N
    for t in tr[ATR_N:]:
        atr = (atr * (ATR_N - 1) + t) / ATR_N
    return atr


def swing_highs_lows(df, n=SWING_N, top=5):
    """Return the most-RECENT swing highs and swing lows (by bar index).
    Stores (index, price) tuples — sorts by index desc so recent levels
    take priority over stale extremes from months ago.
    """
    highs, lows = [], []   # list of (bar_index, price)
    h, l = df['High'].values, df['Low'].values
    for i in range(n, len(h) - n):
        window_h = list(h[i-n:i]) + list(h[i+1:i+n+1])
        if h[i] >= max(window_h):
            highs.append((i, float(h[i])))
        window_l = list(l[i-n:i]) + list(l[i+1:i+n+1])
        if l[i] <= min(window_l):
            lows.append((i, float(l[i])))
    # Sort by bar index descending → most recent first, take top N
    recent_sh = [p for _, p in sorted(highs, key=lambda x: x[0], reverse=True)[:top]]
    recent_sl = [p for _, p in sorted(lows,  key=lambda x: x[0], reverse=True)[:top]]
    return recent_sh, recent_sl



def volume_poc(df, periods=90, n_bins=50):
    """Volume-at-Price Point of Control, Value Area High/Low.
    POC = price level with most traded volume over last `periods` sessions.
    VAH/VAL = upper/lower bounds of the 70% Value Area centred on POC.
    [Murtazin 2025; LuxAlgo Level Clustering Library]
    """
    d = df.tail(periods)
    hi_max = float(d['High'].max())
    lo_min = float(d['Low'].min())
    price_range = hi_max - lo_min
    if price_range <= 0:
        return None, None, None
    bin_size = price_range / n_bins
    vol_bins = [0.0] * n_bins
    for _, row in d.iterrows():
        h, l, v = float(row['High']), float(row['Low']), float(row['Volume'])
        span = h - l
        for i in range(n_bins):
            b_lo = lo_min + i * bin_size
            b_hi = b_lo + bin_size
            overlap = min(h, b_hi) - max(l, b_lo)
            if overlap > 0:
                vol_bins[i] += v * (overlap / span if span > 0 else 1.0)
    poc_idx = vol_bins.index(max(vol_bins))
    poc = lo_min + (poc_idx + 0.5) * bin_size
    # Value Area: expand from POC until 70% of volume is captured
    total = sum(vol_bins)
    va_vol = vol_bins[poc_idx]
    vhi, vlo = poc_idx, poc_idx
    while va_vol < 0.70 * total and (vhi < n_bins - 1 or vlo > 0):
        up = vol_bins[vhi + 1] if vhi < n_bins - 1 else 0.0
        dn = vol_bins[vlo - 1] if vlo > 0 else 0.0
        if up >= dn:
            vhi += 1; va_vol += up
        else:
            vlo -= 1; va_vol += dn
    vah = lo_min + (vhi + 1) * bin_size
    val = lo_min + vlo * bin_size
    return round(poc, 2), round(vah, 2), round(val, 2)

def kmeans_levels(prices, k=None):
    """K-means clustering on price list. Returns k centroids as S/R zones.
    Tengelin & Sopasakis (Lund 2020): K-means on tick/price data for S/R detection.
    """
    if not prices:
        return []
    if k is None:
        k = max(3, int(len(prices) ** 0.5 // 2))
    k = min(k, len(set(prices)))
    # Initialise centroids at evenly-spaced quantiles
    sp = sorted(prices)
    step = len(sp) / k
    centroids = [sp[int(i * step)] for i in range(k)]
    for _ in range(50):   # max iterations
        clusters = [[] for _ in range(k)]
        for p in prices:
            idx = min(range(k), key=lambda i: abs(p - centroids[i]))
            clusters[idx].append(p)
        new_c = [statistics.mean(c) if c else centroids[i]
                 for i, c in enumerate(clusters)]
        if new_c == centroids:
            break
        centroids = new_c
    return sorted(centroids)


def dedupe_levels(levels, atr):
    """Merge levels closer than 0.5 ATR into their mean."""
    if not levels or not atr:
        return levels
    levels = sorted(levels)
    merged = []
    group = [levels[0]]
    for l in levels[1:]:
        if l - group[-1] < 0.5 * atr:
            group.append(l)
        else:
            merged.append(statistics.mean(group))
            group = [l]
    merged.append(statistics.mean(group))
    return merged


def classify(close, resistances, supports, atr):
    """
    Returns (signal, nearest_resistance, nearest_support, dist_r_atr, dist_s_atr).
    Priority: BREAKOUT already applied upstream → classify proximity here.
    """
    if not atr:
        return 'NEUTRAL', None, None, None, None
    nr = min(resistances, key=lambda r: abs(r - close)) if resistances else None
    ns = min(supports, key=lambda s: abs(s - close)) if supports else None
    # nearest resistance above close
    res_above = [r for r in resistances if r > close]
    sup_below = [s for s in supports    if s < close]
    nr = min(res_above, key=lambda r: r - close) if res_above else nr
    ns = max(sup_below) if sup_below else ns   # highest value below close = nearest
    dr = abs(close - nr) / atr if nr else 999
    ds = abs(close - ns) / atr if ns else 999
    # classify
    if   dr <= AT_ATR:   signal = 'AT_RESISTANCE'
    elif ds <= AT_ATR:   signal = 'AT_SUPPORT'
    elif dr <= NEAR_ATR: signal = 'NEAR_RESISTANCE'
    elif ds <= NEAR_ATR: signal = 'NEAR_SUPPORT'
    else:                signal = 'NEUTRAL'
    return signal, nr, ns, round(dr, 2), round(ds, 2)


def analyse(symbol):
    try:
        t   = yf.Ticker(symbol + '.NS')
        df  = t.history(period=FETCH_PD, interval='1d', actions=False)
        if df.empty or len(df) < 32:
            return symbol, {'error': 'insufficient_data'}
        df = df.dropna(subset=['High','Low','Close','Volume'])
        # Split: today's row for price/vol display; completed candles for all S/R
        today   = df.iloc[-1]
        df_hist = df.iloc[:-1]          # completed candles only — safe intraday & post-close
        close   = float(today['Close'])
        vol     = float(today['Volume'])
        vol20   = float(df_hist['Volume'].tail(VOL_N).mean())
        atr     = atr14(df_hist)
        if not atr:
            return symbol, {'error': 'atr_failed'}

        # ── Method 1: Swing H/L (fractal) — completed candles only ──────
        sh, sl = swing_highs_lows(df_hist)

        # ── Method 2: Pivot Points (most recent COMPLETED session) ───────
        yest  = df_hist.iloc[-1]
        H, L, C = float(yest['High']), float(yest['Low']), float(yest['Close'])
        PP  = (H + L + C) / 3
        R1, S1 = 2*PP - L,   2*PP - H
        R2, S2 = PP + (H-L), PP - (H-L)
        R3, S3 = R2 + (H-L), S2 - (H-L)
        pivot_r = [R1, R2, R3]
        pivot_s = [S1, S2, S3]

        # ── Method 3: 52-week High / Low (completed candles) ─────────────
        df52  = df_hist.tail(LOOK_52W)
        hi52  = float(df52['High'].max())
        lo52  = float(df52['Low'].min())

        # ── Method 4: K-means on 90-day H+L (completed candles) ─────────
        df90  = df_hist.tail(LOOK_90)
        prices_90 = list(df90['High'].values) + list(df90['Low'].values)
        km_levels  = kmeans_levels(prices_90)
        km_res = [l for l in km_levels if l > close]
        km_sup = [l for l in km_levels if l < close]

        # ── Method 5: Volume-at-Price POC / Value Area ──────────────────
        poc, vah, val = volume_poc(df_hist)
        poc_res = [vah] if vah and vah > close else []
        poc_sup = [val] if val and val < close else []
        if poc and poc > close: poc_res.append(poc)
        if poc and poc < close: poc_sup.append(poc)

        # ── 20-day VWAP — from completed candles only ────────────────────
        df_vwap = df_hist.tail(20)
        tp_vwap = (df_vwap['High'] + df_vwap['Low'] + df_vwap['Close']) / 3
        vwap20  = float((tp_vwap * df_vwap['Volume']).sum() / df_vwap['Volume'].sum())
        vwap_res = [vwap20] if vwap20 > close else []
        vwap_sup = [vwap20] if vwap20 < close else []

        # ── 20-session Donchian from completed candles (BREAKOUT TRIGGER) ─
        d20_hi = float(df_hist['High'].tail(20).max())
        d20_lo = float(df_hist['Low'].tail(20).min())
        # ── Combine all 6-method resistances and supports ─────────────────
        all_res = dedupe_levels(sorted(set(
            sh + pivot_r + [hi52] + km_res + poc_res + vwap_res
        )), atr)
        all_sup = dedupe_levels(sorted(set(
            sl + pivot_s + [lo52] + km_sup + poc_sup + vwap_sup
        )), atr)
        res_above = [r for r in all_res if r > close]
        sup_below = [s for s in all_sup if s < close]

        # ── Breakout detection ───────────────────────────────────────────
        vol_ok  = vol > VOL_MUL * vol20
        bo_up   = close > d20_hi and vol_ok
        bo_dn   = close < d20_lo and vol_ok
        bo_str  = round((close - d20_hi) / atr, 2) if bo_up else \
                  round((d20_lo - close) / atr, 2) if bo_dn else 0.0

        if bo_up:
            signal = 'BREAKOUT_UP'
        elif bo_dn:
            signal = 'BREAKOUT_DN'
        else:
            signal, nr, ns, dr, ds = classify(close, res_above, sup_below, atr)

        nr = min(res_above, key=lambda r: r-close) if res_above else None
        ns = max(sup_below) if sup_below else None   # highest value below close = nearest
        dr = round(abs(close-nr)/atr, 2) if nr else None
        ds = round(abs(close-ns)/atr, 2) if ns else None

        # ── Plain-English output fields ───────────────────────────────────
        # "floor" = nearest support; "ceiling" = nearest resistance
        # "next_target" = if price rises, first meaningful resistance above ceiling
        # "next_floor"  = if price drops, first meaningful support below floor
        floor   = ns
        ceiling = nr
        next_target = sorted([r for r in res_above if r > (nr or 0)], )[0] \
                      if len(res_above) > 1 else None
        next_floor  = sorted([s for s in sup_below if s < (ns or close)], reverse=True)[0] \
                      if len(sup_below) > 1 else None

        PLAIN = {
            'BREAKOUT_UP':    f"Breaking out 🚀 — cleared ceiling, next target ₹{res_above[1] if len(res_above)>1 else (nr or ''):.0f}" if res_above else "Breaking out 🚀",
            'BREAKOUT_DN':    f"Breaking down ⚠️ — floor lost, next floor ₹{sorted(sup_below,reverse=True)[1] if len(sup_below)>1 else (ns or ''):.0f}" if sup_below else "Breaking down ⚠️",
            'AT_RESISTANCE':  f"At ceiling ₹{nr:.0f} — buyers need to push through, or it may fall back to ₹{ns:.0f}" if nr and ns else "At ceiling — watch closely",
            'AT_SUPPORT':     f"At floor ₹{ns:.0f} — buyers stepping in here; target ₹{nr:.0f} if it holds" if ns and nr else "At floor — potential buy zone",
            'NEAR_RESISTANCE':f"Approaching ceiling ₹{nr:.0f} — decision point soon" if nr else "Approaching ceiling",
            'NEAR_SUPPORT':   f"Approaching floor ₹{ns:.0f} — watch for a bounce" if ns else "Approaching floor",
            'NEUTRAL':        "No key level nearby — wait for price to reach a floor or ceiling",
        }
        ACTION = {
            'BREAKOUT_UP':    "Target next ceiling — trail stop below VWAP or floor",
            'BREAKOUT_DN':    "Avoid — wait for next floor to hold before entering",
            'AT_RESISTANCE':  "Wait — buy only if ceiling breaks with high volume",
            'AT_SUPPORT':     "Buy zone — stop just below floor; target the ceiling",
            'NEAR_RESISTANCE':"Caution — reduce position or wait for breakout",
            'NEAR_SUPPORT':   "Watch — good entry if floor holds with volume",
            'NEUTRAL':        "No action — wait for price to reach floor or ceiling",
        }
        above_vwap = close > vwap20

        # Signal score for ranking
        score = {'BREAKOUT_UP':6,'BREAKOUT_DN':5,
                 'AT_RESISTANCE':4,'AT_SUPPORT':4,
                 'NEAR_RESISTANCE':3,'NEAR_SUPPORT':3,'NEUTRAL':1}.get(signal,1)

        return symbol, {
            'symbol':    symbol,
            'name':      '',      # filled in main()
            'close':     round(close, 2),
            'atr14':     round(atr, 2),
            'signal':    signal,
            'score':     score,
            'vol_ratio': round(vol / vol20, 2) if vol20 else None,
            'bo_strength_atr': bo_str,
            # ── Plain-English fields (layman) ─────────────────────────────
            'plain_signal': PLAIN.get(signal, signal),
            'action':       ACTION.get(signal, ''),
            'floor':         round(floor,   2) if floor   else None,
            'ceiling':       round(ceiling, 2) if ceiling else None,
            'next_target':   round(next_target, 2) if next_target else None,
            'next_floor':    round(next_floor,  2) if next_floor  else None,
            'above_vwap':    above_vwap,
            'vwap20':        round(vwap20, 2),
            # ── Technical levels ─────────────────────────────────────────
            'nearest_resistance': round(nr, 2) if nr else None,
            'nearest_support':    round(ns, 2) if ns else None,
            'dist_resistance_atr': dr,
            'dist_support_atr':    ds,
            'resistances': [round(r,2) for r in res_above[:5]],
            'supports':    [round(s,2) for s in sorted(sup_below,reverse=True)[:5]],
            # ── Per-method breakdown ──────────────────────────────────────
            'pivot': {'PP':round(PP,2),'R1':round(R1,2),'R2':round(R2,2),
                      'S1':round(S1,2),'S2':round(S2,2)},
            'poc': round(poc,2) if poc else None,
            'vah': round(vah,2) if vah else None,
            'val': round(val,2) if val else None,
            'd20_high': round(d20_hi,2), 'd20_low': round(d20_lo,2),
            'hi52w': round(hi52,2), 'lo52w': round(lo52,2),
            'swing_highs': [round(x,2) for x in sh],
            'swing_lows':  [round(x,2) for x in sl],
            'kmeans_levels': [round(x,2) for x in km_levels],
            'as_of': df.index[-1].strftime('%Y-%m-%d'),
        }
    except Exception as e:
        return symbol, {'error': str(e)}


def main():
    rows  = list(csv.DictReader(open(UNIV, newline='', encoding='utf-8-sig')))
    syms  = [(r['Symbol'].strip(), r.get('Company Name','').strip())
             for r in rows if r.get('Series','EQ').strip()=='EQ']
    print(f"Fetching OHLCV + computing S/R for {len(syms)} stocks…")

    results = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(analyse, s): (s, n) for s, n in syms}
        done = 0
        for f in as_completed(futs):
            sym, _ = futs[f]
            _, data = f.result()
            name = next(n for s,n in syms if s==sym)
            if 'error' not in data:
                data['name'] = name
            results[sym] = data
            done += 1
            if done % 30 == 0:
                print(f"  {done}/{len(syms)}…", flush=True)

    # Sort by score desc, then by dist_to_nearest_level asc
    valid = {k: v for k,v in results.items() if 'error' not in v}
    errors= {k: v for k,v in results.items() if 'error' in v}
    ranked = sorted(valid.values(), key=lambda x: (
        -x['score'],
        min(x['dist_resistance_atr'] or 99, x['dist_support_atr'] or 99)
    ))

    output = {
        'as_of': max((v['as_of'] for v in valid.values()), default=date.today().isoformat()),
        'universe_size': len(syms),
        'fetched':       len(valid),
        'errors':        len(errors),
        'methods': [
            'Swing High/Low (fractal, most-recent 5 each side)',
            'Classic Pivot Points PP/R1/R2/S1/S2 (yesterday OHLC)',
            '52-week High/Low (institutional anchor)',
            'K-means clustering on 90-session prices (Tengelin/Sopasakis 2020)',
            'Volume-at-Price POC + 70% Value Area (Murtazin 2025)',
            '20-day VWAP — institutional fair value benchmark (Downstox 2026)',
        ],
        'breakout_trigger': f'Donchian 20d high/low (prior bars only) + vol > {VOL_MUL}× vol20ma',
        'proximity_rule': f'AT = within {AT_ATR} ATR | NEAR = within {NEAR_ATR} ATR',
        'stocks': ranked,
    }
    (OUT / 'sr_levels.json').write_text(json.dumps(output, indent=2), encoding='utf-8')

    # Console summary
    print(f"\n{'='*65}")
    print(f"{'SIGNAL':<18} {'SYMBOL':<13} {'CLOSE':>8} {'VOL×':>6} {'NEAREST LVL':>11} {'DIST(ATR)':>9}")
    print('='*65)
    sig_colors = {
        'BREAKOUT_UP':   '🟢',
        'BREAKOUT_DN':   '🔴',
        'AT_RESISTANCE': '🟡',
        'AT_SUPPORT':    '🟢',
        'NEAR_RESISTANCE':'🟠',
        'NEAR_SUPPORT':  '🔵',
        'NEUTRAL':       '⚪',
    }
    for r in ranked[:30]:
        icon  = sig_colors.get(r['signal'], '⚪')
        lvl   = r['nearest_resistance'] or r['nearest_support'] or '-'
        dist  = min(r['dist_resistance_atr'] or 99, r['dist_support_atr'] or 99)
        print(f"{icon} {r['signal']:<16} {r['symbol']:<13} {r['close']:>8.2f} "
              f"{(r['vol_ratio'] or 0):>5.1f}× {lvl:>11} {dist:>8.2f}atr")

    print(f"\nBreakout_UP:  {sum(1 for v in valid.values() if v['signal']=='BREAKOUT_UP')}")
    print(f"Breakout_DN:  {sum(1 for v in valid.values() if v['signal']=='BREAKOUT_DN')}")
    print(f"AT_RESISTANCE:{sum(1 for v in valid.values() if v['signal']=='AT_RESISTANCE')}")
    print(f"AT_SUPPORT:   {sum(1 for v in valid.values() if v['signal']=='AT_SUPPORT')}")
    print(f"NEAR levels:  {sum(1 for v in valid.values() if 'NEAR' in v['signal'])}")
    print(f"NEUTRAL:      {sum(1 for v in valid.values() if v['signal']=='NEUTRAL')}")
    print(f"\nSaved: screen_output/sr_levels.json ({len(valid)} stocks)")


if __name__ == '__main__':
    main()
