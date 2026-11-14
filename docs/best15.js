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
    if (D.compare) {
      var dv = s.total_pts - D.compare.always_in.total_pts;
      kpi(box, "vs always-in · same entries", spts(dv) + " pts", sinr(dv * D.lot * L) + " on " + L + " lots · " + D.compare.booked_exits + " profits booked", "", dv > 0 ? "up" : "dn");
    }
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
    if (D.book) drawBookLine(baseTrade());
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
        if (zoom && prev && !prev.open && prev.exit_reason !== "book") txt += " " + sinr(prev.rupees);
        m.push({ time: x, position: buy ? "belowBar" : "aboveBar", color: buy ? "#16a34a" : "#dc2626", shape: buy ? "arrowUp" : "arrowDown", text: zoom ? txt : "" });
      }
      if (t.exit_reason === "book" && ts(t.exit_time) >= first) {     // fib profit booking (booking pages only)
        m.push({ time: ts(t.exit_time), position: t.side === "BUY" ? "aboveBar" : "belowBar", color: "#b45309", shape: "circle",
                 text: zoom ? "BOOK " + sinr(t.rupees) : "" });
      }
      prev = t;
    });
    (LIVE.flips || []).forEach(function (f) {
      var buy = f.side === "BUY";
      m.push({ time: ts(f.entry_time), position: buy ? "belowBar" : "aboveBar", color: buy ? "#16a34a" : "#dc2626",
               shape: buy ? "arrowUp" : "arrowDown", text: zoom ? f.side + " LIVE" : "" });
    });
    (LIVE.books || []).forEach(function (f) {
      m.push({ time: ts(f.time), position: f.side === "BUY" ? "aboveBar" : "belowBar", color: "#b45309", shape: "circle", text: zoom ? "BOOK LIVE" : "" });
    });
    m.sort(function (a, b) { return a.time - b.time; });
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
    var all = D.trades, acc = 0, run = [], bk = !!D.book;
    all.forEach(function (t) { acc += t.net_pts; run.push(acc); });
    $("b5-tr-n").textContent = "· " + D.summary.trades + " closed" + (openTrade() ? " + 1 open" : "") + " since " + D.from + ", newest first" +
      (bk && D.compare ? " · " + D.compare.booked_exits + " booked, " + D.compare.crossover_exits + " closed by the next crossover" : "");
    var cols = [["#", "num"], ["Side"], ["Signal (close)"], ["Entry (open)"], ["Entry", "num"], ["Exit (open)"], ["Exit", "num"]];
    if (bk) cols = cols.concat([["Exit by"], ["Best price", "num"], ["Book line", "num"]]);
    cols = cols.concat([["Held", "num"], ["Points", "num"], ["1 lot", "num"], [D.lots + " lots", "num"], ["Running pts", "num"]]);
    var b = head($("b5-trades"), cols);
    all.slice().reverse().forEach(function (t, k) {
      var i = all.length - 1 - k, tr = el("tr", t.open ? "open" : null);
      td(tr, String(i + 1), "num"); td(tr, t.side, "side-" + t.side); td(tr, t.signal_time); td(tr, t.entry_time); td(tr, num(t.entry, 2), "num");
      td(tr, t.open ? "OPEN · last close" : t.exit_time); td(tr, num(t.exit, 2), "num");
      if (bk) {
        td(tr, t.open ? "-" : t.exit_reason === "book" ? "BOOK (fib)" : "crossover", t.exit_reason === "book" ? "side-BOOK" : null);
        td(tr, num(t.best, 2), "num"); td(tr, t.book_level == null ? "-" : num(t.book_level, 2), "num");
      }
      td(tr, t.days + "d · " + t.candles + " candles", "num");
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

  /* booking pages only: always-in vs fib booking, and the current trade's booking maths step by step */
  function renderBook() {
    if (!$("b5-book") || !D.compare) return;
    var a = D.compare.always_in, c = D.compare.book, L = D.lots, lp = D.lot * L, B = D.book;
    var tb = head($("b5-book-cmp"), [["Since " + D.from], ["Always in (6/200 page)", "num"], ["With fib booking", "num"], ["Difference", "num"]]);
    function fmt(v, k) { return k === "rs" ? sinr(v) : k === "pct" ? num(v, 1) + "%" : k === "n" ? num(v, 0) : spts(v); }
    function row(label, x, y, k) {
      var tr = el("tr"), d = y - x;
      td(tr, label); td(tr, fmt(x, k), "num"); td(tr, fmt(y, k), "num");
      td(tr, k === "rs" ? sinr(d) : k === "n" ? String(d) : spts(d) + (k === "pct" ? " pts" : ""), k === "n" ? "num" : tone(d));
      tb.appendChild(tr);
    }
    row("Total points", a.total_pts, c.total_pts, "pts");
    row("₹ on " + L + " lots", a.total_pts * lp, c.total_pts * lp, "rs");
    row("Last 200 sessions (points)", a.last200_pts, c.last200_pts, "pts");
    row("Worst fall (points)", -a.max_dd_pts, -c.max_dd_pts, "pts");
    row("Won", a.win_pct, c.win_pct, "pct");
    row("Closed trades", a.trades, c.trades, "n");
    var n = D.now.book, ul = $("b5-book-now"), op = openTrade(); ul.textContent = "";
    if (!n.position || !op) { ul.appendChild(el("li", null, "No open trade: the last trade's profit was booked. " + D.now.what)); }
    else {
      var p = n.position === "BUY" ? 1 : -1, g = p * (n.best - op.entry);
      ul.appendChild(el("li", null, n.position + " entry " + num(op.entry, 2) + " (" + op.entry_time + ") · best price since the entry " + num(n.best, 2) +
        " · best open profit " + spts(g) + " points"));
      ul.appendChild(el("li", null, "Booking switches on at entry × (1 " + (p > 0 ? "+" : "−") + " " + B.act_pct + "%) = " + num(n.activate_at, 2) +
        (n.armed ? " · reached" : " · not reached yet")));
      if (n.armed) {
        ul.appendChild(el("li", null, "Booking line = best " + (p > 0 ? "−" : "+") + " " + B.frac + " × best open profit = " + num(n.best, 2) +
          (p > 0 ? " − " : " + ") + B.frac + " × " + num(g, 2) + " = " + num(n.level, 2)));
        ul.appendChild(el("li", null, "A 15-minute close " + (p > 0 ? "below " : "above ") + num(n.level, 2) + " books the trade at the next open: about " +
          spts(n.locked_pts) + " points after costs = " + sinr(n.locked_pts * lp) + " on " + L + " lots, before the " + B.slip_pts + "-point slippage."));
      }
    }
    ul.appendChild(el("li", null, "Check any booked trade in the table below: book line = best − " + B.frac + " × (best − entry) for a BUY, best + " + B.frac +
      " × (entry − best) for a SELL; exit = the next open " + "− " + B.slip_pts + " points for a BUY (+ for a SELL); points = (exit − entry) for a BUY, " +
      "(entry − exit) for a SELL, minus " + D.cost_side_pct.toFixed(3) + "% × (entry + exit)."));
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
  /* booking pages: same averages and crossover fills, plus the fib booking; flat after a booking until the next crossover */
  function bookLevel(t) {
    var B = D.live.book, p = t.side === "BUY" ? 1 : -1, g = p * (t.best - t.entry);
    return g > 0 && g >= t.entry * B.act ? t.best - p * B.frac * g : null;
  }
  function baseTrade() {
    var B = D.live.book;
    return B && B.pos ? { side: B.pos, entry: D.live.entry, entry_time: D.live.entry_time, best: B.best } : null;
  }
  function contBook(base, done) {
    var s = { ma: maState(base), want: base.side, path: [], flips: [], books: [], cross: !!base.pending, pend: !!base.book.pend, trade: baseTrade() };
    done.forEach(function (c) {
      if (s.cross) {
        s.trade = { side: s.want, entry: c.o, entry_time: c.t, best: c.o }; s.flips.push(s.trade); s.pend = false;
      } else if (s.pend && s.trade) {
        s.books.push({ side: s.trade.side, time: c.t, price: c.o - (s.trade.side === "BUY" ? 1 : -1) * D.live.book.slip });
        s.trade = null; s.pend = false;
      }
      var prev = s.want;
      maPush(s.ma, c.c);
      s.want = s.ma.f > s.ma.s ? "BUY" : "SELL";
      s.cross = s.want !== prev;
      if (s.trade) {
        var t = s.trade, p = t.side === "BUY" ? 1 : -1;
        t.best = p > 0 ? Math.max(t.best, c.h) : Math.min(t.best, c.l);
        var lv = bookLevel(t);
        if (lv != null && (p > 0 ? c.c <= lv : c.c >= lv)) s.pend = true;
      }
      s.path.push({ t: c.t, e21: s.ma.f, e105: s.ma.s });
    });
    s.ema21 = s.ma.f; s.ema105 = s.ma.s;
    return s;
  }
  function drawBookLine(tr) {
    if (!SER || !D.book) return;
    if (LIVE.bookLine) { SER.removePriceLine(LIVE.bookLine); LIVE.bookLine = null; }
    if (!tr) return;
    var p = tr.side === "BUY" ? 1 : -1, lv = bookLevel(tr), on = lv != null, px = on ? lv : tr.entry * (1 + p * D.live.book.act);
    LIVE.bookLine = SER.createPriceLine({ price: +px.toFixed(2), color: "#b45309", lineWidth: 2, lineStyle: on ? 0 : 1, axisLabelVisible: true,
      title: on ? "book profit " + Math.round(px) : "booking starts " + Math.round(px) });
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
    var st = D.book ? contBook(Lb, done) : contState(Lb, done);
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
      if (st.flips.length || (st.books && st.books.length)) { LIVE.flips = st.flips; LIVE.books = st.books || []; drawMarkers(); }
      var fp = flipPrice(st.ma);
      if (LIVE.flipLine) SER.removePriceLine(LIVE.flipLine);
      LIVE.flipLine = SER.createPriceLine({ price: +fp.toFixed(2), color: "#b8860b", lineWidth: 1, lineStyle: 3, axisLabelVisible: true,
        title: (st.want === "BUY" ? "flip to SELL " : "flip to BUY ") + Math.round(fp) });
      if (D.book) drawBookLine(st.trade);
    }
    renderLive();
  }
  /* ---- optional Kotak tick layer (?kotak=1): a read-only local bridge on YOUR machine
     (kotak_ticker.py -> http://127.0.0.1:8745/nifty) feeds second-level prices into the
     forming candle. Flips still come only from CLOSED candles, exactly like the backtest. ---- */
  var TICK = { on: false, last: 0 };
  function tickMerge(ltp) {
    var n = istNow();
    if (!isNum(ltp) || !D || !D.live || !(LIVE.force || marketOpen(n))) return;
    var m = Math.floor(hm(n)), b = 555 + 15 * Math.floor((m - 555) / 15);
    var key = istStamp(n).slice(0, 10) + " " + pad2(Math.floor(b / 60)) + ":" + pad2(b % 60);
    if (LIVE.form && LIVE.form.t === key) {
      var f = LIVE.form;
      f.c = ltp; f.h = Math.max(f.h, ltp); f.l = Math.min(f.l, ltp); f.m1 = m;
    } else if (!LIVE.form || LIVE.form.t < key) {
      LIVE.form = { t: key, m0: m, m1: m, o: ltp, h: ltp, l: ltp, c: ltp };
    }
    LIVE.price = ltp; LIVE.ptime = key;
    var st = LIVE.state || { ma: maState(D.live) };
    if (SER && LIVE.form) {
      SER.update({ time: ts(LIVE.form.t), open: LIVE.form.o, high: LIVE.form.h, low: LIVE.form.l, close: LIVE.form.c });
      if (LSER.ema21) {
        var pv = maPreview(st.ma, LIVE.form.c);
        LSER.ema21.update({ time: ts(LIVE.form.t), value: +pv[0].toFixed(2) });
        LSER.ema105.update({ time: ts(LIVE.form.t), value: +pv[1].toFixed(2) });
      }
    }
    renderLive();
  }
  function tickLoop() {
    fetch("http://127.0.0.1:8745/nifty", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (j) { if (j && isNum(j.ltp)) { TICK.last = Date.now(); tickMerge(j.ltp); } })
      .catch(function () { });
  }

  function liveTop(box, open, n, price) {
    var top = el("div", "b5l-top");
    top.appendChild(el("span", "b5l-dot" + (open ? " on" : "")));
    top.appendChild(el("b", null, open ? "LIVE · NIFTY 50 · 15-MIN" : "MARKET CLOSED"));
    if (TICK.on && Date.now() - TICK.last < 10000) top.appendChild(el("span", "b5l-tickbadge", "KOTAK TICKS"));
    top.appendChild(el("span", "b5l-price", num(price, 2)));
    if (LIVE.state || LIVE.form) {
      var chg = price - D.now.close;
      top.appendChild(el("span", "b5l-chg " + (chg >= 0 ? "up" : "dn"), spts(chg) + " vs last published close"));
    }
    if (!open) top.appendChild(el("span", "b5l-when", "last candle " + (LIVE.ptime || D.now.time) + " IST · live again " + nextOpen(n) + " IST"));
    var ck = el("span", "b5l-clock"); ck.id = "b5l-clock"; top.appendChild(ck);
    box.appendChild(top);
  }
  function renderLiveBook() {
    var box = $("b5-live"), n = istNow(), open = LIVE.force || marketOpen(n);
    var base = D.live, st = LIVE.state, B = base.book;
    var e21 = st ? st.ema21 : base.ema21, e105 = st ? st.ema105 : base.ema105;
    var want = st ? st.want : base.side;
    var tr = st ? st.trade : baseTrade();
    var cross = st ? st.cross : !!base.pending, pend = !cross && (st ? st.pend : !!B.pend) && !!tr;
    var price = LIVE.price != null ? LIVE.price : D.now.close;
    var fp = flipPrice(st ? st.ma : maState(base)), lv = tr ? bookLevel(tr) : null;
    box.textContent = "";
    box.className = "b5-live " + (cross || pend ? "flip" : !tr ? "flat" : tr.side === "BUY" ? "buy" : "sell");
    box.dataset.side = tr ? tr.side : "FLAT"; box.dataset.want = want; box.dataset.live = open ? "on" : "off";
    box.dataset.e21 = e21.toFixed(4); box.dataset.e105 = e105.toFixed(4); box.dataset.flip = fp.toFixed(2);
    box.dataset.book = lv != null ? lv.toFixed(2) : ""; box.dataset.price = String(price);
    liveTop(box, open, n, price);
    var act = el("div", "b5l-act");
    act.textContent = cross ? "NEW SIGNAL: " + want + " AT THE NEXT 15-MINUTE OPEN"
      : pend ? "BOOK " + tr.side + " PROFIT AT THE NEXT 15-MINUTE OPEN"
      : !tr ? "FLAT · profit booked, wait for the next 6/200 signal"
      : open ? "STAY IN " + tr.side : tr.side + " — unchanged while the market is closed";
    box.appendChild(act);
    if (tr) {
      var p = tr.side === "BUY" ? 1 : -1, opn = p * (price - tr.entry);
      box.appendChild(el("div", "b5l-sub", tr.side + " since " + tr.entry_time + " at " + num(tr.entry, 2) + " · best " + num(tr.best, 2) + " · open " +
        spts(opn) + " pts = " + sinr(opn * D.lot) + " on 1 lot · " + sinr(opn * D.lot * D.lots) + " on " + D.lots + " lots"));
      box.appendChild(el("div", "b5l-next", lv != null
        ? "PROFIT BOOKING LINE → book if a 15-minute candle CLOSES " + (p > 0 ? "below " : "above ") + num(lv, 2) + " (half of the best open profit) · " +
          num(Math.abs(price - lv), 0) + " pts away · keeps about " + spts(p * (lv - tr.entry)) + " pts"
        : "PROFIT BOOKING switches on at " + num(tr.entry * (1 + p * B.act), 2) + " (+" + num(B.act * 100, 1) + "% from the entry)"));
    }
    box.appendChild(el("div", "b5l-next", "NEXT 6/200 SIGNAL → " + (want === "BUY" ? "SELL" : "BUY") + " if a 15-minute candle CLOSES " +
      (want === "BUY" ? "below " : "above ") + num(fp, 2) + " · " + num(Math.abs(price - fp), 0) + " pts away · " + D.fast_label + " " + num(e21, 2) +
      " · " + D.slow_label + " " + num(e105, 2)));
    if (LIVE.fails > 1) box.appendChild(el("div", "b5l-err", "Live feed unreachable (try " + LIVE.fails + ") — retrying with the last good state."));
    if (LIVE.gap > 0) box.appendChild(el("div", "b5l-err", "Note: " + LIVE.gap + " weekday session(s) between the published state (" +
      D.live.time + ") and today are not in the averages yet (holiday or a missed rebuild). Tonight's rebuild corrects this."));
    var notes = (st ? st.flips : []).map(function (f) { return f.side + " at " + num(f.entry, 2) + " (" + f.entry_time.slice(11) + ")"; })
      .concat((st ? st.books : []).map(function (b) { return "BOOKED " + b.side + " at " + num(b.price, 2) + " (" + b.time.slice(11) + ")"; }));
    if (notes.length) box.appendChild(el("div", "b5l-flipnote", "TODAY: " + notes.join(" · ")));
    clockTick();
  }
  function renderLive() {
    var box = $("b5-live"); if (!box || !D || !D.live) return;
    if (D.book) { renderLiveBook(); return; }
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
    liveTop(box, open, n, price);
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
    window.__b5 = { agg15: agg15, emaStep: emaStep, contState: contState, contBook: contBook, bookLevel: bookLevel, flipPrice: flipPrice, maState: maState,
                    maPreview: maPreview, LIVE: LIVE, TICK: TICK, tickMerge: tickMerge };
    if (q.kotak === "1") { TICK.on = true; setInterval(tickLoop, 2000); tickLoop(); }
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
        renderNow(); renderKpis(); renderChart(); renderCurve(); renderYears(); renderSides(); renderMonths(); renderTrades(); renderFoot(); renderBook();
        liveInit();
        document.body.dataset.ready = "true";
      })
      .catch(function (e) { $("b5-sub").textContent = "Failed to load the data: " + e.message; document.body.dataset.ready = "error"; });
  }
  function start() { loadPine(); boot(); }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", start) : start();
})();
