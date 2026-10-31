/* Value Lens DMA Intelligence Desk — renders docs/dma.json */
/* jshint esversion:6 */
(function () {
  "use strict";
  var D, selected = null, activeFilter = "";

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function td(tr, text, cls) {
    var c = el("td", cls || null);
    if (text != null) c.textContent = text;
    tr.appendChild(c);
    return c;
  }
  function inr(n) { return "₹" + Math.round(n || 0).toLocaleString("en-IN"); }
  function pct(n, dec) { return n == null ? "—" : (n > 0 ? "+" : "") + n.toFixed(dec || 1) + "%"; }
  function num(n, dec) { return n == null ? "—" : n.toFixed(dec || 0); }
  function lk(n) { return n == null ? "—" : "₹" + n.toLocaleString("en-IN"); }

  var CROSS_LABELS = {
    platinum: "🏆 Platinum", golden: "🥇 Golden", silver: "🥈 Silver",
    bronze: "🥉 Bronze", watch: "👀 Watch", neutral: "➡️ Neutral",
    bear: "📉 Bear", death: "💀 Death"
  };

  function crossBadge(type) {
    return el("span", "dma-badge dma-" + (type || "neutral"), CROSS_LABELS[type] || type || "—");
  }

  function dmaBar(row) {
    var levels = [
      ["200", row.dma200, row.close > row.dma200],
      ["100", row.dma100, row.close > row.dma100],
      ["50",  row.dma50,  row.close > row.dma50],
      ["20",  row.dma20,  row.close > row.dma20],
    ];
    var bar = el("span", "dma-bar");
    levels.forEach(function (L) {
      bar.appendChild(el("span", "dma-dot " + (L[1] && L[2] ? "on" : L[1] ? "off" : "off"), L[0]));
    });
    return bar;
  }

  function scoreBar(score) {
    var w = el("div", "fd-wbar"); var bar = el("i"); var fill = el("b");
    fill.style.width = Math.min(100, score) + "%"; bar.appendChild(fill); w.appendChild(bar);
    w.appendChild(el("strong", null, score + "/100"));
    return w;
  }

  /* ── Crossover summary ─────────────────────────────────── */
  function renderSummary() {
    var cs = D.crossover_summary || {};
    ["platinum","golden","silver","bronze","watch","bear"].forEach(function (t) {
      var el2 = $("cn-" + t);
      if (el2) el2.textContent = cs[t] != null ? cs[t] : "—";
    });
    // Banner
    var p = D.portfolio || {};
    var b = $("dma-banner");
    b.className = "fd-banner " + (p.guard_on ? "open" : "");
    b.textContent = p.guard_words || "";
    $("p-sub").textContent = D.as_of + " · " + (p.holdings_count || 0) + " stocks · " + D.covered + " scored";
    $("all-sub").textContent = D.covered + " Nifty 500 stocks";

    // Score method
    var sm = $("score-method");
    if (sm) {
      var ol = el("ol");
      (D.score_method || []).forEach(function (s) { ol.appendChild(el("li", null, s)); });
      sm.appendChild(ol);
    }
    var rl = $("rules-list");
    if (rl) {
      var ul = el("ul");
      (D.rules || []).concat(D.limits || []).forEach(function (s) { ul.appendChild(el("li", null, s)); });
      rl.appendChild(ul);
    }

    // Click on summary tiles to filter
    Object.keys(CROSS_LABELS).forEach(function (t) {
      var tile = $("ct-" + t);
      if (tile) {
        tile.addEventListener("click", function () {
          setFilter(activeFilter === t ? "" : t);
        });
      }
    });
  }

  /* ── Portfolio table ───────────────────────────────────── */
  function renderPortfolio(sip) {
    var body = $("port-body");
    body.textContent = "";
    var holdings = D.holdings || [];
    var used = 0;
    holdings.forEach(function (h) {
      var tr = el("tr");
      tr.setAttribute("aria-selected", selected === h.symbol ? "true" : "false");
      var rupees = sip * (h.weight_pct || 0) / 100;
      var shares = h.close ? Math.floor(rupees / h.close) : h.shares || 0;
      used += shares * (h.close || 0);

      td(tr, String(h.rank));
      var sc = td(tr, null, "fd-sym"); sc.appendChild(el("strong", null, h.symbol));
      sc.appendChild(document.createTextNode(" " + (h.name || "").split(" ").slice(0, 3).join(" ")));

      var bc = td(tr, null); bc.appendChild(crossBadge(h.crossover_type));
      var wc = td(tr, null, "num"); wc.appendChild(scoreBar(h.total_score || 0));

      var wb = td(tr, null, "num");
      var wbw = el("div", "fd-wbar"); var wbar = el("i"); var wfill = el("b");
      wfill.style.width = Math.min(100, (h.weight_pct || 0) / 6 * 100) + "%";
      wbar.appendChild(wfill); wbw.appendChild(wbar);
      wbw.appendChild(el("strong", null, (h.weight_pct || 0).toFixed(2) + "%"));
      wb.appendChild(wbw);

      td(tr, inr(rupees), "num");
      td(tr, String(shares), "num");
      td(tr, (h.close || 0).toLocaleString("en-IN"), "num");
      td(tr, h.pct_above_200 != null ? pct(h.pct_above_200) : "—", "num " + (h.pct_above_200 > 0 ? "bull" : "bear"));
      td(tr, h.bt_win_rate_3m != null ? h.bt_win_rate_3m.toFixed(0) + "%" : "—", "num");
      td(tr, h.hhhl_category || "—");
      var dc = td(tr, null); dc.appendChild(dmaBar(h));

      tr.addEventListener("click", function () { showDetail(h.symbol); });
      body.appendChild(tr);
    });

    // Cash row
    var p = D.portfolio || {};
    if (p.cash_pct > 0) {
      var tr2 = el("tr", "cash");
      td(tr2, "—"); td(tr2, "Liquid fund (market guard)"); td(tr2, ""); td(tr2, "");
      td(tr2, null).appendChild((function () { var s = el("strong"); s.textContent = p.cash_pct + "%"; return s; })());
      td(tr2, inr(sip * p.cash_pct / 100), "num"); td(tr2, "—", "num"); td(tr2, "—", "num");
      td(tr2, "—", "num"); td(tr2, "—"); td(tr2, "—");
      body.appendChild(tr2);
    }

    // Footer
    var tf = el("tr"); tf.style.fontWeight = "800";
    td(tf, ""); td(tf, "Total invested in stocks");
    td(tf, ""); td(tf, "");
    td(tf, (p.stock_pct || 0).toFixed(1) + "%", "num");
    td(tf, inr(used), "num");
    for (var i = 0; i < 6; i++) td(tf, "");
    body.appendChild(tf);
  }

  /* ── All-stocks table ──────────────────────────────────── */
  function setFilter(f) {
    activeFilter = f;
    document.querySelectorAll(".dma-filter").forEach(function (btn) {
      btn.classList.toggle("active", btn.dataset.filter === f);
    });
    renderAllStocks();
  }

  function renderAllStocks() {
    var body = $("all-body");
    body.textContent = "";
    var rows = D.rows || [];
    var f = activeFilter;
    var shown = f ? rows.filter(function (r) { return f.split(",").indexOf(r.crossover_type) >= 0; }) : rows;

    $("all-sub").textContent = D.covered + " Nifty 500 stocks" + (f ? " — " + CROSS_LABELS[f] || f : "");

    shown.forEach(function (r) {
      var tr = el("tr");
      tr.setAttribute("aria-selected", selected === r.symbol ? "true" : "false");

      td(tr, String(r.rank));
      var sc = td(tr, null, "fd-sym"); sc.appendChild(el("strong", null, r.symbol));
      td(tr, (r.sector || "").split(" ").slice(0, 2).join(" "));
      var bc = td(tr, null); bc.appendChild(crossBadge(r.crossover_type));
      td(tr, String(r.total_score || 0), "num");
      td(tr, String(r.align_score || 0), "num");
      td(tr, r.close ? r.close.toLocaleString("en-IN") : "—", "num");
      td(tr, r.pct_above_200 != null ? pct(r.pct_above_200) : "—",
             "num " + (r.pct_above_200 != null ? (r.pct_above_200 > 0 ? "bull" : "bear") : ""));
      td(tr, r.bt_win_rate_3m != null ? r.bt_win_rate_3m.toFixed(0) + "%" : "—", "num");
      td(tr, r.bt_events > 0 ? String(r.bt_events) : "—", "num");
      td(tr, r.hhhl_category || "—");
      var dc = td(tr, null); dc.appendChild(dmaBar(r));

      tr.addEventListener("click", function () { showDetail(r.symbol); });
      body.appendChild(tr);
    });
  }

  /* ── Detail panel ─────────────────────────────────────── */
  function showDetail(sym) {
    var r = (D.rows || []).find(function (x) { return x.symbol === sym; }) ||
            (D.holdings || []).find(function (x) { return x.symbol === sym; });
    if (!r) return;
    selected = sym;

    // Update aria-selected on both tables
    document.querySelectorAll("#port-body tr, #all-body tr").forEach(function (tr) {
      var strong = tr.querySelector("strong");
      tr.setAttribute("aria-selected", strong && strong.textContent === sym ? "true" : "false");
    });

    $("d-title").textContent = r.symbol + " · " + (r.name || "");
    $("d-sector").textContent = (r.sector || "") + (r.hhhl_category ? " · HHHL: " + r.hhhl_category : "");
    var dc = $("d-cross-row"); dc.textContent = "";
    dc.appendChild(crossBadge(r.crossover_type));
    dc.appendChild(document.createTextNode("  Score " + (r.total_score || 0) + "/100"));

    // S&R block
    var sr = $("d-sr"); sr.textContent = "";
    var close = r.close || 0;
    var levels = [
      ["20-DMA", r.dma20], ["50-DMA", r.dma50], ["100-DMA", r.dma100], ["200-DMA", r.dma200]
    ].filter(function (L) { return L[1] != null; });

    var res_levels = levels.filter(function (L) { return L[1] > close; })
                           .sort(function (a,b) { return a[1]-b[1]; });  // nearest first
    var sup_levels = levels.filter(function (L) { return L[1] <= close; })
                           .sort(function (a,b) { return b[1]-a[1]; });  // nearest first

    var h4 = el("h4"); h4.textContent = "DMA Support / Resistance"; sr.appendChild(h4);

    if (res_levels.length) {
      sr.appendChild(el("div", "fd-note", "▲ RESISTANCE (above close)"));
      res_levels.forEach(function (L) {
        var row2 = el("div", "dma-sr-row");
        row2.appendChild(el("span", "dma-sr-label", L[0]));
        row2.appendChild(el("span", "dma-sr-val", lk(L[1])));
        var pctv = ((L[1] / close - 1) * 100).toFixed(1);
        row2.appendChild(el("span", "dma-sr-pct res", "+" + pctv + "% away"));
        sr.appendChild(row2);
      });
    } else {
      sr.appendChild(el("div", "fd-note", "▲ No resistance — all DMAs below close"));
    }

    var clDiv = el("div", "dma-sr-close");
    clDiv.textContent = "CLOSE  " + lk(close);
    sr.appendChild(clDiv);

    if (sup_levels.length) {
      sr.appendChild(el("div", "fd-note", "▼ SUPPORT (below close)"));
      sup_levels.forEach(function (L) {
        var row2 = el("div", "dma-sr-row");
        row2.appendChild(el("span", "dma-sr-label", L[0]));
        row2.appendChild(el("span", "dma-sr-val", lk(L[1])));
        var pctv = ((L[1] / close - 1) * 100).toFixed(1);
        row2.appendChild(el("span", "dma-sr-pct sup", pctv + "% below"));
        sr.appendChild(row2);
      });
    } else {
      sr.appendChild(el("div", "fd-note", "▼ Price below all DMAs — no DMA support"));
    }

    // Backtest
    var bt = $("d-bt"); bt.textContent = "";
    var bth = el("h4"); bth.textContent = "Backtest — Golden Cross (" + (r.bt_events || 0) + " events)"; bt.appendChild(bth);
    if ((r.bt_events || 0) < 5) {
      bt.appendChild(el("p", "fd-note", "Fewer than 5 golden crosses in history — backtest score is neutral."));
    } else {
      [["3-Month", r.bt_win_rate_3m, r.bt_avg_ret_3m], ["6-Month", r.bt_win_rate_6m, r.bt_avg_ret_6m]]
        .forEach(function (row2) {
          var d2 = el("div", "dma-bt-row");
          d2.appendChild(el("span", null, row2[0] + ":"));
          d2.appendChild(el("b", null, row2[1] != null ? row2[1].toFixed(1) + "% win rate" : "—"));
          d2.appendChild(document.createTextNode(" · avg "));
          d2.appendChild(el("b", null, row2[2] != null ? pct(row2[2]) : "—"));
          bt.appendChild(d2);
        });
    }

    // Score breakdown
    var sc2 = $("d-score"); sc2.textContent = "";
    var sch = el("h4"); sch.textContent = "Score breakdown"; sc2.appendChild(sch);
    [
      ["DMA alignment (0–35)", r.align_score],
      ["Crossover recency (0–25)", r.cross_score],
      ["HHHL trend (0–20)", r.hhhl_score],
      ["Backtest (0–20)", r.bt_score_pts],
      ["Total", r.total_score],
    ].forEach(function (row2) {
      var d2 = el("div", "dma-score-row");
      d2.appendChild(el("span", null, row2[0]));
      d2.appendChild(el("b", null, row2[1] != null ? String(row2[1]) : "—"));
      sc2.appendChild(d2);
    });

    var chartCont = $("d-chart"); if (chartCont) renderDmaChart(r, chartCont);
    var btCont = $("d-bt-full"); if (btCont) renderBtByType(r, btCont);
    var allocCont = $("d-alloc"); if (allocCont) renderAlloc(r, allocCont);
    var det = $("dma-detail");
    det.removeAttribute("hidden");
    det.scrollTop = 0;
  }

  /* ── Boot ─────────────────────────────────────────────── */
  function boot() {
    var sipInput = $("sip-amt");
    var getSip = function () { return parseInt(sipInput.value) || 1000000; };

    sipInput.addEventListener("input", function () { renderPortfolio(getSip()); });
    document.querySelectorAll("[data-amt]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        sipInput.value = btn.dataset.amt;
        renderPortfolio(getSip());
      });
    });

    document.querySelectorAll(".dma-filter").forEach(function (btn) {
      btn.addEventListener("click", function () { setFilter(btn.dataset.filter); });
    });

    $("d-close").addEventListener("click", function () {
      $("dma-detail").setAttribute("hidden", "");
      selected = null;
    });

    // Tile clicks filter by type
    ["platinum","golden","silver","bronze","watch","bear"].forEach(function (t) {
      var tile = $("ct-" + t);
      if (tile) tile.addEventListener("click", function () {
        setFilter(activeFilter === t ? "" : t);
      });
    });

    fetch("dma.json?" + Date.now())
      .then(function (r) { return r.json(); })
      .then(function (data) {
        D = data;
        renderSummary();
        renderPortfolio(getSip());
        renderAllStocks();
      })
      .catch(function (e) {
        var b = $("dma-banner");
        b.className = "fd-banner open";
        b.textContent = "Failed to load DMA data: " + e;
      });
  }


  /* ── SVG price + DMA chart ──────────────────────────────── */
  function renderDmaChart(r, container) {
    container.textContent = "";
    var hist = r.history;
    if (!hist || !hist.closes || hist.closes.length < 5 || typeof VLChart === "undefined") {
      container.textContent = "No price history."; return;
    }
    var MC = {platinum:'#b8860b',golden:'#F59E0B',silver:'#9CA3AF',bronze:'#CD7F32',death:'#EF4444',bear:'#EF4444',silver_:'#9CA3AF'};
    var markers = (r.crossover_events || []).map(function (ev) {
      return {date: ev.date, price: ev.close, color: MC[ev.type] || '#6b7280',
              label: ev.type + ' @ ' + ev.close + ' on ' + ev.date,
              down: (ev.type === 'death' || ev.type === 'bear')};
    });
    VLChart.render(container, {
      title: r.symbol + " daily candles + DMAs",
      bars: VLChart.barsFromArrays(hist),
      overlays: [
        {values: hist.dma20,  color: '#3B82F6', width: 1.3, label: '20'},
        {values: hist.dma50,  color: '#F59E0B', width: 1.3, label: '50'},
        {values: hist.dma100, color: '#8B5CF6', width: 1.3, label: '100'},
        {values: hist.dma200, color: '#EF4444', width: 1.8, label: '200'}
      ],
      markers: markers
    });
  }

  /* ── Backtest-by-type table ──────────────────────────────── */
  function renderBtByType(r, container) {
    container.textContent = "";
    var bt = r.bt_by_type || {};
    if (!Object.keys(bt).length) { container.textContent = "No backtest data."; return; }
    var tbl = el("table","fd-table"); tbl.style.fontSize=".78rem"; tbl.style.width="100%";
    var thead=el("thead"); var hr=el("tr");
    ["Type","#","1M win","1M avg","3M win","3M avg","6M win","6M avg","1Y win","1Y avg"].forEach(function(h){
      var th=el("th"); th.textContent=h; hr.appendChild(th);
    });
    thead.appendChild(hr); tbl.appendChild(thead);
    var tbody=el("tbody");
    var ORDER=["platinum","golden","silver","bronze","death"];
    ORDER.forEach(function(ct){
      var d=bt[ct]; if(!d)return;
      var tr=el("tr"); 
      var bc=el("td"); bc.appendChild(crossBadge(ct,null)); tr.appendChild(bc);
      [d.n,
       d.win_1m!=null?d.win_1m+'%':'—', d.avg_1m!=null?(d.avg_1m>0?'+':'')+d.avg_1m+'%':'—',
       d.win_3m!=null?d.win_3m+'%':'—', d.avg_3m!=null?(d.avg_3m>0?'+':'')+d.avg_3m+'%':'—',
       d.win_6m!=null?d.win_6m+'%':'—', d.avg_6m!=null?(d.avg_6m>0?'+':'')+d.avg_6m+'%':'—',
       d.win_1y!=null?d.win_1y+'%':'—', d.avg_1y!=null?(d.avg_1y>0?'+':'')+d.avg_1y+'%':'—',
      ].forEach(function(v,i){
        var td2=el("td","num"); td2.textContent=String(v);
        if(i>0&&String(v).charAt(0)==='+') td2.className='num bull';
        if(i>0&&String(v).charAt(0)==='-') td2.className='num bear';
        tr.appendChild(td2);
      });
      tbody.appendChild(tr);
    });
    tbl.appendChild(tbody); container.appendChild(tbl);
  }

  /* ── Rs10L DMA fund allocation ──────────────────────────── */
  function renderAlloc(r, container) {
    container.textContent = "";
    var alloc = {platinum:0.30, golden:0.25, silver:0.15, bronze:0.10, watch:0.05, neutral:0, bear:0, death:0};
    var pct = alloc[r.crossover_type] || 0;
    if (!pct) { container.textContent = "No allocation — not an investable signal today."; return; }
    var sip = 1000000;
    var amt = sip * pct;
    var lot = r.lot_size || 1;
    var close = r.close || 1;
    var lot_val = lot * close;
    var margin = Math.round(lot_val * 0.175);
    var max_lots = margin > 0 ? Math.floor(amt / margin) : 0;
    var rows2 = [
      ["Signal type", r.crossover_type + " → " + (pct*100).toFixed(0) + "% of ₹10L"],
      ["Amount to deploy", "₹" + Math.round(amt).toLocaleString("en-IN")],
      ["NSE lot size", lot + " shares"],
      ["Margin per lot (≈17.5%)", "₹" + margin.toLocaleString("en-IN")],
      ["Max lots with this amount", max_lots],
      ["₹1 P&L at max lots", "₹" + (max_lots * lot).toLocaleString("en-IN")],
    ];
    var optAmt = Math.round(close * lot * 0.015);
    if (r.crossover_type !== 'death' && r.crossover_type !== 'bear') {
      rows2.push(["OPTIONS alt: ATM Call (1 lot est.)", "₹" + optAmt.toLocaleString("en-IN") + " premium"]);
      rows2.push(["Option upside if +5% move", "₹" + Math.round(optAmt * 2.5).toLocaleString("en-IN")]);
    }
    rows2.forEach(function(row2){
      var d2=el("div","dma-score-row");
      d2.appendChild(el("span",null,row2[0]));
      d2.appendChild(el("b",null,String(row2[1])));
      container.appendChild(d2);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
