/* Nifty best setup: EMA 21 / EMA 105 on 15-minute candles, always in. Renders best15.json (nifty_best15.py, after every close).
   All text via textContent. */
(function () {
  "use strict";
  var D = null, CH = null, SER = null, RANGE = "125";
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
  function openTrade() { return D.trades.length && D.trades[D.trades.length - 1].open ? D.trades[D.trades.length - 1] : null; }

  function renderNow() {
    var n = D.now, box = $("b5-now"), op = openTrade(); box.textContent = "";
    box.className = "e9-now" + (n.side === "SELL" ? " sell" : "");
    var st = el("div", "st"); st.appendChild(el("small", null, "Right now · last 15-minute candle " + n.time + " IST")); st.appendChild(document.createTextNode(n.state));
    box.appendChild(st);
    var ul = el("ul");
    ul.appendChild(el("li", null, "Nifty " + num(n.close, 2) + " · EMA 21 " + num(n.ema21, 2) + " · EMA 105 " + num(n.ema105, 2) +
      " (" + (n.ema21 > n.ema105 ? "21 above 105" : "21 below 105") + ")"));
    if (op) ul.appendChild(el("li", null, op.side + " since " + op.entry_time + " at " + num(op.entry, 2) + " · now " + spts(op.net_pts) + " points = " +
      sinr(op.rupees) + " on 1 lot, " + sinr(op.rupees * D.lots) + " on " + D.lots + " lots"));
    ul.appendChild(el("li", null, n.what));
    box.appendChild(ul);
  }

  function renderKpis() {
    var s = D.summary, box = $("b5-kpis"), L = D.lots; box.textContent = "";
    kpi(box, "Total since " + D.from + " · 1 lot", sinr(s.total_rs), spts(s.total_pts) + " points after costs", "main", s.total_rs > 0 ? "up" : "dn");
    kpi(box, L + " lots", sinr(s.total_rs_10), "worst fall " + inr(-s.max_dd_rs_10), "", s.total_rs_10 > 0 ? "up" : "dn");
    kpi(box, "Nifty bought & held", sinr(s.hold_rs), spts(s.hold_pts) + " points, 1 lot", "", s.hold_rs > 0 ? "up" : "dn");
    kpi(box, "Won", s.win_pct + "%", s.wins + " won · " + s.losses + " lost · " + s.trades_per_month + " trades a month");
    kpi(box, "Average win / loss", spts(s.avg_win_pts) + " / " + spts(s.avg_loss_pts), "points · profit factor " + (s.profit_factor == null ? "-" : s.profit_factor));
    kpi(box, "Worst fall", spts(-s.max_dd_pts) + " pts", inr(-s.max_dd_rs) + " on 1 lot" + (s.max_dd_on ? " · low " + s.max_dd_on : ""));
    kpi(box, "Before " + D.split + " / after", spts(s.pick_period_pts) + " / " + spts(s.unseen_period_pts), "points: the rule held up after it");
    kpi(box, "Open trade now", spts(s.open_pts) + " pts", "longest losing run: " + s.longest_losing_run + " trades", "", s.open_pts > 0 ? "up" : s.open_pts < 0 ? "dn" : null);
  }

  function renderChart() {
    var ch = D.chart, box = $("b5-chart");
    if (typeof LightweightCharts === "undefined") { box.textContent = "Chart library failed to load."; return; }
    CH = LightweightCharts.createChart(box, {
      autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
      grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } },
      rightPriceScale: { borderColor: "#e2e8f0" }, crosshair: { mode: 0 },
      timeScale: { borderColor: "#e2e8f0", timeVisible: true, secondsVisible: false, rightOffset: 6 }
    });
    SER = CH.addCandlestickSeries({ upColor: "#16a34a", downColor: "#dc2626", borderUpColor: "#16a34a", borderDownColor: "#dc2626", wickUpColor: "#16a34a", wickDownColor: "#dc2626" });
    SER.setData(ch.bars.map(function (b) { return { time: ts(b[0]), open: b[1], high: b[2], low: b[3], close: b[4] }; }));
    [["ema21", "#f97316", "EMA 21"], ["ema105", "#7c3aed", "EMA 105"]].forEach(function (z) {
      var l = CH.addLineSeries({ color: z[1], lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: z[2] });
      l.setData(ch.bars.map(function (b, j) { return ch[z[0]][j] == null ? { time: ts(b[0]) } : { time: ts(b[0]), value: ch[z[0]][j] }; }));
    });
    var op = openTrade();
    if (op) SER.createPriceLine({ price: op.entry, color: op.side === "BUY" ? "#15803d" : "#b91c1c", lineWidth: 1, lineStyle: 2, axisLabelVisible: true,
      title: "open " + op.side + " " + num(op.entry, 0) });
    drawMarkers(); renderRange();
    $("b5-chart-note").textContent = "15-minute candles in IST, the last " + ch.bars.length + " candles from " + ch.bars[0][0].slice(0, 10) +
      ". Each arrow sits on the candle the order fills at (the open of the candle after the crossover close). Drag to move, scroll to zoom.";
  }

  function drawMarkers() {
    var first = ts(D.chart.bars[0][0]), zoom = RANGE !== "all", m = [], prev = null;
    D.trades.forEach(function (t) {
      var x = ts(t.entry_time);
      if (x >= first) {
        var buy = t.side === "BUY", txt = t.side;
        if (zoom && prev && !prev.open) txt += " " + sinr(prev.rupees);
        m.push({ time: x, position: buy ? "belowBar" : "aboveBar", color: buy ? "#16a34a" : "#dc2626", shape: buy ? "arrowUp" : "arrowDown", text: zoom ? txt : "" });
      }
      prev = t;
    });
    SER.setMarkers(m);
  }

  function renderRange() {
    var box = $("b5-range"); box.textContent = "";
    [["25", "1 day"], ["125", "1 week"], ["500", "1 month"], ["1500", "3 months"], ["all", "1 year"]].forEach(function (r) {
      var b = el("button", RANGE === r[0] ? "on" : null, r[1]); b.type = "button";
      b.addEventListener("click", function () { RANGE = r[0]; renderRange(); drawMarkers(); });
      box.appendChild(b);
    });
    var n = D.chart.bars.length;
    if (RANGE === "all") CH.timeScale().fitContent();
    else CH.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - (+RANGE)), to: n + 4 });
  }

  function showTrade(t) {
    var bars = D.chart.bars, a = ts(t.entry_time), b = t.open ? ts(bars[bars.length - 1][0]) : ts(t.exit_time);
    if (b < ts(bars[0][0])) { $("b5-chart-note").textContent = "That trade is older than the chart's last year: " + t.entry_time + " → " + t.exit_time + "."; return; }
    var i0 = 0, i1 = bars.length - 1;
    for (var i = 0; i < bars.length; i++) { var x = ts(bars[i][0]); if (x <= a) i0 = i; if (x <= b) i1 = i; }
    RANGE = "trade"; Array.prototype.forEach.call($("b5-range").children, function (x) { x.classList.remove("on"); }); drawMarkers();
    CH.timeScale().setVisibleLogicalRange({ from: Math.max(0, i0 - 30), to: Math.min(bars.length + 4, i1 + 30) });
    $("b5-chart").scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function renderCurve() {
    if (typeof LightweightCharts === "undefined") return;
    var c = LightweightCharts.createChart($("b5-curve"), {
      autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
      grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } }, rightPriceScale: { borderColor: "#e2e8f0" },
      timeScale: { borderColor: "#e2e8f0" }, localization: { priceFormatter: function (v) { return "₹" + (v * D.lot / 1e5).toFixed(2) + " L"; } }
    });
    var s = c.addAreaSeries({ lineColor: "#16a34a", topColor: "#16a34a33", bottomColor: "#16a34a05", lineWidth: 2, priceLineVisible: false, title: "EMA 21/105" });
    s.setData(D.curve.map(function (x) { return { time: x[0], value: x[1] }; }));
    var h = c.addLineSeries({ color: "#94a3b8", lineWidth: 2, priceLineVisible: false, title: "Nifty held" });
    h.setData(D.curve.map(function (x) { return { time: x[0], value: x[2] }; }));
    c.timeScale().fitContent();
  }

  function renderYears() {
    var b = head($("b5-years"), [["Year"], ["Points", "num"], ["1 lot", "num"], [D.lots + " lots", "num"], ["Nifty held (pts)", "num"]]);
    var tot = 0;
    D.years_mtm.forEach(function (y) {
      var tr = el("tr"); td(tr, String(y.year) + (y.year === +D.from.slice(0, 4) ? " (from " + D.from.slice(5) + ")" : ""));
      td(tr, spts(y.pts), tone(y.pts)); td(tr, sinr(y.rupees), tone(y.rupees)); td(tr, sinr(y.rupees * D.lots), tone(y.rupees));
      td(tr, spts(y.hold_pts), tone(y.hold_pts)); b.appendChild(tr); tot += y.pts;
    });
    var s = D.summary, tr = el("tr", "fd-total"); td(tr, "Total"); td(tr, spts(s.total_pts), tone(s.total_pts)); td(tr, sinr(s.total_rs), tone(s.total_rs));
    td(tr, sinr(s.total_rs_10), tone(s.total_rs_10)); td(tr, spts(s.hold_pts), tone(s.hold_pts)); b.appendChild(tr);
  }

  function renderSides() {
    var s = D.summary, b = head($("b5-sides"), [["Side"], ["Closed trades", "num"], ["Won", "num"], ["Points", "num"], ["1 lot", "num"], [D.lots + " lots", "num"]]);
    [["BUY (long)", s.buy], ["SELL (short)", s.sell]].forEach(function (x) {
      var tr = el("tr"); td(tr, x[0]); td(tr, String(x[1].trades), "num"); td(tr, x[1].win_pct + "%", "num");
      td(tr, spts(x[1].pts), tone(x[1].pts)); td(tr, sinr(x[1].pts * D.lot), tone(x[1].pts)); td(tr, sinr(x[1].pts * D.lot * D.lots), tone(x[1].pts));
      b.appendChild(tr);
    });
    var tr = el("tr"); td(tr, "Open trade (" + (openTrade() ? openTrade().side : "-") + ")"); td(tr, ""); td(tr, "");
    td(tr, spts(s.open_pts), tone(s.open_pts)); td(tr, sinr(s.open_pts * D.lot), tone(s.open_pts)); td(tr, sinr(s.open_pts * D.lot * D.lots), tone(s.open_pts));
    b.appendChild(tr);
  }

  function renderMonths() {
    var b = head($("b5-months"), [["Month"], ["Trades", "num"], ["Won", "num"], ["Points", "num"], ["1 lot", "num"], [D.lots + " lots", "num"]]);
    D.months.slice().reverse().forEach(function (m) {
      var tr = el("tr"); td(tr, m.period); td(tr, String(m.trades), "num"); td(tr, m.wins + " (" + Math.round(m.wins / m.trades * 100) + "%)", "num");
      td(tr, spts(m.net_pts), tone(m.net_pts)); td(tr, sinr(m.rupees), tone(m.rupees)); td(tr, sinr(m.rupees * D.lots), tone(m.rupees)); b.appendChild(tr);
    });
  }

  function renderTrades() {
    var all = D.trades, acc = 0, run = [];
    all.forEach(function (t) { acc += t.net_pts; run.push(acc); });
    $("b5-tr-n").textContent = "· " + D.summary.trades + " closed" + (openTrade() ? " + 1 open" : "") + " since " + D.from + ", newest first";
    var b = head($("b5-trades"), [["#", "num"], ["Side"], ["Signal (close)"], ["Entry (open)"], ["Entry", "num"], ["Exit (open)"], ["Exit", "num"],
      ["Held", "num"], ["Points", "num"], ["1 lot", "num"], [D.lots + " lots", "num"], ["Running pts", "num"]]);
    all.slice().reverse().forEach(function (t, k) {
      var i = all.length - 1 - k, tr = el("tr", t.open ? "open" : null);
      td(tr, String(i + 1), "num"); td(tr, t.side, "side-" + t.side); td(tr, t.signal_time); td(tr, t.entry_time); td(tr, num(t.entry, 2), "num");
      td(tr, t.open ? "OPEN · last close" : t.exit_time); td(tr, num(t.exit, 2), "num"); td(tr, t.days + "d · " + t.candles + " candles", "num");
      td(tr, spts(t.net_pts), tone(t.net_pts)); td(tr, sinr(t.rupees), tone(t.rupees)); td(tr, sinr(t.rupees * D.lots), tone(t.rupees));
      td(tr, spts(run[i]), tone(run[i]));
      tr.title = "Show this trade on the chart";
      tr.addEventListener("click", function () { showTrade(t); });
      b.appendChild(tr);
    });
  }

  function renderFoot() {
    var r = $("b5-rule"); r.textContent = ""; D.rule.forEach(function (x) { r.appendChild(el("li", null, x)); });
    var w = $("b5-why"); w.textContent = ""; D.why.forEach(function (x) { w.appendChild(el("li", null, x)); });
    var d = D.data, ul = $("b5-data"); ul.textContent = "";
    ul.appendChild(el("li", null, "Source: " + D.source + ". " + d.sessions + " sessions on file, " + d.from + " → " + d.to + "."));
    if (d.vs_nse) {
      var f = d.vs_nse.fields;
      ul.appendChild(el("li", null, "Against NSE's official daily Nifty 50 file on " + d.vs_nse.days + " days: open, high and low match (median gap " +
        f.open.median_pts + " / " + f.high.median_pts + " / " + f.low.median_pts + " points). The last candle's close differs from NSE's official close by a median " +
        f.close.median_pts + " points, because NSE's official close is an average of the last 30 minutes; this rule uses candle closes like TradingView."));
    }
    if (d.vs_yahoo_15m) ul.appendChild(el("li", null, "Against the Yahoo Finance 15-minute candles we keep: " + d.vs_yahoo_15m.bars + " candles, median close gap " + d.vs_yahoo_15m.median_pts + " points."));
    var l = $("b5-limits"); l.textContent = ""; D.limits.forEach(function (x) { l.appendChild(el("li", null, x)); });
  }

  function loadPine() {
    var pre = $("b5-pine"), btn = $("b5-copy"), msg = $("b5-copy-msg");
    if (!pre) return;
    fetch("best15.pine?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.text(); })
      .then(function (txt) {
        pre.textContent = txt;
        pre.dataset.ready = "true";
        btn.addEventListener("click", function () {
          function done(ok) { msg.textContent = ok ? "Copied. Paste it into TradingView's Pine Editor." : "Select the text below and copy it."; }
          if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(txt).then(function () { done(true); }, function () { done(false); });
          } else {
            var r = document.createRange(); r.selectNodeContents(pre);
            var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
            var ok = false; try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
            done(ok);
          }
        });
      })
      .catch(function (e) { pre.textContent = "Could not load best15.pine: " + e.message; });
  }
  function boot() {
    fetch("best15.json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        D = d;
        $("b5-sub").textContent = "EMA 21 / EMA 105 on 15-minute Nifty candles · " + D.from + " → " + D.last_candle + " IST · " + D.summary.trades +
          " closed trades · rebuilt " + D.generated_at.replace("T", " ").slice(0, 16);
        renderNow(); renderKpis(); renderChart(); renderCurve(); renderYears(); renderSides(); renderMonths(); renderTrades(); renderFoot();
        document.body.dataset.ready = "true";
      })
      .catch(function (e) { $("b5-sub").textContent = "Failed to load best15.json: " + e.message; document.body.dataset.ready = "error"; });
  }
  function start() { loadPine(); boot(); }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", start) : start();
})();
