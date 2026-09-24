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

  function viewedRow(row) {return HHHLChart.windowRow(row,Number($('chart-window').value)||70);}

  function chart(source) {
    const row=viewedRow(source),bars=row.chart||[];
    if(bars.length<2)return '<p class="muted">Not enough complete prices to draw a chart.</p>';
    const showVolume=$('chart-volume').checked&&bars.some(b=>numeric(b.volume));
    const w=1200,h=showVolume?580:465,left=20,right=122,future=96,top=36,priceBottom=403,plotRight=w-right-future,axis=w-right;
    const plan=row.entry_plan;
    const levels=[row.zones.breakout_above,row.zones.structure_exit_below,...(plan?.opening_price_band||[]),plan?.stop_at_signal_close_reference].filter(numeric);
    let lo=Math.min(...bars.map(b=>b.low),...levels),hi=Math.max(...bars.map(b=>b.high),...levels);
    const pad=Math.max((hi-lo)*.16,1);lo-=pad;hi+=pad;
    const y=p=>top+(hi-p)/(hi-lo)*(priceBottom-top);
    const step=(plotRight-left)/bars.length,x=i=>left+step*(i+.5),indices=new Map(bars.map((b,i)=>[b.date,i]));
    const swings=HHHLChart.points(row),active=HHHLChart.activePoints(row),activeKeys=new Map(active.map(p=>[p.kind+':'+p.pivot_date,p.sequence]));
    const startX=day=>{if(!day||day>row.data_date)return null;const i=bars.findIndex(b=>b.date>=day);return i<0?null:x(i);};
    const stamp=p=>x(indices.get(p.pivot_date))+','+y(p.price);
    let svg='<svg viewBox="0 0 '+w+' '+h+'" data-width="'+w+'" data-left="'+left+'" data-step="'+step+'" role="group" aria-label="'+esc(row.symbol)+' daily strategy chart"><rect width="'+w+'" height="'+h+'" fill="white"/>';
    svg+='<rect x="'+plotRight+'" y="'+top+'" width="'+future+'" height="'+(priceBottom-top)+'" fill="#f3f6f2"/><text x="'+(plotRight+future/2)+'" y="21" text-anchor="middle" font-size="10" fill="#68796e">NEXT OPEN</text>';
    svg+='<rect x="'+(left+step*Math.max(0,bars.length-2))+'" y="'+top+'" width="'+(2*step)+'" height="'+(priceBottom-top)+'" fill="#fbf3df" opacity=".6"><title>New pivots on these final two bars are not yet confirmed.</title></rect>';
    for(let i=0;i<7;i++){
      const price=lo+(hi-lo)*i/6,py=y(price);
      svg+='<line x1="'+left+'" y1="'+py+'" x2="'+axis+'" y2="'+py+'" stroke="#e9eeea" stroke-dasharray="3 5"/><text x="'+(axis+10)+'" y="'+(py+4)+'" font-size="11" fill="#758176">'+fmt(price)+'</text>';
    }
    if($('chart-levels').checked&&Array.isArray(row.zones.watch_band)&&!plan){
      const band=row.zones.watch_band;
      svg+='<rect class="chart-zone" x="'+x(bars.length-1)+'" y="'+y(band[1])+'" width="'+(axis-x(bars.length-1))+'" height="'+Math.max(0,y(band[0])-y(band[1]))+'" fill="#dce9f5" opacity=".65"><title>Current watch band '+esc(range(band))+'; this band is not an entry.</title></rect>';
    }
    bars.forEach((b,i)=>{
      const c=b.close>=b.open?'#2b8666':'#c26859',py=Math.min(y(b.open),y(b.close));
      svg+='<g class="daily-candle" data-bar="'+i+'"><title>'+esc(b.date)+' | O '+fmt(b.open)+' H '+fmt(b.high)+' L '+fmt(b.low)+' C '+fmt(b.close)+'</title><line x1="'+x(i)+'" y1="'+y(b.high)+'" x2="'+x(i)+'" y2="'+y(b.low)+'" stroke="'+c+'" stroke-width="1.25"/><rect x="'+(x(i)-step*.29)+'" y="'+py+'" width="'+Math.max(1,step*.58)+'" height="'+Math.max(1.5,Math.abs(y(b.open)-y(b.close)))+'" rx=".7" fill="'+c+'"/></g>';
    });
    if($('chart-swings').checked){
      HHHLChart.segments(swings).forEach(segment=>{
        svg+='<polyline class="structure-zigzag" points="'+segment.map(stamp).join(' ')+'" fill="none" stroke="#788ba4" stroke-width="1.5" stroke-linejoin="round" opacity=".42"/>';
      });
      for(const kind of ['high','low']){
        const pair=active.filter(p=>p.kind===kind);
        if(pair.length===2)svg+='<polyline class="active-sequence" points="'+pair.map(stamp).join(' ')+'" fill="none" stroke="'+(pair[1].price>pair[0].price?'#287b5a':'#aa5249')+'" stroke-width="2.2" stroke-dasharray="5 4"/>';
      }
      swings.forEach((p,i)=>{
        const sequence=activeKeys.get(p.kind+':'+p.pivot_date);
        if(!sequence&&!$('chart-all-pivots').checked)return;
        const px=x(indices.get(p.pivot_date)),py=y(p.price),high=p.kind==='high';
        const color=['HH','HL'].includes(p.label)?'#246f53':['LH','LL'].includes(p.label)?'#a44d44':'#64736b';
        const fill=['HH','HL'].includes(p.label)?'#e7f3ea':['LH','LL'].includes(p.label)?'#f9ebe6':'#eef1ec';
        const label=sequence?sequence+' / '+p.label:p.label,width=sequence?64:34,ly=high?py-32:py+12;
        const title=label+' | '+money(p.price)+' | pivot '+p.pivot_date+' | confirmed '+p.confirmed_on;
        svg+='<g class="swing-marker '+(sequence?'active-pivot':'')+'" role="button" tabindex="0" data-pivot="'+i+'" aria-label="'+esc(title)+'"><title>'+esc(title)+'</title><circle cx="'+px+'" cy="'+py+'" r="'+(sequence?4.4:2.8)+'" fill="white" stroke="'+color+'" stroke-width="'+(sequence?2.3:1.4)+'"/><line x1="'+px+'" y1="'+(high?py-5:py+5)+'" x2="'+px+'" y2="'+(high?ly+20:ly)+'" stroke="'+color+'" opacity=".5"/><rect x="'+(px-width/2)+'" y="'+ly+'" width="'+width+'" height="20" rx="5" fill="'+fill+'" stroke="'+color+'" stroke-opacity=".4"/><text x="'+px+'" y="'+(ly+14)+'" text-anchor="middle" font-size="11" font-weight="800" fill="'+color+'">'+label+'</text></g>';
      });
    }
    if($('chart-levels').checked){
      [[row.zones.breakout_above,'high','CLOSING TRIGGER','#376b9f'],[row.zones.structure_exit_below,'low','STRUCTURE EXIT','#ac594d']].forEach(([price,kind,label,color])=>{
        const known=HHHLChart.levelStart(row,kind),sx=startX(known);
        if(!numeric(price)||sx==null)return;
        svg+='<g class="chart-zone confirmed-level" data-known-from="'+esc(known)+'" data-start-date="'+esc(bars.find(b=>b.date>=known)?.date||bars[0].date)+'"><title>'+label+' '+fmt(price)+'; first known '+esc(known)+'</title><line x1="'+sx+'" y1="'+y(price)+'" x2="'+axis+'" y2="'+y(price)+'" stroke="'+color+'" stroke-width="1.6" stroke-dasharray="7 4"/><circle cx="'+sx+'" cy="'+y(price)+'" r="3" fill="'+color+'"/></g>';
      });
      if(plan&&Array.isArray(plan.opening_price_band)){
        const [lower,upper]=plan.opening_price_band,stop=plan.stop_at_signal_close_reference,c=plan.eligible?'#287b5a':'#9a702b';
        svg+='<g class="chart-zone execution-overlay" data-eligible="'+Boolean(plan.eligible)+'"><rect x="'+(plotRight+4)+'" y="'+y(upper)+'" width="'+(future-8)+'" height="'+Math.max(1,y(lower)-y(upper))+'" fill="'+(plan.eligible?'#d9efe2':'#f2e6c9')+'" stroke="'+c+'" stroke-dasharray="4 3"/><title>Next-open band '+esc(range(plan.opening_price_band))+'; '+(plan.eligible?'conditional paper entry':'entry blocked by the rule')+'</title><text x="'+(plotRight+future/2)+'" y="'+(y(upper)-9)+'" text-anchor="middle" font-size="10" font-weight="700" fill="'+c+'">'+(plan.eligible?'ENTRY BAND':'BLOCKED')+'</text>';
        if(numeric(stop))svg+='<line x1="'+plotRight+'" y1="'+y(stop)+'" x2="'+axis+'" y2="'+y(stop)+'" stroke="#b76558" stroke-width="1.5" stroke-dasharray="4 3"/><text x="'+(plotRight+future/2)+'" y="'+(y(stop)+15)+'" text-anchor="middle" font-size="9" fill="#a35045">STOP REF '+fmt(stop)+'</text><title>Stop reference assumes entry at the signal close. Actual stop is actual fill minus 2 ATR.</title>';
        svg+='</g>';
      }
    }
    if($('chart-events').checked){
      bars.forEach((b,i)=>{
        const up=b.structure_breakout,down=b.structure_exit;
        if(!up&&!down)return;
        const py=up?y(b.low)+9:y(b.high)-9,px=x(i),color=up?'#30769e':'#ad5b4f';
        const shape=up?px+','+py+' '+(px-5)+','+(py+9)+' '+(px+5)+','+(py+9):px+','+py+' '+(px-5)+','+(py-9)+' '+(px+5)+','+(py-9);
        svg+='<g class="structure-event" tabindex="0" role="button" data-event="'+i+'" aria-label="'+esc(b.date)+' '+(up?'HH HL closing breakout':'structure exit trigger')+'"><title>'+esc(b.date)+' | '+(up?'HH/HL closing breakout':'Close below confirmed low')+' | structural event, not an executed trade</title><polygon points="'+shape+'" fill="'+color+'"/></g>';
      });
    }
    const last=bars.at(-1),lastY=y(last.close);
    svg+='<line x1="'+x(bars.length-1)+'" y1="'+lastY+'" x2="'+axis+'" y2="'+lastY+'" stroke="#293e34" stroke-dasharray="2 3"/>';
    const tags=[{price:last.close,label:'CLOSE',color:'#293e34',last:true}];
    if($('chart-levels').checked){
      if(numeric(row.zones.breakout_above))tags.push({price:row.zones.breakout_above,label:'CLOSING TRIGGER',color:'#376b9f'});
      if(numeric(row.zones.structure_exit_below))tags.push({price:row.zones.structure_exit_below,label:'STRUCTURE EXIT',color:'#ac594d'});
    }
    tags.sort((a,b)=>y(a.price)-y(b.price));
    tags.forEach((tag,i)=>{tag.py=Math.max(top+16,y(tag.price),i?tags[i-1].py+36:0);});
    const overflow=Math.max(0,tags.at(-1).py-(priceBottom-17));
    tags.forEach(tag=>{
      const py=tag.py-overflow,bg=tag.last?tag.color:'white',fg=tag.last?'white':tag.color;
      svg+='<g class="'+(tag.last?'last-price-label':'chart-zone price-level-label')+'"><path d="M '+axis+' '+y(tag.price)+' L '+(axis+7)+' '+py+'" fill="none" stroke="'+tag.color+'" stroke-width="1"/><rect x="'+(axis+7)+'" y="'+(py-16)+'" width="109" height="32" rx="4" fill="'+bg+'" stroke="'+tag.color+'" stroke-width=".8"/><text x="'+(axis+61)+'" y="'+(py-4)+'" text-anchor="middle" font-size="8" font-weight="700" fill="'+fg+'">'+tag.label+'</text><text x="'+(axis+61)+'" y="'+(py+10)+'" text-anchor="middle" font-size="11" font-weight="700" fill="'+fg+'">'+fmt(tag.price)+'</text></g>';
    });
    if(showVolume){
      const vTop=443,vBottom=539,maxVolume=Math.max(...bars.map(b=>Math.max(b.volume||0,b.volume_average20||0)),1);
      const vy=v=>vBottom-(v/maxVolume)*(vBottom-vTop);
      svg+='<line x1="'+left+'" y1="425" x2="'+axis+'" y2="425" stroke="#dce5dd"/><text x="'+left+'" y="438" font-size="10" fill="#728176">VOLUME / PREVIOUS 20-SESSION AVERAGE</text>';
      const avg=[];
      bars.forEach((b,i)=>{
        svg+='<rect class="volume-bar" x="'+(x(i)-step*.29)+'" y="'+vy(b.volume||0)+'" width="'+Math.max(1,step*.58)+'" height="'+(vBottom-vy(b.volume||0))+'" fill="'+(b.close>=b.open?'#93bba9':'#d5a297')+'"/>';
        if(numeric(b.volume_average20))avg.push(x(i)+','+vy(b.volume_average20));
      });
      if(avg.length)svg+='<polyline class="volume-average" points="'+avg.join(' ')+'" fill="none" stroke="#65779b" stroke-width="1.6"/>';
    }
    svg+='<line id="chart-crosshair" x1="'+x(bars.length-1)+'" x2="'+x(bars.length-1)+'" y1="'+top+'" y2="'+(showVolume?539:priceBottom)+'" stroke="#758579" stroke-dasharray="3 4" opacity="0"/>';
    [0,Math.floor((bars.length-1)/3),Math.floor(2*(bars.length-1)/3),bars.length-1].forEach((i,n)=>{
      svg+='<text x="'+x(i)+'" y="'+(h-12)+'" text-anchor="'+(n===0?'start':n===3?'end':'middle')+'" fill="#748078" font-size="10">'+esc(bars[i].date)+'</text>';
    });
    return svg+'</svg>';
  }

  function candleReadout(row,index) {
    const bar=viewedRow(row).chart[index];
    if(!bar)return;
    $('candle-readout').textContent=bar.date+'   O '+money(bar.open)+'   H '+money(bar.high)+'   L '+money(bar.low)+'   C '+money(bar.close)+'   Vol '+(numeric(bar.volume)?fmt(bar.volume,0):'--');
  }

  function renderChart(row) {
    $('stock-chart').innerHTML=chart(row);
    const bars=viewedRow(row).chart||[],previous=bars.at(-2)?.close,last=bars.at(-1)?.close;
    const change=previous?100*(last/previous-1):null;
    $('chart-price').textContent=money(last)+(numeric(change)?'  '+(change>=0?'+':'')+fmt(change)+'%':'')+' / '+row.data_date;
    candleReadout(row,bars.length-1);
    $('chart-inspect').textContent='Active pivots: H1/H2 are the last two highs; L1/L2 are the last two lows. Tap a label or closing-signal triangle for its dates.';
  }

  function inspectSwing(event) {
    if(!selected)return;
    if(event.type==='keydown'&&!['Enter',' '].includes(event.key))return;
    const marker=event.target.closest('[data-pivot], [data-event]');
    if(!marker)return;
    if(event.type==='keydown')event.preventDefault();
    const row=viewedRow(dataset.rows.find(r=>r.symbol===selected));
    if(marker.hasAttribute('data-event')){
      const bar=row.chart[Number(marker.dataset.event)];
      $('chart-inspect').textContent=bar.date+' / '+(bar.structure_breakout?'HH/HL closing breakout over '+money(bar.confirmed_high):'Structure exit: close below '+money(bar.confirmed_low))+'. This is a historical structure event, not a trade fill or proof that all entry gates passed.';
      return;
    }
    const point=HHHLChart.points(row)[Number(marker.dataset.pivot)];
    if(!point)return;
    const names={HH:'Higher high',HL:'Higher low',LH:'Lower high',LL:'Lower low',EH:'Equal high',EL:'Equal low',H:'Swing high',L:'Swing low'};
    $('chart-inspect').textContent=point.label+' / '+names[point.label]+' / '+money(point.price)+' / Pivot: '+date(point.pivot_date)+' / Confirmed: '+date(point.confirmed_on)+'. This point became usable on its confirmation date.';
    document.querySelectorAll('.swing-marker').forEach(el=>el.classList.toggle('selected-pivot',el===marker));
  }

  function inspectCandle(event) {
    if(!selected)return;
    const svg=$('stock-chart').querySelector('svg');
    if(!svg)return;
    const row=dataset.rows.find(r=>r.symbol===selected),bars=viewedRow(row).chart;
    const rect=svg.getBoundingClientRect(),px=(event.clientX-rect.left)*Number(svg.dataset.width)/rect.width;
    const index=Math.min(bars.length-1,Math.max(0,Math.floor((px-Number(svg.dataset.left))/Number(svg.dataset.step))));
    candleReadout(row,index);
    const hair=$('chart-crosshair'),x=Number(svg.dataset.left)+(index+.5)*Number(svg.dataset.step);
    hair.setAttribute('x1',x);hair.setAttribute('x2',x);hair.setAttribute('opacity','.65');
  }

  function renderPriority() {
    let picks=dataset.priority_watchlist;
    if(!Array.isArray(picks)){
      const pool=dataset.rows.filter(r=>r.complete_for_session&&r.structure==='HH / HL'&&numeric(r.zones.breakout_above)&&['BUY','WATCH','CAUTION'].includes(r.status));
      const tier=r=>r.status==='BUY'?0:r.fresh_breakout?1:r.status==='WATCH'?2:3;
      pool.sort((a,b)=>tier(a)-tier(b)||Math.abs(a.close-a.zones.breakout_above)/a.atr-Math.abs(b.close-b.zones.breakout_above)/b.atr||a.symbol.localeCompare(b.symbol));
      picks=pool.slice(0,10).map((r,i)=>({rank:i+1,symbol:r.symbol,status:r.status,distance_atr:Math.abs(r.close-r.zones.breakout_above)/r.atr,reason:r.reason}));
    }
    $('priority-title').textContent=picks.length+' strongest HH/HL setups to review';
    $('priority-summary').textContent=dataset.counts.BUY+' eligible fresh entries / '+date(dataset.as_of);
    $('priority-method').textContent=(dataset.priority_method||'Eligible breakouts, blocked fresh breakouts, then waiting structures nearest their trigger in ATR units.')+
      (dataset.market.new_entries_allowed?'':' Nifty/data gate is OFF: a high rank does not permit a new entry.');
    $('priority-list').innerHTML=picks.length?picks.map(p=>{
      const row=dataset.rows.find(r=>r.symbol===p.symbol);
      return '<button type="button" class="priority-card '+(selected===p.symbol?'selected':'')+'" data-symbol="'+esc(p.symbol)+'"><span class="priority-top"><span class="priority-rank">'+p.rank+'</span>'+stateBadge(row.status)+'</span><strong>'+esc(p.symbol)+'</strong><span class="priority-price">'+money(row.close)+'</span><span class="priority-trigger">Trigger '+money(row.zones.breakout_above)+' / '+fmt(p.distance_atr)+' ATR away</span><small>'+esc(p.reason)+'</small></button>';
    }).join(''):'<p>No complete HH/HL setups pass the stock-level screens. The full universe remains available below.</p>';
    return picks;
  }

  function selectPriority(symbol) {
    $('search').value='';$('sector').value='ALL';$('structure').value='ALL';status='ALL';
    document.querySelectorAll('.status-card').forEach(b=>{b.classList.toggle('active',b.dataset.status==='ALL');b.setAttribute('aria-pressed',b.dataset.status==='ALL'?'true':'false');});
    filterRows();showDetail(symbol);
  }

  function renderStrategy(row) {
    const latest=row.chart?.at(-1),trigger=row.zones.breakout_above;
    let stage=row.status==='SELL'?'Structure exit condition is active':row.fresh_breakout?'Fresh HH/HL closing breakout':row.structure==='HH / HL'?'Rising structure; waiting for a fresh closing breakout':'The HH/HL setup is incomplete';
    if(row.structure==='HH / HL'&&!row.fresh_breakout&&numeric(trigger)&&latest?.high>trigger&&latest?.close<=trigger)stage='Wick crossed resistance; the close did not confirm a breakout';
    if(row.structure==='HH / HL'&&!row.fresh_breakout&&row.close>trigger)stage='Price is already above the trigger; no fresh entry today';
    $('strategy-story').className='strategy-story '+(row.entry_allowed?'eligible':'blocked');
    $('strategy-story').innerHTML='<strong>'+esc(stage)+'</strong><span>'+esc(row.entry_allowed?'Closing checks pass. Consider only the next open inside the entry band, subject to risk limits.':'No new entry is eligible under the current rule. '+row.reason)+'</span>';
    const pair=kind=>{
      const p=row.pivots[kind]||[],prefix=kind==='high'?'H':'L';
      if(p.length<2)return '<div class="pivot-pair"><span>'+esc(kind.toUpperCase())+'</span><strong>Two confirmed pivots required</strong></div>';
      const rising=p[1].price>p[0].price;
      return '<div class="pivot-pair"><span>'+esc(kind==='high'?'HIGHER HIGHS':'HIGHER LOWS')+' / '+(rising?'PASS':'NOT PRESENT')+'</span><div class="'+(rising?'pair-pass':'pair-fail')+'"><b>'+prefix+'1 '+money(p[0].price)+'</b><span> &rarr; </span><b>'+prefix+'2 '+money(p[1].price)+'</b></div><small>'+date(p[0].pivot_date)+' &rarr; '+date(p[1].pivot_date)+' / latest confirmed '+date(p[1].confirmed_on)+'</small></div>';
    };
    $('active-pivot-pairs').innerHTML=pair('high')+pair('low');
    $('checks-note').textContent=row.entry_allowed?'Closing-signal checks pass; the next opening price, actual fill and allocation limits still need checking.':'Blocked or waiting checks explain why this is not an eligible entry. Volume bars are context; no volume-expansion rule has been added.';
    const checks=row.entry_checks||[];
    $('strategy-checks').innerHTML=checks.length?checks.map(c=>'<div class="strategy-check '+esc(c.state)+'"><span>'+esc(c.state==='pass'?'PASS':c.state==='wait'?'WAIT':'BLOCKED')+'</span><strong>'+esc(c.label)+'</strong><small>'+esc(c.detail)+'</small></div>').join(''):'<p>Detailed strategy checks will appear after the next data refresh.</p>';
    document.querySelectorAll('.priority-card').forEach(card=>card.classList.toggle('selected',card.dataset.symbol===row.symbol));
  }

  function showDetail(symbol, options={scroll:true}) {
    const r = dataset.rows.find(row => row.symbol === symbol);
    if (!r) return;
    selected = symbol;
    window.MarketContext?.showStock(symbol,dataset.as_of);
    $('stock-detail').hidden = false;
    $('detail-title').textContent = r.symbol + ' / ' + r.name;
    $('detail-subtitle').textContent = r.sector + ' \u00b7 prices through ' + date(r.data_date) + ' \u00b7 ' + r.structure;
    $('detail-badge').className = 'state ' + r.status;
    $('detail-badge').textContent = r.status;
    $('detail-reason').textContent = r.reason;
    renderStrategy(r);
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
    const picks=renderPriority();
    if(!selected && picks.length && status==='ALL' && !$('search').value && $('sector').value==='ALL' && $('structure').value==='ALL')showDetail(picks[0].symbol,{scroll:false});
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
  $('priority-list').addEventListener('click',event=>{const card=event.target.closest('button[data-symbol]');if(card)selectPriority(card.dataset.symbol);});
  $('stock-rows').addEventListener('click',event=>{const button=event.target.closest('button[data-symbol]');if(button) showDetail(button.dataset.symbol);});
  $('download-csv').addEventListener('click',exportCsv);
  for(const id of ['chart-swings','chart-levels','chart-all-pivots','chart-events','chart-volume','chart-window']) $(id).addEventListener('change',()=>{
    if(selected)renderChart(dataset.rows.find(r=>r.symbol===selected));
  });
  $('stock-chart').addEventListener('click',inspectSwing);
  $('stock-chart').addEventListener('keydown',inspectSwing);
  $('stock-chart').addEventListener('pointermove',inspectCandle);
  $('stock-chart').addEventListener('pointerleave',()=>{const line=$('chart-crosshair');if(line)line.setAttribute('opacity','0');});
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
  }).then(data=>{validate(data);dataset=data;renderSummary();const requested=new URLSearchParams(location.search).get('symbol');if(requested&&!selected)selected=requested;if(requested&&dataset.rows.some(r=>r.symbol===requested)&&!window.hhhlLinkedStockShown){selected=requested;window.hhhlLinkedStockShown=true;}if(selected)showDetail(selected,{scroll:false});loadRefreshStatus();}).catch(()=>{
    dataset=null;$('notice').textContent='The HH/HL snapshot could not be loaded or did not contain 200 valid stock rows. No signals are displayed.';
    $('session-date').textContent='Unavailable';$('coverage').textContent='Data check failed';$('result-count').textContent='No verified rows to display.';
    $('stock-rows').innerHTML='';$('stock-detail').hidden=true;
    for(const s of ['ALL',...statuses]) $('count-'+s).textContent='--';
  });
  }
  loadSnapshot();
  setInterval(()=>{if(document.visibilityState==='visible') loadSnapshot();},300000);
})();
