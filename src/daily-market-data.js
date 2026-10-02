'use strict';
const fs=require('node:fs/promises');
const path=require('node:path');
const {valid}=require('../public/daily-deals');
let cached=null, pending=null;
function choose(remote,local){
  const candidates=[remote,local].filter(valid);
  if(!candidates.length)throw Error('No valid daily market snapshot');
  candidates.sort((a,b)=>b.as_of.localeCompare(a.as_of)||Date.parse(b.attempted_at)-Date.parse(a.attempted_at));
  return candidates[0];
}
async function loadDailyMarket(){
  if(cached&&cached.expires>Date.now())return cached;
  if(pending)return pending;
  pending=(async()=>{
    const results=await Promise.allSettled([
      fetch('https://raw.githubusercontent.com/originaonxi/nse-value-lens/master/docs/daily_market.json?refresh='+Date.now(),{signal:AbortSignal.timeout(6000)})
        .then(r=>{if(!r.ok)throw Error('Upstream unavailable');return r.json();}),
      fs.readFile(path.join(__dirname,'..','public','data','daily_market.json'),'utf8').then(JSON.parse)
    ]);
    const remote=results[0].status==='fulfilled'?results[0].value:null;
    const local=results[1].status==='fulfilled'?results[1].value:null;
    const payload=choose(remote,local);
    cached={payload,source:payload===remote?'github':'local',expires:Date.now()+60000};
    return cached;
  })();
  try{return await pending;}finally{pending=null;}
}
module.exports={loadDailyMarket,choose};
