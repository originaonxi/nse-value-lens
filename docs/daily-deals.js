'use strict';
(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (typeof document === 'undefined') return;
  root.DailyDeals = api;
  const $ = id => document.getElementById(id);
  let payload = null, selected = null, failed = false;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = n => n.toLocaleString('en-IN', {maximumFractionDigits: 2});
  api.matches = (symbol, mode) => api.match(payload, symbol, mode, Date.now(), failed);
  api.showStock = symbol => {
    selected = symbol;
    const box = $('daily-stock-deals');
    if (!box) return;
    box.hidden = false;
    if (!payload) { box.textContent = 'NSE disclosure data is unavailable. Deal presence is unknown.'; return; }
    const rows = api.recent(payload, symbol);
    const current = ['bulk','block'].every(k => api.fresh(payload,k)) && !failed;
    box.innerHTML = '<strong>Bulk / block disclosures</strong><p>' +
      (current ? 'Latest report: '+esc(payload.as_of)+'. ' : 'A disclosure refresh needs checking. ') +
      'Large disclosed trades are context, not a buy signal. Buyers may also sell on the same day.</p>' +
      (rows.length ? '<ul>'+rows.slice(0,12).map(r => '<li>'+esc(r.date)+' · '+esc(r.kind)+' · '+esc(r.client)+' · <b>'+esc(r.side)+'</b> '+fmt(r.quantity)+' shares at ₹'+fmt(r.price)+'</li>').join('')+'</ul>' :
        '<p>'+(current?'No matching disclosures in the available last-seven-calendar-day reports.':'No matching saved rows; this does not establish that no deal occurred.')+'</p>')+
      '<a href="daily-market.html#deals">All disclosures, dates and source checks →</a>';
  };
  async function load() {
    try {
      const response = await fetch((document.body.dataset.source || '')+'daily_market.json', {cache:'no-store'});
      if (!response.ok) throw Error('Unavailable');
      const next = await response.json();
      if (!api.valid(next)) throw Error('Invalid snapshot');
      payload = next; failed = false;
    } catch { failed = true; }
    const note = $('daily-deal-note');
    if (note) {
      const complete = !failed && ['bulk','block'].every(k=>api.fresh(payload,k));
      note.textContent = payload ? (complete?'NSE reports: ':'NSE reports need checking: ')+payload.as_of+
        ' · Bulk '+(payload.bulk?.state || 'unavailable')+' · Block '+(payload.block?.state || 'unavailable')+
        '. Disclosure filters apply to the table below. Stock states remain the HH/HL classifications.' :
        'NSE disclosures unavailable. Filter matches are unknown; all stock charts remain available.';
      note.classList.toggle('warning', !complete);
    }
    if (selected) api.showStock(selected);
    document.dispatchEvent(new CustomEvent('daily-deals-ready'));
  }
  if ($('daily-deal-filter')) {
    load();
    setInterval(()=>{if(document.visibilityState==='visible')load();},300000);
  }
})(typeof window !== 'undefined' ? window : globalThis, function() {
  function valid(p) {
    return Boolean(p && p.version===1 && /^\d{4}-\d{2}-\d{2}$/.test(p.as_of||'') &&
      Number.isFinite(Date.parse(p.attempted_at)) && Array.isArray(p.recent_deals) &&
      ['bulk','block','market','indices'].every(k=>p[k] && ['fresh','stale','unavailable'].includes(p[k].state) &&
        (p[k].state!=='fresh' || p[k].as_of===p.as_of && Array.isArray(p[k].rows))));
  }
  function fresh(p, kind, now=Date.now()) {
    return Boolean(valid(p) && p[kind].state==='fresh' && p[kind].as_of===p.as_of &&
      now-Date.parse(p.attempted_at)>=-300000 && now-Date.parse(p.attempted_at)<36*3600000);
  }
  function recent(p, symbol) {
    if (!valid(p)) return [];
    const cutoff = new Date(Date.parse(p.as_of+'T00:00:00Z')-6*86400000).toISOString().slice(0,10);
    return p.recent_deals.filter(r=>(!symbol || r.symbol===symbol) && r.date>=cutoff && r.date<=p.as_of)
      .sort((a,b)=>b.date.localeCompare(a.date)||a.symbol.localeCompare(b.symbol));
  }
  function match(p, symbol, mode, now=Date.now(), failed=false) {
    if (!mode || mode==='ALL') return true;
    if (!valid(p) || failed) return false;
    if (mode==='recent') return recent(p,symbol).length>0;
    if (!['bulk','block','any'].includes(mode)) return false;
    const kinds = mode==='any'?['bulk','block']:[mode];
    return kinds.some(k=>fresh(p,k,now) && p[k].rows.some(r=>r.symbol===symbol));
  }
  return {valid, fresh, recent, match};
});
