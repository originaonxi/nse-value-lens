'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {validate,view}=require('../public/hhhl-universe');
const read=name=>JSON.parse(fs.readFileSync(path.join(__dirname,'../docs',name),'utf8'));
const base=read('hhhl_scan.json'),extra=read('hhhl_fno.json');
const options={now:Date.parse(extra.generated_at)+1000};

test('all views deduplicate common stocks and retain original row objects',()=>{
  assert.strictEqual(view(base,extra,'nifty200',options),base);
  const all=view(base,extra,'all',options),fno=view(base,extra,'fno',options);
  const members=new Set(extra.membership.members.map(m=>m.symbol));
  assert.equal(fno.rows.length,members.size);
  assert.equal(all.rows.length,new Set([...base.rows.map(r=>r.symbol),...members]).size);
  for(const row of base.rows){
    assert.strictEqual(all.rows.find(r=>r.symbol===row.symbol),row);
    if(members.has(row.symbol))assert.strictEqual(fno.rows.find(r=>r.symbol===row.symbol),row);
  }
  for(const data of [all,fno])assert.equal(Object.values(data.counts).reduce((a,b)=>a+b,0),data.rows.length);
});

test('damaged membership and duplicate rows fail validation',()=>{
  const damaged=structuredClone(extra);damaged.membership.members[1]=damaged.membership.members[0];
  assert.throws(()=>validate(damaged));
  const duplicate=structuredClone(extra);duplicate.rows.push(duplicate.rows[0]);duplicate.extra_count++;
  assert.throws(()=>validate(duplicate));
  assert.throws(()=>validate({...extra,fno_count:1}));
});

test('new members never silently disappear while awaiting a first price download',()=>{
  const changed=structuredClone(extra);
  changed.membership.members.push({symbol:'NEWSTOCK',name:'New Stock'});changed.fno_count++;
  const row=view(base,changed,'fno',options).rows.find(r=>r.symbol==='NEWSTOCK');
  assert.equal(row.status,'CAUTION');assert.equal(row.chart.length,0);assert.equal(row.entry_allowed,false);
});

test('stale sessions, changed benchmark, overdue refresh and failed fetch block only extra stocks',()=>{
  const original=JSON.stringify({base,extra});
  const next={...base,as_of:'2026-09-28'};
  const market={...base,market:{...base.market,close:base.market.close+1}};
  for(const [snapshot,opts] of [[next,options],[market,options],[base,{now:Date.parse(extra.generated_at)+61*3600000}],[base,{...options,loadError:true}]]){
    const data=view(snapshot,extra,'all',opts);
    for(const old of base.rows)assert.strictEqual(data.rows.find(r=>r.symbol===old.symbol),old);
    for(const row of extra.rows){
      const shown=data.rows.find(r=>r.symbol===row.symbol);
      assert.equal(shown.status,'CAUTION');assert.equal(shown.entry_allowed,false);assert.equal(shown.entry_plan,null);
      assert.strictEqual(shown.chart,row.chart);assert.equal(shown.data_date,row.data_date);
    }
  }
  assert.equal(JSON.stringify({base,extra}),original);
});

test('an invalid BUY gate is never accepted',()=>{
  const invalid=structuredClone(extra);invalid.rows[0].status='BUY';invalid.rows[0].entry_allowed=false;
  assert.throws(()=>validate(invalid));
});
