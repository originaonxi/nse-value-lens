'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const statuses = ['BUY', 'SELL', 'WATCH', 'CAUTION', 'AVOID'];
  const order = {BUY:0, WATCH:1, CAUTION:2, SELL:3, AVOID:4};
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const numeric = value => typeof value === 'number' && Number.isFinite(value);
  const fmt = (value, digits=2) => numeric(value) ? value.toLocaleString('en-IN', {minimumFractionDigits:digits, maximumFractionDigits:digits}) : '--';
  const money = value => numeric(value) ? '\u20b9' + fmt(value) : '--';
  const date = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '') ? new Date(value + 'T00:00:00Z').toLocaleDateString('en-IN', {day:'numeric', month:'short', year:'numeric', timeZone:'UTC'}) : '--';
  const range = values => Array.isArray(values) && values.every(numeric) ? money(values[0]) + ' - ' + money(values[1]) : '--';
  const stateBadge = state => '<span class="state ' + state + '">' + state + '</span>';
  let dataset = null, status = 'ALL', visible = [], selected = null;

  function validate(data) {
    if (!data || !/^\d{4}-\d{2}-\d{2}$/.test(data.as_of || '') || data.universe_count !== 200 ||
        !Array.isArray(data.rows) || data.rows.length !== 200 ||
        new Set(data.rows.map(r => r.symbol)).size !== 200 || !data.market) throw new Error('Incomplete 200-stock snapshot');
    for (const row of data.rows) {
      if (!statuses.includes(row.status) || row.as_of !== data.as_of || !row.zones || !row.pivots) throw new Error('Invalid stock state');
      if (row.status === 'BUY' && (!row.fresh_breakout || !row.entry_allowed || !data.market.new_entries_allowed)) throw new Error('Invalid buy gate');
    }
    for (const s of statuses) if (data.counts[s] !== data.rows.filter(r => r.status === s).length) throw new Error('Count mismatch');
  }

  function filterRows() {
    const search = $('search').value.trim().toLowerCase();
    visible = dataset.rows.filter(r =>
      (status === 'ALL' || r.status === status) &&
      ($('sector').value === 'ALL' || r.sector === $('sector').value) &&
      ($('structure').value === 'ALL' || r.structure === $('structure').value) &&
      (!search || (r.symbol + ' ' + r.name).toLowerCase().includes(search))
    );
    const distance = r => numeric(r.distance_to_breakout_pct) ? Math.abs(r.distance_to_breakout_pct) : Infinity;
    const sorting = $('sort').value;
    visible.sort((a,b) => {
      if (sorting === 'symbol') return a.symbol.localeCompare(b.symbol);
      if (sorting === 'turnover') return (b.turnover_crore ?? -1) - (a.turnover_crore ?? -1) || a.symbol.localeCompare(b.symbol);
      if (sorting === 'distance') return distance(a) - distance(b) || a.symbol.localeCompare(b.symbol);
      return order[a.status] - order[b.status] || Number(b.fresh_breakout) - Number(a.fresh_breakout) || distance(a) - distance(b) || a.symbol.localeCompare(b.symbol);
    });
    $('result-count').textContent = visible.length + ' of 200 stocks shown \u00b7 ' + (status === 'ALL' ? 'all research states' : status) + ' \u00b7 select a symbol for its zones';
    $('stock-rows').innerHTML = visible.length ? visible.map(r =>
      '<tr data-symbol="' + esc(r.symbol) + '" class="' + (selected === r.symbol ? 'selected' : '') + '"><td><button class="stock-name" type="button" data-symbol="' + esc(r.symbol) + '">' + esc(r.symbol) + '</button><small>' + esc(r.sector) + '</small></td><td>' + stateBadge(r.status) +
      (r.fresh_breakout ? '<small>Fresh breakout</small>' : '') + '</td><td>' + money(r.close) + '<small>' + esc(r.data_date || 'No data') +
      (r.complete_for_session ? '' : ' / stale') + '</small></td><td>' + esc(r.structure) + '</td><td>' + money(r.zones.breakout_above) +
      '</td><td>' + money(r.zones.structure_exit_below) + '</td><td>' + (numeric(r.distance_to_breakout_pct) ? (r.distance_to_breakout_pct > 0 ? '+' : '') + fmt(r.distance_to_breakout_pct) + '%' : '--') +
      '</td><td>' + (numeric(r.atr_pct) ? fmt(r.atr_pct) + '%' : '--') + '</td><td class="reason-cell">' + esc(r.reason) + '</td></tr>'
    ).join('') : '<tr><td colspan="9" class="empty-row">No stocks match these filters.' + (status === 'BUY' && !dataset.market.new_entries_allowed ? ' New buys are blocked by the market/data gate.' : '') + '</td></tr>';
    $('download-csv').disabled = !visible.length;
    if (selected && !visible.some(r => r.symbol === selected)) {
      selected = null;
      $('stock-detail').hidden = true;
    }
  }

  function chart(row) {
    const bars=row.chart||[];
    if(bars.length<2) return '<p class="muted">Not enough complete prices to draw a chart.</p>';
    const w=1100,h=430,left=20,right=100,top=34,bottom=36;
    const levels=[row.zones.breakout_above,row.zones.structure_exit_below].filter(numeric);
    let lo=Math.min(...bars.map(b=>b.low),...levels),hi=Math.max(...bars.map(b=>b.high),...levels);
    const pad=Math.max((hi-lo)*.16,1);lo-=pad;hi+=pad;
    const y=p=>top+(hi-p)/(hi-lo)*(h-top-bottom);
    const step=(w-left-right)/bars.length,x=i=>left+step*(i+.5);
    const indices=new Map(bars.map((b,i)=>[b.date,i]));
    const swings=HHHLChart.points(row);
    const stamp=p=>x(indices.get(p.pivot_date))+','+y(p.price);
    let svg='<svg viewBox="0 0 '+w+' '+h+'" role="img" aria-label="'+esc(row.symbol)+' candles with confirmed HH HL LH LL labels and zigzag through '+esc(row.data_date)+'"><rect width="'+w+'" height="'+h+'" fill="#fff"/>';
    svg+='<rect x="'+(left+step*Math.max(0,bars.length-2))+'" y="'+top+'" width="'+(2*step)+'" height="'+(h-top-bottom)+'" fill="#f5eddb" opacity=".75"><title>These final two candles cannot yet be confirmed swing points.</title></rect>';
    for(let i=0;i<7;i++){
      const price=lo+(hi-lo)*i/6,py=y(price);
      svg+='<line x1="'+left+'" y1="'+py+'" x2="'+(w-right)+'" y2="'+py+'" stroke="#e9eee9" stroke-dasharray="3 5"/><text x="'+(w-right+12)+'" y="'+(py+4)+'" font-size="11" fill="#748078">'+fmt(price)+'</text>';
    }
    if($('chart-levels').checked&&Array.isArray(row.zones.watch_band)){
      const band=row.zones.watch_band;
      svg+='<rect class="chart-zone" x="'+left+'" y="'+y(band[1])+'" width="'+(w-left-right)+'" height="'+Math.max(0,y(band[0])-y(band[1]))+'" fill="#e8eff8" opacity=".7"><title>Watch band: '+esc(range(band))+'; wait for a fresh confirmed breakout.</title></rect>';
    }
    bars.forEach((b,i)=>{
      const c=b.close>=b.open?'#2e8767':'#c56a5b',py=Math.min(y(b.open),y(b.close)),bh=Math.max(1.5,Math.abs(y(b.open)-y(b.close)));
      svg+='<g class="daily-candle"><title>'+esc(b.date)+' | O '+fmt(b.open)+' H '+fmt(b.high)+' L '+fmt(b.low)+' C '+fmt(b.close)+'</title><line x1="'+x(i)+'" y1="'+y(b.high)+'" x2="'+x(i)+'" y2="'+y(b.low)+'" stroke="'+c+'" stroke-width="1.3"/><rect x="'+(x(i)-step*.29)+'" y="'+py+'" width="'+Math.max(1,step*.58)+'" height="'+bh+'" rx=".8" fill="'+c+'"/></g>';
    });
    if($('chart-levels').checked){
      [[row.zones.breakout_above,'BREAKOUT','#3a679b'],[row.zones.structure_exit_below,'STRUCTURE EXIT','#ac594d']].forEach(([price,label,color])=>{
        if(!numeric(price))return;
        svg+='<g class="chart-zone"><line x1="'+left+'" y1="'+y(price)+'" x2="'+(w-right)+'" y2="'+y(price)+'" stroke="'+color+'" stroke-width="1.1" stroke-dasharray="7 5"/><rect x="'+left+'" y="'+(y(price)-19)+'" width="'+(label.length*6.5+82)+'" height="16" rx="3" fill="white" opacity=".92"/><text x="'+(left+5)+'" y="'+(y(price)-7)+'" font-size="10" font-weight="700" fill="'+color+'">'+label+' '+fmt(price)+'</text></g>';
      });
    }
    if($('chart-swings').checked){
      HHHLChart.segments(swings).forEach(segment=>{
        const points=segment.map(stamp).join(' ');
        svg+='<polyline class="structure-zigzag" points="'+points+'" fill="none" stroke="#fff" stroke-width="4.5" stroke-linejoin="round" opacity=".8"/><polyline class="structure-zigzag" points="'+points+'" fill="none" stroke="#526f9a" stroke-width="1.8" stroke-linejoin="round"/>';
      });
      swings.forEach((p,i)=>{
        const px=x(indices.get(p.pivot_date)),py=y(p.price),high=p.kind==='high';
        const color=['HH','HL'].includes(p.label)?'#246f53':['LH','LL'].includes(p.label)?'#a44d44':'#64736b';
        const fill=['HH','HL'].includes(p.label)?'#e7f3ea':['LH','LL'].includes(p.label)?'#f9ebe6':'#eef1ec';
        const ly=high?py-29:py+10;
        const title=p.label+' | '+money(p.price)+' | pivot '+p.pivot_date+' | confirmed '+p.confirmed_on;
        svg+='<g class="swing-marker" role="button" tabindex="0" data-pivot="'+i+'" aria-label="'+esc(title)+'"><title>'+esc(title)+'</title><circle cx="'+px+'" cy="'+py+'" r="3.1" fill="white" stroke="'+color+'" stroke-width="1.8"/><line x1="'+px+'" y1="'+(high?py-4:py+4)+'" x2="'+px+'" y2="'+(high?ly+19:ly)+'" stroke="'+color+'" opacity=".45"/><rect x="'+(px-17)+'" y="'+ly+'" width="34" height="19" rx="5" fill="'+fill+'" stroke="'+color+'" stroke-opacity=".25"/><text x="'+px+'" y="'+(ly+13)+'" text-anchor="middle" font-size="11" font-weight="800" fill="'+color+'">'+p.label+'</text></g>';
      });
    }
    const last=bars.at(-1),lastY=y(last.close);
    svg+='<line x1="'+x(bars.length-1)+'" y1="'+lastY+'" x2="'+(w-right+5)+'" y2="'+lastY+'" stroke="#293e34" stroke-dasharray="2 3"/><rect x="'+(w-right+5)+'" y="'+(lastY-10)+'" width="89" height="20" rx="4" fill="#293e34"/><text x="'+(w-right+49)+'" y="'+(lastY+4)+'" text-anchor="middle" font-size="11" fill="white">'+fmt(last.close)+'</text>';
    [0,Math.floor((bars.length-1)/3),Math.floor(2*(bars.length-1)/3),bars.length-1].forEach((i,n)=>{
      svg+='<text x="'+x(i)+'" y="'+(h-10)+'" text-anchor="'+(n===0?'start':n===3?'end':'middle')+'" fill="#748078" font-size="10">'+esc(bars[i].date)+'</text>';
    });
    return svg+'</svg>';
  }

  function renderChart(row) {
    $('stock-chart').innerHTML=chart(row);
    const bars=row.chart||[],previous=bars.at(-2)?.close,last=bars.at(-1)?.close;
    const change=previous?100*(last/previous-1):null;
    $('chart-price').textContent=money(last)+(numeric(change)?'  '+(change>=0?'+':'')+fmt(change)+'%':'')+' / '+row.data_date;
    $('chart-inspect').textContent='Tap a swing label for its price, pivot date and confirmation date.';
  }

  function inspectSwing(event) {
    const marker=event.target.closest('[data-pivot]');
    if(!marker||!selected)return;
    if(event.type==='keydown'&&!['Enter',' '].includes(event.key))return;
    if(event.type==='keydown')event.preventDefault();
    const row=dataset.rows.find(r=>r.symbol===selected),point=HHHLChart.points(row)[Number(marker.dataset.pivot)];
    if(!point)return;
    const names={HH:'Higher high',HL:'Higher low',LH:'Lower high',LL:'Lower low',EH:'Equal high',EL:'Equal low',H:'Swing high',L:'Swing low'};
    $('chart-inspect').textContent=point.label+' / '+names[point.label]+' / '+money(point.price)+' / Pivot: '+date(point.pivot_date)+' / Confirmed: '+date(point.confirmed_on)+'. This point was not known on its original candle.';
    document.querySelectorAll('.swing-marker').forEach(el=>el.classList.toggle('selected-pivot',el===marker));
  }

  function showDetail(symbol, options={scroll:true}) {
    const r = dataset.rows.find(row => row.symbol === symbol);
    if (!r) return;
    selected = symbol;
    $('stock-detail').hidden = false;
    $('detail-title').textContent = r.symbol + ' / ' + r.name;
    $('detail-subtitle').textContent = r.sector + ' \u00b7 prices through ' + date(r.data_date) + ' \u00b7 ' + r.structure;
    $('detail-badge').className = 'state ' + r.status;
    $('detail-badge').textContent = r.status;
    $('detail-reason').textContent = r.reason;
    renderChart(r);
    const z=r.zones, p=r.entry_plan;
    const item=(title,value,note,classes='')=>'<div class="zone-item '+classes+'"><span>'+esc(title)+'</span><strong>'+esc(value)+'</strong><small>'+esc(note)+'</small></div>';
    let zones=item('BREAKOUT REFERENCE',money(z.breakout_above),'A close above this level needs rising structure and a fresh cross.')+
      item('STRUCTURE EXIT BELOW',money(z.structure_exit_below),'Closing below this low triggers a next-open exit for an existing long.')+
      item('WATCH BAND',range(z.watch_band),'One ATR below the high, bounded by support. A reference zone, not an entry.')+
      item('INITIAL STOP DISTANCE',money(z.stop_distance),'Subtract from the actual entry. No fixed profit target; maximum 10 sessions.');
    if(p) zones+=item(p.eligible?'NEXT-OPEN PAPER ENTRY BAND':'CONDITIONAL OPENING BAND / BLOCKED',range(p.opening_price_band),p.timing,'full '+(p.eligible?'':'blocked'))+
      '<div class="zone-item full"><span>STOP & EXIT PLAN</span><p>'+esc(p.stop_formula)+'. '+esc(p.exit)+'</p></div>';
    else zones+='<div class="zone-item full"><span>ENTRY PLAN</span><p>No fresh eligible entry is available. A new closing breakout must occur before an opening band can be set.</p></div>';
    if(!r.complete_for_session) zones='<div class="zone-item full blocked"><span>INCOMPLETE SESSION</span><p>Zones are withheld because there is no complete '+esc(dataset.as_of)+' candle. Last available close: '+money(r.close)+' on '+esc(r.data_date)+'.</p></div>';
    $('zone-panel').innerHTML=zones;
    const pivots=kind=>'<div><b>Last two confirmed '+kind+'s</b><ul>'+r.pivots[kind].map(p=>'<li>'+money(p.price)+' \u00b7 pivot '+esc(p.pivot_date)+' \u00b7 known from '+esc(p.confirmed_on)+'</li>').join('')+'</ul></div>';
    $('pivot-detail').innerHTML='<div class="pivot-grid">'+pivots('high')+pivots('low')+'</div><p>ATR14: '+money(r.atr)+' \u00b7 average daily traded value: '+fmt(r.turnover_crore)+' crore \u00b7 last structure breakout: '+esc(r.last_breakout_date || 'none in available history')+'</p><p>'+esc(r.data_source)+'</p>'+
      r.data_warnings.map(w=>'<p class="caution-text">'+esc(w)+'</p>').join('');
    document.querySelectorAll('#stock-rows tr[data-symbol]').forEach(tr=>tr.classList.toggle('selected',tr.dataset.symbol===symbol));
    if(options.scroll){$('stock-detail').scrollIntoView({behavior:'auto',block:'start'});$('detail-title').focus({preventScroll:true});}
  }

  function exportCsv() {
    const columns=['Symbol','Company','Sector','State','Snapshot date','Price date','Close INR','Structure','Breakout above INR','Structure exit below INR','Watch band low INR','Watch band high INR','Opening band low INR','Opening band high INR','Entry allowed','ATR INR','ATR percent','Turnover crore','Reason'];
    const cell=v=>{
      let text=v==null?'':String(v);
      if(typeof v==='string' && /^[=+@\-]/.test(text)) text="'"+text;
      return '"'+text.replace(/"/g,'""')+'"';
    };
    const rows=visible.map(r=>[r.symbol,r.name,r.sector,r.status,r.as_of,r.data_date,r.close,r.structure,r.zones.breakout_above,r.zones.structure_exit_below,
      r.zones.watch_band?.[0],r.zones.watch_band?.[1],r.entry_plan?.opening_price_band?.[0],r.entry_plan?.opening_price_band?.[1],r.entry_allowed,r.atr,r.atr_pct,r.turnover_crore,r.reason]);
    const blob=new Blob(['\uFEFF'+[columns,...rows].map(row=>row.map(cell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8;'});
    const url=URL.createObjectURL(blob), a=document.createElement('a');a.href=url;a.download='nifty200-hhhl-'+dataset.as_of+'-'+status.toLowerCase()+'.csv';
    document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }

  function renderSummary() {
    $('session-date').textContent=date(dataset.as_of);
    $('coverage').textContent=dataset.universe_count+' listed \u00b7 '+dataset.complete_count+' complete session candles';
    for(const s of ['ALL',...statuses]) $('count-'+s).textContent=s==='ALL'?dataset.universe_count:dataset.counts[s];
    const m=dataset.market;
    $('nifty-close').textContent=money(m.close);
    $('nifty-average').textContent=money(m.sma200 ?? m.average_200_available_bars);
    $('average-label').textContent=m.data_ready?'200-SESSION AVERAGE':'200 AVAILABLE BARS / REFERENCE';
    $('market-gate').textContent=m.new_entries_allowed?'ON / PAPER ENTRIES':'BLOCKED';
    $('market-gate').className=m.new_entries_allowed?'buy-text':'caution-text';
    $('market-note').textContent=(m.reference_filter_passed?'Nifty is above':'Nifty is below')+' the available-history average.'+
      (m.missing_sessions.length?' Benchmark session(s) missing: '+m.missing_sessions.join(', ')+'. The exact 200-session gate is incomplete.':'')+
      ' Stock structure remains visible; this gate controls new entries.';
    $('notice').textContent='Snapshot for '+date(dataset.as_of)+'. '+(m.new_entries_allowed?'Buy labels are conditional next-session paper setups.':'No new BUY entries pass the market/data gate.')+
      ' Sell means an exit condition for existing long holdings. '+(dataset.universe_count-dataset.complete_count)+' stock(s) have incomplete session prices.';
    const previousSector=$('sector').value;
    const sectors=[...new Set(dataset.rows.map(r=>r.sector))].sort();
    $('sector').innerHTML='<option value="ALL">All sectors</option>'+sectors.map(s=>'<option value="'+esc(s)+'">'+esc(s)+'</option>').join('');
    if(sectors.includes(previousSector)) $('sector').value=previousSector;
    $('data-audit').innerHTML='<p>'+esc(dataset.data_audit.price_source)+'</p><p>'+esc(dataset.data_audit.latest_recheck)+'</p><p>'+esc(dataset.data_audit.universe_source)+'</p><ul>'+dataset.limitations.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>';
    document.querySelectorAll('.filters input,.filters select,.filters button').forEach(el=>el.disabled=false);
    $('download-json').href=(document.body.dataset.source || '')+'hhhl_scan.json';
    filterRows();
  }

  document.querySelectorAll('.status-card').forEach(button=>button.addEventListener('click',()=>{
    if(!dataset) return;
    status=button.dataset.status;
    document.querySelectorAll('.status-card').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',b===button?'true':'false');});
    filterRows();
  }));
  $('search').addEventListener('input',()=>dataset&&filterRows());
  ['sector','structure','sort'].forEach(id=>$(id).addEventListener('change',()=>dataset&&filterRows()));
  $('reset').addEventListener('click',()=>{
    $('search').value='';$('sector').value='ALL';$('structure').value='ALL';$('sort').value='status';
    document.querySelector('[data-status="ALL"]').click();
  });
  $('stock-rows').addEventListener('click',event=>{const button=event.target.closest('button[data-symbol]');if(button) showDetail(button.dataset.symbol);});
  $('download-csv').addEventListener('click',exportCsv);
  for(const id of ['chart-swings','chart-levels']) $(id).addEventListener('change',()=>{
    if(selected)renderChart(dataset.rows.find(r=>r.symbol===selected));
  });
  $('stock-chart').addEventListener('click',inspectSwing);
  $('stock-chart').addEventListener('keydown',inspectSwing);
  function loadRefreshStatus() {
    const el=$('refresh-status');
    fetch((document.body.dataset.source || '')+'hhhl_refresh_status.json',{cache:'no-store'}).then(async response=>{
      if(!response.ok) throw new Error('Refresh status unavailable');
      const status=await response.json();
      if(!status.run_id || !status.attempted_at) throw new Error('Invalid refresh status');
      const age=Date.now()-Date.parse(status.attempted_at), overdue=!Number.isFinite(age)||age>27*60*60*1000;
      const fallback=response.headers.get('X-Swing-Source')==='local-fallback';
      const matching=dataset && dataset.generated_at===status.snapshot_generated_at;
      const label=overdue?'REFRESH OVERDUE':!matching?'PUBLICATION UPDATING':status.state.toUpperCase();
      el.dataset.runId=status.run_id;
      el.className='notice '+(status.state==='fresh'&&!overdue&&matching&&!fallback?'':'warning');
      el.textContent=label+' | Automatic checks start at 4:00 pm IST, with later retries. Last attempt: '+
        new Date(status.attempted_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})+' IST. Target session: '+
        status.target_session+'. '+status.message+(fallback?' Cached fallback is being served.':'')+
        (overdue?' The scheduled refresh may have stopped; check Actions.':'');
      const link=document.createElement('a');
      link.href='https://github.com/originaonxi/nse-value-lens/actions/workflows/hhhl_daily.yml';
      link.textContent=' View refresh runs';el.appendChild(link);
    }).catch(()=>{el.className='notice warning';el.textContent='Automatic refresh status unavailable. Check the scan date before using these levels.';});
  }
  function loadSnapshot() {
  fetch((document.body.dataset.source || '')+'hhhl_scan.json',{cache:'no-store'}).then(response=>{
    if(!response.ok) throw new Error('HTTP '+response.status);
    return response.json();
  }).then(data=>{validate(data);dataset=data;renderSummary();if(selected)showDetail(selected,{scroll:false});loadRefreshStatus();}).catch(()=>{
    dataset=null;$('notice').textContent='The HH/HL snapshot could not be loaded or did not contain 200 valid stock rows. No signals are displayed.';
    $('session-date').textContent='Unavailable';$('coverage').textContent='Data check failed';$('result-count').textContent='No verified rows to display.';
    $('stock-rows').innerHTML='';$('stock-detail').hidden=true;
    for(const s of ['ALL',...statuses]) $('count-'+s).textContent='--';
  });
  }
  loadSnapshot();
  setInterval(()=>{if(document.visibilityState==='visible') loadSnapshot();},300000);
})();
