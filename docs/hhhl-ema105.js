'use strict';
/* hhhl-ema105.js: the Nifty 50 setup #1 run on every F&O stock, as its own section of the HH/HL page.
 * Setup: 2-hour close above EMA 105 + ADX>20 + Supertrend(10,3) up + yesterday's daily close above daily EMA 50;
 * TOP exit when RSI(14) reaches 68 then falls 5; EXIT on a 2-hour close below EMA 105. Long only.
 * Data: fno_ema105.json (built after each close by fno_ema105.py). Chart: VLChart (same candle style as HH/HL).
 * All text goes through textContent. */
(function () {
  const $ = id => document.getElementById(id);
  const isNum = v => typeof v === 'number' && Number.isFinite(v);
  const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
  const n0 = v => isNum(v) ? v.toLocaleString('en-IN', { maximumFractionDigits: 0 }) : '–';
  const n2 = v => isNum(v) ? v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '–';
  const sg = (v, d) => isNum(v) ? (v > 0 ? '+' : '') + v.toLocaleString('en-IN', { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }) : '–';
  const pc = v => isNum(v) ? v.toFixed(1) + '%' : '–';
  const tone = v => isNum(v) ? (v > 0 ? 'pos' : v < 0 ? 'neg' : '') : '';
  const STATE_CLS = { BUY: 'buy', TOP: 'top', HOLD: 'hold', EXIT: 'exit', WAIT: 'wait', OUT: 'out' };
  let D = null, view = { state: 'ALL', q: '', sort: 'state', sel: null };

  function td(tr, txt, cls) { const c = el('td', cls || null, txt); tr.appendChild(c); return c; }

  function head() {
    const s = D.summary, ref = D.nifty_reference;
    $('e105-asof').textContent = 'Last 2-hour candle ' + (D.last_candle || '–') + ' IST · ' + D.covered + ' of ' + D.universe +
      ' F&O stocks · contract month ' + (D.contract_month || '–');
    const ul = $('e105-rules'); ul.textContent = '';
    D.rules.forEach(r => ul.appendChild(el('li', null, r)));
    const k = $('e105-kpis'); k.textContent = '';
    const kpi = (label, val, sub, cls) => {
      const b = el('div', 'e105-kpi' + (cls ? ' ' + cls : '')); b.appendChild(el('span', null, label));
      b.appendChild(el('strong', null, val)); if (sub) b.appendChild(el('small', null, sub)); k.appendChild(b);
    };
    kpi('All stocks together', pc(s.win) + ' win', n0(s.trades) + ' trades · PF ' + n2(s.pf_pct) + ' · avg ' + sg(s.avg_trade_pct, 2) + '% a trade', s.pf_pct > 1 ? 'pos' : 'neg');
    kpi('Typical stock', pc(s.median_win) + ' win', 'median PF ' + n2(s.median_pf));
    kpi('Stocks that made money', s.pf_above_1 + ' of ' + s.with_5_trades, 'PF above 1');
    kpi('Held up on unseen part', String(s.robust), 'profit in both the tested and the unseen part, 8+ trades');
    kpi('Stocks at 70%+ win', String(s.win_70), s.win_60 + ' at 60%+');
    if (ref) kpi('Nifty 50 (where it was found)', pc(ref.all.win) + ' win', ref.all.n + ' trades · PF ' + n2(ref.all.pf) + ' · ' + sg(ref.all.net, 0) + ' pts', 'ref');
    $('e105-honest').textContent = 'The setup was found on the Nifty 50 index (' + (ref ? pc(ref.all.win) + ' win, PF ' + n2(ref.all.pf) : '–') +
      '). On individual stocks it is much weaker: ' + pc(s.win) + ' of ' + n0(s.trades) + ' trades won, and ' + pc(s.unseen_win) +
      ' on the unseen part. Use the per-stock numbers below: it works on some stocks and loses on others.';
    const cards = $('e105-states'); cards.textContent = '';
    [['ALL', 'All', D.covered]].concat(Object.keys(D.states).map(k2 => [k2, k2, D.counts[k2] || 0])).forEach(([key, label, count]) => {
      const b = el('button', 'e105-state ' + (STATE_CLS[key] || 'all') + (view.state === key ? ' active' : ''));
      b.type = 'button'; b.dataset.state = key; b.setAttribute('aria-pressed', String(view.state === key));
      b.appendChild(el('span', null, label)); b.appendChild(el('strong', null, String(count)));
      if (D.states[key]) b.title = D.states[key];
      b.addEventListener('click', () => { view.state = key; head(); table(); });
      cards.appendChild(b);
    });
  }

  function rowsNow() {
    const q = view.q.trim().toUpperCase();
    let rows = D.rows.filter(r => (view.state === 'ALL' || r.state === view.state) &&
      (!q || r.symbol.includes(q) || (r.name || '').toUpperCase().includes(q) || (r.sector || '').toUpperCase().includes(q)));
    const by = {
      state: null,
      pf: (a, b) => (b.all.pf || 0) - (a.all.pf || 0),
      win: (a, b) => (b.all.win || 0) - (a.all.win || 0),
      net: (a, b) => (b.all.net_pct || 0) - (a.all.net_pct || 0),
      unseen: (a, b) => (b.os.pf || 0) - (a.os.pf || 0),
      symbol: (a, b) => a.symbol.localeCompare(b.symbol),
    }[view.sort];
    if (by) rows = rows.slice().sort(by);
    return rows;
  }

  function table() {
    const tb = $('e105-rows'); tb.textContent = '';
    const rows = rowsNow();
    $('e105-count').textContent = rows.length + ' of ' + D.covered + ' stocks shown. Click a stock for its 2-hour chart and trades.';
    rows.forEach(r => {
      const a = r.all, tr = el('tr', r.symbol === view.sel ? 'selected' : null);
      tr.tabIndex = 0; tr.dataset.symbol = r.symbol;
      const c0 = td(tr, ''); c0.appendChild(el('b', null, r.symbol)); c0.appendChild(el('small', null, (r.name || '') + (r.sector ? ' · ' + r.sector : '')));
      const cs = td(tr, ''); cs.appendChild(el('span', 'e105-badge ' + STATE_CLS[r.state], r.state + (r.top_armed ? ' · TOP armed' : '')));
      td(tr, n2(r.close), 'num'); td(tr, n2(r.ema), 'num'); td(tr, n0(r.rsi), 'num'); td(tr, n0(r.adx), 'num');
      td(tr, String(a.n), 'num'); td(tr, pc(a.win), 'num ' + (a.win >= 60 ? 'pos' : '')); td(tr, n2(a.pf), 'num ' + (a.pf > 1 ? 'pos' : 'neg'));
      td(tr, sg(a.net, 0), 'num ' + tone(a.net)); td(tr, sg(a.net_pct, 1) + '%', 'num ' + tone(a.net_pct)); td(tr, n0(a.dd), 'num');
      td(tr, r.os.n ? pc(r.os.win) + ' · ' + n2(r.os.pf) : '–', 'num ' + ((r.os.pf || 0) > 1 ? 'pos' : 'neg'));
      td(tr, r.per_lot != null ? '₹' + sg(r.per_lot, 0) : '–', 'num ' + tone(r.per_lot));
      const open = () => detail(r.symbol, true);
      tr.addEventListener('click', open);
      tr.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
      tb.appendChild(tr);
    });
  }

  function partRow(tb, label, s, extra) {
    const tr = el('tr', extra || null);
    td(tr, label); td(tr, String(s.n || 0), 'num'); td(tr, pc(s.win), 'num'); td(tr, n2(s.pf), 'num');
    td(tr, sg(s.net, 2), 'num ' + tone(s.net)); td(tr, n2(s.dd), 'num'); tb.appendChild(tr);
  }

  function detail(sym, scroll) {
    const r = D.rows.find(x => x.symbol === sym);
    if (!r) return;
    view.sel = sym;
    Array.from($('e105-rows').children).forEach(tr => tr.classList.toggle('selected', tr.dataset.symbol === sym));
    const box = $('e105-detail'); box.hidden = false;
    $('e105-d-title').textContent = r.symbol + ' · ' + (r.name || '');
    const b = $('e105-d-badge'); b.className = 'e105-badge big ' + STATE_CLS[r.state]; b.textContent = r.state;
    $('e105-d-note').textContent = r.note;
    const ch = $('e105-d-checks'); ch.textContent = '';
    r.checks.forEach(c => { const li = el('li', c.ok ? 'ok' : 'no'); li.appendChild(el('b', null, c.ok ? '✓ ' : '✗ ')); li.appendChild(document.createTextNode(c.name + ' — ' + c.v)); ch.appendChild(li); });
    ch.appendChild(el('li', 'info', 'RSI ' + n0(r.rsi) + ' · price ' + n2(r.atr_from_ema) + ' ATR from EMA 105 · lot ' + (r.lot || '–')));

    const c = r.chart, bars = c.t.map((t, i) => ({ date: t, open: c.o[i], high: c.h[i], low: c.l[i], close: c.c[i] }));
    const COL = { buy: '#2b8666', top: '#d97706', exit: '#64748b' };
    const markers = r.markers.map(m => ({ date: m[0], price: m[2], color: COL[m[1]], down: m[1] !== 'buy',
      label: (m[1] === 'buy' ? 'BUY ' : m[1] === 'top' ? 'TOP ' : 'EXIT ') + m[0] + ' at ' + n2(m[2]) + (m[3] != null ? ' (' + sg(m[3], 2) + '/share)' : '') }));
    const zones = [{ price: r.ema, color: '#2563eb', label: 'EMA 105 ' + n2(r.ema) }];
    if (window.VLChart) window.VLChart.render($('e105-chart'), { bars, overlays: [{ values: c.e, color: '#2563eb', width: 2, label: 'EMA 105' }], zones, markers,
      title: r.symbol + ' 2-hour candles with EMA 105' });
    else $('e105-chart').textContent = 'Chart library failed to load.';
    $('e105-d-chartnote').textContent = 'Last ' + D.chart_sessions + ' sessions of 2-hour candles (' + c.t[0] + ' → ' + c.t[c.t.length - 1] +
      '). ▲ green = BUY, ▼ orange = TOP, ▼ grey = EXIT. Hover a marker for its price and result.';

    const tb = $('e105-d-parts'); tb.textContent = '';
    partRow(tb, 'Whole period (' + r.from + ' → ' + r.to.slice(0, 10) + ')', r.all, 'strong');
    partRow(tb, 'Tested part (→ ' + r.split + ')', r.is);
    partRow(tb, 'Unseen part (' + r.split + ' →)', r.os);
    $('e105-d-maths').textContent = (() => {
      const t = r.trades, w = t.filter(x => x[4] > 0), gw = w.reduce((s, x) => s + x[4], 0), gl = -t.filter(x => x[4] <= 0).reduce((s, x) => s + x[4], 0);
      return 'Maths: ' + w.length + ' winners ÷ ' + t.length + ' trades = ' + pc(t.length ? w.length / t.length * 100 : null) + ' win. Winners ' + n2(gw) +
        ' ÷ losers ' + n2(gl) + ' = PF ' + (gl > 0 ? n2(gw / gl) : '–') + '. Net ' + sg(gw - gl, 2) + ' ₹/share = ' + sg(r.all.net_pct, 1) +
        '% added up' + (r.lot ? ' ≈ ₹' + sg(r.per_lot, 0) + ' per F&O lot of ' + r.lot : '') + '. After 0.035% cost a trade.';
    })();
    const tt = $('e105-d-trades'); tt.textContent = '';
    r.trades.slice().reverse().forEach(x => {
      const tr = el('tr'); td(tr, x[0]); td(tr, n2(x[1]), 'num'); td(tr, x[6] === 'open' ? 'still holding' : x[2]);
      td(tr, n2(x[3]), 'num'); td(tr, x[6] === 'open' ? 'open' : x[6] === 'top' ? 'TOP' : 'EXIT');
      td(tr, sg(x[4], 2), 'num ' + tone(x[4])); td(tr, sg(x[5], 2) + '%', 'num ' + tone(x[5])); tt.appendChild(tr);
    });
    if (scroll) box.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function boot() {
    const sec = $('ema105-section');
    if (!sec) return;
    fetch('fno_ema105.json?v=' + Date.now(), { cache: 'no-store' })
      .then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))
      .then(d => {
        D = d;
        head(); table();
        $('e105-search').addEventListener('input', e => { view.q = e.target.value; table(); });
        $('e105-sort').addEventListener('change', e => { view.sort = e.target.value; table(); });
        const lim = $('e105-limits'); lim.textContent = '';
        D.limits.forEach(x => lim.appendChild(el('li', null, x)));
        if (D.failures.length) lim.appendChild(el('li', null, 'Not covered today: ' + D.failures.map(f => f.symbol + ' (' + f.reason + ')').join(', ') + '.'));
        const first = D.rows.find(r => r.state === 'BUY') || D.rows.find(r => r.state === 'TOP') || D.rows[0];
        if (first) detail(first.symbol, false);
      })
      .catch(e => { $('e105-asof').textContent = 'Failed to load the EMA 105 F&O scan: ' + e.message; });
  }
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', boot) : boot();
})();
