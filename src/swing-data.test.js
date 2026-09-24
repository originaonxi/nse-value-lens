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

test('HHHL snapshot and status update from GitHub without a Railway redeploy', async t => {
  t.mock.method(globalThis, 'fetch', async url => ({ok:true,json:async()=>url.includes('hhhl_refresh_status') ?
    {as_of:'2026-09-23',state:'partial',run_id:'test',attempted_at:'2026-09-23T11:00:00Z'} :
    {as_of:'2026-09-23',universe_count:200,rows:Array.from({length:200},(_,i)=>({symbol:'S'+i})),market:{data_ready:false}}}));
  const {loadSwing}=fresh();
  assert.equal((await loadSwing('hhhl_scan')).source,'github');
  assert.equal((await loadSwing('hhhl_refresh_status')).source,'github');
});

test('HHHL refuses a truncated upstream universe and preserves the labelled fallback', async t => {
  t.mock.method(globalThis, 'fetch', async()=>({ok:true,json:async()=>({as_of:'2026-09-23',universe_count:200,rows:[],market:{}})}));
  const result=await fresh().loadSwing('hhhl_scan');
  assert.equal(result.source,'local-fallback');
  assert.equal(result.payload.rows.length,200);
});

test('market brief validates all 200 stocks and avoids stale branch caches', async t => {
  const sample=JSON.parse(require('node:fs').readFileSync(require('node:path').join(__dirname,'../public/data/market_brief.json'),'utf8'));
  let requestURL;
  t.mock.method(globalThis,'fetch',async url=>{requestURL=url;return {ok:true,json:async()=>sample};});
  const current=await fresh().loadSwing('market_brief');
  assert.equal(current.source,'github');assert.equal(current.payload.rows.length,200);
  assert.match(requestURL,/market_brief\.json\?refresh=\d+/);
  t.mock.method(globalThis,'fetch',async()=>({ok:true,json:async()=>({...sample,rows:sample.rows.slice(0,199)})}));
  const fallback=await fresh().loadSwing('market_brief');
  assert.equal(fallback.source,'local-fallback');assert.equal(fallback.payload.rows.length,200);
});
