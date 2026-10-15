'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const numeric = value => typeof value === 'number' && Number.isFinite(value);
  const fmt = (value, digits = 2) => numeric(value) ? value.toLocaleString('en-IN', {minimumFractionDigits: digits, maximumFractionDigits: digits}) : '--';
  const intFmt = value => numeric(value) ? Math.round(value).toLocaleString('en-IN') : '--';
  const signedInt = value => numeric(value) ? (value > 0 ? '+' : '') + intFmt(value) : '--';
  const pct = (value, digits = 1) => numeric(value) ? (value > 0 ? '+' : '') + fmt(value, digits) + '%' : '--';
  const pctPlain = (value, digits = 1) => numeric(value) ? fmt(value, digits) + '%' : '--';
  const money = value => numeric(value) ? '\u20b9' + fmt(value) : '--';
  const date = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '') ? new Date(value + 'T00:00:00Z').toLocaleDateString('en-IN', {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'}) : '--';
  const safeUrl = value => /^https?:\/\//i.test(value || '') ? value : null;
  const link = (url, text) => safeUrl(url) ? '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + esc(text) + '</a>' : esc(text);
  const statusBadge = s => '<span class="rule-status ' + esc(s) + '">' + esc(s || '--') + '</span>';
  const sideTag = side => '<span class="side ' + (side === 'SELL' ? 'side-sell' : 'side-buy') + '">' + esc(side || '--') + '</span>';
  const cls = value => numeric(value) ? (value > 0 ? 'pos' : value < 0 ? 'neg' : '') : '';
  const label = s => String(s || '').replace(/_/g, ' ');
  const STANCE_CLASS = {bullish: 'pos', bearish: 'neg', neutral: '', insufficient: 'muted'};
  const RISK_CLASS = {high: 'neg', elevated: 'warn', ordinary: '', unknown: 'muted'};

  let dataset = null, expiry = null, width = 20, oiMode = 'oi';
  const constState = {status: 'ALL', stance: 'ALL', sort: 'symbol', search: ''};

  function validate(data) {
    if (!data || data.symbol !== 'NIFTY') throw new Error('Not a Nifty chain snapshot.');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(data.as_of || '')) throw new Error('Missing or invalid session date.');
    if (!data.index || !numeric(data.index.close)) throw new Error('Missing Nifty index close.');
    if (!Array.isArray(data.expiries) || !data.expiries.length) throw new Error('No option expiries in the snapshot.');
    for (const e of data.expiries) {
      if (!Array.isArray(e.rows) || !e.rows.length) throw new Error('Expiry ' + e.expiry + ' has no strikes.');
    }
    if (!Array.isArray(data.constituents) || data.constituents_count !== data.constituents.length) throw new Error('constituents_count does not match the constituent rows.');
    if (new Set(data.constituents.map(c => c.symbol)).size !== data.constituents.length) throw new Error('Duplicate constituents in the snapshot.');
    if (!Array.isArray(data.rules)) throw new Error('No rules in the snapshot.');
  }

  // ---------------------------------------------------------------- header + index cards
  function renderHeader() {
    const src = dataset.source || {};
    $('session-date').textContent = date(dataset.as_of);
    $('coverage').textContent = intFmt(src.sessions) + ' sessions of official F&O bhavcopy \u00b7 ' + intFmt(src.participant_sessions) + ' of participant OI \u00b7 ' + dataset.constituents_count + ' constituents';
    $('next-session').textContent = dataset.next_session ? 'Setups enter at the next open: ' + date(dataset.next_session) : '';
    const stale = (dataset.inputs || {}).stale || [];
    const notice = $('notice');
    notice.textContent = stale.length ? 'Note: ' + stale.join(' and ') + ' not yet updated to ' + date(dataset.as_of) + '; constituent columns from those pages may be one session behind.' : '';
    notice.hidden = !stale.length;
  }

  function card(title, value, sub, tone) {
    return '<div class="nc-card"><dt>' + esc(title) + '</dt><dd class="' + esc(tone || '') + '">' + value + '</dd>' + (sub ? '<small>' + sub + '</small>' : '') + '</div>';
  }

  function renderIndex() {
    const x = dataset.index, s = x.structure || {};
    const trade = dataset.expiries.find(e => e.trade_expiry) || dataset.expiries[0];
    $('index-source').textContent = x.official_close_file ? 'NSE index close file' : 'Option underlying price (index file unavailable)';
    $('index-cards').innerHTML = '<dl class="nc-card-grid">' + [
      card('Nifty 50', fmt(x.close), pct(x.change_pct, 2) + ' \u00b7 H ' + fmt(x.high) + ' L ' + fmt(x.low), cls(x.change_pct)),
      card('5-session move', pct(x.ret5_pct, 2), numeric(x.z5) ? fmt(x.z5, 1) + ' sigma' : '', cls(x.ret5_pct)),
      card('India VIX', fmt(x.vix), pct(x.vix_change_pct, 2)),
      card('ATM IV (trade expiry)', pctPlain(x.atm_iv), 'IV percentile ' + intFmt(x.iv_pct) + ' \u00b7 realised ' + pctPlain(x.rv20)),
      card('Vol risk premium', numeric(x.vrp) ? (x.vrp > 0 ? '+' : '') + fmt(x.vrp, 1) + ' pts' : '--', 'IV minus 20-session realised vol', cls(x.vrp)),
      card('Expected move', trade ? '\u00b1' + fmt(trade.expected_move, 0) : '--', trade ? '1\u03c3 to ' + date(trade.expiry) + ': ' + fmt(trade.sigma_1[0], 0) + ' \u2013 ' + fmt(trade.sigma_1[1], 0) : ''),
      card('Swing structure', esc(s.structure || '--'), s.breakout ? 'Fresh HH/HL breakout' : 'Swing high ' + fmt(s.confirmed_high, 0) + ' \u00b7 low ' + fmt(s.confirmed_low, 0), s.rising ? 'pos' : s.falling ? 'neg' : ''),
      card('PCR (all expiries)', fmt(x.pcr, 2), numeric(x.pcr_chg5) ? (x.pcr_chg5 > 0 ? '+' : '') + fmt(x.pcr_chg5, 2) + ' in 5 sessions' : ''),
      card('Futures', fmt(x.futures_close), 'Basis ' + (numeric(x.basis) ? (x.basis > 0 ? '+' : '') + fmt(x.basis, 1) : '--') + ' \u00b7 OI ' + pct(x.fut_oi5_pct) + ' (' + esc(x.buildup) + ')'),
      card('FII index futures', numeric(s.fii_long_share) ? pctPlain(s.fii_long_share, 0) + ' long' : '--', numeric(s.fii_long_share_chg5) ? (s.fii_long_share_chg5 > 0 ? '+' : '') + fmt(s.fii_long_share_chg5, 1) + ' pts in 5 sessions' : ''),
      card('Valuation', 'P/E ' + fmt(x.pe), 'P/B ' + fmt(x.pb) + ' \u00b7 yield ' + pctPlain(x.div_yield, 2)),
      card('Bank Nifty', fmt(x.bank_nifty), pct(x.bank_nifty_change_pct, 2), cls(x.bank_nifty_change_pct)),
    ].join('') + '</dl>';
  }

  // ---------------------------------------------------------------- best setup + Jev
  function probBars(p) {
    if (!p) return '';
    return '<div class="nc-probs">' + Object.entries(p).sort((a, b) => (b[1] || 0) - (a[1] || 0)).map(([k, v]) =>
      '<div><span>' + esc(label(k)) + '</span><i style="width:' + (numeric(v) ? Math.round(v * 100) : 0) + '%"></i><b>' + (numeric(v) ? Math.round(v * 100) + '%' : '--') + '</b></div>').join('') + '</div>';
  }

  function renderVerdict() {
    const best = dataset.best_setup || {};
    const setup = (dataset.setups || []).find(s => s.rule === best.rule);
    $('best-setup').innerHTML = '<span class="label">BEST SETUP (BACKTEST-VALIDATED ONLY)</span><h3>' + esc(best.label || 'No validated setup today') + '</h3><p>' + esc(best.reason || '') + '</p>' +
      (setup ? '<p class="muted">' + setup.legs.map(l => sideTag(l.side) + ' ' + esc(l.name) + ' @ ' + money(l.ref_close)).join('<br>') + '</p>' : '') +
      '<p class="muted">Fired today: ' + ((dataset.setups || []).length ? dataset.setups.map(s => esc(s.label) + ' ' + statusBadge(s.status)).join(' \u00b7 ') : 'none') + '</p>';
    const jev = dataset.jev || {}, j = jev.index;
    if (!j) {
      $('jev-index').innerHTML = '<span class="label">JEV REVIEW</span><h3>Jev not run</h3><p class="muted">' + esc(jev.message || '') + '</p>';
      return;
    }
    const row = (title, a) => a ? '<div class="nc-jev-row"><div><strong>' + esc(title) + ':</strong> <span class="nc-chip ' + esc(STANCE_CLASS[a.choice] || RISK_CLASS[a.choice] || '') + '">' + esc(label(a.choice)) + '</span> <small class="muted">confidence ' + (numeric(a.confidence) ? Math.round(a.confidence * 100) + '%' : '--') + '</small></div>' + probBars(a.probabilities) + '</div>' : '';
    const setupRule = j.setup && (dataset.rules || []).find(r => r.id === j.setup.choice);
    $('jev-index').innerHTML = '<span class="label">JEV REVIEW \u00b7 ' + esc(jev.model || '') + '</span>' +
      row('Direction (5 sessions)', j.direction) + row('Implied volatility', j.volatility) + row('Institutional positioning', j.positioning) +
      (j.setup ? '<div class="nc-jev-row"><div><strong>Setup pick:</strong> <span class="nc-chip">' + esc(setupRule ? setupRule.label : label(j.setup.choice)) + '</span> <small class="muted">confidence ' + (numeric(j.setup.confidence) ? Math.round(j.setup.confidence * 100) + '%' : '--') + '</small></div></div>' : '') +
      row('Position risk', j.risk) + '<p class="muted">' + esc(jev.message || '') + ' Jev reads only the numbers on this page; its confidence is not a probability of profit.</p>';
  }

  // ---------------------------------------------------------------- chain table
  const currentExpiry = () => dataset.expiries.find(e => e.expiry === expiry) || dataset.expiries[0];

  function renderExpiryPicker() {
    const sel = $('expiry');
    sel.innerHTML = dataset.expiries.map(e => '<option value="' + esc(e.expiry) + '">' + esc(date(e.expiry)) + ' \u00b7 ' + e.days_to_expiry + 'd ' + esc(e.kind) + (e.trade_expiry ? ' (setups)' : '') + '</option>').join('');
    const pick = dataset.expiries.find(e => e.trade_expiry) || dataset.expiries[0];
    expiry = pick.expiry;
    sel.value = expiry;
  }

  function renderSigma() {
    const e = currentExpiry(), spot = dataset.index.option_spot;
    $('sigma-card').innerHTML = '<dl class="nc-card-grid">' + [
      card('ATM strike / IV', fmt(e.atm, 0), pctPlain(e.atm_iv, 2) + ' implied'),
      card('ATM straddle', money(e.straddle), pctPlain(e.straddle_pct, 2) + ' of spot'),
      card('1 sigma (68%)', fmt(e.sigma_1[0], 0) + ' \u2013 ' + fmt(e.sigma_1[1], 0), '\u00b1' + fmt(e.expected_move, 0) + ' points'),
      card('2 sigma (95%)', fmt(e.sigma_2[0], 0) + ' \u2013 ' + fmt(e.sigma_2[1], 0), 'Spot ' + fmt(spot)),
      card('25-delta skew', numeric(e.skew25) ? (e.skew25 > 0 ? '+' : '') + fmt(e.skew25, 2) + ' pts' : '--', 'Put ' + fmt(e.put25_strike, 0) + ' vs call ' + fmt(e.call25_strike, 0) + ' IV'),
      card('Walls / max pain', fmt(e.put_wall, 0) + ' / ' + fmt(e.call_wall, 0), 'Max pain ' + fmt(e.max_pain, 0) + ' \u00b7 PCR ' + fmt(e.pcr, 2)),
    ].join('') + '</dl>';
  }

  function renderChain() {
    const e = currentExpiry(), spot = dataset.index.option_spot;
    const centre = e.rows.reduce((best, r, i) => Math.abs(r.strike - spot) < Math.abs(e.rows[best].strike - spot) ? i : best, 0);
    const rows = e.rows.slice(Math.max(0, centre - width), centre + width + 1);
    const maxOi = Math.max(1, ...rows.map(r => Math.max(r.ce.oi || 0, r.pe.oi || 0)));
    const lo = e.sigma_1[0], hi = e.sigma_1[1];
    const side = (o, call) => {
      const itm = call ? rowStrike < spot : rowStrike > spot;
      const cells = [intFmt(o.oi), signedInt(o.oi_chg), intFmt(o.volume), (numeric(o.iv) ? fmt(o.iv, 1) : '--') + (o.iv_estimated ? '*' : ''), fmt(o.delta, 2), fmt(o.gamma, 5), fmt(o.theta, 1), fmt(o.vega, 1)];
      const bar = '<i class="nc-oibar ' + (call ? 'ce' : 'pe') + '" style="width:' + Math.round(100 * (o.oi || 0) / maxOi) + '%"></i>';
      const ordered = call ? cells : cells.slice().reverse();
      return ordered.map((c, i) => '<td class="' + (itm ? 'itm ' : '') + ((call && i === 0) || (!call && i === ordered.length - 1) ? 'nc-oicell' : '') + '">' + ((call && i === 0) || (!call && i === ordered.length - 1) ? bar : '') + c + '</td>').join('');
    };
    let rowStrike = 0;
    $('chain-rows').innerHTML = rows.map(r => {
      rowStrike = r.strike;
      const ce = side(r.ce, true);
      const pe = side(r.pe, false);
      const atm = r.strike === e.atm;
      const inSigma = r.strike >= lo && r.strike <= hi;
      const tags = [r.strike === e.call_wall ? 'call wall' : '', r.strike === e.put_wall ? 'put wall' : '', r.strike === e.max_pain ? 'max pain' : ''].filter(Boolean);
      return '<tr data-strike="' + r.strike + '" class="' + (atm ? 'nc-atm ' : '') + (inSigma ? 'nc-sigma1' : '') + '">' + ce +
        '<td class="itm-ce">' + money(r.ce.close) + '</td><td class="nc-strike"><strong>' + fmt(r.strike, 0) + '</strong>' + (tags.length ? '<small>' + esc(tags.join(' \u00b7 ')) + '</small>' : '') + '</td><td>' + money(r.pe.close) + '</td>' + pe + '</tr>';
    }).join('');
    $('oi-heading').textContent = date(e.expiry) + ' \u00b7 ' + e.days_to_expiry + ' days';
    renderOiChart(e);
  }

  // ---------------------------------------------------------------- SVG charts
  function svgLines(host, series, opts = {}) {
    const W = opts.width || 640, H = opts.height || 220, P = {l: 46, r: 46, t: 14, b: 26};
    const n = Math.max(0, ...series.map(s => s.values.length));
    if (!n) { host.innerHTML = '<p class="muted">No history.</p>'; return; }
    const axes = {};
    for (const s of series) {
      const vals = s.values.filter(numeric);
      if (!vals.length) continue;
      const a = axes[s.axis || 'l'] || (axes[s.axis || 'l'] = {min: Infinity, max: -Infinity});
      a.min = Math.min(a.min, ...vals); a.max = Math.max(a.max, ...vals);
    }
    for (const a of Object.values(axes)) { if (a.max === a.min) { a.max += 1; a.min -= 1; } const pad = (a.max - a.min) * 0.06; a.max += pad; a.min -= pad; }
    const x = i => P.l + (W - P.l - P.r) * (n === 1 ? 0.5 : i / (n - 1));
    const y = (v, ax) => { const a = axes[ax || 'l']; return P.t + (H - P.t - P.b) * (1 - (v - a.min) / (a.max - a.min)); };
    let out = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(opts.title || 'chart') + '">';
    for (const [ax, a] of Object.entries(axes)) {
      for (let k = 0; k <= 3; k++) {
        const v = a.min + (a.max - a.min) * k / 3, yy = y(v, ax);
        if (ax === 'l') out += '<line x1="' + P.l + '" x2="' + (W - P.r) + '" y1="' + yy + '" y2="' + yy + '" class="grid"/>';
        out += '<text x="' + (ax === 'l' ? P.l - 4 : W - P.r + 4) + '" y="' + (yy + 3) + '" text-anchor="' + (ax === 'l' ? 'end' : 'start') + '" class="axis">' + esc(fmt(v, opts.digits ?? 1)) + '</text>';
      }
    }
    for (const s of series) {
      let d = '', pen = false;
      s.values.forEach((v, i) => { if (numeric(v)) { d += (pen ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v, s.axis).toFixed(1); pen = true; } else pen = false; });
      out += '<path d="' + d + '" fill="none" stroke="' + s.color + '" stroke-width="1.8"' + (s.dash ? ' stroke-dasharray="4 3"' : '') + '/>';
    }
    const dates = opts.dates || [];
    if (dates.length) {
      out += '<text x="' + P.l + '" y="' + (H - 6) + '" class="axis">' + esc(date(dates[0])) + '</text><text x="' + (W - P.r) + '" y="' + (H - 6) + '" text-anchor="end" class="axis">' + esc(date(dates[dates.length - 1])) + '</text>';
    }
    out += '</svg><p class="chart-legend">' + series.map(s => '<span class="nc-key" style="--k:' + s.color + '">' + esc(s.name) + (s.axis === 'r' ? ' (right)' : '') + '</span>').join(' ') + '</p>';
    host.innerHTML = out;
  }

  function renderOiChart(e) {
    const p = e.oi_profile, host = $('oi-chart');
    if (!p || !p.strikes.length) { host.innerHTML = '<p class="muted">No open-interest profile for this expiry.</p>'; return; }
    const W = 640, H = 240, P = {l: 50, r: 10, t: 12, b: 34}, spot = dataset.index.option_spot;
    const ce = oiMode === 'oi' ? p.ce_oi : p.ce_oi_chg, pe = oiMode === 'oi' ? p.pe_oi : p.pe_oi_chg;
    const lo = Math.min(0, ...ce, ...pe), hi = Math.max(1, ...ce, ...pe);
    const kmin = p.strikes[0], kmax = p.strikes[p.strikes.length - 1];
    const x = k => P.l + (W - P.l - P.r) * (kmax === kmin ? 0.5 : (k - kmin) / (kmax - kmin));
    const y = v => P.t + (H - P.t - P.b) * (1 - (v - lo) / (hi - lo));
    const bw = Math.max(2, (W - P.l - P.r) / p.strikes.length / 2.4);
    let out = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Open interest by strike">';
    const s1 = e.sigma_1;
    if (numeric(s1[0]) && numeric(s1[1])) out += '<rect x="' + x(Math.max(kmin, s1[0])) + '" width="' + Math.max(0, x(Math.min(kmax, s1[1])) - x(Math.max(kmin, s1[0]))) + '" y="' + P.t + '" height="' + (H - P.t - P.b) + '" class="nc-band"/>';
    out += '<line x1="' + P.l + '" x2="' + (W - P.r) + '" y1="' + y(0) + '" y2="' + y(0) + '" class="grid"/>';
    p.strikes.forEach((k, i) => {
      const yc = y(Math.max(0, ce[i])), yp = y(Math.max(0, pe[i]));
      out += '<rect class="bar-ce" x="' + (x(k) - bw) + '" width="' + bw + '" y="' + Math.min(yc, y(ce[i])) + '" height="' + Math.abs(y(ce[i]) - y(0)) + '"><title>' + esc(fmt(k, 0) + ' CE ' + intFmt(ce[i])) + '</title></rect>';
      out += '<rect class="bar-pe" x="' + x(k) + '" width="' + bw + '" y="' + Math.min(yp, y(pe[i])) + '" height="' + Math.abs(y(pe[i]) - y(0)) + '"><title>' + esc(fmt(k, 0) + ' PE ' + intFmt(pe[i])) + '</title></rect>';
    });
    const mark = (k, cls2, text) => numeric(k) && k >= kmin && k <= kmax ? '<line x1="' + x(k) + '" x2="' + x(k) + '" y1="' + P.t + '" y2="' + (H - P.b) + '" class="' + cls2 + '"/><text x="' + (x(k) + 3) + '" y="' + (P.t + 10) + '" class="axis">' + esc(text) + '</text>' : '';
    out += mark(spot, 'spot-line', 'spot') + mark(e.max_pain, 'mp-line', 'max pain');
    [0, Math.floor(p.strikes.length / 2), p.strikes.length - 1].forEach(i => { out += '<text x="' + x(p.strikes[i]) + '" y="' + (H - 18) + '" text-anchor="middle" class="axis">' + esc(fmt(p.strikes[i], 0)) + '</text>'; });
    out += '<text x="' + (P.l - 4) + '" y="' + (y(hi) + 3) + '" text-anchor="end" class="axis">' + esc(intFmt(hi / 1e5)) + 'L</text></svg>';
    host.innerHTML = out;
  }

  function renderVol() {
    const h = dataset.history || {};
    const vix = new Map((h.vix_dates || []).map((d, i) => [d, h.vix[i]]));
    svgLines($('vol-chart'), [
      {name: 'ATM IV', values: h.atm_iv || [], color: '#3066a0'},
      {name: 'Realised vol (20d)', values: h.rv20 || [], color: '#785b20', dash: true},
      {name: 'India VIX', values: (h.dates || []).map(d => vix.has(d) ? vix.get(d) : null), color: '#ad4037'},
    ], {dates: h.dates, title: 'Volatility history'});
  }

  function renderHhhl() {
    const c = dataset.hhhl || {}, host = $('hhhl-chart'), s = (dataset.index || {}).structure || {};
    $('hhhl-state').textContent = (s.structure || '--') + (s.breakout ? ' \u00b7 fresh breakout' : '') + ' \u00b7 close ' + fmt(s.close) + ' vs 20-day ' + fmt(s.sma20);
    const n = (c.dates || []).length;
    if (!n) { host.innerHTML = '<p class="muted">No index price history.</p>'; return; }
    const W = 1100, H = 320, P = {l: 56, r: 12, t: 22, b: 40};
    const lo = Math.min(...c.low.filter(numeric)), hi = Math.max(...c.high.filter(numeric));
    const x = i => P.l + (W - P.l - P.r) * (i + 0.5) / n;
    const y = v => P.t + (H - P.t - P.b) * (1 - (v - lo) / (hi - lo || 1));
    const bw = Math.max(1.5, (W - P.l - P.r) / n * 0.6);
    let out = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Nifty candles with confirmed swing labels">';
    for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4; out += '<line x1="' + P.l + '" x2="' + (W - P.r) + '" y1="' + y(v) + '" y2="' + y(v) + '" class="grid"/><text x="' + (P.l - 4) + '" y="' + (y(v) + 3) + '" text-anchor="end" class="axis">' + esc(fmt(v, 0)) + '</text>'; }
    c.dates.forEach((d, i) => {
      const o = c.open[i], cl = c.close[i];
      if (![o, cl, c.high[i], c.low[i]].every(numeric)) return;
      const up = cl >= o;
      out += '<line x1="' + x(i) + '" x2="' + x(i) + '" y1="' + y(c.high[i]) + '" y2="' + y(c.low[i]) + '" class="' + (up ? 'wick-up' : 'wick-dn') + '"/>' +
        '<rect x="' + (x(i) - bw / 2) + '" width="' + bw + '" y="' + y(Math.max(o, cl)) + '" height="' + Math.max(1, Math.abs(y(o) - y(cl))) + '" class="' + (up ? 'candle-up' : 'candle-dn') + '"><title>' + esc(d + ' O ' + fmt(o) + ' H ' + fmt(c.high[i]) + ' L ' + fmt(c.low[i]) + ' C ' + fmt(cl)) + '</title></rect>';
    });
    let d = '', pen = false;
    (c.sma20 || []).forEach((v, i) => { if (numeric(v)) { d += (pen ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1); pen = true; } });
    out += '<path d="' + d + '" fill="none" stroke="#667264" stroke-width="1.4"/>';
    const idx = new Map(c.dates.map((dd, i) => [dd, i]));
    for (const p of c.swings || []) {
      if (!idx.has(p.pivot_date)) continue;
      const i = idx.get(p.pivot_date), good = p.label === 'HH' || p.label === 'HL', bad = p.label === 'LH' || p.label === 'LL';
      const yy = p.kind === 'high' ? y(p.price) - 7 : y(p.price) + 14;
      out += '<text x="' + x(i) + '" y="' + yy + '" text-anchor="middle" class="swing ' + (good ? 'swing-good' : bad ? 'swing-bad' : '') + '">' + esc(p.label) + '</text>';
    }
    out += '<text x="' + P.l + '" y="' + (H - 6) + '" class="axis">' + esc(date(c.dates[0])) + '</text><text x="' + (W - P.r) + '" y="' + (H - 6) + '" text-anchor="end" class="axis">' + esc(date(c.dates[n - 1])) + '</text></svg>';
    host.innerHTML = out;
  }

  // ---------------------------------------------------------------- participants
  function renderParticipants() {
    const rows = dataset.participants || [];
    $('participant-rows').innerHTML = rows.length ? rows.map(p => {
      const n = p.net || {}, c = p.net_chg5 || {};
      return '<tr data-participant="' + esc(p.participant) + '"><td><strong>' + esc(p.participant) + '</strong></td><td>' + intFmt(p.fut_long) + '</td><td>' + intFmt(p.fut_short) + '</td><td>' + pctPlain(p.fut_long_share, 0) +
        (numeric(p.fut_long_share_chg5) ? ' <small class="' + cls(p.fut_long_share_chg5) + '">(' + (p.fut_long_share_chg5 > 0 ? '+' : '') + fmt(p.fut_long_share_chg5, 1) + ')</small>' : '') + '</td>' +
        '<td class="' + cls(n.futures) + '">' + signedInt(n.futures) + '</td><td class="' + cls(n.calls) + '">' + signedInt(n.calls) + '</td><td class="' + cls(n.puts) + '">' + signedInt(n.puts) + '</td>' +
        '<td><small>Fut ' + signedInt(c.futures) + ' \u00b7 C ' + signedInt(c.calls) + ' \u00b7 P ' + signedInt(c.puts) + '</small></td><td class="nc-read">' + esc(p.read) + '</td></tr>';
    }).join('') : '<tr><td colspan="9" class="muted">Participant-wise OI was not available for this session.</td></tr>';
    const h = dataset.history || {};
    svgLines($('part-chart'), [
      {name: 'FII index-futures long share %', values: h.fii_long_share || [], color: '#3066a0'},
      {name: 'Client long share %', values: h.client_long_share || [], color: '#ad4037', dash: true},
      {name: 'Nifty', values: h.spot || [], color: '#667264', axis: 'r'},
    ], {dates: h.dates, title: 'Participant positioning history', width: 1100, height: 240, digits: 0});
  }

  // ---------------------------------------------------------------- setups + payoff
  function payoffSvg(p) {
    const c = (p || {}).curve || {};
    if (!c.price || !c.price.length) return '';
    const W = 360, H = 140, P = {l: 44, r: 8, t: 8, b: 18};
    const lo = Math.min(0, ...c.pnl), hi = Math.max(0, ...c.pnl), spot = dataset.index.option_spot;
    const x = v => P.l + (W - P.l - P.r) * (v - c.price[0]) / (c.price[c.price.length - 1] - c.price[0]);
    const y = v => P.t + (H - P.t - P.b) * (1 - (v - lo) / (hi - lo || 1));
    const d = c.price.map((v, i) => (i ? 'L' : 'M') + x(v).toFixed(1) + ' ' + y(c.pnl[i]).toFixed(1)).join('');
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" class="nc-payoff" role="img" aria-label="Expiry payoff per lot"><line x1="' + P.l + '" x2="' + (W - P.r) + '" y1="' + y(0) + '" y2="' + y(0) + '" class="grid"/>' +
      '<line x1="' + x(spot) + '" x2="' + x(spot) + '" y1="' + P.t + '" y2="' + (H - P.b) + '" class="spot-line"/><path d="' + d + '" fill="none" stroke="#246c4e" stroke-width="2"/>' +
      '<text x="' + (P.l - 4) + '" y="' + (y(hi) + 3) + '" text-anchor="end" class="axis">' + esc(intFmt(hi)) + '</text><text x="' + (P.l - 4) + '" y="' + (y(lo) + 3) + '" text-anchor="end" class="axis">' + esc(intFmt(lo)) + '</text>' +
      '<text x="' + P.l + '" y="' + (H - 4) + '" class="axis">' + esc(fmt(c.price[0], 0)) + '</text><text x="' + (W - P.r) + '" y="' + (H - 4) + '" text-anchor="end" class="axis">' + esc(fmt(c.price[c.price.length - 1], 0)) + '</text></svg>';
  }

  function renderSetups() {
    const setups = dataset.setups || [];
    const rules = new Map((dataset.rules || []).map(r => [r.id, r]));
    $('setup-cards').innerHTML = setups.length ? setups.map(s => {
      const r = rules.get(s.rule) || {stats: {}}, st = r.stats || {}, g = s.position_greeks_per_lot || {}, pay = s.payoff || {};
      const sl = s.stop_loss || {}, firing = s.firing !== false, jp = s.jev_priority || {};
      const PRIO_CLS = {top: 'pos', high: 'pos', medium: 'warn', low: 'muted', avoid: 'neg'};
      const prioBadge = jp.tier ? '<span class="nc-chip nc-prio-' + esc(jp.tier) + ' ' + (PRIO_CLS[jp.tier] || '') + '">JEV: ' + esc(jp.tier.toUpperCase()) + (numeric(jp.confidence) ? ' ' + Math.round(jp.confidence * 100) + '%' : '') + '</span>' : '';
      return '<article class="nc-setup ' + (firing ? 'nc-firing' : 'nc-dormant') + '" data-rule="' + esc(s.rule) + '"><header><h3>' + esc(s.label) + '</h3>' + prioBadge + ' ' + (firing ? '<span class="nc-chip pos">FIRING TODAY</span>' : '<span class="nc-chip muted">not triggered</span>') + ' ' + statusBadge(s.status) + '</header>' +
        '<p class="muted">' + esc(s.condition) + '</p><table class="nc-legs"><thead><tr><th>Side</th><th>Contract</th><th>Price (live / ref)</th><th>Delta</th><th>Theta</th></tr></thead><tbody>' +
        s.legs.map(l => '<tr><td>' + sideTag(l.side) + '</td><td>' + esc(l.name) + '</td><td>' + (numeric(l.live_ltp) ? '<b class="pos">' + money(l.live_ltp) + '</b> <small class="muted">live</small>' : money(l.ref_close)) + '</td><td>' + fmt(l.delta, 2) + '</td><td>' + fmt(l.theta, 1) + '</td></tr>').join('') + '</tbody></table>' +
        '<dl class="nc-mini"><div><dt>Position delta / lot</dt><dd>' + fmt(g.delta, 1) + '</dd></div><div><dt>Theta / day / lot</dt><dd class="' + cls(g.theta) + '">' + money(g.theta) + '</dd></div><div><dt>Vega / lot</dt><dd>' + money(g.vega) + '</dd></div>' +
        '<div><dt>Max profit (expiry)</dt><dd class="pos">' + (numeric(pay.max_profit) ? money(pay.max_profit) : 'Unlimited') + '</dd></div><div><dt>Max loss (expiry)</dt><dd class="neg">' + (numeric(pay.max_loss) ? money(pay.max_loss) : 'Unlimited') + '</dd></div>' +
        '<div><dt>Breakeven (expiry)</dt><dd>' + ((pay.breakevens || []).map(b => fmt(b, 0)).join(' / ') || '--') + '</dd></div><div><dt>Model P(profit) at expiry</dt><dd>' + pctPlain(pay.prob_profit_model, 0) + '</dd></div>' +
        '<div class="nc-exit"><dt>Expected P&amp;L at exit (' + ((s.exit || {}).hold_sessions || 5) + 's)</dt><dd class="' + cls((s.exit || {}).exp_pnl_per_lot) + '">' + (numeric((s.exit || {}).exp_pnl_per_lot) ? money((s.exit || {}).exp_pnl_per_lot) : '--') + '</dd></div>' +
        '<div class="nc-exit"><dt>P(profit) at exit</dt><dd>' + pctPlain((s.exit || {}).p_profit, 0) + '</dd></div><div><dt>Exit by</dt><dd>' + esc(date((s.plan || {}).exit_by)) + '</dd></div>' +
        (sl.level_per_lot != null ? '<div class="nc-stop"><dt>Stop-loss / lot</dt><dd class="neg">' + money(sl.level_per_lot) + '</dd></div>' : '') + '</dl>' +
        (sl.rule ? '<p class="muted"><small>\u26d4 Stop: ' + esc(sl.rule) + '</small></p>' : '') +
        payoffSvg(pay) + ((s.plan || {}).payoff_note ? '<p class="muted"><small>' + esc(s.plan.payoff_note) + '</small></p>' : '') + '<p class="muted">Backtest: ' + intFmt(st.trades) + ' trades, win ' + pctPlain(st.win_rate, 0) + ', mean ' + pct(st.mean_return_pct) + ' on ' + esc(st.return_basis || '') + ', t-stat ' + fmt(st.t_stat, 2) + ', worst ' + pct(st.worst_return_pct) + '.</p></article>';
    }).join('') : '<p class="muted">No setup\u2019s trigger condition is met today. See the evidence table below for every rule and how close each trigger is.</p>';
  }


  function renderComparison() {
    const cmp = dataset.comparison;
    const host = $('compare-rows'), bestBox = $('compare-best'), note = $('compare-note');
    if (!cmp || !(cmp.candidates || []).length) {
      if (note) note.textContent = 'No directional comparison for today\u2019s view (needs a bullish or bearish swing structure and a live chain).';
      if (host) host.innerHTML = '<tr><td colspan="9" class="muted">Not available for today.</td></tr>';
      if (bestBox) bestBox.innerHTML = '';
      return;
    }
    if (note) note.textContent = cmp.method || '';
    const jev = cmp.jev || {};
    const jevLine = jev.choice ? ' \u00b7 Jev\u2019s independent pick: <strong>' + esc(label(jev.choice)) + '</strong> (' + Math.round((jev.confidence || 0) * 100) + '% confidence)' : '';
    if (bestBox) bestBox.innerHTML = '<div class="nc-best-structure"><span class="label">BEST STRUCTURE \u00b7 ' + esc(String(cmp.view || '').toUpperCase()) + ' VIEW</span><h3>' + esc((cmp.best || {}).name || '--') + '</h3><p>' + esc((cmp.best || {}).reason || '') + jevLine + '</p></div>';
    host.innerHTML = cmp.candidates.map(c => {
      const ex = c.exit || {}, bt = c.backtest || {}, isBest = (cmp.best || {}).id === c.id;
      return '<tr class="' + (isBest ? 'nc-row-best' : '') + '"><td><strong>' + esc(c.name) + '</strong>' + (isBest ? ' <span class="nc-chip pos">best</span>' : '') + (jev.choice === c.id ? ' <span class="nc-chip">Jev</span>' : '') + '</td>' +
        '<td>' + esc(c.debit_or_credit || '--') + '</td>' +
        '<td class="pos">' + (numeric(c.max_profit_at_expiry) ? money(c.max_profit_at_expiry) : 'Unlimited') + '</td>' +
        '<td class="neg">' + (numeric(c.max_loss_at_expiry) ? money(c.max_loss_at_expiry) : 'Undefined') + '</td>' +
        '<td class="' + cls(ex.exp_pnl_per_lot) + '">' + (numeric(ex.exp_pnl_per_lot) ? money(ex.exp_pnl_per_lot) : '--') + '</td>' +
        '<td>' + pctPlain(ex.p_profit, 0) + '</td>' +
        '<td class="' + cls(c.exp_return_on_risk_pct) + '">' + (numeric(c.exp_return_on_risk_pct) ? fmt(c.exp_return_on_risk_pct, 1) + '%' : '--') + '</td>' +
        '<td>' + (bt.mean_return_pct != null ? pct(bt.mean_return_pct) + ' <small class="muted">(' + intFmt(bt.trades) + ')</small>' : '<span class="muted">no exact backtest</span>') + '</td>' +
        '<td><small>' + esc(c.retail_suitability || '') + '</small></td></tr>';
    }).join('');
  }
  function renderRules() {
    const rules = dataset.rules || [];
    const today = new Set((dataset.setups || []).map(s => s.rule));
    const half = h => h && h.trades ? pct(h.mean_return_pct) + ' <small>(' + h.trades + ')</small>' : '--';
    $('rule-rows').innerHTML = rules.map(r => {
      const s = r.stats || {};
      return '<tr data-rule="' + esc(r.id) + '" class="' + (r.baseline ? 'baseline' : '') + '"><td><strong>' + esc(r.label) + '</strong><small class="muted nc-cond">' + esc(r.condition) + '</small></td><td>' + statusBadge(r.status) + '</td><td>' + esc(r.action) + '</td><td>' + (today.has(r.id) ? '<span class="nc-chip pos">fired</span>' : '') + '</td>' +
        '<td>' + intFmt(s.trades) + '</td><td>' + pctPlain(s.win_rate, 0) + '</td><td class="' + cls(s.mean_return_pct) + '">' + pct(s.mean_return_pct) + '</td><td>' + pct(s.median_return_pct) + '</td><td>' + fmt(s.t_stat, 2) + '</td><td>' + pct(s.worst_return_pct) + '</td><td>' + half(s.first_half) + '</td><td>' + half(s.second_half) + '</td><td>' + esc(s.return_basis || '') + '</td></tr>';
    }).join('');
    const v = rules.filter(r => !r.baseline && r.status === 'VALIDATED').length;
    $('rules-note').textContent = v + ' of ' + rules.filter(r => !r.baseline).length + ' setups validated \u00b7 baselines shown for comparison';
  }

  // ---------------------------------------------------------------- constituents
  function constituentRows() {
    const q = constState.search.trim().toLowerCase();
    let rows = dataset.constituents.filter(c =>
      (constState.status === 'ALL' || c.hhhl_status === constState.status) &&
      (constState.stance === 'ALL' || (c.jev || {}).stance === constState.stance) &&
      (!q || c.symbol.toLowerCase().includes(q) || (c.industry || '').toLowerCase().includes(q) || (c.name || '').toLowerCase().includes(q)));
    const key = {symbol: c => c.symbol, ret5: c => -(c.ret5_pct ?? -1e9), iv: c => -((c.greeks || {}).atm_iv ?? -1e9),
                 move: c => -(((c.greeks || {}).expected_move_5d ?? -1e9) / (c.spot || 1)), jev: c => -((c.jev || {}).stance_confidence ?? -1)}[constState.sort];
    rows = rows.slice().sort((a, b) => { const x = key(a), y = key(b); return typeof x === 'string' ? x.localeCompare(y) : x - y; });
    return rows;
  }

  function renderConstituents() {
    const rows = constituentRows();
    $('const-count').textContent = rows.length + ' of ' + dataset.constituents.length + ' constituents shown';
    $('constituent-rows').innerHTML = rows.map(c => {
      const g = c.greeks || {}, j = c.jev || {};
      return '<tr data-symbol="' + esc(c.symbol) + '"><td><strong>' + esc(c.symbol) + '</strong><small class="muted nc-cond">' + esc(c.industry) + '</small></td>' +
        '<td><span class="status ' + esc(c.hhhl_status || '') + '">' + esc(c.hhhl_status || '--') + '</span></td><td>' + esc(c.structure || '--') + '</td><td>' + fmt(c.spot) + '</td>' +
        '<td class="' + cls(c.ret5_pct) + '">' + pct(c.ret5_pct, 2) + '</td><td>' + esc(c.buildup || '--') + '</td><td>' + fmt(c.pcr, 2) + '</td><td>' + pctPlain(g.atm_iv) + '</td>' +
        '<td>' + fmt(g.call_delta, 2) + '</td><td>' + fmt(g.put_delta, 2) + '</td><td>' + fmt(g.call_theta, 2) + '</td><td>' + (numeric(g.expected_move_5d) ? '\u00b1' + fmt(g.expected_move_5d, 1) : '--') + '</td>' +
        '<td><small>' + esc(label(c.desk_bucket || '--')) + '</small></td>' +
        '<td>' + (j.stance ? '<span class="nc-chip ' + esc(STANCE_CLASS[j.stance] || '') + '">' + esc(j.stance) + '</span> <small class="muted">' + Math.round((j.stance_confidence || 0) * 100) + '%</small>' : '<small class="muted">not run</small>') + '</td>' +
        '<td><small>' + esc(label(j.play || '')) + '</small></td><td>' + (j.risk ? '<span class="nc-chip ' + esc(RISK_CLASS[j.risk] || '') + '">' + esc(j.risk) + '</span>' : '') + '</td></tr>';
    }).join('');
  }

  function renderBreadth() {
    const b = dataset.breadth || {};
    const chips = (obj, kind) => Object.entries(obj || {}).map(([k, v]) => '<span class="nc-chip ' + esc(kind === 'stance' ? STANCE_CLASS[k] || '' : '') + '">' + esc(label(k)) + ' ' + v + '</span>').join(' ');
    $('breadth').innerHTML = '<div><strong>HH/HL status</strong> ' + chips(b.hhhl) + '</div><div><strong>Futures build-up</strong> ' + chips(b.buildup) + '</div><div><strong>Jev stance</strong> ' + chips(b.jev_stance, 'stance') + '</div><div><strong>HH / HL structure</strong> <span class="nc-chip">' + intFmt(b.structure_hh_hl) + ' of ' + intFmt(b.total) + '</span></div>';
  }

  function downloadConstituents() {
    const cols = ['symbol', 'name', 'industry', 'hhhl_status', 'structure', 'spot', 'ret5_pct', 'buildup', 'pcr', 'atm_iv', 'call_delta', 'put_delta', 'call_theta', 'vega', 'expected_move_5d', 'desk_bucket', 'jev_stance', 'jev_stance_confidence', 'jev_play', 'jev_risk'];
    const val = (c, k) => ({atm_iv: (c.greeks || {}).atm_iv, call_delta: (c.greeks || {}).call_delta, put_delta: (c.greeks || {}).put_delta, call_theta: (c.greeks || {}).call_theta,
      vega: (c.greeks || {}).vega, expected_move_5d: (c.greeks || {}).expected_move_5d, jev_stance: (c.jev || {}).stance, jev_stance_confidence: (c.jev || {}).stance_confidence,
      jev_play: (c.jev || {}).play, jev_risk: (c.jev || {}).risk})[k] ?? c[k];
    const cell = v => { const s = String(v ?? ''); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
    const csv = [cols.join(',')].concat(constituentRows().map(c => cols.map(k => cell(val(c, k))).join(','))).join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], {type: 'text/csv'}));
    a.download = 'nifty50-options-' + dataset.as_of + '.csv';
    document.body.appendChild(a); a.click(); a.remove();
  }

  // ---------------------------------------------------------------- research
  function renderResearch() {
    const r = dataset.research || {};
    $('research-meta').textContent = r.generated_at ? 'Cited research compiled ' + date(String(r.generated_at).slice(0, 10)) : 'Research file not available';
    $('institution-list').innerHTML = (r.institutions || []).map(i => '<article class="nc-research"><h4>' + link(i.source_url, i.title) + '</h4><p>' + esc(i.summary) + '</p><small class="muted">' + esc(i.source_name || '') + ' \u00b7 ' + esc(i.date || '') + '</small></article>').join('') || '<p class="muted">No institutional research loaded.</p>';
    const tested = new Map();
    for (const rule of dataset.rules || []) if (rule.catalog) tested.set(rule.catalog, rule);
    $('strategy-rows').innerHTML = (r.strategies || []).map(s => {
      const t = tested.get(s.id);
      return '<tr data-strategy="' + esc(s.id) + '"><td><strong>' + esc(s.name) + '</strong></td><td>' + esc(s.view) + '</td><td><small>' + esc(s.who_uses) + '</small></td><td><small>' + esc(s.legs) + '</small></td><td><small>' + esc(s.edge_source) + '</small></td><td><small>' + esc(s.main_risk) + '</small></td><td><small>' + esc(s.retail_suitability) + '</small></td>' +
        '<td>' + (t ? statusBadge(t.status) + '<small class="muted nc-cond">' + esc(t.label) + '</small>' : '<small class="muted">' + (s.testable_on_eod ? 'not yet' : 'needs intraday data') + '</small>') + '</td><td>' + link(s.source_url, 'source') + '</td></tr>';
    }).join('');
    $('evidence-list').innerHTML = (r.evidence || []).map(e => '<li><strong>' + link(e.source_url, e.title) + '</strong> ' + esc(e.finding) + ' <small class="muted">' + esc(e.source_name || '') + (e.year ? ', ' + esc(e.year) : '') + '</small></li>').join('');
    $('github-rows').innerHTML = (r.github || []).map(g => '<tr><td>' + link(g.url, g.repo) + '</td><td><small>' + esc(g.what) + '</small></td><td>' + esc(g.license || '--') + '</td><td>' + esc(g.last_activity || '--') + '</td></tr>').join('');
    $('caveat-list').innerHTML = (r.caveats || []).concat((r.unverified || []).map(u => 'Unverified: ' + u)).map(c => '<li>' + esc(c) + '</li>').join('');
  }

  function renderCalibration() {
    const cal = (dataset.jev || {}).calibration || {};
    const rows = Object.entries(cal.by_call || {});
    $('jev-calibration').innerHTML = '<p>' + intFmt(cal.matured) + ' matured index calls. ' + esc(cal.note || '') + '</p><div class="nc-cal">' + rows.map(([k, v]) => '<div><strong>' + esc(label(k)) + '</strong><span>' + v.n + ' calls</span><span>' + (v.n ? Math.round(100 * v.hits / v.n) + '% hit' : 'no matured calls yet') + '</span></div>').join('') + '</div>';
  }

  function renderMethod() {
    const m = dataset.method || {}, src = dataset.source || {};
    $('method-greeks').textContent = m.greeks || '';
    $('method-sigma').textContent = m.sigma || '';
    $('method-entry').textContent = (m.entry || '') + ' ' + (m.exit || '');
    $('method-cost').textContent = (m.cost_model || '') + ' ' + (m.return_basis || '');
    $('method-validation').textContent = m.validation || '';
    $('method-nolook').textContent = m.no_lookahead || '';
    $('data-audit').innerHTML = '<ul class="nc-list"><li>F&O bhavcopy: ' + esc(src.bhavcopy_url) + ' (' + intFmt(src.sessions) + ' sessions, ' + esc(src.first_session) + ' to ' + esc(src.last_session) + ')</li>' +
      '<li>Participant-wise OI: ' + esc(src.participant_url) + ' (' + intFmt(src.participant_sessions) + ' sessions)</li><li>Index close: ' + esc(src.index_url) + '</li>' +
      '<li>Constituents: ' + esc(src.constituents_url) + ' (' + esc(src.constituents_source) + ')</li><li>Generated ' + esc(dataset.generated_at) + '</li>' +
      ((src.missing_sessions || []).length ? '<li>Weekdays without a bhavcopy (not holidays): ' + esc(src.missing_sessions.join(', ')) + '</li>' : '') + '</ul>' +
      '<ul class="nc-list">' + (dataset.limitations || []).map(l => '<li>' + esc(l) + '</li>').join('') + '</ul>';
  }

  // ---------------------------------------------------------------- wiring
  function bind() {
    $('expiry').addEventListener('change', e => { expiry = e.target.value; renderSigma(); renderChain(); });
    $('width').addEventListener('change', e => { width = Number(e.target.value) || 20; renderChain(); });
    $('oi-mode').addEventListener('change', e => { oiMode = e.target.value; renderOiChart(currentExpiry()); });
    $('const-status').addEventListener('change', e => { constState.status = e.target.value; renderConstituents(); });
    $('const-stance').addEventListener('change', e => { constState.stance = e.target.value; renderConstituents(); });
    $('const-sort').addEventListener('change', e => { constState.sort = e.target.value; renderConstituents(); });
    $('const-search').addEventListener('input', e => { constState.search = e.target.value; renderConstituents(); });
    $('const-download').addEventListener('click', downloadConstituents);
  }

  function fail(message) {
    const notice = $('notice');
    notice.hidden = false;
    notice.classList.add('error');
    notice.textContent = 'The Nifty chain snapshot could not be shown: ' + message;
    document.querySelectorAll('main > section.scan-section').forEach(s => { s.hidden = true; });
  }
  async function loadLivePrices() {
    try {
      const res = await fetch('nifty_live.json?t=' + Date.now(), {cache: 'no-store'});
      if (!res.ok) return;
      const live = await res.json();
      if (live.nifty50 && live.nifty50.ltp) {
        const idx = dataset.index;
        idx.close = live.nifty50.ltp;
        idx.change_pct = live.nifty50.per_change;
        idx.high = live.nifty50.high;
        idx.low = live.nifty50.low;
      }
      if (live.india_vix && live.india_vix.ltp) {
        dataset.index.vix = live.india_vix.ltp;
        dataset.index.vix_change_pct = live.india_vix.per_change;
      }
      if (live.bank_nifty && live.bank_nifty.ltp) {
        dataset.index.bank_nifty = live.bank_nifty.ltp;
        dataset.index.bank_nifty_change_pct = live.bank_nifty.per_change;
      }
      renderIndex();
      applyLiveMaths(live);
    } catch (err) {}
  }

  // ---------------------------------------------------------------- live display (maths done in backend)
  // The backend (kotak_live.py) recomputes ALL setups + comparison with the audited nifty_chain
  // formulas and ships them in live.live_maths. The browser ONLY displays — no math here.
  function applyLiveMaths(live) {
    if (!live || !live.live_maths || !dataset) return;
    const lm = live.live_maths;
    const spot = lm.spot || (live.nifty50 && live.nifty50.ltp) || dataset.index.close;
    // Map backend setup results by rule id
    const bySetup = {};
    for (const s of lm.setups || []) bySetup[s.rule] = s;
    for (const s of dataset.setups || []) {
      const live1 = bySetup[s.rule];
      if (!live1) continue;
      if (live1.payoff) s.payoff = Object.assign({}, s.payoff, live1.payoff);
      if (live1.exit) s.exit = Object.assign({}, s.exit, live1.exit);
      if (live1.stop_loss) s.stop_loss = live1.stop_loss;
      // live leg premiums
      const liveByStrike = {};
      for (const l of live1.legs || []) liveByStrike[Math.round(l.strike) + (l.option_type || '')] = l.live_ltp;
      for (const l of s.legs) { const k = Math.round(l.strike) + (l.option_type || 'PE'); if (numeric(liveByStrike[k])) l.live_ltp = liveByStrike[k]; }
    }
    // Comparison: apply backend-computed candidate numbers + re-rank by backend best
    const cmp = dataset.comparison, lc = lm.comparison || {};
    if (cmp && Array.isArray(cmp.candidates) && (lc.candidates || []).length) {
      const byId = {};
      for (const c of lc.candidates) byId[c.id] = c;
      for (const c of cmp.candidates) {
        const live2 = byId[c.id];
        if (!live2) continue;
        c.max_profit_at_expiry = live2.max_profit_at_expiry;
        c.max_loss_at_expiry = live2.max_loss_at_expiry;
        if (live2.exit) c.exit = Object.assign({}, c.exit, live2.exit);
        c.exp_return_on_risk_pct = live2.exp_return_on_risk_pct;
        c.stop_loss = live2.stop_loss;
      }
      cmp.candidates.sort((a, b) => (b.exp_return_on_risk_pct || -1e9) - (a.exp_return_on_risk_pct || -1e9));
      if (lc.best_id) {
        const top = cmp.candidates.find(c => c.id === lc.best_id) || cmp.candidates[0];
        cmp.best = {id: top.id, name: top.name,
                    reason: 'Live: highest expected profit per rupee of risk at the 5-session exit (' + (top.exp_return_on_risk_pct || 0).toFixed(1) + '% on max risk).'};
      }
    }
    renderSetups(); renderComparison();
    const stamp = $('live-stamp');
    if (stamp) stamp.textContent = 'Live (backend maths) ' + new Date().toLocaleTimeString('en-IN') + ' \u00b7 spot ' + fmt(spot);
  }

  function startLivePricePoll() {
    loadLivePrices();
    setInterval(loadLivePrices, 30000);
  }


  async function load() {
    try {
      const res = await fetch('nifty_chain.json?t=' + Date.now(), {cache: 'no-store'});
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      validate(data);
      dataset = data;
      document.body.dataset.source = data.as_of;
      renderHeader(); renderIndex(); renderVerdict(); renderExpiryPicker(); renderSigma(); renderChain(); renderVol();
      renderHhhl(); renderParticipants(); renderSetups(); renderComparison(); renderRules(); renderBreadth(); renderConstituents();
      renderResearch(); renderCalibration(); renderMethod(); bind();
      document.body.dataset.ready = 'true';
      startLivePricePoll();
    } catch (err) {
      fail(err && err.message ? err.message : String(err));
      document.body.dataset.ready = 'error';
    }
  }

  load();
})();
