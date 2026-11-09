/* Nifty EMA 9/21 page. Renders ema921.json (built by ema921.py after every NSE close). All text via textContent. */
(function () {
  "use strict";
  var D = null, CH = null, SER = null, RANGE = "120";
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
  /* "YYYY-MM-DD HH:MM" IST wall clock -> chart seconds (plotted as-is, like the other Nifty pages) */
  function ts(s) { return Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10), +s.slice(11, 13) || 0, +s.slice(14, 16) || 0) / 1000; }
  function kpi(box, label, big, sub, cls, bigcls) {
    var k = el("div", "e9-kpi " + (cls || ""));
    k.appendChild(el("small", null, label)); k.appendChild(el("strong", bigcls || null, big)); if (sub) k.appendChild(el("span", null, sub));
    box.appendChild(k);
  }

  function renderHead() {
    var s = D.summary;
    $("e9-sub").textContent = D.from + " → " + D.last_candle + " IST · " + s.trades + " closed trades + " +
      (D.trades.length && D.trades[D.trades.length - 1].open ? "1 open" : "none open") + " · 1 lot · rebuilt " + D.generated_at.replace("T", " ").slice(0, 16);
  }

  function renderNow() {
    var n = D.now, box = $("e9-now"), s = D.summary; box.textContent = "";
    var flat = n.state.indexOf("IN TRADE") !== 0 && n.pending !== "EXIT";
    box.className = "e9-now" + (flat ? " flat" : "");
    var st = el("div", "st"); st.appendChild(el("small", null, "Right now · last 1-hour candle " + n.time + " IST")); st.appendChild(document.createTextNode(n.state));
    box.appendChild(st);
    var ul = el("ul");
    ul.appendChild(el("li", null, "Nifty " + num(n.close, 2) + " · EMA 9 " + num(n.ema9, 2) + " · EMA 21 " + num(n.ema21, 2)));
    ul.appendChild(el("li", null, n.what + " That is " + spts(n.trigger_pts) + " points from the last close; the level moves with every candle."));
    var op = D.trades.length && D.trades[D.trades.length - 1].open ? D.trades[D.trades.length - 1] : null;
    if (op) ul.appendChild(el("li", null, "Open trade: bought " + op.entry_time + " at " + num(op.entry, 2) + " · now " + spts(op.net_pts) + " pts = " + sinr(op.rupees) + " on 1 lot (" + op.lot + ")"));
    box.appendChild(ul);
  }

  function renderKpis() {
    var s = D.summary, box = $("e9-kpis"); box.textContent = "";
    kpi(box, "Total P&L · 2 years · 1 lot", sinr(s.total_rs), spts(s.total_pts) + " points, after costs", "main", s.total_rs > 0 ? "up" : "dn");
    kpi(box, "Booked (closed trades)", sinr(s.realised_rs), s.trades + " trades", "", s.realised_rs > 0 ? "up" : "dn");
    kpi(box, "Open trade now", sinr(s.open_rs), spts(s.open_pts) + " pts", "", s.open_rs > 0 ? "up" : s.open_rs < 0 ? "dn" : null);
    kpi(box, "Nifty bought & held", sinr(s.nifty_held_rs), spts(s.nifty_held_pts) + " pts, same 1 lot", "", s.nifty_held_rs > 0 ? "up" : "dn");
    kpi(box, "Won", s.win_pct + "%", s.wins + " won · " + s.losses + " lost");
    kpi(box, "Average win / loss", inr(s.avg_win_rs) + " / " + inr(s.avg_loss_rs), "profit factor " + (s.profit_factor == null ? "-" : s.profit_factor));
    kpi(box, "Worst fall", inr(-s.max_dd_rs), s.max_dd_on ? "low on " + s.max_dd_on : "");
    kpi(box, "Costs paid", inr(s.cost_rs), "longest losing run: " + s.longest_losing_run + " trades");
  }

  function renderChart() {
    var ch = D.chart, box = $("e9-chart");
    if (typeof LightweightCharts === "undefined") { box.textContent = "Chart library failed to load."; return; }
    CH = LightweightCharts.createChart(box, {
      autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
      grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } },
      rightPriceScale: { borderColor: "#e2e8f0" }, crosshair: { mode: 0 },
      timeScale: { borderColor: "#e2e8f0", timeVisible: true, secondsVisible: false, rightOffset: 4 }
    });
    SER = CH.addCandlestickSeries({ upColor: "#16a34a", downColor: "#dc2626", borderUpColor: "#16a34a", borderDownColor: "#dc2626", wickUpColor: "#16a34a", wickDownColor: "#dc2626" });
    SER.setData(ch.bars.map(function (b) { return { time: ts(b[0]), open: b[1], high: b[2], low: b[3], close: b[4] }; }));
    [["ema9", "#16a34a", "EMA 9"], ["ema21", "#dc2626", "EMA 21"]].forEach(function (z) {
      var l = CH.addLineSeries({ color: z[1], lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: z[2] });
      l.setData(ch.bars.map(function (b, j) { return ch[z[0]][j] == null ? { time: ts(b[0]) } : { time: ts(b[0]), value: ch[z[0]][j] }; }));
    });
    var op = D.trades.length && D.trades[D.trades.length - 1].open ? D.trades[D.trades.length - 1] : null;
    if (op) SER.createPriceLine({ price: op.entry, color: "#1f6b4a", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "open BUY " + num(op.entry, 0) });
    if (isNum(D.now.trigger)) SER.createPriceLine({ price: D.now.trigger, color: "#b45309", lineWidth: 1, lineStyle: 1, axisLabelVisible: true,
      title: op ? "EXIT below" : "BUY above" });
    drawMarkers(); renderRange();
    $("e9-chart-note").textContent = "1-hour candles in IST, " + ch.bars.length + " candles from " + ch.bars[0][0].slice(0, 10) +
      ". Arrows sit on the candle the order fills at (the open of the candle after the signal). Scroll or drag to move, pinch or wheel to zoom.";
  }

  function drawMarkers() {
    var zoom = RANGE !== "all", m = [];
    D.trades.forEach(function (t) {
      m.push({ time: ts(t.entry_time), position: "belowBar", color: "#16a34a", shape: "arrowUp", text: zoom ? "BUY " + num(t.entry, 0) : "" });
      if (!t.open) m.push({ time: ts(t.exit_time), position: "aboveBar", color: t.rupees > 0 ? "#15803d" : "#b91c1c", shape: "arrowDown",
        text: zoom ? "EXIT " + sinr(t.rupees) : "" });
    });
    SER.setMarkers(m.sort(function (a, b) { return a.time - b.time; }));
  }

  function renderRange() {
    var box = $("e9-range"); box.textContent = "";
    [["35", "1 week"], ["120", "1 month"], ["360", "3 months"], ["720", "6 months"], ["all", "2 years"]].forEach(function (r) {
      var b = el("button", RANGE === r[0] ? "on" : null, r[1]); b.type = "button";
      b.addEventListener("click", function () { RANGE = r[0]; renderRange(); drawMarkers(); });
      box.appendChild(b);
    });
    var n = D.chart.bars.length;
    if (RANGE === "all") CH.timeScale().fitContent();
    else CH.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - (+RANGE)), to: n + 3 });
  }

  function showTrade(t) {
    var bars = D.chart.bars, a = ts(t.entry_time), b = t.open ? ts(bars[bars.length - 1][0]) : ts(t.exit_time), i0 = 0, i1 = bars.length - 1;
    for (var i = 0; i < bars.length; i++) { var x = ts(bars[i][0]); if (x <= a) i0 = i; if (x <= b) i1 = i; }
    RANGE = "trade"; renderRangeButtonsOnly(); drawMarkers();
    CH.timeScale().setVisibleLogicalRange({ from: Math.max(0, i0 - 20), to: Math.min(bars.length + 3, i1 + 20) });
    $("e9-chart").scrollIntoView({ behavior: "smooth", block: "center" });
  }
  function renderRangeButtonsOnly() { Array.prototype.forEach.call($("e9-range").children, function (x) { x.classList.remove("on"); }); }

  function renderCurve() {
    var box = $("e9-curve");
    if (typeof LightweightCharts === "undefined") return;
    var c = LightweightCharts.createChart(box, {
      autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
      grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } }, rightPriceScale: { borderColor: "#e2e8f0" },
      timeScale: { borderColor: "#e2e8f0" }, localization: { priceFormatter: function (v) { return "₹" + (v / 1e5).toFixed(2) + " L"; } }
    });
    var s = c.addAreaSeries({ lineColor: "#16a34a", topColor: "#16a34a33", bottomColor: "#16a34a05", lineWidth: 2, priceLineVisible: false, title: "EMA 9/21" });
    s.setData(D.curve.map(function (x) { return { time: x[0], value: x[1] }; }));
    var h = c.addLineSeries({ color: "#94a3b8", lineWidth: 2, priceLineVisible: false, title: "Nifty held" });
    h.setData(D.curve.map(function (x) { return { time: x[0], value: x[2] }; }));
    c.timeScale().fitContent();
  }

  function periodTable(id, rows, label) {
    var b = head($(id), [[label], ["Trades", "num"], ["Won", "num"], ["Points", "num"], ["P&L (1 lot)", "num"]]);
    var tot = { t: 0, w: 0, p: 0, r: 0 };
    rows.forEach(function (r) {
      var tr = el("tr"); td(tr, r.period); td(tr, String(r.trades), "num"); td(tr, r.wins + " (" + Math.round(r.wins / r.trades * 100) + "%)", "num");
      td(tr, spts(r.net_pts), tone(r.net_pts)); td(tr, sinr(r.rupees), tone(r.rupees)); b.appendChild(tr);
      tot.t += r.trades; tot.w += r.wins; tot.p += r.net_pts; tot.r += r.rupees;
    });
    var tr = el("tr", "fd-total"); td(tr, "Closed trades"); td(tr, String(tot.t), "num"); td(tr, String(tot.w), "num");
    td(tr, spts(tot.p), tone(tot.p)); td(tr, sinr(tot.r), tone(tot.r)); b.appendChild(tr);
  }

  function renderTrades() {
    var tr0 = D.trades.slice().reverse();
    $("e9-tr-n").textContent = "· " + D.summary.trades + " closed" + (tr0.length && tr0[0].open ? " + 1 open" : "") + ", newest first, 1 lot each";
    var b = head($("e9-trades"), [["#", "num"], ["Signal (close)"], ["Bought (open)"], ["Buy price", "num"], ["Exit signal"], ["Sold (open)"], ["Sell price", "num"],
      ["Held", "num"], ["Points", "num"], ["Costs (pts)", "num"], ["Lot", "num"], ["P&L ₹", "num"], ["Running total ₹", "num"]]);
    var run = [], acc = 0;
    D.trades.forEach(function (t) { acc += t.rupees; run.push(acc); });
    tr0.forEach(function (t, k) {
      var i = D.trades.length - 1 - k, tr = el("tr", t.open ? "open" : null);
      td(tr, String(i + 1), "num"); td(tr, t.signal_time); td(tr, t.entry_time); td(tr, num(t.entry, 2), "num");
      td(tr, t.open ? "-" : t.exit_signal_time); td(tr, t.open ? "OPEN · marked at last close" : t.exit_time); td(tr, num(t.exit, 2), "num");
      td(tr, t.days + "d · " + t.candles + " candles", "num"); td(tr, spts(t.net_pts), tone(t.net_pts)); td(tr, num(t.cost_pts, 1), "num");
      td(tr, String(t.lot), "num"); td(tr, sinr(t.rupees), tone(t.rupees)); td(tr, sinr(run[i]), tone(run[i]));
      tr.title = "Show this trade on the chart";
      tr.addEventListener("click", function () { showTrade(t); });
      b.appendChild(tr);
    });
  }

  function renderFoot() {
    var r = $("e9-rule"); r.textContent = ""; D.rule.forEach(function (x) { r.appendChild(el("li", null, x)); });
    var d = D.data, ul = $("e9-data"); ul.textContent = "";
    ul.appendChild(el("li", null, "Source: " + D.source + ". " + d.sessions + " sessions on file, " + d.from + " → " + d.to + "."));
    if (d.vs_nse) {
      var f = d.vs_nse.fields;
      ul.appendChild(el("li", null, "Against NSE's official daily Nifty 50 file on " + d.vs_nse.days + " days: open, high and low match (median gap " +
        f.open.median_pts + " / " + f.high.median_pts + " / " + f.low.median_pts + " pts). The last candle's close differs from NSE's official close by a median " +
        f.close.median_pts + " pts, because NSE's official close is an average of the last 30 minutes; this rule uses candle closes like TradingView does."));
    }
    if (d.vs_yahoo_15m) ul.appendChild(el("li", null, "Against the Yahoo Finance 15-minute candles we keep: " + d.vs_yahoo_15m.bars + " candles, median close gap " + d.vs_yahoo_15m.median_pts + " pts."));
    var sd = Object.keys(d.short_days || {});
    if (sd.length) ul.appendChild(el("li", null, "Short sessions (fewer than 25 fifteen-minute candles): " + sd.join(", ") + "."));
    var l = $("e9-limits"); l.textContent = ""; D.limits.forEach(function (x) { l.appendChild(el("li", null, x)); });
  }

  function boot() {
    fetch("ema921.json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        D = d;
        renderHead(); renderNow(); renderKpis(); renderChart(); renderCurve();
        periodTable("e9-years", D.years, "Year"); periodTable("e9-months", D.months, "Month");
        renderTrades(); renderFoot();
        document.body.dataset.ready = "true";
      })
      .catch(function (e) { $("e9-sub").textContent = "Failed to load ema921.json: " + e.message; document.body.dataset.ready = "error"; });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
