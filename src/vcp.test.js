'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs');
const {validSnapshot,filtered,csv,esc}=require('../public/vcp');
const snapshot=()=>JSON.parse(fs.readFileSync('public/data/vcp_scan.json','utf8'));
test('VCP requires every stock and every definition, not merely a success HTTP code',()=>{
  const data=snapshot();assert.ok(validSnapshot(data));
  data.rows.pop();assert.equal(validSnapshot(data),false);
  const duplicate=snapshot();duplicate.rows[1]=duplicate.rows[0];assert.equal(validSnapshot(duplicate),false);
  const missing=snapshot();delete missing.rows[0].modes.three;assert.equal(validSnapshot(missing),false);
});
test('filters and CSV retain all qualifying setups beyond ten rows',()=>{
  const data=snapshot();
  for(const row of data.rows)row.modes.three.state='WATCH';
  assert.equal(filtered(data.rows,'three','','WATCH').length,200);
  assert.equal(csv(filtered(data.rows,'three'),'three').split('\r\n').length,201);
  assert.equal(filtered(data.rows,'three','  reliance  ')[0].symbol,'RELIANCE');
});
test('displayed external text is escaped',()=>assert.equal(esc('<script>"&'), '&lt;script&gt;&quot;&amp;'));
test('VCP snapshot and status can refresh on Railway without redeploying',async t=>{
  const data=snapshot();
  t.mock.method(globalThis,'fetch',async url=>{
    assert.match(url,/\.json\?refresh=\d+$/,'mutable GitHub branch cache must be bypassed');
    return {ok:true,json:async()=>url.includes('vcp_refresh_status')?
      {as_of:data.as_of,run_id:'test',state:'fresh',attempted_at:'2026-09-24T08:00:00Z'}:data};
  });
  delete require.cache[require.resolve('./swing-data')];
  const {loadSwing}=require('./swing-data');
  assert.equal((await loadSwing('vcp_scan')).source,'github');
  assert.equal((await loadSwing('vcp_refresh_status')).source,'github');
});
test('broken VCP upstream falls back to a complete dated snapshot',async t=>{
  t.mock.method(globalThis,'fetch',async()=>({ok:true,json:async()=>({as_of:'2026-09-23',rows:[]})}));
  delete require.cache[require.resolve('./swing-data')];
  const result=await require('./swing-data').loadSwing('vcp_scan');
  assert.equal(result.source,'local-fallback');assert.ok(validSnapshot(result.payload));
});
