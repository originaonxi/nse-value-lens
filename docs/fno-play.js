/* F&O ₹1 Play Desk — renders fno-play.json */
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

  function winRateCell(r) {
    var wr = ("buy" in r.signal || r.signal.indexOf("buy") >= 0) ? r.bt_long_wr : r.bt_short_wr;
    if (r.signal.indexOf("buy") >= 0) wr = r.bt_long_wr;
    else if (r.signal.indexOf("sell") >= 0) wr = r.bt_short_wr;
    else wr = null;
    return wr != null ? wr.toFixed(0) + "%" : "—";
  }

  function btTrades(r) {
    if (r.signal.indexOf("buy") >= 0) return r.bt_long_n > 0 ? r.bt_long_n : "—";
    if (r.signal.indexOf("sell") >= 0) return r.bt_short_n > 0 ? r.bt_short_n : "—";
    return "—";
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

    // VIX color
    var vix = D.vix || 15;
    var vc = vix < 15 ? "#16a34a" : vix < 20 ? "#d97706" : "#dc2626";
    $("vix-val").style.color = vc;

    // Banner
    var b = $("fno-banner"); b.className = "fd-banner open";
    b.textContent = D.as_of + " · VIX " + (D.vix ? D.vix.toFixed(1) : "—") +
      (vix > 20 ? " ⚠ High VIX — reduce size or stay out" : " · Market open for ₹1 plays");

    // Method / rules / limits
    ["method-list","rules-list","limits-list"].forEach(function (id) {
      var key = id === "method-list" ? "method" : id === "rules-list" ? "rules" : "limits";
      var el2 = $(id); if (!el2) return;
      var ul = el("ul");
      (D[key] || []).forEach(function (s) { ul.appendChild(el("li", null, s)); });
      el2.appendChild(ul);
    });

    $("picks-sub").textContent = (D.top_picks || []).length + " high-conviction plays";
    $("all-sub").textContent   = D.covered + " F&O stocks";
  }

  /* ── Top picks table ─────────────────────────────────── */
  function renderPicks() {
    var body = $("picks-body"); body.textContent = "";
    (D.top_picks || []).forEach(function (r, i) {
      var tr = el("tr");
      tr.setAttribute("aria-selected", selected === r.symbol ? "true" : "false");
      td(tr, String(i + 1));
      var sc2 = td(tr, null, "fd-sym");
      sc2.appendChild(el("strong", null, r.symbol));
      sc2.appendChild(document.createTextNode(" " + (r.name || "").split(" ").slice(0, 3).join(" ")));

      var bc = td(tr, null); bc.appendChild(sigBadge(r.signal, r.signal_label));
      td(tr, r.adr20 ? r.adr20.toFixed(1) : "—", "num");
      td(tr, r.adr_vs_rs1 ? r.adr_vs_rs1.toFixed(0) + "×" : "—", "num");
      td(tr, r.close ? r.close.toLocaleString("en-IN") : "—", "num");
      td(tr, String(r.rs1_per_lot || r.lot_size), "num");
      td(tr, winRateCell(r), "num");
      td(tr, String(btTrades(r)), "num");

      var ac = td(tr, null);
      ac.style.fontSize = ".78rem";
      ac.style.maxWidth = "260px";
      ac.textContent = r.action || "—";

      tr.addEventListener("click", function () { showDetail(r.symbol); });
      body.appendChild(tr);
    });
  }

  /* ── Capital calculator ──────────────────────────────── */
  function renderCalc(capital) {
    var out = $("calc-out"); out.textContent = "";
    var grid = el("div", "fno-calc-grid");
    var picks = (D.top_picks || []).slice(0, 6);
    if (!picks.length) picks = (D.rows || []).filter(function (r) {
      return r.signal.indexOf("buy") >= 0 || r.signal.indexOf("sell") >= 0;
    }).slice(0, 6);

    picks.forEach(function (r) {
      var margin_est = Math.round(r.close * r.lot_size * 0.175);
      var max_lots   = margin_est > 0 ? Math.floor(capital / margin_est) : 0;
      var daily_rs1  = max_lots * r.lot_size;
      var card = el("div", "fno-calc-card");
      var sig_label = r.signal_label || r.signal;
      card.innerHTML = "";
      card.appendChild(el("strong", null, r.symbol + "  " + sig_label));
      [
        ["Lot size", r.lot_size + " shares"],
        ["₹1 / lot", "₹" + r.lot_size],
        ["~Margin / lot", "₹" + margin_est.toLocaleString("en-IN")],
        ["Max lots (₹" + Math.round(capital/100000) + "L)", max_lots],
        ["₹1 daily P&L", "₹" + daily_rs1.toLocaleString("en-IN")],
      ].forEach(function (row2) {
        var d2 = document.createElement("div"); d2.style.display = "flex"; d2.style.justifyContent = "space-between";
        d2.appendChild(el("span", null, row2[0]));
        d2.appendChild(el("b", null, String(row2[1])));
        card.appendChild(d2);
      });
      grid.appendChild(card);
    });
    out.appendChild(grid);
  }

  /* ── All stocks table ────────────────────────────────── */
  function setFilter(f) {
    activeFilter = f;
    document.querySelectorAll(".dma-filter").forEach(function (btn) {
      btn.classList.toggle("active", btn.dataset.filter === f);
    });
    renderAll();
  }

  function renderAll() {
    var body = $("all-body"); body.textContent = "";
    var rows = D.rows || [];
    var f = activeFilter;
    var shown = f ? rows.filter(function (r) { return f.split(",").indexOf(r.signal) >= 0; }) : rows;

    shown.forEach(function (r) {
      var tr = el("tr");
      tr.setAttribute("aria-selected", selected === r.symbol ? "true" : "false");
      td(tr, String(r.rank));
      var sc2 = td(tr, null, "fd-sym"); sc2.appendChild(el("strong", null, r.symbol));
      var bc = td(tr, null); bc.appendChild(sigBadge(r.signal, r.signal_label));
      td(tr, r.score != null ? r.score.toFixed(2) : "—", "num");
      td(tr, r.adr_vs_rs1 ? r.adr_vs_rs1.toFixed(0) + "×" : "—", "num");
      td(tr, r.close ? r.close.toLocaleString("en-IN") : "—", "num");
      td(tr, r.change_pct != null ? pct(r.change_pct) : "—",
         "num " + (r.change_pct > 0 ? "bull" : r.change_pct < 0 ? "bear" : ""));
      td(tr, String(r.rs1_per_lot || r.lot_size), "num");
      td(tr, winRateCell(r), "num");
      td(tr, r.pivot ? r.pivot.toLocaleString("en-IN") : "—", "num");
      td(tr, r.r1 ? r.r1.toLocaleString("en-IN") : "—", "num");
      td(tr, r.s1 ? r.s1.toLocaleString("en-IN") : "—", "num");
      tr.addEventListener("click", function () { showDetail(r.symbol); });
      body.appendChild(tr);
    });
  }

  /* ── Detail panel ────────────────────────────────────── */
  function showDetail(sym) {
    var r = (D.rows || []).find(function (x) { return x.symbol === sym; });
    if (!r) return;
    selected = sym;
    document.querySelectorAll("#picks-body tr, #all-body tr").forEach(function (tr) {
      var s = tr.querySelector("strong");
      tr.setAttribute("aria-selected", s && s.textContent === sym ? "true" : "false");
    });

    $("fd-title").textContent = r.symbol;
    $("fd-name").textContent  = (r.name || "") + " · Lot " + r.lot_size + " shares · ₹1/lot = ₹" + r.lot_size;

    var dc = $("fd-signal-row"); dc.textContent = "";
    dc.appendChild(sigBadge(r.signal, r.signal_label));
    dc.appendChild(document.createTextNode("  Score " + (r.score > 0 ? "+" : "") + (r.score || 0).toFixed(2)));

    // Action
    $("fd-action-text").textContent = r.action || "—";

    // S&R
    var srb = $("fd-sr-body"); srb.textContent = "";
    var close = r.close || 0;
    var levels = [
      {label:"R2", val: r.r2, cls:"fno-sr-r"},
      {label:"R1", val: r.r1, cls:"fno-sr-r"},
      {label:"Pivot", val: r.pivot, cls:"fno-sr-p"},
      {label:"S1", val: r.s1, cls:"fno-sr-s"},
      {label:"S2", val: r.s2, cls:"fno-sr-s"},
    ];
    var closeDiv = el("div", "dma-sr-close"); closeDiv.textContent = "CLOSE  " + lk(close);
    var aboveClose = levels.filter(function (L) { return L.val > close; }).reverse();
    var belowClose = levels.filter(function (L) { return L.val <= close; });
    if (aboveClose.length) { srb.appendChild(el("div","fd-note","▲ RESISTANCE")); aboveClose.forEach(function (L) { _srRow(srb, L, close); }); }
    srb.appendChild(closeDiv);
    if (belowClose.length) { srb.appendChild(el("div","fd-note","▼ SUPPORT")); belowClose.forEach(function (L) { _srRow(srb, L, close); }); }

    // Backtest
    var btd = $("fd-bt"); btd.querySelector("h4").textContent =
      "Backtest — on BUY/SELL signal days, did next session hit ₹1?";
    var old = btd.querySelector(".fno-bt-body");
    if (old) old.remove();
    var btb = el("div","fno-bt-body"); btd.appendChild(btb);
    [
      ["LONG signals (" + r.bt_long_n + " trades)", r.bt_long_wr],
      ["SHORT signals (" + r.bt_short_n + " trades)", r.bt_short_wr],
    ].forEach(function (row2) {
      var d2 = el("div","dma-bt-row");
      d2.appendChild(el("span", null, row2[0] + ":"));
      var wr = row2[1];
      d2.appendChild(el("b", wr != null ? (wr >= 70 ? "conv-high" : wr >= 55 ? "conv-medium" : "conv-low") : "",
                        wr != null ? wr.toFixed(1) + "% ₹1 hit rate" : "< 5 signals (unproven)"));
      btb.appendChild(d2);
    });

    // Reasons
    var rb = $("fd-reasons-body"); rb.textContent = "";
    (r.reasons || []).forEach(function (s) {
      var d2 = el("div", "dma-score-row");
      d2.appendChild(el("span", null, s));
      rb.appendChild(d2);
    });

    var det = $("fno-detail"); det.removeAttribute("hidden"); det.scrollTop = 0;
  }

  function _srRow(parent, L, close) {
    var row2 = el("div","dma-sr-row");
    row2.appendChild(el("span","dma-sr-label " + L.cls, L.label));
    row2.appendChild(el("span","dma-sr-val", lk(L.val)));
    var gapPct = ((L.val / close - 1) * 100).toFixed(1);
    var isPct  = L.val > close;
    row2.appendChild(el("span", "dma-sr-pct " + (isPct ? "res" : "sup"), (isPct ? "+" : "") + gapPct + "%"));
    parent.appendChild(row2);
  }

  /* ── Boot ────────────────────────────────────────────── */
  function boot() {
    var capInput = $("cap-input");
    capInput.addEventListener("input", function () { renderCalc(parseInt(capInput.value) || 1000000); });
    document.querySelectorAll("[data-cap]").forEach(function (btn) {
      btn.addEventListener("click", function () { capInput.value = btn.dataset.cap; renderCalc(parseInt(btn.dataset.cap)); });
    });
    document.querySelectorAll(".dma-filter").forEach(function (btn) {
      btn.addEventListener("click", function () { setFilter(btn.dataset.filter); });
    });
    $("fd-close").addEventListener("click", function () { $("fno-detail").setAttribute("hidden",""); selected = null; });

    fetch("fno-play.json?" + Date.now())
      .then(function (r) { return r.json(); })
      .then(function (data) {
        D = data;
        renderStats();
        renderPicks();
        renderCalc(parseInt(capInput.value) || 1000000);
        renderAll();
      })
      .catch(function (e) {
        var b = $("fno-banner"); b.className = "fd-banner open"; b.textContent = "Failed to load: " + e;
      });
  }

  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
