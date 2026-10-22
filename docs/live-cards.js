'use strict';
/* live-cards.js — renders docs/live_cards.json (Kotak live quotes + nifty_chain maths + Kronos + Jev
 * + rule backtests) and per-stock HH/HL trade plans with Kronos agreement counts.
 * Every number comes from the JSON or the provenance-checked Kronos entry; nothing is invented.
 * Research output, not investment advice. */
(function () {
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fin = v => typeof v === 'number' && Number.isFinite(v);
  const inr = (v, d = 0) => fin(v) ? (v < 0 ? '\u2212' : '') + '\u20b9' + Math.abs(v).toLocaleString('en-IN', {maximumFractionDigits: d, minimumFractionDigits: d}) : '—';
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
  details.lc-more summary{cursor:pointer;color:#9aa7b8;font-size:13px;margin:4px 0}
  .sc-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px}
  .sc-card{border:2px solid #30363d;border-radius:12px;padding:12px 14px;background:#0d1117;color:#e6edf3;font-size:13px;line-height:1.45}
  .sc-bull{border-color:#238636}.sc-bear{border-color:#da3633}.sc-side{border-color:#9e6a03}
  .sc-top{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
  .sc-rank{font-size:22px;font-weight:800}.sc-prob{font-size:20px;font-weight:800}
  .sc-moves{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:12px;margin:6px 0}
  .sc-moves td,.sc-moves th{padding:2px 4px;border-bottom:1px solid #21262d;text-align:right}
  .sc-moves th{color:#9aa7b8;font-weight:600}
  .sc-pos{color:#3fb950}.sc-neg{color:#f85149}
  .sc-bar{display:flex;height:22px;border-radius:6px;overflow:hidden;font-size:11.5px;font-weight:700;margin:6px 0}
  .sc-bar span{display:flex;align-items:center;justify-content:center;color:#0d1117}
  .sc-trend{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}`;
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
    const dir = /bear/.test(c.view || '') ? 'bear' : /bull/.test(c.view || '') ? 'bull' : 'neutral';
    const dirTag = dir === 'bear' ? '<span class="lc-v lc-SELL">▼ BEARISH</span>' : dir === 'bull' ? '<span class="lc-v lc-BUY">▲ BULLISH</span>' : `<span class="lc-v lc-WATCH">◆ ${esc((c.view || 'neutral').toUpperCase())}</span>`;
    return `<article class="lc-card" data-rule="${esc(c.rule)}" data-dir="${dir}">
      <span class="lc-v lc-${esc(c.verdict)}">${esc(c.verdict)}</span> ${dirTag} <span class="lc-small">${c.firing_today ? 'rule fired today' : 'rule not fired today'}${c.jev ? ' · Jev tier ' + esc(c.jev) : ''}</span>
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

  function directionPanel(n) {
    const d = n.direction;
    if (!d || !Array.isArray(d.votes)) return '';
    const col = s => s === 'bear' ? '#f85149' : s === 'bull' ? '#3fb950' : '#9aa7b8';
    const rows = d.votes.map(v => `<tr><td>${esc(v.name)}</td><td style="color:${col(v.side)};font-weight:700">${v.side === 'bear' ? '▼' : v.side === 'bull' ? '▲' : '◆'} ${esc(v.value)}</td><td class="lc-small">${esc(v.detail)}</td></tr>`).join('');
    const leanCol = d.lean === 'BEARISH' ? '#f85149' : d.lean === 'BULLISH' ? '#3fb950' : '#e3b341';
    return `<div class="lc-banner"><b>Direction right now: <span style="color:${leanCol}">${esc(d.lean)}</span></b> — ${d.bear} bearish · ${d.bull} bullish · ${d.neutral} neutral inputs.
      <table class="lc-legs" style="margin-top:6px">${rows}</table>
      <span class="lc-small">Kronos ${n.kronos_source === 'live' ? 'includes today\'s live Kotak bar (run ' + esc((n.kronos_generated_at || '').slice(11, 16)) + ' IST)' : 'uses the last completed EOD candle ' + esc(n.kronos_input || '')}. No single input is a forecast; this is the evidence each card is judged against.</span></div>`;
  }

  function renderNifty(el, d) {
    injectCss();
    const n = d.nifty, cards = n.cards;
    const lean = n.direction?.lean;
    const fits = c => lean === 'BEARISH' ? /bear/.test(c.view || '') : lean === 'BULLISH' ? /bull/.test(c.view || '') : true;
    const order = {CANDIDATE: 0, WATCH: 1, AVOID: 2};
    // Cards that match today's live lean come first inside each verdict group.
    const sorted = [...cards].sort((a, b) => order[a.verdict] - order[b.verdict] || (fits(b) - fits(a)) || ((b.exit?.exp_pnl_per_lot ?? -1e12) - (a.exit?.exp_pnl_per_lot ?? -1e12)));
    const cand = sorted.filter(c => c.verdict === 'CANDIDATE');
    const watch = sorted.filter(c => c.verdict === 'WATCH');
    const bears = sorted.filter(c => c.verdict === 'AVOID' && /bear/.test(c.view || ''));
    const avoid = sorted.filter(c => c.verdict === 'AVOID' && !/bear/.test(c.view || ''));
    const age = ageMin(d.generated_at);
    const stale = age > STALE_MIN;
    const banner = cand.length
      ? `<div class="lc-banner"><b>${cand.length} candidate${cand.length > 1 ? 's' : ''}</b>: model exit P&amp;L positive, at least 60% of Kronos paths in profit at exit, and backtest not negative. Size so the max loss is acceptable.</div>`
      : `<div class="lc-banner lc-warn"><b>No candidate right now.</b> No setup has positive model P&amp;L at exit, at least 60% of Kronos paths in profit, and a non-negative backtest together. Staying flat is a position. WATCH cards show where the evidence disagrees.</div>`;
    el.innerHTML = `<div class="lc-wrap">
      <div class="lc-head"><span>Kotak live · <strong>${esc(d.generated_at.replace('T', ' ').slice(0, 16))} IST</strong>${stale ? ' <b style="color:#e3b341">(' + Math.round(age) + ' min old)</b>' : ''}</span>
        <span>Nifty <strong>${num(n.spot)}</strong></span><span>Live ATM IV <strong>${num(n.live_iv_pct)}%</strong> (EOD ${num(n.eod_iv_pct)}%)</span>
        <span>Expiry <strong>${esc(n.expiry)}</strong> · ${esc(n.dte)} days · lot ${esc(n.lot)}</span></div>
      ${directionPanel(n)}${banner}${previousBox(d.previous_card)}
      <div class="lc-grid">${[...cand, ...watch].map(c => optionCard(c, n.lot)).join('')}</div>
      ${bears.length ? `<h3 style="margin:6px 0 0;color:#f85149;font-size:14px">▼ Bearish setups (${bears.length}) — priced live, marked AVOID for the reason on each card</h3><div class="lc-grid">${bears.map(c => optionCard(c, n.lot)).join('')}</div>` : ''}
      <details class="lc-more"><summary>${avoid.length} other AVOID setups (shown for transparency)</summary><div class="lc-grid">${avoid.map(c => optionCard(c, n.lot)).join('')}</div></details>
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

  const SC_NAME = {bull: '▲ BULLISH', bear: '▼ BEARISH', side: '◆ SIDEWAYS'};
  const SC_COL = {bull: '#3fb950', bear: '#f85149', side: '#e3b341'};
  const pct = v => fin(v) ? (v * 100).toFixed(0) + '%' : '—';
  const pnlCell = v => `<td class="${v > 0 ? 'sc-pos' : v < 0 ? 'sc-neg' : ''}">${signed(v)}</td>`;

  function scenarioCard(c, s) {
    const legs = c.legs.map(l => `<tr><td class="lc-side-${esc(l.side)}">${esc(l.side)}</td><td>${num(l.strike, 0)} ${esc(l.type)}</td>
      <td class="lc-small">bid ${inr(l.bid, 2)} / ask ${inr(l.ask, 2)}</td><td>${inr(l.fill, 2)} <span class="lc-small">${esc(l.fill_basis)}</span></td></tr>`).join('');
    const mv = c.pnl_moves || [];
    const moves = `<table class="sc-moves"><tr><th>Nifty move by ${esc(c.exit_by)}</th>${mv.map(m => `<th>${m.move_pct > 0 ? '+' : ''}${m.move_pct}%</th>`).join('')}</tr>
      <tr><th>Nifty</th>${mv.map(m => `<td>${num(m.nifty, 0)}</td>`).join('')}</tr>
      <tr><th>P&amp;L / lot</th>${mv.map(m => pnlCell(m.pnl)).join('')}</tr></table>`;
    const ex = c.exits || {}, t = c.trigger || {};
    const stopN = [fin(ex.stop_nifty_below) ? 'Nifty below ' + num(ex.stop_nifty_below, 0) : '', fin(ex.stop_nifty_above) ? 'Nifty above ' + num(ex.stop_nifty_above, 0) : ''].filter(Boolean).join(' or ');
    const ifs = c.if_scenario || {};
    const alts = (c.alternatives || []).map(a => `<li>${esc(a.name)} · ${esc(a.net?.type)} ${inr(a.net?.per_lot)} · max loss ${inr(a.max_loss)} · if ${SC_NAME[c.scenario].slice(2).toLowerCase()} ${signed(a.if_scenario)} (${num(a.scenario_return_on_risk, 0)}% of risk)</li>`).join('');
    return `<article class="sc-card sc-${esc(c.scenario)}" data-scenario="${esc(c.scenario)}">
      <div class="sc-top"><span class="sc-rank">#${esc(c.rank)}</span><span style="color:${SC_COL[c.scenario]};font-weight:800;font-size:16px">${SC_NAME[c.scenario]}</span>
        <span class="sc-prob" style="color:${SC_COL[c.scenario]}">${pct(c.probability)}</span></div>
      <p class="lc-small" style="margin:0">Blended probability that Nifty is ${c.scenario === 'bull' ? 'more than ' + s.band_pct + '% above' : c.scenario === 'bear' ? 'more than ' + s.band_pct + '% below' : 'within ±' + s.band_pct + '% of'} ${num(s.spot)} on ${esc(c.exit_by)}</p>
      <h3 style="margin:8px 0 4px">${esc(c.name)}</h3>
      <table class="lc-legs">${legs}</table>
      <dl class="lc-kv">
        <dt>Net ${esc(c.net?.type)} per lot (${s.lot})</dt><dd><b>${inr(c.net?.per_lot)}</b></dd>
        <dt>Max profit / max loss (expiry ${esc(s.expiry)})</dt><dd><b class="sc-pos">${c.max_profit == null ? 'uncapped' : inr(c.max_profit)}</b> / <b class="sc-neg">${signed(c.max_loss)}</b></dd>
        <dt>Breakeven at expiry</dt><dd>${(c.breakevens || []).map(b => num(b, 0)).join(' / ') || '—'}</dd>
        <dt>If ${SC_NAME[c.scenario].slice(2).toLowerCase()} (${c.scenario === 'side' ? 'Nifty within ±' + s.band_pct + '%' : s.band_pct + '–' + s.band_max_pct + '% ' + (c.scenario === 'bull' ? 'up' : 'down')})</dt><dd class="sc-pos"><b>${signed(ifs[c.scenario])}</b> · ${num(c.scenario_return_on_risk, 0)}% of max loss</dd>
        <dt>If wrong</dt><dd>${['bull', 'side', 'bear'].filter(k => k !== c.scenario).map(k => SC_NAME[k].slice(2).toLowerCase() + ' ' + signed(ifs[k])).join(' · ')}</dd>
        <dt>Probability-weighted P&amp;L</dt><dd><b class="${c.regime_ev > 0 ? 'sc-pos' : 'sc-neg'}">${signed(c.regime_ev)}</b> (${num(c.regime_ev_per_risk, 1)}% of risk)</dd>
      </dl>
      ${moves}
      <dl class="lc-kv">
        <dt>Trigger</dt><dd style="text-align:left">${t.active ? '<b class="sc-pos">ACTIVE NOW</b> · ' : '<b style="color:#e3b341">WAIT</b> · '}${esc(t.text)}</dd>
        <dt>Structure exit</dt><dd style="text-align:left">${esc(c.structure_exit)}</dd>
        <dt>Stop</dt><dd style="text-align:left">${esc(ex.stop_rule)}: ${signed(ex.stop_rupees)}/lot${stopN ? ' ≈ ' + stopN + ' (next day)' : ''}</dd>
        <dt>Target</dt><dd style="text-align:left">${esc(ex.target_rule)}: ${signed(ex.target_rupees)}/lot · ${esc(ex.target_text)}</dd>
        <dt>Time exit</dt><dd style="text-align:left">by ${esc(c.exit_by)} (${esc(s.sessions)} sessions), before expiry ${esc(s.expiry)}</dd>
      </dl>
      ${alts ? `<details class="lc-more"><summary>Next best ${esc(SC_NAME[c.scenario].slice(2).toLowerCase())} structures</summary><ul class="lc-small">${alts}</ul></details>` : ''}
    </article>`;
  }

  function renderScenarios(el, d) {
    injectCss();
    const s = d.scenarios;
    if (!s || s.error || !Array.isArray(s.cards)) {
      el.innerHTML = `<p class="lc-small">Scenario cards unavailable${s && s.error ? ' (' + esc(s.error) + ')' : ''}. No numbers are being invented.</p>`;
      return;
    }
    const a = s.trend, p = s.probabilities, b = p.blended;
    const age = ageMin(s.generated_at);
    const src = Object.entries(p.sources).map(([k, v]) => v ? `<tr><td>${esc({implied: 'Options market (live IV)', kronos: 'Kronos', history: 'Historical analogs', jev: 'Jev'}[k] || k)}</td>
      <td class="sc-pos">${pct(v.bull)}</td><td style="color:#e3b341">${pct(v.side)}</td><td class="sc-neg">${pct(v.bear)}</td><td class="lc-small">${esc(v.note)}</td></tr>` : `<tr><td>${esc(k)}</td><td colspan="4" class="lc-small">unavailable</td></tr>`).join('');
    const bar = ['bear', 'side', 'bull'].map(k => `<span style="width:${(b[k] * 100).toFixed(1)}%;background:${SC_COL[k]}">${SC_NAME[k].slice(2)} ${pct(b[k])}</span>`).join('');
    const votes = a.votes.map(v => `<tr><td>${esc(v.name)}</td><td style="color:${v.side === 'bear' ? '#f85149' : v.side === 'bull' ? '#3fb950' : '#9aa7b8'};font-weight:700">${v.side === 'bear' ? '▼' : v.side === 'bull' ? '▲' : '◆'} ${esc(v.value)}</td><td class="lc-small">${esc(v.detail)}</td></tr>`).join('');
    const levels = [...a.levels].sort((x, y) => y.value - x.value).map(l => `<tr${l.kind === 'live' ? ' style="background:#1f2937;font-weight:700"' : ''}><td>${esc(l.name)}</td><td>${num(l.value, 0)}</td><td class="${l.dist_pct > 0 ? 'sc-pos' : l.dist_pct < 0 ? 'sc-neg' : ''}">${l.dist_pct > 0 ? '+' : ''}${num(l.dist_pct, 2)}%</td></tr>`).join('');
    const st = a.stats;
    el.innerHTML = `<div class="lc-wrap">
      <div class="lc-head"><span>Kotak live · <strong>${esc(s.generated_at.replace('T', ' ').slice(0, 16))} IST</strong>${age > STALE_MIN ? ' <b style="color:#e3b341">(' + Math.round(age) + ' min old)</b>' : ''}</span>
        <span>Nifty <strong>${num(s.spot)}</strong> (${s.change_pct > 0 ? '+' : ''}${num(s.change_pct)}%)</span>
        <span>Today O ${num(s.today?.open, 0)} · H ${num(s.today?.high, 0)} · L ${num(s.today?.low, 0)}</span>
        <span>Expiry <strong>${esc(s.expiry)}</strong> · ${esc(s.dte)} days · lot ${esc(s.lot)} · exit by <strong>${esc(s.exit_by)}</strong></span></div>
      <div class="lc-banner"><b>Trend now: <span style="color:${a.label === 'BEARISH' ? '#f85149' : a.label === 'BULLISH' ? '#3fb950' : '#e3b341'}">${esc(a.label)}</span></b>
        — ${a.bear} bearish · ${a.bull} bullish · ${a.neutral} neutral checks.
        RSI ${num(st.rsi14, 1)} · ATR ${num(st.atr14, 0)} pts (${num(st.atr_pct, 2)}%) · live ATM IV ${num(st.live_atm_iv)}% (IV percentile ${num(st.iv_percentile, 0)}) ·
        live PCR ${num(st.pcr_live, 2)} · 1σ move by exit ±${num(st.move_1sigma_exit_pts, 0)} pts (±${num(st.move_1sigma_exit_pct)}%).
        <div class="sc-bar">${bar}</div>
        <span class="lc-small">Scenario odds for ${esc(s.exit_by)} (${esc(s.sessions)} sessions): bull = Nifty above ${num(s.spot * (1 + s.band_pct / 100), 0)}, bear = below ${num(s.spot * (1 - s.band_pct / 100), 0)}, sideways = between.</span></div>
      <div class="sc-grid">${s.cards.map(c => scenarioCard(c, s)).join('')}</div>
      <div class="sc-trend">
        <details class="lc-more" open><summary>Trend checks (HH/HL style)</summary><table class="lc-legs">${votes}</table></details>
        <details class="lc-more" open><summary>Key levels from live price</summary><table class="lc-legs">${levels}</table></details>
      </div>
      <details class="lc-more"><summary>How the scenario odds are calculated</summary>
        <table class="lc-legs"><tr><td></td><td class="sc-pos">Bull</td><td style="color:#e3b341">Side</td><td class="sc-neg">Bear</td><td></td></tr>${src}
        <tr><td><b>Blended (equal weight)</b></td><td class="sc-pos"><b>${pct(b.bull)}</b></td><td style="color:#e3b341"><b>${pct(b.side)}</b></td><td class="sc-neg"><b>${pct(b.bear)}</b></td><td></td></tr></table>
        <p class="lc-small">${esc(s.method)} ${esc(s.candidates)} live structures valued from ${esc(s.chain_quotes)} option quotes.</p></details>
      <p class="lc-small">${esc(d.disclaimer)}</p>
    </div>`;
  }

  /* Live replacement for the EOD EV screen: all live structures ranked by probability-weighted P&L per rupee of risk. */
  function renderLiveEV(host, d) {
    const s = d.scenarios;
    if (!host || !s || s.error || !Array.isArray(s.ranked_all) || !s.ranked_all.length) return false;
    injectCss();
    host.dataset.live = '1';
    const h = document.getElementById('mathplay-title');
    if (h) h.textContent = 'Live EV ranking — all structures, probability-weighted (research only)';
    const b = s.probabilities.blended;
    const rows = s.ranked_all.map((e, i) => `<tr data-dir="${esc(e.scenario)}">
      <td>#${i + 1}</td><td style="color:${SC_COL[e.scenario]};font-weight:700">${SC_NAME[e.scenario]}</td>
      <td>${esc(e.name)}<br><span class="lc-small">${e.legs.map(l => `${l.side} ${num(l.strike, 0)} ${l.type} @ ${inr(l.fill, 2)}`).join(' · ')}</span></td>
      <td>${esc(e.net.type)} ${inr(e.net.per_lot)}</td><td class="sc-pos">${e.max_profit == null ? 'uncapped' : inr(e.max_profit)}</td><td class="sc-neg">${signed(e.max_loss)}</td>
      <td>${(e.breakevens || []).map(x => num(x, 0)).join(' / ')}</td>
      ${['bull', 'side', 'bear'].map(k => pnlCell(e.cond[k])).join('')}
      <td><b class="${e.regime_ev > 0 ? 'sc-pos' : 'sc-neg'}">${signed(e.regime_ev)}</b><br><span class="lc-small">${num(e.regime_ev_per_risk, 1)}% of risk</span></td></tr>`).join('');
    host.innerHTML = `<div class="lc-wrap">
      <p class="lc-small" style="margin:0">LIVE PAYOFF SCREEN — RESEARCH ONLY · Kotak bid/ask ${esc(s.generated_at.slice(11, 16))} IST · Nifty ${num(s.spot)} · expiry ${esc(s.expiry)} · exit ${esc(s.exit_by)} · lot ${esc(s.lot)}.
        Odds used: bull ${pct(b.bull)} · sideways ${pct(b.side)} · bear ${pct(b.bear)} (from the scenario section above).</p>
      <div class="nc-table-scroll"><table class="lc-legs sc-moves"><tr><th>Rank</th><th>View</th><th>Structure</th><th>Net / lot</th><th>Max profit</th><th>Max loss</th><th>Breakeven</th>
        <th>If bull</th><th>If sideways</th><th>If bear</th><th>Weighted P&amp;L</th></tr>${rows}</table></div>
      <p class="lc-small">"If bull/sideways/bear" = average P&amp;L at the exit date across that whole scenario (tails included) at each leg's live implied vol, costs removed.
        Ranked by weighted P&amp;L per rupee of max loss across ${esc(s.candidates)} live structures. Weighted P&amp;L near zero is normal for fairly priced options. Not investment advice.</p>
    </div>`;
    return true;
  }

  window.LiveCards = {load, renderNifty, renderScenarios, renderLiveEV, stockPlanHtml, kronosAgreement};

  function boot() {
    const el = document.getElementById('live-cards');
    const sc = document.getElementById('scenario-cards');
    const ev = document.getElementById('mathplay-card');
    if (!el && !sc) return;
    const source = document.body.dataset.liveSource || '';
    const tick = () => load(source).then(d => {
      if (sc) renderScenarios(sc, d);
      if (ev) renderLiveEV(ev, d);
      if (el) renderNifty(el, d);
    }).catch(e => {
      for (const x of [sc, el]) if (x && !x.querySelector('.lc-wrap')) x.innerHTML = '<p class="lc-small">Live cards unavailable (' + esc(e.message) + '). No live prices are being shown.</p>';
    });
    tick();
    setInterval(() => { if (document.visibilityState === 'visible') tick(); }, 60000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
