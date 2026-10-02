'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');
const {valid,loadCurrentMarket}=require('./current-market-data');
test('F&O and global snapshots update from GitHub rather than remaining at deployment date',async()=>{
  const original=global.fetch;const calls=[];
  global.fetch=async url=>{calls.push(url);const name=url.includes('hhhl_fno')?'hhhl_fno':'global_markets';return {ok:true,json:async()=>JSON.parse(fs.readFileSync('public/data/'+name+'.json','utf8'))};};
  try{
    for(const name of ['hhhl_fno','global_markets']){
      const result=await loadCurrentMarket(name);assert.equal(result.source,'github');assert.equal(valid(name,result.payload),true);
      assert.equal(valid(name,{...result.payload,rows:[]}),false);
    }
    assert.equal(calls.length,2);assert.ok(calls.every(url=>url.includes('?refresh=')));
    await assert.rejects(loadCurrentMarket('../secret'));
  }finally{global.fetch=original;}
});
