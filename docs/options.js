'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const BUCKETS = ['BUY_CALL', 'BUY_PUT', 'SELL', 'VOLATILITY', 'UNPROVEN', 'NO_SIGNAL'];
  const ACTIONABLE = ['BUY_CALL', 'BUY_PUT', 'SELL', 'VOLATILITY'];
  const order = {BUY_CALL: 0, BUY_PUT: 1, SELL: 2, VOLATILITY: 3, UNPROVEN: 4, NO_SIGNAL: 5};
  const BUCKET_LABEL = {BUY_CALL: 'Buy call', BUY_PUT: 'Buy put', SELL: 'Sell options', VOLATILITY: 'Volatility', UNPROVEN: 'Unproven', NO_SIGNAL: 'No signal'};
  const BUCKET_CLASS = {BUY_CALL: 'buy-call', BUY_PUT: 'buy-put', SELL: 'sell', VOLATILITY: 'volatility', UNPROVEN: 'unproven', NO_SIGNAL: 'no-signal'};

  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const numeric = value => typeof value === 'number' && Number.isFinite(value);
  const fmt = (value, digits = 2) => numeric(value) ? value.toLocaleString('en-IN', {minimumFractionDigits: digits, maximumFractionDigits: digits}) : '--';
  const intFmt = value => numeric(value) ? Math.round(value).toLocaleString('en-IN') : '--';
  const money = value => numeric(value) ? '\u20b9' + fmt(value) : '--';
  const pct = (value, digits = 1) => numeric(value) ? (value > 0 ? '+' : '') + fmt(value, digits) + '%' : '--';
  const pctPlain = (value, digits = 1) => numeric(value) ? fmt(value, digits) + '%' : '--';
  const signed = value => numeric(value) ? (value > 0 ? '+' : '') + fmt(value) : '--';
  const date = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '') ? new Date(value + 'T00:00:00Z').toLocaleDateString('en-IN', {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'}) : '--';
  const statusBadge = s => '<span class="rule-status ' + esc(s) + '">' + esc(s || '--') + '</span>';
  const sideTag = side => '<span class="side ' + (side === 'SELL' ? 'side-sell' : 'side-buy') + '">' + esc(side || '--') + '</span>';

  let dataset = null, visible = [], selected = null, oiMode = 'oi';

  function validate(data) {
    if (!data || !/^\d{4}-\d{2}-\d{2}$/.test(data.as_of || '')) throw new Error('Missing or invalid session date.');
    if (!Array.isArray(data.rows)) throw new Error('No rows in the options snapshot.');
    if (data.universe_count !== data.rows.length) throw new Error('universe_count does not match the number of rows.');
    if (new Set(data.rows.map(r => r.symbol)).size !== data.rows.length) throw new Error('Duplicate underlyings in the snapshot.');
    if (!data.counts) throw new Error('No bucket counts in the snapshot.');
    for (const b of BUCKETS) {
      const actual = data.rows.filter(r => r.bucket === b).length;
      if (data.counts[b] !== actual) throw new Error('Count mismatch for ' + b + ' (' + data.counts[b] + ' vs ' + actual + ').');
    }
    for (const row of data.rows) {
      if (!BUCKETS.includes(row.bucket)) throw new Error('Unknown bucket for ' + row.symbol + '.');
      if ((row.bucket === 'UNPROVEN' || row.bucket === 'NO_SIGNAL') && row.action != null) throw new Error('Non-trade bucket for ' + row.symbol + ' must have a null action.');
      if (ACTIONABLE.includes(row.bucket)) {
        if (row.action == null) throw new Error('Actionable bucket for ' + row.symbol + ' needs an action.');
        const sigs = Array.isArray(row.signals) ? row.signals : [];
        if (!sigs.some(s => s.status === 'VALIDATED')) throw new Error('Actionable bucket for ' + row.symbol + ' needs a VALIDATED signal.');
      }
    }
    if (!Array.isArray(data.rules)) throw new Error('No rules in the snapshot.');
  }

  const ruleById = id => (dataset.rules || []).find(r => r.id === id) || null;

  // ---- Header / coverage ----
  function renderHeader() {
    $('session-date').textContent = date(dataset.as_of);
    const src = dataset.source || {};
    $('coverage').textContent = dataset.universe_count + ' underlyings \u00b7 ' + (numeric(src.sessions) ? intFmt(src.sessions) : '--') + ' sessions of official F&O bhavcopy';
    $('next-session').textContent = dataset.next_session ? 'Signals enter at the next open: ' + date(dataset.next_session) : '';
  }

  // ---- Pickers ----
  function renderPickers() {
    for (const b of BUCKETS) {
      const select = $('pick-' + b);
      const rows = dataset.rows.filter(r => r.bucket === b).sort((a, c) => a.symbol.localeCompare(c.symbol));
      $('pick-count-' + b).textContent = String(rows.length);
      select.innerHTML = '<option value="">' + (rows.length ? 'Choose an underlying' : 'None in this bucket today') + '</option>' +
        rows.map(r => '<option value="' + esc(r.symbol) + '">' + esc(r.symbol) + '</option>').join('');
      select.disabled = !rows.length;
    }
    syncPickers();
  }

  function syncPickers() {
    const row = dataset.rows.find(r => r.symbol === selected);
    document.querySelectorAll('[data-pick-bucket]').forEach(select => {
      const active = row && row.bucket === select.dataset.pickBucket;
      select.value = active ? row.symbol : '';
      select.closest('.stock-picker').classList.toggle('selected', !!active);
    });
  }

  // ---- Index market cards ----
  function renderMarket() {
    const market = Array.isArray(dataset.market) ? dataset.market : [];
    const host = $('market-cards');
    if (!market.length) { host.innerHTML = '<p class="muted">No index option context in this snapshot.</p>'; return; }
    host.innerHTML = market.map(m =>
      '<article class="market-card"><div class="market-card-head"><strong>' + esc(m.symbol) + '</strong><span>' + money(m.spot) + '</span></div>' +
      '<dl>' +
      '<div><dt>5d</dt><dd class="' + trendClass(m.ret5_pct) + '">' + pct(m.ret5_pct) + '</dd></div>' +
      '<div><dt>Build-up</dt><dd>' + esc(m.buildup || 'n/a') + '</dd></div>' +
      '<div><dt>PCR (5d)</dt><dd>' + fmt(m.pcr) + ' <small>(' + signed(m.pcr_chg5) + ')</small></dd></div>' +
      '<div><dt>ATM IV</dt><dd>' + pctPlain(m.atm_iv) + ' <small>(' + (numeric(m.iv_pct) ? fmt(m.iv_pct, 0) + ' pct' : '--') + ')</small></dd></div>' +
      '<div><dt>Call wall</dt><dd>' + intFmt(m.call_wall) + '</dd></div>' +
      '<div><dt>Put wall</dt><dd>' + intFmt(m.put_wall) + '</dd></div>' +
      '<div><dt>Max pain</dt><dd>' + intFmt(m.max_pain) + '</dd></div>' +
      '<div><dt>Expiry</dt><dd>' + date(m.expiry) + '</dd></div>' +
      '</dl></article>'
    ).join('');
  }

  const trendClass = v => numeric(v) ? (v > 0 ? 'positive' : v < 0 ? 'negative' : '') : '';

  // ---- Detail panel ----
  function renderDetail() {
    const row = dataset.rows.find(r => r.symbol === selected);
    const panel = $('stock-detail');
    if (!row) { panel.hidden = true; return; }
    panel.hidden = false;
    $('detail-title').textContent = row.symbol;
    $('detail-subtitle').textContent = (row.kind === 'index' ? 'Index' : 'Stock') + ' \u00b7 ' + (row.action ? esc(row.action) : 'No trade') + (row.expiry ? ' \u00b7 expiry ' + date(row.expiry) : '');
    const badge = $('detail-badge');
    badge.textContent = BUCKET_LABEL[row.bucket] || row.bucket;
    badge.className = 'state option-badge ' + (BUCKET_CLASS[row.bucket] || '');
    $('detail-reason').textContent = row.reason || '';
    renderSignals(row);
    renderJev(row);
    renderOiChart(row);
    renderHistoryChart(row);
    syncPickers();
    filterRows();
  }

  function renderSignals(row) {
    const host = $('signal-cards');
    const sigs = Array.isArray(row.signals) ? row.signals : [];
    if (!sigs.length) { host.innerHTML = '<div class="signal-card empty"><p class="muted">No rule fired for this underlying today.</p></div>'; return; }
    host.innerHTML = sigs.map(sig => {
      const rule = ruleById(sig.rule);
      const legs = Array.isArray(sig.legs) ? sig.legs : [];
      const legsHtml = legs.map(l =>
        '<li>' + sideTag(l.side) + ' <strong>' + esc(l.name) + '</strong> <span class="leg-meta">' +
        esc(l.option_type || '') + ' ' + intFmt(l.strike) + ' \u00b7 exp ' + date(l.expiry) + ' \u00b7 ref ' + money(l.ref_close) +
        ' \u00b7 lot ' + intFmt(l.lot) + '</span></li>').join('');
      const plan = sig.plan || {};
      const planHtml = '<p class="signal-plan">Plan: ' + esc(plan.entry || 'Enter at the next session open') +
        ' \u00b7 exit after ' + (numeric(plan.exit_after_sessions) ? plan.exit_after_sessions : 5) + ' sessions by ' + date(plan.exit_by) + '.</p>';
      return '<article class="signal-card"><div class="signal-card-head"><strong>' + esc(sig.action || '--') + '</strong>' + statusBadge(sig.status) + '</div>' +
        '<p class="signal-rule">' + esc(rule ? rule.label : sig.rule) + '</p>' +
        (legs.length ? '<ul class="legs">' + legsHtml + '</ul>' : '') +
        planHtml + ruleEvidenceHtml(rule) + '</article>';
    }).join('');
  }

  function ruleEvidenceHtml(rule) {
    if (!rule || !rule.stats) return '<p class="muted signal-evidence">No backtest evidence is attached to this rule.</p>';
    const s = rule.stats;
    const basis = s.return_basis === 'margin' ? 'on margin' : 'on premium';
    const half = h => h ? (date(h.from) + '\u2013' + date(h.to) + ': ' + (numeric(h.trades) ? h.trades : '--') + ' trades, mean ' + pct(h.mean_return_pct) + ', win ' + pctPlain(h.win_rate, 0)) : '--';
    return '<div class="signal-evidence"><span class="evidence-head">Evidence (' + basis + ')</span>' +
      '<dl class="evidence-grid">' +
      '<div><dt>Trades</dt><dd>' + intFmt(s.trades) + '</dd></div>' +
      '<div><dt>Win rate</dt><dd>' + pctPlain(s.win_rate, 0) + '</dd></div>' +
      '<div><dt>Mean</dt><dd class="' + trendClass(s.mean_return_pct) + '">' + pct(s.mean_return_pct) + '</dd></div>' +
      '<div><dt>Median</dt><dd>' + pct(s.median_return_pct) + '</dd></div>' +
      '<div><dt>t-stat</dt><dd>' + fmt(s.t_stat) + '</dd></div>' +
      '<div><dt>Worst</dt><dd class="negative">' + pct(s.worst_return_pct) + '</dd></div>' +
      '<div><dt>Best</dt><dd class="positive">' + pct(s.best_return_pct) + '</dd></div>' +
      '<div><dt>Avg P&L/lot</dt><dd class="' + trendClass(s.avg_pnl_per_lot) + '">' + money(s.avg_pnl_per_lot) + '</dd></div>' +
      '</dl>' +
      '<p class="evidence-halves">First half \u2014 ' + half(s.first_half) + '<br>Second half \u2014 ' + half(s.second_half) + '</p></div>';
  }

  function renderJev(row) {
    const host = $('jev-review');
    const j = row.jev;
    if (!j) { host.innerHTML = '<div class="jev-card none"><span class="jev-head">Jev review</span><p class="muted">Jev not run for this underlying.</p></div>'; return; }
    const conf = v => numeric(v) ? Math.round(v * 100) + '%' : '--';
    host.innerHTML = '<div class="jev-card"><span class="jev-head">Jev review</span>' +
      '<p>Support: <strong class="jev-' + esc(j.support) + '">' + esc(j.support || '--') + '</strong> <small>(' + conf(j.support_confidence) + ' confidence)</small></p>' +
      '<p>Risk: <strong class="jev-risk-' + esc(j.risk) + '">' + esc(j.risk || '--') + '</strong> <small>(' + conf(j.risk_confidence) + ' confidence)</small></p>' +
      '<p class="muted">A Jev review is a typed model opinion on the evidence, not a forecast.</p></div>';
  }

  // ---- SVG open interest by strike ----
  function renderOiChart(row) {
    const host = $('oi-chart');
    const p = row.oi_profile;
    $('oi-heading').textContent = p ? 'Expiry ' + date(p.expiry) : 'No chain';
    if (!p || !Array.isArray(p.strikes) || !p.strikes.length) {
      host.innerHTML = '<p class="muted">No option-chain data for this underlying.</p>';
      return;
    }
    const strikes = p.strikes;
    const ce = oiMode === 'chg' ? (p.ce_oi_chg || []) : (p.ce_oi || []);
    const pe = oiMode === 'chg' ? (p.pe_oi_chg || []) : (p.pe_oi || []);
    const W = 960, H = 320, padL = 56, padR = 20, padT = 20, padB = 46;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const vals = [];
    ce.forEach(v => numeric(v) && vals.push(v));
    pe.forEach(v => numeric(v) && vals.push(v));
    const maxV = vals.length ? Math.max(...vals, 0) : 1;
    const minV = vals.length ? Math.min(...vals, 0) : 0;
    const span = (maxV - minV) || 1;
    const yOf = v => padT + plotH - ((v - minV) / span) * plotH;
    const zeroY = yOf(0);
    const n = strikes.length;
    const slot = plotW / n;
    const barW = Math.max(4, slot * 0.32);
    const xMid = i => padL + slot * (i + 0.5);
    const xOfStrike = strike => {
      if (!numeric(strike)) return null;
      const lo = strikes[0], hi = strikes[n - 1];
      if (!numeric(lo) || !numeric(hi) || hi === lo) return xMid(0);
      const clamped = Math.max(lo, Math.min(hi, strike));
      return padL + ((clamped - lo) / (hi - lo)) * plotW;
    };
    let bars = '';
    for (let i = 0; i < n; i++) {
      const cv = ce[i], pv = pe[i];
      if (numeric(cv)) {
        const y = Math.min(zeroY, yOf(cv)), h = Math.abs(yOf(cv) - zeroY);
        bars += '<rect class="bar-ce" x="' + (xMid(i) - barW - 1).toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + barW.toFixed(1) + '" height="' + Math.max(0, h).toFixed(1) + '"><title>' + esc(intFmt(strikes[i])) + ' CE: ' + esc(intFmt(cv)) + '</title></rect>';
      }
      if (numeric(pv)) {
        const y = Math.min(zeroY, yOf(pv)), h = Math.abs(yOf(pv) - zeroY);
        bars += '<rect class="bar-pe" x="' + (xMid(i) + 1).toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + barW.toFixed(1) + '" height="' + Math.max(0, h).toFixed(1) + '"><title>' + esc(intFmt(strikes[i])) + ' PE: ' + esc(intFmt(pv)) + '</title></rect>';
      }
    }
    // x labels (thinned)
    const step = Math.ceil(n / 8);
    let labels = '';
    for (let i = 0; i < n; i += step) labels += '<text class="axis-x" x="' + xMid(i).toFixed(1) + '" y="' + (H - 26).toFixed(1) + '">' + esc(intFmt(strikes[i])) + '</text>';
    // zero / baseline
    const baseline = '<line class="axis-base" x1="' + padL + '" y1="' + zeroY.toFixed(1) + '" x2="' + (W - padR) + '" y2="' + zeroY.toFixed(1) + '"/>';
    // markers
    const marker = (strike, cls, label) => {
      const x = xOfStrike(strike);
      if (x == null) return '';
      return '<line class="' + cls + '" x1="' + x.toFixed(1) + '" y1="' + padT + '" x2="' + x.toFixed(1) + '" y2="' + (padT + plotH) + '"><title>' + esc(label) + ' ' + esc(intFmt(strike)) + '</title></line>' +
        '<text class="marker-label ' + cls + '-t" x="' + x.toFixed(1) + '" y="' + (padT - 6).toFixed(1) + '">' + esc(label) + '</text>';
    };
    const spotLine = marker(row.spot, 'line-spot', 'Spot');
    const markers = marker(row.call_wall, 'line-callwall', 'Call wall') + marker(row.put_wall, 'line-putwall', 'Put wall') + marker(row.max_pain, 'line-maxpain', 'Max pain');
    host.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Open interest by strike for ' + esc(row.symbol) + '">' +
      baseline + bars + spotLine + markers + labels + '</svg>';
  }

  // ---- SVG history mini lines ----
  function miniLine(dates, series, title, unit) {
    const W = 460, H = 120, padL = 40, padR = 12, padT = 16, padB = 22;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const pts = (series || []).map((v, i) => ({v, i})).filter(d => numeric(d.v));
    if (pts.length < 2) {
      return '<div class="mini"><span class="mini-title">' + esc(title) + '</span><svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(title) + ' history"><text class="axis-x" x="' + (W / 2) + '" y="' + (H / 2) + '">Not enough data</text></svg></div>';
    }
    const vals = pts.map(d => d.v);
    const lo = Math.min(...vals), hi = Math.max(...vals), span = (hi - lo) || 1;
    const n = (dates || []).length || series.length;
    const xOf = i => padL + (n > 1 ? (i / (n - 1)) * plotW : plotW / 2);
    const yOf = v => padT + plotH - ((v - lo) / span) * plotH;
    const path = pts.map((d, k) => (k ? 'L' : 'M') + xOf(d.i).toFixed(1) + ' ' + yOf(d.v).toFixed(1)).join(' ');
    const last = pts[pts.length - 1];
    const dots = '<circle class="mini-dot" cx="' + xOf(last.i).toFixed(1) + '" cy="' + yOf(last.v).toFixed(1) + '" r="3"/>';
    const yLabels = '<text class="axis-y" x="' + (padL - 6) + '" y="' + (padT + 4) + '">' + esc(fmt(hi, unit === '' ? 0 : 2)) + '</text>' +
      '<text class="axis-y" x="' + (padL - 6) + '" y="' + (padT + plotH) + '">' + esc(fmt(lo, unit === '' ? 0 : 2)) + '</text>';
    return '<div class="mini"><span class="mini-title">' + esc(title) + '</span><svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(title) + ' history"><path class="mini-path" d="' + path + '"/>' + dots + yLabels + '</svg></div>';
  }

  function renderHistoryChart(row) {
    const h = row.history || {};
    const host = $('history-chart');
    if (!h.dates || !h.dates.length) { host.innerHTML = '<p class="muted">No history for this underlying.</p>'; return; }
    host.innerHTML = miniLine(h.dates, h.spot, 'Spot', '2') + miniLine(h.dates, h.pcr, 'PCR', '2') + miniLine(h.dates, h.iv, 'ATM IV %', '2');
  }

  // ---- Universe table ----
  function filterRows() {
    const bucket = $('bucket').value, kind = $('kind').value, sort = $('sort').value;
    const search = $('search').value.trim().toLowerCase();
    visible = dataset.rows.filter(r =>
      (bucket === 'ALL' || r.bucket === bucket) &&
      (kind === 'ALL' || r.kind === kind) &&
      (!search || r.symbol.toLowerCase().includes(search))
    );
    const num = (v, d) => numeric(v) ? v : d;
    visible.sort((a, b) => {
      if (sort === 'symbol') return a.symbol.localeCompare(b.symbol);
      if (sort === 'turnover') return num(b.turnover_cr, -Infinity) - num(a.turnover_cr, -Infinity) || a.symbol.localeCompare(b.symbol);
      if (sort === 'iv') return num(b.iv_pct, -Infinity) - num(a.iv_pct, -Infinity) || a.symbol.localeCompare(b.symbol);
      if (sort === 'pcr') return num(b.pcr, -Infinity) - num(a.pcr, -Infinity) || a.symbol.localeCompare(b.symbol);
      return order[a.bucket] - order[b.bucket] || a.symbol.localeCompare(b.symbol);
    });
    $('result-count').textContent = visible.length + ' of ' + dataset.universe_count + ' underlyings shown';
    $('option-rows').innerHTML = visible.length ? visible.map(r =>
      '<tr data-symbol="' + esc(r.symbol) + '" class="' + (selected === r.symbol ? 'selected' : '') + '">' +
      '<td><button class="stock-name" type="button" data-symbol="' + esc(r.symbol) + '">' + esc(r.symbol) + '</button><small>' + (r.kind === 'index' ? 'Index' : 'Stock') + '</small></td>' +
      '<td><span class="bucket-tag ' + (BUCKET_CLASS[r.bucket] || '') + '">' + esc(BUCKET_LABEL[r.bucket] || r.bucket) + '</span>' + (r.action ? '<small>' + esc(r.action) + '</small>' : '') + '</td>' +
      '<td>' + money(r.spot) + '</td>' +
      '<td class="' + trendClass(r.ret5_pct) + '">' + pct(r.ret5_pct) + '</td>' +
      '<td>' + esc(r.buildup || 'n/a') + '</td>' +
      '<td>' + fmt(r.pcr) + '<small>' + signed(r.pcr_chg5) + '</small></td>' +
      '<td>' + pctPlain(r.atm_iv) + '<small>' + (numeric(r.iv_pct) ? fmt(r.iv_pct, 0) + ' pct' : '--') + '</small></td>' +
      '<td>' + date(r.expiry) + '</td>' +
      '<td>' + (numeric(r.turnover_cr) ? '\u20b9' + fmt(r.turnover_cr, 0) + ' cr' : '--') + '</td>' +
      '<td class="reason-cell">' + esc(r.reason) + '</td></tr>'
    ).join('') : '<tr><td colspan="10" class="empty-row">No underlyings match these filters.</td></tr>';
    $('download').disabled = !visible.length;
  }

  // ---- Rule evidence table ----
  function renderRuleTable() {
    const rules = dataset.rules || [];
    const half = h => h ? (pct(h.mean_return_pct) + ' <small>(' + (numeric(h.trades) ? h.trades : '--') + 't, win ' + pctPlain(h.win_rate, 0) + ')</small>') : '--';
    $('rule-rows').innerHTML = rules.map((rule, idx) => {
      const s = rule.stats || {};
      const trades = Array.isArray(rule.recent_trades) ? rule.recent_trades : [];
      const main = '<tr class="rule-row" data-rule-idx="' + idx + '">' +
        '<td><button class="stock-name rule-toggle" type="button" data-rule-idx="' + idx + '">' + esc(rule.label) + '</button><small>' + esc(rule.condition) + '</small></td>' +
        '<td>' + statusBadge(rule.status) + '</td>' +
        '<td>' + esc(rule.action || '--') + '</td>' +
        '<td>' + intFmt(s.trades) + '</td>' +
        '<td>' + pctPlain(s.win_rate, 0) + '</td>' +
        '<td class="' + trendClass(s.mean_return_pct) + '">' + pct(s.mean_return_pct) + '</td>' +
        '<td>' + fmt(s.t_stat) + '</td>' +
        '<td>' + half(s.first_half) + '</td>' +
        '<td>' + half(s.second_half) + '</td>' +
        '<td>' + (rule.baseline ? 'Baseline' : 'No') + '</td></tr>';
      const tradesHtml = trades.length ? trades.map(t =>
        '<li><strong>' + esc(t.symbol) + '</strong> ' + date(t.signal_date) + ' \u2192 ' + date(t.exit_date) + ': ' +
        (Array.isArray(t.legs) ? t.legs.map(l => sideTag(l.side) + ' ' + esc(l.name) + ' ' + money(l.entry) + '\u2192' + money(l.exit)).join(', ') : '') +
        ' <span class="' + trendClass(t.return_pct) + '">' + pct(t.return_pct) + '</span> (' + money(t.pnl_per_lot) + '/lot)</li>').join('') :
        '<li class="muted">No recent trades recorded.</li>';
      const detail = '<tr class="rule-detail" data-rule-idx="' + idx + '" hidden><td colspan="10"><ul class="recent-trades">' + tradesHtml + '</ul></td></tr>';
      return main + detail;
    }).join('');
  }

  // ---- Paper trades ----
  function renderPaper() {
    const paper = dataset.paper || {};
    const open = Array.isArray(paper.open) ? paper.open : [];
    $('paper-rows').innerHTML = open.length ? open.map(t =>
      '<tr><td>' + esc((ruleById(t.rule) || {}).label || t.rule) + '</td><td>' + esc(t.symbol) + '</td><td>' + esc(t.action || '--') + '</td>' +
      '<td>' + date(t.signal_date) + '</td><td>' + date(t.entry_date) + '</td>' +
      '<td>' + (Array.isArray(t.legs) ? t.legs.map(l => sideTag(l.side) + ' ' + esc(l.name) + ' ' + money(l.entry) + '\u2192' + money(l.mark)).join('<br>') : '--') + '</td>' +
      '<td class="' + trendClass(t.mark_return_pct) + '">' + pct(t.mark_return_pct) + '</td></tr>'
    ).join('') : '<tr><td colspan="7" class="empty-row">No open paper trades.</td></tr>';
    const fl = paper.forward_log || {};
    $('forward-log').textContent = fl.since ?
      ('Forward log since ' + date(fl.since) + ': ' + intFmt(fl.signals) + ' signals, ' + intFmt(fl.matured) + ' matured, mean ' + pct(fl.mean_return_pct) + ', win ' + pctPlain(fl.win_rate, 0) + '.') :
      'No forward log yet.';
  }

  // ---- Jev calibration ----
  function renderCalibration() {
    const jev = dataset.jev || {};
    const cal = jev.calibration || {};
    const host = $('jev-calibration');
    const order2 = ['supportive', 'conflicting', 'mixed', 'insufficient'];
    host.innerHTML = order2.map(k => {
      const c = cal[k] || {};
      return '<article class="calib-card jev-' + k + '"><span class="calib-label">' + k[0].toUpperCase() + k.slice(1) + '</span>' +
        '<strong>' + (numeric(c.mean_return_pct) ? pct(c.mean_return_pct) : '--') + '</strong>' +
        '<small>' + (numeric(c.n) ? c.n + ' matured \u00b7 win ' + pctPlain(c.win_rate, 0) : 'no data') + '</small></article>';
    }).join('');
    $('jev-calibration-note').textContent = 'State: ' + (jev.state || 'unknown') + ' \u00b7 model ' + (jev.model || '--') + ' \u00b7 ' + (jev.message || '') +
      (numeric(cal.matured) ? ' (' + cal.matured + ' matured signals scored).' : '');
  }

  // ---- Methods & data audit ----
  function renderMethods() {
    const m = dataset.method || {};
    $('method-entry').textContent = m.entry || '';
    $('method-exit').textContent = m.exit || '';
    $('method-cost').textContent = m.cost_model || '';
    $('method-margin').textContent = m.margin_model || '';
    $('method-validation').textContent = m.validation || '';
    $('method-nolook').textContent = m.no_lookahead || '';
    const src = dataset.source || {};
    const lim = Array.isArray(dataset.limitations) ? dataset.limitations : [];
    $('data-audit').innerHTML =
      '<p><strong>Source:</strong> ' + esc(src.name || '--') + '</p>' +
      '<p><strong>Sessions:</strong> ' + intFmt(src.sessions) + ' (' + date(src.first_session) + ' to ' + date(src.last_session) + ')</p>' +
      (Array.isArray(src.missing_sessions) && src.missing_sessions.length ? '<p><strong>Missing sessions:</strong> ' + esc(src.missing_sessions.map(date).join(', ')) + '</p>' : '') +
      '<p><strong>Generated:</strong> ' + esc(dataset.generated_at || '--') + '</p>' +
      (lim.length ? '<ul>' + lim.map(l => '<li>' + esc(l) + '</li>').join('') + '</ul>' : '');
  }

  // ---- CSV ----
  function downloadCsv() {
    if (!visible.length) return;
    const cols = ['symbol', 'kind', 'bucket', 'action', 'primary_rule', 'spot', 'ret1_pct', 'ret5_pct', 'fut_oi5_pct', 'buildup', 'pcr', 'pcr_chg5', 'atm_iv', 'iv_pct', 'call_wall', 'put_wall', 'max_pain', 'expiry', 'days_to_expiry', 'turnover_cr'];
    const cell = v => {
      if (v == null) return '';
      const s = String(v);
      return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    const lines = [cols.join(',')].concat(visible.map(r => cols.map(c => cell(r[c])).join(',')));
    const blob = new Blob(['\ufeff' + lines.join('\n')], {type: 'text/csv;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'options_desk_' + (dataset.as_of || 'snapshot') + '.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // ---- Selection ----
  function select(symbol) {
    if (!dataset.rows.some(r => r.symbol === symbol)) return;
    selected = symbol;
    renderDetail();
    $('stock-detail').scrollIntoView({behavior: 'smooth', block: 'start'});
    const title = $('detail-title');
    if (title && typeof title.focus === 'function') title.focus({preventScroll: true});
  }

  function wire() {
    document.querySelectorAll('[data-pick-bucket]').forEach(sel => sel.addEventListener('change', () => { if (sel.value) select(sel.value); }));
    ['bucket', 'kind', 'sort'].forEach(id => $(id).addEventListener('change', filterRows));
    $('search').addEventListener('input', filterRows);
    $('reset').addEventListener('click', () => {
      $('bucket').value = 'ALL'; $('kind').value = 'ALL'; $('sort').value = 'bucket'; $('search').value = '';
      filterRows();
    });
    $('download').addEventListener('click', downloadCsv);
    $('option-rows').addEventListener('click', e => {
      const btn = e.target.closest('button[data-symbol]');
      if (btn) select(btn.dataset.symbol);
    });
    $('oi-mode').addEventListener('change', () => {
      oiMode = $('oi-mode').value;
      const row = dataset.rows.find(r => r.symbol === selected);
      if (row) renderOiChart(row);
    });
    $('rule-rows').addEventListener('click', e => {
      const btn = e.target.closest('.rule-toggle');
      if (!btn) return;
      const idx = btn.dataset.ruleIdx;
      const detail = document.querySelector('.rule-detail[data-rule-idx="' + idx + '"]');
      if (detail) detail.hidden = !detail.hidden;
    });
  }

  function failClosed(message) {
    $('notice').textContent = message;
    $('notice').classList.add('warning');
    $('session-date').textContent = 'Unavailable';
    $('coverage').textContent = 'Data check failed';
    $('next-session').textContent = '';
    $('result-count').textContent = 'No verified rows to display.';
    $('option-rows').innerHTML = '';
    $('rule-rows').innerHTML = '';
    $('market-cards').innerHTML = '';
    $('paper-rows').innerHTML = '';
    $('stock-detail').hidden = true;
    document.querySelectorAll('[data-pick-bucket]').forEach(sel => { sel.disabled = true; sel.innerHTML = '<option value="">Snapshot unavailable</option>'; sel.closest('.stock-picker').classList.remove('selected'); });
    for (const b of BUCKETS) $('pick-count-' + b).textContent = '—';
  }

  function load() {
    const source = document.body.dataset.source || '';
    fetch(source + 'options_desk.json?v=' + Date.now(), {cache: 'no-store'})
      .then(r => { if (!r.ok) throw new Error('status ' + r.status); return r.json(); })
      .then(data => {
        validate(data);
        dataset = data;
        $('notice').hidden = true;
        $('notice').classList.remove('warning');
        renderHeader();
        renderPickers();
        renderMarket();
        renderRuleTable();
        renderPaper();
        renderCalibration();
        renderMethods();
        filterRows();
      })
      .catch(err => {
        console.error(err);
        failClosed('The options snapshot could not be loaded or did not pass its integrity checks (' + (err && err.message ? err.message : 'unknown error') + '). No signals are displayed.');
      });
  }

  wire();
  load();
})();
