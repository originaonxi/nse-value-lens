'use strict';
const fs=require('node:fs/promises');
const path=require('node:path');
const {validate:validateFno}=require('../public/hhhl-universe');
const cache=new Map(),inflight=new Map();
function valid(name,data){
  try{
    if(name==='hhhl_fno'){validateFno(data);return true;}
    if(name==='global_markets')return data?.schema_version===1&&Number.isFinite(Date.parse(data.generated_at))&&data.instrument_count===26&&Array.isArray(data.rows)&&data.rows.length===26&&new Set(data.rows.map(r=>r.symbol)).size===26&&data.rows.every(r=>Array.isArray(r.chart)&&r.zones&&r.pivots);
  }catch{}
  return false;
}
async function loadCurrentMarket(name){
  if(!['hhhl_fno','global_markets'].includes(name))throw Error('Unknown dataset');
  if(cache.get(name)?.expires>Date.now())return cache.get(name);
  if(inflight.has(name))return inflight.get(name);
  const request=(async()=>{
    let payload,source='github';
    try{
      const res=await fetch('https://raw.githubusercontent.com/originaonxi/nse-value-lens/master/docs/'+name+'.json?refresh='+Date.now(),{signal:AbortSignal.timeout(6000)});
      if(!res.ok)throw Error('Upstream unavailable');payload=await res.json();
      if(!valid(name,payload))throw Error('Incomplete upstream');
    }catch{
      source='local-fallback';payload=cache.get(name)?.payload||JSON.parse(await fs.readFile(path.join(__dirname,'..','public','data',name+'.json'),'utf8'));
      if(!valid(name,payload))throw Error('Incomplete local snapshot');
    }
    const result={payload,source,expires:Date.now()+(source==='github'?60000:15000)};cache.set(name,result);return result;
  })();inflight.set(name,request);
  try{return await request;}finally{inflight.delete(name);}
}
module.exports={loadCurrentMarket,valid};
