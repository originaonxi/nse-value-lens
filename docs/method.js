/* One model of the 10-methods race: ?m=<key>. Reads methods.json (stats + trades) and
   method_<key>.json (its own-timeframe candles + the exact series the formula watches).
   All text via textContent. */
(function () {
  "use strict";
  var D = null, M = null, C = null, CH = null, SER = null, RANGE = null;
  var LINE_COLORS = ["#f97316", "#7c3aed"];
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
  function num(v, d) { return isNum(v) ? v.toLocaleString("en-IN", { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }) : "-"; }
  function spts(v) { return isNum(v) ? (v > 0 ? "+" : "") + num(v, 1) : "-"; }
  function tone(v) { return isNum(v) ? (v > 0 ? "num up" : v < 0 ? "num dn" : "num") : "num"; }
  function td(tr, t, c) { tr.appendChild(el("td", c || null, t)); }
  function head(tb, cols) {
    tb.textContent = "";
    var th = el("thead"), tr = el("tr");
    cols.forEach(function (c) { tr.appendChild(el("th", c[1] || null, c[0])); });
    th.appendChild(tr); tb.appendChild(th);
    var b = el("tbody"); tb.appendChild(b); return b;
  }
  function ts(s) { return Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10), +s.slice(11, 13) || 0, +s.slice(14, 16) || 0) / 1000; }
  function kpi(box, label, big, sub, cls) {
    var k = el("div", "e9-kpi");
    k.appendChild(el("small", null, label)); k.appendChild(el("strong", cls || null, big)); if (sub) k.appendChild(el("span", null, sub));
    box.appendChild(k);
  }

  function renderHead() {
    var s = M.summary;
    document.title = M.name + " · " + M.tf + " · 10 methods | NSE Value Lens";
    $("mp-eyebrow").textContent = "NIFTY 50 · " + M.name.toUpperCase() + " · " + M.tf.toUpperCase() + " CANDLES · " + M.family.toUpperCase() + " · ALWAYS IN A TRADE";
    $("mp-name").firstChild.textContent = M.name + " ";
    $("mp-sub").textContent = M.tf + " candles · " + D.from + " → " + D.last_candle + " IST · " + s.trades +
      " closed trades so far (grows every session) · rebuilt " + D.generated_at.replace("T", " ").slice(0, 16);
    $("mp-formula").textContent = M.formula;
    var ul = $("mp-why"); ul.textContent = "";
    ul.appendChild(el("li", null, M.desc));
    ul.appendChild(el("li", null, M.why));
  }

  function renderKpis() {
    var s = M.summary, box = $("mp-kpis"); box.textContent = "";
    kpi(box, "Net since " + D.from + " · 1 lot", sinr(s.net_rs), spts(s.net_pts) + " points after costs", s.net_rs > 0 ? "up" : "dn");
    kpi(box, "Total plus (won)", "+" + num(s.plus_pts, 0) + " pts", sinr(s.plus_rs) + " · " + s.win_pct + "% of trades", "up");
    kpi(box, "Total minus (lost)", num(s.minus_pts, 0) + " pts", sinr(s.minus_rs), "dn");
    kpi(box, "Open trade", spts(s.open_pts) + " pts", M.now.side ? M.now.side + " since " + M.now.entry_time : "none", s.open_pts > 0 ? "up" : s.open_pts < 0 ? "dn" : null);
    kpi(box, "Profit factor", s.profit_factor == null ? "-" : num(s.profit_factor, 2), "avg win " + spts(s.avg_win) + " / avg loss " + spts(s.avg_loss));
    kpi(box, "Worst fall", "-" + num(s.max_dd_pts, 0) + " pts", inr(-s.max_dd_rs) + " on 1 lot", "dn");
    kpi(box, "2026", spts(s.y2026_pts) + " pts", "last 20 sessions " + spts(s.last20_pts), s.y2026_pts > 0 ? "up" : "dn");
    kpi(box, "Trades", num(s.trades), "about " + num(s.trades / Math.max(1, (ts(D.last_candle) - ts(D.from + " 00:00")) / 2629800), 1) + " a month");
  }

  function renderNow() {
    var box = $("mp-now"); box.textContent = "";
    box.className = "e9-now" + (M.now.side === "SELL" ? " sell" : "");
    var st = el("div", "st");
    st.appendChild(el("small", null, "Right now · last candle " + D.last_candle + " IST"));
    st.appendChild(document.createTextNode(M.now.side ? "IN TRADE · " + M.now.side : "no open trade"));
    box.appendChild(st);
    var ul = el("ul");
    if (M.now.side) ul.appendChild(el("li", null, M.now.side + " since " + M.now.entry_time + " at " + num(M.now.entry, 2) +
      " · open " + spts(M.now.open_pts) + " points = " + sinr(M.now.open_pts * D.lot) + " on 1 lot"));
    ul.appendChild(el("li", null, "The model re-decides at every " + M.tf + " close; a flip fills at the next open."));
    box.appendChild(ul);
  }

  function barsPerDay() { return { "15m": 25, "30m": 13, "1h": 7 }[C.tf] || 25; }

  function renderChart() {
    var box = $("mp-chart");
    if (typeof LightweightCharts === "undefined") { box.textContent = "Chart library failed to load."; return; }
    CH = LightweightCharts.createChart(box, {
      autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
      grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } },
      rightPriceScale: { borderColor: "#e2e8f0" }, crosshair: { mode: 0 },
      leftPriceScale: { visible: C.aux.length > 0, borderColor: "#e2e8f0" },
      timeScale: { borderColor: "#e2e8f0", timeVisible: true, secondsVisible: false, rightOffset: 5 }
    });
    SER = CH.addCandlestickSeries({ upColor: "#16a34a", downColor: "#dc2626", borderUpColor: "#16a34a", borderDownColor: "#dc2626", wickUpColor: "#16a34a", wickDownColor: "#dc2626" });
    SER.setData(C.bars.map(function (b) { return { time: ts(b[0]), open: b[1], high: b[2], low: b[3], close: b[4] }; }));
    var legend = [];
    C.lines.forEach(function (ln, i) {
      var s = CH.addLineSeries({ color: LINE_COLORS[i % 2], lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: ln.name });
      s.setData(C.bars.map(function (b, j) { return ln.values[j] == null ? { time: ts(b[0]) } : { time: ts(b[0]), value: ln.values[j] }; }));
      legend.push(ln.name);
    });
    C.aux.forEach(function (ln) {
      var s = CH.addLineSeries({ color: "#0f766e", lineWidth: 2, priceScaleId: "left", priceLineVisible: false, lastValueVisible: true, title: ln.name });
      s.setData(C.bars.map(function (b, j) { return ln.values[j] == null ? { time: ts(b[0]) } : { time: ts(b[0]), value: ln.values[j] }; }));
      legend.push(ln.name + " (left scale)");
    });
    var first = ts(C.bars[0][0]), markers = [];
    M.trades.forEach(function (t) {
      var x = ts(t.entry_time);
      if (x < first) return;
      var buy = t.side === "BUY";
      markers.push({ time: x, position: buy ? "belowBar" : "aboveBar", color: buy ? "#16a34a" : "#dc2626",
                     shape: buy ? "arrowUp" : "arrowDown", text: t.side });
    });
    SER.setMarkers(markers);
    var op = M.trades.length && M.trades[M.trades.length - 1].open ? M.trades[M.trades.length - 1] : null;
    if (op) SER.createPriceLine({ price: op.entry, color: op.side === "BUY" ? "#15803d" : "#b91c1c", lineWidth: 1, lineStyle: 2,
      axisLabelVisible: true, title: "open " + op.side + " " + num(op.entry, 0) });
    $("mp-legend").textContent = "▲ BUY fill · ▼ SELL fill · " + legend.join(" · ") + " · dashed = open trade's entry";
    $("mp-chart-note").textContent = C.bars.length + " " + C.tf + " candles · the last year · drag to move, scroll to zoom";
    renderRange();
  }

  function renderRange() {
    var box = $("mp-range"); box.textContent = "";
    var bpd = barsPerDay();
    [["1 week", 5 * bpd], ["1 month", 21 * bpd], ["3 months", 63 * bpd], ["1 year", 0]].forEach(function (r, i) {
      var b = el("button", (RANGE === null ? i === 1 : RANGE === r[1]) ? "on" : null, r[0]); b.type = "button";
      b.addEventListener("click", function () { RANGE = r[1]; renderRange(); });
      box.appendChild(b);
    });
    var n = C.bars.length, w = RANGE === null ? 21 * bpd : RANGE;
    if (w === 0) CH.timeScale().fitContent();
    else CH.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - w), to: n + 4 });
  }

  function renderYears() {
    var b = head($("mp-years"), [["Year"], ["Points", "r"], ["₹ 1 lot", "r"]]);
    M.years.forEach(function (y) {
      var tr = el("tr");
      td(tr, String(y.year));
      td(tr, spts(y.pts), "r " + tone(y.pts));
      td(tr, sinr(y.pts * D.lot), "r " + tone(y.pts));
      b.appendChild(tr);
    });
  }

  function renderTrades() {
    var s = M.summary;
    $("mp-tr-n").textContent = s.trades + " closed + " + (M.trades.length - s.trades) + " open · total plus +" + num(s.plus_pts, 0) +
      " · total minus " + num(s.minus_pts, 0) + " · open " + spts(s.open_pts) + " · net " + spts(s.net_pts) + " points";
    var b = head($("mp-trades"), [["#", "r"], ["Side"], ["Entry (IST)"], ["Entry", "r"], ["Exit (IST)"], ["Exit", "r"],
      ["Points", "r"], ["₹ 1 lot", "r"], ["Running pts", "r"]]);
    var run = 0, rows = [];
    M.trades.forEach(function (t, i) {
      run += t.net_pts;
      rows.push({ i: i + 1, t: t, run: run });
    });
    rows.reverse().forEach(function (r) {
      var tr = el("tr", r.t.open ? "open" : null);
      td(tr, String(r.i), "r");
      td(tr, r.t.side, "side-" + r.t.side);
      td(tr, r.t.entry_time);
      td(tr, num(r.t.entry, 2), "r");
      td(tr, r.t.open ? "open" : r.t.exit_time);
      td(tr, num(r.t.exit, 2), "r");
      td(tr, spts(r.t.net_pts), "r " + tone(r.t.net_pts));
      td(tr, sinr(r.t.rupees), "r " + tone(r.t.rupees));
      td(tr, spts(r.run), "r " + tone(r.run));
      b.appendChild(tr);
    });
  }


  function renderLiveTest() {
    var L = D.livetest, wrap = $("mp-livetest-wrap"), box = $("mp-livetest");
    if (!L || !wrap || L.key !== M.key) return;
    wrap.hidden = false;
    box.textContent = "";
    var k = L.closed, pct = Math.min(100, Math.round(100 * k / L.target));
    var top = el("div", "lt-top");
    top.appendChild(el("b", null, "Trade " + k + " of " + L.target));
    top.appendChild(el("span", "lt-status " + (L.status.indexOf("PASSED") === 0 || L.status.indexOf("AHEAD") === 0 ? "up"
      : L.status.indexOf("FAIL") === 0 || L.status.indexOf("WARNING") === 0 ? "dn" : ""), L.status));
    box.appendChild(top);
    var bar = el("div", "lt-bar"), fill = el("i");
    fill.style.width = (k ? Math.max(pct, 2) : 0) + "%";
    bar.appendChild(fill); box.appendChild(bar);
    var ul = el("ul", "fd-limits");
    ul.appendChild(el("li", null, "Live P&L (closed live trades): " + spts(L.cum_pts) + " points = " + sinr(L.cum_rs) + " on 1 lot" +
      (k ? " · expected if the backtest is true: " + spts(L.expected_pts) + " ± " + num(L.band_pts, 0) + " points" : "")));
    if (L.open_trade) ul.appendChild(el("li", null, "Open live trade: " + L.open_trade.side + " since " + L.open_trade.entry_time +
      " at " + num(L.open_trade.entry, 2) + " · " + spts(L.open_trade.net_pts) + " points (counts when it closes)"));
    L.rules.forEach(function (r) { ul.appendChild(el("li", null, r)); });
    box.appendChild(ul);
  }
  function renderJev() {
    fetch("methods_jev.json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        var a = (j.answers || {})[M.key];
        $("mp-jev").textContent = a && !a.error
          ? "Jev grades this model \"" + a.grade + "\" (confidence " + a.conf + "%, sturdiness score " + a.score + "/100), judged " +
            String(j.generated_at || "").replace("T", " ").slice(0, 16) + " from the real numbers above. " + (j.note || "")
          : "No Jev assessment available for this model yet.";
      })
      .catch(function () { $("mp-jev").textContent = "No Jev assessment available for this model yet."; });
  }

  function boot() {
    var q = {}; location.search.replace(/[?&]([^=&]+)=([^&]*)/g, function (a, k, v) { q[k] = v; return a; });
    var key = /^[a-z0-9_]+$/.test(q.m || "") ? q.m : "sma5200";
    fetch("methods.json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        D = d;
        M = d.methods.filter(function (x) { return x.key === key; })[0];
        if (!M) throw new Error("unknown model " + key);
        return fetch(M.chart + "?v=" + Date.now(), { cache: "no-store" });
      })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (c) {
        C = c;
        renderHead(); renderKpis(); renderNow(); renderChart(); renderYears(); renderTrades(); renderJev(); renderLiveTest();
        document.body.dataset.ready = "true";
      })
      .catch(function (e) { $("mp-sub").textContent = "Failed to load: " + e.message; document.body.dataset.ready = "error"; });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
