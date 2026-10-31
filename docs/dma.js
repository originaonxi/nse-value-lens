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

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
