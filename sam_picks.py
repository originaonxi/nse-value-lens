#!/usr/bin/env python3
"""
sam_picks.py — SAM PICKS: synthesis of every data layer into one ranked action list.

Reads:
  screen_output/sr_levels.json      daily S&R, confluence, JEV trade scores
  screen_output/jev_rank.json       JEV-ranked setup quality / follow-through / R:R
  screen_output/monthly_regimes.json monthly regime direction, age, reversal risk

Composite SAM SCORE formula (all components 0-1 or -1 to +1):
  SAM = 0.30 × regime_component
      + 0.25 × sr_signal_component
      + 0.25 × jev_component × sign(regime + sr_signal)   ← directional: good bearish setup REDUCES SAM
      + 0.20 × confluence_component

Regime component (+1 = strong UP, -1 = strong DOWN):
  UP  regime: +0.5 × (1 + JEV_quality_norm × 0.4 + JEV_persistence_norm × 0.4 + (1-JEV_rw_norm) × 0.2)
  DOWN regime: mirror
  SIDE / N/A: 0

Signal component (daily S&R):
  BREAKOUT_UP=+1.0  AT_SUPPORT=+0.7  NEAR_SUPPORT=+0.35
  NEUTRAL=0
  NEAR_RESISTANCE=-0.35  AT_RESISTANCE=-0.60  BREAKOUT_DN=-1.0

JEV component (from jev_rank.json):
  composite value direct (already 0-1)

Confluence component:
  For positive signals: floor_strength (0-1)
  For negative signals: -(ceiling_strength)

Action classification:
  SAM > +0.50 and UP regime and bullish signal      -> BUY
  SAM > +0.35 and bullish signal                    -> WATCH_BUY
  SAM < -0.40 and DOWN regime and bearish signal    -> AVOID
  SAM < -0.25 and bearish signal                    -> CAUTION
  reclaim_support=True                              -> WATCH (potential reversal)
  else                                              -> NEUTRAL

Target / stop / R:R (BUY):
  entry   = close
  stop    = floor - 0.25 × ATR14 (one ATR-buffer below the floor)
  target1 = ceiling
  target2 = next_target
  R:R     = (target1 - entry) / (entry - stop)

Outputs:
  screen_output/sam_picks.json   machine-readable full output
  public/data/sam_picks.js       window.SAM_PICKS for Pages UI
"""
import json
from pathlib import Path
from datetime import date

HERE = Path(__file__).resolve().parent
OUT  = HERE / "screen_output"
JS_OUT = HERE / "public" / "data" / "sam_picks.js"

SIG_SCORE = {
    'BREAKOUT_UP':    +1.00,
    'AT_SUPPORT':     +0.70,
    'NEAR_SUPPORT':   +0.35,
    'NEUTRAL':         0.00,
    'NEAR_RESISTANCE':-0.35,
    'AT_RESISTANCE':  -0.60,
    'BREAKOUT_DN':    -1.00,
}

ACTION_LABELS = {
    'BUY':       '🟢 BUY',
    'WATCH_BUY': '🔵 WATCH — setup forming',
    'AVOID':     '🔴 AVOID',
    'CAUTION':   '🟠 CAUTION',
    'WATCH':     '🟡 WATCH — reversal possible',
    'NEUTRAL':   '⚪ NEUTRAL',
}


def regime_component(mr):
    if not mr or mr.get('recently_listed'):
        return 0.0, 'N/A'
    label = mr['current']['label']
    j = mr.get('jev') or {}
    q   = (j.get('regime_quality',    0) or 0) / 4     # 0-1
    p   = (j.get('persistence_odds',  0) or 0) / 4     # 0-1
    rw  = (j.get('reversal_watch',    0) or 0) / 4     # 0-1; inverted below
    rw_inv = 1 - rw
    if label == 'UP':
        score = 0.5 * (1 + q * 0.4 + p * 0.4 + rw_inv * 0.2)
    elif label == 'DOWN':
        score = -0.5 * (1 + (1-q)*0.4 + (1-p)*0.4 + rw*0.2)
    else:
        score = 0.0
    return round(score, 4), label


def confluence_comp(sr, signal_score):
    conf = sr.get('confluence') or {}
    if signal_score >= 0:
        fl = conf.get('floor') or {}
        return round(float(fl.get('strength', 0) or 0), 4)
    else:
        cl = conf.get('ceiling') or {}
        return round(-float(cl.get('strength', 0) or 0), 4)


def classify(sam, sr, mr, jev_row=None):
    label   = (mr or {}).get('current', {}).get('label', 'SIDE')
    signal  = sr.get('signal', 'NEUTRAL')
    reclaim = sr.get('reclaim_support', False)
    failed  = sr.get('failed_breakout', False)
    bull    = signal in ('BREAKOUT_UP', 'AT_SUPPORT', 'NEAR_SUPPORT')
    bear    = signal in ('BREAKOUT_DN', 'AT_RESISTANCE', 'NEAR_RESISTANCE')
    rsi     = sr.get('rsi14')
    close   = sr.get('close', 0)
    ema50   = sr.get('ema50') or (close + 1)
    st_dir  = sr.get('supertrend_dir')
    ema_t   = sr.get('ema_trend')
    ichi    = sr.get('ichimoku') or {}
    bearish_tech_count = sum([
        ema_t == 'DOWN',
        st_dir == -1,
        bool(ichi.get('below_cloud')),
    ])

    # ── Hard deterministic vetoes — code owns these, Jev cannot override ─────
    # Veto 1: Supertrend bearish + below EMA50 + DOWN regime + bearish signal → AVOID
    if (st_dir == -1 and close < ema50 and label == 'DOWN' and bear):
        return 'AVOID'
    # ── Normal classification ─────────────────────────────────────────────────
    if sam >= 0.50 and label == 'UP' and bull:
        action = 'BUY'
    elif sam >= 0.35 and bull:
        action = 'WATCH_BUY'
    elif sam <= -0.40 and label == 'DOWN' and bear:
        action = 'AVOID'
    elif sam <= -0.25 and bear:
        action = 'CAUTION'
    elif reclaim:
        action = 'WATCH'
    elif failed:
        action = 'CAUTION'
    else:
        action = 'NEUTRAL'
    # ── Trend contradiction guard: support-bounce only, not a clean BUY ───────
    if action == 'BUY' and bearish_tech_count >= 2:
        action = 'WATCH_BUY'
    # ── JEV confidence gate (calibrated probability, paper §V) ───────────────
    confidence = (jev_row or {}).get('confidence_gate')
    if confidence is not None and confidence < 0.45:
        if action == 'BUY':     action = 'WATCH_BUY'
        elif action == 'AVOID': action = 'CAUTION'
    # ── RSI hard cap: don't chase extreme overbought for BUY ─────────────────
    if rsi and rsi > 82 and action == 'BUY':
        action = 'WATCH_BUY'
    return action


def risk_reward(sr):
    close   = sr.get('close')
    floor_p = sr.get('floor')
    ceil_p  = sr.get('ceiling')
    atr     = sr.get('atr14')
    nxt     = sr.get('next_target')
    if not (close and floor_p and ceil_p and atr):
        return None, None, None
    stop   = round(floor_p - 0.25 * atr, 2)
    risk   = close - stop
    if risk <= 0:
        return stop, ceil_p, None
    rr1 = round((ceil_p - close) / risk, 2)
    return stop, ceil_p, rr1



def build_why(sr, mr, jev_row, reg_comp, sig_comp, conf_comp, sam, jev_comp=0.0, dir_sign=0):
    """Elevator-pitch reasons — layman first, real numbers, verifiable, formula underneath."""
    reasons = []
    label   = (mr or {}).get('current', {}).get('label', '?')
    age     = (mr or {}).get('current', {}).get('age_months')
    rr_rat  = (mr or {}).get('reversal_risk_ratio')
    avg12   = (mr or {}).get('current', {}).get('avg_12m_ret_pct')
    signal  = sr.get('signal', '')
    close   = sr.get('close')
    floor_p = sr.get('floor')
    ceil_p  = sr.get('ceiling')
    fl_str  = sr.get('floor_strength')
    cl_str  = sr.get('ceiling_strength')
    atr     = sr.get('atr14')
    vwap    = sr.get('vwap20')
    above_v = sr.get('above_vwap')
    vol_r   = sr.get('vol_ratio')
    reclaim = sr.get('reclaim_support', False)
    bo_conf = sr.get('breakout_confirmed', False)
    conf    = sr.get('confluence') or {}
    fl_cl   = conf.get('floor') or {}
    cl_cl   = conf.get('ceiling') or {}
    fl_n    = fl_cl.get('n_sources', 0)
    cl_n    = cl_cl.get('n_sources', 0)
    fl_src  = ', '.join(fl_cl.get('sources') or [])
    cl_src  = ', '.join(cl_cl.get('sources') or [])
    d_sup   = round(sr.get('dist_support_atr') or 0, 2)
    d_res   = round(sr.get('dist_resistance_atr') or 0, 2)
    rsi_val = sr.get('rsi14')
    ema_t   = sr.get('ema_trend')
    ema10   = sr.get('ema10')
    ema20   = sr.get('ema20')
    ema50   = sr.get('ema50')
    above50 = sr.get('above_ema50')
    bb_pctb = sr.get('bb_pct_b')
    bb_up   = sr.get('bb_upper')
    bb_mid  = sr.get('bb_mid')
    bb_lo   = sr.get('bb_lower')
    st_dir  = sr.get('supertrend_dir')
    st_val  = sr.get('supertrend')
    ichi    = sr.get('ichimoku') or {}
    jconf   = (jev_row or {}).get('confidence_gate')
    jreg    = str((jev_row or {}).get('regime_jev') or 'n/a').replace('_',' ')
    jdir    = str((jev_row or {}).get('direction_jev') or 'n/a')
    jsq     = (jev_row or {}).get('setup_quality')
    jft     = (jev_row or {}).get('follow_through')
    jrr_j   = (jev_row or {}).get('risk_reward')

    # ── 1. SAM SCORE — overall verdict, sorted first ─────────────────────────
    bear_or_bull = 'bullish' if sam > 0 else 'bearish' if sam < 0 else 'neutral'
    reasons.append({
        'icon': '⭐',
        'layman': (
            f"SAM score {round(sam*100)}/100 — our composite reads {bear_or_bull} "
            f"(monthly trend 30% + daily signal 25% + AI setup quality 25% + confluence 20%). "
            f"Every number below feeds into this single score. Higher = more layers agree."
        ),
        'formula': f"SAM = 0.30×({reg_comp:+.3f}) + 0.25×({sig_comp:+.3f}) + 0.25×(jev={jev_comp:.3f}×dir={dir_sign:+d}) + 0.20×({conf_comp:+.3f}) = {sam:+.3f}",
    })

    # ── 2. Monthly regime ─────────────────────────────────────────────────────
    if label and label != 'N/A':
        stretched = rr_rat and rr_rat > 1.5
        river = 'flowing upriver' if label == 'UP' else 'flowing downhill — swim against it at your own risk' if label == 'DOWN' else 'going sideways'
        stretch_note = f" Caution: at {age} months this trend is getting long in the tooth (reversal risk {rr_rat}×) — consider tighter stops." if stretched else ""
        reasons.append({
            'icon': '📅',
            'layman': (
                f"Big-picture trend (last 12 months): {label} for {age} months, avg return {avg12}%. "
                f"Think of the monthly trend as checking which way the river is {river}. "
                f"Trend-following systems pay attention to this backdrop — being aligned with it matters.{stretch_note}"
            ),
            'formula': f"12m trailing return > +5% = UP, < -5% = DOWN, else SIDE. Reversal risk ratio = {rr_rat}× (current age ÷ historical mean duration). Component = {reg_comp:+.2f}",
        })

    # ── 3. Volume + daily signal ──────────────────────────────────────────────
    vol_r_str = f"{vol_r:.1f}× the 20-day avg" if isinstance(vol_r, (int, float)) else "unknown volume vs 20-day avg"
    vol_txt = ''
    if isinstance(vol_r, (int, float)):
        if vol_r >= 2.0:
            vol_txt = f"Today's volume was {vol_r_str} — very heavy versus the 20-day average. "
        elif vol_r >= 1.5:
            vol_txt = f"Today's volume was {vol_r_str} — above-average, real conviction behind the move. "
        elif vol_r >= 1.0:
            vol_txt = f"Today's volume was {vol_r_str} — normal; the move is consistent but not exceptional. "
        else:
            vol_txt = f"Today's volume was only {vol_r_str} — below-average; treat this signal cautiously. "

    sig_explain = {
        'BREAKOUT_UP':   f"Price broke ABOVE the 20-day high on {vol_r_str}. {vol_txt}Buying pressure is visible because price cleared the recent high and volume confirmed the move. Low-volume breakouts are weaker and more likely to fail. Nearest support floor ₹{floor_p} is {d_sup} ATR ({round((d_sup or 0)*atr,0) if atr else '?'}₹) below. ATR (daily range) = ₹{atr}.",
        'BREAKOUT_DN':   f"Price BROKE BELOW the 20-day low on {vol_r_str}. {vol_txt}Selling pressure is visible because price lost the recent low and volume confirmed the move. Nearest ceiling resistance ₹{ceil_p} is {d_res} ATR overhead.",
        'AT_SUPPORT':    f"Price has pulled back to a known support zone at ₹{floor_p}. {vol_txt}This is the price where buyers defended previously. Floor strength {round((fl_str or 0)*100)}% (backed by {fl_n} independent methods: {fl_src or '—'}). If it holds again, risk is clearly defined: stop below ₹{floor_p}.",
        'AT_RESISTANCE': f"Price is pressing into resistance at ₹{ceil_p}. {vol_txt}This is where sellers overpowered buyers before. Ceiling strength {round((cl_str or 0)*100)}% (backed by {cl_n} methods: {cl_src or '—'}). A breakout above here on volume = bullish; a rejection = fade.",
        'NEAR':          f"Price is near a key level (floor ₹{floor_p}, ceiling ₹{ceil_p}). {vol_txt}Watching for a breakout or rejection. ATR = ₹{atr}.",
    }.get(signal, f"{signal}. Floor ₹{floor_p}, ceiling ₹{ceil_p}. ATR ₹{atr}. {vol_txt}")

    reasons.append({
        'icon': '📊',
        'layman': sig_explain,
        'formula': f"Signal = {signal} → SR component = {sig_comp:+.2f}. Floor ₹{floor_p} ({d_sup} ATR away) · Ceiling ₹{ceil_p} ({d_res} ATR away). ATR14 = ₹{atr}.",
    })

    # ── 4. Confluence ─────────────────────────────────────────────────────────
    reasons.append({
        'icon': '🔬',
        'layman': (
            f"Support at ₹{floor_p} confirmed by {fl_n} independent methods ({fl_src or '—'}), strength {round((fl_str or 0)*100)}%. "
            f"Resistance at ₹{ceil_p} confirmed by {cl_n} methods ({cl_src or '—'}), strength {round((cl_str or 0)*100)}%. "
            f"When 3+ unrelated methods point to the same price, it is a multi-method price cluster — stronger than a single indicator."
        ),
        'formula': f"Strength = 0.40×VolumeProfile + 0.25×touches/4 + 0.20×rejection/2 + 0.15×(AVWAP or round). Confluence component = {conf_comp:+.2f}.",
    })

    # ── 5. VWAP ───────────────────────────────────────────────────────────────
    gap_pct = round((close - vwap) / vwap * 100, 1) if vwap and close else None
    if vwap:
        vwap_msg = (
            f"Price ₹{close} is {'ABOVE' if above_v else 'BELOW'} the 20-day VWAP ₹{vwap} "
            f"({'+'if gap_pct and gap_pct>=0 else ''}{gap_pct}%). "
            f"VWAP = volume-weighted average price — the average at which actual trades happened. "
            f"{'Above = every buyer over the last 20 sessions is sitting on a profit; no forced selling.' if above_v else 'Below = most recent buyers are at a loss; sellers have the psychological edge.'}"
        )
        reasons.append({'icon': '📈', 'layman': vwap_msg,
                        'formula': 'VWAP20 = Σ(TypicalPrice×Volume)/ΣVolume over 20 sessions. Above VWAP = cost-basis support for recent buyers.'})

    # ── 6. Confirmed breakout ─────────────────────────────────────────────────
    if bo_conf:
        reasons.append({
            'icon': '🚀',
            'layman': (
                f"Breakout confirmed by BOTH price AND volume filters: price exceeded the 20-day Donchian channel "
                f"by more than 0.25 ATR (buffer against false breaks) AND volume was >{1.5:.1f}× the 20-day median. "
                f"Both must be true simultaneously — volume alone without price or price without volume = filtered out as noise."
            ),
            'formula': 'BO = Close > D20_high + 0.25×ATR14 AND Vol > 1.5×Median(Vol,20d). Buffer eliminates single-candle fake-outs.',
        })

    # ── 7. Bear trap / Reclaim ────────────────────────────────────────────────
    if reclaim:
        reasons.append({
            'icon': '🔄',
            'layman': (
                f"Bear trap pattern detected: price dipped below the floor ₹{floor_p} (trapping short sellers) "
                f"then bounced back above it within 5 sessions. "
                f"Short sellers who shorted the breakdown are now underwater and forced to buy to cover — "
                f"this fuel often accelerates the recovery. Verify: the reclaim must close above floor, not just touch."
            ),
            'formula': f"Reclaim: any of last 5 closes < floor − 0.25×ATR AND today close > floor + 0.25×ATR. Floor = ₹{floor_p}.",
        })

    # ── 8. RSI14 ─────────────────────────────────────────────────────────────
    if rsi_val is not None:
        if rsi_val > 82:
            rsi_msg = f"RSI = {rsi_val:.0f} — EXTREME overbought. BUY signal downgraded to WATCH_BUY automatically. The stock has run very hard very fast; chasing here historically leads to getting caught in a pullback."
        elif rsi_val > 70:
            rsi_msg = f"RSI = {rsi_val:.0f} — entering overbought territory (>70). Momentum is strong but risk of a short-term pullback is elevated. Not a sell signal on its own, but size conservatively."
        elif rsi_val < 25:
            rsi_msg = f"RSI = {rsi_val:.0f} — deeply oversold (<25). Selling pressure is typically exhausted at this level; bounces are statistically likely. Not a trend reversal signal alone — wait for price confirmation."
        elif rsi_val < 30:
            rsi_msg = f"RSI = {rsi_val:.0f} — oversold (<30). Buyers could step in here. Best used alongside a support level test for a higher-probability entry."
        else:
            rsi_msg = f"RSI = {rsi_val:.0f} — healthy momentum zone (30–70), not overbought or oversold. There is room for the move to continue without immediate mean-reversion risk."
        reasons.append({'icon': '🔢', 'layman': rsi_msg,
                        'formula': 'RSI14 = 100 − 100/(1 + avg_14d_gain/avg_14d_loss) using Wilder EWM. >70 overbought, <30 oversold; >82 hard-caps BUY → WATCH_BUY.'})

    # ── 9. EMA trend ─────────────────────────────────────────────────────────
    if ema_t:
        e50_dist = round((close - ema50) / ema50 * 100, 1) if ema50 and close else '?'
        if ema_t == 'UP':
            ema_msg = (
                f"EMA golden alignment — short-term EMA10 ₹{ema10} > medium EMA20 ₹{ema20} > long EMA50 ₹{ema50}. "
                f"Price ₹{close} is {'+' if isinstance(e50_dist,float) and e50_dist>=0 else ''}{e50_dist}% vs the 50-day trend line. "
                f"Buyers at the 50-day EMA are in profit — this acts as a natural support floor. "
                f"Every dip to the EMA cluster is a potential buy opportunity while this alignment holds."
            )
        elif ema_t == 'DOWN':
            ema_msg = (
                f"EMA death alignment — EMA10 ₹{ema10} < EMA20 ₹{ema20} < EMA50 ₹{ema50}. "
                f"Price ₹{close} is {'+' if isinstance(e50_dist,float) and e50_dist>=0 else ''}{e50_dist}% vs the 50-day. "
                f"Short-term sellers are in control. Every rally into the EMA cluster typically meets selling pressure. "
                f"Do not buy against a death-aligned EMA stack without a very clear catalyst."
            )
        else:
            ema_msg = (
                f"EMAs are mixed (MIXED alignment): EMA10 ₹{ema10}, EMA20 ₹{ema20}, EMA50 ₹{ema50}. "
                f"Price ₹{close} is {'above' if above50 else 'below'} the 50-day. "
                f"No clear trend — the stock is in a transitional phase. Wait for alignment before committing."
            )
        reasons.append({'icon': '📉', 'layman': ema_msg,
                        'formula': 'EMA_n = α×close + (1-α)×prev_EMA, α=2/(n+1). UP: EMA10>EMA20>EMA50. DOWN: reverse. MIXED: otherwise.'})

    # ── 10. Supertrend ────────────────────────────────────────────────────────
    if st_dir is not None:
        bull = st_dir == 1
        st_msg = (
            f"Supertrend (10-period, 3×ATR) is {'BULLISH 🟢' if bull else 'BEARISH 🔴'} — "
            f"trailing {'support' if bull else 'resistance'} line at ₹{st_val}. "
            f"{'Price has stayed above this line — the uptrend is mechanically intact. Many trend systems treat this as a trailing support line; as long as it holds, sellers are contained.' if bull else 'Price is below this line — the downtrend is intact. Every bounce will likely be sold at or below the Supertrend line ₹'+str(st_val)+'. A close above it = potential trend flip.'} "
            f"ATR used = ₹{atr} (average daily price range, Wilder-smoothed)."
        )
        reasons.append({'icon': '🌊', 'layman': st_msg,
                        'formula': f"Supertrend = (H+L)/2 ± 3×ATR(10,Wilder). Flips {'bull when close > upper band' if bull else 'bear when close < lower band'}."})

    # ── 11. Ichimoku cloud ────────────────────────────────────────────────────
    if ichi:
        c_top   = ichi.get('cloud_top')
        c_bot   = ichi.get('cloud_bottom')
        cpos    = 'ABOVE' if ichi.get('above_cloud') else 'BELOW' if ichi.get('below_cloud') else 'INSIDE'
        cbull   = ichi.get('bullish_cloud')
        tk_ab   = ichi.get('tenkan_above_kijun')
        ch_ab   = ichi.get('chikou_above')
        cloud_note = (
            'Price above cloud = medium and long-term buyers in full control. Cloud acts as dynamic support.' if cpos == 'ABOVE' else
            'Price below cloud = sellers dominating medium and long-term. Cloud acts as resistance overhead.' if cpos == 'BELOW' else
            'Price inside the cloud = no clear bias; wait for a breakout above or below.'
        )
        ichi_msg = (
            f"Ichimoku cloud: price is {cpos} the cloud (₹{c_bot}–₹{c_top}). {cloud_note} "
            f"Cloud color: {'BULLISH (green = Senkou A above B, upward momentum)' if cbull else 'BEARISH (red = Senkou B above A, downward momentum)'}. "
            f"Tenkan (9-day midpoint) {'above' if tk_ab else 'below'} Kijun (26-day): {'bullish short-term crossover' if tk_ab else 'bearish — short-term weaker than medium-term'}. "
            f"Chikou (today's close plotted 26 days back): {'above' if ch_ab else 'below'} past prices — {'confirms upward bias' if ch_ab else 'confirms downward bias'}. "
            f"Zero lookahead used (cloud built from data available at the time)."
        )
        reasons.append({'icon': '☁️', 'layman': ichi_msg,
                        'formula': f"Senkou A=(Tenkan+Kijun)/2 shifted +26. Senkou B=(52H+52L)/2 shifted +26. Today's cloud = values from 26 bars ago. Cloud top={c_top}, bottom={c_bot}."})

    # ── 12. Bollinger Bands ───────────────────────────────────────────────────
    if bb_pctb is not None:
        if bb_pctb > 1.0:
            bb_msg = f"Bollinger %B = {bb_pctb:.0%} — price is ABOVE the upper band (₹{bb_up}), which is 2 standard deviations above the 20-day average (₹{bb_mid}). In strong trending moves price can walk the upper band; it signals momentum but risk of snap-back is elevated. Lower band ₹{bb_lo}."
        elif bb_pctb > 0.8:
            bb_msg = f"Bollinger %B = {bb_pctb:.0%} — price near the upper band (₹{bb_up}). Overbought short-term; in a strong trend this is normal but chasing at this level risks catching a pullback to the midline ₹{bb_mid}."
        elif bb_pctb < 0.0:
            bb_msg = f"Bollinger %B = {bb_pctb:.0%} — price BELOW the lower band (₹{bb_lo}). Statistically extreme — happens only ~5% of the time. Oversold bounce likely but not guaranteed. Wait for a close back inside the band before acting. Mid ₹{bb_mid}."
        elif bb_pctb < 0.2:
            bb_msg = f"Bollinger %B = {bb_pctb:.0%} — price near the lower band (₹{bb_lo}), oversold zone. Mean-reversion candidates: if support holds here, target is the midline ₹{bb_mid} (+{round((bb_mid/bb_lo-1)*100,1) if bb_mid and bb_lo else '?'}%). Upper ₹{bb_up}."
        else:
            bb_msg = f"Bollinger %B = {bb_pctb:.0%} — price in the neutral mid-band range between ₹{bb_lo} and ₹{bb_up} (mid ₹{bb_mid}). No extreme squeeze or expansion signal. Wait for a move toward either band for a cleaner entry."
        reasons.append({'icon': '🎯', 'layman': bb_msg,
                        'formula': 'BB(20,2σ): mid=SMA20, upper=mid+2σ, lower=mid−2σ. %B=(close−lower)/(upper−lower). >1.0=above upper, <0.0=below lower.'})

    # ── 13. JEV AI confidence gate ───────────────────────────────────────────
    if jconf is not None:
        gate_state = 'GREEN ✅ (high confidence)' if jconf >= 0.7 else 'RED ⚠️ — signal downgraded' if jconf < 0.45 else 'AMBER (moderate)'
        sq_txt  = f"{jsq+1:.1f}/5" if isinstance(jsq,(int,float)) else 'n/a'
        ft_txt  = f"{jft+1:.1f}/5" if isinstance(jft,(int,float)) else 'n/a'
        rr_txt  = f"{jrr_j+1:.1f}/5" if isinstance(jrr_j,(int,float)) else 'n/a'
        reasons.append({
            'icon': '🔒',
            'layman': (
                f"TypeSafe AI (JEV) is {jconf:.0%} confident this setup is actionable — gate: {gate_state}. "
                f"Regime detected: {jreg}. Direction: {jdir}. "
                f"Three scored dimensions: setup quality {sq_txt} (how good is the technical alignment), "
                f"follow-through {ft_txt} (odds price moves in signal direction over 1–5 sessions), "
                f"risk/reward {rr_txt} (floor-to-ceiling vs stop distance). "
                f"{'Below 45% = BUY automatically downgraded to WATCH_BUY; above 70% = all layers agree, trade with normal sizing.' if jconf < 0.7 else 'At this confidence level all technical layers agree — trade with standard sizing per your plan.'}"
            ),
            'formula': (
                'JEV calibrated via RLCD (Reinforcement Learning from Calibrated Decisions). '
                'noul probability = P(signals clearly aligned and actionable). '
                f'Composite = 0.35×setup_quality/4 + 0.30×follow_through/4 + 0.35×risk_reward/4 = {jev_comp:.3f}.'
            ),
        })

    # SAM score sorted to front
    reasons.sort(key=lambda r: 0 if r.get('icon') == '⭐' else 1)
    return reasons


def indicator_snapshot(sr, jev_row=None):
    """Compact raw indicator snapshot for the website audit strip."""
    rsi = sr.get('rsi14')
    bbp = sr.get('bb_pct_b')
    st_dir = sr.get('supertrend_dir')
    ichi = sr.get('ichimoku') or {}
    return {
        'rsi14':            rsi,
        'rsi_state':        'HOT>82' if rsi and rsi > 82 else 'overbought>70' if rsi and rsi > 70 else 'oversold<30' if rsi and rsi < 30 else 'neutral',
        'ema_trend':        sr.get('ema_trend'),
        'ema10':            sr.get('ema10'),
        'ema20':            sr.get('ema20'),
        'ema50':            sr.get('ema50'),
        'above_ema50':      sr.get('above_ema50'),
        'bb_pct_b':         bbp,
        'bb_state':         'upper/hot' if bbp is not None and bbp > 0.80 else 'lower/cold' if bbp is not None and bbp < 0.20 else 'middle',
        'bb_upper':         sr.get('bb_upper'),
        'bb_mid':           sr.get('bb_mid'),
        'bb_lower':         sr.get('bb_lower'),
        'supertrend':       sr.get('supertrend'),
        'supertrend_dir':   st_dir,
        'supertrend_state': 'BULL' if st_dir == 1 else 'BEAR' if st_dir == -1 else 'N/A',
        'ichimoku_pos':     'ABOVE' if ichi.get('above_cloud') else 'BELOW' if ichi.get('below_cloud') else 'INSIDE',
        'ichimoku_cloud':   'BULL' if ichi.get('bullish_cloud') else 'BEAR',
        'tenkan_above_kijun': ichi.get('tenkan_above_kijun'),
        'chikou_above':     ichi.get('chikou_above'),
        'vol_ratio':        sr.get('vol_ratio'),
        'jev_confidence':   (jev_row or {}).get('confidence_gate'),
        'jev_regime':       (jev_row or {}).get('regime_jev'),
        'jev_direction':    (jev_row or {}).get('direction_jev'),
    }



def action_language(action, sr, mr, jev_row=None):
    """Plain-English action + trigger plan. Facts only; no institution claims."""
    ind     = indicator_snapshot(sr, jev_row)
    close   = sr.get('close')
    signal  = sr.get('signal', 'NEUTRAL')
    floor_p = sr.get('floor')
    ceil_p  = sr.get('ceiling')
    nxt     = sr.get('next_target') or ceil_p
    nxt_floor = sr.get('next_floor') or floor_p
    stop, target1, rr1 = risk_reward(sr)
    vol_r  = ind.get('vol_ratio')
    rsi    = ind.get('rsi14')
    ema_t  = ind.get('ema_trend')
    st     = ind.get('supertrend_state')
    ichi   = ind.get('ichimoku_pos')
    bbp    = ind.get('bb_pct_b')
    jconf  = ind.get('jev_confidence')
    regime = (mr or {}).get('current', {}).get('label', '?')

    vol_txt = f"{vol_r:.2f}× 20-day average volume" if isinstance(vol_r,(int,float)) else "unknown volume vs 20-day average"
    vol_ok = isinstance(vol_r,(int,float)) and vol_r >= 1.5
    buy_trend = (regime == 'UP') or (ema_t == 'UP' and st == 'BULL')
    sell_trend = (regime == 'DOWN') and (ema_t == 'DOWN' or st == 'BEAR')
    mixed_bullish = (ema_t != 'DOWN') and (st == 'BULL' or ichi == 'ABOVE')
    low_jev = isinstance(jconf,(int,float)) and jconf < 0.45
    high_jev = isinstance(jconf,(int,float)) and jconf >= 0.70

    def nums():
        parts = [f"close ₹{close}"]
        if isinstance(vol_r,(int,float)): parts.append(f"volume {vol_txt}")
        if rsi is not None: parts.append(f"RSI {rsi:.0f}")
        parts.append(f"EMA {ema_t or 'n/a'}")
        parts.append(f"Supertrend {st or 'n/a'}")
        parts.append(f"Ichimoku {ichi or 'n/a'}")
        if bbp is not None: parts.append(f"Bollinger {bbp:.0%}")
        if isinstance(jconf,(int,float)): parts.append(f"JEV confidence {jconf:.0%}")
        return "; ".join(parts)

    # ── Clean BUY ────────────────────────────────────────────────────────────
    if action == 'BUY':
        if signal == 'BREAKOUT_UP':
            plain = (
                f"BUY — buying pressure is visible because price closed above its recent high and volume is {vol_txt}; "
                f"trend signals are aligned upward."
            )
        elif signal == 'AT_SUPPORT':
            plain = (
                f"BUY — buyers defended support near ₹{floor_p}; price is holding above that floor and trend signals are supportive."
            )
        else:
            plain = f"BUY — buyers have the advantage because trend and support signals are aligned."
        plan = (
            f"Entry around ₹{close}; first target ₹{target1}; next target ₹{nxt}; stop/invalid below ₹{stop}. "
            f"Facts: {nums()}."
        )
        return plain, plan

    # ── WATCH BUY / setup forming ────────────────────────────────────────────
    if action == 'WATCH_BUY' or (action == 'WATCH'):
        if signal == 'AT_SUPPORT':
            plain = (
                f"WATCH TO BUY — setup is forming because price is near support ₹{floor_p}, but buyers still need confirmation."
            )
        elif signal == 'AT_RESISTANCE':
            plain = (
                f"WATCH TO BUY — price is testing resistance ₹{ceil_p}; buy only after a clean close above it with stronger volume."
            )
        else:
            plain = f"WATCH TO BUY — buyers are improving, but the setup is not confirmed yet."
        plan = (
            f"Trigger: close above ₹{ceil_p} on >1.5× 20-day average volume → target ₹{nxt}. "
            f"Fail/avoid: close below ₹{floor_p} or stop ₹{stop}. Facts: {nums()}."
        )
        return plain, plan

    # ── CAUTION at resistance / mixed internals ──────────────────────────────
    if action == 'CAUTION' and signal == 'AT_RESISTANCE':
        plain = (
            f"BE CAUTIOUS — price is stuck just under strong resistance ₹{ceil_p}; buyers have not confirmed a breakout yet."
        )
        if regime == 'DOWN':
            plain += " Long-term trend is still down, so chasing here is risky."
        if low_jev:
            plain += f" AI confidence is low at {jconf:.0%}, so the signal is not clean."
        plan = (
            f"Buy trigger: close above ₹{ceil_p} on >1.5× 20-day average volume → target ₹{nxt}. "
            f"Seller confirmation: rejection from ₹{ceil_p} or close below floor ₹{floor_p} → downside risk toward ₹{nxt_floor}. "
            f"Facts: {nums()}."
        )
        return plain, plan

    # ── Clean AVOID / seller control ─────────────────────────────────────────
    if action == 'AVOID' or (action == 'CAUTION' and signal == 'BREAKOUT_DN'):
        if signal == 'BREAKOUT_DN':
            plain = (
                f"AVOID — selling pressure is visible because price broke below its recent low on {vol_txt}."
            )
        elif signal == 'AT_RESISTANCE':
            plain = (
                f"AVOID — price is failing at resistance ₹{ceil_p} and the bigger trend is weak."
            )
        else:
            plain = f"AVOID — sellers have the advantage because trend and price signals are weak."
        plan = (
            f"Do not buy until price closes back above ₹{ceil_p} with >1.5× volume. "
            f"If price loses ₹{floor_p}, next downside level is ₹{nxt_floor}. Facts: {nums()}."
        )
        return plain, plan

    # ── NEUTRAL / no edge ────────────────────────────────────────────────────
    if signal == 'AT_RESISTANCE':
        plain = f"WAIT — price is under resistance ₹{ceil_p}; buyers must prove strength before this becomes a buy."
        plan = f"Buy trigger: close above ₹{ceil_p} on >1.5× volume → target ₹{nxt}. Rejection/downside trigger: close below ₹{floor_p} → risk toward ₹{nxt_floor}. Facts: {nums()}."
    elif signal == 'AT_SUPPORT':
        plain = f"SETUP FORMING — price is near support ₹{floor_p}; wait to see if buyers defend it."
        plan = f"Buy trigger: bounce/close above ₹{ceil_p} with >1.5× volume → target ₹{nxt}. Fail trigger: close below ₹{floor_p} → risk toward ₹{nxt_floor}. Facts: {nums()}."
    else:
        plain = "NO CLEAR EDGE — buyers and sellers are not giving a clean signal yet."
        plan = f"Wait between floor ₹{floor_p} and resistance ₹{ceil_p}; breakout above ₹{ceil_p} targets ₹{nxt}, breakdown below ₹{floor_p} risks ₹{nxt_floor}. Facts: {nums()}."
    return plain, plan


def plain_english(action, sr, mr, jev_row=None):
    return action_language(action, sr, mr, jev_row)[0]


def trigger_plan(action, sr, mr, jev_row=None):
    return action_language(action, sr, mr, jev_row)[1]


def key_reason(action, sam, sr, mr, jev_row=None):
    """Keep this factual; plain action sentence is separate and shown first."""
    plain, plan = action_language(action, sr, mr, jev_row)
    return plan

def main():
    sr_data  = json.loads((OUT / 'sr_levels.json').read_text())
    jev_data = json.loads((OUT / 'jev_rank.json').read_text())
    mr_data  = json.loads((OUT / 'monthly_regimes.json').read_text())

    # ── Freshness guard: never silently blend stale JEV/regime into a
    # today-dated output. If the JEV or monthly-regime steps were skipped
    # (no TYPESAFE_API_KEY) or failed (continue-on-error), their as_of
    # falls behind the fresh S&R date. Flag it loudly so the UI can warn
    # and the workflow can refuse to republish a degraded landing tab.
    sr_as_of     = sr_data.get('as_of', date.today().isoformat())
    jev_as_of    = jev_data.get('as_of', '')
    regime_as_of = mr_data.get('as_of', '')
    def _ym(s):
        try:
            p = s.split('-'); return int(p[0]) * 12 + int(p[1])
        except Exception:
            return 0
    jev_fresh    = bool(jev_as_of) and jev_as_of == sr_as_of
    # monthly regime lags by design (excludes current incomplete month);
    # fresh if within 2 months of the S&R date.
    regime_behind = _ym(sr_as_of[:7]) - _ym(regime_as_of[:7]) if regime_as_of else 99
    regime_fresh  = 0 <= regime_behind <= 2
    stale = (not jev_fresh) or (not regime_fresh)
    stale_reasons = []
    if not jev_fresh:
        stale_reasons.append(f"JEV data is {jev_as_of or 'missing'} but S&R is {sr_as_of} — JEV layer did not refresh (check TYPESAFE_API_KEY).")
    if not regime_fresh:
        stale_reasons.append(f"Monthly regime data is {regime_as_of or 'missing'} ({regime_behind} months behind) — regime layer did not refresh.")

    sr_by_sym  = {s['symbol']: s for s in sr_data.get('stocks', []) if 'error' not in s}
    jev_by_sym = {r['symbol']: r for r in jev_data.get('ranking', [])}
    mr_by_sym  = {s['symbol']: s for s in mr_data.get('stocks', []) if not s.get('recently_listed') and 'error' not in s}

    picks = []
    for sym, sr in sr_by_sym.items():
        mr      = mr_by_sym.get(sym)
        jev_row = jev_by_sym.get(sym)

        reg_comp, reg_label = regime_component(mr)
        sig_comp  = SIG_SCORE.get(sr.get('signal', 'NEUTRAL'), 0.0)
        jev_comp  = float((jev_row or {}).get('composite') or 0.0)
        conf_comp_val = confluence_comp(sr, sig_comp)
        # JEV measures setup QUALITY not direction; multiply by direction sign so a
        # high-quality bearish setup (BREAKOUT_DN, DOWN regime) reduces SAM,
        # not inflates it toward BUY.
        direction = reg_comp + sig_comp
        dir_sign  = 1 if direction > 0 else (-1 if direction < 0 else 0)
        jev_directional = jev_comp * dir_sign
        sam = round(
            0.30 * reg_comp +
            0.25 * sig_comp +
            0.25 * jev_directional +
            0.20 * conf_comp_val,
            4
        )

        action  = classify(sam, sr, mr, jev_row=jev_row)
        stop, target1, rr1 = risk_reward(sr)
        why     = build_why(sr, mr, jev_row, reg_comp, sig_comp, conf_comp_val, sam, jev_comp=jev_comp, dir_sign=dir_sign)
        ind     = indicator_snapshot(sr, jev_row)
        key     = key_reason(action, sam, sr, mr, jev_row)
        plain   = plain_english(action, sr, mr, jev_row)
        plan    = trigger_plan(action, sr, mr, jev_row)

        picks.append({
            'symbol':        sym,
            'name':          sr.get('name', ''),
            'action':        action,
            'action_label':  ACTION_LABELS[action],
            'sam_score':     sam,
            'sam_score_100': round(sam * 100, 1),
            'close':         sr.get('close'),
            'stop':          stop,
            'target1':       target1,
            'target2':       sr.get('next_target'),
            'rr':            rr1,
            'signal':        sr.get('signal'),
            'regime':        reg_label,
            'regime_age':    (mr or {}).get('current', {}).get('age_months'),
            'rev_risk':      (mr or {}).get('reversal_risk_ratio'),
            'floor':         sr.get('floor'),
            'floor_strength': sr.get('floor_strength'),
            'ceiling':       sr.get('ceiling'),
            'ceiling_strength': sr.get('ceiling_strength'),
            'atr14':         sr.get('atr14'),
            'vol_ratio':     sr.get('vol_ratio'),
            'above_vwap':    sr.get('above_vwap'),
            'breakout_confirmed': sr.get('breakout_confirmed'),
            'reclaim_support': sr.get('reclaim_support'),
            'jev_composite': jev_comp,
            'jev_setup':     (jev_row or {}).get('setup_quality'),
            'jev_follow':    (jev_row or {}).get('follow_through'),
            'jev_rr':        (jev_row or {}).get('risk_reward'),
            'plain':         plain,
            'key_reason':    key,
            'setup_plan':    plan,
            'indicators':    ind,
            'why':           why,
        })

    # Sort: BUY desc SAM, then AVOID asc SAM, rest by |SAM|
    order = ['BUY','WATCH_BUY','WATCH','CAUTION','NEUTRAL','AVOID']
    picks.sort(key=lambda x: (order.index(x['action']) if x['action'] in order else 5, -abs(x['sam_score'])))

    from collections import Counter
    summary = dict(Counter(p['action'] for p in picks))

    output = {
        'as_of':     sr_as_of,
        'universe':  len(sr_by_sym),
        'summary':   summary,
        'formula':   'SAM = 0.30×regime + 0.25×sr_signal + 0.25×(jev_quality×direction_sign) + 0.20×confluence_strength',
        'data_freshness': {
            'sr_as_of': sr_as_of, 'jev_as_of': jev_as_of, 'regime_as_of': regime_as_of,
            'jev_fresh': jev_fresh, 'regime_fresh': regime_fresh,
        },
        'stale': stale,
        'stale_reasons': stale_reasons,
        'picks':     picks,
    }
    (OUT / 'sam_picks.json').write_text(json.dumps(output, indent=1), encoding='utf-8')
    JS_OUT.parent.mkdir(parents=True, exist_ok=True)
    JS_OUT.write_text('// generated by sam_picks.py\nwindow.SAM_PICKS = ' + json.dumps(output) + ';\n', encoding='utf-8')

    print(f"Summary: {summary}")
    print(f"Freshness: sr={sr_as_of} jev={jev_as_of}({'fresh' if jev_fresh else 'STALE'}) regime={regime_as_of}({'fresh' if regime_fresh else 'STALE'})")
    if stale:
        print("⚠️  STALE: " + " | ".join(stale_reasons))
    print(f"Saved: sam_picks.json + sam_picks.js ({len(picks)} stocks)")
    buys = [p for p in picks if p['action'] == 'BUY'][:5]
    for b in buys:
        print(f"  BUY {b['symbol']} ₹{b['close']} → target ₹{b['target1']} stop ₹{b['stop']} R:R {b['rr']}× SAM {b['sam_score_100']}")


if __name__ == '__main__':
    main()
