/* F&O ₹1 Play Desk — renders fno-play.json (v2: ₹1 Zones, 20 signals, ₹6L plan, charts) */
(function () {
  "use strict";
  var D, selected = null, activeFilter = "";

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
  function td(tr, txt, cls) { var c = el("td", cls || null); if (txt != null) c.textContent = txt; tr.appendChild(c); return c; }
  function lk(n) { return n == null ? "—" : "₹" + n.toLocaleString("en-IN"); }
  function pct(n) { return n == null ? "—" : (n > 0 ? "+" : "") + n.toFixed(1) + "%"; }

  function sigBadge(sig, label) {
    return el("span", "sig-badge sig-" + (sig || "wait").replace(/_/g, "-"), label || sig);
  }
  function wrColor(wr) { return wr == null ? "" : wr >= 75 ? "conv-high" : wr >= 60 ? "conv-medium" : "conv-low"; }

  function zoneWr(r) {
    if (r.signal.indexOf("buy") >= 0) return r.zone_buy_wr;
    if (r.signal.indexOf("sell") >= 0) return r.zone_sell_wr;
    return null;
  }
  function zoneN(r) {
    if (r.signal.indexOf("buy") >= 0) return r.zone_buy_n;
    if (r.signal.indexOf("sell") >= 0) return r.zone_sell_n;
    return 0;
  }

  /* ── Stats hero ──────────────────────────────────────── */
  function renderStats() {
    var sc = D.signal_counts || {};
    var buys  = (sc.buy_strong || 0) + (sc.buy || 0);
    var sells = (sc.sell_strong || 0) + (sc.sell || 0);
    var waits = (sc.wait || 0) + (sc.watch_buy || 0) + (sc.watch_sell || 0);
    $("vix-val").textContent = D.vix ? D.vix.toFixed(1) : "—";
    $("buy-n").textContent   = buys;
    $("sell-n").textContent  = sells;
    $("wait-n").textContent  = waits;
    $("avoid-n").textContent = sc.avoid || 0;
    $("cov-n").textContent   = D.covered || 0;
    var vix = D.vix || 15;
    $("vix-val").style.color = vix < 15 ? "#16a34a" : vix < 20 ? "#d97706" : "#dc2626";

    var b = $("fno-banner"); b.className = "fd-banner open";
    var now = new Date();
    b.textContent = "Updated " + D.as_of + " · VIX " + (D.vix ? D.vix.toFixed(1) : "—") +
      (vix > 20 ? " ⚠ High VIX — reduce size" : "") +
      " · This page is designed to refresh every 15 minutes during market hours (09:15–15:30 IST).";

    ["method-list","rules-list","limits-list"].forEach(function (id) {
      var key = id === "method-list" ? "method" : id === "rules-list" ? "rules" : "limits";
      var e2 = $(id); if (!e2) return; e2.textContent = "";
      var ul = el("ul"); (D[key] || []).forEach(function (s) { ul.appendChild(el("li", null, s)); }); e2.appendChild(ul);
    });
    $("picks-sub").textContent = (D.top_picks || []).length + " plays";
    $("all-sub").textContent   = D.covered + " F&O stocks";
  }

  /* ── ₹6 lakh Monday plan ─────────────────────────────── */
  function renderPlan() {
    var wrap = $("plan-body"); if (!wrap) return;
    wrap.textContent = "";
    var plan = D.rs6l_plan || [];
    if (!plan.length) { wrap.appendChild(el("p", "fd-note", "No high-conviction BUY plays today — wait for a better setup.")); return; }
    var totalCap = 0, totalPnl = 0;
    plan.forEach(function (p) {
      totalCap += p.capital; totalPnl += p.rs1_pnl;
      var card = el("div", "plan-card");
      var head = el("div", "plan-card-head");
      head.appendChild(el("strong", null, p.symbol));
      head.appendChild(sigBadge("buy", "🟢 BUY"));
      card.appendChild(head);
      card.appendChild(el("div", "plan-card-name", p.name));
      var rows = [
        ["Buy zone (entry)", lk(p.entry_zone)],
        ["Target (+₹1)", lk(p.target)],
        ["Stop (−₹1)", lk(p.stop)],
        ["Lots × size", p.lots + " × " + p.lot_size + " = " + (p.lots * p.lot_size).toLocaleString("en-IN") + " shares"],
        ["Capital (margin)", lk(p.capital)],
        ["₹1 profit", lk(p.rs1_pnl)],
        ["Zone win rate", (p.zone_buy_wr != null ? p.zone_buy_wr + "% (" + p.zone_buy_n + " samples)" : "thin data")],
        ["20-signal score", (p.twenty_score != null ? p.twenty_score + "/20" : "—") + " · RSI " + (p.rsi != null ? p.rsi : "—")],
      ];
      rows.forEach(function (rw) {
        var d = el("div", "plan-row");
        d.appendChild(el("span", null, rw[0]));
        d.appendChild(el("b", null, String(rw[1])));
        card.appendChild(d);
      });
      if (p.why && p.why.length) {
        card.appendChild(el("div", "plan-why", "Zone = " + p.why.join(" + ")));
      }
      wrap.appendChild(card);
    });
    var summ = $("plan-summary");
    if (summ) {
      summ.textContent = "";
      summ.appendChild(el("strong", null, "₹6L deployed across " + plan.length + " stocks: ₹" + totalCap.toLocaleString("en-IN") + " margin used · ₹" + totalPnl.toLocaleString("en-IN") + " profit per ₹1 move (all hit = one green day)."));
    }
  }

  /* ── Top picks table ─────────────────────────────────── */
  function renderPicks() {
    var body = $("picks-body"); body.textContent = "";
    (D.top_picks || []).forEach(function (r, i) {
      var tr = el("tr");
      td(tr, String(i + 1));
      var s = td(tr, null, "fd-sym"); s.appendChild(el("strong", null, r.symbol));
      s.appendChild(document.createTextNode(" " + (r.name || "").split(" ").slice(0, 2).join(" ")));
      var bc = td(tr, null); bc.appendChild(sigBadge(r.signal, r.signal_label));
      td(tr, (r.twenty_score != null ? r.twenty_score + "/20" : "—"), "num");
      td(tr, r.adr20 ? r.adr20.toFixed(1) : "—", "num");
      td(tr, r.adr_vs_rs1 ? r.adr_vs_rs1.toFixed(0) + "×" : "—", "num");
      td(tr, r.close ? r.close.toLocaleString("en-IN") : "—", "num");
      td(tr, String(r.rs1_per_lot || r.lot_size), "num");
      var wr = zoneWr(r);
      td(tr, wr != null ? wr.toFixed(0) + "% (" + zoneN(r) + ")" : "—", "num " + wrColor(wr));
      var ac = td(tr, null); ac.style.fontSize = ".76rem"; ac.style.maxWidth = "240px"; ac.textContent = r.action || "—";
      tr.addEventListener("click", function () { showDetail(r.symbol); });
      body.appendChild(tr);
    });
  }

  /* ── Capital calculator ──────────────────────────────── */
  function renderCalc(capital) {
    var out = $("calc-out"); out.textContent = "";
    var grid = el("div", "fno-calc-grid");
    var picks = (D.top_picks || []).filter(function (r) { return r.signal.indexOf("buy") >= 0; }).slice(0, 6);
    picks.forEach(function (r) {
      var margin = Math.round(r.close * r.lot_size * 0.175);
      var lots = margin > 0 ? Math.floor(capital / margin) : 0;
      var card = el("div", "fno-calc-card");
      card.appendChild(el("strong", null, r.symbol + "  " + (r.signal_label || "")));
      [["Lot size", r.lot_size + " sh"], ["₹1 / lot", "₹" + r.lot_size],
       ["Margin / lot", "₹" + margin.toLocaleString("en-IN")],
       ["Max lots", lots], ["₹1 daily P&L", "₹" + (lots * r.lot_size).toLocaleString("en-IN")]
      ].forEach(function (rw) {
        var d = document.createElement("div"); d.style.display = "flex"; d.style.justifyContent = "space-between";
        d.appendChild(el("span", null, rw[0])); d.appendChild(el("b", null, String(rw[1]))); card.appendChild(d);
      });
      grid.appendChild(card);
    });
    out.appendChild(grid);
  }

  /* ── All stocks table ────────────────────────────────── */
  function setFilter(f) {
    activeFilter = f;
    document.querySelectorAll(".dma-filter").forEach(function (b) { b.classList.toggle("active", b.dataset.filter === f); });
    renderAll();
  }
  function renderAll() {
    var body = $("all-body"); body.textContent = "";
    var f = activeFilter;
    var rows = D.rows || [];
    var shown = f ? rows.filter(function (r) { return f.split(",").indexOf(r.signal) >= 0; }) : rows;
    shown.forEach(function (r) {
      var tr = el("tr");
      td(tr, String(r.rank));
      var s = td(tr, null, "fd-sym"); s.appendChild(el("strong", null, r.symbol));
      var bc = td(tr, null); bc.appendChild(sigBadge(r.signal, r.signal_label));
      td(tr, (r.twenty_score != null ? r.twenty_score + "/20" : "—"), "num");
      td(tr, (r.rsi != null ? r.rsi.toFixed(0) : "—"), "num");
      td(tr, r.adr_vs_rs1 ? r.adr_vs_rs1.toFixed(0) + "×" : "—", "num");
      td(tr, r.close ? r.close.toLocaleString("en-IN") : "—", "num");
      td(tr, r.change_pct != null ? pct(r.change_pct) : "—", "num " + (r.change_pct > 0 ? "bull" : r.change_pct < 0 ? "bear" : ""));
      td(tr, String(r.rs1_per_lot || r.lot_size), "num");
      var wr = zoneWr(r);
      td(tr, wr != null ? wr.toFixed(0) + "%" : "—", "num " + wrColor(wr));
      tr.addEventListener("click", function () { showDetail(r.symbol); });
      body.appendChild(tr);
    });
  }

  /* ── ₹1 Zone chart (SVG) ─────────────────────────────── */
  function renderZoneChart(r, container) {
    container.textContent = "";
    var h = r.history;
    if (!h || !h.closes || h.closes.length < 5 || typeof VLChart === "undefined") { container.textContent = "No price history."; return; }
    var zones = [];
    (r.buy_zones || []).forEach(function (z) { zones.push({price: z.price, color: "#16a34a", label: "BUY ₹" + z.price + (z.strength > 1 ? " ×" + z.strength : "")}); });
    (r.sell_zones || []).forEach(function (z) { zones.push({price: z.price, color: "#dc2626", label: "SELL ₹" + z.price + (z.strength > 1 ? " ×" + z.strength : "")}); });
    VLChart.render(container, {
      title: r.symbol + " daily candles + ₹1 Zones",
      bars: VLChart.barsFromArrays(h),
      overlays: [
        {values: h.dma20, color: "#3B82F6", width: 1.3, label: "20"},
        {values: h.dma50, color: "#F59E0B", width: 1.3, label: "50"}
      ],
      zones: zones
    });
  }

  /* ── Detail panel ────────────────────────────────────── */
  function showDetail(sym) {
    var r = (D.rows || []).find(function (x) { return x.symbol === sym; });
    if (!r) return;
    selected = sym;
    $("fd-title").textContent = r.symbol;
    $("fd-name").textContent = (r.name || "") + " · Lot " + r.lot_size + " · ₹1/lot = ₹" + r.lot_size + " · RSI " + (r.rsi != null ? r.rsi : "—");
    var dc = $("fd-signal-row"); dc.textContent = "";
    dc.appendChild(sigBadge(r.signal, r.signal_label));
    dc.appendChild(document.createTextNode("  " + (r.twenty_score != null ? r.twenty_score + "/20 signals" : "")));

    $("fd-action-text").textContent = r.action || "—";

    // Chart with zones
    var ch = $("fd-chart"); if (ch) renderZoneChart(r, ch);

    // Zones table
    var zb = $("fd-zones"); if (zb) {
      zb.textContent = "";
      var mkZone = function (z, kind) {
        var row = el("div", "dma-sr-row");
        row.appendChild(el("span", "dma-sr-label " + (kind === "buy" ? "fno-sr-s" : "fno-sr-r"), (kind === "buy" ? "BUY " : "SELL ") + "₹" + z.price));
        row.appendChild(el("span", "dma-sr-val", z.levels.join(" + ")));
        row.appendChild(el("span", "dma-sr-pct " + (kind === "buy" ? "sup" : "res"), (z.dist_pct > 0 ? "+" : "") + z.dist_pct + "% · ×" + z.strength));
        return row;
      };
      zb.appendChild(el("div", "fd-note", "▼ BUY zones (support — expect ₹1 bounce)"));
      (r.buy_zones || []).forEach(function (z) { zb.appendChild(mkZone(z, "buy")); });
      zb.appendChild(el("div", "fd-note", "▲ SELL zones (resistance — expect ₹1 drop)"));
      (r.sell_zones || []).forEach(function (z) { zb.appendChild(mkZone(z, "sell")); });
    }

    // Zone backtest
    var bt = $("fd-zonebt"); if (bt) {
      bt.textContent = "";
      [["Support-zone BUY → ₹1 up in 2 sessions", r.zone_buy_wr, r.zone_buy_n],
       ["Resistance-zone SELL → ₹1 down in 2 sessions", r.zone_sell_wr, r.zone_sell_n]
      ].forEach(function (rw) {
        var d = el("div", "dma-bt-row");
        d.appendChild(el("span", null, rw[0] + ":"));
        d.appendChild(el("b", wrColor(rw[1]), rw[1] != null ? rw[1] + "% (" + rw[2] + " samples)" : (rw[2] + " samples — too thin")));
        bt.appendChild(d);
      });
    }

    // 20 signals
    var sg = $("fd-signals"); if (sg) {
      sg.textContent = "";
      var grid = el("div", "fno-sig-grid");
      (r.twenty_signals || []).forEach(function (s) {
        var chip = el("span", "fno-sig-chip " + (s[1] ? "on" : "off"), (s[1] ? "✓ " : "✗ ") + s[0]);
        grid.appendChild(chip);
      });
      sg.appendChild(grid);
    }

    var det = $("fno-detail"); det.removeAttribute("hidden"); det.scrollTop = 0;
  }

  /* ── Boot ────────────────────────────────────────────── */
  function boot() {
    var capInput = $("cap-input");
    if (capInput) {
      capInput.addEventListener("input", function () { renderCalc(parseInt(capInput.value) || 1000000); });
      document.querySelectorAll("[data-cap]").forEach(function (b) {
        b.addEventListener("click", function () { capInput.value = b.dataset.cap; renderCalc(parseInt(b.dataset.cap)); });
      });
    }
    document.querySelectorAll(".dma-filter").forEach(function (b) { b.addEventListener("click", function () { setFilter(b.dataset.filter); }); });
    var fc = $("fd-close"); if (fc) fc.addEventListener("click", function () { $("fno-detail").setAttribute("hidden", ""); selected = null; });

    fetch("fno-play.json?" + Date.now()).then(function (x) { return x.json(); }).then(function (data) {
      D = data;
      renderStats(); renderPlan(); renderPicks();
      if (capInput) renderCalc(parseInt(capInput.value) || 1000000);
      renderAll();
    }).catch(function (e) {
      var b = $("fno-banner"); if (b) { b.className = "fd-banner open"; b.textContent = "Failed to load: " + e; }
    });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
