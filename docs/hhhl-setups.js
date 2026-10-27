'use strict';
/* hhhl-setups.js: adds the daily-setups layer to the HH/HL page.
 * - overlay(): Supertrend, Bollinger (20,2) and VWAP-20 drawn on the existing price chart, matched by date.
 * - panel(): category, plan (buy / stop / next target), 5 indicator readings in words, Jev and hedge.
 * Data: daily_setups.json + daily_setups_series.json (built after each close by daily_setups.py). */
(function (root) {
  const isNum = v => typeof v === 'number' && Number.isFinite(v);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const rs = v => isNum(v) ? '₹' + v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '–';
  const COLOR = { supertrend: '#7c3aed', adx: '#d97706', rsi: '#2563eb', bollinger: '#0d9488', obv: '#db2777', vwap20: '#64748b' };
  const NAME = { supertrend: 'Supertrend', adx: 'ADX', rsi: 'RSI', bollinger: 'Bollinger', obv: 'OBV', vwap20: 'VWAP-20' };
  let setups = null, series = null, ready = null;

  function load(source, onReady) {
    if (ready) return ready;
    const get = f => fetch((source || '') + f, { cache: 'no-store' }).then(r => r.ok ? r.json() : Promise.reject(new Error(f + ' HTTP ' + r.status)));
    ready = Promise.all([get('daily_setups.json'), get('daily_setups_series.json')]).then(([d, s]) => {
      if (!Array.isArray(d.stocks) || s.as_of !== d.as_of) throw new Error('daily setups and chart series dates differ');
      setups = new Map(d.stocks.map(x => [x.symbol, x])); setups.meta = d; series = s.series || {};
      onReady && onReady();
    }).catch(() => { setups = null; series = null; });
    return ready;
  }

  function overlay(symbol, bars, x, y, lo, hi) {
    const s = series?.[symbol];
    if (!s || !bars?.length) return '';
    const idx = new Map(s.dates.map((d, i) => [d, i]));
    const inRange = v => isNum(v) && v >= lo && v <= hi;
    const path = (key, attrs) => {
      let d = '', pen = false;
      bars.forEach((b, i) => { const v = s[key]?.[idx.get(b.date)]; if (inRange(v)) { d += (pen ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1); pen = true; } else pen = false; });
      return d ? '<path d="' + d + '" fill="none" pointer-events="none" ' + attrs + '/>' : '';
    };
    let g = '<g class="setup-indicators">';
    g += path('bb_upper', 'stroke="#0d9488" stroke-width="1" opacity=".7"') + path('bb_lower', 'stroke="#0d9488" stroke-width="1" opacity=".7"') +
      path('bb_middle', 'stroke="#0d9488" stroke-width="1" stroke-dasharray="3 3" opacity=".5"');
    g += path('vwap20', 'stroke="#64748b" stroke-width="1.5" stroke-dasharray="6 3"');
    // Supertrend coloured per direction run: purple = up, orange = down
    let run = [], dir = null;
    const flush = () => { if (run.length > 1) g += '<polyline points="' + run.join(' ') + '" fill="none" pointer-events="none" stroke="' + (dir === 1 ? '#7c3aed' : '#c2410c') + '" stroke-width="2.2"/>'; run = []; };
    bars.forEach((b, i) => {
      const j = idx.get(b.date), v = s.supertrend?.[j], d = s.supertrend_dir?.[j];
      if (!inRange(v)) { flush(); return; }
      if (d !== dir) { flush(); dir = d; }
      run.push(x(i).toFixed(1) + ',' + y(v).toFixed(1));
    });
    flush();
    g += '<text x="24" y="31" font-size="10" pointer-events="none"><tspan fill="#7c3aed" font-weight="700">━ Supertrend</tspan><tspan fill="#5d6b63"> (purple up / orange down) </tspan><tspan fill="#0d9488" font-weight="700">  ━ Bollinger 20,2 </tspan><tspan fill="#64748b" font-weight="700">  ┅ VWAP-20</tspan></text>';
    return g + '</g>';
  }

  function panel(symbol) {
    if (!setups) return '';
    const s = setups.get(symbol);
    if (!s) return '<p class="muted">No daily setup row for ' + esc(symbol) + '.</p>';
    const cat = (setups.meta.categories || []).find(c => c.key === s.category) || {};
    const toneColor = cat.tone === 'bull' ? '#1f7a52' : cat.tone === 'bear' ? '#b4473c' : '#6b7770';
    const p = s.plan || {}, r = s.indicators || {};
    const levels = p.stop ? '<div style="display:flex;flex-wrap:wrap;gap:6px 18px;font-size:14px;margin:6px 0">' +
      '<span><b style="color:#1d4ed8">' + (p.side === 'long' ? 'Buy' : 'Bearish below') + '</b> ' + rs(p.entry) + '</span>' +
      '<span><b style="color:#b91c1c">Stop</b> ' + rs(p.stop) + ' (' + (p.risk_pct ?? '–') + '%)</span>' +
      '<span><b style="color:#15803d">Next target</b> ' + rs(p.next_target) + ' (' + (p.reward_risk?.[0] ?? '–') + 'R)</span>' +
      (p.targets?.length > 1 ? '<span><b style="color:#15803d">Then</b> ' + p.targets.slice(1).map(rs).join(' · ') + '</span>' : '') + '</div>' : '';
    const inds = ['supertrend', 'adx', 'rsi', 'bollinger', 'obv', 'vwap20'].filter(k => r[k]).map(k =>
      '<li style="border-left:4px solid ' + COLOR[k] + ';padding:2px 0 2px 8px;margin:4px 0;list-style:none"><b style="color:' + COLOR[k] + '">' + NAME[k] + ' · ' + esc(r[k].label) + '</b> ' + esc(r[k].words) + '</li>').join('');
    const j = s.jev || {}, h = s.hedge || {};
    return '<div class="setup-panel" style="border:1px solid #dfe5dc;border-radius:10px;padding:12px 14px;margin:10px 0;background:#fff">' +
      '<div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:center"><strong>Daily setup · ' + esc(setups.meta.as_of) + '</strong>' +
      '<span style="background:' + toneColor + ';color:#fff;border-radius:999px;padding:2px 10px;font-size:11px;font-weight:800;text-transform:uppercase">' + esc(cat.label || s.category) + '</span></div>' +
      '<p style="margin:6px 0;font-size:13px">' + esc(cat.meaning || '') + '</p>' + levels +
      (p.how ? '<p style="margin:4px 0;font-size:13px">' + esc(p.how) + '</p>' : '') +
      '<ul style="padding:0;margin:8px 0;font-size:13px">' + inds + '</ul>' +
      (j.words ? '<p style="margin:4px 0;font-size:13px"><b>Jev:</b> ' + esc(j.words) + '</p>' : '') +
      (h.words ? '<p style="margin:4px 0;font-size:13px"><b>' + esc(h.available ? 'Hedge · ' + h.name : 'Hedge') + ':</b> ' + esc(h.words) + '</p>' : '') +
      '<a href="setups.html?symbol=' + encodeURIComponent(symbol) + '">Full chart with RSI, ADX and OBV panels, sizing and option legs →</a></div>';
  }

  root.HHHLSetups = { load, overlay, panel };
})(typeof window !== 'undefined' ? window : globalThis);
