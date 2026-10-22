'use strict';
// Unit fixtures below are deliberately synthetic; NEVER published as model output.
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.join(__dirname, '..');
const scan = JSON.parse(fs.readFileSync(path.join(root, 'docs/hhhl_scan.json')));
const chain = JSON.parse(fs.readFileSync(path.join(root, 'docs/nifty_chain.json')));
const script = new vm.Script(fs.readFileSync(path.join(root, 'docs/kronos.js'), 'utf8'));
const clone = x => JSON.parse(JSON.stringify(x));
const model = 'NeoQuasar/Kronos-small';
const futureDates = [1, 2, 3].map(days => {
  const d = new Date(scan.as_of + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
});
const fc = {model, provenance:{kind:'kronos-neural'}, pred_len:3, symbols:{NSEI:{
  provenance:{kind:'kronos-neural',model}, data_as_of:scan.as_of,
  last_close:chain.index.close, config:{n_samples:4},
  paths:[1, 2, -1, -2].map(offset => futureDates.map((d, i) => ({d,c:chain.index.close + offset * (i + 1)}))),
}}};
function element() {
  let html = '';
  const el = {hidden:false,value:'',textContent:'',options:[],listeners:{},attrs:{},
    setAttribute(k,v){this.attrs[k]=v;},addEventListener(k,v){this.listeners[k]=v;}};
  Object.defineProperty(el,'innerHTML',{get:()=>html,set(v){
    html=v;
    if (v.includes('<option')) {el.options=[...v.matchAll(/<option value="([^"]*)"/g)].map(m=>({value:m[1]}));el.value=el.options[0]?.value||'';}
  }});
  return el;
}
async function render({forecast=fc,snapshot=scan,index=chain,symbol='NSEI',delays={}}={}) {
  const store={}; const doc={getElementById(id){return store[id] ||= element();}};
  const ctx=vm.createContext({document:doc,URL,URLSearchParams,location:{search:'?symbol='+symbol,href:'https://example.test/kronos.html?symbol='+symbol},history:{replaceState(){}},console,
    fetch:async url=>{if(delays[url])await new Promise(r=>setTimeout(r,delays[url]));const data=url==='hhhl_scan.json'?snapshot:url==='nifty_chain.json'?index:forecast;return {ok:!!data,status:data?200:404,json:async()=>data};}});
  script.runInContext(ctx);
  await new Promise(r=>setTimeout(r,Math.max(0,...Object.values(delays))+15));
  return store;
}
const html=(s,id)=>s[id]?.innerHTML||'';
let passed=0;
async function test(name,fn){await fn();passed++;console.log('PASS',name);}
(async()=>{
  await test('real schema: all 201 selectors and actual Nifty market gate',async()=>{
    const s=await render();assert.equal(s['kro-symbol'].options.length,scan.rows.length+1);
    assert.equal(s['kro-symbol'].value,'NSEI');
    assert.match(html(s,'kro-market-gate'),new RegExp(scan.market.new_entries_allowed?'MARKET GATE OPEN':'MARKET GATE CLOSED'));
    assert.match(html(s,'kro-interp'),/Confirmed structure/);assert.ok(html(s,'kro-interp').includes(chain.index.structure.structure));
  });
  await test('valid close-only paths and even sample median',async()=>{
    const s=await render();assert.equal(html(s,'kro-forecast'),'');assert.match(html(s,'kronos-chart'),/model-generated close paths/);
    assert.match(html(s,'kro-stats'),/4 paths/);assert.match(html(s,'kro-stats'),/\+0\.0%/);
    assert.doesNotMatch(html(s,'kro-stats'),/profit|probability|regime/i);
  });
  for(const [name,mutate] of [
    ['wrong top model',d=>d.model='mock'],['missing top provenance',d=>delete d.provenance],
    ['wrong entry model',d=>d.symbols.NSEI.provenance.model='mock'],
    ['missing entry date',d=>delete d.symbols.NSEI.data_as_of],
    ['stale entry',d=>d.symbols.NSEI.data_as_of='2000-01-01'],
    ['future mismatch',d=>d.symbols.NSEI.data_as_of='2099-01-01'],
    ['stale flag',d=>d.symbols.NSEI.input_stale=true],
    ['zero close',d=>d.symbols.NSEI.paths[0][0].c=0],
    ['bad date',d=>d.symbols.NSEI.paths[0][0].d='<svg onload=alert(1)>'],
    ['partial path',d=>d.symbols.NSEI.paths[0].pop()],
    ['wrong sample count',d=>d.symbols.NSEI.config.n_samples=100],
  ]) await test(name+' rejected without hiding actual candles',async()=>{
    const d=clone(fc);mutate(d);const s=await render({forecast:d});
    assert.match(html(s,'kro-forecast'),/unavailable|stale/i);assert.doesNotMatch(html(s,'kro-forecast'),/running/i);
    assert.equal(html(s,'kro-stats'),'');assert.match(html(s,'kronos-chart'),/Historical EOD candles/);
    assert.ok((html(s,'kronos-chart').match(/<rect/g)||[]).length>=30);
  });
  await test('no forecast still renders independent actual stock candles and levels',async()=>{
    const row=scan.rows[0];const s=await render({forecast:null,symbol:row.symbol});
    assert.equal(s['kro-symbol'].value,row.symbol);assert.match(html(s,'kronos-chart'),/Historical EOD candles/);
    assert.ok(html(s,'kro-interp').includes(row.status));assert.match(html(s,'kro-interp'),/Overextension warning above/);
    assert.match(html(s,'kro-interp'),/not a price target/);
  });
  await test('late scanner and chain arrival still renders correct context',async()=>{
    const s=await render({delays:{'hhhl_scan.json':30,'nifty_chain.json':50}});
    assert.equal(s['kro-symbol'].options.length,scan.rows.length+1);assert.equal(html(s,'kro-forecast'),'');
    assert.ok(html(s,'kro-interp').includes(chain.index.structure.structure));
  });
  await test('all source failures show unavailability rather than job running',async()=>{
    const s=await render({forecast:null,snapshot:null,index:null});
    assert.doesNotMatch(html(s,'kro-forecast'),/running/i);assert.match(html(s,'kro-market-gate'),/unavailable/i);
  });
  console.log(passed+' regression cases passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
