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
    """Bullet-point math reasons — both layman and formula."""
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
    plain   = sr.get('plain_signal', '')
    vwap    = sr.get('vwap20')
    above_v = sr.get('above_vwap')
    reclaim = sr.get('reclaim_support', False)
    bo_conf = sr.get('breakout_confirmed', False)
    conf    = sr.get('confluence') or {}
    fl_cl   = conf.get('floor') or {}
    cl_cl   = conf.get('ceiling') or {}
    fl_src  = ', '.join(fl_cl.get('sources') or [])
    cl_src  = ', '.join(cl_cl.get('sources') or [])

    # Monthly regime
    if label and label != 'N/A':
        stretched = rr_rat and rr_rat > 1.5
        reasons.append({
            'icon': '📅',
            'layman': f"Monthly trend is {label} for {age} months (avg 12m return {avg12}%{', STRETCHED — could be near end' if stretched else ''})",
            'formula': f"Trailing 12m return > +5% = UP. Reversal risk = {rr_rat}× (age ÷ hist mean). Component = {reg_comp:+.2f}",
        })
    # Daily S&R signal
    reasons.append({
        'icon': '📊',
        'layman': plain or signal,
        'formula': f"Signal = {signal} → SR score = {sig_comp:+.2f}. Floor ₹{floor_p} ({round(sr.get('dist_support_atr') or 0,2)} ATR away) · Ceiling ₹{ceil_p} ({round(sr.get('dist_resistance_atr') or 0,2)} ATR away). ATR14 = ₹{atr}.",
    })
    # Confluence
    fl_n = fl_cl.get('n_sources', 0)
    cl_n = cl_cl.get('n_sources', 0)
    reasons.append({
        'icon': '🔬',
        'layman': f"Floor backed by {fl_n} independent methods ({fl_src or '—'}), strength {round((fl_str or 0)*100)}%. Ceiling backed by {cl_n} methods ({cl_src or '—'}), strength {round((cl_str or 0)*100)}%.",
        'formula': f"Strength(L)=0.40×VP_density+0.25×touches/4+0.20×rejection/2+0.15×(AVWAP/round). Floor str={fl_str} → conf_comp={conf_comp:+.2f}.",
    })
    # VWAP position
    reasons.append({
        'icon': '📈',
        'layman': f"Price ₹{close} is {'ABOVE' if above_v else 'BELOW'} 20-day VWAP ₹{vwap} — {'premium, buyers in control' if above_v else 'discount, sellers in control'}.",
        'formula': f"VWAP20 = Σ(TypicalPrice×Volume)/ΣVolume over 20 sessions. Above VWAP = institutional cost basis support.",
    })
    # Breakout confirmation
    if bo_conf:
        reasons.append({
            'icon': '🚀',
            'layman': f"Breakout is CONFIRMED: price broke the 20-day Donchian channel by >0.25 ATR with volume >1.5× the 20-day median. Real buyers/sellers stepped in.",
            'formula': f"BO = Close > D20_high + 0.25×ATR AND Vol > 1.5×Median(Vol20). Buffer avoids false Donchian crosses.",
        })
    if reclaim:
        reasons.append({
            'icon': '🔄',
            'layman': "Price previously broke below the floor and then bounced back above it. This is a 'bear trap' — sellers pushed it through but couldn't hold. Often marks a reversal.",
            'formula': f"Reclaim: any of last 5 closes < floor − 0.25×ATR AND today close > floor + 0.25×ATR.",
        })
    # JEV
    if jev_row:
        jc = jev_row.get('composite', 0)
        sq = jev_row.get('setup_quality', 0)
        ft = jev_row.get('follow_through', 0)
        rr_jev = jev_row.get('risk_reward', 0)
        reasons.append({
            'icon': '🤖',
            'layman': f"JEV AI model (TypeSafe System One) scored this setup {round(jc*100)}/100 based purely on the numbers. Setup quality {sq}/4, follow-through {ft}/4, risk/reward {rr_jev}/4.",
            'formula': f"JEV composite = 0.35×setup_quality/4 + 0.30×follow_through/4 + 0.35×risk_reward/4. JEV sees only numeric features — no names.",
        })
    # SAM SCORE
    reasons.append({
        'icon': '⭐',
        'layman': f"SAM SCORE = {round(sam*100)}/100. Combined score from monthly trend (30%) + daily signal (25%) + JEV setup quality (25%) + confluence strength (20%).",
        'formula': f"SAM = 0.30×({reg_comp:+.3f}) + 0.25×({sig_comp:+.3f}) + 0.25×(jev={jev_comp:.3f}×dir={dir_sign:+d}) + 0.20×({conf_comp:+.3f}) = {sam:+.3f}",
    })
    # ── RSI14 ─────────────────────────────────────────────────────────────────
    rsi_val  = sr.get('rsi14')
    if rsi_val is not None:
        rsi_state = 'overbought >82' if rsi_val>82 else 'overbought >70' if rsi_val>70 else 'oversold <25' if rsi_val<25 else 'oversold <30' if rsi_val<30 else 'neutral'
        reasons.append({'icon':'🔢','layman':f"RSI14 = {rsi_val:.0f} ({rsi_state}). {'Do not chase — overbought cap applied.' if rsi_val>82 else 'Potential bounce zone.' if rsi_val<25 else ''}",
                        'formula':'RSI14 = 100 − 100/(1 + avg_gain/avg_loss) over 14 sessions via Wilder EWM. >70 overbought, <30 oversold; >82 hard-caps BUY → WATCH_BUY.'})
    # ── EMA Trend ─────────────────────────────────────────────────────────────
    ema_trend = sr.get('ema_trend')
    if ema_trend:
        reasons.append({'icon':'📉','layman':f"EMA trend = {ema_trend}. Price {'ABOVE' if sr.get('above_ema50') else 'BELOW'} EMA50 ₹{sr.get('ema50','?')}. EMA10={sr.get('ema10','?')} / EMA20={sr.get('ema20','?')}.",
                        'formula':'EMA_n = Σ(close × α × (1−α)^k) where α=2/(n+1). Trend: UP=EMA10>EMA20>EMA50, DOWN=EMA10<EMA20<EMA50, else MIXED.'})
    # ── Bollinger Bands ───────────────────────────────────────────────────────
    bb_pctb = sr.get('bb_pct_b')
    if bb_pctb is not None:
        bb_pos = 'near upper band (overbought zone)' if bb_pctb>0.8 else 'near lower band (oversold zone)' if bb_pctb<0.2 else 'mid-band range'
        reasons.append({'icon':'📊','layman':f"Bollinger %B = {bb_pctb:.0%} ({bb_pos}). Upper ₹{sr.get('bb_upper','?')} / Mid ₹{sr.get('bb_mid','?')} / Lower ₹{sr.get('bb_lower','?')}.",
                        'formula':'BB(20,2σ): mid=SMA20, upper=mid+2σ, lower=mid−2σ. %B=(close−lower)/(upper−lower). <0.2=oversold zone, >0.8=overbought zone.'})
    # ── Supertrend ────────────────────────────────────────────────────────────
    st_dir = sr.get('supertrend_dir')
    if st_dir is not None:
        reasons.append({'icon':'🌊','layman':f"Supertrend(10,3) = {'BULLISH 🟢' if st_dir==1 else 'BEARISH 🔴'} at ₹{sr.get('supertrend','?')}. {'Price above Supertrend = uptrend bias.' if st_dir==1 else 'Price below Supertrend = downtrend bias.'}",
                        'formula':'Supertrend = (H+L)/2 ± 3×ATR(10, Wilder). Flips bullish when close > upper band; bearish when close < lower band.'})
    # ── Ichimoku Cloud (no-lookahead) ─────────────────────────────────────────
    ichi = sr.get('ichimoku') or {}
    if ichi:
        cpos = 'ABOVE cloud ✅' if ichi.get('above_cloud') else 'BELOW cloud ❌' if ichi.get('below_cloud') else 'INSIDE cloud ⚠️'
        reasons.append({'icon':'☁️','layman':f"Ichimoku: {cpos}. Cloud is {'BULLISH (green)' if ichi.get('bullish_cloud') else 'BEARISH (red)'}. Tenkan {'>' if ichi.get('tenkan_above_kijun') else '<'} Kijun. Chikou {'above' if ichi.get('chikou_above') else 'below'} past price.",
                        'formula':f"Senkou A={ichi.get('senkou_a')} / B={ichi.get('senkou_b')} (today's cloud = values from 26 bars ago, zero lookahead). Tenkan=9H/L mid, Kijun=26H/L mid."})
    # ── JEV confidence gate ───────────────────────────────────────────────────
    conf = (jev_row or {}).get('confidence_gate')
    if conf is not None:
        cstate = 'HIGH ✅' if conf>=0.7 else 'LOW ⚠️ — action downgraded' if conf<0.45 else 'MODERATE'
        reasons.append({'icon':'🔒','layman':f"JEV signal confidence = {conf:.0%} ({cstate}). Regime: {str((jev_row or {}).get('regime_jev') or '?').replace('_',' ')}. Direction: {str((jev_row or {}).get('direction_jev') or '?')}.",
                        'formula':'JEV noul question: do regime/EMA/Supertrend/Ichimoku/signal all agree? Calibrated probability via RLCD. <45% downgrades BUY→WATCH_BUY, AVOID→CAUTION.'})
    reasons.sort(key=lambda r: 0 if r.get('icon') == '⭐' else 1)
    return reasons


def indicator_snapshot(sr, jev_row=None):
    """Compact raw indicator snapshot for the website audit strip.
    All fields come from daily_sr.py / jev_rank.py JSON generated after close."""
    rsi = sr.get('rsi14')
    bbp = sr.get('bb_pct_b')
    st_dir = sr.get('supertrend_dir')
    ichi = sr.get('ichimoku') or {}
    return {
        'rsi14': rsi,
        'rsi_state': 'HOT>82' if rsi and rsi > 82 else 'overbought>70' if rsi and rsi > 70 else 'oversold<30' if rsi and rsi < 30 else 'neutral',
        'ema_trend': sr.get('ema_trend'),
        'ema10': sr.get('ema10'),
        'ema20': sr.get('ema20'),
        'ema50': sr.get('ema50'),
        'above_ema50': sr.get('above_ema50'),
        'bb_pct_b': bbp,
        'bb_state': 'upper/hot' if bbp is not None and bbp > 0.80 else 'lower/cold' if bbp is not None and bbp < 0.20 else 'middle',
        'bb_upper': sr.get('bb_upper'),
        'bb_mid': sr.get('bb_mid'),
        'bb_lower': sr.get('bb_lower'),
        'supertrend': sr.get('supertrend'),
        'supertrend_dir': st_dir,
        'supertrend_state': 'BULL' if st_dir == 1 else 'BEAR' if st_dir == -1 else 'N/A',
        'ichimoku_pos': 'ABOVE' if ichi.get('above_cloud') else 'BELOW' if ichi.get('below_cloud') else 'INSIDE',
        'ichimoku_cloud': 'BULL' if ichi.get('bullish_cloud') else 'BEAR',
        'tenkan_above_kijun': ichi.get('tenkan_above_kijun'),
        'chikou_above': ichi.get('chikou_above'),
        'jev_confidence': (jev_row or {}).get('confidence_gate'),
        'jev_regime': (jev_row or {}).get('regime_jev'),
        'jev_direction': (jev_row or {}).get('direction_jev'),
    }


def key_reason(action, sam, sr, mr, jev_row=None):
    """One-line verdict for the SAM PICKS table; raw details are in indicators/why."""
    ind = indicator_snapshot(sr, jev_row)
    rsi = ind.get('rsi14')
    rsi_txt = f"RSI {rsi:.0f} {ind['rsi_state']}" if isinstance(rsi, (int, float)) else "RSI n/a"
    bbp = ind.get('bb_pct_b')
    bb_txt = f"BB {bbp:.0%} {ind['bb_state']}" if isinstance(bbp, (int, float)) else "BB n/a"
    conf = ind.get('jev_confidence')
    conf_txt = f"JEV {conf:.0%}" if isinstance(conf, (int, float)) else "JEV n/a"
    regime = (mr or {}).get('current', {}).get('label', '?')
    return (
        f"{action}: SAM {sam*100:+.1f}; regime {regime}; {sr.get('signal','NEUTRAL')}; "
        f"{rsi_txt}; EMA {ind.get('ema_trend') or '?'}; ST {ind.get('supertrend_state')}; "
        f"Ichi {ind.get('ichimoku_pos')}; {bb_txt}; {conf_txt}"
    )


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
            'key_reason':    key,
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
