'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {match,fresh,valid}=require('../public/daily-deals');
const {choose}=require('./daily-market-data');
const now=Date.parse('2026-10-02T14:00:00Z');
function snapshot(){return {version:1,as_of:'2026-10-01',attempted_at:'2026-10-02T13:00:00Z',recent_deals:[{date:'2026-09-29',symbol:'BSE',kind:'bulk'}],...Object.fromEntries(['bulk','block','market','indices'].map(k=>[k,{state:'fresh',as_of:'2026-10-01',rows:k==='bulk'?[{symbol:'ADANIENT'}]:[]}]))};}
test('all stocks work when disclosure service is down; filters never invent negative evidence',()=>{
  assert.equal(match(null,'BSE','ALL',now),true);assert.equal(match(null,'BSE','bulk',now),false);
  const p=snapshot();assert.equal(match(p,'ADANIENT','bulk',now),true);assert.equal(match(p,'BSE','bulk',now),false);
  assert.equal(match(p,'BSE','recent',now),true);assert.equal(match(p,'ADANIENT','bulk',now,true),false);
});
test('stale and mismatched dates cannot satisfy current-session filter',()=>{
  const p=snapshot();p.bulk.as_of='2026-09-30';assert.equal(valid(p),false);assert.equal(match(p,'ADANIENT','bulk',now),false);
  const q=snapshot();q.attempted_at='2026-09-29T00:00:00Z';assert.equal(fresh(q,'bulk',now),false);
});
test('Railway backup is served when newer; dated source failure is not hidden by old fresh data',()=>{
  const remote=snapshot(),local=snapshot();local.attempted_at='2026-10-02T14:00:00Z';local.bulk.state='stale';
  assert.equal(choose(remote,local),local);assert.equal(choose(remote,null),remote);
  assert.throws(()=>choose({},{}));
});
