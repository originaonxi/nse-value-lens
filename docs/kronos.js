'use strict';
/* kronos.js — 100-path Kronos fan chart renderer for NSE Value Lens */
(() => {
  const DATA_URL = 'kronos_forecast.json';
  const SVG_NS   = 'http://www.w3.org/2000/svg';

  let dataset = null;
  let currentSymbol = null;

  // ── Helpers ──────────────────────────────────────────────────────────────
  const $ = id => document.getElementById(id);
  const fin = v => typeof v === 'number' && Number.isFinite(v);
  const fmt = (v, d = 2) => fin(v) ? v.toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d }) : '—';
  const money = v => fin(v) ? '₹' + fmt(v) : '—';
  const pctStr = v => fin(v) ? (v >= 0 ? '+' : '') + fmt(v, 1) + '%' : '—';

  // ── Load data ─────────────────────────────────────────────────────────────
  async function load() {
    try {
      const res = await fetch(DATA_URL, { cache: 'no-store' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      dataset = await res.json();
      init();
    } catch (e) {
      showError('Could not load kronos_forecast.json — ' + e.message +
        '. Run kronos_forecast.py to generate it.');
    }
  }

  function showError(msg) {
    const svg = $('kronos-chart');
    if (svg) svg.innerHTML =
      `<text x="600" y="220" text-anchor="middle" fill="#f85149" font-size="13">${msg}</text>`;
  }

  // ── Init: populate selector ───────────────────────────────────────────────
  function init() {
    const sel = $('kro-symbol');
    if (!sel) return;

    const symbols = Object.keys(dataset.symbols || {});
    if (!symbols.length) { showError('No symbols in forecast JSON.'); return; }

    // Update metadata
    const asof = $('kro-asof');
    if (asof) asof.textContent =
      `EOD ${dataset.as_of || ''} · ${dataset.n_paths || 100} paths · pred ${dataset.pred_len || 24} days`;

    sel.innerHTML = symbols.map(sym => {
      const s = dataset.symbols[sym];
      const label = s.status ? `[${s.status}] ${sym} — ${s.name || sym}` : `${sym} — ${s.name || sym}`;
      return `<option value="${sym}">${label}</option>`;
    }).join('');

    sel.addEventListener('change', () => renderSymbol(sel.value));
    renderSymbol(symbols[0]);
  }

  // ── Render one symbol ─────────────────────────────────────────────────────
  function renderSymbol(sym) {
    if (!sym || !dataset) return;
    currentSymbol = sym;
    const s = dataset.symbols[sym];
    if (!s) return;

    renderRegime(s);
    renderStats(s, sym);
    renderFanChart(s, sym);

    const cnt = $('kro-path-count');
    if (cnt) cnt.textContent = (s.paths || []).length + ' paths';
  }

  // ── Regime badge ──────────────────────────────────────────────────────────
  function renderRegime(s) {
    const wrap = $('kro-regime-wrap');
    if (!wrap) return;
    const regime = s.regime || 'UNKNOWN';
    const cls = regime.includes('↑') ? 'trend-up'
              : regime.includes('↓') ? 'trend-dn'
              : regime.includes('↔') || regime.includes('CHOPPY') ? 'choppy'
              : 'mixed';
    wrap.innerHTML =
      `<div class="kro-regime ${cls}" role="status" aria-label="Market regime: ${regime}">${regime}</div>`;
  }

  // ── Stats cards ───────────────────────────────────────────────────────────
  function renderStats(s, sym) {
    const el = $('kro-stats');
    if (!el) return;
    const pa = fin(s.pct_above) ? Math.round(s.pct_above * 100) : null;
    const mr = s.median_ret;
    const sp = s.spread_pct;
    el.innerHTML = [
      ['Last close',     money(s.last_close), ''],
      ['Paths above',   pa != null ? pa + '%' : '—', pa >= 50 ? 'up' : 'dn'],
      ['Median return', pctStr(mr), fin(mr) && mr >= 0 ? 'up' : 'dn'],
      ['Spread (±1σ)',  fin(sp) ? fmt(sp, 1) + '%' : '—', ''],
      ['Pred horizon',  (dataset.pred_len || 24) + ' days', ''],
    ].map(([label, val, cls]) =>
      `<div class="kro-stat"><dt>${label}</dt><dd class="${cls}">${val}</dd></div>`
    ).join('');
  }

  // ── Fan chart SVG ─────────────────────────────────────────────────────────
  function renderFanChart(s, sym) {
    const svgEl = $('kronos-chart');
    if (!svgEl) return;

    const history = s.history || [];
    const paths   = s.paths   || [];
    const lastClose = s.last_close || 0;
    const nHist = history.length;
    const nPred = (paths[0] || []).length;
    if (!nHist || !paths.length || !nPred) {
      svgEl.innerHTML = `<text x="600" y="220" text-anchor="middle" fill="#7d8590" font-size="13">No data for ${sym}</text>`;
      return;
    }

    // Chart dimensions
    const W = 1200, H = 440;
    const marginL = 10, marginR = 72, marginT = 24, marginB = 40;
    const sepGap  = 12;   // gap width at separator
    const chartW  = W - marginL - marginR;
    const chartH  = H - marginT - marginB;

    // X layout: history + small gap + forecast
    const histW   = Math.round(chartW * 0.42);
    const predW   = chartW - histW - sepGap;
    const xH      = i => marginL + (histW / nHist) * (i + 0.5);     // historical bar x
    const barW    = Math.max(2, (histW / nHist) * 0.55);
    const xP      = i => marginL + histW + sepGap + (predW / nPred) * (i + 0.5); // forecast x

    // Price scale: span all historical + all path prices
    const allClose = [
      ...history.map(b => b.h), ...history.map(b => b.l),
      ...paths.flatMap(path => path.map(c => c.h)),
      ...paths.flatMap(path => path.map(c => c.l)),
    ].filter(fin);
    if (!allClose.length) return;

    let loP = Math.min(...allClose);
    let hiP = Math.max(...allClose);
    const pad = (hiP - loP) * 0.12 || lastClose * 0.05;
    loP -= pad; hiP += pad;
    const yf = v => marginT + chartH * (1 - (v - loP) / (hiP - loP));

    // Grid labels
    const gridN = 5;
    let svgStr = '';
    for (let k = 0; k <= gridN; k++) {
      const gp = loP + (hiP - loP) * k / gridN;
      const gy = yf(gp).toFixed(1);
      svgStr += `<line x1="${marginL}" x2="${W - marginR}" y1="${gy}" y2="${gy}" stroke="#21262d" stroke-width="1"/>`;
      svgStr += `<text x="${W - marginR + 4}" y="${(parseFloat(gy) + 4).toFixed(1)}" font-size="9" fill="#7d8590" font-family="system-ui">${Math.round(gp).toLocaleString('en-IN')}</text>`;
    }

    // 10–90th percentile band on fan
    const pctBand = (i, lo, hi) => {
      const vals = paths.map(p => p[i]?.c).filter(fin).sort((a, b) => a - b);
      if (!vals.length) return null;
      const n = vals.length;
      return [vals[Math.floor(n * lo)], vals[Math.floor(n * hi)]];
    };
    const bandPts10 = [], bandPts90 = [];
    for (let i = 0; i < nPred; i++) {
      const b = pctBand(i, 0.1, 0.9);
      if (b) { bandPts10.push([xP(i), yf(b[0])]); bandPts90.push([xP(i), yf(b[1])]); }
    }
    if (bandPts10.length > 1) {
      const polyTop = bandPts90.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
      const polyBot = [...bandPts10].reverse().map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
      svgStr += `<polygon points="${polyTop} ${polyBot}" fill="rgba(188,140,255,0.10)" stroke="none"/>`;
    }

    // 100 fan paths — colored by final close vs last close
    for (const path of paths) {
      const finalClose = path[nPred - 1]?.c;
      const col = fin(finalClose) && finalClose >= lastClose ? '#3fb950' : '#f85149';
      const pts = path.map((c, i) => fin(c.c) ? `${xP(i).toFixed(1)},${yf(c.c).toFixed(1)}` : null).filter(Boolean);
      if (pts.length > 1) {
        svgStr += `<polyline points="${pts.join(' ')}" fill="none" stroke="${col}" stroke-width="0.8" opacity="0.08"/>`;
      }
    }

    // Median path (bold white)
    const medianPts = [];
    for (let i = 0; i < nPred; i++) {
      const vals = paths.map(p => p[i]?.c).filter(fin).sort((a, b) => a - b);
      if (vals.length) {
        const med = vals[Math.floor(vals.length / 2)];
        medianPts.push(`${xP(i).toFixed(1)},${yf(med).toFixed(1)}`);
      }
    }
    if (medianPts.length > 1) {
      svgStr += `<polyline points="${medianPts.join(' ')}" fill="none" stroke="rgba(255,255,255,0.75)" stroke-width="2" stroke-linejoin="round"/>`;
    }

    // Historical candlesticks
    for (let i = 0; i < nHist; i++) {
      const b = history[i];
      if (!fin(b.o) || !fin(b.c)) continue;
      const up  = b.c >= b.o;
      const col = up ? '#3fb950' : '#f85149';
      const yHi = yf(b.h || Math.max(b.o, b.c)).toFixed(1);
      const yLo = yf(b.l || Math.min(b.o, b.c)).toFixed(1);
      const yOp = yf(Math.max(b.o, b.c)).toFixed(1);
      const yBH = Math.max(1.5, Math.abs(yf(b.o) - yf(b.c))).toFixed(1);
      svgStr += `<line x1="${xH(i).toFixed(1)}" x2="${xH(i).toFixed(1)}" y1="${yHi}" y2="${yLo}" stroke="${col}" stroke-width="0.8"/>`;
      svgStr += `<rect x="${(xH(i) - barW / 2).toFixed(1)}" width="${barW.toFixed(1)}" y="${yOp}" height="${yBH}" fill="${col}" rx="0.5"/>`;
    }

    // Last-close horizontal dashed line into forecast
    const lcY = yf(lastClose).toFixed(1);
    svgStr += `<line x1="${marginL + histW}" x2="${W - marginR}" y1="${lcY}" y2="${lcY}" stroke="#7d8590" stroke-width="0.8" stroke-dasharray="4 3" opacity="0.6"/>`;
    svgStr += `<text x="${W - marginR + 4}" y="${(parseFloat(lcY) - 3).toFixed(1)}" font-size="8" fill="#7d8590" font-family="system-ui">Last</text>`;

    // Vertical separator (NOW line)
    const sepX = (marginL + histW + sepGap / 2).toFixed(1);
    svgStr += `<line x1="${sepX}" x2="${sepX}" y1="${marginT}" y2="${marginT + chartH}" stroke="#58a6ff" stroke-width="1.2" stroke-dasharray="6 4" opacity="0.5"/>`;
    svgStr += `<text x="${sepX}" y="${(marginT - 6)}" text-anchor="middle" font-size="9" fill="#58a6ff" font-family="system-ui">NOW</text>`;

    // Date labels on x-axis
    const ax = `font-size="9" fill="#7d8590" font-family="system-ui"`;
    const histDates = [0, Math.floor(nHist / 2), nHist - 1];
    histDates.forEach(i => {
      const d = history[i]?.d;
      if (d) svgStr += `<text x="${xH(i).toFixed(1)}" y="${H - 8}" text-anchor="middle" ${ax}>${d.slice(5)}</text>`;
    });
    const predDates = [0, Math.floor(nPred / 2), nPred - 1];
    predDates.forEach(i => {
      const d = paths[0]?.[i]?.d;
      if (d) svgStr += `<text x="${xP(i).toFixed(1)}" y="${H - 8}" text-anchor="middle" ${ax}>${d.slice(5)}</text>`;
    });

    // Symbol label
    svgStr += `<text x="${marginL + histW / 2}" y="${marginT + 14}" text-anchor="middle" font-size="13" font-weight="700" fill="#e6edf3" font-family="system-ui">${sym}</text>`;
    svgStr += `<text x="${marginL + histW + sepGap + predW / 2}" y="${marginT + 14}" text-anchor="middle" font-size="10" fill="#bc8cff" font-family="system-ui">${paths.length} Kronos paths · ${nPred}d forecast</text>`;

    svgEl.innerHTML = svgStr;
    svgEl.setAttribute('aria-label', `Kronos 100-path fan chart for ${sym}`);
  }

  // ── Boot ──────────────────────────────────────────────────────────────────
  load();
})();
