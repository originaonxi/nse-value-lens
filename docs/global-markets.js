'use strict';
(() => {
  const $=id=>document.getElementById(id);
  const numeric=value=>typeof value==='number'&&Number.isFinite(value);
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let dataset=null,selected=null,refreshProblem=null;
  const overdue=()=>dataset&&Date.now()-Date.parse(dataset.generated_at)>60*60*60*1000;
  const displayRow=row=>row.chart.length&&(refreshProblem||overdue())?{...row,status:'CAUTION',data_state:'cached',reason:refreshProblem||'Automatic updates are overdue; this is the last saved chart.'}:row;
  const activeRow=()=>dataset?.rows.find(r=>r.symbol===selected);
  const fmt=(value,digits=activeRow()?.digits??2)=>numeric(value)?value.toLocaleString('en-IN',{minimumFractionDigits:digits,maximumFractionDigits:digits}):'--';
  const money=value=>fmt(value);
  const range=values=>Array.isArray(values)&&values.every(numeric)?values.map(money).join(' – '):'--';
  const date=value=>/^\d{4}-\d{2}-\d{2}$/.test(value||'')?new Date(value+'T00:00:00Z').toLocaleDateString('en-IN',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}):'Unavailable';
  const colors={'BREAKOUT':'BUY','BELOW LOW':'SELL','WATCH':'WATCH','NO SETUP':'AVOID','CAUTION':'CAUTION'};

  function explanation(row) {
    const close=money(row.close),high=money(row.zones?.breakout_above),low=money(row.zones?.structure_exit_below);
    if(row.data_state!=='ready')return row.reason+(row.data_date?' The chart is dated '+date(row.data_date)+'.':'');
    if(row.status==='BREAKOUT')return 'The confirmed highs and lows are rising. The latest close of '+close+' crossed above '+high+' (CLOSING TRIGGER), confirming an upward price-structure breakout.';
    if(row.status==='BELOW LOW')return 'The latest close of '+close+' is below the last confirmed low at '+low+' (STRUCTURE EXIT). Price has broken below that support level.';
    if(row.status==='WATCH')return 'The last two confirmed highs and lows are rising (HH/HL), but the close of '+close+' has not finished above '+high+' (CLOSING TRIGGER). A fresh close above that level would confirm an upward breakout.';
    if(row.status==='CAUTION')return numeric(row.zones?.breakout_above)&&row.close>row.zones.breakout_above?'The close of '+close+' is already above '+high+', but there was no fresh crossing above that level in the latest session.':row.reason;
    const pair=kind=>{
      const values=(row.pivots?.[kind]||[]).map(p=>p.price);
      if(values.length!==2)return null;
      return (kind==='high'?'highs':'lows')+(values[1]>values[0]?' rose':values[1]<values[0]?' fell':' stayed level')+' from '+money(values[0])+' to '+money(values[1]);
    };
    return pair('high')&&pair('low')?'The last two confirmed '+pair('high')+', and the '+pair('low')+'. Both need to rise together for an HH/HL setup.':row.reason;
  }

  function validate(data) {
    if(data?.schema_version!==1||!Number.isFinite(Date.parse(data.generated_at))||data.instrument_count!==26||!Array.isArray(data.rows)||data.rows.length!==26||new Set(data.rows.map(r=>r.symbol)).size!==26)throw Error('Incomplete instrument snapshot');
    for(const row of data.rows){
      if(!['commodity','forex'].includes(row.group)||!colors[row.status]||!Array.isArray(row.chart))throw Error('Invalid instrument');
      let prior='';
      for(const bar of row.chart){
        if(![bar.open,bar.high,bar.low,bar.close].every(numeric)||bar.low>Math.min(bar.open,bar.close)||bar.high<Math.max(bar.open,bar.close)||bar.high<bar.low||bar.date<=prior||bar.date>row.data_date)throw Error('Invalid price candle');
        prior=bar.date;
      }
      if(row.chart.length&&row.chart.at(-1).date!==row.data_date)throw Error('Price date mismatch');
    }
  }

  function showDetail(symbol) {
    const source=dataset.rows.find(r=>r.symbol===symbol);
    if(!source)return;
    const row=displayRow(source);
    selected=symbol;
    document.querySelectorAll('[data-group]').forEach(select=>{
      const active=select.dataset.group===row.group;
      select.value=active?symbol:'';
      select.closest('.stock-picker').classList.toggle('selected',active);
    });
    $('stock-detail').hidden=false;
    $('detail-title').textContent=row.name;
    $('detail-subtitle').textContent=row.kind+' · '+row.unit+' · prices through '+date(row.data_date)+' · '+row.structure;
    $('detail-badge').className='state '+colors[row.status];
    $('detail-badge').textContent=row.status;
    $('selection-reason').textContent='WHY '+row.status+': '+explanation(row);
    $('data-warning').hidden=row.data_state==='ready';
    $('data-warning').textContent=row.data_state==='unavailable'?'No verified candles are available for this instrument.':row.data_state==='cached'?'Refresh failed. Showing saved prices from '+date(row.data_date)+'.':row.data_state==='delayed'?'Awaiting the latest expected weekday price. Last available candle: '+date(row.data_date)+'.':'Some recent price records failed the quality or coverage checks. Treat this chart with caution.';
    $('volume-toggle').hidden=row.group==='forex';
    renderChart(row);
    $('instrument-note').textContent=row.note||row.reason;
    $('instrument-session').textContent='Daily session: '+(row.session||'Unavailable')+'. Quote unit: '+row.unit+'.';
    $('instrument-audit').textContent='History: '+(row.audit?.history_sessions||0)+' sessions. Retrieved: '+(row.retrieved_at?new Date(row.retrieved_at).toLocaleString():'Unavailable')+'.'+(row.audit?.invalid_recent?.length?' Excluded invalid dates: '+row.audit.invalid_recent.join(', ')+'.':'')+(row.audit?.partial_recent?.length?' Incomplete coverage: '+row.audit.partial_recent.join(', ')+'.':'');
    const safeSource=typeof row.source_url==='string'&&row.source_url.startsWith('https://finance.yahoo.com/quote/');
    $('source-link').hidden=!safeSource;
    if(safeSource)$('source-link').href=row.source_url;
    $('pivot-detail').innerHTML='<div class="pivot-grid">'+['high','low'].map(kind=>'<div><b>Last two confirmed '+kind+'s</b><ul>'+(row.pivots[kind]||[]).map(p=>'<li>'+esc(money(p.price))+' · pivot '+esc(date(p.pivot_date))+' · confirmed '+esc(date(p.confirmed_on))+'</li>').join('')+'</ul></div>').join('')+'</div>';
    const url=new URL(location.href);url.searchParams.set('symbol',symbol);history.replaceState(null,'',url);
  }

  function renderSummary() {
    for(const group of ['commodity','forex']){
      const rows=dataset.rows.filter(r=>r.group===group).map(displayRow),select=$(group+'-picker');
      $(group+'-count').textContent=String(rows.length);
      select.innerHTML='<option value="">'+(group==='forex'?'Choose a currency pair':'Choose a commodity')+'</option>'+rows.map(r=>'<option value="'+esc(r.symbol)+'">'+esc(r.name+' · '+r.status)+'</option>').join('');
      select.disabled=false;
    }
    $('session-date').textContent='Latest expected: '+date(dataset.expected_date);
    $('coverage').textContent=dataset.available_count+' charts · '+(refreshProblem||overdue()?'refresh needs checking':dataset.ready_count+' pass data checks');
    $('refresh-status').textContent=(refreshProblem||'')+(overdue()?' Refresh overdue. ':'')+' Last checked: '+new Date(dataset.generated_at).toLocaleString()+'. '+dataset.refresh_schedule;
    $('instrument-rows').innerHTML=dataset.rows.map(displayRow).map(r=>'<tr><td><button type="button" data-symbol="'+esc(r.symbol)+'">'+esc(r.name)+'</button></td><td>'+esc(fmt(r.close,r.digits))+' '+esc(r.unit)+'</td><td>'+esc(date(r.data_date))+'</td><td>'+esc(r.structure)+'</td><td>'+esc(r.status)+'</td><td>'+esc(r.data_state)+'</td></tr>').join('');
    const requested=new URLSearchParams(location.search).get('symbol');
    const symbol=[selected,requested,dataset.rows.find(r=>r.chart.length)?.symbol].find(s=>dataset.rows.some(r=>r.symbol===s));
    if(symbol)showDetail(symbol);
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
    const pad=Math.max((hi-lo)*.16,Math.abs(hi)*.001,10**-(source.digits||2));lo-=pad;hi+=pad;
    const y=p=>top+(hi-p)/(hi-lo)*(priceBottom-top);
    const step=(plotRight-left)/bars.length,x=i=>left+step*(i+.5),indices=new Map(bars.map((b,i)=>[b.date,i]));
    const swings=HHHLChart.points(row),active=HHHLChart.activePoints(row),activeKeys=new Map(active.map(p=>[p.kind+':'+p.pivot_date,p.sequence]));
    const startX=day=>{if(!day||day>row.data_date)return null;const i=bars.findIndex(b=>b.date>=day);return i<0?null:x(i);};
    const stamp=p=>x(indices.get(p.pivot_date))+','+y(p.price);
    let svg='<svg viewBox="0 0 '+w+' '+h+'" data-width="'+w+'" data-left="'+left+'" data-step="'+step+'" role="group" aria-label="'+esc(row.symbol)+' daily price-structure chart"><rect width="'+w+'" height="'+h+'" fill="white"/>';
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
    $('candle-readout').textContent=bar.date+'   O '+money(bar.open)+'   H '+money(bar.high)+'   L '+money(bar.low)+'   C '+money(bar.close)+(numeric(bar.volume)?'   Vol '+fmt(bar.volume,0):'');
  }

  function renderChart(row) {
    $('stock-chart').innerHTML=chart(row);
    const bars=viewedRow(row).chart||[],previous=bars.at(-2)?.close,last=bars.at(-1)?.close;
    const change=previous?100*(last/previous-1):null;
    $('chart-price').textContent=money(last)+(numeric(change)?'  '+(change>=0?'+':'')+fmt(change,2)+'%':'')+' / '+row.data_date;
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
    if(!svg||!bars.length)return;
    const rect=svg.getBoundingClientRect(),px=(event.clientX-rect.left)*Number(svg.dataset.width)/rect.width;
    const index=Math.min(bars.length-1,Math.max(0,Math.floor((px-Number(svg.dataset.left))/Number(svg.dataset.step))));
    candleReadout(row,index);
    const hair=$('chart-crosshair'),x=Number(svg.dataset.left)+(index+.5)*Number(svg.dataset.step);
    hair.setAttribute('x1',x);hair.setAttribute('x2',x);hair.setAttribute('opacity','.65');
  }


  document.querySelectorAll('[data-group]').forEach(select=>select.addEventListener('change',()=>{
    if(dataset&&select.value)showDetail(select.value);
    else if(selected)showDetail(selected);
  }));
  for(const id of ['chart-swings','chart-levels','chart-all-pivots','chart-events','chart-volume','chart-window'])$(id).addEventListener('change',()=>{if(activeRow())renderChart(activeRow());});
  $('stock-chart').addEventListener('click',inspectSwing);
  $('stock-chart').addEventListener('keydown',inspectSwing);
  $('stock-chart').addEventListener('pointermove',inspectCandle);
  $('stock-chart').addEventListener('pointerleave',()=>{const line=$('chart-crosshair');if(line)line.setAttribute('opacity','0');});
  $('instrument-rows').addEventListener('click',event=>{const button=event.target.closest('[data-symbol]');if(button){showDetail(button.dataset.symbol);$('stock-detail').scrollIntoView({block:'start'});}});
  async function load() {
    try{
      const response=await fetch((document.body.dataset.source||'')+'global_markets.json',{cache:'no-store'});
      if(!response.ok)throw Error('Prices unavailable');
      const fresh=await response.json();validate(fresh);dataset=fresh;refreshProblem=null;renderSummary();
    }catch(error){
      $('refresh-status').textContent='The latest global snapshot could not be loaded. '+(dataset?'The displayed charts retain their original dates.':'No price signals are displayed.');
      if(!dataset){$('session-date').textContent='Prices unavailable';$('stock-detail').hidden=true;}
      else{refreshProblem='The latest refresh failed; previously loaded prices are shown.';renderSummary();}
    }
  }
  load();setInterval(()=>{if(document.visibilityState==='visible')load();},300000);
})();
