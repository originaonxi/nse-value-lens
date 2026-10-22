'use strict';
/* live-cards.js — renders docs/live_cards.json (Kotak live quotes + nifty_chain maths + Kronos + Jev
 * + rule backtests) and per-stock HH/HL trade plans with Kronos agreement counts.
 * Every number comes from the JSON or the provenance-checked Kronos entry; nothing is invented.
 * Research output, not investment advice. */
(function () {
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fin = v => typeof v === 'number' && Number.isFinite(v);
  const inr = (v, d = 0) => fin(v) ? '\u20b9' + v.toLocaleString('en-IN', {maximumFractionDigits: d, minimumFractionDigits: d}) : '—';
  const num = (v, d = 2) => fin(v) ? v.toLocaleString('en-IN', {maximumFractionDigits: d}) : '—';
  const signed = v => fin(v) ? (v >= 0 ? '+' : '\u2212') + inr(Math.abs(v)) : '—';
  const KRONOS_MODEL = 'NeoQuasar/Kronos-small';
  const PLAN_SESSIONS = 10;
  const STALE_MIN = 20;

  const css = `
  .lc-wrap{display:grid;gap:12px}
  .lc-head{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:baseline;font-size:13px;color:#9aa7b8}
  .lc-head strong{color:#e6edf3}
  .lc-banner{padding:10px 12px;border-radius:8px;border:1px solid #30363d;background:#0d1117;color:#e6edf3;font-size:13.5px;line-height:1.45}
  .lc-banner.lc-warn{border-color:#9e6a03;background:#1f1a0e}
  .lc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px}
  .lc-card{border:1px solid #30363d;border-radius:10px;padding:12px 14px;background:#0d1117;color:#e6edf3;font-size:13px;line-height:1.45}
  .lc-card h3{margin:4px 0 6px;font-size:15px}
  .lc-v{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11.5px;font-weight:700;letter-spacing:.03em}
  .lc-CANDIDATE,.lc-BUY{background:#12361f;color:#3fb950}.lc-WATCH{background:#2d2a12;color:#e3b341}
  .lc-AVOID,.lc-SELL{background:#3a1515;color:#f85149}.lc-CAUTION{background:#2d2112;color:#f0883e}
  .lc-legs{width:100%;border-collapse:collapse;margin:6px 0;font-variant-numeric:tabular-nums}
  .lc-legs td{padding:3px 4px;border-bottom:1px solid #21262d}
  .lc-legs td:last-child{text-align:right}
  .lc-side-BUY{color:#3fb950;font-weight:700}.lc-side-SELL{color:#f85149;font-weight:700}
  .lc-kv{display:grid;grid-template-columns:auto 1fr;gap:2px 10px;margin:6px 0}
  .lc-kv dt{color:#9aa7b8}.lc-kv dd{margin:0;text-align:right;font-variant-numeric:tabular-nums}
  .lc-why{color:#c9d1d9;font-size:12.5px;margin:6px 0 0}
  .lc-small{color:#7d8590;font-size:11.5px;margin:6px 0 0}
  .lc-plan{border:1px solid #30363d;border-radius:8px;padding:10px 12px;margin:10px 0;background:#0d1117;color:#e6edf3;font-size:13px}
  .lc-plan .lc-act{font-size:15px;font-weight:700;margin:4px 0 8px}
  details.lc-more summary{cursor:pointer;color:#9aa7b8;font-size:13px;margin:4px 0}`;
  function injectCss() {
    if (document.getElementById('lc-css')) return;
    const s = document.createElement('style'); s.id = 'lc-css'; s.textContent = css; document.head.appendChild(s);
  }

  function ageMin(iso) { const t = Date.parse(iso); return Number.isFinite(t) ? (Date.now() - t) / 60000 : Infinity; }

  function load(source) {
    return fetch((source || '') + 'live_cards.json?t=' + Date.now(), {cache: 'no-store'})
      .then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))
      .then(d => { if (!d || !d.nifty || !Array.isArray(d.nifty.cards) || !d.stocks) throw new Error('invalid live_cards.json'); return d; });
  }

  function optionCard(c, lot) {
    const legs = c.legs.map(l => `<tr><td class="lc-side-${esc(l.side)}">${esc(l.side)}</td><td>${num(l.strike, 0)} ${esc(l.option_type)}</td><td>${esc(l.contract)}</td><td>${inr(l.live_ltp, 2)}</td></tr>`).join('');
    const k = c.kronos;
    const stopLv = c.stop?.nifty_levels || {};
    const stopNifty = [fin(stopLv.below) ? 'Nifty below ' + num(stopLv.below, 0) : '', fin(stopLv.above) ? 'Nifty above ' + num(stopLv.above, 0) : ''].filter(Boolean).join(' or ');
    const bt = c.backtest || {};
    return `<article class="lc-card" data-rule="${esc(c.rule)}">
      <span class="lc-v lc-${esc(c.verdict)}">${esc(c.verdict)}</span> <span class="lc-small">${c.firing_today ? 'rule fired today' : 'rule not fired today'}${c.jev ? ' · Jev tier ' + esc(c.jev) : ''}</span>
      <h3>${esc(c.label)}</h3>
      <table class="lc-legs">${legs}</table>
      <dl class="lc-kv">
        <dt>Net ${esc(c.net?.type)} per lot (${lot})</dt><dd>${inr(c.net?.per_lot)}</dd>
        <dt>Max profit / max loss (expiry)</dt><dd>${c.max_profit == null ? 'uncapped' : inr(c.max_profit)} / ${c.max_loss == null ? '<b style="color:#f85149">uncapped</b>' : inr(c.max_loss)}</dd>
        <dt>Breakeven (Nifty)</dt><dd>${(c.breakevens || []).map(b => num(b, 0)).join(' / ') || '—'}</dd>
        <dt>Planned exit</dt><dd>by ${esc(c.exit?.by)} (${esc(c.exit?.sessions)} sessions)</dd>
        <dt>Model P&amp;L at exit / lot</dt><dd>${signed(c.exit?.exp_pnl_per_lot)} <span class="lc-small">(worst 5% ${signed(c.exit?.worst5)})</span></dd>
        <dt>Stop</dt><dd>${esc(c.stop?.rule)}: ${signed(c.stop?.level_per_lot)}/lot${stopNifty ? ' ≈ ' + stopNifty : ''}</dd>
        <dt>Kronos agreement</dt><dd>${k ? `${k.paths_in_profit}/${k.paths} paths in profit on ${esc(k.exit_date)} · median Nifty ${num(k.median_close, 0)}` : 'unavailable'}</dd>
        <dt>Backtest</dt><dd>${esc(bt.status)}${fin(bt.trades) ? ` · ${bt.trades} trades · win ${num(bt.win_rate, 1)}% · t ${num(bt.t_stat, 2)}` : ''}</dd>
      </dl>
      <p class="lc-why">${esc(c.why)}</p>
    </article>`;
  }

  function previousBox(p) {
    if (!p || !p.available || !p.refs) return '';
    const ref = (r, lbl) => r ? `${lbl}: debit ${inr(r.debit, 2)} → now ${inr(p.spread_now, 2)} = <b>${fin(r.return_pct) ? (r.return_pct >= 0 ? '+' : '') + r.return_pct + '%' : '—'}</b> (${signed(r.pnl_per_unit * 65)}/lot of 65; max ${inr(r.max_profit_per_unit * 65)}/lot)` : '';
    return `<div class="lc-banner"><b>Your earlier card — ${esc(p.label)} (published ${esc(p.published)})</b>: <b>BUY 22600 PE / SELL 22150 PE</b>, expiry ${esc(p.expiry)}, plan exit by ${esc(p.exit_by)}.
      Live now: 22600 PE ${inr(p.ltp_now?.['22600'], 2)}, 22150 PE ${inr(p.ltp_now?.['22150'], 2)}.<br>
      ${ref(p.refs.eod_then, 'From the EOD card price')}<br>
      ${ref(p.refs.live_then, 'From the live-repriced card price')}<br>
      <span class="lc-small">Your actual fill decides your real return. One trade is one outcome, not evidence of an edge.</span></div>`;
  }

  function renderNifty(el, d) {
    injectCss();
    const n = d.nifty, cards = n.cards;
    const cand = cards.filter(c => c.verdict === 'CANDIDATE');
    const watch = cards.filter(c => c.verdict === 'WATCH');
    const avoid = cards.filter(c => c.verdict === 'AVOID');
    const age = ageMin(d.generated_at);
    const stale = age > STALE_MIN;
    const banner = cand.length
      ? `<div class="lc-banner"><b>${cand.length} candidate${cand.length > 1 ? 's' : ''}</b>: model exit P&amp;L positive, at least 6 of 10 Kronos paths in profit at exit, and backtest not negative. Size so the max loss is acceptable.</div>`
      : `<div class="lc-banner lc-warn"><b>No candidate right now.</b> No setup has positive model P&amp;L at exit, at least 6 of 10 Kronos paths in profit, and a non-negative backtest together. Staying flat is a position. WATCH cards show where the evidence disagrees.</div>`;
    el.innerHTML = `<div class="lc-wrap">
      <div class="lc-head"><span>Kotak live · <strong>${esc(d.generated_at.replace('T', ' ').slice(0, 16))} IST</strong>${stale ? ' <b style="color:#e3b341">(' + Math.round(age) + ' min old)</b>' : ''}</span>
        <span>Nifty <strong>${num(n.spot)}</strong></span><span>Live ATM IV <strong>${num(n.live_iv_pct)}%</strong> (EOD ${num(n.eod_iv_pct)}%)</span>
        <span>Expiry <strong>${esc(n.expiry)}</strong> · ${esc(n.dte)} days · lot ${esc(n.lot)}</span>
        <span>Kronos input ${esc(n.kronos_input || 'unavailable')}</span></div>
      ${banner}${previousBox(d.previous_card)}
      <div class="lc-grid">${[...cand, ...watch].map(c => optionCard(c, n.lot)).join('')}</div>
      <details class="lc-more"><summary>${avoid.length} AVOID setups (shown for transparency)</summary><div class="lc-grid">${avoid.map(c => optionCard(c, n.lot)).join('')}</div></details>
      <p class="lc-small">${esc(d.disclaimer)} Entry at the live LTP shown; real fills differ by bid/ask. Model P&amp;L uses Black-Scholes at live IV with costs removed.</p>
    </div>`;
  }

  /* Kronos agreement for a stock over the HH/HL holding window, from a provenance-checked entry. */
  function kronosAgreement(entry, row, asOf) {
    if (!entry || !row) return null;
    const prov = entry.provenance || {};
    if (prov.kind !== 'kronos-neural' || prov.model !== KRONOS_MODEL || entry.input_stale || entry.data_as_of !== asOf) return null;
    const paths = (entry.paths || []).filter(p => Array.isArray(p) && p.length >= PLAN_SESSIONS && p.every(b => fin(b.c) && b.c > 0)).map(p => p.slice(0, PLAN_SESSIONS));
    if (!paths.length || !fin(entry.last_close)) return null;
    const z = row.zones || {}, last = entry.last_close;
    const ends = paths.map(p => p[p.length - 1].c).sort((a, b) => a - b);
    const mid = (ends[(ends.length - 1) >> 1] + ends[ends.length >> 1]) / 2;
    return {
      n: paths.length, end: paths[0][paths[0].length - 1].d,
      up: ends.filter(c => c > last).length,
      trig: fin(z.breakout_above) ? paths.filter(p => p.some(b => b.c > z.breakout_above)).length : null,
      stop: fin(z.structure_exit_below) ? paths.filter(p => p.some(b => b.c < z.structure_exit_below)).length : null,
      medPct: (mid / last - 1) * 100,
    };
  }

  const ACTION = {
    BUY: 'BUY at next open — scanner entry rules met',
    WATCH: 'WAIT — buy only after a daily close above the trigger',
    CAUTION: 'DO NOT CHASE — already above the trigger',
    SELL: 'EXIT if holding — closed below the structure stop',
    AVOID: 'NO TRADE — structure does not qualify',
  };

  function stockPlanHtml(row, entry, live, scan) {
    injectCss();
    if (!row) return '';
    const z = row.zones || {};
    const lc = live?.stocks?.cards?.find(c => c.symbol === row.symbol);
    const gateOpen = scan?.market?.new_entries_allowed === true;
    const price = fin(lc?.live_ltp) ? lc.live_ltp : row.close;
    let act = ACTION[row.status] || 'NO TRADE';
    if (row.status === 'BUY' && !gateOpen) act += ' (blocked: market gate closed)';
    const k = kronosAgreement(entry, row, scan?.as_of);
    const belowStop = fin(z.structure_exit_below) && fin(price) && price < z.structure_exit_below;
    const risk = fin(z.structure_exit_below) && price > z.structure_exit_below ? (price - z.structure_exit_below) / price * 100 : null;
    const kTxt = k ? `${k.up}/${k.n} paths end above last close by ${esc(k.end)} (median ${k.medPct >= 0 ? '+' : ''}${k.medPct.toFixed(1)}%)` +
      (k.trig != null ? ` · ${k.trig}/${k.n} close above trigger` : '') + (k.stop != null ? ` · ${k.stop}/${k.n} close below stop` : '') : 'unavailable';
    return `<div class="lc-plan" id="lc-plan-${esc(row.symbol)}">
      <span class="lc-v lc-${esc(row.status)}">${esc(row.status)}</span> <span class="lc-small">HH/HL scanner ${esc(scan?.as_of || row.data_date)} · market gate ${gateOpen ? 'open' : 'closed'}</span>
      <div class="lc-act">${esc(act)}</div>
      <dl class="lc-kv">
        <dt>Price</dt><dd>${fin(lc?.live_ltp) ? inr(lc.live_ltp, 2) + ' live (Kotak)' : inr(row.close, 2) + ' EOD close'}</dd>
        <dt>Trigger (daily close above)</dt><dd>${fin(z.breakout_above) ? inr(z.breakout_above, 2) : '—'}</dd>
        <dt>Stop (daily close below)</dt><dd>${fin(z.structure_exit_below) ? inr(z.structure_exit_below, 2) : '—'}${belowStop ? ' <b style="color:#f85149">· price below stop now</b>' : ''}</dd>
        <dt>Risk from price to stop</dt><dd>${fin(risk) ? risk.toFixed(1) + '%' : '—'}</dd>
        <dt>Overextended above</dt><dd>${fin(z.extended_above) ? inr(z.extended_above, 2) + ' (warning, not a price target)' : '—'}</dd>
        <dt>Kronos agreement (${PLAN_SESSIONS} sessions)</dt><dd>${kTxt}</dd>
      </dl>
      <p class="lc-why">${esc(row.reason || '')}</p>
      <p class="lc-small">Levels are the scanner's confirmed swing high/low. Kronos counts are ${k ? k.n : 'model'} sampled paths, not a calibrated likelihood. Not investment advice.</p>
    </div>`;
  }

  window.LiveCards = {load, renderNifty, stockPlanHtml, kronosAgreement};

  function boot() {
    const el = document.getElementById('live-cards');
    if (!el) return;
    const source = document.body.dataset.liveSource || '';
    const tick = () => load(source).then(d => renderNifty(el, d)).catch(e => {
      if (!el.querySelector('.lc-wrap')) el.innerHTML = '<p class="lc-small">Live cards unavailable (' + esc(e.message) + '). No live prices are being shown.</p>';
    });
    tick();
    setInterval(() => { if (document.visibilityState === 'visible') tick(); }, 60000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
