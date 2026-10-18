/* Pure dashboard calculations. No market-data mutations, orders or model calls. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.NiftyMath = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const finite = v => typeof v === 'number' && Number.isFinite(v);
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const day = value => {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
    const t = Date.parse(value + 'T00:00:00Z');
    return Number.isFinite(t) && new Date(t).toISOString().slice(0, 10) === value ? t : null;
  };
  const quantity = l => l.quantity === undefined ? 1 : l.quantity;
  const sign = l => l.side === 'BUY' ? 1 : -1;
  const validLeg = l => l && ['BUY', 'SELL'].includes(l.side) && ['CE', 'PE'].includes(l.option_type) &&
    finite(l.strike) && l.strike > 0 && finite(l.ref_close) && l.ref_close > 0 &&
    finite(l.lot) && l.lot > 0 && Number.isInteger(l.lot) &&
    finite(quantity(l)) && quantity(l) > 0 && Number.isInteger(quantity(l)) && day(l.expiry) !== null;

  function expiryRisk(legs, spot) {
    const invalid = {valid: false, maxProfit: null, maxLoss: null, breakevens: [],
      unlimitedProfit: false, unlimitedLoss: false, netDebit: null, riskReward: null, curve: {price: [], pnl: []}};
    if (!Array.isArray(legs) || !legs.length || !legs.every(validLeg) ||
        new Set(legs.map(l => l.expiry)).size !== 1 || new Set(legs.map(l => l.lot)).size !== 1) return invalid;
    const lot = legs[0].lot;
    const debit = legs.reduce((v, l) => v + sign(l) * quantity(l) * l.ref_close, 0);
    const value = s => lot * (legs.reduce((v, l) => v + sign(l) * quantity(l) *
      Math.max(l.option_type === 'CE' ? s - l.strike : l.strike - s, 0), 0) - debit);
    const knots = [...new Set([0, ...legs.map(l => l.strike)])].sort((a, b) => a - b);
    const values = knots.map(value);
    const slope = lot * legs.filter(l => l.option_type === 'CE').reduce((v, l) => v + sign(l) * quantity(l), 0);
    const unlimitedProfit = slope > 0, unlimitedLoss = slope < 0;
    // Index prices cannot fall below zero: short-put loss is finite, but unhedged.
    const tailRisk = legs.filter(l => l.option_type === 'PE')
      .reduce((v, l) => v + sign(l) * quantity(l), 0) < 0;
    const maxProfit = unlimitedProfit ? null : Math.max(...values);
    const maxLoss = unlimitedLoss ? null : Math.min(...values);
    const be = [];
    for (let i = 0; i < knots.length; i++) {
      if (Math.abs(values[i]) < 1e-7) be.push(knots[i]);
      else if (i && Math.abs(values[i - 1]) >= 1e-7 && values[i - 1] * values[i] < 0)
        be.push(knots[i - 1] - values[i - 1] * (knots[i] - knots[i - 1]) / (values[i] - values[i - 1]));
    }
    const last = knots.length - 1;
    if (slope && Math.abs(values[last]) >= 1e-7 && -values[last] / slope > 0) be.push(knots[last] - values[last] / slope);
    const centre = finite(spot) && spot > 0 ? spot : knots[Math.ceil(last / 2)];
    const lo = Math.max(0, Math.min(centre * .85, knots[1] * .97));
    const hi = Math.max(centre * 1.15, knots[last] * 1.03);
    const prices = [...new Set([...Array.from({length: 61}, (_, i) => lo + (hi - lo) * i / 60),
      ...knots.filter(x => x >= lo && x <= hi), ...be.filter(x => x >= lo && x <= hi)])].sort((a, b) => a - b);
    return {valid: true, maxProfit, maxLoss, breakevens: [...new Set(be)].sort((a, b) => a - b),
      unlimitedProfit, unlimitedLoss, tailRisk, netDebit: debit * lot,
      riskReward: finite(maxProfit) && maxProfit > 0 && finite(maxLoss) && maxLoss < 0 ? maxProfit / -maxLoss : null,
      curve: {price: prices, pnl: prices.map(value)}};
  }

  function positionGreeks(legs) {
    return Object.fromEntries(['delta', 'gamma', 'theta', 'vega'].map(k => [k,
      Array.isArray(legs) && legs.length && legs.every(l => validLeg(l) && finite(l[k]))
        ? legs.reduce((v, l) => v + sign(l) * quantity(l) * l.lot * l[k], 0) : null]));
  }

  function rankTradeSetups(data, options = {}) {
    const now = options.now instanceof Date ? options.now : new Date();
    const current = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    const asof = day(data.as_of);
    // Four calendar days is a conservative freshness guard, not an exchange holiday calendar.
    const stale = asof === null || !Number.isFinite(current) || current - asof > 4 * 86400000 || asof > current;
    const inputsStale = Array.isArray((data.inputs || {}).stale) && data.inputs.stale.length > 0;
    const rules = new Map((data.rules || []).map(r => [r.id, r]));
    const tierOrder = {top: 0, high: 1, medium: 2, low: 3, avoid: 4};
    const bucketOrder = {consider: 0, watch: 1, inactive: 2, avoid: 3};
    const result = (data.setups || []).map(setup => {
      const rule = rules.get(setup.rule) || {}, stats = rule.stats || {};
      const legs = setup.legs || [], risk = expiryRisk(legs, (data.index || {}).option_spot);
      const greeks = positionGreeks(legs), ex = setup.exit || {};
      const warnings = [], reasons = [];
      const exp = (data.expiries || []).find(e => legs.length && e.expiry === legs[0].expiry);
      const expiryDate = legs.length ? day(legs[0].expiry) : null;
      const daysToExpiry = expiryDate !== null && asof !== null ? (expiryDate - asof) / 86400000 : null;
      const iv = exp && finite(exp.atm_iv) && exp.atm_iv > 0 ? exp.atm_iv : null;
      const spot = (data.index || {}).option_spot;
      const sigmaMove = iv !== null && finite(spot) && spot > 0 && finite(daysToExpiry) && daysToExpiry > 0
        ? spot * iv / 100 * Math.sqrt(daysToExpiry / 365) : null;
      const jp = setup.jev_priority || {};
      const jevAvailable = (data.jev || {}).state === 'ok' && Object.hasOwn(tierOrder, jp.tier) &&
        finite(jp.confidence) && jp.confidence >= 0 && jp.confidence <= 1;
      const jev = {available: jevAvailable, tier: jevAvailable ? jp.tier : null, confidence: jevAvailable ? jp.confidence : null};
      const bounded = risk.valid && !risk.unlimitedLoss && !risk.tailRisk && finite(risk.maxLoss) && risk.maxLoss < 0;
      const evOnRisk = bounded && finite(ex.exp_pnl_per_lot) ? ex.exp_pnl_per_lot / -risk.maxLoss * 100 : null;
      const exitDate = day((setup.plan || {}).exit_by);
      const calendarDays = exitDate !== null && asof !== null ? (exitDate - asof) / 86400000 : null;
      const horizonOK = finite(ex.hold_sessions) && ex.hold_sessions === (data.method || {}).hold_sessions &&
        exitDate !== null && asof !== null && expiryDate !== null && exitDate > asof && exitDate <= expiryDate &&
        finite(ex.horizon_calendar_days) && ex.horizon_calendar_days === calendarDays &&
        finite(ex.remaining_dte) && ex.remaining_dte === daysToExpiry - calendarDays;
      // Producer forecasts one composite strategy lot, encoding ratios as repeated legs.
      // Quantity-coded legs cannot be matched safely to that forecast's units.
      const forecastUnitsOK = legs.every(l => quantity(l) === 1);
      const exitOK = finite(ex.exp_pnl_per_lot) && finite(ex.p_profit) && ex.p_profit >= 0 && ex.p_profit <= 100 &&
        finite(ex.round_trip_costs) && ex.round_trip_costs >= 0 && finite(ex.pnl_worst5) && horizonOK && forecastUnitsOK;
      const mathComponents = {exitProbability: null, expectedReturn: null, downside: null};
      let mathScore = null;
      if (risk.valid && bounded && exitOK) {
        mathComponents.exitProbability = .5 * ex.p_profit;
        mathComponents.expectedReturn = .3 * clamp(evOnRisk / 10 * 100, 0, 100);
        mathComponents.downside = .2 * clamp(100 * (1 - Math.max(0, -ex.pnl_worst5) / -risk.maxLoss), 0, 100);
        mathScore = Object.values(mathComponents).reduce((a, b) => a + b, 0);
      }
      const validated = setup.status === 'VALIDATED' && rule.status === 'VALIDATED' &&
        finite(stats.trades) && stats.trades >= 60 && finite(stats.t_stat) && stats.t_stat >= 2 &&
        finite(stats.mean_return_pct) && stats.mean_return_pct > 0 &&
        finite((stats.first_half || {}).mean_return_pct) && stats.first_half.mean_return_pct > 0 &&
        finite((stats.second_half || {}).mean_return_pct) && stats.second_half.mean_return_pct > 0;
      const complete = risk.valid && Object.values(greeks).every(finite) && sigmaMove !== null && exitOK;
      const expired = expiryDate === null || expiryDate <= current || exitDate === null || exitDate < current;
      if (stale) warnings.push('Snapshot is stale (over 4 calendar days), future-dated or missing a valid date. Refresh before considering a trade.');
      if (inputsStale) warnings.push('One or more upstream inputs are stale.');
      if (expired) warnings.push('Contract or planned exit is expired/unavailable.');
      if (!forecastUnitsOK) warnings.push('Quantity-coded legs do not match the producer forecast unit contract; ranking withheld.');
      if (!risk.valid) warnings.push('Incomplete legs, mixed expiries or invalid contract inputs: payoff is unavailable.');
      if (risk.unlimitedLoss) warnings.push('Unbounded upside loss: naked net short calls. Not a defined-risk buy candidate.');
      if (risk.tailRisk) warnings.push('Unhedged downside exposure: net short puts. Loss is finite at index zero but not protected by a lower wing; excluded from safe-buy ranking.');
      if (risk.valid && !bounded && !risk.unlimitedLoss && !risk.tailRisk) warnings.push('No positive finite loss budget: check quotes, costs and execution; apparent arbitrage is not trade-ready.');
      if (!complete) warnings.push('Missing or inconsistent Greeks, IV, exit horizon or cost-adjusted exit model.');
      if (!horizonOK) warnings.push('Exit model calendar-time metadata is missing or inconsistent with the planned exit. Legacy five-calendar-day forecasts cannot rank as five-session forecasts.');
      if (finite(ex.exp_pnl_per_lot) && ex.exp_pnl_per_lot <= 0) warnings.push('Expected P&L at the planned exit is non-positive after modelled costs.');
      if (!validated) warnings.push('Historical evidence does not meet the dashboard validation gate. More trades do not guarantee an edge.');
      if (!jevAvailable) warnings.push('Jev review unavailable; no AI score has been invented.');
      else if (jev.tier === 'avoid') warnings.push('Jev assessment is avoid; confidence measures that assessment, not profit probability.');
      if ((data.jev || {}).message) warnings.push('Jev provenance: ' + data.jev.message);
      if (setup.firing !== true) reasons.push('Trigger is not active in this snapshot.');
      else reasons.push('Rule trigger is active; that is not an entry recommendation.');
      reasons.push('Maths score = 50% exit P(profit) + 30% capped expected return on gross expiry risk + 20% 5th-percentile downside buffer. Heuristic, not a probability.');
      reasons.push('Rank by safety/evidence bucket, then maths score, then Jev tier and assessment confidence. Greeks explain sensitivity; their signs are not standalone alpha.');
      reasons.push('Expiry payoff bounds are gross, before fees, slippage and execution risk. Exit forecasts use a constant-volatility lognormal model, not a forecast of actual market returns.');
      const supported = jevAvailable && ['top', 'high'].includes(jev.tier);
      const hardBlock = stale || inputsStale || expired || !complete || !bounded ||
        (finite(ex.exp_pnl_per_lot) && ex.exp_pnl_per_lot <= 0) || setup.status === 'NO_EDGE' ||
        rule.status === 'NO_EDGE' || (jevAvailable && jev.tier === 'avoid');
      const eligible = !hardBlock && setup.firing === true && validated && supported;
      const bucket = hardBlock ? 'avoid' : eligible ? 'consider' : setup.firing === true ? 'watch' : 'inactive';
      return {setup, rule, bucket, eligible, mathScore, mathComponents, jev, risk, greeks, evOnRisk,
        sigmaMove, iv, daysToExpiry, warnings, reasons};
    });
    result.sort((a, b) => bucketOrder[a.bucket] - bucketOrder[b.bucket] ||
      (b.mathScore ?? -1) - (a.mathScore ?? -1) ||
      (tierOrder[a.jev.tier] ?? 5) - (tierOrder[b.jev.tier] ?? 5) ||
      (b.jev.confidence ?? -1) - (a.jev.confidence ?? -1) || String(a.setup.rule).localeCompare(String(b.setup.rule)));
    return result.map((r, i) => ({...r, rank: i + 1}));
  }
  function findBestDebitSpread(data, opts) {
    const maxLoss   = (opts && finite(opts.maxLoss))   ? opts.maxLoss   : 20000;
    const minProfit = (opts && finite(opts.minProfit)) ? opts.minProfit : 100000;
    const maxLots   = (opts && opts.maxLots)           ? opts.maxLots   : 8;
    const idx   = data.index || {};
    const spot  = idx.option_spot || idx.close;
    const lot   = idx.lot;
    if (!finite(spot) || spot <= 0 || !Number.isInteger(lot) || lot <= 0 ||
        !finite(maxLoss) || maxLoss <= 0 || !finite(minProfit) || minProfit <= 0 ||
        !Number.isInteger(maxLots) || maxLots < 1 || maxLots > 100) return [];
    const tradeExp = (data.expiries || []).find(e => e.trade_expiry);
    if (!tradeExp || !Array.isArray(tradeExp.rows)) return [];
    const now = opts && opts.now instanceof Date ? opts.now : new Date();
    const current = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    const asof = day(data.as_of), expiry = day(tradeExp.expiry);
    if (!finite(current) || asof === null || asof > current || current - asof > 4 * 86400000 ||
        expiry === null || expiry <= current || ((data.inputs || {}).stale || []).length) return [];
    const ceMap = {};
    tradeExp.rows.forEach(r => {
      if (r.ce && finite(r.ce.close) && r.ce.close > 0.5 && finite(r.strike) && r.strike > 0)
        ceMap[r.strike] = r.ce;
    });
    const strikes = Object.keys(ceMap).map(Number).sort((a, b) => a - b);
    const out = [];
    for (let i = 0; i < strikes.length; i++) {
      const Kb = strikes[i];
      if (Kb < spot * 0.99) continue;
      const Pb = ceMap[Kb].close;
      for (let j = i + 1; j < strikes.length; j++) {
        const Ks = strikes[j], Ps = ceMap[Ks].close;
        const deb = Pb - Ps;
        if (deb <= 0) continue;
        const w = Ks - Kb, mp1 = (w - deb) * lot, ml1 = deb * lot;
        if (mp1 <= 0) continue;
        for (let n = 1; n <= maxLots; n++) {
          const ml = ml1 * n, mp = mp1 * n;
          if (ml > maxLoss) break;
          if (mp >= minProfit) {
            const cb = ceMap[Kb], cs = ceMap[Ks];
            out.push({
              K_buy: Kb, K_sell: Ks, P_buy: Pb, P_sell: Ps, n_lots: n,
              net_debit: Math.round(deb * 100) / 100, width: w, lot,
              max_loss: Math.round(ml), max_profit: Math.round(mp),
              rr: mp / ml,
              breakeven: Kb + deb,
              breakeven_move_pct: (Kb + deb - spot) / spot * 100,
              delta_buy: finite(cb.delta) ? cb.delta : null, delta_sell: finite(cs.delta) ? cs.delta : null,
              theta_buy: finite(cb.theta) ? cb.theta : null, theta_sell: finite(cs.theta) ? cs.theta : null,
              theta_net: finite(cb.theta) && finite(cs.theta) ? (cb.theta - cs.theta) * lot * n : null,
              iv_buy: finite(cb.iv) ? cb.iv : null, iv_sell: finite(cs.iv) ? cs.iv : null,
              vrp: idx.vrp, atm_iv: idx.atm_iv, rv20: idx.rv20,
              as_of: data.as_of, expiry: tradeExp.expiry, dte: tradeExp.days_to_expiry,
            });
            break;
          }
        }
      }
    }
    out.sort((a, b) => b.rr - a.rr);
    return out.slice(0, 5);
  }
  function rankSpreadsByEV(data, opts) {
    const maxR = opts && Number.isInteger(opts.maxResults) && opts.maxResults > 0 ? opts.maxResults : 5;
    const maxL = opts && finite(opts.maxLoss) && opts.maxLoss > 0 ? opts.maxLoss : 100000;
    const idx   = data.index || {};
    const spot  = idx.option_spot || idx.close;
    const lot   = idx.lot;
    const rv20  = idx.rv20;
    if (!finite(spot) || spot <= 0 || !Number.isInteger(lot) || lot <= 0 || !finite(rv20) || rv20 <= 0) return [];
    const tradeExp = (data.expiries || []).find(e => e.trade_expiry);
    if (!tradeExp || !Array.isArray(tradeExp.rows)) return [];
    const dte = tradeExp.days_to_expiry;
    if (!finite(dte) || dte <= 0) return [];
    const T   = dte / 365;
    const now = opts && opts.now instanceof Date ? opts.now : new Date();
    const current = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    const asof = day(data.as_of), expDate = day(tradeExp.expiry);
    if (!finite(current) || asof === null || asof > current || current - asof > 4 * 86400000 ||
        expDate === null || expDate <= current || ((data.inputs || {}).stale || []).length) return [];
    const sig = rv20 / 100;
    function normCdf(x) {
      const t = 1 / (1 + 0.2316419 * Math.abs(x));
      const p = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
      const phi = Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
      return x >= 0 ? 1 - phi * p : phi * p;
    }
    function pAbove(K) {
      const d2 = (Math.log(spot / K) - 0.5 * sig * sig * T) / (sig * Math.sqrt(T));
      return normCdf(d2);
    }
    const ceMap = {};
    tradeExp.rows.forEach(r => {
      if (r.ce && finite(r.ce.close) && r.ce.close > 0.5 && finite(r.strike) && r.strike > 0)
        ceMap[r.strike] = r.ce;
    });
    const strikes = Object.keys(ceMap).map(Number).sort((a, b) => a - b);
    const out = [];
    for (let i = 0; i < strikes.length; i++) {
      const K1 = strikes[i];
      if (K1 < spot * 0.99) continue;
      const cb = ceMap[K1];
      for (let j = i + 1; j < strikes.length; j++) {
        const K2 = strikes[j], cs = ceMap[K2];
        const deb = cb.close - cs.close;
        if (deb <= 0) continue;
        const width = K2 - K1, mpUnit = width - deb;
        if (mpUnit <= 0) continue;
        const ml = Math.round(deb * lot);
        if (ml > maxL) continue;
        const mp = Math.round(mpUnit * lot), rr = mp / ml;
        const be = K1 + deb;
        const pA = pAbove(be), pM = pAbove(K2);
        const ev = Math.round(pM * mp + (pA - pM) * (mp * 0.5) - (1 - pA) * ml);
        out.push({
          K1, K2, P1: cb.close, P2: cs.close,
          net_debit: Math.round(deb * 100) / 100,
          width, lot, max_loss: ml, max_profit: mp, rr,
          breakeven: Math.round(be * 10) / 10,
          breakeven_pct: Math.round((be - spot) / spot * 1000) / 10,
          max_profit_pct: Math.round((K2 - spot) / spot * 1000) / 10,
          p_any_rv: Math.round(pA * 1000) / 10,
          p_max_rv: Math.round(pM * 1000) / 10,
          ev_per_lot: ev,
          theta_net: finite(cb.theta) && finite(cs.theta) ? Math.round((cb.theta - cs.theta) * lot * 10) / 10 : null,
          net_delta: finite(cb.delta) && finite(cs.delta) ? Math.round((cb.delta - cs.delta) * lot * 10) / 10 : null,
          delta_buy: finite(cb.delta) ? cb.delta : null,
          delta_sell: finite(cs.delta) ? cs.delta : null,
          vrp: idx.vrp, atm_iv: idx.atm_iv, rv20,
          as_of: data.as_of, expiry: tradeExp.expiry, dte,
        });
      }
    }
    out.sort((a, b) => b.ev_per_lot - a.ev_per_lot);
    return out.slice(0, maxR);
  }
  function buildHedgedMoveCard(data) {
    const xss=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const f2=v=>finite(v)?Number(v).toFixed(2):'\u2014';
    const idx=data.index||{};
    const spot=idx.option_spot||idx.close,lot=idx.lot;
    if(!finite(spot)||spot<=0||!Number.isInteger(lot)||lot<=0) return '';
    const tradeExp=(data.expiries||[]).find(e=>e.trade_expiry);
    if(!tradeExp||!Array.isArray(tradeExp.rows)) return '';
    const ceMap={},peMap={};
    tradeExp.rows.forEach(r=>{
      if(r.ce&&finite(r.ce.close)&&r.ce.close>0.5&&finite(r.strike)&&r.strike>0) ceMap[r.strike]=r.ce;
      if(r.pe&&finite(r.pe.close)&&r.pe.close>0.5&&finite(r.strike)&&r.strike>0) peMap[r.strike]=r.pe;
    });
    const ceS=Object.keys(ceMap).map(Number).sort((a,b)=>a-b);
    const peS=Object.keys(peMap).map(Number).sort((a,b)=>a-b);
    if(!ceS.length||!peS.length) return '';
    const atm=ceS.reduce((b,k)=>Math.abs(k-spot)<Math.abs(b-spot)?k:b,ceS[0]);
    const bcS=ceS.find(k=>k>=atm+350)||ceS[ceS.length-1];
    const bpH=[...peS].reverse().find(k=>k<=spot-350)||peS[0];
    const bpB=[...peS].reverse().find(k=>k<=spot*1.001)||peS[peS.length-1];
    const bpSl=[...peS].reverse().find(k=>k<=bpB-300)||peS[0];
    const bcH=ceS.find(k=>k>=spot+350)||ceS[ceS.length-1];
    if(!ceMap[atm]||!ceMap[bcS]||!peMap[bpH]||!peMap[bpB]||!peMap[bpSl]||!ceMap[bcH]) return '';
    const hhhl=data.hhhl||{};
    const allCl=hhhl.close||[],hArr=hhhl.high||[],lArr=hhhl.low||[];
    const fCl=allCl.filter(v=>finite(v));
    let ema9=null;
    if(fCl.length>=9){const k9=2/10;ema9=fCl.slice(0,9).reduce((s,v)=>s+v,0)/9;for(let i=9;i<fCl.length;i++) ema9=fCl[i]*k9+ema9*(1-k9);}
    let vwap20=null;
    const n20=Math.min(20,allCl.length);
    if(n20>0){let vs=0,vc=0;for(let i=allCl.length-n20;i<allCl.length;i++){if(finite(hArr[i])&&finite(lArr[i])&&finite(allCl[i])){vs+=(hArr[i]+lArr[i]+allCl[i])/3;vc++;}}if(vc) vwap20=vs/vc;}
    const lastCl=fCl.length?fCl[fCl.length-1]:null;
    const e9Bull=finite(ema9)&&finite(lastCl)&&lastCl>ema9;
    const vwBull=finite(vwap20)&&finite(lastCl)&&lastCl>vwap20;
    const bias=(e9Bull&&vwBull)?'bullish':(!e9Bull&&!vwBull)?'bearish':'mixed';
    const setups=Array.isArray(data.setups)?data.setups:[];
    const str=idx.structure||{};
    const bullSU=setups.find(s=>s.rule==='hhhl_breakout_call'||s.rule==='hhhl_bull_call_spread');
    const bearSU=setups.find(s=>s.rule==='lhll_bear_put_spread'||s.rule==='lhll_buy_put');
    const bFire=bullSU&&bullSU.firing,beFire=bearSU&&bearSU.firing;
    const curStr=(str.structure||'').toLowerCase();
    const isHh=curStr.includes('hh'),isLh=curStr.includes('lh');
    let sigL='NO CONFIRMED SIGNAL \u2014 reference only',sigC='nc-hm-wait',sigD='wait';
    if(bFire){sigL='\u25b2 HH+HL CONFIRMED \u2014 BULLISH ACTIVE';sigC='nc-hm-bull';sigD='bull';}
    else if(beFire){sigL='\u25bc LH+LL CONFIRMED \u2014 BEARISH ACTIVE';sigC='nc-hm-bear';sigD='bear';}
    else if(isHh&&bias==='bullish'){sigL='\u26a0 HH/HL+EMA9+VWAP all bullish \u2014 awaiting backtest gate';sigC='nc-hm-watch';}
    else if(isLh&&bias==='bearish'){sigL='\u26a0 LH/LL+EMA9+VWAP all bearish \u2014 awaiting backtest gate';sigC='nc-hm-watch';}
    const jev=(data.jev||{}).index||{};
    const jDir=jev.direction||{},jPos=jev.positioning||{},jSet=jev.setup||{};
    const jBear=jPos.choice==='institutions_bearish'||(jSet.choice||'').includes('bear');
    const jBull=jDir.choice==='bullish';
    const bD=Math.round((ceMap[atm].close-ceMap[bcS].close+peMap[bpH].close)*lot);
    const beD=Math.round((peMap[bpB].close-peMap[bpSl].close+ceMap[bcH].close)*lot);
    const scens=[-700,-500,-300,-100,0,200,400,600,800].map(d=>Math.round(spot+d));
    const bPnl=s=>Math.round((Math.max(s-atm,0)-Math.max(s-bcS,0)-(ceMap[atm].close-ceMap[bcS].close)+Math.max(bpH-s,0)-peMap[bpH].close)*lot);
    const bePnl=s=>Math.round((Math.max(bpB-s,0)-Math.max(bpSl-s,0)-(peMap[bpB].close-peMap[bpSl].close)+Math.max(s-bcH,0)-ceMap[bcH].close)*lot);
    const pC=v=>v>0?'pos':v<0?'neg':'';
    const fP=v=>(v>=0?'+':'')+'\u20b9'+Math.abs(v).toLocaleString('en-IN');
    const tR=fn=>scens.map(s=>{const v=fn(s),ch=Math.round((s-spot)/spot*100);return '<tr><td class="nc-num">'+s.toLocaleString('en-IN')+' <span class="nc-hm-chg">'+(ch>=0?'+':'')+ch+'%</span></td><td class="nc-num '+pC(v)+'">'+fP(v)+'</td></tr>';}).join('');
    const chips=''
      +'<span class="nc-hm-chip '+(e9Bull?'pos':'neg')+'">EMA 9: '+(finite(ema9)?Math.round(ema9).toLocaleString('en-IN'):'\u2014')+'\u202f\u2014\u202fclose '+(e9Bull?'above \u2191':'below \u2193')+'</span>'
      +'<span class="nc-hm-chip '+(vwBull?'pos':'neg')+'">VWAP-20d: '+(finite(vwap20)?Math.round(vwap20).toLocaleString('en-IN'):'\u2014')+'\u202f\u2014\u202fclose '+(vwBull?'above \u2191':'below \u2193')+'</span>'
      +'<span class="nc-hm-chip '+(isHh?'pos':isLh?'neg':'')+'">HH/HL: '+xss(str.structure||'n/a')+'</span>'
      +'<span class="nc-hm-chip '+(bias==='bullish'?'pos':bias==='bearish'?'neg':'')+'">Combined bias: '+xss(bias)+'</span>';
    const jevR='<div class="nc-hm-jev">Jev: direction <strong class="'+(jBull?'pos':jDir.choice==='bearish'?'neg':'')+'">'
      +xss(jDir.choice||'\u2014')+'</strong>'+(finite(jDir.confidence)?' ('+Math.round(jDir.confidence*100)+'% conf.)':'')
      +' \u00b7 positioning <strong class="'+(jBear?'neg':'pos')+'">'+xss(jPos.choice||'\u2014')+'</strong>'
      +(jBear?' <span class="nc-hm-warn">\u26a0 Institutions SHORT</span>':'')+'</div>';
    const mkCard=(dir,legs,deb,fn,dim)=>'<div class="nc-hm-trade'+dim+'">'
      +'<div class="nc-hm-trade-hdr nc-hm-'+(dir==='bull'?'bull':'bear')+'-hdr">'
      +(dir==='bull'?'\u25b2 BULLISH HEDGED \u2014 deploy when HH+HL fires':'\u25bc BEARISH HEDGED \u2014 deploy when LH+LL fires'+(jBear?' \u00b7 \u26a0 Jev: insts short':''))+'</div>'
      +'<div class="nc-hm-legs">'+legs+'<strong class="nc-hm-debit">Debit \u20b9'+deb.toLocaleString('en-IN')+'/lot</strong></div>'
      +'<table class="nc-hm-tbl"><thead><tr><th>Nifty at expiry</th><th>P&amp;L / lot</th></tr></thead><tbody>'+tR(fn)+'</tbody></table>'
      +'<p class="nc-caveat">Gross at expiry \u00b7 lot='+lot+' \u00b7 EOD closes \u00b7 fees excluded \u00b7 not advice.</p></div>';
    const bLegs='<span class="pos">BUY</span> '+atm+' CE @\u20b9'+f2(ceMap[atm].close)+' &nbsp;<span class="neg">SELL</span> '+bcS+' CE @\u20b9'+f2(ceMap[bcS].close)+' &nbsp;<span class="pos">BUY</span> '+bpH+' PE @\u20b9'+f2(peMap[bpH].close)+' ';
    const beLegs='<span class="pos">BUY</span> '+bpB+' PE @\u20b9'+f2(peMap[bpB].close)+' &nbsp;<span class="neg">SELL</span> '+bpSl+' PE @\u20b9'+f2(peMap[bpSl].close)+' &nbsp;<span class="pos">BUY</span> '+bcH+' CE @\u20b9'+f2(ceMap[bcH].close)+' ';
    return '<div class="nc-hm-wrap">'
      +'<div class="nc-hm-signal '+sigC+'">'+xss(sigL)+'</div>'
      +'<div class="nc-hm-inds">'+chips+'</div>'
      +jevR
      +'<p class="nc-hm-note">EMA9 &amp; VWAP computed from EOD daily closes. For intraday 3-5-10 min precision, apply same signal logic on a live chart. Bullish: close above EMA9 &amp; VWAP; bearish: below both.</p>'
      +'<div class="nc-hm-trades">'+mkCard('bull',bLegs,bD,bPnl,sigD==='bear'?' nc-hm-dim':'')+mkCard('bear',beLegs,beD,bePnl,sigD==='bull'?' nc-hm-dim':'')+'</div>'
      +'<p class="nc-hm-disc">Framework: HH+HL + EMA9 + VWAP confirm \u2192 deploy matched hedged spread. Wait for confirmed HHHL backtest gate before entry. Not investment advice.</p>'
      +'</div>';
  }
  return {expiryRisk, positionGreeks, rankTradeSetups, findBestDebitSpread, rankSpreadsByEV, buildHedgedMoveCard};
});
