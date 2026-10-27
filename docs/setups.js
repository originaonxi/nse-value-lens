'use strict';
/* setups.js renders docs/daily_setups.json (one category per stock, 5 indicators, plan, Jev, hedge)
 * and docs/daily_setups_series.json (candles + indicator series for the chart).
 * Every number comes from those files. Strings are escaped before they reach innerHTML. */
(function () {
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const isNum = v => typeof v === 'number' && Number.isFinite(v);
  const fmt = (v, d = 2) => isNum(v) ? v.toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d }) : '–';
  const rs = (v, d = 2) => isNum(v) ? '₹' + fmt(v, d) : '–';
  const big = v => !isNum(v) ? '–' : Math.abs(v) >= 1e7 ? (v / 1e7).toFixed(2) + ' Cr' : Math.abs(v) >= 1e5 ? (v / 1e5).toFixed(2) + ' L' : fmt(v, 0);
  const IND = ['supertrend', 'adx', 'rsi', 'bollinger', 'obv'];
  const COLOR = { supertrend: '#7c3aed', adx: '#d97706', rsi: '#2563eb', bollinger: '#0d9488', obv: '#db2777', vwap20: '#64748b' };
  const SHORT = { supertrend: 'ST', adx: 'ADX', rsi: 'RSI', bollinger: 'BB', obv: 'OBV' };

  let data = null, series = null, seriesPromise = null, cat = null, selected = null;
  const catMeta = {};

  // ── load ──────────────────────────────────────────────────────────────
  function bust(url) { return url + '?t=' + Math.floor(Date.now() / 300000); }
  function validate(d) {
    if (!d || !/^\d{4}-\d{2}-\d{2}$/.test(d.as_of || '') || !Array.isArray(d.stocks) || d.stocks.length < 150 || !Array.isArray(d.categories))
      throw new Error('Incomplete daily setups snapshot');
    return d;
  }
  function loadSeries() {
    if (!seriesPromise) seriesPromise = fetch(bust(data.series_file || 'daily_setups_series.json')).then(r => {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(s => {
      if (s.as_of !== data.as_of) throw new Error('chart data is dated ' + s.as_of + ', list is ' + data.as_of);
      series = s.series; return series;
    });
    return seriesPromise;
  }

  // ── header, categories, guide ───────────────────────────────────────────
  function renderHeader() {
    const days = Math.round((Date.now() - Date.parse(data.as_of + 'T16:00:00+05:30')) / 864e5);
    $('su-date').textContent = new Date(data.as_of + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
    $('su-count').textContent = data.universe_count + ' stocks · ' + data.fno_count + ' in F&O' + (days > 4 ? ' · ' + days + ' days old' : '');
    const g = $('su-gate');
    g.className = 'su-gate ' + (data.market.gate_open ? 'open' : 'closed');
    g.textContent = data.market.words;
    const inp = data.inputs || {};
    const stale = Object.entries(inp).filter(([, v]) => v && v !== data.as_of);
    $('su-inputs').textContent = 'Inputs: price scan ' + (inp.hhhl_scan || '–') + ' · F&O ' + (inp.hhhl_fno || '–') + ' · Jev rank ' + (inp.jev_rank || '–') +
      ' · Jev brief ' + (inp.market_brief || '–') + ' · options ' + (inp.options_desk || '–') +
      (stale.length ? '. Older inputs keep their own date (' + stale.map(([k]) => k.replace('_', ' ')).join(', ') + ').' : '. All inputs match this session.');
  }
  function renderCats() {
    $('su-cats').innerHTML = data.categories.map(c => {
      catMeta[c.key] = c;
      return '<button class="su-cat" type="button" data-cat="' + esc(c.key) + '" data-tone="' + esc(c.tone) + '" aria-pressed="false"><strong>' + esc(c.label) + '</strong><b>' + esc(c.count) + '</b></button>';
    }).join('');
    $('su-cats').addEventListener('click', e => {
      const b = e.target.closest('[data-cat]'); if (!b) return;
      setCat(b.dataset.cat === cat ? null : b.dataset.cat);
    });
  }
  function setCat(key) {
    cat = key;
    document.querySelectorAll('.su-cat').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.cat === key)));
    const m = key && catMeta[key];
    $('su-meaning').innerHTML = m ? '<strong>' + esc(m.label) + ' (' + esc(m.count) + '):</strong> ' + esc(m.meaning)
      : '<strong>All categories.</strong> Click a category to filter. Rows are ordered bullish → bearish, then by conviction. Click any row to open its chart, indicators, plan and hedge.';
    const u = new URL(location.href);
    if (key) u.searchParams.set('cat', key); else u.searchParams.delete('cat');
    history.replaceState(null, '', u);
    renderRows();
  }
  function renderGuide() {
    const g = data.indicator_guide || {};
    $('su-guide').innerHTML = Object.entries(g).map(([k, v]) =>
      '<div class="su-card" style="--c:' + esc(v.color) + '"><h4>' + esc(v.name) + '</h4><p><strong>' + esc(v.covers) + '.</strong> ' + esc(v.how) + '</p></div>').join('');
    $('su-method').innerHTML = Object.entries(data.method || {}).map(([k, v]) => '<li><strong>' + esc(k.replace('_', ' ')) + ':</strong> ' + esc(v) + '</li>').join('');
    $('su-limits').innerHTML = (data.limitations || []).map(v => '<li>' + esc(v) + '</li>').join('');
  }

  // ── table ──────────────────────────────────────────────────────────────
  function dots(s) {
    const r = s.indicators || {};
    return '<span class="dots" aria-label="' + esc(IND.map(k => SHORT[k] + ' ' + (r[k]?.state || 'n/a')).join(', ')) + '">' +
      IND.map(k => '<span class="dot5" style="color:' + COLOR[k] + '" data-s="' + esc(r[k]?.state || 'neutral') + '" title="' + esc((r[k]?.label || '') + ' – ' + (data.indicator_guide?.[k]?.name || k)) + '"></span>').join('') + '</span>';
  }
  function rr2(s) { const r = s.plan?.reward_risk; return Array.isArray(r) && isNum(r[1]) ? r[1] : -1; }
  function filtered() {
    const q = $('su-search').value.trim().toLowerCase(), uni = $('su-universe').value, sort = $('su-sort').value;
    let rows = data.stocks.filter(s => (!cat || s.category === cat) &&
      (uni === 'all' || (uni === 'fno' ? s.fno : s.universe === 'Nifty 200')) &&
      (!q || s.symbol.toLowerCase().includes(q) || String(s.name || '').toLowerCase().includes(q)));
    const order = Object.fromEntries(data.categories.map((c, i) => [c.key, i]));
    const by = {
      conviction: (a, b) => (order[a.category] - order[b.category]) || ((b.conviction ?? -1) - (a.conviction ?? -1)),
      jev: (a, b) => (a.jev?.rank ?? 999) - (b.jev?.rank ?? 999),
      rr: (a, b) => rr2(b) - rr2(a),
      symbol: (a, b) => a.symbol.localeCompare(b.symbol),
    }[sort];
    return rows.sort((a, b) => by(a, b) || a.symbol.localeCompare(b.symbol));
  }
  function renderRows() {
    const rows = filtered();
    $('su-shown').textContent = rows.length + ' shown';
    if (!rows.length) { $('su-rows').innerHTML = '<tr><td colspan="9" class="su-empty">No stocks match.</td></tr>'; return; }
    $('su-rows').innerHTML = rows.map(s => {
      const p = s.plan || {}, c = catMeta[s.category] || {}, tone = c.tone;
      const level = !p.stop ? '<span class="muted">No trade</span>' :
        '<span class="num" style="color:var(--entry)">' + (p.side === 'long' ? 'Buy ' : 'Bear below ') + rs(p.entry) + '</span>';
      const ch = isNum(s.change_pct) ? '<small class="' + (s.change_pct >= 0 ? 'up' : 'down') + '">' + (s.change_pct >= 0 ? '+' : '') + fmt(s.change_pct) + '%</small>' : '';
      const jev = s.jev?.rank ? '#' + s.jev.rank + (s.jev.agrees === true ? ' ✓' : s.jev.agrees === false ? ' ✗' : '') : '–';
      const conv = isNum(s.conviction) ? '<span class="conv"><i><b style="width:' + Math.min(100, s.conviction) + '%"></b></i>' + s.conviction + '</span>' : '–';
      return '<tr data-sym="' + esc(s.symbol) + '" tabindex="0" aria-selected="' + (s.symbol === selected) + '">' +
        '<td class="su-sym"><strong>' + esc(s.symbol) + (s.fno ? '<span class="tag-f">F&amp;O</span>' : '') + '</strong><small><span class="su-badge" data-tone="' + esc(tone) + '" style="font-size:9px;padding:1px 6px">' + esc(c.label || s.category) + '</span> ' + esc(s.structure || '') + '</small></td>' +
        '<td class="num">' + rs(s.close) + '<br>' + ch + '</td>' +
        '<td>' + level + '</td>' +
        '<td class="num" style="color:var(--stop)">' + (p.stop ? rs(p.stop) + '<br><small>' + fmt(p.risk_pct, 1) + '% risk</small>' : '–') + '</td>' +
        '<td class="num" style="color:var(--tgt)">' + (p.next_target ? rs(p.next_target) + '<br><small>' + fmt(p.reward_risk?.[0], 1) + 'R</small>' : '–') + '</td>' +
        '<td>' + dots(s) + '</td><td class="num">' + esc(jev) + '</td><td>' + conv + '</td>' +
        '<td><small>' + esc(s.hedge?.available ? s.hedge.name : (s.fno ? 'Data incomplete' : 'Stop = hedge')) + '</small></td></tr>';
    }).join('');
  }

  // ── chart ──────────────────────────────────────────────────────────────
  function layers() { const o = {}; document.querySelectorAll('#su-toggles [data-layer]').forEach(i => o[i.dataset.layer] = i.checked); return o; }
  function poly(vals, xf, yf, attrs) {
    let d = '', pen = false;
    vals.forEach((v, i) => { if (isNum(v)) { d += (pen ? 'L' : 'M') + xf(i).toFixed(1) + ' ' + yf(v).toFixed(1); pen = true; } else pen = false; });
    return d ? '<path d="' + d + '" fill="none" ' + attrs + '/>' : '';
  }
  function slice(ser, n) {
    const out = {}, start = Math.max(0, ser.dates.length - n);
    for (const [k, v] of Object.entries(ser)) out[k] = Array.isArray(v) && k !== 'swings' ? v.slice(start) : v;
    out.swings = (ser.swings || []).filter(p => p.d >= out.dates[0]);
    return out;
  }
  function drawChart(s, full) {
    const L = layers(), S = slice(full, Number($('su-window').value) || 70), N = S.dates.length;
    const W = 1200, left = 14, axis = 1090, right = W - axis, plotR = axis - 70;
    const panels = [];
    let y0 = 30; const priceH = 330; const price = { top: y0, bot: y0 + priceH }; y0 += priceH;
    if (L.volume) { panels.push(['volume', y0 + 8, y0 + 62]); y0 += 62; }
    if (L.rsi) { panels.push(['rsi', y0 + 22, y0 + 102]); y0 += 102; }
    if (L.adx) { panels.push(['adx', y0 + 22, y0 + 102]); y0 += 102; }
    if (L.obv) { panels.push(['obv', y0 + 22, y0 + 102]); y0 += 102; }
    const H = y0 + 28;
    const step = (plotR - left) / N, x = i => left + step * (i + .5);
    const p = s.plan || {};
    const lv = [p.entry, p.stop, ...(p.targets || [])].filter(isNum);
    const pool = [...S.h, ...S.l, ...(L.plan ? lv : []), ...(L.bollinger ? [...S.bb_upper, ...S.bb_lower] : []), ...(L.supertrend ? S.supertrend : [])].filter(isNum);
    let lo = Math.min(...pool), hi = Math.max(...pool); const pad = (hi - lo) * .06 || 1; lo -= pad; hi += pad;
    const y = v => price.top + (hi - v) / (hi - lo) * (price.bot - price.top);
    let g = '<svg viewBox="0 0 ' + W + ' ' + H + '" data-left="' + left + '" data-step="' + step + '" data-w="' + W + '" role="img" aria-label="' + esc(s.symbol) + ' chart with Supertrend, Bollinger, VWAP, RSI, ADX and OBV"><rect width="' + W + '" height="' + H + '" fill="#fff"/>';
    for (let i = 0; i <= 5; i++) { const v = lo + (hi - lo) * i / 5; g += '<line x1="' + left + '" x2="' + axis + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="#eef2ee"/><text x="' + (axis + 6) + '" y="' + (y(v) + 4) + '" font-size="11" fill="#7a857f">' + fmt(v, v > 999 ? 0 : 1) + '</text>'; }
    g += '<rect x="' + plotR + '" y="' + price.top + '" width="' + (axis - plotR) + '" height="' + priceH + '" fill="#f4f7f3"/><text x="' + (plotR + (axis - plotR) / 2) + '" y="' + (price.top - 8) + '" font-size="10" text-anchor="middle" fill="#7a857f">PLAN</text>';
    if (L.bollinger) {
      const up = S.bb_upper.map((v, i) => isNum(v) ? x(i).toFixed(1) + ',' + y(v).toFixed(1) : null).filter(Boolean);
      const dn = S.bb_lower.map((v, i) => isNum(v) ? x(i).toFixed(1) + ',' + y(v).toFixed(1) : null).filter(Boolean).reverse();
      if (up.length) g += '<polygon points="' + up.concat(dn).join(' ') + '" fill="#0d9488" opacity=".07"/>';
      g += poly(S.bb_upper, x, y, 'stroke="#0d9488" stroke-width="1" opacity=".75"') + poly(S.bb_lower, x, y, 'stroke="#0d9488" stroke-width="1" opacity=".75"') +
        poly(S.bb_middle, x, y, 'stroke="#0d9488" stroke-width="1" stroke-dasharray="3 3" opacity=".6"');
    }
    if (L.vwap) g += poly(S.vwap20, x, y, 'stroke="#64748b" stroke-width="1.6" stroke-dasharray="6 3"');
    S.c.forEach((c, i) => {
      const o = S.o[i], col = c >= o ? '#2b8666' : '#c26859';
      g += '<line x1="' + x(i) + '" x2="' + x(i) + '" y1="' + y(S.h[i]) + '" y2="' + y(S.l[i]) + '" stroke="' + col + '"/><rect x="' + (x(i) - step * .3) + '" width="' + Math.max(1, step * .6) + '" y="' + Math.min(y(o), y(c)) + '" height="' + Math.max(1.2, Math.abs(y(o) - y(c))) + '" fill="' + col + '"/>';
    });
    if (L.supertrend) {
      // one colour per direction run so the line's colour tells the trend at a glance
      let run = [], dir = null;
      const flush = () => { if (run.length > 1) g += '<polyline points="' + run.join(' ') + '" fill="none" stroke="' + (dir === 1 ? '#7c3aed' : '#c2410c') + '" stroke-width="2.2"/>'; run = []; };
      S.supertrend.forEach((v, i) => {
        const d = S.supertrend_dir[i];
        if (!isNum(v)) { flush(); return; }
        if (d !== dir) { flush(); dir = d; }
        run.push(x(i).toFixed(1) + ',' + y(v).toFixed(1));
      });
      flush();
    }
    if (L.swings) (S.swings || []).forEach(sw => {
      const i = S.dates.indexOf(sw.d); if (i < 0) return;
      const hiK = sw.k === 'high', yy = y(sw.p) + (hiK ? -10 : 16), bull = ['HH', 'HL'].includes(sw.t), bear = ['LH', 'LL'].includes(sw.t);
      g += '<text x="' + x(i) + '" y="' + yy + '" font-size="10" font-weight="800" text-anchor="middle" fill="' + (bull ? '#1f7a52' : bear ? '#b4473c' : '#6b7770') + '">' + esc(sw.t || '') + '</text>';
    });
    if (L.plan && p.stop) {
      const tags = [];
      const line = (v, col, label, dash) => { if (!isNum(v)) return; g += '<line x1="' + x(Math.max(0, N - 25)) + '" x2="' + axis + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="' + col + '" stroke-width="1.6" stroke-dasharray="' + dash + '"/>'; tags.push([v, col, label]); };
      line(p.entry, '#1d4ed8', p.side === 'long' ? 'BUY' : 'BEAR BELOW', '0');
      line(p.stop, '#b91c1c', 'STOP', '6 3');
      (p.targets || []).forEach((t, i) => line(t, '#15803d', 'T' + (i + 1), '3 3'));
      tags.sort((a, b) => y(a[0]) - y(b[0]));
      let last = -99;
      tags.forEach(([v, col, label]) => {
        const ty = Math.max(y(v), last + 15); last = ty;
        g += '<rect x="' + (plotR + 3) + '" y="' + (ty - 7) + '" width="' + (axis - plotR - 6) + '" height="14" rx="3" fill="' + col + '"/><text x="' + (plotR + (axis - plotR) / 2) + '" y="' + (ty + 3.5) + '" font-size="9" font-weight="700" text-anchor="middle" fill="#fff">' + label + ' ' + fmt(v, v > 999 ? 0 : 1) + '</text>';
      });
    }
    // last close tag
    const lc = S.c[N - 1];
    g += '<rect x="' + (axis + 2) + '" y="' + (y(lc) - 9) + '" width="' + (right - 4) + '" height="18" rx="3" fill="#182c24"/><text x="' + (axis + right / 2) + '" y="' + (y(lc) + 4) + '" font-size="11" font-weight="700" text-anchor="middle" fill="#fff">' + fmt(lc, lc > 999 ? 0 : 1) + '</text>';
    // sub-panels
    for (const [name, top, bot] of panels) {
      const span = (vals, fixed) => { const f = vals.filter(isNum); let a = fixed ? fixed[0] : Math.min(...f), b = fixed ? fixed[1] : Math.max(...f); if (a === b) b = a + 1; return [a, b]; };
      const py = (a, b) => v => bot - (v - a) / (b - a) * (bot - top);
      g += '<line x1="' + left + '" x2="' + axis + '" y1="' + (top - 14) + '" y2="' + (top - 14) + '" stroke="#e3e9e3"/>';
      if (name === 'volume') {
        const [, b] = span(S.v, null), f = v => bot - v / b * (bot - top);
        S.v.forEach((v, i) => g += '<rect x="' + (x(i) - step * .3) + '" width="' + Math.max(1, step * .6) + '" y="' + f(v) + '" height="' + (bot - f(v)) + '" fill="' + (S.c[i] >= S.o[i] ? '#9cc4b0' : '#ddaa9f') + '"/>');
        g += '<text x="' + left + '" y="' + (top + 4) + '" font-size="10" fill="#7a857f">VOLUME</text>';
      } else if (name === 'rsi') {
        const f = py(0, 100);
        [[70, '#c2410c'], [55, '#93c5a8'], [45, '#e5a99c'], [30, '#1f7a52']].forEach(([lv, c]) => g += '<line x1="' + left + '" x2="' + axis + '" y1="' + f(lv) + '" y2="' + f(lv) + '" stroke="' + c + '" stroke-dasharray="3 3"/><text x="' + (axis + 6) + '" y="' + (f(lv) + 4) + '" font-size="10" fill="#7a857f">' + lv + '</text>');
        g += poly(S.rsi, x, f, 'stroke="#2563eb" stroke-width="1.8"');
        g += '<text x="' + left + '" y="' + (top - 2) + '" font-size="11" font-weight="700" fill="#2563eb">RSI (14) ' + fmt(S.rsi[N - 1], 1) + ' · momentum: above 55 buyers, below 45 sellers</text>';
      } else if (name === 'adx') {
        const [, b] = span([...S.adx, ...S.plus_di, ...S.minus_di], null), f = py(0, Math.max(b, 40));
        [20, 25].forEach(lv => g += '<line x1="' + left + '" x2="' + axis + '" y1="' + f(lv) + '" y2="' + f(lv) + '" stroke="#e8c48c" stroke-dasharray="3 3"/><text x="' + (axis + 6) + '" y="' + (f(lv) + 4) + '" font-size="10" fill="#7a857f">' + lv + '</text>');
        g += poly(S.plus_di, x, f, 'stroke="#1f7a52" stroke-width="1.1" opacity=".8"') + poly(S.minus_di, x, f, 'stroke="#b4473c" stroke-width="1.1" opacity=".8"') + poly(S.adx, x, f, 'stroke="#d97706" stroke-width="2"');
        g += '<text x="' + left + '" y="' + (top - 2) + '" font-size="11" font-weight="700" fill="#d97706">ADX (14) ' + fmt(S.adx[N - 1], 1) + ' · strength: above 25 strong, below 20 choppy · <tspan fill="#1f7a52">+DI ' + fmt(S.plus_di[N - 1], 0) + '</tspan> <tspan fill="#b4473c">−DI ' + fmt(S.minus_di[N - 1], 0) + '</tspan></text>';
      } else if (name === 'obv') {
        const [a, b] = span([...S.obv, ...S.obv_ema20], null), f = py(a, b);
        g += poly(S.obv_ema20, x, f, 'stroke="#64748b" stroke-width="1.2" stroke-dasharray="4 3"') + poly(S.obv, x, f, 'stroke="#db2777" stroke-width="1.8"');
        g += '<text x="' + left + '" y="' + (top - 2) + '" font-size="11" font-weight="700" fill="#db2777">OBV ' + big(S.obv[N - 1]) + ' vs 20-day avg ' + big(S.obv_ema20[N - 1]) + ' · money flow: OBV above the dashed average = accumulation</text>';
      }
    }
    [0, Math.floor(N / 3), Math.floor(2 * N / 3), N - 1].forEach((i, n) => g += '<text x="' + x(i) + '" y="' + (H - 8) + '" font-size="10" fill="#7a857f" text-anchor="' + (n === 0 ? 'start' : n === 3 ? 'end' : 'middle') + '">' + esc(S.dates[i]) + '</text>');
    g += '<line id="su-hair" x1="0" x2="0" y1="' + price.top + '" y2="' + (H - 22) + '" stroke="#5d6b63" stroke-dasharray="3 3" opacity="0"/>';
    g += '<text x="' + left + '" y="18" font-size="11" fill="#5d6b63"><tspan fill="#7c3aed" font-weight="700">━ Supertrend</tspan> (purple = up, orange = down)   <tspan fill="#0d9488" font-weight="700">▒ Bollinger 20,2</tspan>   <tspan fill="#64748b" font-weight="700">┅ VWAP-20</tspan>   <tspan fill="#1d4ed8" font-weight="700">━ Buy</tspan> <tspan fill="#b91c1c" font-weight="700">┅ Stop</tspan> <tspan fill="#15803d" font-weight="700">┅ Targets</tspan></text>';
    $('su-chart').innerHTML = g + '</svg>';
    $('su-chart').dataset.n = N;
    readout(S, N - 1);
    $('su-chart').onpointermove = ev => {
      const svg = $('su-chart').querySelector('svg'); if (!svg) return;
      const r = svg.getBoundingClientRect(), px = (ev.clientX - r.left) * W / r.width;
      const i = Math.max(0, Math.min(N - 1, Math.floor((px - left) / step)));
      const h = $('su-hair'); h.setAttribute('x1', x(i)); h.setAttribute('x2', x(i)); h.setAttribute('opacity', '.6');
      readout(S, i);
    };
    $('su-chart').onpointerleave = () => { $('su-hair')?.setAttribute('opacity', '0'); readout(S, N - 1); };
  }
  function readout(S, i) {
    $('su-readout').textContent = S.dates[i] + '  O ' + fmt(S.o[i]) + '  H ' + fmt(S.h[i]) + '  L ' + fmt(S.l[i]) + '  C ' + fmt(S.c[i]) + '  Vol ' + big(S.v[i]) +
      '\nST ' + fmt(S.supertrend[i]) + (S.supertrend_dir[i] === 1 ? ' (up)' : S.supertrend_dir[i] === -1 ? ' (down)' : '') +
      '  BB ' + fmt(S.bb_lower[i]) + '–' + fmt(S.bb_upper[i]) + '  VWAP20 ' + fmt(S.vwap20[i]) + '  RSI ' + fmt(S.rsi[i], 1) + '  ADX ' + fmt(S.adx[i], 1) + '  OBV ' + big(S.obv[i]);
  }

  // ── detail panels ──────────────────────────────────────────────────────
  function indicatorCards(s) {
    const r = s.indicators || {};
    return [...IND, 'vwap20'].filter(k => r[k]).map(k => {
      const v = r[k], gd = data.indicator_guide?.[k] || {};
      const val = k === 'bollinger' ? fmt(v.value, 0) + '%B' : k === 'obv' ? big(v.value) : k === 'supertrend' || k === 'vwap20' ? rs(v.value) : fmt(v.value, k === 'adx' || k === 'rsi' ? 1 : 2);
      return '<div class="su-card" style="--c:' + COLOR[k] + '"><h4>' + esc(gd.name || k) + ' · ' + esc(gd.covers || '') + '</h4><span class="v">' + esc(val) + '</span><span class="lab" data-s="' + esc(v.state) + '">' + esc(v.label) + '</span><p>' + esc(v.words) + '</p></div>';
    }).join('');
  }
  function planPanel(s) {
    const p = s.plan;
    if (!p) return '<h3>Plan</h3><p>' + esc(s.summary) + '</p>';
    if (!p.stop) return '<h3>Plan: no trade</h3><p>' + esc(p.how) + '</p><div class="su-levels"><span class="k">Bullish above</span><span class="num">' + rs(s.trigger) + '</span><small>closing trigger</small><span class="k">Bearish below</span><span class="num">' + rs(s.structure_exit) + '</span><small>structure exit</small></div>';
    const long = p.side === 'long', rows = [
      ['entry', long ? 'Buy at' : 'Bearish below', p.entry, long ? 'entry' : 'today\'s close'],
      ['stop', 'Stop loss', p.stop, fmt(p.risk_pct, 1) + '% · ' + rs(p.risk) + '/share'],
      ...(p.targets || []).map((t, i) => ['tgt', (i ? 'Target ' : 'NEXT target ') + (i + 1), t, fmt(p.reward_risk?.[i], 1) + 'R · ' + (long ? '+' : '−') + fmt(Math.abs(t / p.entry - 1) * 100, 1) + '%']),
    ];
    return '<h3>' + (long ? 'Trade plan: buy' : 'Trade plan: bearish / exit longs') + '</h3><div class="su-levels">' +
      rows.map(([c, k, v, n]) => '<span class="k ' + c + '">' + esc(k) + '</span><span class="num"><strong>' + rs(v) + '</strong></span><small>' + esc(n) + '</small>').join('') + '</div>' +
      '<p>' + esc(p.how) + '</p>' + (p.sizing ? '<p><strong>Position size.</strong> ' + esc(p.sizing.words) + '</p>' : '') +
      (long && !data.market.gate_open ? '<p style="color:var(--bear)"><strong>Market gate closed:</strong> paper plan only until Nifty closes above its 200-day average.</p>' : '');
  }
  function hedgePanel(s) {
    const h = s.hedge;
    if (!h) return '<h3>Hedge</h3><p class="muted">No plan, so no hedge.</p>';
    if (!h.available) return '<h3>Hedge</h3><p>' + esc(h.words) + '</p>';
    const legs = '<table class="su-legs"><tbody>' + (h.legs || []).map(l => '<tr><td class="' + esc(l.side) + '">' + esc(l.side) + '</td><td>' + esc(fmt(l.strike, l.strike % 1 ? 1 : 0)) + ' ' + esc(l.type) + '</td><td class="num">≈ ' + rs(l.premium) + '</td></tr>').join('') + '</tbody></table>';
    const kv = [['Lot', h.lot], ['Expiry', h.expiry + ' (' + h.days_to_expiry + 'd)'], ['ATM IV', fmt(h.atm_iv_pct, 1) + '%'],
      [h.net_debit != null ? 'Cost / lot' : 'Credit / lot', h.net_debit != null ? rs(h.max_loss, 0) : rs(h.max_profit, 0)],
      ['Max profit / lot', rs(h.max_profit, 0)], ['Max loss / lot', rs(h.max_loss, 0)], ['Breakeven', h.breakeven != null ? fmt(h.breakeven, 1) : h.range ? h.range.join('–') : '–'],
      ['OI walls', (h.put_wall ?? '–') + ' put / ' + (h.call_wall ?? '–') + ' call']];
    return '<h3>Options setup: ' + esc(h.name) + '</h3>' + legs + '<div class="su-kv">' + kv.map(([k, v]) => '<span>' + esc(k) + ' <b>' + esc(v) + '</b></span>').join('') + '</div><p>' + esc(h.words) + '</p>' +
      (h.holder ? '<p><strong>' + esc(h.holder.name) + ':</strong> ' + esc(h.holder.words) + '</p>' : '') + '<p class="muted" style="font-size:11px">' + esc(h.pricing) + '</p>';
  }
  function jevPanel(s) {
    const j = s.jev || {};
    if (!j.available) return '<h3>Jev</h3><p>' + esc(j.words || 'No Jev view for this stock.') + '</p>';
    const kv = [['Rank', j.rank ? '#' + j.rank + ' / ' + j.of : '–'], ['Score', fmt(j.composite, 2)], ['Direction', j.direction || '–'], ['Regime', String(j.regime || '–').replace('_', ' ')],
      ['Confidence', isNum(j.confidence) ? Math.round(j.confidence * 100) + '%' : '–'], ['News context', j.context || '–'], ['Event risk', j.event_risk || '–']];
    const verdict = j.agrees === true ? '<p style="color:var(--bull)"><strong>Jev agrees</strong> with this category.</p>' : j.agrees === false ? '<p style="color:var(--bear)"><strong>Jev disagrees</strong>: treat as lower conviction.</p>' : '';
    const c = s.indicator_counts || {};
    return '<h3>Jev ranking &amp; agreement</h3><div class="su-kv">' + kv.map(([k, v]) => '<span>' + esc(k) + ' <b>' + esc(v) + '</b></span>').join('') + '</div>' + verdict + '<p>' + esc(j.words) + '</p>' +
      '<p><strong>Indicators:</strong> ' + (c.bull ?? 0) + ' bullish · ' + (c.bear ?? 0) + ' bearish · ' + (c.neutral ?? 0) + ' neutral. <strong>Conviction ' + esc(s.conviction ?? '–') + '/100.</strong></p>';
  }
  function openStock(sym, scroll) {
    const s = data.stocks.find(x => x.symbol === sym); if (!s) return;
    selected = sym;
    document.querySelectorAll('#su-rows tr[data-sym]').forEach(tr => tr.setAttribute('aria-selected', String(tr.dataset.sym === sym)));
    const c = catMeta[s.category] || {};
    $('su-detail').hidden = false;
    $('su-dtitle').textContent = s.symbol + ' / ' + (s.name || '');
    $('su-dsub').textContent = [s.sector, s.universe, s.fno ? 'F&O lot ' + s.lot : 'cash only', 'close ' + rs(s.close) + ' on ' + s.data_date, 'ATR ' + rs(s.atr), 'structure ' + (s.structure || '–')].filter(Boolean).join(' · ');
    const b = $('su-dbadge'); b.textContent = c.label || s.category; b.dataset.tone = c.tone || 'neutral';
    $('su-dsummary').textContent = s.summary;
    $('su-inds').innerHTML = indicatorCards(s);
    $('su-plan').innerHTML = planPanel(s); $('su-hedge').innerHTML = hedgePanel(s); $('su-jev').innerHTML = jevPanel(s);
    $('su-hhhl-link').href = 'hhhl.html?symbol=' + encodeURIComponent(s.symbol);
    $('su-chart').innerHTML = '<p class="muted">Loading chart…</p>';
    loadSeries().then(ser => { if (selected !== sym) return; ser[sym] ? drawChart(s, ser[sym]) : ($('su-chart').innerHTML = '<p class="muted">No chart data for this stock.</p>'); })
      .catch(err => { $('su-chart').innerHTML = '<p class="muted">Chart unavailable: ' + esc(err.message) + '</p>'; });
    const u = new URL(location.href); u.searchParams.set('symbol', sym); history.replaceState(null, '', u);
    if (scroll) $('su-detail').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // ── wiring ─────────────────────────────────────────────────────────────
  function wire() {
    ['su-search', 'su-universe', 'su-sort'].forEach(id => $(id).addEventListener('input', renderRows));
    const rows = $('su-rows');
    rows.addEventListener('click', e => { const tr = e.target.closest('tr[data-sym]'); if (tr) openStock(tr.dataset.sym, true); });
    rows.addEventListener('keydown', e => { if (e.key !== 'Enter' && e.key !== ' ') return; const tr = e.target.closest('tr[data-sym]'); if (tr) { e.preventDefault(); openStock(tr.dataset.sym, true); } });
    $('su-toggles').addEventListener('change', () => { if (selected && series?.[selected]) drawChart(data.stocks.find(x => x.symbol === selected), series[selected]); });
  }
  fetch(bust('daily_setups.json')).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }).then(d => {
    data = validate(d);
    renderHeader(); renderCats(); renderGuide(); wire();
    const q = new URLSearchParams(location.search);
    setCat(catMeta[q.get('cat')] ? q.get('cat') : null);
    const first = q.get('symbol') && data.stocks.some(s => s.symbol === q.get('symbol')) ? q.get('symbol')
      : (data.stocks.find(s => s.category === 'breakout_today') || data.stocks.find(s => s.category === 'ready_to_break') || data.stocks[0]).symbol;
    openStock(first, false);
  }).catch(err => {
    $('su-gate').className = 'su-gate closed';
    $('su-gate').textContent = 'Daily setups unavailable: ' + err.message + '. Nothing is shown rather than an old or partial list.';
    $('su-rows').innerHTML = '<tr><td colspan="9" class="su-empty">No data.</td></tr>';
  });
})();
