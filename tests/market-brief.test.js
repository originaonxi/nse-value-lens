const test=require('node:test');
const assert=require('node:assert/strict');
const {safeURL,filtered,validSnapshot,esc}=require('../public/market-brief');
test('market links and titles cannot execute source text',()=>{
  assert.equal(safeURL('javascript:alert(1)'),'#');
  assert.equal(safeURL('https://key:secret@example.com'),'#');
  assert.equal(safeURL('https://www.rbi.org.in/a'),'https://www.rbi.org.in/a');
  assert.equal(esc('<script>'), '&lt;script&gt;');
});
test('context filtering cannot turn supportive non-setups into entries',()=>{
  const rows=[{symbol:'A',name:'Alpha',sector:'IT',context:'supportive',hhhl_eligible:false,vcp:'WATCH',vcp_ready:false},{symbol:'B',name:'Beta',sector:'Bank',context:'conflicting',hhhl_eligible:true,vcp:'NO_SETUP',vcp_ready:true}];
  assert.equal(filtered(rows,'','supportive','HHHL').length,0);
  assert.equal(filtered(rows,'','ALL','VCP').length,0);
  assert.equal(filtered(rows,'bank','ALL','HHHL')[0].symbol,'B');
});
test('partial or duplicate public universes fail validation',()=>{
  assert.equal(validSnapshot({rows:[]}),false);
  const d={version:1,as_of:'2026-09-23',generated_at:'2026-09-24T01:00:00Z',universe_count:200,rows:Array.from({length:200},(_,i)=>({symbol:'S'+i,context:'insufficient',event_risk:'unknown'})),evidence:{quotes:[],sources:[]},macro:{},drivers:[],forward_test:{}};
  assert.equal(validSnapshot(d),true);d.rows[1].symbol=d.rows[0].symbol;assert.equal(validSnapshot(d),false);
});
