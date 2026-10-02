'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = (n,d=2) => Number.isFinite(n)?n.toLocaleString('en-IN',{maximumFractionDigits:d}):'—';
  const pct = n => (n>0?'+':'')+fmt(n)+'%';
  const member = (r,scope) => scope==='exchange' || (scope==='all'?r.membership?.nifty200||r.membership?.fno:r.membership?.[scope]);
  let data=null, displayed=[], fetchFailed=false;
  function market() {
    const scope=$('market-universe').value;
    if (!Array.isArray(data.market.rows) || !data.market.rows.length) {
      $('breadth-scope').textContent='Official bhavcopy unavailable. Breadth cannot be calculated.';
      $('breadth-cards').innerHTML='';$('ma-breadth').innerHTML='';$('sector-breadth').innerHTML='';
      $('market-leaders').innerHTML='<tr><td colspan="5">Market prices unavailable.</td></tr>';
      $('breadth-legend').textContent='No market figures available.';
      for(const id of ['up','down','flat'])$('breadth-'+id).style.width='0%';
      return;
    }
    const rows=(data.market.rows||[]).filter(r=>member(r,scope));
    const up=rows.filter(r=>r.close>r.previous_close),down=rows.filter(r=>r.close<r.previous_close),flat=rows.length-up.length-down.length;
    const vol=rs=>rs.reduce((sum,r)=>sum+r.volume,0),uv=vol(up),dv=vol(down);
    $('breadth-scope').textContent=(data.market.as_of||'Unavailable')+' · '+rows.length+' securities with valid prices · '+(scope==='exchange'?data.market.scope:'Only available stocks in the selected site universe.');
    const card=(label,value,note)=>'<div><span class="label">'+label+'</span><strong>'+value+'</strong><small>'+note+'</small></div>';
    $('breadth-cards').innerHTML=card('ADVANCING',fmt(up.length,0),fmt(flat,0)+' unchanged')+card('DECLINING',fmt(down.length,0),fmt(rows.length,0)+' in scope')+card('A/D RATIO',down.length?fmt(up.length/down.length):'—','Advances ÷ declines')+card('UP / DOWN VOLUME',uv+dv?fmt(100*uv/(uv+dv),0)+'% / '+fmt(100*dv/(uv+dv),0)+'%':'—','Share volume; unchanged excluded');
    for(const [id,n] of [['up',up.length],['down',down.length],['flat',flat]])$('breadth-'+id).style.width=(rows.length?100*n/rows.length:0)+'%';
    $('breadth-legend').textContent=up.length+' advancing · '+flat+' unchanged · '+down.length+' declining';
    const tracked=rows.filter(r=>r.membership?.nifty200||r.membership?.fno);
    $('ma-breadth').innerHTML=[20,50,200].map(n=>{
      const eligible=tracked.filter(r=>typeof r.above_sma?.[n]==='boolean'),above=eligible.filter(r=>r.above_sma[n]).length;
      return '<div class="ma-item"><span>Above '+n+'-session average</span><strong>'+(eligible.length?fmt(above/eligible.length*100,1)+'%':'—')+'</strong><span>'+above+' / '+eligible.length+' eligible tracked stocks · adjusted histories</span></div>';
    }).join('');
    const ranking=$('market-ranking').value;
    const ranked=[...rows].sort((a,b)=>ranking==='gainers'?b.change_pct-a.change_pct:ranking==='losers'?a.change_pct-b.change_pct:ranking==='volume'?b.volume-a.volume:b.turnover_crore-a.turnover_crore).slice(0,15);
    $('market-leaders').innerHTML=ranked.map(r=>'<tr><td>'+stockLink(r)+'<small>'+esc(r.name)+'</small></td><td>₹'+fmt(r.close)+'</td><td class="'+(r.change_pct>=0?'positive':'negative')+'">'+pct(r.change_pct)+'</td><td>'+fmt(r.volume,0)+'</td><td>₹'+fmt(r.turnover_crore)+' cr</td></tr>').join('');
    const sectors=new Map();
    for(const r of tracked){const name=r.membership.sector||'Unknown';if(!sectors.has(name))sectors.set(name,[]);sectors.get(name).push(r);}
    $('sector-breadth').innerHTML=[...sectors].map(([name,rs])=>({name,count:rs.length,up:rs.filter(r=>r.change_pct>0).length,change:rs.reduce((s,r)=>s+r.change_pct,0)/rs.length})).sort((a,b)=>b.change-a.change).map(s=>'<div class="sector-item"><strong>'+esc(s.name)+'</strong><span class="'+(s.change>=0?'positive':'negative')+'">'+pct(s.change)+'</span><span> · '+s.up+'/'+s.count+' advancing</span></div>').join('');
  }
  function stockLink(r){return member(r,'all')?'<a href="hhhl.html?universe=all&amp;symbol='+encodeURIComponent(r.symbol)+'">'+esc(r.symbol)+'</a>':esc(r.symbol);}
  function deals(){
    const period=$('deal-period').value,kind=$('deal-kind').value,scope=$('deal-universe').value,search=$('deal-search').value.trim().toLowerCase();
    let rows=period==='latest'?['bulk','block'].flatMap(k=>data[k]?.as_of===data.as_of?(data[k].rows||[]):[]):period==='recent'?DailyDeals.recent(data):data.recent_deals;
    displayed=rows.filter(r=>member(r,scope)&&(kind==='all'||r.kind===kind)&&(!search||(r.symbol+' '+r.name+' '+r.client).toLowerCase().includes(search))).sort((a,b)=>b.date.localeCompare(a.date)||a.symbol.localeCompare(b.symbol)||b.value_crore-a.value_crore);
    const kinds=kind==='all'?['bulk','block']:[kind];const current=!fetchFailed&&kinds.every(k=>DailyDeals.fresh(data,k));
    $('deal-status').classList.toggle('warning',!current);
    $('deal-status').textContent=displayed.length+' disclosure rows in this view. '+(current?'Latest dated reports: '+data.as_of+'. ':'Refresh incomplete or overdue; absence of a row does not prove absence of a deal. ')+(period==='latest'?'': 'History includes only collected reports; '+data.history_errors.length+' recent report gaps recorded.');
    $('deal-rows').innerHTML=displayed.length?displayed.map(r=>'<tr><td>'+esc(r.date)+'<small>'+esc(r.kind.toUpperCase())+'</small></td><td>'+stockLink(r)+'</td><td>'+esc(r.client)+'</td><td class="deal-side">'+esc(r.side)+'</td><td>'+fmt(r.quantity,0)+'</td><td>₹'+fmt(r.price)+'</td><td>₹'+fmt(r.value_crore)+' cr</td></tr>').join(''):'<tr><td colspan="7">'+(current?'No disclosures match these filters in the available reports.':'No matching saved disclosures. Current coverage needs checking.')+'</td></tr>';
    $('deals-download').disabled=!displayed.length;
  }
  function render(){
    $('daily-session').textContent=data.as_of;
    $('daily-checked').textContent='Last attempt '+new Date(data.attempted_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})+' IST';
    const good=!fetchFailed&&['market','indices','bulk','block'].every(k=>DailyDeals.fresh(data,k));
    $('daily-status').classList.toggle('warning',!good);
    $('daily-status').textContent=good?'All four official reports checked for '+data.as_of+'. Holidays keep the last completed trading session.':'Some reports are unavailable, stale, or overdue. Each section retains its actual source date; no new prices or zero-deal claims are invented.';
    market();deals();
    const names=['Nifty 50','Nifty Next 50','Nifty 100','Nifty 200','Nifty 500','Nifty Bank','Nifty IT','Nifty Midcap 100'];
    $('indices-date').textContent=(data.indices.as_of||'Unavailable')+' · '+data.indices.state;
    $('index-cards').innerHTML=names.map(name=>(data.indices.rows||[]).find(r=>r.name.toLowerCase()===name.toLowerCase())).filter(Boolean).map(r=>'<div class="index-item"><span>'+esc(r.name)+'</span><strong>'+fmt(r.close)+'</strong><span class="'+(r.change_pct>=0?'positive':'negative')+'">'+pct(r.change_pct)+'</span></div>').join('');
    $('daily-sources').innerHTML=['market','indices','bulk','block'].map(k=>{
      const p=data[k],url=p.source?.url;const safe=typeof url==='string'&&/^https:\/\/(www\.nseindia\.com|nsearchives\.nseindia\.com)\//.test(url);
      return '<p><b>'+esc(k.toUpperCase())+'</b> · '+esc(p.state)+' · '+esc(p.as_of||'no dated report')+(safe?' · <a target="_blank" rel="noopener noreferrer" href="'+esc(url)+'">NSE source</a>':'')+(p.error?' · '+esc(p.error):'')+'</p>';
    }).join('')+'<p>Universe: '+data.coverage.nifty200+' Nifty 200 members, '+data.coverage.fno+' F&amp;O members, '+data.coverage.all+' unique tracked stocks. '+esc(data.coverage.source_note)+'</p>';
  }
  async function load(){try{const r=await fetch((document.body.dataset.source||'')+'daily_market.json',{cache:'no-store'});if(!r.ok)throw Error('Unavailable');const p=await r.json();if(!DailyDeals.valid(p))throw Error('Invalid');data=p;fetchFailed=false;render();}catch{fetchFailed=true;if(data)render();else{$('daily-status').textContent='Daily NSE reports could not be loaded. No market figures or deal matches are available.';$('daily-status').classList.add('warning');$('deals-download').disabled=true;}}}
  ['market-universe','market-ranking'].forEach(id=>$(id).addEventListener('change',()=>data&&market()));
  ['deal-universe','deal-period','deal-kind'].forEach(id=>$(id).addEventListener('change',()=>data&&deals()));
  $('deal-search').addEventListener('input',()=>data&&deals());
  $('deals-download').addEventListener('click',()=>{
    const columns=['date','kind','symbol','client','side','quantity','price','value_crore'];
    const cell=v=>'"'+String(v??'').replace(/^[=+@-]/,"'$&").replace(/"/g,'""')+'"';
    const csv=[columns.join(','),...displayed.map(r=>columns.map(k=>cell(r[k])).join(','))].join('\r\n');
    const url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download='nse-disclosures-'+data.as_of+'.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  load();setInterval(()=>{if(document.visibilityState==='visible')load();},300000);
})();
