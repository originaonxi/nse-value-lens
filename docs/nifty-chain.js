'use strict';
/* nifty-chain.js — trader-2 — requires nifty-math.js loaded first (defer order) */
(() => {

  /* ── Helpers ── */
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fin = v => typeof v === 'number' && Number.isFinite(v);
  const fmt  = (v, d=2) => fin(v) ? v.toLocaleString('en-IN',{minimumFractionDigits:d,maximumFractionDigits:d}) : '\u2014';
  const iInt = v => fin(v) ? Math.round(v).toLocaleString('en-IN') : '\u2014';
  const money = v => fin(v) ? '\u20b9'+fmt(v) : '\u2014';
  const pct  = (v,d=1) => fin(v) ? (v>0?'+':'')+fmt(v,d)+'%' : '\u2014';
  const pctP = (v,d=1) => fin(v) ? fmt(v,d)+'%' : '\u2014';
  const cls  = v => fin(v) ? (v>0?'pos':v<0?'neg':'') : '';
  const isoD = v => /^\d{4}-\d{2}-\d{2}$/.test(v||'') ?
    new Date(v+'T00:00:00Z').toLocaleDateString('en-IN',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}) : '\u2014';
  const sideTag = s => '<span class="nc-side-'+(s==='SELL'?'sell':'buy')+'">'+esc(s||'\u2014')+'</span>';

  let dataset=null, ranked=[], activeFilter='all', searchQ='';
  const byRule=new Map();

  /* ── Validate snapshot ── */
  function validate(d) {
    if (!d || d.symbol !== 'NIFTY') throw new Error('Not a Nifty chain snapshot.');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(d.as_of||'')) throw new Error('Missing or invalid session date.');
    if (!d.index || !fin(d.index.close)) throw new Error('Missing index close price.');
    if (!Array.isArray(d.expiries) || !d.expiries.length) throw new Error('No expiries in snapshot.');
    if (!Array.isArray(d.rules)) throw new Error('No rules array.');
    if (!Array.isArray(d.constituents) || d.constituents_count !== d.constituents.length)
      throw new Error('constituents_count mismatch \u2014 snapshot may be corrupt.');
  }

  /* ── Payoff SVG from risk.curve (expiryRisk exact extrema) ── */
  function payoffSvg(curve) {
    if (!curve||!Array.isArray(curve.price)||!curve.price.length||
        !Array.isArray(curve.pnl)||curve.pnl.length!==curve.price.length) return '';
    const pr=curve.price, pn=curve.pnl;
    const W=560,H=140,L=60,R=12,T=12,B=28;
    const loV=Math.min(...pn), hiV=Math.max(...pn);
    const klo=pr[0], khi=pr[pr.length-1];
    const xf=k=>L+(W-L-R)*(k-klo)/(khi-klo||1);
    const yf=v=>T+(H-T-B)*(1-(v-loV)/(hiV-loV||1));
    const z=yf(0);
    const pts=pr.map((k,i)=>xf(k).toFixed(1)+','+yf(pn[i]).toFixed(1)).join(' ');
    const ax='font-size="9" fill="#6b7a91" font-family="system-ui,sans-serif"';
    let s='<svg viewBox="0 0 '+W+' '+H+'" class="nc-payoff-svg" role="img" aria-label="Gross payoff at expiry per lot">';
    s+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+z.toFixed(1)+'" y2="'+z.toFixed(1)+'" stroke="#dde3ec" stroke-width="1"/>';
    s+='<polyline points="'+pts+'" fill="none" stroke="#0d8a7a" stroke-width="2" stroke-linejoin="round"/>';
    [0,Math.floor(pr.length/2),pr.length-1].forEach(i=>
      s+='<text x="'+xf(pr[i]).toFixed(1)+'" y="'+(H-6)+'" text-anchor="middle" '+ax+'>'+Math.round(pr[i]).toLocaleString('en-IN')+'</text>');
    s+='<text x="'+(L-4)+'" y="'+(T+8)+'" text-anchor="end" '+ax+'>'+Math.round(hiV).toLocaleString('en-IN')+'</text>';
    s+='<text x="'+(L-4)+'" y="'+(z+4).toFixed(1)+'" text-anchor="end" '+ax+'>0</text>';
    if (Math.abs(loV-hiV)>1) s+='<text x="'+(L-4)+'" y="'+(H-B+2)+'" text-anchor="end" '+ax+'>'+Math.round(loV).toLocaleString('en-IN')+'</text>';
    s+='</svg>';
    return '<div class="nc-payoff-wrap">'+s+'</div>';
  }

  /* ── Build one setup card HTML ── */
  function buildCard(r, expanded) {
    const s=r.setup, rObj=r.rule||{}, legs=s.legs||{}, ex=s.exit||{}, plan=s.plan||{}, rsk=r.risk, mc=r.mathComponents||{};
    const legsArr=Array.isArray(legs)?legs:[];
    const horizonWarn=r.warnings.some(w=>w.includes('calendar-time'));
    const bLabels={consider:'Consider',watch:'Watch',inactive:'Inactive',avoid:'Avoid'};
    const bCls='nc-bucket-'+(r.bucket||'inactive');
    const statusLower=(s.status||'').toLowerCase().replace(/[^a-z0-9]/g,'_');

    /* legs table */
    const legsHtml=legsArr.length
      ?'<div class="nc-table-scroll"><table class="nc-legs-table">'
        +'<thead><tr><th>Side</th><th>Contract</th><th>Expiry</th><th>Strike</th><th>Ref close</th><th>Lot</th><th>Qty</th>'
        +'<th title="Position delta per lot">\u0394 delta</th><th title="Position gamma per lot">\u0393 gamma</th>'
        +'<th title="Daily decay per lot">\u0398/day</th><th title="Vega per lot">V vega</th></tr></thead>'
        +'<tbody>'+legsArr.map(l=>'<tr>'
          +'<td>'+sideTag(l.side)+'</td>'
          +'<td>'+esc(l.name||l.option_type+' '+l.strike)+'</td>'
          +'<td>'+esc(l.expiry||'\u2014')+'</td>'
          +'<td class="nc-num">'+iInt(l.strike)+'</td>'
          +'<td class="nc-num">'+money(l.ref_close)+'</td>'
          +'<td class="nc-num">'+esc(String(l.lot||'\u2014'))+'</td>'
          +'<td class="nc-num">'+esc(String(l.quantity??1))+'</td>'
          +'<td class="nc-num '+cls(l.delta)+'">'+fmt(l.delta,3)+'</td>'
          +'<td class="nc-num">'+fmt(l.gamma,5)+'</td>'
          +'<td class="nc-num '+cls(l.theta)+'">'+fmt(l.theta,1)+'</td>'
          +'<td class="nc-num '+cls(l.vega)+'">'+fmt(l.vega,1)+'</td>'
          +'</tr>').join('')
        +'</tbody></table></div>'
        +'<p class="nc-caveat">Entry proxy: next-session official open. Ref close = today\'s EOD \u2014 actual fills will differ. Lot: '
        +esc(String(legsArr[0]?.lot||'\u2014'))+'. Values per lot \xd7 quantity, gross before fees.</p>'
      :'<p class="nc-muted">No legs available.</p>';

    /* greeks grid */
    const g=r.greeks||{};
    const gCells=[
      ['\u0394 delta/lot',  fmt(g.delta,2),  cls(g.delta),  'Position delta per lot \u2014 direction sensitivity, not a profit signal.'],
      ['\u0393 gamma/lot',  fmt(g.gamma,4),  cls(g.gamma),  'Delta rate of change. High near ATM and near expiry.'],
      ['\u0398 theta \u20b9/d', money(g.theta), cls(g.theta), 'Daily premium decay per lot. Negative = buyer pays; positive = seller collects.'],
      ['V vega \u20b9/pt',  money(g.vega),   cls(g.vega),   '\u20b9 change per 1-pt implied vol move per lot.'],
      ['ATM IV',            pctP(r.iv),        '',            'Expiry-specific ATM implied vol (annualised). Null when expiry data unavailable.'],
      ['1\u03c3 to exp.',   fin(r.sigmaMove)?'\xb1'+iInt(r.sigmaMove):'\u2014', '', 'spot \xd7 IV% \xd7 \u221a(DTE/365). Expected \xb1 range to expiry.'],
    ];
    const greeksHtml='<div class="nc-greeks-grid">'+gCells.map(([nm,val,vc,tip])=>
      '<div class="nc-greek-cell"><dl><dt title="'+esc(tip)+'">'+esc(nm)+'</dt><dd class="'+esc(vc)+'">'+val+'</dd></dl></div>'
    ).join('')+'</div>';

    /* exit EV (primary) */
    const holdDesc=fin(ex.hold_sessions)?ex.hold_sessions+' sessions':'5 sessions';
    const calNote=fin(ex.horizon_calendar_days)?' ('+ex.horizon_calendar_days+' calendar days)'
                 :horizonWarn?' (legacy approximation \u2014 backend fix in progress)':'';
    const evCls=cls(ex.exp_pnl_per_lot);
    const evPosCls=fin(ex.exp_pnl_per_lot)&&ex.exp_pnl_per_lot>0?' nc-ev-pos':fin(ex.exp_pnl_per_lot)&&ex.exp_pnl_per_lot<0?' nc-ev-neg':'';
    const exitHtml=
      '<div class="nc-ev-grid">'
      +'<div class="nc-ev-cell'+evPosCls+'"><dl><dt>Model exit EV / lot</dt><dd class="'+evCls+'">'+money(ex.exp_pnl_per_lot)+'</dd></dl></div>'
      +'<div class="nc-ev-cell"><dl><dt>P(profit) at exit</dt><dd>'+pctP(ex.p_profit,0)+'</dd></dl></div>'
      +'<div class="nc-ev-cell"><dl><dt>Hold horizon</dt><dd>'+esc(holdDesc+calNote)+'</dd></dl></div>'
      +'<div class="nc-ev-cell"><dl><dt>Exit by</dt><dd>'+isoD(plan.exit_by)+'</dd></dl></div>'
      +'<div class="nc-ev-cell"><dl><dt>Round-trip costs</dt><dd>'+money(ex.round_trip_costs)+'</dd></dl></div>'
      +'<div class="nc-ev-cell"><dl><dt>EV / max-risk</dt><dd class="'+cls(r.evOnRisk)+'">'+(fin(r.evOnRisk)?fmt(r.evOnRisk,1)+'%':'\u2014')+'</dd></dl></div>'
      +'</div>'
      +(horizonWarn?'<p class="nc-caveat nc-caveat-warn">\u26a0 Exit model calendar-time metadata is inconsistent or missing (backend correction in progress). Values shown are legacy approximations; do not use EV for position sizing.</p>':'')
      +'<p class="nc-caveat">Exit EV and P(profit) use a constant-volatility lognormal model at the planned exit date, not a backtested win rate. Jev confidence \u2260 profit probability. Expiry payoff is in the risk section below.</p>';

    /* risk at expiry (secondary) */
    const mpStr=rsk.unlimitedProfit?'Unlimited \u2191':money(rsk.maxProfit);
    const mlStr=rsk.unlimitedLoss  ?'\u26a0 Unlimited \u2193':money(rsk.maxLoss);
    const mlCls=rsk.unlimitedLoss  ?'nc-warn':'neg';
    const riskHtml=
      '<div class="nc-risk-grid">'
      +'<div class="nc-risk-cell nc-risk-gain"><dl><dt>Max profit (expiry)</dt><dd>'+mpStr+'</dd></dl></div>'
      +'<div class="nc-risk-cell nc-risk-loss"><dl><dt>Max loss (expiry)</dt><dd class="'+mlCls+'">'+mlStr+'</dd></dl></div>'
      +'<div class="nc-risk-cell"><dl><dt>Breakeven(s)</dt><dd>'+(rsk.breakevens.map(b=>iInt(b)).join(' / ')||'\u2014')+'</dd></dl></div>'
      +'<div class="nc-risk-cell"><dl><dt>Risk / reward</dt><dd>'+(fin(rsk.riskReward)?rsk.riskReward.toFixed(2)+'\xd7':'\u2014')+'</dd></dl></div>'
      +'<div class="nc-risk-cell"><dl><dt>Net debit(+)/credit(\u2212)</dt><dd>'+money(rsk.netDebit)+'</dd></dl></div>'
      +'<div class="nc-risk-cell"><dl><dt>P(profit at expiry)</dt><dd>'+pctP((s.payoff||{}).prob_profit_model,0)+'</dd></dl></div>'
      +'</div>'
      +'<p class="nc-caveat">Expiry values computed from today\'s EOD leg prices \u2014 gross per lot, before fees and slippage. Assumes holding to contract expiry; the exit EV section above is what the plan actually targets. Max profit/loss use exact payoff extrema, not a sampled grid.</p>';

    /* payoff SVG */
    const svgHtml=payoffSvg(rsk.curve);

    /* plan */
    const planHtml=
      '<div class="nc-plan-row">'
      +'<div><dl><dt>Entry</dt><dd>'+esc(plan.entry||'Next-session official open')+'</dd></dl></div>'
      +'<div><dl><dt>Hold</dt><dd>'+esc(holdDesc+calNote)+'</dd></dl></div>'
      +'<div><dl><dt>Exit by</dt><dd>'+isoD(plan.exit_by)+'</dd></dl></div>'
      +'<div><dl><dt>DTE to expiry</dt><dd>'+(fin(r.daysToExpiry)?r.daysToExpiry+' days':'\u2014')+'</dd></dl></div>'
      +'</div>'
      +(plan.payoff_note?'<p class="nc-caveat">'+esc(plan.payoff_note)+'</p>':'');

    /* reasons + warnings (all from module — no invented text) */
    const rwHtml=
      '<div class="nc-reasons-list">'
      +r.warnings.map(t=>'<div class="nc-reason nc-reason-warn">'+esc(t)+'</div>').join('')
      +r.reasons.map(t =>'<div class="nc-reason nc-reason-info">'+esc(t)+'</div>').join('')
      +'</div>';

    /* Jev block */
    const jevHtml=r.jev.available
      ?'<div class="sc-section"><h4 class="sc-section-title">Jev setup assessment</h4>'
        +'<p style="font-size:13px;color:var(--nc-navy2)">Tier: <strong>'+esc(r.jev.tier)+'</strong>\u2002\xb7\u2002Confidence: <strong>'
        +(fin(r.jev.confidence)?Math.round(r.jev.confidence*100)+'%':'\u2014')+'</strong>\u2002\xb7\u2002Rank: <strong>'+r.rank+' of '+ranked.length+'</strong></p>'
        +'<p class="nc-caveat">Jev tier = structural alignment of this setup with current index state as assessed by the model. Top/high = strong alignment found; not a trade recommendation. Confidence = model posterior on its own tier choice, not a probability of profit.</p>'
        +'</div>'
      :'<div class="sc-section"><p class="nc-muted" style="font-size:12.5px">Jev review not available for this setup.</p></div>';

    /* backtest stats */
    const stats=rObj.stats||{};
    const statsHtml=fin(stats.trades)
      ?'<div class="sc-section"><h4 class="sc-section-title">Backtest statistics\u00a0<span class="nc-status-chip nc-status-'+esc(statusLower)+'">'+esc(s.status||'\u2014')+'</span></h4>'
        +'<p class="nc-caveat">Paper simulation on NSE F&amp;O bhavcopy. Costs include modelled commission, taxes and slippage \u2014 not executable quotes. Validation gate: \u226560 trades, t-stat \u22652.0, positive mean in both sample halves. Past results \u2260 future performance. Return basis: '+esc(stats.return_basis||'\u2014')+'.</p>'
        +'<div class="nc-table-scroll"><table class="nc-stats-table"><thead><tr><th>Metric</th><th>Value</th><th>Note</th></tr></thead><tbody>'
        +'<tr><td>Trades</td><td>'+iInt(stats.trades)+'</td><td>Sample size</td></tr>'
        +'<tr><td>Win rate</td><td>'+pctP(stats.win_rate,1)+'</td><td>Win rate without EV edge is unreliable</td></tr>'
        +'<tr><td>Mean return</td><td class="'+cls(stats.mean_return_pct)+'">'+pct(stats.mean_return_pct,2)+'</td><td>Arithmetic; skewed by tails</td></tr>'
        +'<tr><td>Median return</td><td class="'+cls(stats.median_return_pct)+'">'+pct(stats.median_return_pct,2)+'</td><td>More robust than mean</td></tr>'
        +'<tr><td>T-stat</td><td class="'+cls(stats.t_stat)+'">'+fmt(stats.t_stat,2)+'</td><td>|t|\u22652 = conventional significance</td></tr>'
        +'<tr><td>Worst return</td><td class="neg">'+pct(stats.worst_return_pct,2)+'</td><td>Tail risk reference</td></tr>'
        +(stats.first_half ?'<tr><td>1st-half mean</td><td class="'+cls(stats.first_half.mean_return_pct)+'">'+pct(stats.first_half.mean_return_pct,2)+'</td><td>Stability check</td></tr>':'')
        +(stats.second_half?'<tr><td>2nd-half mean</td><td class="'+cls(stats.second_half.mean_return_pct)+'">'+pct(stats.second_half.mean_return_pct,2)+'</td><td>Stability check</td></tr>':'')
        +'</tbody></table></div></div>'
      :'<div class="sc-section"><p class="nc-caveat">No backtest statistics for this rule. Treat as structural/model research only.</p></div>';

    /* math score bar */
    const scoreHtml=
      '<div class="nc-score-bar">'
      +'<div><div class="nc-score-num">'+(fin(r.mathScore)?r.mathScore.toFixed(0):'\u2014')+'<span class="nc-score-denom">/100</span></div>'
      +'<div style="font-size:10px;color:var(--nc-muted);margin-top:3px">Heuristic \u2014 not a probability</div></div>'
      +'<div class="nc-score-breakdown">'
      +(fin(mc.exitProbability)?'<div class="nc-score-comp"><span>Exit P(profit) \xd750%</span><div class="nc-score-track"><div class="nc-score-fill" style="width:'+Math.round(mc.exitProbability)+'%"></div></div><span>'+mc.exitProbability.toFixed(0)+'</span></div>':'')
      +(fin(mc.expectedReturn) ?'<div class="nc-score-comp"><span>EV/risk \xd730%</span><div class="nc-score-track"><div class="nc-score-fill" style="width:'+Math.round(mc.expectedReturn)+'%"></div></div><span>'+mc.expectedReturn.toFixed(0)+'</span></div>':'')
      +(fin(mc.downside)       ?'<div class="nc-score-comp"><span>Downside buffer \xd720%</span><div class="nc-score-track"><div class="nc-score-fill" style="width:'+Math.round(mc.downside)+'%"></div></div><span>'+mc.downside.toFixed(0)+'</span></div>':'')
      +(!fin(r.mathScore)?'<p class="nc-muted" style="font-size:11px;margin:4px 0 0">Score unavailable \u2014 risk or exit data incomplete or horizon inconsistent.</p>':'')
      +'</div></div>';

    /* assemble */
    return '<article class="nc-setup-card'+(expanded?' is-expanded':'')+'" data-rule="'+esc(s.rule)+'" data-bucket="'+esc(r.bucket)+'">'
      /* compact header */
      +'<button class="nc-setup-compact" aria-expanded="'+expanded+'" type="button">'
        +'<div class="nc-rank-badge nc-rank-'+esc(r.bucket)+'">#'+r.rank+'</div>'
        +'<div class="nc-setup-info">'
          +'<span class="nc-setup-label">'+esc(s.label||s.rule)+'</span>'
          +'<div class="nc-setup-chips">'
            +'<span class="nc-chip '+bCls+'">'+esc(bLabels[r.bucket]||r.bucket)+'</span>'
            +'<span class="nc-chip nc-chip-action">'+esc(s.action||'\u2014')+'</span>'
            +(s.firing?'<span class="nc-chip nc-chip-firing">\u25cf Firing</span>':'<span class="nc-chip nc-chip-dormant">\u25cb Not firing</span>')
            +(r.jev.available
              ?'<span class="nc-chip nc-chip-jev">Jev '+esc(r.jev.tier)+(fin(r.jev.confidence)?' '+Math.round(r.jev.confidence*100)+'%':'')+'</span>'
              :'<span class="nc-chip nc-chip-jev-none">Jev \u2014</span>')
            +'<span class="nc-status-chip nc-status-'+esc(statusLower)+'">'+esc(s.status||'\u2014')+'</span>'
          +'</div>'
        +'</div>'
        +'<div class="nc-setup-ev">'
          +'<span class="nc-ev-val '+cls(ex.exp_pnl_per_lot)+'">'+money(ex.exp_pnl_per_lot)+'</span>'
          +'<span class="nc-ev-lbl">'+(fin(r.mathScore)?'score '+r.mathScore.toFixed(0):'score \u2014')+'</span>'
        +'</div>'
        +'<span class="nc-expand-icon" aria-hidden="true">\u25be</span>'
      +'</button>'
      /* full body — always in DOM; CSS hides until is-expanded */
      +'<div class="nc-setup-body">'
        +scoreHtml
        +'<div class="sc-section"><h4 class="sc-section-title">Model exit P&amp;L \u00b7 '+esc(holdDesc)+' horizon (primary)</h4>'+exitHtml+'</div>'
        +'<div class="sc-section"><h4 class="sc-section-title">Legs \u00b7 EOD reference prices</h4>'+legsHtml+'</div>'
        +'<div class="sc-section"><h4 class="sc-section-title">Position Greeks per lot (sensitivity \u2014 not standalone alpha)</h4>'+greeksHtml+'</div>'
        +'<div class="sc-section"><h4 class="sc-section-title">Risk at expiry \u00b7 gross per lot (secondary \u00b7 theoretical)</h4>'+riskHtml+'</div>'
        +(svgHtml?'<div class="sc-section"><h4 class="sc-section-title">Gross payoff at expiry (computed from EOD leg prices)</h4>'+svgHtml
          +'<p class="nc-caveat" style="margin-top:6px">X-axis: Nifty spot at expiry. Y-axis: gross P&amp;L per lot before fees. Theoretical expiry scenario \u2014 not the planned 5-session exit.</p></div>':'')
        +'<div class="sc-section"><h4 class="sc-section-title">Entry &amp; exit plan</h4>'+planHtml+'</div>'
        +'<div class="sc-section"><h4 class="sc-section-title">Signal assessment &amp; blockers</h4>'+rwHtml+'</div>'
        +jevHtml
        +statsHtml
      +'</div>'
    +'</article>';
  }

  /* ── Render all cards into #setup-cards ── */
  function renderSetupFeed() {
    const host=$('setup-cards'); if(!host) return;
    host.innerHTML=ranked.map((r,i)=>buildCard(r,i<3)).join('');
    ranked.forEach(r=>byRule.set(r.setup.rule,r));
    updateCounts();
    updateVisibility();
    host.querySelectorAll('.nc-setup-compact').forEach(btn=>{
      btn.addEventListener('click',()=>{
        const card=btn.closest('.nc-setup-card');
        const exp=card.classList.toggle('is-expanded');
        btn.setAttribute('aria-expanded',String(exp));
      });
    });
  }

  /* ── Filter predicates ── */
  function matchFilter(r) {
    if (activeFilter==='active')   return r.bucket==='consider'||r.bucket==='watch';
    if (activeFilter==='buyers') {
      const a=(r.setup.action||'').toUpperCase();
      return fin(r.risk.netDebit) && r.risk.netDebit > 0 && !a.startsWith('SHORT');
    }
    if (activeFilter==='defined')  return r.risk.valid&&!r.risk.unlimitedLoss;
    if (activeFilter==='inactive') return r.bucket==='inactive';
    if (activeFilter==='avoid')    return r.bucket==='avoid';
    return true;
  }
  function matchSearch(r) {
    if (!searchQ) return true;
    return (r.setup.label||'').toLowerCase().includes(searchQ)||
           (r.setup.rule||'').toLowerCase().includes(searchQ)||
           (r.setup.action||'').toLowerCase().includes(searchQ);
  }
  function updateVisibility() {
    let vis=0;
    document.querySelectorAll('#setup-cards [data-rule]').forEach(card=>{
      const r=byRule.get(card.dataset.rule);
      const show=r?(matchFilter(r)&&matchSearch(r)):false;
      card.classList.toggle('setup-hidden',!show);
      if(show) vis++;
    });
    const el=$('feed-count'); if(el) el.textContent=vis+' of '+ranked.length+' setups';
  }
  function updateCounts() {
    const defFn=r=>r.risk.valid&&!r.risk.unlimitedLoss;
    const buyFn=r=>fin(r.risk.netDebit)&&r.risk.netDebit>0&&!(r.setup.action||'').toUpperCase().startsWith('SHORT');
    const c={all:ranked.length,active:ranked.filter(r=>r.bucket==='consider'||r.bucket==='watch').length,buyers:ranked.filter(buyFn).length,defined:ranked.filter(defFn).length,inactive:ranked.filter(r=>r.bucket==='inactive').length,avoid:ranked.filter(r=>r.bucket==='avoid').length};
    Object.entries(c).forEach(([f,n])=>{const el=$('count-'+f);if(el) el.textContent=n;});
  }

  /* ── Bind filter tabs + search ── */
  function bindFilters() {
    const tabs=$('filter-tabs');
    if(tabs) {
      tabs.querySelectorAll('[data-filter]').forEach(btn=>{
        btn.addEventListener('click',()=>{
          activeFilter=btn.dataset.filter;
          tabs.querySelectorAll('.nc-tab').forEach(b=>{
            const active=b===btn;
            b.classList.toggle('nc-tab-active',active);
            b.setAttribute('aria-pressed',String(active));
          });
          updateVisibility();
        });
      });
    }
    const srch=$('setup-search');
    if(srch){
      let t;
      srch.addEventListener('input',()=>{
        clearTimeout(t);
        t=setTimeout(()=>{searchQ=srch.value.trim().toLowerCase();updateVisibility();},200);
      });
    }
  }

  /* ── Header ── */
  function renderHeader() {
    const d=dataset;
    const el=$('session-date'); if(el) el.textContent='EOD '+isoD(d.as_of);
    const cv=$('coverage'); if(cv) cv.textContent=(d.expiries||[]).length+' expiries \u00b7 '+(d.constituents_count||50)+' constituents';
    const ns=$('next-session'); if(ns) ns.textContent='Next: '+isoD(d.next_session);
  }

  /* ── Decision summary ── */
  function renderDecisionSummary() {
    const el=$('decision-summary'); if(!el) return;
    const eligible=ranked.filter(r=>r.eligible);
    if (!eligible.length) {
      const top=ranked[0];
      const topW=top?top.warnings.filter(w=>!w.startsWith('Maths score')&&!w.startsWith('Rank by')&&!w.startsWith('Expiry payoff')&&!w.startsWith('Jev provenance')).slice(0,1):[];
      el.innerHTML='<div class="nc-ds-wait">'
        +'<span class="nc-ds-wait-icon" aria-hidden="true">\u23f8</span>'
        +'<div><strong>WAIT \u2014 No setup qualifies today</strong>'
        +'<p>No setup clears every evidence, model-return and risk check.'
        +(topW.length?' '+esc(topW[0]):'')
        +' The watchlist is for research, not an entry signal. Open a card for its numbers and failed checks.</p>'
        +'</div></div>';
      return;
    }
    const top=eligible[0], s=top.setup, ev=s.exit?.exp_pnl_per_lot;
    el.innerHTML='<div class="nc-ds-candidate">'
      +'<div>'
        +'<div class="nc-ds-badge consider">Top candidate \u2014 consider</div>'
        +'<h3 class="nc-ds-title">'+esc(s.label||s.rule)+'</h3>'
        +'<div class="nc-ds-chips">'
          +'<span class="nc-chip nc-chip-action">'+esc(s.action||'\u2014')+'</span>'
          +'<span class="nc-chip nc-bucket-consider">Consider</span>'
          +(top.jev.available?'<span class="nc-chip nc-chip-jev">Jev '+esc(top.jev.tier)+(fin(top.jev.confidence)?' '+Math.round(top.jev.confidence*100)+'%':'')+'</span>':'')
        +'</div>'
        +'<p class="nc-ds-ev">Model exit EV: <strong class="'+cls(ev)+'">'+money(ev)+'</strong>\u2002\xb7\u2002P(profit at exit): <strong>'+pctP(s.exit?.p_profit,0)+'</strong></p>'
        +'<p class="nc-ds-caveat">EOD snapshot only. Model EV is not a profit guarantee. Jev confidence \u2260 profit probability. Not investment advice.</p>'
      +'</div>'
      +'<div class="nc-ds-score">'
        +'<span class="nc-ds-score-num">'+(fin(top.mathScore)?top.mathScore.toFixed(0):'\u2014')+'</span>'
        +'<span class="nc-ds-score-lbl">Math score<br><em>heuristic/100</em></span>'
      +'</div>'
    +'</div>';
  }

  /* ── Market cards ── */
  function renderMarketCards() {
    const idx=dataset.index||{};
    const spot=idx.option_spot||idx.close;
    const sigma=ranked.length&&fin(ranked[0].sigmaMove)?ranked[0].sigmaMove:null;
    const el=$('market-cards'); if(!el) return;
    const cards=[
      {l:'Nifty spot',    v:iInt(spot),           sub:pct(idx.change_pct)+' today',      vc:cls(idx.change_pct)},
      {l:'ATM IV',        v:pctP(idx.atm_iv),     sub:'Implied vol (1m)',                vc:''},
      {l:'Realised vol',  v:pctP(idx.rv20),       sub:'20-day RV',                       vc:''},
      {l:'VRP (IV\u2212RV)',v:pct(idx.vrp,1),     sub:'Negative = cheap options',        vc:cls(fin(idx.vrp)?-idx.vrp:null)},
      {l:'IV percentile', v:pctP(idx.iv_pct,0),   sub:'1-year rank',                    vc:''},
      {l:'1\u03c3 to exp.',v:fin(sigma)?'\xb1'+iInt(sigma):'\u2014',sub:'To trade expiry',vc:''},
      {l:'PCR',           v:fmt(idx.pcr),          sub:pct(idx.pcr_chg5)+' (5d)',        vc:cls(idx.pcr_chg5)},
      {l:'India VIX',     v:fmt(idx.vix),          sub:pct(idx.vix_change_pct)+' today', vc:cls(fin(idx.vix_change_pct)?-idx.vix_change_pct:null)},
    ];
    el.innerHTML=cards.map(c=>
      '<div class="mkt-card"><dl><dt>'+esc(c.l)+'</dt><dd class="'+esc(c.vc)+'">'+c.v+'</dd><dd><small>'+c.sub+'</small></dd></dl></div>'
    ).join('');
    const expl=$('market-explain');
    if(expl){
      const vrp=idx.vrp,pcr=idx.pcr;
      const vt=fin(vrp)?(vrp<-2?'IV below recent realised vol \u2014 options look relatively cheap.':vrp>2?'IV above recent realised vol \u2014 options look relatively expensive.':'Vol fairly priced vs recent realised moves.'):'';
      const pt=fin(pcr)?(pcr>1.3?' Put OI dominates \u2014 institutional hedging signal.':pcr<0.8?' Call OI dominates.':' PCR near neutral.'):'';
      const bt=idx.buildup?' Futures build-up: '+idx.buildup+'.':'';
      expl.innerHTML=esc(vt+pt+bt)+' All values are EOD official NSE data \u2014 not live prices.';
    }
  }

  /* ── Comparison section ── */
  function renderComparisonSection() {
    const cmp=dataset.comparison; if(!cmp) return;
    const note=$('comparison-note');
    if(note) note.textContent='Research comparison at the planned exit, net of modelled costs. Negative EV is not a buy signal. Expiry bounds below are exact gross leg payoffs, not an early-exit loss guarantee.';
    const host=$('comparison-rows'); if(!host) return;
    const cands=cmp.candidates||[];
    if(!cands.length){host.innerHTML='<tr><td colspan="8" class="nc-muted">Not available for today\u2019s view.</td></tr>';return;}
    host.innerHTML=cands.map(c=>{
      const ex=c.exit||{},bt=c.backtest||{},idx=dataset.index||{};
      const risk=NiftyMath.expiryRisk((c.legs||[]).map(l=>({...l,expiry:idx.trade_expiry,lot:idx.lot})),idx.option_spot||idx.close);
      const ror=risk.valid&&!risk.unlimitedLoss&&risk.maxLoss<0&&fin(ex.exp_pnl_per_lot)?100*ex.exp_pnl_per_lot/-risk.maxLoss:null;
      return '<tr>'
        +'<td><strong>'+esc(c.name||c.id)+'</strong></td>'
        +'<td class="'+cls(c.net_premium_per_lot)+'">'+money(c.net_premium_per_lot)+'</td>'
        +'<td class="pos">'+(risk.unlimitedProfit?'Unlimited ↑':money(risk.maxProfit))+'</td>'
        +'<td class="neg">'+(risk.unlimitedLoss?'Unbounded':money(risk.maxLoss))+'</td>'
        +'<td class="'+cls(ex.exp_pnl_per_lot)+'">'+money(ex.exp_pnl_per_lot)+'</td>'
        +'<td>'+pctP(ex.p_profit,0)+'</td>'
        +'<td class="'+cls(ror)+'">'+pctP(ror,1)+'</td>'
        +'<td class="'+cls(bt.mean_return_pct)+'">'+pct(bt.mean_return_pct,2)+'</td>'
        +'</tr>';
    }).join('');
  }

  /* ── SVG multi-line chart (vol history) ── */
  function svgLines(host,series,opts) {
    if(!host) return;
    const dates=(opts&&opts.dates)||[];
    const n=dates.length; if(!n){host.innerHTML='<p class="nc-muted">No data.</p>';return;}
    const W=1100,H=200,L=52,R=14,T=14,B=36;
    const all=series.flatMap(s2=>(s2.values||[]).filter(fin));
    if(!all.length){host.innerHTML='<p class="nc-muted">No values.</p>';return;}
    const lo=Math.min(...all),hi=Math.max(...all);
    const xf=i=>L+(W-L-R)*(i+0.5)/n;
    const yf=v=>T+(H-T-B)*(1-(v-lo)/(hi-lo||1));
    const ax='font-size="9" fill="#6b7a91" font-family="system-ui"';
    let svg='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+esc((opts&&opts.title)||'Chart')+'">';
    for(let k=0;k<=4;k++){const v=lo+(hi-lo)*k/4;svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+yf(v).toFixed(1)+'" y2="'+yf(v).toFixed(1)+'" stroke="#eef1ec" stroke-width="1"/><text x="'+(L-4)+'" y="'+(yf(v)+3).toFixed(1)+'" text-anchor="end" '+ax+'>'+v.toFixed(1)+'%</text>';}
    let lx=L;
    series.forEach(s2=>{
      const vals=s2.values||[];
      const pts=[];
      vals.forEach((v,i)=>{if(fin(v)) pts.push(xf(i).toFixed(1)+','+yf(v).toFixed(1));});
      if(pts.length>1) svg+='<polyline points="'+pts.join(' ')+'" fill="none" stroke="'+esc(s2.color||'#000')+'" stroke-width="1.5"'+(s2.dash?' stroke-dasharray="4 3"':'')+'/>';
      svg+='<line x1="'+lx+'" x2="'+(lx+12)+'" y1="8" y2="8" stroke="'+esc(s2.color||'#000')+'" stroke-width="2"'+(s2.dash?' stroke-dasharray="4 3"':'')+'/><text x="'+(lx+16)+'" y="11" '+ax+'>'+esc(s2.name||'')+'</text>';
      lx+=100;
    });
    [0,Math.floor(n/2),n-1].forEach(i=>{if(dates[i]) svg+='<text x="'+xf(i).toFixed(1)+'" y="'+(H-8)+'" text-anchor="middle" '+ax+'>'+esc(String(dates[i]).slice(5))+'</text>';});
    svg+='</svg>';
    host.innerHTML=svg;
  }

  /* ── Chain section ── */
  let curExp=null;
  function renderChainSection(){
    const exps=dataset.expiries||[]; if(!exps.length) return;
    curExp=exps[0];
    const sel=$('expiry-select');
    if(sel){
      sel.innerHTML=exps.map(e=>'<option value="'+esc(e.expiry)+'">'+esc(e.expiry)+'</option>').join('');
      sel.addEventListener('change',()=>{curExp=exps.find(e=>e.expiry===sel.value)||exps[0];renderSigma();renderOI();renderChainTable();});
      document.querySelectorAll('input[name="oi-mode"]').forEach(r=>r.addEventListener('change',renderOI));
    }
    renderSigma(); renderOI(); renderChainTable();
    const h=dataset.history||{};
    const vix=new Map((h.vix_dates||[]).map((d,i)=>[d,(h.vix||[])[i]]));
    svgLines($('vol-chart'),[
      {name:'ATM IV',    values:h.atm_iv||[],                                           color:'#0d8a7a'},
      {name:'RV (20d)',  values:h.rv20||[],                                             color:'#c07830',dash:true},
      {name:'India VIX', values:(h.dates||[]).map(d=>vix.has(d)?vix.get(d):null),      color:'#c0392b'},
    ],{dates:h.dates||[],title:'Volatility history'});
    renderHhhl();
  }
  function renderSigma(){
    const e=curExp; if(!e) return;
    const el=$('sigma-cards'); if(!el) return;
    const s1=e.sigma_1||[],s2=e.sigma_2||[];
    el.innerHTML='<div class="nc-sigma-cards">'
      +'<div class="nc-sigma-card"><dl><dt>Expiry</dt><dd>'+esc(e.expiry||'\u2014')+'</dd></dl></div>'
      +'<div class="nc-sigma-card"><dl><dt>Max pain</dt><dd>'+iInt(e.max_pain)+'</dd></dl></div>'
      +'<div class="nc-sigma-card"><dl><dt>1\u03c3 band</dt><dd>'+(s1.length===2?iInt(s1[0])+' \u2013 '+iInt(s1[1]):'\u2014')+'</dd></dl></div>'
      +'<div class="nc-sigma-card"><dl><dt>2\u03c3 band</dt><dd>'+(s2.length===2?iInt(s2[0])+' \u2013 '+iInt(s2[1]):'\u2014')+'</dd></dl></div>'
      +'</div>';
  }
  function renderOI(){
    const e=curExp; if(!e||!Array.isArray(e.rows)||!e.rows.length) return;
    const host=$('oi-chart-wrap'); if(!host) return;
    const spot=(dataset.index||{}).option_spot||(dataset.index||{}).close||0;
    const modeEl=document.querySelector('input[name="oi-mode"]:checked');
    const mode=modeEl?modeEl.value:'oi';
    const rows=e.rows.filter(r=>r.strike>=spot*0.82&&r.strike<=spot*1.18);
    if(!rows.length){host.innerHTML='<p class="nc-muted">No nearby strikes.</p>';return;}
    const str=rows.map(r=>r.strike);
    const ceV=rows.map(r=>mode==='oi_change'?(r.ce?.oi_change||0):(r.ce?.oi||0));
    const peV=rows.map(r=>mode==='oi_change'?(r.pe?.oi_change||0):(r.pe?.oi||0));
    const maxV=Math.max(...ceV.map(Math.abs),...peV.map(Math.abs),1);
    const W=1100,H=220,L=56,R=16,T=20,B=44,n=str.length;
    const bw=Math.max(2,Math.floor((W-L-R)/n/2.6));
    const xc=i=>L+(W-L-R)*(i+0.5)/n;
    const yb=T+(H-T-B); // base line (zero)
    const yf=v=>T+(H-T-B)*(1-v/maxV);
    const ax='font-size="9" fill="#6b7a91" font-family="system-ui"';
    let svg='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Open interest by strike">';
    const s1=e.sigma_1||[];
    if(s1.length===2){
      const x1=L+(W-L-R)*(Math.max(str[0],s1[0])-str[0])/(str[n-1]-str[0]||1);
      const x2=L+(W-L-R)*(Math.min(str[n-1],s1[1])-str[0])/(str[n-1]-str[0]||1);
      if(x2>x1) svg+='<rect x="'+x1.toFixed(1)+'" width="'+(x2-x1).toFixed(1)+'" y="'+T+'" height="'+(H-T-B)+'" fill="#0d8a7a" opacity="0.07"/>';
    }
    str.forEach((k,i)=>{
      const yc=yf(Math.max(0,ceV[i])),yp=yf(Math.max(0,peV[i]));
      svg+='<rect x="'+(xc(i)-bw).toFixed(1)+'" width="'+bw+'" y="'+yc.toFixed(1)+'" height="'+(yb-yc).toFixed(1)+'" class="nc-bar-ce"><title>'+esc(k+' CE: '+iInt(ceV[i]))+'</title></rect>';
      svg+='<rect x="'+xc(i).toFixed(1)+'" width="'+bw+'" y="'+yp.toFixed(1)+'" height="'+(yb-yp).toFixed(1)+'" class="nc-bar-pe"><title>'+esc(k+' PE: '+iInt(peV[i]))+'</title></rect>';
    });
    const spotX=L+(W-L-R)*(spot-str[0])/(str[n-1]-str[0]||1);
    if(spotX>L&&spotX<W-R) svg+='<line x1="'+spotX.toFixed(1)+'" x2="'+spotX.toFixed(1)+'" y1="'+T+'" y2="'+yb+'" class="nc-spot-line"/><text x="'+(spotX+4).toFixed(1)+'" y="'+(T+10)+'" '+ax+'>spot</text>';
    if(fin(e.max_pain)){const mx=L+(W-L-R)*(e.max_pain-str[0])/(str[n-1]-str[0]||1);if(mx>L&&mx<W-R) svg+='<line x1="'+mx.toFixed(1)+'" x2="'+mx.toFixed(1)+'" y1="'+T+'" y2="'+yb+'" class="nc-mp-line"/><text x="'+(mx+4).toFixed(1)+'" y="'+(T+20)+'" '+ax+' fill="#c07830">max pain</text>';}
    [0,Math.floor(n/2),n-1].forEach(i=>svg+='<text x="'+xc(i).toFixed(1)+'" y="'+(H-18)+'" text-anchor="middle" '+ax+'>'+str[i]+'</text>');
    svg+='<text x="'+(L-4)+'" y="'+(T+8)+'" text-anchor="end" '+ax+'>'+iInt(maxV/1e5)+'L</text>';
    svg+='<rect x="'+L+'" y="'+(H-14)+'" width="10" height="8" class="nc-bar-ce" opacity="0.8"/><text x="'+(L+14)+'" y="'+(H-8)+'" '+ax+'>CE</text>';
    svg+='<rect x="'+(L+50)+'" y="'+(H-14)+'" width="10" height="8" class="nc-bar-pe" opacity="0.8"/><text x="'+(L+64)+'" y="'+(H-8)+'" '+ax+'>PE</text>';
    svg+='</svg>';
    host.innerHTML=svg;
  }
  function renderChainTable(){
    const e=curExp; if(!e||!Array.isArray(e.rows)||!e.rows.length) return;
    const host=$('chain-table-wrap'); if(!host) return;
    const spot=(dataset.index||{}).option_spot||(dataset.index||{}).close||0;
    const rows=e.rows.filter(r=>r.strike>=spot*0.88&&r.strike<=spot*1.12);
    if(!rows.length){host.innerHTML='<p class="nc-muted">No strikes in range.</p>';return;}
    const atm=rows.reduce((a,b)=>Math.abs(b.strike-spot)<Math.abs(a.strike-spot)?b:a).strike;
    host.innerHTML='<table class="nc-chain-table nc-table" style="min-width:500px">'
      +'<thead><tr><th>\u0394 CE</th><th>IV% CE</th><th>OI CE</th><th class="nc-strike-cell">Strike</th><th>OI PE</th><th>IV% PE</th><th>\u0394 PE</th></tr></thead>'
      +'<tbody>'+rows.map(r=>{
        const ce=r.ce||{},pe=r.pe||{},isAtm=r.strike===atm;
        return '<tr'+(isAtm?' class="nc-atm"':'')+'>'
          +'<td class="nc-num '+cls(ce.delta)+'">'+fmt(ce.delta,3)+'</td>'
          +'<td class="nc-num">'+pctP(ce.iv,1)+'</td>'
          +'<td class="nc-num">'+iInt(ce.oi)+'</td>'
          +'<td class="nc-strike-cell">'+iInt(r.strike)+(isAtm?'<small>ATM</small>':'')+'</td>'
          +'<td class="nc-num">'+iInt(pe.oi)+'</td>'
          +'<td class="nc-num">'+pctP(pe.iv,1)+'</td>'
          +'<td class="nc-num '+cls(pe.delta)+'">'+fmt(pe.delta,3)+'</td>'
          +'</tr>';
      }).join('')+'</tbody></table>';
  }
  function renderHhhl(){
    const c=dataset.hhhl||{},host=$('hhhl-chart'),str=(dataset.index||{}).structure||{};
    const stEl=$('hhhl-state');
    if(stEl) stEl.textContent=(str.structure||'\u2014')+(str.breakout?' \u00b7 fresh breakout':'')+' \u00b7 close '+fmt(str.close)+' vs 20d SMA '+fmt(str.sma20);
    if(!host) return;
    const n=(c.dates||[]).length; if(!n){host.innerHTML='<p class="nc-muted">No price history.</p>';return;}
    const W=1100,H=270,L=56,R=12,T=20,B=40;
    const lo=Math.min(...(c.low||[]).filter(fin)), hi=Math.max(...(c.high||[]).filter(fin));
    const xf=i=>L+(W-L-R)*(i+0.5)/n;
    const yf=v=>T+(H-T-B)*(1-(v-lo)/(hi-lo||1));
    const bw=Math.max(1.5,(W-L-R)/n*0.55);
    const ax='font-size="9" fill="#6b7a91" font-family="system-ui"';
    let svg='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Nifty price chart">';
    for(let k=0;k<=4;k++){const v=lo+(hi-lo)*k/4;svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+yf(v).toFixed(1)+'" y2="'+yf(v).toFixed(1)+'" stroke="#eef1ec" stroke-width="1"/><text x="'+(L-4)+'" y="'+(yf(v)+3).toFixed(1)+'" text-anchor="end" '+ax+'>'+fmt(v,0)+'</text>';}
    c.dates.forEach((d,i)=>{
      const o=(c.open||[])[i],h2=(c.high||[])[i],l2=(c.low||[])[i],cl2=(c.close||[])[i];
      if(!fin(o)||!fin(cl2)) return;
      const up=cl2>=o;
      svg+='<line x1="'+xf(i).toFixed(1)+'" x2="'+xf(i).toFixed(1)+'" y1="'+yf(h2).toFixed(1)+'" y2="'+yf(l2).toFixed(1)+'" class="'+(up?'nc-wick-up':'nc-wick-dn')+'"/>';
      svg+='<rect x="'+(xf(i)-bw/2).toFixed(1)+'" width="'+bw.toFixed(1)+'" y="'+yf(Math.max(o,cl2)).toFixed(1)+'" height="'+Math.max(1,Math.abs(yf(o)-yf(cl2))).toFixed(1)+'" class="'+(up?'nc-candle-up':'nc-candle-dn')+'"/>';
      const lbl=(c.labels||[])[i];
      if(lbl) svg+='<text x="'+xf(i).toFixed(1)+'" y="'+(T+10)+'" text-anchor="middle" font-size="8" fill="'+(lbl.includes('HH')||lbl.includes('HL')?'#0d8a7a':'#c0392b')+'" font-family="system-ui">'+esc(lbl)+'</text>';
    });
    [0,Math.floor(n/4),Math.floor(n/2),Math.floor(3*n/4),n-1].forEach(i=>{if(c.dates[i]) svg+='<text x="'+xf(i).toFixed(1)+'" y="'+(H-12)+'" text-anchor="middle" '+ax+'>'+esc(String(c.dates[i]).slice(5))+'</text>';});
    svg+='</svg>';
    host.innerHTML=svg;
  }

  /* ── Participants ── */
  function renderParticipantsSection(){
    const parts=dataset.participants; const host=$('participant-cards'); if(!host) return;
    const rows=Array.isArray(parts)?parts:[];
    if(!rows.length){host.innerHTML='<p class="nc-muted">No participant data.</p>';return;}
    host.innerHTML=rows.map(p=>{
      const net=p.net||{};
      return '<div class="nc-part-card"><h4>'+esc(p.participant||'\u2014')+'</h4>'
        +'<dl>'
        +(fin(net.futures)?'<dt>Net futures</dt><dd class="'+cls(net.futures)+'">'+iInt(net.futures)+'</dd>':'')
        +(fin(net.calls)?'<dt>Net calls</dt><dd class="'+cls(net.calls)+'">'+iInt(net.calls)+'</dd>':'')
        +(fin(net.puts)?'<dt>Net puts</dt><dd class="'+cls(net.puts)+'">'+iInt(net.puts)+'</dd>':'')
        +'</dl>'
        +(p.read?'<div class="nc-part-read">'+esc(String(p.read).slice(0,220))+'</div>':'')
        +'</div>';
    }).join('');
  }

  /* ── Rules evidence ── */
  function renderRulesSection(){
    const rules=dataset.rules||[]; const host=$('rules-wrap'); if(!host) return;
    if(!rules.length){host.innerHTML='<p class="nc-muted">No rules data.</p>';return;}
    host.innerHTML='<table class="nc-table" style="min-width:600px">'
      +'<thead><tr><th>Rule</th><th>Action</th><th>Status</th><th>Trades</th><th>Win rate</th><th>Mean rtn</th><th>T-stat</th></tr></thead>'
      +'<tbody>'+rules.map(r=>{
        const st=r.stats||{},sl=(r.status||'').toLowerCase().replace(/[^a-z0-9]/g,'_');
        return '<tr>'
          +'<td>'+esc(r.label||r.id||'\u2014')+'</td>'
          +'<td>'+esc(r.action||'\u2014')+'</td>'
          +'<td><span class="nc-status-chip nc-status-'+esc(sl)+'">'+esc(r.status||'\u2014')+'</span></td>'
          +'<td class="nc-num">'+iInt(st.trades)+'</td>'
          +'<td class="nc-num">'+pctP(st.win_rate,1)+'</td>'
          +'<td class="nc-num '+cls(st.mean_return_pct)+'">'+pct(st.mean_return_pct,2)+'</td>'
          +'<td class="nc-num '+cls(st.t_stat)+'">'+fmt(st.t_stat,2)+'</td>'
          +'</tr>';
      }).join('')+'</tbody></table>';
  }

  /* ── Constituents ── */
  let constS={status:'',stance:'',sort:'symbol',q:''};
  function renderConstituentsSection(){
    filterConst();
    ['const-status','const-stance','const-sort'].forEach(id=>{
      const el=$(id); if(!el) return;
      el.addEventListener('change',()=>{
        if(id==='const-status') constS.status=el.value;
        else if(id==='const-stance') constS.stance=el.value;
        else constS.sort=el.value;
        filterConst();
      });
    });
    const s2=$('const-search');
    if(s2){let t;s2.addEventListener('input',()=>{clearTimeout(t);t=setTimeout(()=>{constS.q=s2.value.trim().toLowerCase();filterConst();},220);});}
  }
  function filterConst(){
    let rows=(dataset.constituents||[]).slice();
    if(constS.status) rows=rows.filter(c=>(c.hhhl_status||'')===constS.status);
    if(constS.stance) rows=rows.filter(c=>(c.jev||{}).stance===constS.stance);
    if(constS.q) rows=rows.filter(c=>(c.symbol||'').toLowerCase().includes(constS.q));
    if(constS.sort==='iv') rows.sort((a,b)=>(b.iv_pct||0)-(a.iv_pct||0));
    else if(constS.sort==='ret5') rows.sort((a,b)=>(b.ret5_pct||0)-(a.ret5_pct||0));
    else rows.sort((a,b)=>(a.symbol||'').localeCompare(b.symbol||''));
    const cnt=$('const-count'); if(cnt) cnt.textContent=rows.length+' of '+(dataset.constituents||[]).length+' constituents';
    const host=$('constituents-wrap'); if(!host) return;
    host.innerHTML='<table class="nc-table" style="min-width:540px">'
      +'<thead><tr><th>Symbol</th><th>Name</th><th>Spot</th><th>5d ret</th><th>HH/HL</th><th>Jev stance</th><th>IV %ile</th><th>Desk</th></tr></thead>'
      +'<tbody>'+rows.map(c=>{
        const jd=(c.jev||{}).stance||'\u2014';
        return '<tr>'
          +'<td><strong>'+esc(c.symbol||'\u2014')+'</strong></td>'
          +'<td>'+esc((c.name||'').slice(0,26))+'</td>'
          +'<td class="nc-num">'+iInt(c.spot)+'</td>'
          +'<td class="nc-num '+cls(c.ret5_pct)+'">'+pct(c.ret5_pct,1)+'</td>'
          +'<td>'+esc(c.hhhl_status||'\u2014')+'</td>'
          +'<td class="'+(jd==='bullish'?'pos':jd==='bearish'?'neg':'')+'">'+esc(jd)+'</td>'
          +'<td class="nc-num">'+pctP(c.iv_pct,0)+'</td>'
          +'<td>'+esc(c.desk_bucket||'\u2014')+'</td>'
          +'</tr>';
      }).join('')+'</tbody></table>';
  }

  /* ── Jev section ── */
  function renderJevSection(){
    const jev=dataset.jev||{},idx=jev.index||{};
    const el=$('jev-index-cards'); if(!el) return;
    const items=[{l:'Direction',d:idx.direction||{}},{l:'Volatility',d:idx.volatility||{}},{l:'Positioning',d:idx.positioning||{}},{l:'Favoured setup',d:idx.setup||{}}];
    el.innerHTML=items.map(it=>'<div class="nc-jev-card"><dl><dt>'+esc(it.l)+'</dt><dd class="nc-jev-choice">'+esc(it.d.choice||'\u2014')+'</dd><dd class="nc-jev-conf">Conf: '+pctP(fin(it.d.confidence)?it.d.confidence*100:null,0)+'</dd></dl></div>').join('');
    if(jev.message) el.insertAdjacentHTML('afterend','<p class="nc-caveat nc-caveat-warn">Jev provenance: '+esc(jev.message)+'</p>');
    const cal=jev.calibration; const calEl=$('jev-calibration'); if(!calEl) return;
    if(!cal||!fin(cal.matured)){calEl.innerHTML='<p class="nc-muted">No calibration data.</p>';return;}
    calEl.innerHTML='<p class="nc-caveat">'+iInt(cal.matured)+' matured index reviews. '+esc(cal.note||'')+' Small samples do not establish predictive reliability.</p>'
      +'<div class="nc-jev-cal">'+Object.entries(cal.by_call||{}).map(([name,c])=>'<div class="nc-jev-cal-item"><strong>'+esc(name)+'</strong><span>'+iInt(c.hits)+' hits / '+iInt(c.n)+' observations</span></div>').join('')+'</div>';
  }

  /* ── Research ── */
  function renderResearchSection(){
    const res=dataset.research||{},host=$('research-body'); if(!host) return;
    const sections=['institutions','strategies','evidence','github'];
    host.innerHTML=sections.map(section=>{
      const rows=Array.isArray(res[section])?res[section]:[];
      return '<details class="nc-details"><summary>'+esc(section)+' · '+rows.length+'</summary><div class="nc-research-list">'+rows.map(r=>{
        const url=r.source_url||r.url||'';
        const text=r.summary||r.finding||r.what||[r.legs,r.edge_source,r.main_risk].filter(Boolean).join(' · ');
        return '<article class="nc-research-item"><h4>'+esc(r.title||r.name||r.repo||'Research')+'</h4><p>'+esc(text||'')+'</p>'
          +(/^https?:\/\//.test(url)?'<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">Source</a>':'')+'</article>';
      }).join('')+'</div></details>';
    }).join('');
  }

  /* ── Method / data audit ── */
  function renderMethodSection(){
    const src=dataset.source||{},lims=dataset.limitations;
    const host=$('method-body'); if(!host) return;
    let html='';
    if(src.name) html+='<p><strong>Source:</strong> '+esc(src.name)+'</p>';
    if(dataset.method) html+='<dl>'+Object.entries(dataset.method).map(([k,v])=>'<dt><strong>'+esc(k.replaceAll('_',' '))+'</strong></dt><dd>'+esc(typeof v==='object'?JSON.stringify(v):v)+'</dd>').join('')+'</dl>';
    if(Array.isArray(lims)&&lims.length) html+='<ul style="font-size:12.5px;color:var(--nc-muted);padding-left:18px">'+lims.map(l=>'<li>'+esc(l)+'</li>').join('')+'</ul>';
    host.innerHTML=html;
    const audit=$('data-audit');
    if(audit&&dataset.inputs) audit.textContent='Inputs: '+JSON.stringify(dataset.inputs).slice(0,300);
  }

  /* ── Main load ── */
  async function load(){
    const notice=$('notice');
    try {
      const src=document.body.dataset.source||new URLSearchParams(location.search).get('source')||'nifty_chain.json';
      const res=await fetch(src,{cache:'no-store'});
      if(!res.ok) throw new Error('HTTP '+res.status+' loading '+src);
      const data=await res.json();
      validate(data);
      dataset=data;
      document.body.dataset.source=data.as_of;
      if(notice) notice.hidden=true;
      ranked=NiftyMath.rankTradeSetups(data);
      renderHeader();
      renderDecisionSummary();
      renderMarketCards();
      renderSetupFeed();
      renderComparisonSection();
      renderChainSection();
      renderParticipantsSection();
      renderRulesSection();
      renderConstituentsSection();
      renderJevSection();
      renderResearchSection();
      renderMethodSection();
      bindFilters();
      document.body.dataset.ready='true';
    } catch(err){
      document.body.dataset.ready='error';
      if(notice){
        notice.hidden=false;
        notice.className='nc-notice error';
        notice.textContent='\u26a0 '+((err&&err.message)||String(err));
      }
    }
  }

  load();
})();
