/* Nifty best setup: EMA 21 / EMA 105 on 15-minute candles, always in. Renders best15.json (nifty_best15.py, after every close).
   All text via textContent. */
(function () {
  "use strict";
  var D = null, CH = null, SER = null, RANGE = "125";
  var LSER = {}, LIVE = { force: false, state: null, form: null, price: null, ptime: null, flipLine: null, timer: null, fails: 0, flips: [] };
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
    ul.appendChild(el("li", null, "Nifty " + num(n.close, 2) + " · " + D.fast_label + " " + num(n.ema21, 2) + " · " + D.slow_label + " " + num(n.ema105, 2) +
      " (" + (n.ema21 > n.ema105 ? "fast above slow" : "fast below slow") + ")"));
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
    [["ema21", "#f97316", D.fast_label || "EMA 21"], ["ema105", "#7c3aed", D.slow_label || "EMA 105"]].forEach(function (z) {
      var l = CH.addLineSeries({ color: z[1], lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: z[2] });
      l.setData(ch.bars.map(function (b, j) { return ch[z[0]][j] == null ? { time: ts(b[0]) } : { time: ts(b[0]), value: ch[z[0]][j] }; }));
      LSER[z[0]] = l;
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
    (LIVE.flips || []).forEach(function (f) {
      var buy = f.side === "BUY";
      m.push({ time: ts(f.entry_time), position: buy ? "belowBar" : "aboveBar", color: buy ? "#16a34a" : "#dc2626",
               shape: buy ? "arrowUp" : "arrowDown", text: zoom ? f.side + " LIVE" : "" });
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
    fetch((document.body.dataset.pine || "best15.pine") + "?v=" + Date.now(), { cache: "no-store" })
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
      .catch(function (e) { pre.textContent = "Could not load the script: " + e.message; });
  }

  /* ---- live: during market hours the browser extends the chart straight from Upstox's public
     candle API (it sends CORS headers for this site; no account, no keys). The maths is the same
     recursion as the engine: EMA = a*close + (1-a)*previous, flips fill at the next 15-min open. ---- */
  var AF = 2 / 22, AS = 2 / 106;              // set from D in liveInit
  function emaStep(prev, close, a) { return a * close + (1 - a) * prev; }
  function sumTail(w, n) { var s = 0, k = Math.min(n, w.length); for (var i = w.length - k; i < w.length; i++) s += w[i]; return s; }
  function avgTail(w, n) { return sumTail(w, n) / Math.min(n, w.length); }
  function maState(base) { return { f: base.ema21, s: base.ema105, win: base.closes ? base.closes.slice() : null }; }
  function maPush(st, close) {              // a COMPLETED candle extends the averages
    if (st.win) {
      st.win.push(close); if (st.win.length > D.slow) st.win.shift();
      st.f = avgTail(st.win, D.fast); st.s = avgTail(st.win, D.slow);
    } else { st.f = emaStep(st.f, close, AF); st.s = emaStep(st.s, close, AS); }
  }
  function maPreview(st, close) {           // what the averages would be if the forming candle closed now
    if (st.win) { var w = st.win.concat([close]); return [avgTail(w, D.fast), avgTail(w, D.slow)]; }
    return [emaStep(st.f, close, AF), emaStep(st.s, close, AS)];
  }
  function flipPrice(st) {                  // the one next close that puts fast exactly on slow
    if (st.win) return (D.fast * sumTail(st.win, D.slow - 1) - D.slow * sumTail(st.win, D.fast - 1)) / (D.slow - D.fast);
    return ((1 - AS) * st.s - (1 - AF) * st.f) / (AF - AS);
  }
  function istNow() { var d = new Date(); return new Date(d.getTime() + (330 + d.getTimezoneOffset()) * 60000); }
  function pad2(n) { return (n < 10 ? "0" : "") + n; }
  function istStamp(d) {
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate()) + " " + pad2(d.getHours()) + ":" + pad2(d.getMinutes());
  }
  function hm(d) { return d.getHours() * 60 + d.getMinutes() + d.getSeconds() / 60; }
  function marketOpen(d) { return d.getDay() > 0 && d.getDay() < 6 && hm(d) >= 555 && hm(d) < 930.5; }
  function nextOpen(d) {
    var x = new Date(d.getTime());
    if (hm(x) >= 555) x.setDate(x.getDate() + 1);
    while (x.getDay() === 0 || x.getDay() === 6) x.setDate(x.getDate() + 1);
    return istStamp(x).slice(0, 10) + " 09:15";
  }
  /* 1-minute rows [ts,o,h,l,c,...] in any order -> ascending 15-minute candles anchored at 09:15 */
  function agg15(rows) {
    var by = {};
    rows.forEach(function (r) {
      var t = String(r[0]).replace("T", " ").slice(0, 16);
      var m = +t.slice(11, 13) * 60 + +t.slice(14, 16);
      if (m < 555 || m >= 930) return;
      var b = 555 + 15 * Math.floor((m - 555) / 15);
      var k = t.slice(0, 10) + " " + pad2(Math.floor(b / 60)) + ":" + pad2(b % 60);
      var x = by[k];
      if (!x) by[k] = { t: k, m0: m, m1: m, o: +r[1], h: +r[2], l: +r[3], c: +r[4] };
      else {
        x.h = Math.max(x.h, +r[2]); x.l = Math.min(x.l, +r[3]);
        if (m < x.m0) { x.m0 = m; x.o = +r[1]; }
        if (m >= x.m1) { x.m1 = m; x.c = +r[4]; }
      }
    });
    return Object.keys(by).sort().map(function (k) { return by[k]; });
  }
  /* continue the EMAs over completed candles; a pending flip fills at the next candle's open */
  function contState(base, done) {
    var s = { ma: maState(base), want: base.side, path: [], flips: [],
              trade: { side: base.pending ? (base.side === "BUY" ? "SELL" : "BUY") : base.side, entry: base.entry, entry_time: base.entry_time } };
    done.forEach(function (c) {
      if (s.want !== s.trade.side) { s.trade = { side: s.want, entry: c.o, entry_time: c.t }; s.flips.push(s.trade); }
      maPush(s.ma, c.c);
      s.want = s.ma.f > s.ma.s ? "BUY" : "SELL";
      s.path.push({ t: c.t, e21: s.ma.f, e105: s.ma.s });
    });
    s.ema21 = s.ma.f; s.ema105 = s.ma.s;
    return s;
  }
  function liveApply(all) {
    var Lb = D.live, nowI = istNow(), nm = hm(nowI), today = istStamp(nowI).slice(0, 10);
    var done = [], form = null;
    all.forEach(function (c) {
      if (c.t <= Lb.time) return;
      var b = +c.t.slice(11, 13) * 60 + +c.t.slice(14, 16);
      var later = all.some(function (x) { return x.t.slice(0, 10) === c.t.slice(0, 10) && x.m0 >= b + 15; });
      var byClock = !LIVE.force && (c.t.slice(0, 10) < today || nm >= b + 15.3);
      if (later || byClock) done.push(c); else form = c;
    });
    LIVE.gap = 0;
    if (all.length) {   // weekdays missing between the published state and the feed's day (holiday or a missed rebuild)
      var d0 = new Date(Lb.time.slice(0, 10) + "T12:00:00Z"), d1 = new Date(all[0].t.slice(0, 10) + "T12:00:00Z");
      for (var g = new Date(d0.getTime() + 864e5); g < d1; g = new Date(g.getTime() + 864e5)) {
        if (g.getUTCDay() > 0 && g.getUTCDay() < 6) LIVE.gap++;
      }
    }
    var st = contState(Lb, done);
    LIVE.state = st; LIVE.form = form;
    LIVE.price = form ? form.c : done.length ? done[done.length - 1].c : D.now.close;
    LIVE.ptime = form ? form.t : done.length ? done[done.length - 1].t : D.now.time;
    if (SER) {
      done.concat(form ? [form] : []).forEach(function (c) { SER.update({ time: ts(c.t), open: c.o, high: c.h, low: c.l, close: c.c }); });
      st.path.forEach(function (p) {
        if (!LSER.ema21) return;
        LSER.ema21.update({ time: ts(p.t), value: +p.e21.toFixed(2) });
        LSER.ema105.update({ time: ts(p.t), value: +p.e105.toFixed(2) });
      });
      if (form && LSER.ema21) {
        var pv = maPreview(st.ma, form.c);
        LSER.ema21.update({ time: ts(form.t), value: +pv[0].toFixed(2) });
        LSER.ema105.update({ time: ts(form.t), value: +pv[1].toFixed(2) });
      }
      if (st.flips.length) { LIVE.flips = st.flips; drawMarkers(); }
      var fp = flipPrice(st.ma);
      if (LIVE.flipLine) SER.removePriceLine(LIVE.flipLine);
      LIVE.flipLine = SER.createPriceLine({ price: +fp.toFixed(2), color: "#b8860b", lineWidth: 1, lineStyle: 3, axisLabelVisible: true,
        title: (st.want === "BUY" ? "flip to SELL " : "flip to BUY ") + Math.round(fp) });
    }
    renderLive();
  }
  function renderLive() {
    var box = $("b5-live"); if (!box || !D || !D.live) return;
    var n = istNow(), open = LIVE.force || marketOpen(n);
    var base = D.live, st = LIVE.state;
    var e21 = st ? st.ema21 : base.ema21, e105 = st ? st.ema105 : base.ema105;
    var want = st ? st.want : base.side;
    var tr = st ? st.trade : { side: base.pending ? (base.side === "BUY" ? "SELL" : "BUY") : base.side, entry: base.entry, entry_time: base.entry_time };
    var price = LIVE.price != null ? LIVE.price : D.now.close;
    var pending = want !== tr.side;
    var fp = flipPrice(st ? st.ma : maState(base));
    var opn = isNum(tr.entry) ? (tr.side === "BUY" ? price - tr.entry : tr.entry - price) : null;
    box.textContent = "";
    box.className = "b5-live " + (pending ? "flip" : tr.side === "BUY" ? "buy" : "sell");
    box.dataset.side = tr.side; box.dataset.want = want; box.dataset.live = open ? "on" : "off";
    box.dataset.e21 = e21.toFixed(4); box.dataset.e105 = e105.toFixed(4); box.dataset.flip = fp.toFixed(2);
    box.dataset.entry = isNum(tr.entry) ? String(tr.entry) : ""; box.dataset.price = String(price);
    var top = el("div", "b5l-top");
    top.appendChild(el("span", "b5l-dot" + (open ? " on" : "")));
    top.appendChild(el("b", null, open ? "LIVE · NIFTY 50 · 15-MIN" : "MARKET CLOSED"));
    top.appendChild(el("span", "b5l-price", num(price, 2)));
    if (st || LIVE.form) {
      var chg = price - D.now.close;
      top.appendChild(el("span", "b5l-chg " + (chg >= 0 ? "up" : "dn"), spts(chg) + " vs last published close"));
    }
    if (!open) top.appendChild(el("span", "b5l-when", "last candle " + (LIVE.ptime || D.now.time) + " IST · live again " + nextOpen(n) + " IST"));
    var ck = el("span", "b5l-clock"); ck.id = "b5l-clock"; top.appendChild(ck);
    box.appendChild(top);
    var act = el("div", "b5l-act");
    act.textContent = pending ? "FLIP: " + want + " AT THE NEXT 15-MINUTE OPEN"
      : open ? "STAY IN " + tr.side : tr.side + " — unchanged while the market is closed";
    box.appendChild(act);
    if (isNum(tr.entry)) box.appendChild(el("div", "b5l-sub", tr.side + " since " + tr.entry_time + " at " + num(tr.entry, 2) +
      " · open " + spts(opn) + " pts = " + sinr(opn * D.lot) + " on 1 lot · " + sinr(opn * D.lot * D.lots) + " on " + D.lots + " lots"));
    var dist = want === "BUY" ? price - fp : fp - price;
    box.appendChild(el("div", "b5l-next", "NEXT OPPORTUNITY → " + (want === "BUY" ? "SELL" : "BUY") + " if a 15-minute candle CLOSES " +
      (want === "BUY" ? "below " : "above ") + num(fp, 2) + " · " + num(Math.abs(dist), 0) + " pts away · " + D.fast_label + " " + num(e21, 2) +
      " · " + D.slow_label + " " + num(e105, 2) + " · not in yet? the side to be on is " + want + ", entries always at the next 15-min open"));
    if (LIVE.fails > 1) box.appendChild(el("div", "b5l-err", "Live feed unreachable (try " + LIVE.fails + ") — retrying with the last good state."));
    if (LIVE.gap > 0) box.appendChild(el("div", "b5l-err", "Note: " + LIVE.gap + " weekday session(s) between the published state (" +
      D.live.time + ") and today are not in the EMAs yet (holiday or a missed rebuild). Tonight's rebuild corrects this."));
    if (st && st.flips.length) box.appendChild(el("div", "b5l-flipnote", "FLIPPED TODAY: " + st.flips.map(function (f) {
      return f.side + " at " + num(f.entry, 2) + " (" + f.entry_time.slice(11) + ")"; }).join(" · ")));
    clockTick();
  }
  function clockTick() {
    var c = $("b5l-clock"); if (!c) return;
    var n = istNow();
    if (!(LIVE.force || marketOpen(n))) { c.textContent = ""; return; }
    var left = Math.max(0, Math.round((15 - ((hm(n) - 555) % 15)) * 60));
    c.textContent = istStamp(n).slice(11) + ":" + pad2(n.getSeconds()) + " IST · candle closes in " + Math.floor(left / 60) + ":" + pad2(left % 60);
  }
  function liveLoop() {
    var n = istNow(), open = LIVE.force || marketOpen(n);
    if (open) {
      fetch(D.live.feed, { cache: "no-store" })
        .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
        .then(function (j) { LIVE.fails = 0; liveApply(agg15((j.data && j.data.candles) || [])); })
        .catch(function () { LIVE.fails++; renderLive(); });
    } else renderLive();
    var ms = open ? (D.live.poll_s || 30) * 1000 : 60000;
    LIVE.timer = setTimeout(liveLoop, document.hidden ? Math.max(ms, 120000) : ms);
  }
  function liveInit() {
    if (!D.live || !$("b5-live")) return;
    var q = {}; location.search.replace(/[?&]([^=&]+)=([^&]*)/g, function (a, k, v) { q[k] = v; return a; });
    if (q.live === "off") return;
    LIVE.force = q.live === "force";
    AF = 2 / (D.fast + 1); AS = 2 / (D.slow + 1);
    window.__b5 = { agg15: agg15, emaStep: emaStep, contState: contState, flipPrice: flipPrice, maState: maState, maPreview: maPreview, LIVE: LIVE };
    renderLive(); liveLoop(); setInterval(clockTick, 1000);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) { clearTimeout(LIVE.timer); liveLoop(); } });
  }
  function boot() {
    fetch((document.body.dataset.src || "best15.json") + "?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        D = d;
        $("b5-sub").textContent = D.fast_label + " / " + D.slow_label + " on 15-minute Nifty candles · " + D.from + " → " + D.last_candle + " IST · " + D.summary.trades +
          " closed trades · rebuilt " + D.generated_at.replace("T", " ").slice(0, 16);
        renderNow(); renderKpis(); renderChart(); renderCurve(); renderYears(); renderSides(); renderMonths(); renderTrades(); renderFoot();
        liveInit();
        document.body.dataset.ready = "true";
      })
      .catch(function (e) { $("b5-sub").textContent = "Failed to load the data: " + e.message; document.body.dataset.ready = "error"; });
  }
  function start() { loadPine(); boot(); }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", start) : start();
})();
