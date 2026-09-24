(function (root) {
  'use strict';
  const LABELS = {WATCH:'Awaiting breakout',TRIGGERED:'Already triggered',SCREEN_ONLY:'Filters only',NO_SETUP:'Filters not passed',INVALIDATED:'Invalidated',EXPIRED:'Expired',DATA:'Data incomplete'};
  const MODES = ['three','three_or_two_70','three_or_two_smaller'];
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = (v,d=2) => Number.isFinite(v) ? v.toLocaleString('en-IN',{maximumFractionDigits:d,minimumFractionDigits:d}) : '—';
  const rupee = v => Number.isFinite(v) ? '₹'+num(v) : '—';
  function validSnapshot(data) {
    return data?.version === 1 && /^\d{4}-\d{2}-\d{2}$/.test(data.as_of || '') && data.universe_count === 200 &&
      Array.isArray(data.rows) && data.rows.length === 200 && new Set(data.rows.map(r=>r.symbol)).size === 200 &&
      data.rows.every(r=>typeof r.symbol==='string' && Array.isArray(r.checks) && Array.isArray(r.chart) && MODES.every(m=>LABELS[r.modes?.[m]?.state]));
  }
  function filtered(rows, mode, search='', state='ALL', sector='ALL') {
    const q=search.trim().toLowerCase();
    const order={WATCH:0,TRIGGERED:1,SCREEN_ONLY:2,EXPIRED:3,INVALIDATED:4,NO_SETUP:5,DATA:6};
    return rows.filter(r=>(!q || (r.symbol+' '+r.name).toLowerCase().includes(q)) &&
      (state==='ALL'||r.modes[mode].state===state) && (sector==='ALL'||r.sector===sector))
      .sort((a,b)=>(order[a.modes[mode].state]-order[b.modes[mode].state])||a.symbol.localeCompare(b.symbol));
  }
  function csv(rows,mode) {
    const cell=v=>'"'+String(v??'').replace(/"/g,'""')+'"';
    const lines=[['Symbol','Company','Sector','Mode','State','Close','Daily date','Weekly screen date','Pivot','Trigger reference','Stop at trigger','Event date','Reason'],
      ...rows.map(r=>{const s=r.modes[mode];return [r.symbol,r.name,r.sector,mode,s.state,r.close,r.data_date,r.weekly_date,s.pattern?.pivot,s.preview?.trigger,s.preview?.stop_at_trigger,s.event_date,s.reason];})];
    return '\uFEFF'+lines.map(line=>line.map(cell).join(',')).join('\r\n');
  }
  if(typeof module==='object'&&module.exports) module.exports={validSnapshot,filtered,csv,esc};
  if(!root.document) return;
  const $=id=>document.getElementById(id);
  let data,mode='three_or_two_70',selected,visible=[];
  const badge=s=>`<span class="state ${esc(s)}">${esc(LABELS[s])}</span>`;
  function showRow(symbol,scroll=false) {
    selected=data.rows.find(r=>r.symbol===symbol); if(!selected) return;
    const r=selected,s=r.modes[mode],p=s.pattern;
    $('stock-detail').hidden=false;
    $('detail-title').textContent=r.symbol;
    $('detail-subtitle').textContent=r.name+' · '+r.sector;
    $('detail-state').textContent=LABELS[s.state];
    $('detail-reason').textContent=s.reason;
    const levels=[['Latest daily close',rupee(r.close),r.data_date || 'Unavailable'],['Daily ATR20',rupee(r.atr20),'As of latest completed session']];
    if(s.preview) levels.push(['Breakout reference',rupee(s.preview.trigger),'Pivot + 0.1%'],['Initial stop at trigger',rupee(s.preview.stop_at_trigger),num(s.preview.risk_pct)+'% planned distance']);
    else levels.push(['Entry reference','Unavailable','No active eligible entry'],['10-week SMA',rupee(r.weekly_exit_reference),'Weekly exit reference for existing positions']);
    $('entry-levels').innerHTML=levels.map(([a,b,c])=>`<div><span>${esc(a)}</span><strong>${esc(b)}</strong><small>${esc(c)}</small></div>`).join('')+
      '<p class="level-note">Actual entry determines the stop. An opening gap, slippage and fees can exceed planned risk. Weekly structure is frozen through '+esc(r.weekly_date || 'unavailable')+'.</p>';
    $('checks-date').textContent='Stock filters evaluated at weekly close '+(r.weekly_date||'unavailable')+'. Current daily data quality is checked separately.';
    const checks=r.checks.concat([{label:'Confirmed VCP under selected definition',pass:!!p,detail:p ? `${p.count} shrinking pullbacks; price, time and volume conditions passed.`:'No qualifying confirmed contraction sequence.'},{label:'Fresh setup still awaiting a trigger',pass:s.state==='WATCH',detail:s.reason}]);
    $('rule-checks').innerHTML=checks.map(c=>`<div class="check ${c.pass?'pass':'fail'}"><span class="verdict">${c.pass?'PASS':'NOT PASSED'}</span><b>${esc(c.label)}</b><p>${esc(c.detail)}</p></div>`).join('');
    $('contractions').innerHTML=p ? p.depths.map((depth,i)=>`<div class="contraction"><span class="label">CONTRACTION ${i+1}</span><strong>${num(depth*100)}%</strong><p>${p.durations[i]} week${p.durations[i]===1?'':'s'} from high to low</p><p>${esc(p.pivot_dates[i*2])} → ${esc(p.pivot_dates[i*2+1])}</p><p>Low confirmed ${esc(p.confirmation_dates[i*2+1])}</p><p>Mean pullback volume ${num(p.pullback_volumes[i],0)}</p></div>`).join('') : '<p class="muted">No VCP highlighted: the chart is price context only. An unfinished swing is not a confirmed contraction.</p>';
    chart();
    if(scroll){$('stock-detail').scrollIntoView({behavior:'smooth',block:'start'});$('detail-title').focus({preventScroll:true});}
  }
  function chart() {
    const r=selected,p=r.modes[mode].pattern,bars=r.chart.slice(-Number($('chart-window').value));
    const good=bars.filter(b=>[b.open,b.high,b.low,b.close].every(Number.isFinite));
    if(!good.length){$('stock-chart').innerHTML='<p>No complete weekly candles available.</p>';return;}
    const W=1100,H=455,left=18,right=90,top=26,bottom=326,volTop=366,volBottom=418;
    const prices=good.flatMap(b=>[b.high,b.low,...(Number.isFinite(b.sma10)?[b.sma10]:[])]);
    if(p) prices.push(p.pivot);
    const lo=Math.min(...prices),hi=Math.max(...prices),pad=Math.max((hi-lo)*.09,1),min=lo-pad,max=hi+pad;
    const step=(W-left-right)/bars.length,x=i=>left+(i+.5)*step,y=v=>top+(max-v)/(max-min)*(bottom-top),vol=Math.max(...good.map(b=>b.volume||0),1);
    let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(r.symbol)} completed weekly price and volume chart"><title>${esc(r.symbol)} weekly candles; ${esc(bars[0].date)} to ${esc(bars.at(-1).date)}</title>`;
    for(let i=0;i<=4;i++){const value=min+(max-min)*i/4,yy=y(value);svg+=`<line x1="${left}" x2="${W-right}" y1="${yy}" y2="${yy}" stroke="#e9ece5"/><text x="${W-right+10}" y="${yy+4}" fill="#76806e" font-size="12">${num(value)}</text>`;}
    let path='';bars.forEach((b,i)=>{if(Number.isFinite(b.sma10)){path+=(path?'L':'M')+x(i)+','+y(b.sma10)+' ';}else path='';});
    svg+=`<path d="${path}" fill="none" stroke="#7e9cb4" stroke-width="1.8"/>`;
    bars.forEach((b,i)=>{
      const xx=x(i),bw=Math.max(2,step*.55),valid=[b.open,b.high,b.low,b.close].every(Number.isFinite),color=b.close>=b.open?'#44745a':'#b48270';
      if(valid)svg+=`<line x1="${xx}" x2="${xx}" y1="${y(b.high)}" y2="${y(b.low)}" stroke="${color}"/><rect x="${xx-bw/2}" y="${y(Math.max(b.open,b.close))}" width="${bw}" height="${Math.max(1,Math.abs(y(b.open)-y(b.close)))}" fill="${color}"/><rect x="${xx-bw/2}" y="${volBottom-(b.volume||0)/vol*(volBottom-volTop)}" width="${bw}" height="${(b.volume||0)/vol*(volBottom-volTop)}" fill="${color}" opacity=".5"/>`;
      if(i%Math.ceil(bars.length/7)===0)svg+=`<text x="${xx}" y="443" text-anchor="middle" font-size="11" fill="#76806e">${esc(b.date.slice(2))}</text>`;
    });
    if(p){
      svg+=`<line x1="${left}" x2="${W-right}" y1="${y(p.pivot)}" y2="${y(p.pivot)}" stroke="#ac7c30" stroke-dasharray="6 5"/><text x="${W-right+8}" y="${y(p.pivot)-7}" font-size="11" fill="#956c2c">Pivot</text>`;
      const points=p.pivot_dates.map((date,i)=>{const j=bars.findIndex(b=>b.date===date);return j<0?null:{x:x(j),y:y(i%2?bars[j].low:bars[j].high)};});
      const allVisible=points.every(Boolean);
      if(allVisible)svg+=`<polyline points="${points.map(pt=>pt.x+','+pt.y).join(' ')}" fill="none" stroke="#244e35" stroke-width="2.5"/>`;
      for(let i=0;i<points.length;i+=2){const a=points[i],b=points[i+1];if(a&&b)svg+=`<line x1="${a.x}" x2="${b.x}" y1="${a.y}" y2="${b.y}" stroke="#244e35" stroke-width="3"/><circle cx="${a.x}" cy="${a.y}" r="4" fill="#244e35"/><circle cx="${b.x}" cy="${b.y}" r="4" fill="#244e35"/><text x="${(a.x+b.x)/2}" y="${Math.min(bottom+18,Math.max(a.y,b.y)+20)}" font-size="13" text-anchor="middle" font-weight="bold" fill="#244e35">C${i/2+1} · ${num(p.depths[i/2]*100,1)}%</text>`;}
    }
    svg+='<text x="18" y="359" font-size="11" fill="#76806e">Weekly volume</text>';
    bars.forEach((b,i)=>{svg+=`<rect x="${x(i)-step/2}" y="${top}" width="${step}" height="${volBottom-top}" fill="transparent" tabindex="0" role="button" aria-label="Week ${esc(b.date)}" data-candle="${i}"><title>${esc(b.date)} · O ${num(b.open)} H ${num(b.high)} L ${num(b.low)} C ${num(b.close)}</title></rect>`;});
    $('stock-chart').innerHTML=svg+'</svg>';
    $('candle-readout').textContent=`Weekly candles through ${bars.at(-1).date}. Current incomplete week is excluded.`;
    const inspect=event=>{const el=event.target.closest('[data-candle]');if(!el)return;const b=bars[Number(el.dataset.candle)];$('candle-readout').textContent=`Week ending ${b.date} · Open ${rupee(b.open)} · High ${rupee(b.high)} · Low ${rupee(b.low)} · Close ${rupee(b.close)} · Volume ${num(b.volume,0)}`;};
    $('stock-chart').onclick=inspect;$('stock-chart').onfocusin=inspect;
    $('stock-chart').onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();inspect(e);}};
  }
  function table() {
    visible=filtered(data.rows,mode,$('search').value,$('state').value,$('sector').value);
    $('result-count').textContent=`${visible.length} of 200 stocks shown · ${data.modes[mode]}`;
    $('stock-rows').innerHTML=visible.length?visible.map(r=>`<tr data-symbol="${esc(r.symbol)}"><td><button class="symbol-button" data-symbol="${esc(r.symbol)}">${esc(r.symbol)}</button><span class="company">${esc(r.name)}</span></td><td>${badge(r.modes[mode].state)}</td><td>${rupee(r.close)}<span class="company">${esc(r.data_date||'Missing')}</span></td><td>${num(r.above_low_pct,1)}%</td><td>${num(r.from_high_pct,1)}%</td><td>${r.checks.filter(c=>c.pass).length}/${r.checks.length}</td><td class="reason-cell">${esc(r.modes[mode].reason)}</td></tr>`).join(''):'<tr><td colspan="7">No stocks match these filters.</td></tr>';
  }
  function render() {
    const watch=filtered(data.rows,mode,'','WATCH');
    $('watch-count').textContent=watch.length;$('watch-total').textContent=`${watch.length} active setups`;
    $('mode-note').textContent=mode==='three'?'Requires three confirmed pullbacks, each smaller and no longer than the previous one.':mode==='three_or_two_70'?'The two-pullback exception requires the second depth to be at most 30% of the first: for example, 20% → 6%.':'Exploratory variant from the backtest: the second pullback can be any smaller depth. A historical profit is not proof of an edge.';
    $('setups').innerHTML=watch.length?watch.map(r=>{const s=r.modes[mode],p=s.pattern,v=s.preview;return `<article class="card"><div class="card-top"><h3>${esc(r.symbol)}</h3><span class="tag">${p.count} contractions</span></div><p class="name">${esc(r.name)}</p><p class="strategy">${p.depths.map(n=>num(n*100,1)+'%').join(' → ')}</p><div class="levels"><div><span>BREAKOUT REFERENCE</span><strong>${rupee(v?.trigger)}</strong></div><div><span>STOP AT TRIGGER</span><strong>${rupee(v?.stop_at_trigger)}</strong></div></div><p class="why">${num(v?.distance_pct)}% to trigger · Weekly screen ${esc(r.weekly_date)}</p><button data-symbol="${esc(r.symbol)}">Inspect ${esc(r.symbol)} →</button></article>`;}).join(''):'<div class="empty"><strong>No active setups meet this definition.</strong><p>The full Nifty 200 was checked. Keep the rules intact and wait for a qualifying structure. Use the table below to inspect passed filters, missing conditions and already-triggered patterns.</p></div>';
    table();
    if(!selected) selected=watch[0]||[...data.rows].sort((a,b)=>b.checks.filter(c=>c.pass).length-a.checks.filter(c=>c.pass).length)[0];
    showRow(selected.symbol);
  }
  async function init() {
    const source=document.body.dataset.source||'';
    try {
      const response=await fetch(source+'vcp_scan.json?t='+Date.now(),{cache:'no-store'});
      if(!response.ok)throw new Error('Snapshot HTTP '+response.status);
      data=await response.json();if(!validSnapshot(data))throw new Error('Incomplete or invalid 200-stock snapshot');
      mode=data.default_mode; $('mode').value=mode;
      $('asof').textContent=data.as_of;$('weekly-date').textContent='Weekly screen through '+data.weekly_as_of;
      $('universe-count').textContent=data.rows.length;
      $('coverage').textContent=`${data.complete_count}/200 current · ${data.ready_count}/200 history ready`;
      $('screen-count').textContent=data.rows.filter(r=>r.screen_pass && r.data_ready).length;
      $('notice').textContent=`Daily prices: ${data.as_of}. Weekly screen: ${data.weekly_as_of}. Checking refresh status…`;
      $('json-link').href=source+'vcp_scan.json';
      $('sector').innerHTML='<option value="ALL">All sectors</option>'+[...new Set(data.rows.map(r=>r.sector))].sort().map(s=>`<option value="${esc(s)}">${esc(s)}</option>`).join('');
      $('methodology').innerHTML=data.methodology.map(s=>'<li>'+esc(s)+'</li>').join('');
      for(const id of ['mode','search','state','sector','reset','download'])$(id).disabled=false;
      $('mode').onchange=()=>{mode=$('mode').value;render();};
      $('search').oninput=table;$('state').onchange=table;$('sector').onchange=table;
      $('reset').onclick=()=>{$('search').value='';$('state').value='ALL';$('sector').value='ALL';table();};
      $('chart-window').onchange=chart;
      for(const id of ['setups','stock-rows'])$(id).onclick=e=>{const b=e.target.closest('button[data-symbol]');if(b)showRow(b.dataset.symbol,true);};
      $('download').onclick=()=>{const url=URL.createObjectURL(new Blob([csv(visible,mode)],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`vcp-${mode}-${data.as_of}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
      render();
      try {
        const res=await fetch(source+'vcp_refresh_status.json?t='+Date.now(),{cache:'no-store'});if(!res.ok)throw new Error('Status unavailable');const status=await res.json();
        const same=status.snapshot_run_id===data.refresh_run_id && status.scan_as_of===data.as_of;
        const old=Date.now()-Date.parse(status.attempted_at)>36*3600000;
        const fallback=response.headers.get('X-Swing-Source')==='local-fallback'||res.headers.get('X-Swing-Source')==='local-fallback';
        const okay=status.state==='fresh'&&same&&!old&&!fallback;
        $('notice').className='notice'+(okay?'':' warning');
        $('notice').textContent=`${okay?'Refresh verified':'Refresh needs attention'} · Daily ${data.as_of} · Weekly ${data.weekly_as_of}. ${status.message||''}`+(old?' Last attempt is over 36 hours old.':'')+(!same?' Latest attempt and displayed snapshot differ.':'')+(fallback?' Serving a cached fallback.':'');
        $('refresh-detail').textContent=`Last attempt: ${status.attempted_at}. State: ${status.state}. Snapshot run: ${data.refresh_run_id}. ${data.universe_note||''}`;
      } catch { $('notice').className='notice warning';$('notice').textContent=`Dated snapshot through ${data.as_of}. Latest refresh status could not be verified; this is not an intraday feed.`; }
    } catch(error) {
      $('notice').className='notice error';$('notice').textContent='VCP data could not be loaded: '+error.message+'. Reload to retry.';
      $('setups').innerHTML='<div class="empty"><strong>Scan unavailable</strong><p>Missing data is not the same as zero qualifying setups.</p></div>';
      $('result-count').textContent='Coverage could not be verified.';
    }
  }
  init();
})(typeof window!=='undefined'?window:globalThis);
