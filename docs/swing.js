'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = n => Number.isFinite(n) ? '₹'+n.toLocaleString('en-IN',{maximumFractionDigits:2}) : '—';
const pct = n => n == null ? '—' : (n > 0 ? '+' : '')+n.toFixed(2)+'%';
const names = {breakout:'20-day breakout',pullback:'Trend pullback',reversion:'Mean reversion'};
let desk, expired = true;
function isExpired(asof, now = new Date()) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(asof || '')) return true;
  const ist = new Date(now.getTime()+330*60000);
  const day = new Date(asof+'T00:00:00Z');
  if (!Number.isFinite(day.getTime()) || day > ist) return true;
  const next = new Date(day);
  do { next.setUTCDate(next.getUTCDate()+1); } while ([0,6].includes(next.getUTCDay()));
  next.setUTCHours(9,20,0,0);
  // Conservative weekday expiry. Exchange holidays are not inferred.
  return ist >= next;
}
function renderCards() {
  expired = isExpired(desk.as_of);
  const strategy = $('strategy').value;
  const rows = desk.candidates.filter(p => strategy === 'all' || p.strategy === strategy);
  if (expired || !rows.length) {
    $('cards').innerHTML = '<div class="empty"><strong>'+ (expired ? 'Wait for a fresh snapshot.' : !desk.market.risk_on ? 'Cash is a position, too.' : 'No setup passes these rules.')+
      '</strong><p>'+(expired ? 'The next-opening entry window has expired. Old entry levels are hidden; refresh the data before planning a new trade.' : !desk.market.risk_on ? 'The broad-market trend filter is off. New entries are paused across all three strategies.' : 'There is no need to force a trade. Check the next completed session.')+'</p></div>';
    return;
  }
  $('cards').innerHTML = rows.slice(0,6).map(p => '<article class="card"><div class="card-top"><h3>'+esc(p.symbol)+'</h3><span class="tag">'+p.hold+' sessions max</span></div><p class="name">'+esc(p.name)+' · '+esc(p.sector)+'</p><div class="strategy">'+esc(names[p.strategy])+' / PAPER SETUP</div><div class="levels"><div class="entry"><span>NEXT-OPEN ENTRY BAND</span><strong>'+money(p.entry_low)+' – '+money(p.entry_high)+'</strong></div><div><span>INITIAL STOP</span><strong>'+money(p.stop)+'</strong></div><div><span>2R TARGET AT SIGNAL CLOSE</span><strong>'+money(p.target)+'</strong></div><div><span>VOLUME / PRIOR AVERAGE</span><strong>'+p.volume_ratio.toFixed(2)+'×</strong></div><div><span>63-SESSION RELATIVE RETURN</span><strong>'+pct(p.relative_strength*100)+'</strong></div></div><p class="why">'+esc(p.reason)+'</p></article>').join('');
}
function sizePosition() {
  const p = desk?.candidates[Number($('sizing-symbol').value)];
  expired = !desk || isExpired(desk.as_of);
  const capital = Number($('capital').value), open = Number($('fill').value), entry = open*1.0005;
  if (expired || !p || $('sizing-symbol').value === '') return $('size-result').textContent = 'No current setup available for position sizing.';
  if (!Number.isFinite(capital) || capital <= 0 || !Number.isFinite(open) || open <= 0)
    return $('size-result').textContent = 'Enter positive capital and an opening price.';
  if (entry < p.entry_low || entry > p.entry_high)
    return $('size-result').textContent = 'Skip this entry: the estimated fill is outside the permitted band.';
  const risk = entry-p.stop;
  const qty = Math.floor(Math.min(capital*.005/(risk+entry*.0015+p.stop*.002), capital*.2/(entry*1.0015)));
  if (qty < 1) return $('size-result').textContent = 'Capital is too small for one share within these risk limits.';
  $('size-result').textContent = qty+' shares · estimated entry '+money(entry)+' · capital used '+money(qty*entry*1.0015)+' · stop '+money(p.stop)+' · target '+money(entry+2*risk)+' · price risk '+money(qty*risk)+' before costs / gaps.';
}

let historyRows = [];
const tradeDate = value => value ? esc(value) : 'Pending';
function renderHistory() {
  const selected = $('history-strategy').value;
  const matches = historyRows.filter(row => selected === 'all' || row.strategy === selected);
  const rows = matches.slice(0, 10);
  $('history-note').textContent = rows.length
    ? 'Showing '+rows.length+' of '+matches.length+' filled setups. Dates are NSE session dates. Prices include simulated slippage; net results include estimated costs. Open positions are as of the evidence snapshot.'
    : 'No filled setups available for this selection.';
  $('history-rows').innerHTML = rows.length ? rows.map(t => {
    const closed = t.status === 'CLOSED';
    return '<tr><td>'+esc(t.symbol)+'<br><small>'+esc(names[t.strategy])+'</small></td>'+
      '<td>'+tradeDate(t.signal_date)+'</td><td>Buy &rarr; sell<br><small>Long</small></td>'+
      '<td>'+tradeDate(t.entry_date)+'<br><strong>'+money(t.entry_price)+'</strong></td>'+
      '<td>'+(closed ? tradeDate(t.exit_date)+'<br><strong>'+money(t.exit_price)+'</strong>' : 'Open<br><small>No sell fill yet</small>')+'</td>'+
      '<td>'+money(t.stop)+'<br>'+money(t.target)+'</td>'+
      '<td class="'+(closed ? (t.pnl >= 0 ? 'positive' : 'negative') : '')+'">'+
      (closed ? money(t.pnl)+'<br><small>'+pct(t.return_pct)+'</small>' : 'Unrealized')+'</td>'+
      '<td>'+esc(t.reason)+'<br><small>'+esc(t.sessions)+' sessions</small></td></tr>';
  }).join('') : '<tr><td colspan="8">No historical fills to display.</td></tr>';
}

function renderEvidence(e) {
  historyRows = Object.entries(e.results).flatMap(([strategy, result]) => ['earlier', 'recent'].flatMap(window => {
    const r = result[window];
    return [...(r?.trade_log || []), ...(r?.open_trade_log || [])].filter(t => t.signal_date && Number.isFinite(t.entry_price)).map(t => ({...t, strategy}));
  })).sort((a,b) => b.signal_date.localeCompare(a.signal_date) || b.entry_date.localeCompare(a.entry_date) || a.symbol.localeCompare(b.symbol) || a.strategy.localeCompare(b.strategy));
  renderHistory();
  $('evidence-note').textContent = 'Earlier: '+e.windows.earlier.join(' → ')+'. Recent: '+e.windows.recent.join(' → ')+'. Fixed rules, no parameter search. Current constituents create survivorship bias; these retrospective results are not proof of future profits.'+(e.as_of !== desk?.as_of ? ' Evidence snapshot: '+e.as_of+'.' : '');
  $('results').innerHTML = Object.entries(e.results).map(([key,v]) => '<tr><td>'+esc(names[key])+'</td><td>'+pct(v.earlier.return_pct)+'</td><td class="'+(v.recent.return_pct>=0?'positive':'negative')+'">'+pct(v.recent.return_pct)+'</td><td>'+v.recent.max_drawdown_pct.toFixed(2)+'%</td><td>'+v.recent.trades+'</td><td>'+(v.recent.win_rate_pct == null ? '—' : v.recent.win_rate_pct.toFixed(1)+'%')+'</td><td>'+pct(v.stress.return_pct)+'</td></tr>').join('');
  $('cost-note').textContent = e.cost_note+' '+e.benchmark_note+' Open holdings are marked to the last available close with estimated exit costs reserved; closed-trade statistics exclude those holdings.';
  $('limitations').innerHTML = e.limitations.map(x => '<li>'+esc(x)+'</li>').join('');
  const first = Object.values(e.results)[0];
  $('benchmark').textContent = 'Nifty 50 price return over the recent window: '+pct(first.recent.benchmark_price_return_pct)+'. No dividends; this comparison does not adjust for different market exposure.';
  drawChart(e.results);
}
function drawChart(results) {
  const colors=['#246c4e','#688ac2','#c18a45'];
  const series=Object.entries(results).map(([key,v],i)=>({name:names[key],curve:v.recent.curve,color:colors[i]}));
  const all=series.flatMap(s=>s.curve.map(p=>p.equity));
  if (!all.length) return $('chart').textContent='No equity observations available.';
  let min=Math.min(100000,...all), max=Math.max(100000,...all);
  const pad=Math.max(1000,(max-min)*.15); min-=pad;max+=pad;
  const w=1000,h=230,left=65,right=20,top=15,bottom=35;
  const y=v=>top+(max-v)/(max-min)*(h-top-bottom);
  let svg='<svg viewBox="0 0 '+w+' '+h+'" role="img" aria-label="Recent research equity curves for three fixed strategies">';
  for(let i=0;i<4;i++){const v=min+(max-min)*i/3, yy=y(v);svg+='<line x1="'+left+'" y1="'+yy+'" x2="'+(w-right)+'" y2="'+yy+'" stroke="#e7ece3"/><text x="0" y="'+(yy+4)+'" fill="#65716a" font-size="11">'+Math.round(v/1000)+'k</text>';}
  svg+='<line x1="'+left+'" y1="'+y(100000)+'" x2="'+(w-right)+'" y2="'+y(100000)+'" stroke="#a7b3a3" stroke-dasharray="4 4"/>';
  series.forEach(s=>{const points=s.curve.map((p,i)=>(left+i/Math.max(1,s.curve.length-1)*(w-left-right)).toFixed(1)+','+y(p.equity).toFixed(1)).join(' ');svg+='<polyline fill="none" stroke="'+s.color+'" stroke-width="2.2" points="'+points+'"/>';});
  const c=series[0].curve;
  svg+='<text x="'+left+'" y="'+(h-5)+'" fill="#65716a" font-size="11">'+esc(c[0]?.date)+'</text><text text-anchor="end" x="'+(w-right)+'" y="'+(h-5)+'" fill="#65716a" font-size="11">'+esc(c.at(-1)?.date)+'</text></svg>';
  $('chart').innerHTML=svg;
  $('legend').innerHTML=series.map(s=>'<span style="--series:'+s.color+'">'+esc(s.name)+'</span>').join('');
}
async function load(name) {
  const res=await fetch(document.body.dataset.source+name+'.json',{cache:'no-store'});
  if(!res.ok)throw new Error(name+' unavailable');
  return res.json();
}
async function start() {
  const [snapshot,evidence]=await Promise.allSettled([load('swing_desk'),load('swing_evidence')]);
  if(snapshot.status==='fulfilled'){
    desk=snapshot.value;expired=isExpired(desk.as_of);
    $('asof').textContent=new Date(desk.as_of+'T00:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});
    $('coverage').textContent=desk.fresh_count+' / '+desk.universe_count+' stocks on the same session';
    $('market').textContent=desk.market.risk_on?'Trend supportive':'Entries paused';
    $('count').textContent=expired?'Expired':desk.candidates.length;
    $('notice').textContent=expired?'Snapshot expired — entry bands and sizing are disabled. The weekday guard is conservative around exchange holidays.':
      desk.fresh_count<desk.universe_count*.9?'Partial data coverage — treat this watchlist as incomplete. All setups are unvalidated paper research.':
      'Research mode. No strategy has a validated edge yet. Review the evidence before planning a paper trade.';
    $('notice').classList.toggle('warning',expired||desk.fresh_count<desk.universe_count*.9);
    $('sizing-symbol').innerHTML='<option value="">Choose a setup</option>'+desk.candidates.map((p,i)=>'<option value="'+i+'">'+esc(p.symbol+' · '+names[p.strategy])+'</option>').join('');
    $('sizing-symbol').disabled=expired||!desk.candidates.length;
    renderCards();
    $('strategy').addEventListener('change',renderCards);
    $('sizing-symbol').addEventListener('change',()=>{const p=desk.candidates[Number($('sizing-symbol').value)];$('fill').value=$('sizing-symbol').value!==''&&p?p.close.toFixed(2):'';sizePosition();});
    ['capital','fill'].forEach(id=>$(id).addEventListener('input',sizePosition));
  }else{
    $('asof').textContent='Unavailable';$('coverage').textContent='Data refresh required';
    $('notice').textContent='Market snapshot could not be loaded. No trade plans are available. Retry after the data refresh.';$('notice').classList.add('warning');
    $('cards').innerHTML='<div class="empty"><strong>Data unavailable</strong><p>Entry plans stay hidden until a valid snapshot can be loaded.</p></div>';
  }
  $('download').href=document.body.dataset.source+'swing_evidence.json';
  if(evidence.status==='fulfilled')renderEvidence(evidence.value);
  else{$('history-note').textContent='Trade history unavailable until evidence loads.';$('evidence-note').textContent='Historical comparison unavailable. No performance claim can be made.';$('results').innerHTML='<tr><td colspan="7">Evidence has not loaded.</td></tr>';}
}
$('history-strategy').addEventListener('change', renderHistory);
start().catch(()=>{$('notice').textContent='Research data is invalid or incomplete. Reload after a successful refresh.';$('notice').classList.add('warning');$('cards').replaceChildren();});


// Expire plans even when a browser tab stays open overnight.
setInterval(() => {
  if (desk && !expired && isExpired(desk.as_of)) {
    expired = true;
    $('count').textContent = 'Expired';
    $('notice').textContent = 'The next-opening entry window has expired. Refresh for a new snapshot.';
    $('notice').classList.add('warning');
    $('sizing-symbol').disabled = true;
    renderCards();
    sizePosition();
  }
}, 30000);
