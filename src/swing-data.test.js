'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
function fresh() { delete require.cache[require.resolve('./swing-data')]; return require('./swing-data'); }
test('swing data shares inflight fetch and caches a valid upstream snapshot', async t => {
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => { calls++; return {ok:true,json:async()=>({as_of:'2026-09-23',candidates:[]})}; });
  const {loadSwing} = fresh();
  const [a,b] = await Promise.all([loadSwing('swing_desk'),loadSwing('swing_desk')]);
  assert.equal(a.source,'github'); assert.deepEqual(a,b);
  await loadSwing('swing_desk'); assert.equal(calls,1);
});
test('invalid upstream uses a labelled local fallback', async t => {
  t.mock.method(globalThis, 'fetch', async () => ({ok:true,json:async()=>({error:'bad data'})}));
  const result = await fresh().loadSwing('swing_desk');
  assert.equal(result.source,'local-fallback');
  assert.ok(Array.isArray(result.payload.candidates));
});
test('unknown dataset cannot select an arbitrary file or URL', async () => {
  await assert.rejects(fresh().loadSwing('../../.env'),/Unknown/);
});
