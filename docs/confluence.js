/* Confluence Top Picks — renders confluence.json with VLChart candlesticks */
(function () {
  'use strict';

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }

  function lk(n) { return n == null ? '—' : '₹' + n.toLocaleString('en-IN'); }

  /* ── Signal row ───────────────────────────────────────── */
  function renderSignal(sig) {
    var v = sig.vote, row = el('div', 'cf-sig-row ' + (v > 0 ? 'bull' : v < 0 ? 'bear' : 'neut'));
    row.appendChild(el('span', 'cf-sig-icon', v > 0 ? '✅' : v < 0 ? '❌' : '➡️'));
    row.appendChild(el('span', 'cf-sig-name', sig.system));
    var det = el('span', 'cf-sig-detail');
    det.textContent = ' — ' + (sig.detail || '');
    row.appendChild(det);
    return row;
  }

  /* ── Vote badge ───────────────────────────────────────── */
  function voteBadge(net, n, side) {
    var div = el('div', 'cf-vote ' + side);
    div.appendChild(el('span', 'cf-vote-num', (net > 0 ? '+' : '') + net));
    div.appendChild(el('span', 'cf-vote-den', '/ ' + n + ' systems'));
    return div;
  }

  /* ── Stock card ───────────────────────────────────────── */
  function renderCard(s, container) {
    var side = s.side; // 'buy' | 'sell'
    var card = el('div', 'cf-card');

    // ── Head
    var head = el('div', 'cf-card-head');
    head.appendChild(voteBadge(s.net, s.n_sys, side === 'buy' ? 'bull' : 'bear'));
    var titleBlock = el('div', 'cf-card-title');
    titleBlock.appendChild(el('h3', null, s.symbol));
    titleBlock.appendChild(el('div', 'cf-name', s.name || ''));
    var metaRow = el('div', 'cf-card-meta');
    var agreeChip = el('span', 'cf-pill ' + (side === 'buy' ? 'cf-pill-buy' : 'cf-pill-sell'),
      s.agree_pct + '% agree  —  ' + (side === 'buy' ? '🟢 BUY' : '🔴 SELL'));
    metaRow.appendChild(agreeChip);
    if (s.adr != null) metaRow.appendChild(el('span', 'cf-pill cf-pill-neu', 'ADR ₹' + s.adr));
    if (s.div_yield > 0) metaRow.appendChild(el('span', 'cf-pill cf-pill-neu', 'Div ' + s.div_yield + '%'));
    titleBlock.appendChild(metaRow);
    head.appendChild(titleBlock);
    head.appendChild(el('div', 'cf-close-price', lk(s.close)));
    card.appendChild(head);

    // ── Chart
    var chartArea = el('div', 'cf-chart-area');
    var chartId = 'chart-' + s.symbol;
    chartArea.id = chartId;
    card.appendChild(chartArea);

    // ── Signals grid
    var sigWrap = el('div', 'cf-signals');
    var grid = el('div', 'cf-signals-grid');
    (s.signals || []).forEach(function (sig) { grid.appendChild(renderSignal(sig)); });
    sigWrap.appendChild(grid);
    card.appendChild(sigWrap);

    // ── Action bar
    var act = s.action || {};
    var actionBar = el('div', 'cf-action');
    if (act.entry != null) {
      var lab = side === 'buy' ? 'Entry' : 'Sell at';
      actionBar.appendChild(el('span', null, lab + ': '));
      actionBar.appendChild(el('strong', null, lk(act.entry)));
    }
    if (act.stop != null) {
      actionBar.appendChild(el('span', null, '  Stop: '));
      actionBar.appendChild(el('strong', side === 'buy' ? 'bear' : 'bull', lk(act.stop)));
    }
    if (act.why) {
      var why = el('div', 'cf-why'); why.textContent = '📌 ' + act.why; actionBar.appendChild(why);
    }
    card.appendChild(actionBar);

    container.appendChild(card);

    // ── Render chart after DOM insertion (VLChart needs element in document)
    setTimeout(function () {
      var hist = s.history;
      if (!hist || !hist.closes || !hist.closes.length || typeof VLChart === 'undefined') return;
      var bars = VLChart.barsFromArrays(hist);
      var overlays = [];
      if (hist.dma20)  overlays.push({values: hist.dma20,  color: '#3B82F6', width: 1.3, label: '20-DMA'});
      if (hist.dma50)  overlays.push({values: hist.dma50,  color: '#F59E0B', width: 1.3, label: '50-DMA'});
      if (hist.dma200) overlays.push({values: hist.dma200, color: '#EF4444', width: 2.0, label: '200-DMA'});
      var zones = (s.levels || []).map(function (lev) {
        return {price: lev.price, color: lev.color, label: lev.label};
      });
      VLChart.render(chartArea, {
        title: s.symbol + ' — ' + (side === 'buy' ? 'BUY' : 'SELL') + ' confluence',
        bars: bars, overlays: overlays, zones: zones
      });
    }, 0);
  }

  /* ── Boot ─────────────────────────────────────────────── */
  function boot() {
    fetch('confluence.json?' + Date.now())
      .then(function (r) { return r.json(); })
      .then(function (D) {
        // Header stats
        $('cf-date').textContent   = D.as_of || '—';
        $('cf-scored').textContent = D.scored || '—';
        $('cf-ubull').textContent  = D.unanimous_bull || '—';
        $('cf-ubear').textContent  = D.unanimous_bear || '—';

        var b = $('cf-banner');
        b.className = 'fd-banner';
        b.textContent = D.as_of + ' · ' + D.scored + ' Nifty 200 stocks scored across ' + D.systems + ' independent systems.';

        // Method list
        var ml = $('cf-systems-list'); if (ml) {
          var ol = el('ol');
          (D.systems_list || []).forEach(function (s2) { ol.appendChild(el('li', null, s2)); });
          ml.appendChild(ol);
        }
        var mn = $('cf-method-note'); if (mn && D.method_note) mn.textContent = D.method_note;

        // Buy + sell
        var buyStocks  = (D.stocks || []).filter(function (s2) { return s2.side === 'buy'; });
        var sellStocks = (D.stocks || []).filter(function (s2) { return s2.side === 'sell'; });
        $('cf-buy-sub').textContent  = buyStocks.length  + ' stocks, ranked by unanimity';
        $('cf-sell-sub').textContent = sellStocks.length + ' stocks, ranked by unanimity';

        var buyList  = $('cf-buy-list');
        var sellList = $('cf-sell-list');
        buyStocks.forEach(function (s2)  { renderCard(s2, buyList);  });
        sellStocks.forEach(function (s2) { renderCard(s2, sellList); });
      })
      .catch(function (e) {
        var b = $('cf-banner'); b.className = 'fd-banner open'; b.textContent = 'Failed to load: ' + e;
      });
  }

  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', boot) : boot();
})();
