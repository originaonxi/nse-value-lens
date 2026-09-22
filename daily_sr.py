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
from datetime import date, datetime, time
from zoneinfo import ZoneInfo
from pathlib import Path

warnings.filterwarnings('ignore')
import yfinance as yf
import numpy as np
import pandas as pd

HERE  = Path(__file__).resolve().parent
IST   = ZoneInfo('Asia/Kolkata')
MARKET_CLOSE = time(15, 30)   # NSE close; last bar excluded only before this
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


def compute_rsi(df, n=14):
    """RSI-14 using Wilder smoothing (EWM com=n-1)."""
    delta = df['Close'].diff()
    gain  = delta.clip(lower=0).ewm(com=n-1, adjust=True).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=n-1, adjust=True).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - 100 / (1 + rs)
    v = rsi.iloc[-1]
    return round(float(v), 1) if not np.isnan(v) else None


def compute_ema(series, span):
    """Exponential Moving Average, last value."""
    return float(series.ewm(span=span, adjust=False).mean().iloc[-1])


def compute_bollinger(df, n=20, k=2.0):
    """Bollinger Bands → (upper, mid, lower, %B, bandwidth). All last-bar values."""
    c   = df['Close']
    sma = c.rolling(n).mean()
    std = c.rolling(n).std(ddof=0)
    u, m, l = float(sma.iloc[-1] + k*std.iloc[-1]), float(sma.iloc[-1]), float(sma.iloc[-1] - k*std.iloc[-1])
    bw   = (u - l) / m if m else 0.0
    pctb = (float(c.iloc[-1]) - l) / (u - l) if (u - l) > 0 else 0.5
    return round(u,2), round(m,2), round(l,2), round(pctb,3), round(bw,3)


def compute_supertrend(df, n=10, mult=3.0):
    """Supertrend indicator. Returns (line_value, direction) where direction 1=bullish, -1=bearish.
    Uses numpy arrays to avoid pandas iloc-in-loop issues."""
    h  = df['High'].to_numpy(dtype=float)
    lo = df['Low'].to_numpy(dtype=float)
    c  = df['Close'].to_numpy(dtype=float)
    # True range (offset by 1 to align with h/lo from bar 1 onward)
    tr = np.maximum(h[1:]-lo[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(lo[1:]-c[:-1])))
    # Wilder ATR (EWM with alpha=1/n)
    alpha   = 1.0 / n
    atr_arr = np.empty(len(tr))
    atr_arr[0] = tr[0]
    for i in range(1, len(tr)):
        atr_arr[i] = alpha * tr[i] + (1 - alpha) * atr_arr[i-1]
    hl2   = (h[1:] + lo[1:]) / 2.0
    upper = hl2 + mult * atr_arr
    lower = hl2 - mult * atr_arr
    cs    = c[1:]  # close series aligned with atr
    fu    = upper.copy(); fl = lower.copy()
    dirn  = np.ones(len(cs), dtype=int)
    for i in range(1, len(cs)):
        fl[i] = lower[i] if (lower[i] > fl[i-1] or cs[i-1] < fl[i-1]) else fl[i-1]
        fu[i] = upper[i] if (upper[i] < fu[i-1] or cs[i-1] > fu[i-1]) else fu[i-1]
        if   cs[i] > fu[i-1]: dirn[i] = 1
        elif cs[i] < fl[i-1]: dirn[i] = -1
        else:                  dirn[i] = dirn[i-1]
    d   = int(dirn[-1])
    val = float(fl[-1]) if d == 1 else float(fu[-1])
    return round(val, 2), d


def compute_ichimoku(df):
    """Ichimoku Cloud — NO LOOKAHEAD.
    Today's actionable cloud = Senkou A & B computed 26 bars ago (already plotted forward).
    Requires ≥ 78 bars (52 + 26 displacement)."""
    if len(df) < 78:
        return None
    h = df['High']; lo = df['Low']; c = df['Close']
    tenkan  = (h.rolling(9).max()  + lo.rolling(9).min())  / 2  # conversion line
    kijun   = (h.rolling(26).max() + lo.rolling(26).min()) / 2  # base line
    sen_a   = (tenkan + kijun) / 2                               # Senkou A (unshifted)
    sen_b   = (h.rolling(52).max() + lo.rolling(52).min()) / 2  # Senkou B (unshifted)
    # Today's cloud = values from 26 bars ago (avoids lookahead bias)
    sa = float(sen_a.iloc[-27]) if len(sen_a) > 26 and not np.isnan(sen_a.iloc[-27]) else None
    sb = float(sen_b.iloc[-27]) if len(sen_b) > 26 and not np.isnan(sen_b.iloc[-27]) else None
    tn_now = float(tenkan.iloc[-1]); kj_now = float(kijun.iloc[-1])
    cl_now = float(c.iloc[-1])
    chikou_above = bool(cl_now > float(c.iloc[-27])) if len(c) > 26 else None
    ct = max(sa, sb) if (sa and sb) else None
    cb = min(sa, sb) if (sa and sb) else None
    above_cloud   = bool(cl_now > ct)  if ct else None
    below_cloud   = bool(cl_now < cb)  if cb else None
    bullish_cloud = bool(sa > sb)      if (sa and sb) else None
    return {
        'tenkan':       round(tn_now, 2),
        'kijun':        round(kj_now, 2),
        'senkou_a':     round(sa, 2) if sa else None,
        'senkou_b':     round(sb, 2) if sb else None,
        'cloud_top':    round(ct, 2) if ct else None,
        'cloud_bottom': round(cb, 2) if cb else None,
        'above_cloud':  above_cloud,
        'below_cloud':  below_cloud,
        'in_cloud':     (not above_cloud and not below_cloud) if above_cloud is not None else None,
        'bullish_cloud': bullish_cloud,
        'chikou_above':  chikou_above,
        'tenkan_above_kijun': bool(tn_now > kj_now),
    }


def swing_points(df, n=SWING_N):
    """Return ALL swing fractals as (bar_index, price) tuples — indices are
    also Anchored-VWAP event anchors, so keep them."""
    highs, lows = [], []
    h, l = df['High'].values, df['Low'].values
    for i in range(n, len(h) - n):
        window_h = list(h[i-n:i]) + list(h[i+1:i+n+1])
        if h[i] >= max(window_h):
            highs.append((i, float(h[i])))
        window_l = list(l[i-n:i]) + list(l[i+1:i+n+1])
        if l[i] <= min(window_l):
            lows.append((i, float(l[i])))
    return highs, lows


def swing_structure(df, n=SWING_N):
    """Dow Theory swing structure: label HH / HL / LH / LL on consecutive
    3-bar fractal pivots; classify the stock's structure state and expose
    the reversal trigger + invalidation levels. Used by S&R, SAM PICKS and
    the Swing Structure tab."""
    highs, lows = swing_points(df, n)
    idx = df.index
    events = [(i, p, 'H') for i, p in highs] + [(i, p, 'L') for i, p in lows]
    events.sort(key=lambda x: x[0])
    labeled = []
    prev_price = {'H': None, 'L': None}
    for i, p, t in events:
        prev = prev_price[t]
        if prev is not None:
            if t == 'H':
                lab = 'HH' if p > prev else 'LH'
            else:
                lab = 'HL' if p > prev else 'LL'
            labeled.append((i, p, t, lab))
        prev_price[t] = p
    if not labeled:
        return None
    last_h = next((x for x in reversed(labeled) if x[2] == 'H'), None)
    last_l = next((x for x in reversed(labeled) if x[2] == 'L'), None)
    if last_h is None or last_l is None:
        return None
    def _consec(which_type, target_label):
        run = 0
        for x in reversed([y for y in labeled if y[2] == which_type]):
            if x[3] == target_label:
                run += 1
            else:
                break
        return run
    consec_hh = _consec('H', 'HH')
    consec_lh = _consec('H', 'LH')
    consec_hl = _consec('L', 'HL')
    consec_ll = _consec('L', 'LL')
    # Label sequences for each side, in time order.
    highs_seq = [x[3] for x in labeled if x[2] == 'H']
    lows_seq  = [x[3] for x in labeled if x[2] == 'L']
    # Confidence guard: need at least 2 labelled pivots on each side, else the
    # structure is under-informed and we must not state a confident trend.
    if len(highs_seq) < 2 or len(lows_seq) < 2:
        structure = 'MIXED'
    # Most recent pivot each side — the structure state is decided by the
    # *last confirmed* pivot pair, not by earlier history.
    elif last_h[3] == 'HH' and last_l[3] == 'HL':
        structure = 'UPTREND'
    elif last_h[3] == 'LH' and last_l[3] == 'LL':
        structure = 'DOWNTREND'
    else:
        # Which pivot printed most recently decides the reversal direction.
        # Require evidence of the PRIOR opposite structure so ordinary
        # continuation is not mislabelled as a reversal setup.
        last_pivot_type = labeled[-1][2]   # 'H' or 'L'
        prior_lows  = lows_seq[:-1]   # lows before the newest low
        prior_highs = highs_seq[:-1]  # highs before the newest high
        if (last_pivot_type == 'L' and last_l[3] == 'HL'
                and last_h[3] in ('LH', 'HH') and 'LL' in prior_lows):
            # ...LL -> LH -> HL(newest): higher low after lower lows = 1-2-3 bottom SETUP
            structure = 'REVERSAL_UP'
        elif (last_pivot_type == 'H' and last_h[3] == 'LH'
                and last_l[3] in ('HL', 'LL') and 'HH' in prior_highs):
            # ...HH -> HL -> LH(newest): lower high after higher highs = 1-2-3 top SETUP
            structure = 'REVERSAL_DN'
        else:
            structure = 'MIXED'
    def _info(x):
        return {'label': x[3], 'price': round(x[1], 2),
                'date': idx[x[0]].strftime('%Y-%m-%d')}
    seq = [{'date': idx[i].strftime('%Y-%m-%d'), 'price': round(p, 2), 'label': lbl}
           for i, p, t, lbl in labeled][-10:]
    # Reversal trigger + invalidation, only if structure is forming
    # For REVERSAL_UP: buy on break of the *last swing high* (the LH between the lows)
    # For REVERSAL_DN: short/breakdown on break of the *last swing low* (the HL before the LH)
    rev_trigger = rev_invalidate = None
    if structure == 'REVERSAL_UP':
        rev_trigger    = {'price': round(last_h[1], 2), 'label': last_h[3], 'level': f"break of {last_h[3]} ₹{round(last_h[1],2)}"}
        rev_invalidate = {'price': round(last_l[1], 2), 'label': last_l[3], 'level': f"below {last_l[3]} ₹{round(last_l[1],2)}"}
    elif structure == 'REVERSAL_DN':
        rev_trigger    = {'price': round(last_l[1], 2), 'label': last_l[3], 'level': f"break of {last_l[3]} ₹{round(last_l[1],2)}"}
        rev_invalidate = {'price': round(last_h[1], 2), 'label': last_h[3], 'level': f"above {last_h[3]} ₹{round(last_h[1],2)}"}
    # Extended warnings
    extended = None
    if consec_hh >= 3: extended = f'{consec_hh} consecutive HH — extended uptrend, watch for first LH'
    elif consec_ll >= 3: extended = f'{consec_ll} consecutive LL — extended downtrend, watch for first HL'

    # ── BOS / CHoCH (informational — NOT action-changing until calibrated) ────
    close_now = float(df['Close'].iloc[-1])
    def _vfmt(v):
        if v is None: return 'n/a'
        if v >= 1e7:  return f"{v/1e7:.1f}Cr"
        if v >= 1e5:  return f"{v/1e5:.1f}L"
        return f"{int(v):,}"
    def _vol(idx_): return float(df['Volume'].iloc[idx_]) if 0 <= idx_ < len(df) else None

    bos   = None   # Break of Structure — trend continuing in its direction
    choch = None   # Change of Character — structure is weakening / turning

    if structure == 'UPTREND':
        if close_now > last_h[1]:
            bos   = {'fired': True, 'dir': 'UP',   'level': round(last_h[1],2),
                     'desc': f"BOS ✅ closed above last HH ₹{round(last_h[1],2)} — uptrend confirmed continuing"}
        if close_now < last_l[1]:
            choch = {'fired': True, 'dir': 'BEAR', 'level': round(last_l[1],2),
                     'desc': f"CHoCH ⚠️ closed below last HL ₹{round(last_l[1],2)} — uptrend character broken"}
    elif structure == 'DOWNTREND':
        if close_now < last_l[1]:
            bos   = {'fired': True, 'dir': 'DOWN', 'level': round(last_l[1],2),
                     'desc': f"BOS ✅ closed below last LL ₹{round(last_l[1],2)} — downtrend confirmed continuing"}
        if close_now > last_h[1]:
            choch = {'fired': True, 'dir': 'BULL', 'level': round(last_h[1],2),
                     'desc': f"CHoCH ⚠️ closed above last LH ₹{round(last_h[1],2)} — downtrend character broken"}
    elif structure == 'REVERSAL_UP':
        choch = {'fired': True, 'dir': 'BULL', 'level': round(last_l[1],2),
                 'desc': f"CHoCH ⚠️ already fired — HL ₹{round(last_l[1],2)} formed after lower lows (structure shifted bullish)"}
        if rev_trigger and close_now > rev_trigger['price']:
            bos = {'fired': True, 'dir': 'UP', 'level': rev_trigger['price'],
                   'desc': f"BOS ✅ closed above trigger ₹{rev_trigger['price']} — reversal UP now CONFIRMED, not just a setup"}
        elif rev_invalidate and close_now < rev_invalidate['price']:
            choch = {'fired': False, 'dir': 'BULL', 'level': rev_invalidate['price'],
                     'desc': f"⛔ setup FAILED — closed below HL ₹{rev_invalidate['price']}, reversal invalidated"}
    elif structure == 'REVERSAL_DN':
        choch = {'fired': True, 'dir': 'BEAR', 'level': round(last_h[1],2),
                 'desc': f"CHoCH ⚠️ already fired — LH ₹{round(last_h[1],2)} formed after higher highs (structure shifted bearish)"}
        if rev_trigger and close_now < rev_trigger['price']:
            bos = {'fired': True, 'dir': 'DOWN', 'level': rev_trigger['price'],
                   'desc': f"BOS ✅ closed below trigger ₹{rev_trigger['price']} — reversal DOWN now CONFIRMED, not just a setup"}
        elif rev_invalidate and close_now > rev_invalidate['price']:
            choch = {'fired': False, 'dir': 'BEAR', 'level': rev_invalidate['price'],
                     'desc': f"⛔ setup FAILED — closed above LH ₹{rev_invalidate['price']}, reversal invalidated"}

    # ── Wyckoff volume phase (informational — forward-log to calibration) ─────
    vol_h = _vol(last_h[0]); vol_l = _vol(last_l[0])
    wyckoff = None
    if vol_h and vol_l:
        if structure == 'UPTREND':
            high_vol = vol_h >= vol_l * 0.9
            wyckoff = {'phase': 'MARKUP', 'conviction': 'HIGH' if high_vol else 'LOW',
                       'vol_at_last_high': int(vol_h), 'vol_at_last_low': int(vol_l),
                       'note': (f"MARKUP — breakout highs on {_vfmt(vol_h)} vs pullback lows {_vfmt(vol_l)}. "
                                + ("Healthy: breakouts attract volume." if high_vol
                                   else "⚠️ Rallies thinning vs pullbacks — watch for distribution."))}
        elif structure == 'DOWNTREND':
            down_vol = vol_l >= vol_h * 0.9
            wyckoff = {'phase': 'MARKDOWN', 'conviction': 'HIGH' if down_vol else 'LOW',
                       'vol_at_last_high': int(vol_h), 'vol_at_last_low': int(vol_l),
                       'note': (f"MARKDOWN — breakdown lows on {_vfmt(vol_l)} vs bounce highs {_vfmt(vol_h)}. "
                                + ("Real sellers driving down." if down_vol
                                   else "⚠️ Selling on low volume — potential exhaustion."))}
        elif structure == 'REVERSAL_UP':
            prior_ll = [x for x in labeled if x[2]=='L' and x[3]=='LL']
            v_pll = _vol(prior_ll[-1][0]) if prior_ll else None
            if v_pll:
                acc = vol_l >= v_pll * 0.70
                wyckoff = {'phase': 'ACCUMULATION', 'conviction': 'HIGH' if acc else 'LOW',
                           'vol_at_hl': int(vol_l), 'vol_at_prior_ll': int(v_pll),
                           'note': (f"ACCUMULATION — vol at HL {_vfmt(vol_l)} vs prior LL {_vfmt(v_pll)}. "
                                    + ("✅ Buyers sustaining at higher low = real accumulation." if acc
                                       else "⚠️ Volume thinning at HL = weak bounce, no conviction."))}
        elif structure == 'REVERSAL_DN':
            prior_hh = [x for x in labeled if x[2]=='H' and x[3]=='HH']
            v_phh = _vol(prior_hh[-1][0]) if prior_hh else None
            if v_phh:
                dist = vol_h < v_phh * 0.85
                wyckoff = {'phase': 'DISTRIBUTION', 'conviction': 'HIGH' if dist else 'LOW',
                           'vol_at_lh': int(vol_h), 'vol_at_prior_hh': int(v_phh),
                           'note': (f"DISTRIBUTION — vol at LH {_vfmt(vol_h)} vs prior HH {_vfmt(v_phh)}. "
                                    + ("✅ Buyers fading at lower high = real distribution." if dist
                                       else "⚠️ Volume still high at LH = buyers fighting, setup less clean."))}

    return {
        'structure':           structure,
        'consec_hh':           consec_hh,
        'consec_lh':           consec_lh,
        'consec_hl':           consec_hl,
        'consec_ll':           consec_ll,
        'last_high':           _info(last_h),
        'last_low':            _info(last_l),
        'reversal_trigger':    rev_trigger,
        'reversal_invalidate': rev_invalidate,
        'extended_warning':    extended,
        'sequence':            seq,
        'bos':                 bos,
        'choch':               choch,
        'wyckoff':             wyckoff,
    }


def swing_highs_lows(df, n=SWING_N, top=5):
    """Return the most-RECENT swing highs and swing lows (by bar index)."""
    highs, lows = swing_points(df, n)
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


def volume_density_at(df, price, periods=90, n_bins=50):
    """Relative volume-at-price density (0..1) at `price` — same proportional
    distribution as volume_poc. 1.0 = the POC itself. Institutional levels
    are where volume actually traded [Murtazin 2025]."""
    d = df.tail(periods)
    hi_max, lo_min = float(d['High'].max()), float(d['Low'].min())
    rng = hi_max - lo_min
    if rng <= 0 or not (lo_min <= price <= hi_max):
        return 0.0
    bsz = rng / n_bins
    vol_bins = [0.0] * n_bins
    for _, row in d.iterrows():
        h, l, v = float(row['High']), float(row['Low']), float(row['Volume'])
        span = h - l
        for i in range(n_bins):
            b_lo = lo_min + i * bsz
            overlap = min(h, b_lo + bsz) - max(l, b_lo)
            if overlap > 0:
                vol_bins[i] += v * (overlap / span if span > 0 else 1.0)
    if not max(vol_bins):
        return 0.0
    idx = min(n_bins - 1, int((price - lo_min) / bsz))
    return vol_bins[idx] / max(vol_bins)


def anchored_vwap(df, anchor_idx):
    """VWAP from an event anchor (swing extreme, 52w extreme, breakout bar) to
    the latest bar. Volume-weighted average cost of participants since the
    turning point — institutional dynamic S/R [Brian Shannon, AVWAP]."""
    d = df.iloc[anchor_idx:]
    if d.empty:
        return None
    total_vol = float(d['Volume'].sum())
    if total_vol <= 0:
        return None
    tp = (d['High'] + d['Low'] + d['Close']) / 3
    return float((tp * d['Volume']).sum() / total_vol)


def round_levels(close, atr):
    """Nearby psychological round numbers — stop/limit orders cluster at them
    [Osler 2000 stop-clustering research; Aggarwal & Lucey round-number bias]."""
    mag = 10 ** max(0, len(str(int(close))) - 2)   # 10 for 3xx, 100 for 1xxx+
    if mag >= 100:
        grid = [mag, mag / 2, mag / 5]              # 100, 50, 20
    else:
        grid = [mag, mag / 2]                       # 10, 5
    out = []
    for g in grid:
        for k in (-1, 0, 1):
            lvl = round(round(close / g) * g + k * g, 2)
            if abs(lvl - close) <= NEAR_ATR * atr and lvl > 0:
                out.append(lvl)
    return sorted(set(out))


def touches_rejection(df, zone_price, atr, buf=0.25, min_gap=5):
    """Independent tests of a zone (±buf ATR) that reversed: count + mean
    rejection depth in ATR. More touches + deeper rejections = defended level
    [Osler: S/R levels predict trend interruptions]."""
    if not atr:
        return 0, 0.0
    lo, hi = zone_price - buf * atr, zone_price + buf * atr
    touches, last_touch = [], -min_gap - 1
    for i in range(len(df)):
        l, h = float(df['Low'].iloc[i]), float(df['High'].iloc[i])
        if l <= hi and h >= lo and i - last_touch >= min_gap:
            # entered the zone — did it reject?
            c = float(df['Close'].iloc[i])
            rej = abs(c - zone_price) / atr
            touches.append(rej)
            last_touch = i
    n = len(touches)
    return n, (sum(touches) / n if n else 0.0)


def cluster_candidates(cands, atr):
    """Provenance-preserving clustering: merge candidate levels closer than
    0.5 ATR, keeping every contributing source. Price = source-weighted mean."""
    if not cands:
        return []
    cands = sorted(cands, key=lambda c: c['price'])
    clusters, group = [], [cands[0]]
    for c in cands[1:]:
        if c['price'] - group[-1]['price'] < 0.5 * atr:
            group.append(c)
        else:
            clusters.append(group); group = [c]
    clusters.append(group)
    out = []
    for g in clusters:
        wsum = sum(c['weight'] for c in g)
        price = sum(c['price'] * c['weight'] for c in g) / wsum
        out.append({'price': price,
                    'sources': sorted({c['source'] for c in g}),
                    'members': g})
    return out


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
        # Market-date guard: only drop the last row from S/R history when it is
        # actually the CURRENT session (possibly incomplete intraday bar).
        # On holidays/weekends the last row is a completed session and MUST
        # stay in history — otherwise pivots/Swing/K-means rebalance one
        # session stale.
        now_ist   = datetime.now(IST)
        today_ist = now_ist.date()
        last_date = df.index[-1].date() if hasattr(df.index[-1], 'date') else None
        market_open_now = now_ist.time() < MARKET_CLOSE and now_ist.weekday() < 5
        if last_date == today_ist and market_open_now:
            today   = df.iloc[-1]
            df_hist = df.iloc[:-1]      # intraday session separate — partial bar
        else:
            today   = df.iloc[-1]       # last completed session (or latest trade)
            df_hist = df                # all rows are completed candles
        # "prior" = bars strictly BEFORE the latest session — used for vol20
        # and the Donchian breakout trigger so a breakout can legitimately
        # fire (close vs PRIOR-20d high) and vol_ratio compares vs past avg.
        df_prior = df.iloc[:-1]
        close   = float(today['Close'])
        vol     = float(today['Volume'])
        vol20   = float(df_prior['Volume'].tail(VOL_N).mean())
        atr     = atr14(df_hist)
        if not atr:
            return symbol, {'error': 'atr_failed'}

        # ── New: RSI14 / EMA10/20/50 / Bollinger / Supertrend / Ichimoku ────
        rsi_val  = compute_rsi(df_hist)
        ema10_v  = compute_ema(df_hist['Close'], 10)
        ema20_v  = compute_ema(df_hist['Close'], 20)
        ema50_v  = compute_ema(df_hist['Close'], 50)
        bb_upper_v, bb_mid_v, bb_lower_v, bb_pctb, bb_bw = compute_bollinger(df_hist)
        st_val, st_dir = compute_supertrend(df_hist)
        ichi    = compute_ichimoku(df_hist)
        ema_trend   = ('UP'   if ema10_v > ema20_v > ema50_v else
                       'DOWN' if ema10_v < ema20_v < ema50_v else 'MIXED')
        above_ema50 = close > ema50_v
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

        # ── Method 6: Anchored VWAP from event anchors ────────────────────
        # Anchors: most-recent swing low/high, 52w low/high, last 20d-close
        # breakout bar. AVWAP = volume-weighted participant cost since the
        # turning point [Brian Shannon]. JEV-picked as highest-value add.
        hi_pts, lo_pts = swing_points(df_hist)
        swing_struct = swing_structure(df_hist)
        i_hi52 = len(df_hist) - len(df52) + int(df52['High'].values.argmax())
        i_lo52 = len(df_hist) - len(df52) + int(df52['Low'].values.argmin())
        # most recent bar whose close exceeded the trailing 20 closes (anchor)
        i_bo = None
        closes_h = df_hist['Close'].values
        for i in range(len(closes_h) - 1, max(20, len(closes_h) - 31), -1):
            if closes_h[i] > max(closes_h[i-20:i]):
                i_bo = i
                break
        anchors = {}
        if lo_pts: anchors['swing_low']  = sorted(lo_pts, key=lambda x: x[0])[-1][0]
        if hi_pts: anchors['swing_high'] = sorted(hi_pts, key=lambda x: x[0])[-1][0]
        anchors['low_52w']  = i_lo52
        anchors['high_52w'] = i_hi52
        if i_bo is not None: anchors['breakout'] = i_bo
        avwap = {name: anchored_vwap(df_hist, idx) for name, idx in anchors.items()}
        avwap = {k: round(v, 2) for k, v in avwap.items() if v is not None}
        avwap_vals = list(avwap.values())

        # ── Method 7: round-number order clustering ───────────────────────
        rounds = round_levels(close, atr)

        # ── 20-session Donchian from PRIOR bars only (BREAKOUT TRIGGER) ───
        d20_hi = float(df_prior['High'].tail(20).max())
        d20_lo = float(df_prior['Low'].tail(20).min())
        # ── Combine all 6-method resistances and supports ─────────────────
        all_res = dedupe_levels(sorted(set(
            sh + pivot_r + [hi52] + km_res + poc_res + vwap_res
        )), atr)
        all_sup = dedupe_levels(sorted(set(
            sl + pivot_s + [lo52] + km_sup + poc_sup + vwap_sup
        )), atr)
        res_above = [r for r in all_res if r > close]
        sup_below = [s for s in all_sup if s < close]

        # ── Confluence zones: provenance-preserving clusters, scored ─────
        # Strength(L) = 0.40*VolumeDensity + 0.25*Touches + 0.20*Rejection
        #             + 0.15*(AVWAP or round-number confluence)
        SRC_W = {'vp':1.6,'vwap':1.4,'avwap':1.4,'52w':1.3,'poc':1.6}
        cands = []
        for i, p in enumerate(sh, 1):
            cands.append({'price':p,'source':'swing','label':f'Swing high #{i}','weight':1.0})
        for i, p in enumerate(sl, 1):
            cands.append({'price':p,'source':'swing','label':f'Swing low #{i}','weight':1.0})
        for label, p in zip(['Pivot R1','Pivot R2','Pivot R3'], pivot_r):
            cands.append({'price':p,'source':'pivot','label':label,'weight':0.8})
        for label, p in zip(['Pivot S1','Pivot S2','Pivot S3'], pivot_s):
            cands.append({'price':p,'source':'pivot','label':label,'weight':0.8})
        cands.append({'price':hi52,'source':'52w','label':'52-week high','weight':SRC_W['52w']})
        cands.append({'price':lo52,'source':'52w','label':'52-week low','weight':SRC_W['52w']})
        for i, p in enumerate(km_levels, 1):
            cands.append({'price':p,'source':'kmeans','label':f'K-means centroid #{i}','weight':1.0})
        for label, p in [('Volume Profile POC', poc), ('Volume Profile VAH', vah), ('Volume Profile VAL', val)]:
            if p: cands.append({'price':p,'source':'vp','label':label,'weight':SRC_W['vp']})
        cands.append({'price':vwap20,'source':'vwap','label':'20-day VWAP','weight':SRC_W['vwap']})
        for name, v in avwap.items():
            cands.append({'price':v,'source':'avwap','label':f'Anchored VWAP {name}','weight':SRC_W['avwap']})
        for p in rounds:
            cands.append({'price':p,'source':'round','label':f'Round number {p:g}','weight':0.6})
        clusters = cluster_candidates(cands, atr)
        for cl in clusters:
            p   = cl['price']
            vp_d = volume_density_at(df_hist, p)
            tch, rej = touches_rejection(df_hist, p, atr)
            has_avwap = any(abs(a - p) <= 0.5 * atr for a in avwap_vals)
            has_round = any(abs(r - p) <= 0.25 * atr for r in rounds)
            members = cl.pop('members', [])
            cl.update({
                'price': round(p, 2),
                'n_sources': len(cl['sources']),
                'components': [
                    {'source': m['source'], 'label': m.get('label', m['source']),
                     'price': round(m['price'], 2), 'weight': round(m['weight'], 2)}
                    for m in members
                ],
                'vp_density': round(vp_d, 2),
                'touches': tch,
                'rejection_atr': round(rej, 2),
                'has_avwap': has_avwap,
                'has_round': has_round,
                'strength': round(0.40 * vp_d + 0.25 * min(tch / 4, 1)
                                  + 0.20 * min(rej / 2, 1)
                                  + 0.15 * (1 if (has_avwap or has_round) else 0), 2),
            })
        sup_clusters = sorted((c for c in clusters if c['price'] < close),
                              key=lambda c: c['price'], reverse=True)
        res_clusters = sorted((c for c in clusters if c['price'] > close),
                              key=lambda c: c['price'])
        # floor/ceiling = NEAREST actionable zones; strongest exposed separately
        cl_floor   = sup_clusters[0] if sup_clusters else None
        cl_ceiling = res_clusters[0] if res_clusters else None
        strongest = lambda lst: (max(lst, key=lambda c: c['strength']) if lst else None)

        # ── Breakout: ATR-buffered + volume, plus reclaim / trap flags ───
        # Real break = close beyond level ± 0.25 ATR AND >1.5× 20d median
        # volume (Osler: order clusters consume at levels; volume = participation)
        BO_BUF   = 0.25
        vol20_med = statistics.median(df_prior['Volume'].tail(VOL_N)) if len(df_prior) else vol20
        vol_ok    = vol > VOL_MUL * vol20_med
        bo_up   = close > d20_hi + BO_BUF * atr and vol_ok
        bo_dn   = close < d20_lo - BO_BUF * atr and vol_ok
        bo_str  = round((close - d20_hi) / atr, 2) if bo_up else \
                  round((d20_lo - close) / atr, 2) if bo_dn else 0.0
        prior5      = list(df_prior['Close'].tail(5).values)
        reclaim     = (not bo_up) and any(c < d20_lo - BO_BUF * atr for c in prior5) \
                               and close > d20_lo + BO_BUF * atr
        failed_bo   = (not bo_dn) and any(c > d20_hi + BO_BUF * atr for c in prior5) \
                               and close < d20_hi - BO_BUF * atr

        # floor/ceiling = nearest actionable CONFLUENCE zones (name/priceressed cluster);
        # fall back to legacy nearest deduped level if clustering produced none
        nr = cl_ceiling['price'] if cl_ceiling else \
             (min(res_above, key=lambda r: r-close) if res_above else None)
        ns = cl_floor['price'] if cl_floor else \
             (max(sup_below) if sup_below else None)   # highest value below close = nearest
        dr = round(abs(close-nr)/atr, 2) if nr else None
        ds = round(abs(close-ns)/atr, 2) if ns else None
        if bo_up:
            signal = 'BREAKOUT_UP'
        elif bo_dn:
            signal = 'BREAKOUT_DN'
        else:
            signal, _, _, _, _ = classify(close, [nr] if nr else [], [ns] if ns else [], atr)
            # recompute distances against the cluster floor/ceiling
            dr = round(abs(close-nr)/atr, 2) if nr else None
            ds = round(abs(close-ns)/atr, 2) if ns else None
            if   dr is not None and dr <= AT_ATR:   signal = 'AT_RESISTANCE'
            elif ds is not None and ds <= AT_ATR:   signal = 'AT_SUPPORT'
            elif dr is not None and dr <= NEAR_ATR: signal = 'NEAR_RESISTANCE'
            elif ds is not None and ds <= NEAR_ATR: signal = 'NEAR_SUPPORT'
            else:                                   signal = 'NEUTRAL'

        # ── Plain-English output fields ───────────────────────────────────
        # "floor" = nearest support; "ceiling" = nearest resistance
        # "next_target" = if price rises, first meaningful resistance above ceiling
        # "next_floor"  = if price drops, first meaningful support below floor
        floor   = ns
        ceiling = nr
        # next levels come from the same confluence clusters as nr/ns, so
        # "next target" always sits beyond the level we just identified
        legacy_next_res = sorted([r for r in res_above if r > (nr or 0)])
        legacy_next_sup = sorted([s for s in sup_below if s < (ns or close)], reverse=True)
        next_target = res_clusters[1]['price'] if len(res_clusters) > 1 else \
                      (legacy_next_res[0] if legacy_next_res else None)
        next_floor  = sup_clusters[1]['price'] if len(sup_clusters) > 1 else \
                      (legacy_next_sup[0] if legacy_next_sup else None)
        strength_label = lambda cl: ('STRONG' if cl['strength'] >= 0.65
                                     else 'SOLID' if cl['strength'] >= 0.45
                                     else 'WEAK') if cl else None

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
        # confluence/trap notes appended to plain text for the layman UI
        con_note = ''
        if cl_floor and signal in ('AT_SUPPORT','NEAR_SUPPORT') and cl_floor['strength'] >= 0.45:
            con_note = f" Floor is {strength_label(cl_floor).lower()} ({cl_floor['n_sources']} methods agree)."
        if cl_ceiling and signal in ('AT_RESISTANCE','NEAR_RESISTANCE') and cl_ceiling['strength'] >= 0.45:
            con_note = f" Ceiling is {strength_label(cl_ceiling).lower()} ({cl_ceiling['n_sources']} methods agree)."
        if reclaim:      con_note += ' Price fell below the floor and bounced back above it — buyers defending.'
        if failed_bo and not reclaim: con_note += ' Earlier breakout failed and price fell back — likely bull trap.'

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
            'plain_signal': PLAIN.get(signal, signal) + con_note,
            'action':       ACTION.get(signal, ''),
            'floor':         round(floor,   2) if floor   else None,
            'ceiling':       round(ceiling, 2) if ceiling else None,
            'next_target':   round(next_target, 2) if next_target else None,
            'next_floor':    round(next_floor,  2) if next_floor  else None,
            'above_vwap':    above_vwap,
            'vwap20':        round(vwap20, 2),
            'floor_strength':   cl_floor['strength'] if cl_floor else None,
            'ceiling_strength': cl_ceiling['strength'] if cl_ceiling else None,
            'reclaim_support':  reclaim,
            'failed_breakout':  failed_bo,
            'breakout_confirmed': bool(bo_up or bo_dn),
            'breakout_buffer_atr': 0.25,
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
            'avwap': avwap,
            'round_levels': [round(x,2) for x in rounds],
            'confluence': {
                'floor': cl_floor,
                'ceiling': cl_ceiling,
                'strongest_support': strongest(sup_clusters),
                'strongest_resistance': strongest(res_clusters),
                'top_supports': sorted(sup_clusters, key=lambda c: c['strength'], reverse=True)[:3],
                'top_resistances': sorted(res_clusters, key=lambda c: c['strength'], reverse=True)[:3],
            },
            # ── New technical indicators ─────────────────────────────────
            'rsi14':          rsi_val,
            'ema10':          round(ema10_v, 2),
            'ema20':          round(ema20_v, 2),
            'ema50':          round(ema50_v, 2),
            'ema_trend':      ema_trend,
            'above_ema50':    above_ema50,
            'bb_upper':       bb_upper_v,
            'bb_mid':         bb_mid_v,
            'bb_lower':       bb_lower_v,
            'bb_pct_b':       bb_pctb,
            'bb_bandwidth':   bb_bw,
            'supertrend':     st_val,
            'supertrend_dir': st_dir,
            'ichimoku':       ichi,
            'swing_structure': swing_struct,
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
        'error_detail':  {k: v for k, v in errors.items()},
        'methods': [
            'Swing High/Low (fractal, most-recent 5 each side)',
            'Classic Pivot Points PP/R1/R2/S1/S2 (yesterday OHLC)',
            '52-week High/Low (institutional anchor)',
            'K-means clustering on 90-session prices (Tengelin/Sopasakis 2020)',
            'Volume-at-Price POC + 70% Value Area (Volume Profile)',
            '20-day VWAP — rolling institutional fair-value benchmark',
            'Anchored VWAP from swing/52w/breakout event anchors',
            'Psychological round-number levels',
            'Provenance-preserving confluence zones: 40% volume profile, 25% touches, 20% rejection, 15% AVWAP/round confluence',
        ],
        'breakout_trigger': f'Donchian 20d high/low + 0.25 ATR buffer + vol > {VOL_MUL}× 20d median volume',
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
