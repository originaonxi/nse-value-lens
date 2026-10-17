'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {expiryRisk, positionGreeks, rankTradeSetups} = require('../docs/nifty-math.js');
const approx = (a, b, eps = 1e-8) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);
const leg = (side, option_type, strike, ref_close, extra = {}) => ({side, option_type, strike, ref_close,
  expiry: '2026-11-03', lot: 65, delta: .4, gamma: .002, theta: -2, vega: 12, ...extra});
const callSpread = [leg('BUY', 'CE', 23000, 150), leg('SELL', 'CE', 23100, 100)];
const putSpread = [leg('BUY', 'PE', 23100, 150), leg('SELL', 'PE', 23000, 100)];
for (const legs of [callSpread, putSpread]) {
  const p = expiryRisk(legs, 23050); assert.equal(p.valid, true);
  approx(p.maxProfit, 3250); approx(p.maxLoss, -3250); approx(p.riskReward, 1); approx(p.breakevens[0], 23050);
}
const longCall = expiryRisk([callSpread[0]], 23000);
assert.equal(longCall.unlimitedProfit, true); assert.equal(longCall.maxProfit, null); approx(longCall.maxLoss, -9750);
const shortCall = expiryRisk([leg('SELL', 'CE', 23000, 150)], 23000);
assert.equal(shortCall.unlimitedLoss, true); assert.equal(shortCall.maxLoss, null);
const shortPut = expiryRisk([leg('SELL', 'PE', 23000, 150)], 23000);
approx(shortPut.maxLoss, -(23000 - 150) * 65); assert.equal(shortPut.unlimitedLoss, false);
const ratio = expiryRisk([leg('BUY', 'CE', 23000, 150), leg('SELL', 'CE', 23100, 100, {quantity: 2})], 23050);
const duplicated = expiryRisk([leg('BUY', 'CE', 23000, 150), leg('SELL', 'CE', 23100, 100), leg('SELL', 'CE', 23100, 100)], 23050);
assert.deepEqual(ratio, duplicated); assert.equal(ratio.unlimitedLoss, true); assert.ok(ratio.breakevens.some(b => b > 23100));
const butterfly = expiryRisk([leg('BUY', 'PE', 23200, 250), leg('SELL', 'PE', 23000, 130, {quantity: 2}), leg('BUY', 'PE', 22600, 40)], 23100);
approx(butterfly.maxProfit, 170 * 65); approx(butterfly.maxLoss, -230 * 65);
const nearZero = expiryRisk([leg('BUY', 'CE', 200, 20), leg('SELL', 'CE', 210, 10, {quantity: 2}), leg('BUY', 'CE', 230, 10 - 1e-10)], 210);
assert.equal(nearZero.breakevens.length, 1); approx(nearZero.breakevens[0], 210);
for (const bad of [[], [leg('BUY', 'CE', 0, 150)], [leg('BUY', 'CE', 23000, null)],
  [leg('BUY', 'CE', 23000, 0)], [leg('BUY', 'CE', 23000, 150, {quantity: 0})],
  [leg('BUY', 'CE', 23000, 150, {expiry: '2026-02-30'})],
  [callSpread[0], leg('SELL', 'CE', 23100, 100, {expiry: '2026-12-01'})],
  [callSpread[0], leg('SELL', 'CE', 23100, 100, {lot: 75})]]) assert.equal(expiryRisk(bad).valid, false);
approx(positionGreeks([leg('BUY', 'CE', 23000, 150, {quantity: 2}), leg('SELL', 'CE', 23100, 100)]).delta, 26);
assert.equal(positionGreeks([leg('BUY', 'CE', 23000, 150, {gamma: null})]).gamma, null);

const stats = {trades: 70, t_stat: 2.5, mean_return_pct: 4, first_half: {mean_return_pct: 3}, second_half: {mean_return_pct: 5}};
const setup = (id, extra = {}) => ({rule: id, label: id, firing: true, status: 'VALIDATED', legs: callSpread,
  plan: {exit_by: '2026-10-26'}, exit: {hold_sessions: 5, horizon_calendar_days: 10, remaining_dte: 8, exp_pnl_per_lot: 300, p_profit: 60, pnl_worst5: -2000, round_trip_costs: 120},
  jev_priority: {tier: 'high', confidence: .8}, ...extra});
const fixture = setups => ({as_of: '2026-10-16', inputs: {stale: []}, index: {option_spot: 23100},
  method: {hold_sessions: 5}, jev: {state: 'ok'}, expiries: [{expiry: '2026-11-03', atm_iv: 15}], setups,
  rules: setups.map(s => ({id: s.rule, status: s.status, stats}))});
const options = {now: new Date('2026-10-17T12:00:00Z')};
const rank = setups => rankTradeSetups(fixture(setups), options);
let ranked = rank([setup('positive')]);
assert.equal(ranked[0].bucket, 'consider'); assert.equal(ranked[0].eligible, true);
approx(ranked[0].sigmaMove, 23100 * .15 * Math.sqrt(18 / 365));
assert.ok(ranked[0].mathScore >= 0 && ranked[0].mathScore <= 100);
ranked = rank([setup('bad-ev', {exit: {...setup('x').exit, exp_pnl_per_lot: -1, p_profit: 99}}), setup('positive')]);
assert.equal(ranked[0].setup.rule, 'positive'); assert.equal(ranked[1].bucket, 'avoid');
assert.equal(rank([setup('unknown', {jev_priority: null})])[0].bucket, 'watch');
assert.equal(rank([setup('avoid', {jev_priority: {tier: 'avoid', confidence: .99}})])[0].bucket, 'avoid');
assert.equal(rank([setup('inactive', {firing: false})])[0].bucket, 'inactive');
assert.equal(rank([setup('missing-trigger', {firing: undefined})])[0].eligible, false);
assert.equal(rank([setup('weak', {status: 'WEAK'})])[0].eligible, false);
assert.equal(rank([setup('no-edge', {status: 'NO_EDGE'})])[0].bucket, 'avoid');
assert.equal(rank([setup('missing-exit', {exit: {}})])[0].bucket, 'avoid');
assert.equal(rank([setup('mixed-horizon', {exit: {...setup('x').exit, hold_sessions: 1}})])[0].bucket, 'avoid');
assert.equal(rank([setup('legacy-calendar', {exit: {...setup('x').exit, horizon_calendar_days: undefined}})])[0].bucket, 'avoid');
assert.equal(rank([setup('wrong-calendar', {exit: {...setup('x').exit, horizon_calendar_days: 5}})])[0].bucket, 'avoid');
assert.equal(rank([setup('call-ratio', {legs: [leg('BUY', 'CE', 23000, 150), leg('SELL', 'CE', 23100, 100, {quantity: 2})]})])[0].eligible, false);
assert.equal(rank([setup('unsupported-forecast-units', {legs: callSpread.map(l => ({...l, quantity: 2}))})])[0].eligible, false);
let f = fixture([setup('stale')]); f.as_of = '2026-10-01'; assert.equal(rankTradeSetups(f, options)[0].bucket, 'avoid');
f = fixture([setup('future')]); f.as_of = '2026-10-18'; assert.equal(rankTradeSetups(f, options)[0].eligible, false);
f = fixture([setup('expired')]); assert.equal(rankTradeSetups(f, {now: new Date('2026-11-04')})[0].eligible, false);
f = fixture([setup('stale-input')]); f.inputs.stale = ['options']; assert.equal(rankTradeSetups(f, options)[0].eligible, false);
f = fixture([setup('unvalidated')]); f.rules[0].stats = {...stats, trades: 3}; assert.equal(rankTradeSetups(f, options)[0].eligible, false);
f = fixture([setup('missing-greek', {legs: [leg('BUY', 'CE', 23000, 150, {gamma: null}), callSpread[1]]})]);
assert.equal(rankTradeSetups(f, options)[0].eligible, false);
const actual = JSON.parse(fs.readFileSync(path.join(__dirname, '../docs/nifty_chain.json'), 'utf8'));
const report = rankTradeSetups(actual, {now: new Date(actual.as_of + 'T12:00:00Z')});
assert.equal(report.length, actual.setups.length);
for (const s of actual.setups) {
  if (!s.exit) continue;
  const days = (Date.parse(s.plan.exit_by) - Date.parse(actual.as_of)) / 86400000;
  assert.equal(s.exit.horizon_calendar_days, days, `${s.rule}: producer must supply actual calendar exit time`);
}
assert.ok(report.every(s => s.mathScore === null || Number.isFinite(s.mathScore)));
assert.equal(new Set(report.map(r => r.setup.rule)).size, report.length);
assert.deepEqual(rankTradeSetups(actual, options), rankTradeSetups(actual, options));
console.log(`Dashboard maths regression passed; ${report.length} current setups ranked, ${report.filter(s => s.eligible).length} pass entry-research gate.`);
