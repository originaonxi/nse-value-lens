/* EMA 200 desk. Renders ema200.json + ema200/<SYMBOL>.json (built by ema200_fib.py after every close).
   All text via textContent. */
(function () {
  "use strict";
  var D = null, S = null, CH = null, SER = null, EMA = null, LINES = [], RANGE = "all", GROUP = "ALL", RULE = null;
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
  function isNum(v) { return typeof v === "number" && isFinite(v); }
  function inr(v) {
    if (!isNum(v)) return "-";
    var s = Math.round(Math.abs(v)).toString(), last = s.slice(-3), rest = s.slice(0, -3);
    if (rest) last = "," + last;
    rest = rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",");
    return (v < 0 ? "-₹" : "₹") + rest + last;
  }
  function sinr(v) { return isNum(v) && v > 0 ? "+" + inr(v) : inr(v); }
  function lakh(v) { return isNum(v) ? (v > 0 ? "+" : v < 0 ? "-" : "") + "₹" + (Math.abs(v) / 1e5).toFixed(2) + "L" : "-"; }
  function num(v, d) { return isNum(v) ? v.toLocaleString("en-IN", { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }) : "-"; }
  function pct(v) { return isNum(v) ? (v > 0 ? "+" : "") + v.toFixed(2) + "%" : "-"; }
  function tone(v) { return isNum(v) ? (v > 0 ? "num up" : v < 0 ? "num dn" : "num") : "num"; }
  function td(tr, t, c) { tr.appendChild(el("td", c || null, t)); }
  function head(tb, cols) {
    tb.textContent = "";
    var th = el("thead"), tr = el("tr");
    cols.forEach(function (c) { tr.appendChild(el("th", c[1] || null, c[0])); });
    th.appendChild(tr); tb.appendChild(th);
    var b = el("tbody"); tb.appendChild(b); return b;
  }
  function fibName(r) { return (Math.round(+r * 1000) / 10) + "%"; }
  function kindOf(label) { return label.split(" · ").length === 3 ? label.split(" · ")[1] : label.split(" · ")[0]; }

  function renderAnswer() {
    var st = D.stocks, nf = D.nifty, w = D.window;
    var sp = st.rows.filter(function (r) { return r.label === st.pick; })[0];
    var np = nf.rows.filter(function (r) { return r.label === nf.pick; })[0];
    var bothRows = st.rows.filter(function (r) { return r.mode === "both"; });
    var bothNeg = bothRows.filter(function (r) { return r.stats.total < 0; }).length;
    var bestStock = st.rows.slice().sort(function (a, b) { return b.stats.total - a.stats.total; })[0];
    var bestNifty = nf.rows.slice().sort(function (a, b) { return b.stats.total - a.stats.total; })[0];
    var bothHalves = nf.rows.filter(function (r) { return r.stats.h1 > 0 && r.stats.h2 > 0; });
    var j = (D.jev && D.jev.answers) || {};
    var box = $("e2-answer"); box.textContent = "";
    box.appendChild(el("b", "big", "Winner picked on sessions 1-100, tested on sessions 101-200: it lost on both books. Jev: " +
      ((j.stocks && j.stocks.real_money) ? j.stocks.real_money.choice : "-") + " / " + ((j.nifty && j.nifty.real_money) ? j.nifty.real_money.choice : "-") + "."));
    var ul = el("ul");
    [
      "₹1 crore in the Nifty 200 (" + w.from + " → " + w.to + "): the best rule on sessions 1-100 was " + st.pick + " (" + lakh(sp.stats.h1) +
        "), then " + lakh(sp.stats.h2) + " on sessions 101-200. Simply holding all stocks: " + lakh(st.hold.h1) + " then " + lakh(st.hold.h2) + ".",
      "SELL (short) side on stocks: " + bothNeg + " of " + bothRows.length + " BUY + SELL rules lost money over 200 sessions. Best of all " + st.rows.length +
        " stock rules on the whole window (hindsight): " + bestStock.label + " " + lakh(bestStock.stats.total) + " (" + bestStock.stats.return_pct + "%).",
      "Nifty 10 lots (20 lots = double): the best rule on sessions 1-100 was " + nf.pick + " (" + lakh(np.stats.h1) + "), then " + lakh(np.stats.h2) +
        " on sessions 101-200. Holding Nifty: " + num(np.hold_pts, 0) + " points.",
      bothHalves.length + " of " + nf.rows.length + " Nifty rules made money in both halves. Best on the whole window (hindsight): " + bestNifty.label + " " +
        lakh(bestNifty.stats.total) + " on 10 lots, " + lakh(bestNifty.stats.total * 2) + " on 20 lots, worst fall " + lakh(-bestNifty.stats.max_dd) + ".",
      "Jev's pick: stocks " + ((j.stocks && j.stocks.winner) ? j.stocks.winner.choice + " (" + j.stocks.winner.conf + "%)" : "-") + "; Nifty " +
        ((j.nifty && j.nifty.winner) ? j.nifty.winner.choice + " (" + j.nifty.winner.conf + "%)" : "-") + ". Luck from fitting the past: " +
        ((j.stocks && j.stocks.overfit) ? j.stocks.overfit.choice : "-") + " / " + ((j.nifty && j.nifty.overfit) ? j.nifty.overfit.choice : "-") + ".",
    ].forEach(function (t) { ul.appendChild(el("li", null, t)); });
    box.appendChild(ul);
  }

  function renderGroups() {
    var box = $("e2-groups"); box.textContent = "";
    [["ALL", D.rows.length, "All Nifty 200"], ["ABOVE", D.counts.ABOVE, "Above EMA 200"], ["ON", D.counts.ON, "On EMA 200 (±0.5 ATR)"], ["BELOW", D.counts.BELOW, "Below EMA 200"]]
      .forEach(function (g) {
        var b = el("button", "g-" + g[0] + (GROUP === g[0] ? " on" : "")); b.type = "button";
        b.appendChild(el("b", null, String(g[1]))); b.appendChild(el("small", null, g[2]));
        b.addEventListener("click", function () { GROUP = g[0]; renderGroups(); renderRows(); });
        box.appendChild(b);
      });
  }

  function zoneText(z) {
    if (!z) return "-";
    return num(z.price, 2) + " (" + pct(z.pct) + ")" + (z.ema200 ? " +EMA200" : "");
  }

  function renderRows() {
    var rows = D.rows.filter(function (r) { return GROUP === "ALL" || r.zone === GROUP; })
      .sort(function (a, b) { return b.dist_atr - a.dist_atr; });
    $("e2-rows-sub").textContent = "· " + rows.length + " stocks · as of " + D.as_of + " · sorted by distance from EMA 200 in ATRs";
    var b = head($("e2-rows"), [["Stock"], ["Group"], ["Close", "num"], ["EMA 200", "num"], ["Distance", "num"], ["ATRs", "num"], ["Side since"],
      ["Double-fib support"], ["Double-fib resistance"], ["Zones", "num"], ["F&O"], ["Position now"], ["Rule P&L ₹", "num"]]);
    rows.forEach(function (r) {
      var tr = el("tr", S && S.symbol === r.symbol ? "on" : null);
      td(tr, r.symbol); td(tr, r.zone, "pill-" + r.zone); td(tr, num(r.close, 2), "num"); td(tr, num(r.ema200, 2), "num");
      td(tr, pct(r.dist_pct), tone(r.dist_pct)); td(tr, num(r.dist_atr, 2), tone(r.dist_atr)); td(tr, r.since || "-");
      td(tr, zoneText(r.support)); td(tr, zoneText(r.resistance)); td(tr, String(r.zones), "num"); td(tr, r.fno ? "yes" : "no");
      td(tr, r.position + (r.pos_since ? " since " + r.pos_since : ""), r.position === "BUY" ? "up" : r.position === "SELL" ? "dn" : null);
      td(tr, sinr(r.book_rs), tone(r.book_rs));
      tr.addEventListener("click", function () { $("e2-sym").value = r.symbol; loadStock(r.symbol, true); });
      b.appendChild(tr);
    });
  }

  function loadStock(sym, scroll) {
    fetch("ema200/" + encodeURIComponent(sym) + ".json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (s) { S = s; renderStock(); if (GROUP) renderRows(); if (scroll) $("e2-chart").scrollIntoView({ behavior: "smooth", block: "center" }); })
      .catch(function (e) { $("e2-chart-note").textContent = "Failed to load " + sym + ": " + e.message; });
  }

  function renderStock() {
    var row = D.rows.filter(function (r) { return r.symbol === S.symbol; })[0];
    $("e2-chart-sub").textContent = S.symbol + " · " + S.name + " · daily · last " + S.bars.length + " sessions" +
      (row ? " · " + row.zone + " EMA 200 by " + pct(row.dist_pct) : "");
    if (typeof LightweightCharts === "undefined") { $("e2-chart").textContent = "Chart library failed to load."; return; }
    if (!CH) {
      CH = LightweightCharts.createChart($("e2-chart"), {
        autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
        grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } }, rightPriceScale: { borderColor: "#e2e8f0" },
        timeScale: { borderColor: "#e2e8f0", rightOffset: 4 }
      });
      SER = CH.addCandlestickSeries({ upColor: "#16a34a", downColor: "#dc2626", borderUpColor: "#16a34a", borderDownColor: "#dc2626", wickUpColor: "#16a34a", wickDownColor: "#dc2626" });
      EMA = CH.addLineSeries({ color: "#2563eb", lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: "EMA 200" });
    }
    SER.setData(S.bars.map(function (b) { return { time: b[0], open: b[1], high: b[2], low: b[3], close: b[4] }; }));
    EMA.setData(S.bars.map(function (b, j) { return S.ema200[j] == null ? { time: b[0] } : { time: b[0], value: S.ema200[j] }; }));
    LINES.forEach(function (l) { SER.removePriceLine(l); }); LINES = [];
    Object.keys(S.big.levels).forEach(function (r) {
      LINES.push(SER.createPriceLine({ price: S.big.levels[r], color: "#94a3b8", lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: "200d " + fibName(r) }));
    });
    Object.keys(S.small.levels).forEach(function (r) {
      LINES.push(SER.createPriceLine({ price: S.small.levels[r], color: "#f59e0b", lineWidth: 1, lineStyle: 3, axisLabelVisible: false, title: "50d " + fibName(r) }));
    });
    S.zones.forEach(function (z) {
      LINES.push(SER.createPriceLine({ price: z.price, color: "#7c3aed", lineWidth: 3, lineStyle: 0, axisLabelVisible: true, title: "DOUBLE FIB" + (z.ema200 ? " + EMA200" : "") }));
    });
    drawMarkers(); renderRange(); renderLevels();
    $("e2-chart-note").textContent = "Grey dashed = Fibonacci of the last 200 sessions (" + num(S.big.low, 2) + " → " + num(S.big.high, 2) + "), orange dotted = last 50 sessions (" +
      num(S.small.low, 2) + " → " + num(S.small.high, 2) + "), purple = double-fib zone where both agree within 0.5%. Markers: trades of the chosen rule over the last 200 sessions.";
  }

  function drawMarkers() {
    var tr = (S.trades && S.trades[RULE]) || [], m = [], first = S.bars[0][0];
    tr.forEach(function (x) {
      var buy = x[0] === "BUY";
      if (x[1] >= first) m.push({ time: x[1], position: buy ? "belowBar" : "aboveBar", color: buy ? "#16a34a" : "#dc2626", shape: buy ? "arrowUp" : "arrowDown", text: x[0] });
      if (x[3] && x[3] >= first) m.push({ time: x[3], position: buy ? "aboveBar" : "belowBar", color: x[5] > 0 ? "#15803d" : "#b91c1c", shape: "circle", text: sinr(x[5]), size: 0.7 });
    });
    m.sort(function (a, b) { return a.time < b.time ? -1 : a.time > b.time ? 1 : 0; });
    SER.setMarkers(m);
  }

  function renderRange() {
    var box = $("e2-range"); box.textContent = "";
    [["60", "3 months"], ["130", "6 months"], ["all", "1 year"]].forEach(function (r) {
      var b = el("button", RANGE === r[0] ? "on" : null, r[1]); b.type = "button";
      b.addEventListener("click", function () { RANGE = r[0]; renderRange(); });
      box.appendChild(b);
    });
    var n = S.bars.length;
    if (RANGE === "all") CH.timeScale().fitContent();
    else CH.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - (+RANGE)), to: n + 3 });
  }

  function renderLevels() {
    var last = S.bars[S.bars.length - 1][4];
    var b = head($("e2-levels"), [["Level"], ["200-session fib", "num"], ["vs close", "num"], ["50-session fib", "num"], ["vs close", "num"]]);
    Object.keys(S.big.levels).forEach(function (r) {
      var tr = el("tr"), bg = S.big.levels[r], sm = S.small.levels[r];
      td(tr, fibName(r)); td(tr, num(bg, 2), "num"); td(tr, pct((bg / last - 1) * 100), tone(bg - last));
      td(tr, num(sm, 2), "num"); td(tr, pct((sm / last - 1) * 100), tone(sm - last)); b.appendChild(tr);
    });
    S.zones.forEach(function (z) {
      var tr = el("tr", "pick");
      td(tr, "DOUBLE FIB" + (z.ema200 ? " + EMA 200" : "")); td(tr, num(z.lo, 2) + " – " + num(z.hi, 2), "num"); td(tr, pct(z.pct), tone(z.pct));
      td(tr, z.pairs.map(function (p) { return fibName(p[0]) + "/" + fibName(p[1]); }).join(", ")); td(tr, ""); b.appendChild(tr);
    });
  }

  function statCells(tr, s, mult) {
    var k = mult || 1;
    td(tr, sinr(s.h1 * k), tone(s.h1)); td(tr, sinr(s.h2 * k), tone(s.h2)); td(tr, sinr(s.total * k), tone(s.total));
  }

  function renderStocks() {
    var st = D.stocks;
    $("e2-stk-sub").textContent = "· ₹" + num(st.slot) + " per stock × " + st.stocks + " · " + st.cost_pct + "% per side · sessions 1-100 = pick, 101-200 = test";
    var b = head($("e2-stk"), [["Rule"], ["Sessions 1-100", "num"], ["Sessions 101-200", "num"], ["200 sessions", "num"], ["Return", "num"],
      ["BUY side", "num"], ["SELL side", "num"], ["Trades", "num"], ["Won", "num"], ["Profit factor", "num"], ["Worst fall", "num"], ["Stocks up", "num"]]);
    st.rows.forEach(function (r) {
      var s = r.stats, tr = el("tr", r.label === st.pick ? "pick" : null);
      var c = el("td", null, r.label); c.title = r.rule; tr.appendChild(c);
      statCells(tr, s); td(tr, s.return_pct + "%", tone(s.return_pct)); td(tr, sinr(s.long_rs), tone(s.long_rs)); td(tr, sinr(s.short_rs), tone(s.short_rs));
      td(tr, String(s.trades), "num"); td(tr, s.win + "%", "num"); td(tr, s.pf == null ? "-" : String(s.pf), "num"); td(tr, inr(-s.max_dd), "num dn");
      td(tr, String(s.stocks_up), "num"); b.appendChild(tr);
    });
    var h = st.hold, tr = el("tr", "hold"); td(tr, "Hold every stock (no trading)"); td(tr, sinr(h.h1), tone(h.h1)); td(tr, sinr(h.h2), tone(h.h2));
    td(tr, sinr(h.total), tone(h.total)); td(tr, (h.total / st.capital * 100).toFixed(2) + "%", tone(h.total));
    for (var i = 0; i < 5; i++) td(tr, ""); td(tr, inr(-h.max_dd), "num dn"); td(tr, ""); b.appendChild(tr);
    if (typeof LightweightCharts === "undefined") return;
    var c2 = LightweightCharts.createChart($("e2-stk-curve"), {
      autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
      grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } }, rightPriceScale: { borderColor: "#e2e8f0" },
      timeScale: { borderColor: "#e2e8f0" }, localization: { priceFormatter: function (v) { return "₹" + (v / 1e5).toFixed(1) + " L"; } }
    });
    var pick = st.rows.filter(function (r) { return r.label === st.pick; })[0];
    var best = st.rows.filter(function (r) { return r.mode === "both"; }).sort(function (a, b) { return b.stats.total - a.stats.total; })[0];
    [[pick, "#16a34a", 3], [best, "#dc2626", 2]].forEach(function (z) {
      var s = c2.addLineSeries({ color: z[1], lineWidth: z[2], priceLineVisible: false, title: z[0].label });
      s.setData(z[0].curve.map(function (x) { return { time: x[0], value: x[1] }; }));
    });
    c2.timeScale().fitContent();
  }

  function renderNifty() {
    var nf = D.nifty;
    $("e2-nf-sub").textContent = "· 1 lot = " + nf.lot + " · " + nf.cost_pct + "% per side · 20 lots = 2 × 10 lots · Nifty now " + num(nf.now.close, 2) + ", " + nf.now.zone + " EMA 200 by " + pct(nf.now.dist_pct);
    var b = head($("e2-nf"), [["Rule"], ["10 lots: 1-100", "num"], ["10 lots: 101-200", "num"], ["10 lots: 200 sessions", "num"], ["20 lots: 200 sessions", "num"],
      ["Points", "num"], ["BUY side", "num"], ["SELL side", "num"], ["Trades", "num"], ["Won", "num"], ["PF", "num"], ["Worst fall (10 lots)", "num"]]);
    nf.rows.forEach(function (r) {
      var s = r.stats, tr = el("tr", r.label === nf.pick ? "pick" : null);
      var c = el("td", null, r.label); c.title = r.rule; tr.appendChild(c);
      statCells(tr, s); td(tr, sinr(s.total * 2), tone(s.total)); td(tr, num(s.points, 1), tone(s.points));
      td(tr, sinr(s.long_rs), tone(s.long_rs)); td(tr, sinr(s.short_rs), tone(s.short_rs)); td(tr, String(s.trades), "num");
      td(tr, s.win + "%", "num"); td(tr, s.pf == null ? "-" : String(s.pf), "num"); td(tr, inr(-s.max_dd), "num dn"); b.appendChild(tr);
    });
  }

  function renderJev() {
    var j = D.jev || {}, b = head($("e2-jev"), [["Book"], ["Most likely to keep working"], ["Luck from fitting the past"], ["Real money"]]);
    if (!j.answers) { var tr0 = el("tr"); td(tr0, "Jev " + (j.status || "not run")); b.appendChild(tr0); return; }
    [["stocks", "₹1 crore · Nifty 200"], ["nifty", "Nifty 50 · 10 lots"]].forEach(function (k) {
      var a = j.answers[k[0]] || {}, tr = el("tr");
      td(tr, k[1]);
      if (a.error) { td(tr, "error: " + a.error); td(tr, ""); td(tr, ""); }
      else ["winner", "overfit", "real_money"].forEach(function (q) { td(tr, a[q] ? a[q].choice + " (" + a[q].conf + "% sure)" : "-"); });
      b.appendChild(tr);
    });
    var tr = el("tr"); td(tr, "Model " + (j.model || "-") + " · " + j.status); b.appendChild(tr);
  }

  function renderFoot() {
    var m = $("e2-method"); m.textContent = ""; D.method.forEach(function (x) { m.appendChild(el("li", null, x)); });
    var l = $("e2-limits"); l.textContent = ""; D.limits.forEach(function (x) { l.appendChild(el("li", null, x)); });
  }

  function boot() {
    fetch("ema200.json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        D = d;
        $("e2-sub").textContent = D.rows.length + " Nifty 200 stocks · " + D.counts.ABOVE + " above, " + D.counts.ON + " on, " + D.counts.BELOW +
          " below EMA 200 · test " + D.window.from + " → " + D.window.to + " · rebuilt " + D.generated_at.replace("T", " ").slice(0, 16);
        RULE = kindOf(D.stocks.pick);
        renderAnswer(); renderGroups(); renderRows(); renderStocks(); renderNifty(); renderJev(); renderFoot();
        var sel = $("e2-sym");
        var o0 = el("option", null, "NIFTY 50 (index)"); o0.value = "NIFTY"; sel.appendChild(o0);
        D.rows.slice().sort(function (a, b) { return a.symbol < b.symbol ? -1 : 1; }).forEach(function (r) {
          var o = el("option", null, r.symbol + " · " + r.zone); o.value = r.symbol; sel.appendChild(o);
        });
        sel.addEventListener("change", function () { loadStock(sel.value); });
        var rs = $("e2-rule");
        Object.keys(D.kinds).forEach(function (k) { var o = el("option", null, k + (k === RULE ? " (picked)" : "")); o.value = k; o.title = D.kinds[k]; rs.appendChild(o); });
        rs.value = RULE;
        rs.addEventListener("change", function () { RULE = rs.value; if (S) drawMarkers(); });
        loadStock("NIFTY");
        document.body.dataset.ready = "true";
      })
      .catch(function (e) { $("e2-sub").textContent = "Failed to load ema200.json: " + e.message; document.body.dataset.ready = "error"; });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
