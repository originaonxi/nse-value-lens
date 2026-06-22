'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { classifyFramework, classifyDiscount, lenderValuation, industrialValuation } = require('./analyzer');

test('classifies banks as lender framework', () => {
  const c = { symbol: 'BANKBARODA', companyName: 'Bank of Baroda', industry: 'Financial Services' };
  assert.equal(classifyFramework(c), 'bank');
  assert.match(classifyDiscount(c, { pe: 7, pb: 0.9, roe: 13 }).label, /PSU bank/);
});

test('classifies industrial companies separately', () => {
  const c = { symbol: 'POLYCAB', companyName: 'Polycab India Ltd.', industry: 'Capital Goods' };
  assert.equal(classifyFramework(c), 'industrial');
});

test('lender Gordon PB model produces conservative fair PB', () => {
  const result = lenderValuation({ roe: 12.7, pb: 0.89 }, 'bank');
  assert.ok(result.fairPb > 1.0 && result.fairPb < 1.1);
  assert.ok(result.upside > 0.1 && result.upside < 0.2);
});

test('industrial PE rerating math works', () => {
  const result = industrialValuation({ symbol: 'BPCL', industry: 'Oil Gas & Consumable Fuels' }, { pe: 5, earningsGrowth: 0 });
  assert.equal(result.targetPe, 9);
  assert.ok(result.upside > 0.7 && result.upside < 0.9);
});
