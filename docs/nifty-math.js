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
      unlimitedProfit, unlimitedLoss, netDebit: debit * lot,
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
      const bounded = risk.valid && !risk.unlimitedLoss && finite(risk.maxLoss) && risk.maxLoss < 0;
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
      if (risk.valid && !bounded && !risk.unlimitedLoss) warnings.push('No positive finite loss budget: check quotes, costs and execution; apparent arbitrage is not trade-ready.');
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
    if (!finite(spot) || !finite(lot) || lot <= 0) return [];
    const tradeExp = (data.expiries || []).find(e => e.trade_expiry);
    if (!tradeExp || !Array.isArray(tradeExp.rows)) return [];
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
              delta_buy: cb.delta || null, delta_sell: cs.delta || null,
              theta_buy: cb.theta || null, theta_sell: cs.theta || null,
              iv_buy: cb.iv || null, iv_sell: cs.iv || null,
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
  return {expiryRisk, positionGreeks, rankTradeSetups, findBestDebitSpread};
});
