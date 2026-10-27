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
  let baseDataset=null, fnoDataset=null, universeMode='nifty200', fnoLoadError=false;

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
      (window.DailyDeals?.matches(r.symbol,$('daily-deal-filter').value) ?? ($('daily-deal-filter').value === 'ALL')) &&
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
    $('result-count').textContent = visible.length + ' of '+dataset.universe_count+' stocks shown \u00b7 ' + (status === 'ALL' ? 'all research states' : status) + ' \u00b7 select a symbol for its zones';
    $('stock-rows').innerHTML = visible.length ? visible.map(r =>
      '<tr data-symbol="' + esc(r.symbol) + '" class="' + (selected === r.symbol ? 'selected' : '') + '"><td><button class="stock-name" type="button" data-symbol="' + esc(r.symbol) + '">' + esc(r.symbol) + '</button><small>' + esc(r.sector) + '</small></td><td>' + stateBadge(r.status) +
      (r.fresh_breakout ? '<small>Fresh breakout</small>' : '') + '</td><td>' + money(r.close) + '<small>' + esc(r.data_date || 'No data') +
      (r.complete_for_session ? '' : ' / stale') + '</small></td><td>' + esc(r.structure) + '</td><td>' + money(r.zones.breakout_above) +
      '</td><td>' + money(r.zones.structure_exit_below) + '</td><td>' + (numeric(r.distance_to_breakout_pct) ? (r.distance_to_breakout_pct > 0 ? '+' : '') + fmt(r.distance_to_breakout_pct) + '%' : '--') +
      '</td><td>' + (numeric(r.atr_pct) ? fmt(r.atr_pct) + '%' : '--') + '</td><td class="reason-cell">' + esc(r.reason) + '</td></tr>'
    ).join('') : '<tr><td colspan="9" class="empty-row">No stocks match these filters.' + (status === 'BUY' && !dataset.market.new_entries_allowed ? ' New buys are blocked by the market/data gate.' : '') + '</td></tr>';
    $('download-csv').disabled = !visible.length;
  }

  function syncStockPickers(row) {
    document.querySelectorAll('[data-pick-state]').forEach(select=>{
      const active=row?.status===select.dataset.pickState;
      select.value=active?row.symbol:'';
      select.closest('.stock-picker').classList.toggle('selected',active);
    });
  }

  function renderStockPickers() {
    for(const state of statuses) {
      const select=$('pick-'+state),rows=dataset.rows.filter(r=>r.status===state).sort((a,b)=>a.symbol.localeCompare(b.symbol));
      $('pick-count-'+state).textContent=String(rows.length);
      select.innerHTML='<option value="">'+(rows.length?'Choose a stock':'No '+state.toLowerCase()+' stocks today')+'</option>'+rows.map(r=>
        '<option value="'+esc(r.symbol)+'">'+esc(r.symbol+' / '+r.name)+'</option>').join('');
      select.disabled=!rows.length;
    }
    syncStockPickers(dataset.rows.find(r=>r.symbol===selected));
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
    // ── Pine Signal overlays: EMA9 + RSI + OB + FVG (chart-signals checkbox) ──
    if($('chart-signals')&&$('chart-signals').checked){
      const N=bars.length;
      // EMA9 (Pine ta.ema: exponential moving average)
      const k9=2/10;
      const ema9=new Array(N);ema9[0]=bars[0].close;
      for(let i=1;i<N;i++) ema9[i]=bars[i].close*k9+ema9[i-1]*(1-k9);
      // RSI14 (Wilder RMA — same as Pine ta.rsi)
      const kw=1/14,ag2=new Array(N).fill(0),al2=new Array(N).fill(0);
      if(N>=15){
        let ga=0,la=0;for(let j=1;j<=14;j++){const d=bars[j].close-bars[j-1].close;if(d>0)ga+=d;else la-=d;}
        ag2[14]=ga/14;al2[14]=la/14;
        for(let i=15;i<N;i++){const d=bars[i].close-bars[i-1].close;ag2[i]=ag2[i-1]*(1-kw)+(d>0?d:0)*kw;al2[i]=al2[i-1]*(1-kw)+(d<0?-d:0)*kw;}
      }
      const rsi14=bars.map((_,i)=>i<14||al2[i]===0?NaN:100-100/(1+ag2[i]/al2[i]));
      // ATR14 (Wilder) for FVG min gap and TP step
      const kw14=1/14,atr14=new Array(N).fill(NaN);
      if(N>=14){
        let s=0;for(let i=0;i<14;i++) s+=bars[i].high-bars[i].low;
        atr14[13]=s/14;
        for(let i=14;i<N;i++) atr14[i]=atr14[i-1]*(1-kw14)+Math.max(bars[i].high-bars[i].low,Math.abs(bars[i].high-bars[i-1].close),Math.abs(bars[i].low-bars[i-1].close))*kw14;
      }
      const curAtr=atr14[N-1]||((hi-lo)*0.025);
      const tpStep=curAtr; // 1×ATR per TP level — adapts to each stock's volatility
      // Bull/Bear conditions (close > EMA9 and RSI > 50)
      const bull2=bars.map((b,i)=>i>=14&&b.close>ema9[i]&&rsi14[i]>50);
      const bear2=bars.map((b,i)=>i>=14&&b.close<ema9[i]&&rsi14[i]<50);
      // Walk-forward signal simulation — no look-ahead (exact PineScript logic)
      let dirSt=0,eBar2=-1,eVal2=0,slV2=0,tp1v=0,tp2v=0,tp3v=0,h1=false,h2=false,h3=false;
      const buyBs=[],sellBs=[],tp1h=new Array(N).fill(false),tp2h=new Array(N).fill(false),tp3h=new Array(N).fill(false),slH=new Array(N).fill(false);
      for(let i=0;i<N;i++){
        const b=bars[i];
        const buySig=bull2[i]&&(i===0||!bull2[i-1])&&dirSt!==1;
        const selSig=bear2[i]&&(i===0||!bear2[i-1])&&dirSt!==-1;
        if(dirSt!==0&&i>eBar2){
          const isL=dirSt===1,hit=isL?b.low<=slV2:b.high>=slV2;
          if(hit){slH[i]=true;}else{
            if(!h1&&(isL?b.high>=tp1v:b.low<=tp1v)){h1=true;tp1h[i]=true;}
            if(!h2&&(isL?b.high>=tp2v:b.low<=tp2v)){h2=true;tp2h[i]=true;}
            if(!h3&&(isL?b.high>=tp3v:b.low<=tp3v)){h3=true;tp3h[i]=true;}
          }
          if(hit||h3)dirSt=0;
        }
        if(buySig||selSig){
          dirSt=buySig?1:-1;eBar2=i;eVal2=b.close;
          const st=Math.max(0,i-4); // slLookback=4, shifted by 1 = bars [i-4..i-1]
          slV2=buySig?Math.min(...bars.slice(st,i).map(b=>b.low)||[b.low]):Math.max(...bars.slice(st,i).map(b=>b.high)||[b.high]);
          tp1v=eVal2+dirSt*tpStep;tp2v=eVal2+dirSt*tpStep*2;tp3v=eVal2+dirSt*tpStep*3;
          h1=h2=h3=false;(buySig?buyBs:sellBs).push(i);
        }
      }
      // Order Blocks: swing_len=5, last bearish/bullish candle before pivot-break
      const sLen=5;
      const bOBs=[],beOBs=[];
      let swHv2=NaN,swLv2=NaN,swHb2=-1,swLb2=-1,swHu2=true,swLu2=true;
      for(let i=0;i<N;i++){
        const phb=i-sLen;
        if(phb>=sLen){const sl2=bars.slice(phb-sLen,phb+sLen+1);if(sl2.length===sLen*2+1&&bars[phb].high===Math.max(...sl2.map(b=>b.high))&&bars[phb].high>bars[phb-1].high&&bars[phb].high>bars[phb+1].high){swHv2=bars[phb].high;swHb2=phb;swHu2=false;}}
        const plb=i-sLen;
        if(plb>=sLen){const sl2=bars.slice(plb-sLen,plb+sLen+1);if(sl2.length===sLen*2+1&&bars[plb].low===Math.min(...sl2.map(b=>b.low))&&bars[plb].low<bars[plb-1].low&&bars[plb].low<bars[plb+1].low){swLv2=bars[plb].low;swLb2=plb;swLu2=false;}}
        for(let j=bOBs.length-1;j>=0;j--){if(bars[i].close<bOBs[j].bot)bOBs.splice(j,1);}
        for(let j=beOBs.length-1;j>=0;j--){if(bars[i].close>beOBs[j].top)beOBs.splice(j,1);}
        if(!swHu2&&!isNaN(swHv2)&&bars[i].close>swHv2){
          swHu2=true;const sp=Math.min(i-swHb2,200);let ot=null,ob=null,oi=i-1;
          for(let j=1;j<=sp;j++){const idx=i-j;if(idx>=0&&bars[idx].close<bars[idx].open){ot=bars[idx].high;ob=bars[idx].low;oi=idx;break;}}
          if(ot===null&&sp>0){const ib=Array.from({length:Math.min(sp,i)},(_,k)=>i-1-k).reduce((b,c)=>bars[c].low<bars[b].low?c:b,i-1);ot=bars[ib].high;ob=bars[ib].low;oi=ib;}
          if(ot!==null){bOBs.push({top:ot,bot:ob,bi:oi});if(bOBs.length>3)bOBs.shift();}
        }
        if(!swLu2&&!isNaN(swLv2)&&bars[i].close<swLv2){
          swLu2=true;const sp=Math.min(i-swLb2,200);let ot=null,ob=null,oi=i-1;
          for(let j=1;j<=sp;j++){const idx=i-j;if(idx>=0&&bars[idx].close>bars[idx].open){ot=bars[idx].high;ob=bars[idx].low;oi=idx;break;}}
          if(ot===null&&sp>0){const ib=Array.from({length:Math.min(sp,i)},(_,k)=>i-1-k).reduce((b,c)=>bars[c].high>bars[b].high?c:b,i-1);ot=bars[ib].high;ob=bars[ib].low;oi=ib;}
          if(ot!==null){beOBs.push({top:ot,bot:ob,bi:oi});if(beOBs.length>3)beOBs.shift();}
        }
      }
      // FVGs (3-bar gap ≥ 0.25×ATR)
      const bFVGs=[],beFVGs=[],mg=curAtr*0.25;
      for(let i=2;i<N;i++){
        if(bars[i].low>bars[i-2].high&&(bars[i].low-bars[i-2].high)>=mg){bFVGs.push({top:bars[i].low,bot:bars[i-2].high,bi:i-2});for(let j=bFVGs.length-1;j>=0;j--){if(bars[i].close<bFVGs[j].bot)bFVGs.splice(j,1);}if(bFVGs.length>3)bFVGs.shift();}
        if(bars[i].high<bars[i-2].low&&(bars[i-2].low-bars[i].high)>=mg){beFVGs.push({top:bars[i-2].low,bot:bars[i].high,bi:i-2});for(let j=beFVGs.length-1;j>=0;j--){if(bars[i].close>beFVGs[j].top)beFVGs.splice(j,1);}if(beFVGs.length>3)beFVGs.shift();}
      }
      // Draw OB boxes
      const dbox=(ot,ob,bi,col,labTop)=>{const xt=x(bi),x2=plotRight;if(xt>=x2)return;svg+='<rect x="'+xt.toFixed(1)+'" width="'+Math.max(2,x2-xt).toFixed(1)+'" y="'+y(ot).toFixed(1)+'" height="'+Math.max(1,y(ob)-y(ot)).toFixed(1)+'" fill="'+col+'" opacity="0.12" stroke="'+col+'" stroke-width="0.5" rx="1" pointer-events="none"/><text x="'+(xt+3)+'" y="'+(labTop?y(ot)+10:y(ob)-2).toFixed(1)+'" font-size="8" fill="'+col+'" font-family="system-ui" pointer-events="none">'+(labTop?'Bear OB':'Bull OB')+'</text>';};
      bOBs.forEach(ob=>dbox(ob.top,ob.bot,ob.bi,'#2962ff',false));
      beOBs.forEach(ob=>dbox(ob.top,ob.bot,ob.bi,'#e040fb',true));
      // Draw FVG zones
      const dfvg=(ot,ob,bi,col)=>{const xt=x(bi),x2=plotRight;svg+='<rect x="'+xt.toFixed(1)+'" width="'+Math.max(2,x2-xt).toFixed(1)+'" y="'+y(ot).toFixed(1)+'" height="'+Math.max(1,y(ob)-y(ot)).toFixed(1)+'" fill="'+col+'" opacity="0.1" stroke="'+col+'" stroke-width="0.5" pointer-events="none"/>';};
      bFVGs.forEach(f=>dfvg(f.top,f.bot,f.bi,'#00bcd4'));
      beFVGs.forEach(f=>dfvg(f.top,f.bot,f.bi,'#ff9800'));
      // EMA9 polyline (purple — same as emaCol in Pine)
      svg+='<polyline points="'+ema9.map((v,i)=>x(i).toFixed(1)+','+y(v).toFixed(1)).join(' ')+'" fill="none" stroke="#2962ff" stroke-width="1.8" opacity="0.85"/>';
      svg+='<text x="'+x(N-1).toFixed(1)+'" y="'+(y(ema9[N-1])-5).toFixed(1)+'" font-size="9" fill="#2962ff" font-family="system-ui" text-anchor="end">EMA9</text>';
      // Buy ▲ / Sell ▼ markers
      buyBs.forEach(i=>{svg+='<text x="'+x(i).toFixed(1)+'" y="'+(y(bars[i].low)+14).toFixed(1)+'" text-anchor="middle" font-size="14" fill="#43d443" font-weight="bold">\u25b2</text><text x="'+x(i).toFixed(1)+'" y="'+(y(bars[i].low)+24).toFixed(1)+'" text-anchor="middle" font-size="8" fill="#43d443" font-family="system-ui">Buy</text>';});
      sellBs.forEach(i=>{svg+='<text x="'+x(i).toFixed(1)+'" y="'+(y(bars[i].high)-9).toFixed(1)+'" text-anchor="middle" font-size="14" fill="#f44336" font-weight="bold">\u25bc</text><text x="'+x(i).toFixed(1)+'" y="'+(y(bars[i].high)-20).toFixed(1)+'" text-anchor="middle" font-size="8" fill="#f44336" font-family="system-ui">Sell</text>';});
      // TP/SL hit dots
      tp1h.forEach((v,i)=>{if(v)svg+='<circle cx="'+x(i).toFixed(1)+'" cy="'+y(bars[i].high).toFixed(1)+'" r="4" fill="#43d443" opacity="0.85"><title>TP1 hit</title></circle>';});
      tp2h.forEach((v,i)=>{if(v)svg+='<circle cx="'+x(i).toFixed(1)+'" cy="'+y(bars[i].high).toFixed(1)+'" r="4" fill="#2e7d32" opacity="0.85"><title>TP2 hit</title></circle>';});
      tp3h.forEach((v,i)=>{if(v)svg+='<circle cx="'+x(i).toFixed(1)+'" cy="'+y(bars[i].high).toFixed(1)+'" r="4" fill="#1b5e20" opacity="0.85"><title>TP3 hit</title></circle>';});
      slH.forEach((v,i)=>{if(v)svg+='<circle cx="'+x(i).toFixed(1)+'" cy="'+y(bars[i].low).toFixed(1)+'" r="4" fill="#f44336" opacity="0.85"><title>SL hit</title></circle>';});
      // Current active SL / TP lines (dashed horizontal — same as PineScript drawTrade)
      if(dirSt!==0&&eBar2>=0){
        const ex=x(eBar2),x2=plotRight;
        svg+='<line x1="'+ex.toFixed(1)+'" x2="'+x2+'" y1="'+y(slV2).toFixed(1)+'" y2="'+y(slV2).toFixed(1)+'" stroke="#f44336" stroke-width="1.5" stroke-dasharray="5 3"/><text x="'+(x2+5)+'" y="'+(y(slV2)+4).toFixed(1)+'" font-size="9" fill="#f44336" font-family="system-ui">SL '+fmt(slV2)+'</text>';
        [[tp1v,'TP1','#43d443'],[tp2v,'TP2','#2e7d32'],[tp3v,'TP3','#1b5e20']].forEach(([tp,lbl,col])=>{if(!numeric(tp))return;svg+='<line x1="'+ex.toFixed(1)+'" x2="'+x2+'" y1="'+y(tp).toFixed(1)+'" y2="'+y(tp).toFixed(1)+'" stroke="'+col+'" stroke-width="1" stroke-dasharray="4 2"/><text x="'+(x2+5)+'" y="'+(y(tp)-2).toFixed(1)+'" font-size="9" fill="'+col+'" font-family="system-ui">'+lbl+' '+fmt(tp)+'</text>';});
        // Entry vertical tick
        svg+='<line x1="'+ex.toFixed(1)+'" x2="'+ex.toFixed(1)+'" y1="'+y(tp3v).toFixed(1)+'" y2="'+y(slV2).toFixed(1)+'" stroke="#9e9e9e" stroke-width="0.8" stroke-dasharray="2 3" opacity="0.5"/>';
      }
    }
    if($('chart-indicators')?.checked&&window.HHHLSetups)svg+=window.HHHLSetups.overlay(row.symbol,bars,x,y,lo,hi);
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
    $('chart-price').textContent=money(last)+(numeric(change)?'  '+(change>=0?'+':'')+fmt(change)+'%':'')+' / '+(row.data_date||'No price history');
    $('candle-readout').textContent='';
    candleReadout(row,bars.length-1);
    $('chart-inspect').textContent='Active pivots: H1/H2 are the last two highs; L1/L2 are the last two lows. Tap a label or closing-signal triangle for its dates.';
    if($('setup-panel'))$('setup-panel').innerHTML=window.HHHLSetups?window.HHHLSetups.panel(row.symbol):'';
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
      const pool=dataset.rows.filter(r=>r.complete_for_session&&r.structure==='HH / HL'&&numeric(r.zones.breakout_above)&&['BUY','WATCH','CAUTION'].includes(r.status)&&
        (r.entry_checks||[]).every(c=>['trigger','market'].includes(c.key)||c.state==='pass'));
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
    syncStockPickers(r);
    window.MarketContext?.showStock(symbol,dataset.as_of);
    window.DailyDeals?.showStock(symbol);
    $('stock-detail').hidden = false;
    $('detail-title').textContent = r.symbol + ' / ' + r.name;
    $('detail-subtitle').textContent = r.sector + ' \u00b7 prices through ' + date(r.data_date) + ' \u00b7 ' + r.structure;
    $('detail-badge').className = 'state ' + r.status;
    $('detail-badge').textContent = r.status;
    $('selection-reason').textContent = 'WHY ' + r.status + ': ' + HHHLReason.explain(r,dataset.market);
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
    const url=URL.createObjectURL(blob), a=document.createElement('a');a.href=url;a.download=universeMode+'-hhhl-'+dataset.as_of+'-'+status.toLowerCase()+'.csv';
    document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }

  function renderSummary() {
    document.querySelector('.chart-desk-heading h1').textContent=HHHLUniverse.modes[universeMode]+' / HH-HL scanner';
    $('universe-title').textContent='Filter '+HHHLUniverse.modes[universeMode];
    document.querySelector('.stock-table caption').textContent=HHHLUniverse.modes[universeMode]+' with HH/HL research states and dated reference levels';
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
    $('download-json').textContent='Full JSON';
    $('download-json').href=(document.body.dataset.source || '')+'hhhl_scan.json';
    filterRows();
    const picks=renderPriority();
    renderStockPickers();
    if(!selected) {
      const first=picks[0]?.symbol||dataset.rows.find(r=>r.status==='WATCH')?.symbol||dataset.rows[0]?.symbol;
      if(first)showDetail(first,{scroll:false});
    }
  }

  document.querySelectorAll('[data-pick-state]').forEach(select=>select.addEventListener('change',()=>{
    if(dataset&&select.value)showDetail(select.value,{scroll:false});
    else syncStockPickers(dataset?.rows.find(r=>r.symbol===selected));
  }));

  function applyUniverse() {
    if(!baseDataset)return;
    dataset=HHHLUniverse.view(baseDataset,fnoDataset,universeMode,{loadError:fnoLoadError});
    if(!dataset.rows.some(r=>r.symbol===selected))selected=null;
    renderSummary();
    if(selected)showDetail(selected,{scroll:false});
  }

  function updateUniverseOptions() {
    const options=$('universe').options;
    options[0].textContent='Nifty 200 (200)';
    if(!fnoDataset){
      options[1].disabled=options[2].disabled=true;
      $('universe-note').textContent='F&O coverage is temporarily unavailable. The Nifty 200 list is available.';
      $('universe-note').className='warning';return;
    }
    const members=fnoDataset.membership.members;
    const total=new Set([...baseDataset.rows.map(r=>r.symbol),...members.map(m=>m.symbol)]).size;
    options[1].textContent='All F&O stocks ('+members.length+')';options[2].textContent='All stocks ('+total+')';
    options[1].disabled=options[2].disabled=false;
    const old=Date.now()-Date.parse(fnoDataset.generated_at)>60*60*60*1000;
    const delayed=fnoLoadError||old||fnoDataset.as_of!==baseDataset.as_of;
    $('universe-note').textContent=delayed?'Extra-stock updates need checking; saved charts show Caution.':
      !fnoDataset.membership.verified?'Using saved NSE F&O membership; its latest check failed.':
      (total-200)+' additional F&O stocks. Charts show daily share prices.';
    $('universe-note').className=delayed||!fnoDataset.membership.verified?'warning':'';
  }

  $('universe').addEventListener('change',()=>{
    universeMode=$('universe').value;applyUniverse();
    const url=new URL(location.href);url.searchParams.set('universe',universeMode);
    if(selected)url.searchParams.set('symbol',selected);history.replaceState(null,'',url);
  });

  $('download-json').addEventListener('click',event=>{
    if(universeMode==='nifty200'||!dataset)return;
    event.preventDefault();
    const url=URL.createObjectURL(new Blob([JSON.stringify(dataset)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download=universeMode+'-hhhl-'+dataset.as_of+'.json';
    document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });

  document.querySelectorAll('.status-card').forEach(button=>button.addEventListener('click',()=>{
    if(!dataset) return;
    status=button.dataset.status;
    document.querySelectorAll('.status-card').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',b===button?'true':'false');});
    filterRows();
  }));
  $('search').addEventListener('input',()=>dataset&&filterRows());
  ['sector','structure','sort','daily-deal-filter'].forEach(id=>$(id).addEventListener('change',()=>dataset&&filterRows()));
  document.addEventListener('daily-deals-ready',()=>{if(dataset)filterRows();});
  $('reset').addEventListener('click',()=>{
    $('search').value='';$('sector').value='ALL';$('structure').value='ALL';$('sort').value='status';
    $('daily-deal-filter').value='ALL';
    document.querySelector('[data-status="ALL"]').click();
  });
  $('priority-list').addEventListener('click',event=>{const card=event.target.closest('button[data-symbol]');if(card)selectPriority(card.dataset.symbol);});
  $('stock-rows').addEventListener('click',event=>{const button=event.target.closest('button[data-symbol]');if(button) showDetail(button.dataset.symbol);});
  $('download-csv').addEventListener('click',exportCsv);
    for(const id of ['chart-swings','chart-levels','chart-all-pivots','chart-events','chart-volume','chart-signals','chart-indicators','chart-window']) $(id)?.addEventListener('change',()=>{
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
  const source=document.body.dataset.source || '';
  const extra=fetch(source+'hhhl_fno.json',{cache:'no-store'}).then(response=>{
    if(!response.ok)throw new Error('F&O snapshot unavailable');return response.json();
  }).then(HHHLUniverse.validate).then(data=>({data})).catch(()=>({error:true}));
  fetch(source+'hhhl_scan.json',{cache:'no-store'}).then(response=>{
    if(!response.ok) throw new Error('HTTP '+response.status);
    return response.json();
  }).then(async data=>{
    validate(data);baseDataset=data;$('universe').disabled=false;
    applyUniverse();loadRefreshStatus();
    const result=await extra;
    fnoLoadError=!!result.error;if(result.data)fnoDataset=result.data;
    updateUniverseOptions();
    const params=new URLSearchParams(location.search),requested=params.get('symbol'),requestedMode=params.get('universe');
    if(!window.hhhlLinkedStockShown){
      if(fnoDataset&&['fno','all'].includes(requestedMode))universeMode=requestedMode;
      else if(fnoDataset&&requested&&!baseDataset.rows.some(r=>r.symbol===requested)&&fnoDataset.membership.members.some(m=>m.symbol===requested))universeMode='all';
      if(requested)selected=requested;window.hhhlLinkedStockShown=true;
    }
    $('universe').value=universeMode;applyUniverse();
  }).catch(()=>{
    dataset=null;baseDataset=null;$('universe').disabled=true;$('notice').textContent='The HH/HL snapshot could not be loaded or did not contain 200 valid stock rows. No signals are displayed.';
    $('session-date').textContent='Unavailable';$('coverage').textContent='Data check failed';$('result-count').textContent='No verified rows to display.';
    $('stock-rows').innerHTML='';$('stock-detail').hidden=true;
    document.querySelectorAll('[data-pick-state]').forEach(select=>{select.disabled=true;select.innerHTML='<option value="">Snapshot unavailable</option>';select.closest('.stock-picker').classList.remove('selected');});
    for(const s of statuses)$('pick-count-'+s).textContent='—';
    for(const s of ['ALL',...statuses]) $('count-'+s).textContent='--';
  });
  }
  // Daily setups layer (indicators on the chart + plan/Jev/hedge panel). Redraw the open stock once it arrives.
  window.HHHLSetups?.load(document.body.dataset.source||'',()=>{if(selected&&dataset)renderChart(dataset.rows.find(r=>r.symbol===selected)||dataset.rows[0]);});
  function loadNiftySignal() {
    const host=$('pine-signal-nifty'); if(!host) return;
    const src=document.body.dataset.source||'';
    fetch(src+'nifty_chain.json',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject('HTTP '+r.status)).then(data=>{
      const hh=data.hhhl||{};
      const pine_signal=hh.signals||{};
      const cur=pine_signal.current||{};
      const ds=hh.dates||[],op=hh.open||[],hi=hh.high||[],lo=hh.low||[],cl=hh.close||[],sm=hh.sma20||[];
      const n=ds.length; if(!n){host.innerHTML='<p class="muted">Chart data unavailable.</p>';return;}
      const badge=$('nifty-signal-badge');
      if(badge){badge.textContent=cur.direction==='buy'?'BUY':cur.direction==='sell'?'SELL':'FLAT';badge.className='state '+(cur.direction==='buy'?'BUY':cur.direction==='sell'?'SELL':'WATCH');}
      // SVG chart
      const W=960,H=240,L=60,R=80,T=16,B=32;
      const allH=hi.filter(numeric),allL=lo.filter(numeric);
      if(!allH.length||!allL.length){host.innerHTML='<p class="muted">No price data.</p>';return;}
      const hiV=Math.max(...allH),loV=Math.min(...allL);
      const xf=i=>L+(W-L-R)*(i+0.5)/n;
      const yf=v=>T+(H-T-B)*(1-(v-loV)/(hiV-loV||1));
      const bw=Math.max(1.5,(W-L-R)/n*0.5);
      const ax='font-size="9" fill="#6b7a91" font-family="system-ui,sans-serif"';
      let svg='<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;height:auto;display:block;overflow:visible" role="img" aria-label="Nifty 50 daily chart with EMA9 RSI signals">';
      for(let k=0;k<=4;k++){const v=loV+(hiV-loV)*k/4,y=yf(v).toFixed(1);svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+y+'" y2="'+y+'" stroke="#eef1f6" stroke-width="1"/><text x="'+(L-4)+'" y="'+(parseFloat(y)+3)+'" text-anchor="end" '+ax+'>'+Math.round(v).toLocaleString('en-IN')+'</text>';}
      // Build date→index map
      const dIdx={};ds.forEach((d,i)=>{dIdx[d]=i;});
      // OB boxes
      ((pine_signal.order_blocks||{}).bull||[]).forEach(ob=>{const xi=dIdx[ob.date];if(xi===undefined)return;const rx=xf(xi),rw=Math.max(2,xf(n-1)+bw-rx),yt=yf(ob.top),yh=yf(ob.bot)-yt;svg+='<rect x="'+rx.toFixed(1)+'" width="'+rw.toFixed(1)+'" y="'+yt.toFixed(1)+'" height="'+Math.max(1,yh).toFixed(1)+'" fill="#2962ff" opacity="0.12" stroke="#2962ff" stroke-width="0.5" rx="1" pointer-events="none"/><text x="'+(rx+3)+'" y="'+(yt+yh+10).toFixed(1)+'" font-size="7" fill="#2962ff" font-family="system-ui" pointer-events="none">Bull OB</text>';});
      ((pine_signal.order_blocks||{}).bear||[]).forEach(ob=>{const xi=dIdx[ob.date];if(xi===undefined)return;const rx=xf(xi),rw=Math.max(2,xf(n-1)+bw-rx),yt=yf(ob.top),yh=yf(ob.bot)-yt;svg+='<rect x="'+rx.toFixed(1)+'" width="'+rw.toFixed(1)+'" y="'+yt.toFixed(1)+'" height="'+Math.max(1,yh).toFixed(1)+'" fill="#e040fb" opacity="0.12" stroke="#e040fb" stroke-width="0.5" rx="1" pointer-events="none"/><text x="'+(rx+3)+'" y="'+(yt+9).toFixed(1)+'" font-size="7" fill="#e040fb" font-family="system-ui" pointer-events="none">Bear OB</text>';});
      // FVG zones
      ((pine_signal.fvgs||{}).bull||[]).forEach(fvg=>{const xi=dIdx[fvg.date];if(xi===undefined)return;const rx=xf(xi),rw=Math.max(2,xf(n-1)+bw-rx),yt=yf(fvg.top),yh=yf(fvg.bot)-yt;svg+='<rect x="'+rx.toFixed(1)+'" width="'+rw.toFixed(1)+'" y="'+yt.toFixed(1)+'" height="'+Math.max(1,yh).toFixed(1)+'" fill="#00bcd4" opacity="0.1" stroke="#00bcd4" stroke-width="0.5" pointer-events="none"/>';});
      ((pine_signal.fvgs||{}).bear||[]).forEach(fvg=>{const xi=dIdx[fvg.date];if(xi===undefined)return;const rx=xf(xi),rw=Math.max(2,xf(n-1)+bw-rx),yt=yf(fvg.top),yh=yf(fvg.bot)-yt;svg+='<rect x="'+rx.toFixed(1)+'" width="'+rw.toFixed(1)+'" y="'+yt.toFixed(1)+'" height="'+Math.max(1,yh).toFixed(1)+'" fill="#ff9800" opacity="0.1" stroke="#ff9800" stroke-width="0.5" pointer-events="none"/>';});
      // Candlesticks
      for(let i=0;i<n;i++){const o=op[i],h2=hi[i],l2=lo[i],c2=cl[i];if(!numeric(o)||!numeric(c2))continue;const up=c2>=o,col=up?'#43d443':'#f44336';svg+='<line x1="'+xf(i).toFixed(1)+'" x2="'+xf(i).toFixed(1)+'" y1="'+yf(h2).toFixed(1)+'" y2="'+yf(l2).toFixed(1)+'" stroke="'+col+'" stroke-width="0.8"/><rect x="'+(xf(i)-bw/2).toFixed(1)+'" width="'+bw.toFixed(1)+'" y="'+yf(Math.max(o,c2)).toFixed(1)+'" height="'+Math.max(1,Math.abs(yf(o)-yf(c2))).toFixed(1)+'" fill="'+col+'" opacity="0.85"/>';}
      // SMA20 (amber dashed)
      const smaPts=sm.map((v,i)=>numeric(v)?xf(i).toFixed(1)+','+yf(v).toFixed(1):null).filter(Boolean);
      if(smaPts.length>1) svg+='<polyline points="'+smaPts.join(' ')+'" fill="none" stroke="#c07830" stroke-width="1" stroke-dasharray="3 2" opacity="0.7"/>';
      // EMA9 (purple)
      const e9=(pine_signal.ema9||[]);
      const e9pts=e9.map((v,i)=>numeric(v)?xf(i).toFixed(1)+','+yf(v).toFixed(1):null).filter(Boolean);
      if(e9pts.length>1){svg+='<polyline points="'+e9pts.join(' ')+'" fill="none" stroke="#7c3aed" stroke-width="1.5" opacity="0.85"/><text x="'+(W-R+2)+'" y="'+(yf(e9[e9.length-1])+4).toFixed(1)+'" font-size="8" fill="#7c3aed" font-family="system-ui">EMA9</text>';}
      // Buy ▲ / Sell ▼ markers
      (pine_signal.buy_bars||[]).forEach(i=>{if(i>=0&&i<n&&numeric(lo[i])) svg+='<text x="'+xf(i).toFixed(1)+'" y="'+(yf(lo[i])+13).toFixed(1)+'" text-anchor="middle" font-size="12" fill="#43d443" font-family="system-ui" font-weight="bold">\u25b2</text>';});
      (pine_signal.sell_bars||[]).forEach(i=>{if(i>=0&&i<n&&numeric(hi[i])) svg+='<text x="'+xf(i).toFixed(1)+'" y="'+(yf(hi[i])-5).toFixed(1)+'" text-anchor="middle" font-size="12" fill="#f44336" font-family="system-ui" font-weight="bold">\u25bc</text>';});
      // TP/SL hit dots
      (pine_signal.tp1_hits||[]).forEach((v,i)=>{if(v&&i<n&&numeric(hi[i])) svg+='<circle cx="'+xf(i).toFixed(1)+'" cy="'+yf(hi[i]).toFixed(1)+'" r="3.5" fill="#43d443"/>';});
      (pine_signal.sl_hits||[]).forEach((v,i)=>{if(v&&i<n&&numeric(lo[i])) svg+='<circle cx="'+xf(i).toFixed(1)+'" cy="'+yf(lo[i]).toFixed(1)+'" r="3.5" fill="#f44336"/>';});
      // Current SL/TP dashed lines
      if(cur.direction!=='flat'&&numeric(cur.sl)&&numeric(cur.tp1)){
        const xe=cur.entry_date&&dIdx[cur.entry_date]!==undefined?dIdx[cur.entry_date]:0;
        const x1=xf(xe).toFixed(1),x2=W-R;
        svg+='<line x1="'+x1+'" x2="'+x2+'" y1="'+yf(cur.sl).toFixed(1)+'" y2="'+yf(cur.sl).toFixed(1)+'" stroke="#f44336" stroke-width="1.2" stroke-dasharray="5 3"/><text x="'+(x2+2)+'" y="'+(yf(cur.sl)+4).toFixed(1)+'" font-size="8" fill="#f44336" font-family="system-ui">SL '+Math.round(cur.sl).toLocaleString('en-IN')+'</text>';
        [['tp1','TP1'],['tp2','TP2'],['tp3','TP3']].forEach(([k,lbl])=>{if(!numeric(cur[k]))return;svg+='<line x1="'+x1+'" x2="'+x2+'" y1="'+yf(cur[k]).toFixed(1)+'" y2="'+yf(cur[k]).toFixed(1)+'" stroke="#43d443" stroke-width="1" stroke-dasharray="4 2"/><text x="'+(x2+2)+'" y="'+(yf(cur[k])-2).toFixed(1)+'" font-size="8" fill="#43d443" font-family="system-ui">'+lbl+' '+Math.round(cur[k]).toLocaleString('en-IN')+'</text>';});
      }
      // Date labels + legend
      [0,Math.floor(n/4),Math.floor(n/2),Math.floor(3*n/4),n-1].forEach(i=>{if(ds[i]) svg+='<text x="'+xf(i).toFixed(1)+'" y="'+(H-8)+'" text-anchor="middle" '+ax+'>'+ds[i].slice(5)+'</text>';});
      svg+='<line x1="'+L+'" x2="'+(L+14)+'" y1="'+(T+8)+'" y2="'+(T+8)+'" stroke="#7c3aed" stroke-width="1.5"/><text x="'+(L+18)+'" y="'+(T+11)+'" '+ax+'>EMA9</text>';
      svg+='<line x1="'+(L+52)+'" x2="'+(L+66)+'" y1="'+(T+8)+'" y2="'+(T+8)+'" stroke="#c07830" stroke-width="1" stroke-dasharray="3 2"/><text x="'+(L+70)+'" y="'+(T+11)+'" '+ax+'>SMA20</text>';
      svg+='<rect x="'+(L+110)+'" width="10" height="8" y="'+(T+4)+'" fill="#2962ff" opacity="0.25"/><text x="'+(L+124)+'" y="'+(T+11)+'" '+ax+'>Bull OB</text>';
      svg+='<rect x="'+(L+170)+'" width="10" height="8" y="'+(T+4)+'" fill="#e040fb" opacity="0.25"/><text x="'+(L+184)+'" y="'+(T+11)+'" '+ax+'>Bear OB</text>';
      svg+='<rect x="'+(L+230)+'" width="10" height="8" y="'+(T+4)+'" fill="#00bcd4" opacity="0.25"/><text x="'+(L+244)+'" y="'+(T+11)+'" '+ax+'>FVG\u25b2</text>';
      svg+='<rect x="'+(L+278)+'" width="10" height="8" y="'+(T+4)+'" fill="#ff9800" opacity="0.25"/><text x="'+(L+292)+'" y="'+(T+11)+'" '+ax+'>FVG\u25bc</text>';
      svg+='</svg>';
      // Signal card
      const isBull=cur.direction==='buy',isBear=cur.direction==='sell';
      const dStyle=isBull?'background:#d4f0e7;color:#0a5c47;border:1px solid #0d8a7a':isBear?'background:#fde8e8;color:#7f1d1d;border:1px solid #c0392b':'background:#f0f4f8;color:#4a5568;border:1px solid #dde3ec';
      const hit=(h,lbl)=>'<span style="padding:3px 8px;border-radius:3px;font-size:12px;'+(h?'background:#d4f0e7;color:#0a5c47;border:1px solid #0d8a7a':'background:#f9fafb;color:#6b7a91;border:1px solid #dde3ec')+'">'+lbl+(h?' \u2713':'')+'</span>';
      const obs=pine_signal.order_blocks||{},fvg2=pine_signal.fvgs||{};
      const pills=[...(obs.bull||[]).map(b=>'<span style="padding:2px 6px;border-radius:10px;font-size:11px;background:#e8f0fe;color:#1a56db;border:1px solid #2962ff">Bull OB '+Math.round(b.bot).toLocaleString('en-IN')+'\u2013'+Math.round(b.top).toLocaleString('en-IN')+'</span>'),
        ...(obs.bear||[]).map(b=>'<span style="padding:2px 6px;border-radius:10px;font-size:11px;background:#fce4fc;color:#9b1fa8;border:1px solid #e040fb">Bear OB '+Math.round(b.bot).toLocaleString('en-IN')+'\u2013'+Math.round(b.top).toLocaleString('en-IN')+'</span>'),
        ...(fvg2.bull||[]).map(f=>'<span style="padding:2px 6px;border-radius:10px;font-size:11px;background:#e0f7fa;color:#006064;border:1px solid #00bcd4">FVG\u25b2 '+Math.round(f.bot).toLocaleString('en-IN')+'\u2013'+Math.round(f.top).toLocaleString('en-IN')+'</span>'),
        ...(fvg2.bear||[]).map(f=>'<span style="padding:2px 6px;border-radius:10px;font-size:11px;background:#fff3e0;color:#e65100;border:1px solid #ff9800">FVG\u25bc '+Math.round(f.bot).toLocaleString('en-IN')+'\u2013'+Math.round(f.top).toLocaleString('en-IN')+'</span>')].join(' ');
      const card=cur.direction!=='flat'?'<div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:8px;align-items:center">'
        +'<span style="padding:8px 14px;border-radius:4px;font-weight:700;font-size:14px;'+dStyle+'">'+(isBull?'\u25b2 BUY':'\u25bc SELL')+(cur.entry_date?' \u00b7 '+date(cur.entry_date):'')+(numeric(cur.entry)?' \u00b7 @ '+Math.round(cur.entry).toLocaleString('en-IN'):'')+'</span>'
        +'<span style="padding:4px 10px;border-radius:3px;font-size:12.5px;font-weight:600;background:#fde8e8;color:#7f1d1d;border:1px solid #c0392b">\u26d4 SL '+Math.round(cur.sl||0).toLocaleString('en-IN')+'</span>'
        +hit(cur.hit1,'TP1 '+Math.round(cur.tp1||0).toLocaleString('en-IN'))
        +hit(cur.hit2,'TP2 '+Math.round(cur.tp2||0).toLocaleString('en-IN'))
        +hit(cur.hit3,'TP3 '+Math.round(cur.tp3||0).toLocaleString('en-IN'))
        +'</div>':'';
      host.innerHTML=svg+card+(pills?'<div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px">'+pills+'</div>':'')+'<p style="margin:8px 0 0;font-size:11.5px;color:#6b7a91">EMA9+RSI daily signal \u00b7 tp_step=100 pts \u00b7 sl_buffer=20 pts \u00b7 EOD NSE data \u00b7 not investment advice</p>';
    }).catch(err=>{if(host) host.innerHTML='<p class="muted">Nifty signal unavailable ('+err+').</p>';});
  }
  loadNiftySignal();

  loadSnapshot();
  setInterval(()=>{if(document.visibilityState==='visible') loadSnapshot();},300000);

  // ── Kronos 24-bar fan overlay ────────────────────────────────────
  let kronosData=null,liveCards=null;
  (async()=>{try{const src=document.body.dataset.source||'';const r=await fetch(src+'kronos_forecast.json',{cache:'no-store'});if(r.ok){kronosData=await r.json();if(typeof selected!=='undefined'&&selected)renderKronosCard(selected);}}catch{/*not generated yet — silent*/}})();
  if(globalThis.LiveCards)globalThis.LiveCards.load(document.body.dataset.source||'').then(d=>{liveCards=d;if(typeof selected!=='undefined'&&selected)renderKronosCard(selected);}).catch(()=>{/*live prices optional; EOD levels still shown*/});
  // Trade plan (action, trigger, stop, risk, Kronos agreement) — shown even when Kronos paths are unavailable.
  const tradePlan=sym=>{const row=dataset?.rows?.find(r=>r.symbol===sym);const entry=kronosData?.model==='NeoQuasar/Kronos-small'&&kronosData?.provenance?.kind==='kronos-neural'?kronosData.symbols?.[sym]:null;return globalThis.LiveCards&&row?globalThis.LiveCards.stockPlanHtml(row,entry,liveCards,dataset):'';};
  function renderKronosCard(sym){
    let card=document.getElementById('kronos-stock-card');
    if(!card){
      card=document.createElement('div');card.id='kronos-stock-card';
      card.style.cssText='margin:10px 0;padding:8px 10px;background:#0d1117;border-radius:6px;border:1px solid #21262d;';
      const anchor=$('stock-chart');if(!anchor)return;
      anchor.parentNode.insertBefore(card,anchor.nextSibling);
    }
    const unavailable=reason=>{card.hidden=false;card.innerHTML=tradePlan(sym)+'<p class="muted">Kronos forecast unavailable: '+esc(reason)+'. <a href="kronos.html?symbol='+encodeURIComponent(sym)+'">View recorded candles and structural context</a>.</p>';};
    if(!kronosData){unavailable('data not loaded');return;}
    if(kronosData.model!=='NeoQuasar/Kronos-small'||kronosData.provenance?.kind!=='kronos-neural'){unavailable('unverified model provenance');return;}
    const key=sym==='NIFTY 50'?'NSEI':sym;
    const entry=kronosData.symbols?.[key];
    if(!entry){unavailable('no current model output');return;}
    const prov=entry.provenance||{},row=dataset?.rows?.find(r=>r.symbol===sym);
    if(prov.kind!=='kronos-neural'||prov.model!==kronosData.model){unavailable('unverified entry provenance');return;}
    if(!entry.data_as_of||entry.input_stale||entry.data_as_of!==dataset?.as_of||entry.data_as_of!==row?.data_date){unavailable('stale or mismatched input date');return;}
    const rawPaths=Array.isArray(entry.paths)?entry.paths:[];
    const validPaths=rawPaths.filter(p=>Array.isArray(p)&&p.length===kronosData.pred_len&&p.every((bar,i)=>bar&&numeric(bar.c)&&bar.c>0&&/^\d{4}-\d{2}-\d{2}$/.test(bar.d)&&bar.d>(i?p[i-1].d:entry.data_as_of)));
    if(!validPaths.length||validPaths.length!==rawPaths.length||validPaths.length!==entry.config?.n_samples||!numeric(entry.last_close)||entry.last_close<=0||validPaths.some(p=>p.some((b,i)=>b.d!==validPaths[0][i].d))){unavailable('invalid or incomplete model paths');return;}
    card.hidden=false;
    const predLen=validPaths[0].length;
    const cpaths=validPaths.map(p=>p.map(bar=>bar.c));
    const W=560,H=120,PL=6,PR=6,PT=22,PB=8,cW=W-PL-PR,cH=H-PT-PB;
    const flat=cpaths.flat().filter(Number.isFinite);
    if(!flat.length){card.hidden=true;return;}
    const yMin=Math.min(...flat),yMax=Math.max(...flat),yRange=(yMax-yMin)||1;
    const sy=v=>PT+cH-((v-yMin)/yRange)*cH;
    const sx=i=>PL+(i/(predLen-1||1))*cW;
    const med=cpaths[0].map((_,i)=>{const c=cpaths.map(p=>p[i]).filter(Number.isFinite).sort((a,b)=>a-b);return (c[Math.floor((c.length-1)/2)]+c[Math.floor(c.length/2)])/2;});
    const p10=cpaths[0].map((_,i)=>{const c=cpaths.map(p=>p[i]).filter(Number.isFinite).sort((a,b)=>a-b);return c[Math.floor(c.length*0.1)];});
    const p90=cpaths[0].map((_,i)=>{const c=cpaths.map(p=>p[i]).filter(Number.isFinite).sort((a,b)=>a-b);return c[Math.floor(c.length*0.9)];});
    const endMed=med[med.length-1],last=entry.last_close;
    const up=typeof endMed==='number'&&typeof last==='number'&&endMed>=last,col=up?'#22c55e':'#ef4444';
    const medPct=(typeof endMed==='number'&&typeof last==='number'&&last>0)?((endMed-last)/last*100).toFixed(1):null;
    let s='<svg viewBox="0 0 '+W+' '+H+'" width="100%" style="display:block">';
    s+='<rect width="'+W+'" height="'+H+'" fill="#0d1117" rx="5"/>';
    const bp=[...p90.map((v,i)=>sx(i)+','+sy(v)),...[...p10].reverse().map((v,i)=>sx(predLen-1-i)+','+sy(v))].join(' ');
    s+='<polygon points="'+bp+'" fill="'+col+'" opacity="0.10"/>';
    for(const cpath of cpaths)s+='<polyline points="'+cpath.map((v,i)=>sx(i)+','+sy(v)).join(' ')+'" stroke="'+col+'" stroke-width="0.5" fill="none" opacity="0.18"/>';
    s+='<polyline points="'+med.map((v,i)=>sx(i)+','+sy(v)).join(' ')+'" stroke="'+col+'" stroke-width="2.5" fill="none" stroke-linecap="round"/>';
    s+='<text x="'+PL+'" y="15" font-size="10.5" fill="#e6edf3" font-family="sans-serif" font-weight="600">KRONOS \u00b7 '+esc(sym)+' \u00b7 predicted closes, next '+predLen+' sessions<\/text>';
    s+=medPct!==null?'<text x="'+(W*0.55)+'" y="15" font-size="10" fill="'+col+'" font-family="sans-serif">median '+(up?'+':'')+medPct+'%<\/text>':'';
    s+='<text x="'+(W-PR)+'" y="15" font-size="10" fill="#7d8590" font-family="sans-serif" text-anchor="end">'+validPaths.length+' paths<\/text>';
    const zr=row?.zones||{},endsUp=cpaths.filter(p=>p[p.length-1]>last).length,hitStop=numeric(zr.structure_exit_below)?cpaths.filter(p=>p.some(c=>c<zr.structure_exit_below)).length:null,hitTrig=numeric(zr.breakout_above)?cpaths.filter(p=>p.some(c=>c>zr.breakout_above)).length:null;
    s+='<\/svg><p style="margin:4px 0 0;font-size:12px;color:#e6edf3"><b>Kronos agreement:</b> '+endsUp+'/'+validPaths.length+' paths end above last close'+(hitTrig!==null?' \u00b7 '+hitTrig+'/'+validPaths.length+' close above trigger':'')+(hitStop!==null?' \u00b7 '+hitStop+'/'+validPaths.length+' close below stop':'')+' over '+predLen+' sessions<\/p><p style="margin:3px 0 0;font-size:10.5px;color:#6b7a91">'+validPaths.length+' model-generated close paths \u00b7 input '+esc(entry.data_as_of)+' \u00b7 not observed future candles \u00b7 small uncalibrated sample, not a profit probability \u00b7 not investment advice<\/p>';
    card.innerHTML=tradePlan(sym)+s;
  }
  setTimeout(()=>{const h=$('stock-chart');if(h)new MutationObserver(()=>{if(selected)renderKronosCard(selected);}).observe(h,{childList:true,subtree:true});},200);
})();
