'use strict';
/* kronos.js — NSE Value Lens · Kronos fan chart with HHHL structural context
 * Loads hhhl_scan.json (market gate + scan rows), nifty_chain.json (index context),
 * and kronos_forecast.json (forecast) in parallel.
 * Selector always shows NSEI first then all scan rows.  URL ?symbol= drives initial pick.
 * Forecast gates: model=NeoQuasar/Kronos-small, provenance.kind=kronos-neural,
 *   per-symbol data_as_of non-stale vs scanner date, valid finite positive close paths.
 * Historical candles render independently when any gate fails.
 * NEVER claim a background job is running — missing data is "unavailable".
 */
(() => {
  const SCAN_URL     = 'hhhl_scan.json';
  const FORECAST_URL = 'kronos_forecast.json';
  const CHAIN_URL    = 'nifty_chain.json';

  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const finP = v => typeof v === 'number' && Number.isFinite(v) && v > 0;   // finite positive
  const fin  = v => typeof v === 'number' && Number.isFinite(v);
  const fmt  = (v, d = 0) => fin(v) ? v.toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d }) : '—';
  const money = v => fin(v) ? '₹' + fmt(v, 2) : '—';
  const pct   = v => fin(v) ? (v >= 0 ? '+' : '') + v.toFixed(1) + '%' : '—';

  let scanData  = null;    // hhhl_scan.json
  let forecast  = null;    // kronos_forecast.json
  let chainData = null;    // nifty_chain.json — index context (spot, signal direction)

  // ── URL query param ──────────────────────────────────────────────────────
  function urlSymbol() {
    try { return new URLSearchParams(location.search).get('symbol') || ''; } catch { return ''; }
  }

  // ── Three-way parallel load ──────────────────────────────────────────────
  async function loadAll() {
    const [scanRes, fcRes, chainRes] = await Promise.allSettled([
      fetch(SCAN_URL,     { cache: 'no-store' }).then(r => r.ok ? r.json() : Promise.reject('HTTP ' + r.status)),
      fetch(FORECAST_URL, { cache: 'no-store' }).then(r => r.ok ? r.json() : Promise.reject('HTTP ' + r.status)),
      fetch(CHAIN_URL,    { cache: 'no-store' }).then(r => r.ok ? r.json() : Promise.reject('HTTP ' + r.status)),
    ]);

    if (scanRes.status  === 'fulfilled') scanData  = scanRes.value;
    else showNotice('hhhl_scan.json unavailable — structural context cannot be shown (' + scanRes.reason + ').');

    if (fcRes.status    === 'fulfilled') forecast  = fcRes.value;
    // forecast failure is silent — historical candles will render from scan/forecast.history

    if (chainRes.status === 'fulfilled') chainData = chainRes.value;
    // chain failure is silent — NSEI context simply shows "unavailable"

    populateSelector();
  }

  // ── Selector: NSEI always first, then all scan rows ──────────────────────
  function populateSelector() {
    const sel = $('kro-symbol');
    if (!sel) return;

    const rows  = (scanData && Array.isArray(scanData.rows)) ? scanData.rows : [];
    const nsei  = rows.find(r => r.symbol === 'NSEI')
               || { symbol: 'NSEI', name: 'Nifty 50', status: '' };
    const rest  = rows.filter(r => r.symbol !== 'NSEI');
    const allRows = [nsei, ...rest];

    if (!allRows.length) {
      sel.innerHTML = '<option value="">No scan data available</option>';
    } else {
      sel.innerHTML = allRows.map(r => {
        const tag  = r.status ? ` [${r.status}]` : '';
        const name = r.name   ? ` — ${r.name}`   : '';
        return `<option value="${esc(r.symbol)}">${esc(r.symbol)}${tag}${name}</option>`;
      }).join('');
    }

    const asofEl = $('kro-asof');
    if (asofEl) {
      const scanDate = (scanData && scanData.as_of) || '';
      asofEl.textContent = scanDate
        ? `EOD ${scanDate} · ${allRows.length} symbols · EOD data only`
        : `${allRows.length} symbols · EOD data only`;
    }

    // URL param overrides default first
    const desired = urlSymbol();
    if (desired && [...sel.options].some(o => o.value === desired)) sel.value = desired;

    sel.addEventListener('change', () => renderSymbol(sel.value));
    renderSymbol(sel.value);
  }

  // ── Market gate (always shown from hhhl_scan.json) ───────────────────────
  function renderMarketGate() {
    const el = $('kro-market-gate');
    if (!el) return;
    const gate = scanData && scanData.market;
    if (!gate) {
      el.innerHTML = '<span style="color:var(--muted)">Market gate — unavailable</span>';
      return;
    }
    const open = gate.data_ready === true && gate.new_entries_allowed === true;
    const badgeCls = open ? 'kro-gate-open' : 'kro-gate-closed';
    const badgeTxt = open ? 'MARKET GATE OPEN' : 'MARKET GATE CLOSED';

    const chainCtx = chainData?.index
      ? `<div class="kro-gate-note">Nifty close ${money(chainData.index.close)} · source ${esc(chainData.as_of)} · structure ${esc(chainData.index.structure?.structure || 'unavailable')}</div>` : '';

    el.innerHTML =
      `<div class="kro-gate-row">
        <span class="kro-gate-badge ${badgeCls}">${badgeTxt}</span>
        <span class="kro-gate-meta">Nifty ${money(gate.close)} · SMA200 ${money(gate.sma200)} · ${esc(gate.data_date)} · ${gate.data_ready ? 'completed data' : 'data incomplete'}</span>
      </div>`
      + (gate.note ? `<div class="kro-gate-note">${esc(gate.note)}</div>` : '')
      + chainCtx;
  }

  // ── Render for selected symbol ───────────────────────────────────────────
  function renderSymbol(sym) {
    if (!sym) return;
    // update URL without reload
    try {
      const u = new URL(location.href);
      u.searchParams.set('symbol', sym);
      history.replaceState(null, '', u.toString());
    } catch { /* navigation unavailable in test env */ }

    const row = sym === 'NSEI' ? niftyRow() : scanData?.rows?.find(r => r.symbol === sym);

    const cnt = $('kro-path-count');
    if (cnt) cnt.textContent = '';
    const legend = $('kro-legend');
    if (legend) legend.hidden = true;

    renderMarketGate();
    renderInterpPanel(row, sym);
    renderForecast(row, sym);
  }

  function niftyRow() {
    if (!chainData?.index) return null;
    const index = chainData.index, structure = index.structure || {};
    return {
      symbol: 'NSEI', name: 'Nifty 50', close: index.close, data_date: chainData.as_of,
      structure: structure.structure, status: structure.structure || 'UNAVAILABLE',
      reason: chainData.best_setup?.reason || 'Confirmed Nifty structure; no validated trade recommendation.',
      entry_allowed: scanData?.market?.new_entries_allowed === true,
      fresh_breakout: structure.breakout,
      zones: {breakout_above: structure.confirmed_high, structure_exit_below: structure.confirmed_low},
    };
  }

  function sourceHistory(sym) {
    const row = scanData?.rows?.find(r => r.symbol === sym);
    const h = chainData?.hhhl;
    const bars = sym === 'NSEI' && Array.isArray(h?.dates)
      ? h.dates.map((d, i) => ({d, o:h.open?.[i], h:h.high?.[i], l:h.low?.[i], c:h.close?.[i]}))
      : (row?.chart || []).map(b => ({d:b.date, o:b.open, h:b.high, l:b.low, c:b.close}));
    return bars.filter(b => /^\d{4}-\d{2}-\d{2}$/.test(b.d) && [b.o,b.h,b.l,b.c].every(finP)
      && b.h >= Math.max(b.o,b.c) && b.l <= Math.min(b.o,b.c)).slice(-40);
  }

  // ── Factual interpretation panel ─────────────────────────────────────────
  // Shows scanner data only: status, reason, breakout ref, structural exit,
  // extended_above warning.  No buy/sell advice.
  function renderInterpPanel(row, sym) {
    const el = $('kro-interp');
    if (!el) return;
    if (!row) {
      el.innerHTML = `<span class="kro-unavailable">Structural context unavailable for ${esc(sym)} — not in scan data.</span>`;
      return;
    }

    const statusCls   = esc(row.status || 'FLAT');
    const breakoutRef = fin(row.zones && row.zones.breakout_above)
                        ? money(row.zones.breakout_above) : '—';
    const structExit  = fin(row.zones && row.zones.structure_exit_below)
                        ? money(row.zones.structure_exit_below) : '—';
    const close       = money(row.close);
    const dataDate    = esc(row.data_date || '—');
    const distPct     = fin(row.distance_to_breakout_pct) ? pct(row.distance_to_breakout_pct) : '—';
    const atrPct      = fin(row.atr_pct) ? row.atr_pct.toFixed(1) + '%' : '—';

    const extWarning = fin(row.zones?.extended_above)
      ? `<div class="kro-ext-warning">Overextension warning above ${money(row.zones.extended_above)}${row.close > row.zones.extended_above ? ' — currently exceeded' : ''}. This is not a price target.</div>`
      : '';

    const facts = [
      ['Last close',     close],
      ['Data date',      dataDate],
      ['Confirmed structure', esc(row.structure || 'unavailable')],
      ['Breakout ref',   breakoutRef],
      ['Structure exit', structExit],
      ['Dist to breakout', distPct],
      ['ATR%',           atrPct],
      ['Sector',         esc(row.sector || '—')],
    ];

    el.innerHTML =
      `<div class="kro-interp-header">
        <span class="kro-sym-title">${esc(sym)}</span>
        ${row.name ? `<span class="kro-meta">${esc(row.name)}</span>` : ''}
        <span class="state ${statusCls}">${statusCls}</span>
        ${row.fresh_breakout ? `<span class="kro-badge-fresh">Fresh breakout</span>` : ''}
        ${row.entry_allowed === false ? `<span class="state AVOID">Entry blocked</span>` : ''}
      </div>
      ${row.reason ? `<div class="kro-reason">${esc(row.reason)}</div>` : ''}
      <div class="kro-facts">${facts.map(([lbl, val]) =>
        `<dl class="kro-fact"><dt>${lbl}</dt><dd>${val}</dd></dl>`
      ).join('')}</div>
      ${extWarning}
      <div class="kro-interp-note">
        Breakout reference and structure exit are factual scanner reference levels — not guaranteed trade signals or price targets.
        extended_above is an overextension warning only, never a target.
      </div>`;
  }

  // ── Forecast gate sequence → then render or candles-only ─────────────────
  function renderForecast(row, sym) {
    const fcEl   = $('kro-forecast');
    const statsEl = $('kro-stats');
    const legend  = $('kro-legend');
    const cntEl   = $('kro-path-count');

    if (legend)  legend.hidden = true;
    if (statsEl) statsEl.innerHTML = '';
    if (cntEl)   cntEl.textContent = '';

    function notice(msg) {
      if (fcEl) fcEl.innerHTML = `<div class="kro-notice">${esc(msg)}</div>`;
    }

    // No forecast loaded
    if (!forecast) {
      notice('Forecast unavailable — kronos_forecast.json could not be loaded.');
      renderHistoricalOnly(sym);
      return;
    }

    // Gate 1: model name
    if (forecast.model !== 'NeoQuasar/Kronos-small') {
      notice('Forecast unavailable — model field does not match NeoQuasar/Kronos-small'
           + (forecast.model ? ` (got: ${forecast.model})` : ' (field missing or pending)') + '.');
      renderHistoricalOnly(sym);
      return;
    }

    // Per-symbol entry
    const entry = forecast.symbols && forecast.symbols[sym];
    if (!entry) {
      notice(`Forecast unavailable — no entry for ${sym} in forecast data.`);
      renderHistoricalOnly(sym);
      return;
    }

    // Gate 2: provenance.kind
    const prov = entry.provenance || {};
    if (forecast.provenance?.kind !== 'kronos-neural' || prov.kind !== 'kronos-neural' || prov.model !== forecast.model) {
      notice('Forecast unavailable — provenance.kind is not kronos-neural'
           + (prov.kind ? ` (got: ${prov.kind})` : ' (field absent)') + '.');
      renderHistoricalOnly(sym);
      return;
    }

    // Gate 3: per-symbol data_as_of present and non-stale vs scanner
    const entryDate = entry.data_as_of || '';
    const scanDate = scanData?.as_of || '';
    if (!entryDate) {
      notice('Forecast unavailable — per-symbol data_as_of is missing.');
      renderHistoricalOnly(sym);
      return;
    }
    if (!scanDate || entryDate !== scanDate || entry.input_stale || row?.data_date !== entryDate) {
      notice(`Forecast stale or mismatched — input ${entryDate}, scanner ${scanDate || 'unavailable'}, symbol ${row?.data_date || 'unavailable'}.`);
      renderHistoricalOnly(sym);
      return;
    }

    // Gate 4: valid close-only paths ({d, c}) with finite positive c
    const rawPaths = Array.isArray(entry.paths) ? entry.paths : [];
    const validPaths = rawPaths.filter(p =>
      Array.isArray(p) && p.length === forecast.pred_len
      && p.every((bar, i) => bar && /^\d{4}-\d{2}-\d{2}$/.test(bar.d) && finP(bar.c)
        && bar.d > (i ? p[i-1].d : entryDate))
    );
    if (!finP(entry.last_close) || !validPaths.length || validPaths.length !== rawPaths.length
        || validPaths.length !== entry.config?.n_samples
        || validPaths.some(p => p.some((b,i) => b.d !== validPaths[0][i].d))) {
      notice('Forecast unavailable — no paths with valid finite close values (expected {d, c} per bar).');
      renderHistoricalOnly(sym);
      return;
    }

    // All gates passed — clear notice and render
    if (fcEl) fcEl.innerHTML = '';
    renderStats(entry, validPaths, sym);
    renderFanChart({...entry, history: sourceHistory(sym)}, validPaths, row, sym);
    if (legend) legend.hidden = false;
    if (cntEl) cntEl.textContent = `${validPaths.length} sample paths`;
  }

  // ── Historical candles only (gates failed or no forecast) ─────────────────
  function renderHistoricalOnly(sym) {
    const svgEl = $('kronos-chart');
    if (!svgEl) return;
    const history = sourceHistory(sym);
    if (!history.length) {
      svgEl.innerHTML = `<text x="600" y="220" text-anchor="middle" fill="#7d8590" font-size="13">No historical candle data for ${esc(sym)}</text>`;
      return;
    }
    renderCandlesOnly(history, sym);
  }

  // ── Historical candlestick chart ──────────────────────────────────────────
  function renderCandlesOnly(history, sym) {
    const svgEl = $('kronos-chart');
    if (!svgEl) return;
    const W = 1200, H = 440, mL = 10, mR = 72, mT = 24, mB = 40;
    const cW = W - mL - mR, cH = H - mT - mB;
    const n  = history.length;
    if (!n) return;
    const bw = Math.max(2, cW / n * 0.55);
    const xH = i => mL + (cW / n) * (i + 0.5);

    const prices = history.flatMap(b => [b.h, b.l, b.o, b.c].filter(fin));
    if (!prices.length) {
      svgEl.innerHTML = `<text x="600" y="220" text-anchor="middle" fill="#7d8590" font-size="13">No price data for ${esc(sym)}</text>`;
      return;
    }
    const loP = Math.min(...prices) * 0.98;
    const hiP = Math.max(...prices) * 1.02;
    const yf  = v => mT + cH * (1 - (v - loP) / (hiP - loP));

    const ax = `font-size="9" fill="#7d8590" font-family="system-ui"`;
    let s = '';
    for (let k = 0; k <= 5; k++) {
      const gp = loP + (hiP - loP) * k / 5, gy = yf(gp).toFixed(1);
      s += `<line x1="${mL}" x2="${W-mR}" y1="${gy}" y2="${gy}" stroke="#21262d" stroke-width="1"/>`;
      s += `<text x="${W-mR+4}" y="${(+gy+4).toFixed(1)}" ${ax}>${Math.round(gp).toLocaleString('en-IN')}</text>`;
    }
    for (let i = 0; i < n; i++) {
      const b = history[i];
      if (!fin(b.o) || !fin(b.c)) continue;
      const up  = b.c >= b.o, col = up ? '#3fb950' : '#f85149';
      const yHi = yf(b.h).toFixed(1);
      const yLo = yf(b.l).toFixed(1);
      s += `<line x1="${xH(i).toFixed(1)}" x2="${xH(i).toFixed(1)}" y1="${yHi}" y2="${yLo}" stroke="${col}" stroke-width="0.8"/>`;
      s += `<rect x="${(xH(i)-bw/2).toFixed(1)}" width="${bw.toFixed(1)}" y="${yf(Math.max(b.o,b.c)).toFixed(1)}" height="${Math.max(1.5,Math.abs(yf(b.o)-yf(b.c))).toFixed(1)}" fill="${col}" rx="0.5"/>`;
    }
    [0, Math.floor(n/2), n-1].forEach(i => {
      const d = history[i]?.d;
      if (d) s += `<text x="${xH(i).toFixed(1)}" y="${H-8}" text-anchor="middle" ${ax}>${esc(d.slice(5))}</text>`;
    });
    s += `<text x="${mL+cW/2}" y="${mT+14}" text-anchor="middle" font-size="13" font-weight="700" fill="#e6edf3" font-family="system-ui">${esc(sym)} · Historical EOD candles</text>`;
    svgEl.innerHTML = s;
    svgEl.setAttribute('aria-label', `Historical EOD candlestick chart for ${esc(sym)}`);
  }

  // ── Stats: actual sample count, median, range, above/below ───────────────
  // Never uses "profit probability" or regime heuristic language.
  function renderStats(entry, validPaths, sym) {
    const el = $('kro-stats');
    if (!el) return;

    const nSamples  = validPaths.length;
    const predLen   = validPaths[0].length;
    const lastClose = entry.last_close;

    // Per-bar across all valid paths
    const endCloses = validPaths.map(p => p[predLen - 1]?.c).filter(fin);
    const sorted    = [...endCloses].sort((a, b) => a - b);
    const medEnd = sorted.length ? (sorted[Math.floor((sorted.length-1)/2)] + sorted[Math.floor(sorted.length/2)]) / 2 : null;
    const p10End    = sorted.length ? sorted[Math.floor(sorted.length * 0.10)] : null;
    const p90End    = sorted.length ? sorted[Math.floor(sorted.length * 0.90)] : null;

    const aboveLC   = (fin(lastClose) && sorted.length)
                    ? sorted.filter(c => c > lastClose).length : null;

    const medRet = (medEnd != null && fin(lastClose) && lastClose > 0)
                 ? (medEnd - lastClose) / lastClose * 100 : null;

    const dataAsOf = esc(entry.data_as_of || '—');

    el.innerHTML = [
      ['Samples',          nSamples + ' paths',                         ''],
      ['Data as-of',       dataAsOf,                                    ''],
      ['Last close',       money(lastClose),                            ''],
      ['Median return',    medRet != null ? pct(medRet) : '—',          fin(medRet) && medRet >= 0 ? 'up' : 'dn'],
      ['Paths above / not above', aboveLC != null ? `${aboveLC} / ${nSamples - aboveLC}` : '—', ''],
      ['p10 – p90 end',   (p10End != null && p90End != null)
                          ? `${money(p10End)} – ${money(p90End)}` : '—', ''],
      ['Horizon',          predLen + ' trading days',                   ''],
    ].map(([label, val, cls]) =>
      `<div class="kro-stat"><dt>${label}</dt><dd class="${cls}">${val}</dd></div>`
    ).join('');
  }

  // ── Fan chart: close-only paths {d,c} ────────────────────────────────────
  // History is real OHLC.  Forecast paths are model-generated closes, not observed candles.
  function renderFanChart(entry, validPaths, row, sym) {
    const svgEl = $('kronos-chart');
    if (!svgEl) return;

    const history   = (entry.history && Array.isArray(entry.history)) ? entry.history : [];
    const lastClose = entry.last_close || 0;
    const nHist     = history.length;
    const nPred     = validPaths[0].length;

    const W = 1200, H = 440, mL = 10, mR = 72, mT = 24, mB = 40;
    const sepGap = 12;
    const cW   = W - mL - mR;
    const cH   = H - mT - mB;
    const histW = nHist ? Math.round(cW * 0.42) : 0;
    const predW = cW - histW - sepGap;
    const bw    = nHist ? Math.max(2, histW / nHist * 0.55) : 0;
    const xH    = i => mL + (histW / Math.max(nHist, 1)) * (i + 0.5);
    const xP    = i => mL + histW + sepGap + (predW / nPred) * (i + 0.5);

    const histPrices = history.flatMap(b => [b.h, b.l].filter(fin));
    const predCloses = validPaths.flatMap(p => p.map(bar => bar.c).filter(finP));
    const allP = [...histPrices, ...predCloses];
    if (!allP.length) {
      svgEl.innerHTML = `<text x="600" y="220" text-anchor="middle" fill="#7d8590" font-size="13">No price data for ${esc(sym)}</text>`;
      return;
    }
    const loRaw = Math.min(...allP), hiRaw = Math.max(...allP);
    const pad   = (hiRaw - loRaw) * 0.12 || Math.abs(lastClose) * 0.05 || 10;
    const loP   = loRaw - pad, hiP = hiRaw + pad;
    const yf    = v => mT + cH * (1 - (v - loP) / (hiP - loP));

    const ax = `font-size="9" fill="#7d8590" font-family="system-ui"`;
    let s = '';

    // Grid lines
    for (let k = 0; k <= 5; k++) {
      const gp = loP + (hiP - loP) * k / 5, gy = yf(gp).toFixed(1);
      s += `<line x1="${mL}" x2="${W-mR}" y1="${gy}" y2="${gy}" stroke="#21262d" stroke-width="1"/>`;
      s += `<text x="${W-mR+4}" y="${(+gy+4).toFixed(1)}" ${ax}>${Math.round(gp).toLocaleString('en-IN')}</text>`;
    }

    // p10–p90 band on forecast
    const bandLo = [], bandHi = [];
    for (let i = 0; i < nPred; i++) {
      const vals = validPaths.map(p => p[i]?.c).filter(finP).sort((a,b)=>a-b);
      if (vals.length) {
        bandLo.push([xP(i), yf(vals[Math.floor(vals.length * 0.10)])]);
        bandHi.push([xP(i), yf(vals[Math.floor(vals.length * 0.90)])]);
      }
    }
    if (bandLo.length > 1) {
      const top = bandHi.map(([x,y])=>`${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
      const bot = [...bandLo].reverse().map(([x,y])=>`${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
      s += `<polygon points="${top} ${bot}" fill="rgba(188,140,255,0.10)" stroke="none"/>`;
    }

    // Fan paths (model-generated closes only, coloured by end vs last close)
    for (const path of validPaths) {
      const finalC = path[nPred-1]?.c;
      const col    = finP(finalC) && finalC >= lastClose ? '#3fb950' : '#f85149';
      const pts    = path.map((bar, i) => finP(bar.c) ? `${xP(i).toFixed(1)},${yf(bar.c).toFixed(1)}` : null).filter(Boolean);
      if (pts.length > 1)
        s += `<polyline points="${pts.join(' ')}" fill="none" stroke="${col}" stroke-width="0.9" opacity="0.30"/>`;
    }

    // Median path (sample median close at each step)
    const medPts = [];
    for (let i = 0; i < nPred; i++) {
      const vals = validPaths.map(p => p[i]?.c).filter(finP).sort((a,b)=>a-b);
      if (vals.length) medPts.push(`${xP(i).toFixed(1)},${yf((vals[Math.floor((vals.length-1)/2)]+vals[Math.floor(vals.length/2)])/2).toFixed(1)}`);
    }
    if (medPts.length > 1)
      s += `<polyline points="${medPts.join(' ')}" fill="none" stroke="rgba(255,255,255,0.75)" stroke-width="2" stroke-linejoin="round"/>`;

    // Historical OHLC candlesticks
    if (nHist) {
      for (let i = 0; i < nHist; i++) {
        const b = history[i];
        if (!fin(b.o) || !fin(b.c)) continue;
        const up  = b.c >= b.o, col = up ? '#3fb950' : '#f85149';
        const yHi = yf(b.h).toFixed(1);
        const yLo = yf(b.l).toFixed(1);
        s += `<line x1="${xH(i).toFixed(1)}" x2="${xH(i).toFixed(1)}" y1="${yHi}" y2="${yLo}" stroke="${col}" stroke-width="0.8"/>`;
        s += `<rect x="${(xH(i)-bw/2).toFixed(1)}" width="${bw.toFixed(1)}" y="${yf(Math.max(b.o,b.c)).toFixed(1)}" height="${Math.max(1.5,Math.abs(yf(b.o)-yf(b.c))).toFixed(1)}" fill="${col}" rx="0.5"/>`;
      }
    }

    // Last-close dashed reference into forecast zone
    if (finP(lastClose)) {
      const lcY = yf(lastClose).toFixed(1);
      s += `<line x1="${mL+histW}" x2="${W-mR}" y1="${lcY}" y2="${lcY}" stroke="#7d8590" stroke-width="0.8" stroke-dasharray="4 3" opacity="0.6"/>`;
      s += `<text x="${W-mR+4}" y="${(+lcY-3).toFixed(1)}" font-size="8" fill="#7d8590" font-family="system-ui">Last</text>`;
    }

    // NOW separator
    if (nHist) {
      const sepX = (mL + histW + sepGap/2).toFixed(1);
      s += `<line x1="${sepX}" x2="${sepX}" y1="${mT}" y2="${mT+cH}" stroke="#58a6ff" stroke-width="1.2" stroke-dasharray="6 4" opacity="0.5"/>`;
      s += `<text x="${sepX}" y="${mT-6}" text-anchor="middle" font-size="9" fill="#58a6ff" font-family="system-ui">NOW</text>`;
    }

    // Date labels
    [0, Math.floor(nHist/2), nHist-1].forEach(i => {
      const d = history[i]?.d;
      if (d) s += `<text x="${xH(i).toFixed(1)}" y="${H-8}" text-anchor="middle" ${ax}>${esc(d.slice(5))}</text>`;
    });
    [0, Math.floor(nPred/2), nPred-1].forEach(i => {
      const d = validPaths[0]?.[i]?.d;
      if (d) s += `<text x="${xP(i).toFixed(1)}" y="${H-8}" text-anchor="middle" ${ax}>${esc(d.slice(5))}</text>`;
    });

    // Chart labels
    if (nHist)
      s += `<text x="${mL+histW/2}" y="${mT+14}" text-anchor="middle" font-size="11" fill="#e6edf3" font-family="system-ui" font-weight="700">${esc(sym)} · observed EOD candles</text>`;
    s += `<text x="${mL+histW+sepGap+predW/2}" y="${mT+14}" text-anchor="middle" font-size="10" fill="#bc8cff" font-family="system-ui">${validPaths.length} model-generated close paths · ${nPred}d</text>`;
    s += `<text x="${mL+histW+sepGap+predW/2}" y="${H-20}" text-anchor="middle" font-size="9" fill="#7d8590" font-family="system-ui">model-generated close paths, not observed future candles</text>`;

    svgEl.innerHTML = s;
    svgEl.setAttribute('aria-label', `Kronos fan chart for ${esc(sym)} · ${validPaths.length} sample close paths · ${nPred}-day horizon`);
  }

  // ── Notice banner ────────────────────────────────────────────────────────
  function showNotice(msg) {
    const el = $('kro-notice');
    if (el) { el.textContent = msg; el.hidden = false; }
  }

  // ── Boot ─────────────────────────────────────────────────────────────────
  loadAll();
})();
