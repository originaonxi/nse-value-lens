/* ₹1 crore test page. Renders crore.json (built by crore.py after each NSE close). All text via textContent. */
(function () {
  "use strict";
  var D = null, W = "2y", SEL = 0, chart = null, sMain = null, sBench = null;
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
  function cr(v) { return isNum(v) ? "₹" + (v / 1e7).toFixed(2) + " cr" : "-"; }
  function pct(v, d) { return isNum(v) ? v.toFixed(d == null ? 1 : d) + "%" : "-"; }
  function spct(v, d) { return isNum(v) ? (v > 0 ? "+" : "") + v.toFixed(d == null ? 1 : d) + "%" : "-"; }
  function num(v, d) { return isNum(v) ? v.toLocaleString("en-IN", { maximumFractionDigits: d == null ? 0 : d, minimumFractionDigits: d || 0 }) : "-"; }
  function td(tr, txt, cls) { tr.appendChild(el("td", cls || null, txt)); }
  function tone(v) { return isNum(v) ? (v > 0 ? "num up" : v < 0 ? "num dn" : "num") : "num"; }
  function head(tb, cols) {
    tb.textContent = "";
    var th = el("thead"), tr = el("tr");
    cols.forEach(function (c) { tr.appendChild(el("th", c[1] || null, c[0])); });
    th.appendChild(tr); tb.appendChild(th);
    var body = el("tbody"); tb.appendChild(body); return body;
  }
  function win() { return D.windows[W]; }
  function ports() { return win().portfolios; }
  function bench() { return ports().filter(function (p) { return p.kind === "benchmark"; })[0]; }
  var KIND = { benchmark: "benchmark", ema: "EMA 105", setup: "homepage", best: "best set", honest: "honest" };

  function renderWin() {
    var box = $("cr-win"); box.textContent = "";
    [["2y", "Put in 2 years ago"], ["200", "Put in 200 sessions ago"]].forEach(function (w) {
      if (!D.windows[w[0]]) return;
      var b = el("button", W === w[0] ? "on" : null, w[1]); b.type = "button";
      b.addEventListener("click", function () { W = w[0]; SEL = bestIndex(); renderAll(); });
      box.appendChild(b);
    });
  }

  function bestIndex() {
    var P = ports(), j = 0;
    P.forEach(function (p, i) { if (p.kind === "best" && p.end > P[j].end) j = i; if (P[j].kind !== "best" && p.kind === "best") j = i; });
    return j;
  }

  function card(cls, kicker, big, line1, line2) {
    var c = el("div", "cr-card " + (cls || ""));
    c.appendChild(el("small", null, kicker)); c.appendChild(el("strong", null, big));
    if (line1) c.appendChild(el("p", null, line1));
    if (line2) c.appendChild(el("p", null, line2));
    return c;
  }

  function renderAnswer() {
    var w = win(), P = ports(), box = $("cr-answer"); box.textContent = "";
    $("cr-sub").textContent = w.from + " → " + w.to + " · " + w.sessions + " sessions · " + num(D.rules_tried) + " rules tried (EMA 105 + up to " +
      D.depth + " of " + D.signals.length + " confirmations × " + D.exit_settings + " exits × buy/sell) · " + num(w.sets_tried) +
      " portfolios priced in rupees · NIFTY lot " + D.lot_sizes.join(" / ") + " · cost " + D.cost_pct.toFixed(3) + "% a trade";
    var b = bench(), best = P.filter(function (p) { return p.kind === "best"; }).sort(function (a, c) { return c.end - a.end; })[0];
    var ema = P.filter(function (p) { return p.kind === "ema"; });
    if (best) box.appendChild(card("best", best.name, cr(best.end),
      sinr(best.profit) + " (" + spct(best.return_pct) + ") · worst fall " + pct(best.max_dd_pct),
      best.trades + " trades, " + pct(best.win_pct) + " won · after 31.2% tax " + sinr(best.after_tax_profit)));
    ema.forEach(function (p) { box.appendChild(card("", p.name, cr(p.end), sinr(p.profit) + " (" + spct(p.return_pct) + ")",
      p.trades + " trades, " + p.wins + " won, " + p.losses + " lost · worst fall " + pct(p.max_dd_pct))); });
    if (b) box.appendChild(card("", "Nifty 50 bought and held", cr(b.end), sinr(b.profit) + " (" + spct(b.return_pct) + ")",
      "worst fall " + pct(b.max_dd_pct) + " · no trades, no tax on the way"));
    var H = (D.honest || [])[W === "2y" ? 0 : 1];
    if (H) {
      var hp = H.portfolios.filter(function (p) { return p.kind === "honest"; }).sort(function (a, c) { return c.end - a.end; })[0];
      var hb = H.portfolios[0];
      if (hp) box.appendChild(card("warn", "Honest test · " + H.title, spct(hp.return_pct),
        hp.name + " · Nifty held " + spct(hb.return_pct) + " in the same months", "Chosen without seeing these months: the fairer guide to what comes next."));
    }
  }

  function renderPorts() {
    var b = head($("cr-port"), [["Portfolio"], ["Type"], ["₹1 crore became", "num"], ["Profit", "num"], ["Return", "num"], ["CAGR", "num"],
      ["Worst fall", "num"], ["Trades", "num"], ["Won", "num"], ["Win %", "num"], ["Costs paid", "num"], ["After tax", "num"]]);
    ports().forEach(function (p, i) {
      var tr = el("tr", i === SEL ? "sel" : null);
      td(tr, p.name);
      var k = el("td"); k.appendChild(el("span", "cr-kind " + p.kind, KIND[p.kind] || p.kind)); tr.appendChild(k);
      td(tr, inr(p.end), "num"); td(tr, sinr(p.profit), tone(p.profit)); td(tr, spct(p.return_pct), tone(p.return_pct));
      td(tr, spct(p.cagr_pct), tone(p.cagr_pct)); td(tr, pct(p.max_dd_pct), "num");
      td(tr, p.kind === "benchmark" ? "-" : String(p.trades), "num"); td(tr, p.kind === "benchmark" ? "-" : String(p.wins), "num");
      td(tr, pct(p.win_pct), "num"); td(tr, p.kind === "benchmark" ? "-" : inr(p.costs), "num"); td(tr, sinr(p.after_tax_profit), tone(p.after_tax_profit));
      tr.tabIndex = 0;
      var pick = function () { SEL = i; renderPorts(); renderDetail(); };
      tr.addEventListener("click", pick);
      tr.addEventListener("keydown", function (e) { if (e.key === "Enter") pick(); });
      b.appendChild(tr);
    });
  }

  function series(p) { return p.curve.map(function (c) { return { time: c[0], value: c[1] / 1e5 }; }); }

  function renderChart(p) {
    var box = $("cr-chart");
    if (typeof LightweightCharts === "undefined") { box.textContent = "Chart library failed to load."; return; }
    if (!chart) {
      chart = LightweightCharts.createChart(box, {
        autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
        grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } },
        rightPriceScale: { borderColor: "#e2e8f0" }, timeScale: { borderColor: "#e2e8f0" },
        localization: { priceFormatter: function (v) { return "₹" + v.toFixed(1) + " L"; } }
      });
      sBench = chart.addLineSeries({ color: "#94a3b8", lineWidth: 2, priceLineVisible: false, title: "Nifty held" });
      sMain = chart.addBaselineSeries({ baseValue: { type: "price", price: 100 }, lineWidth: 2, priceLineVisible: false,
        topLineColor: "#16a34a", topFillColor1: "#16a34a33", topFillColor2: "#16a34a05",
        bottomLineColor: "#dc2626", bottomFillColor1: "#dc262605", bottomFillColor2: "#dc262633" });
    }
    var b = bench();
    sBench.setData(b && p !== b ? series(b) : []);
    sMain.setData(series(p));
    chart.timeScale().fitContent();
    $("cr-curve-name").textContent = "· " + p.name + " · ₹ lakh (100 = the ₹1 crore put in)";
  }

  function renderDetail() {
    var p = ports()[SEL];
    renderChart(p);
    $("cr-sl-name").textContent = "· " + p.name;
    var b = head($("cr-sleeves"), [["Sleeve (strategy)"], ["Put in", "num"], ["Ended at", "num"], ["Profit", "num"], ["Trades", "num"], ["Won", "num"], ["Skipped (too small for 1 lot)", "num"]]);
    p.sleeves.forEach(function (s) {
      var tr = el("tr"); td(tr, s.strategy, "cr-rule"); td(tr, inr(s.start), "num"); td(tr, inr(s.end), "num");
      td(tr, sinr(s.profit), tone(s.profit)); td(tr, String(s.trades), "num"); td(tr, String(s.wins), "num"); td(tr, String(s.skipped), "num");
      b.appendChild(tr);
    });
    var rows = p.trade_rows || [];
    $("cr-tr-count").textContent = "· " + rows.length + " rows" + (p.open ? " · " + p.open + " still open" : "");
    var t = head($("cr-trades"), [["#", "num"], ["Sleeve"], ["Side"], ["Entry (2-hour close)"], ["Entry", "num"], ["Exit"], ["Exit", "num"],
      ["Lots × size", "num"], ["Position", "num"], ["Points", "num"], ["Cost", "num"], ["P&L", "num"], ["Sleeve after", "num"], ["Exit reason"]]);
    var multi = p.sleeves.length > 1;
    rows.forEach(function (r, i) {
      var tr = el("tr");
      td(tr, String(i + 1), "num"); td(tr, multi ? r.strategy.slice(0, 60) + (r.strategy.length > 60 ? "…" : "") : "this one", "cr-rule");
      td(tr, r.side, r.side === "BUY" ? "up" : "dn"); td(tr, r.entry_time); td(tr, num(r.entry, 2), "num");
      if (r.skipped) { var s = el("td", "muted", "skipped: " + r.skipped); s.colSpan = 9; tr.appendChild(s); t.appendChild(tr); return; }
      td(tr, r.open ? "open (latest close " + r.exit_time + ")" : r.exit_time); td(tr, num(r.exit, 2), "num");
      td(tr, r.lots + " × " + r.lot_size, "num"); td(tr, inr(r.notional), "num"); td(tr, (r.points > 0 ? "+" : "") + num(r.points, 2), tone(r.points));
      td(tr, inr(r.cost), "num"); td(tr, sinr(r.pnl), tone(r.pnl)); td(tr, inr(r.sleeve_after), "num"); td(tr, r.why);
      t.appendChild(tr);
    });
  }

  function miniTable(P) {
    var t = el("table", "fd-table");
    var b = head(t, [["Portfolio"], ["₹1 crore became", "num"], ["Profit", "num"], ["Return", "num"], ["Worst fall", "num"], ["Trades", "num"], ["Win %", "num"]]);
    P.forEach(function (p) {
      var tr = el("tr"); td(tr, p.name); td(tr, inr(p.end), "num"); td(tr, sinr(p.profit), tone(p.profit)); td(tr, spct(p.return_pct), tone(p.return_pct));
      td(tr, pct(p.max_dd_pct), "num"); td(tr, p.kind === "benchmark" ? "-" : String(p.trades), "num"); td(tr, pct(p.win_pct), "num");
      b.appendChild(tr);
    });
    var w = el("div", "fd-wrap"); w.appendChild(t); return w;
  }

  function renderHonest() {
    var box = $("cr-honest"); box.textContent = "";
    $("cr-honest-note").textContent = "The best sets above were chosen after seeing the same months they are scored on, so they flatter. " +
      "Here the rules are chosen only from the earlier part, then ₹1 crore is put in at the start of the part they never saw.";
    (D.honest || []).forEach(function (H) {
      box.appendChild(el("h3", "cr-h3", H.title + " · trading from " + H.test_from + " · picked on " + H.picked_on));
      box.appendChild(miniTable(H.portfolios));
      var t = el("table", "fd-table"), b = head(t, [["Picked rule"], ["Trades in the earlier part", "num"], ["Return in the earlier part", "num"]]);
      H.picked.forEach(function (r) { var tr = el("tr"); td(tr, r.rule, "cr-rule"); td(tr, String(r.train_trades), "num"); td(tr, spct(r.train_return_pct), tone(r.train_return_pct)); b.appendChild(tr); });
      var d = el("details"); d.appendChild(el("summary", null, "The rules it picked")); var w = el("div", "fd-wrap"); w.appendChild(t); d.appendChild(w);
      box.appendChild(d);
    });
  }

  function renderCombos() {
    var w = win();
    $("cr-sets").textContent = "· " + num(w.sets_tried) + " sets from " + w.units.length + " building blocks (" + w.candidates + " rules made money in both halves)";
    var b = head($("cr-combos"), [["Sleeves", "num"], ["Ranked by"], ["Strategies"], ["₹1 crore became", "num"], ["Return", "num"], ["Worst fall", "num"], ["Return ÷ fall", "num"]]);
    w.combos.slice().sort(function (a, c) { return a.k - c.k || (a.by < c.by ? -1 : a.by > c.by ? 1 : c.end - a.end); }).forEach(function (c) {
      var tr = el("tr"); td(tr, String(c.k), "num"); td(tr, c.by);
      var cell = el("td", "cr-rule"); c.names.forEach(function (n, i) { if (i) cell.appendChild(el("br")); cell.appendChild(document.createTextNode((i + 1) + ". " + n)); });
      tr.appendChild(cell); td(tr, inr(c.end), "num"); td(tr, spct(c.return_pct), tone(c.return_pct)); td(tr, pct(c.max_dd_pct), "num"); td(tr, num(c.ret_per_dd, 2), "num");
      b.appendChild(tr);
    });
    var r = head($("cr-rules"), [["Side"], ["Rule"], ["Trades", "num"], ["Win %", "num"], ["Return (whole sleeve, compounding)", "num"]]);
    w.longs.concat(w.shorts).forEach(function (x) {
      var tr = el("tr"); td(tr, x.side, x.side === "BUY" ? "up" : "dn"); td(tr, x.rule, "cr-rule"); td(tr, String(x.trades), "num");
      td(tr, pct(x.win), "num"); td(tr, spct(x.return_pct), tone(x.return_pct)); r.appendChild(tr);
    });
  }

  function renderAudit() {
    var A = D.audit, box = $("cr-audit"); box.textContent = "";
    if (!A) { box.textContent = "Audit not available yet."; return; }
    var ck = A.data_check, O = A.official, J = A.jev, a = O.buy_and_sell, b = O.buy_only;
    box.appendChild(el("p", "fd-note", A.window.from + " → " + A.window.to + " · " + A.window.sessions + " NSE sessions · " + A.window.candles +
      " two-hour candles. Rule: " + A.rule + ". Cost " + A.cost_pct.toFixed(3) + "% a trade. Jev " + (J.model || "") + " was given every trade on its own and asked: profit or loss?"));
    var t = el("table", "fd-table");
    var bd = head(t, [[""], ["Code: buy and sell", "num"], ["Jev: buy and sell", "num"], ["Code: buy only", "num"], ["Jev: buy only", "num"]]);
    var jb = J.buy_and_sell, jo = J.buy_only;
    [["Profit trades", a.wins, jb.profit_trades, b.wins, jo.profit_trades, 0],
     ["Loss trades", a.losses, jb.loss_trades, b.losses, jo.loss_trades, 0],
     ["Points in profit trades", a.profit_pts, jb.profit_pts, b.profit_pts, jo.profit_pts, 1],
     ["Points in loss trades", a.loss_pts, jb.loss_pts, b.loss_pts, jo.loss_pts, 1],
     ["Net points after costs", a.net_pts, jb.net_pts, b.net_pts, jo.net_pts, 1]].forEach(function (r) {
      var tr = el("tr"); td(tr, r[0]);
      for (var i = 1; i <= 4; i++) td(tr, (r[5] && r[i] > 0 ? "+" : "") + num(r[i], r[5]), r[5] ? tone(r[i]) : "num");
      bd.appendChild(tr);
    });
    var tr = el("tr"); td(tr, "Jev agrees with the code"); td(tr, ""); td(tr, jb.agree_with_code + " of " + jb.labelled, "num"); td(tr, ""); td(tr, jo.agree_with_code + " of " + jo.labelled, "num"); bd.appendChild(tr);
    var w = el("div", "fd-wrap"); w.appendChild(t); box.appendChild(w);
    var ul = el("ul", "fd-limits");
    [
      "Win rate " + pct(a.win_pct) + " (buy and sell) and " + pct(b.win_pct) + " (buy only): most EMA 105 flips are small losses; the money comes from a few long trends (best +" + num(a.best, 0) + " points).",
      "Costs ate " + num(a.cost_pts, 0) + " points of " + num(a.gross_pts, 0) + " gross over " + a.trades + " trades. Profit factor " + num(a.pf, 2) + " (buy and sell), " + num(b.pf, 2) + " (buy only).",
      "Still open: " + (O.open_trade ? O.open_trade.side + " from " + O.open_trade.entry_time + " at " + num(O.open_trade.entry, 2) + ", now " + (O.open_trade.net > 0 ? "+" : "") + num(O.open_trade.net, 0) + " points (not counted above)." : "none"),
      "Data check: NSE's two files (index close and F&O underlying) agree on " + ck.nse_files_agree + " of " + ck.sessions + " days. Yahoo's high and low match NSE closely (median gap " +
        ck.fields.high.median_pts + " / " + ck.fields.low.median_pts + " points). Yahoo's last 2-hour close differs from NSE's official close by a median " + ck.fields.close.median_pts +
        " points; Yahoo's 5-minute feed matches NSE's close exactly (median gap 0 over 60 sessions), so the gap is in Yahoo's hourly feed. The audit trades on NSE's official close.",
      "Missing days: " + (ck.missing_days.join(", ") || "none") + "; days with fewer than 4 candles: " + Object.keys(ck.bars_not_4).join(", ") + "."
    ].forEach(function (s) { ul.appendChild(el("li", null, s)); });
    box.appendChild(ul);
  }

  function renderJev() {
    var J = D.jev || {}, A = J.answers || {};
    var b = head($("cr-jev"), [["Result (" + (J.model || "Jev") + " · " + (J.status || "") + ")"], ["Luck from fitting the past"], ["Real money?"]]);
    Object.keys(A).forEach(function (k) {
      var a = A[k], tr = el("tr"); td(tr, k);
      if (a.error) { var c = el("td", "muted", "not judged (" + a.error + ")"); c.colSpan = 2; tr.appendChild(c); }
      else { td(tr, a.overfit.choice + " (" + a.overfit.conf + "%)"); td(tr, a.real_money.choice + " (" + a.real_money.conf + "%)"); }
      b.appendChild(tr);
    });
  }

  function renderText() {
    var ol = $("cr-rules-money"); ol.textContent = ""; (D.money_rules || []).forEach(function (t) { ol.appendChild(el("li", null, t)); });
    var ul = $("cr-limits"); ul.textContent = ""; (D.limits || []).forEach(function (t) { ul.appendChild(el("li", null, t)); });
  }

  /* ── the winner on the Nifty 50 chart ─────────────────────────────────────── */
  var WC = null, WS = null, WRANGE = "all";
  function wbox(k, v, cls) { var d = el("div"); d.appendChild(el("small", null, k)); d.appendChild(el("b", cls || null, v)); return d; }

  function renderWinnerChart() {
    var w = win().winner, ch = D.chart;
    if (!w || !ch) { $("cr-w-title").textContent = "Winner chart not available yet."; return; }
    $("cr-w-title").textContent = w.name + " · ₹1 crore → " + cr(w.end) + " (" + spct(w.return_pct) + ")";
    var rb = $("cr-w-rules"); rb.textContent = "";
    w.rules.forEach(function (r, i) { if (i) rb.appendChild(el("br")); rb.appendChild(document.createTextNode(r)); });
    var k = $("cr-w-kpis"); k.textContent = "";
    k.appendChild(wbox("Profit", sinr(w.profit), w.profit > 0 ? "up" : "dn"));
    k.appendChild(wbox("Closed trades", w.trades_n + " · " + w.wins + " won"));
    k.appendChild(wbox("Worst fall", pct(w.max_dd_pct)));
    k.appendChild(wbox("Open trade", w.open ? sinr(w.open_pnl) : "none", w.open_pnl > 0 ? "up" : null));
    if (typeof LightweightCharts === "undefined") { $("cr-w-chart").textContent = "Chart library failed to load."; return; }
    if (!WC) {
      WC = LightweightCharts.createChart($("cr-w-chart"), {
        autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
        grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } },
        rightPriceScale: { borderColor: "#e2e8f0" }, timeScale: { borderColor: "#e2e8f0", timeVisible: true, secondsVisible: false, rightOffset: 4 }
      });
      WS = WC.addCandlestickSeries({ upColor: "#16a34a", downColor: "#dc2626", borderUpColor: "#16a34a", borderDownColor: "#dc2626",
        wickUpColor: "#16a34a", wickDownColor: "#dc2626" });
      WS.setData(ch.bars.map(function (b) { return { time: b[0], open: b[1], high: b[2], low: b[3], close: b[4] }; }));
      var l = WC.addLineSeries({ color: "#2563eb", lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: "EMA 105" });
      l.setData(ch.bars.map(function (b, i) { return { time: b[0], value: ch.ema[i] }; }));
      WC._ema = l;
    }
    var mk = w.markers.map(function (m) {
      var buy = m[2] === "BUY";
      if (m[1] === "entry") return { time: m[0], position: buy ? "belowBar" : "aboveBar", color: buy ? "#16a34a" : "#dc2626",
        shape: buy ? "arrowUp" : "arrowDown", text: m[4] };
      var win_ = m[4].charAt(0) === "+";
      return { time: m[0], position: buy ? "aboveBar" : "belowBar", color: win_ ? "#15803d" : "#b91c1c", shape: "circle", text: m[4] };
    }).sort(function (a, b) { return a.time - b.time; });
    WS.setMarkers(mk);
    if (WC._open) { WS.removePriceLine(WC._open); WC._open = null; }
    if (w.open) WC._open = WS.createPriceLine({ price: w.open.entry, color: w.open.side === "BUY" ? "#16a34a" : "#dc2626", lineWidth: 1,
      lineStyle: 2, axisLabelVisible: true, title: "open " + w.open.side + " @ " + num(w.open.entry, 2) });
    renderRange(); renderWinnerNow(w);
  }

  function renderRange() {
    var box = $("cr-w-range"); box.textContent = "";
    [["all", "Whole window"], ["60", "Last 60 sessions"], ["20", "Last 20 sessions"]].forEach(function (r) {
      var b = el("button", WRANGE === r[0] ? "on" : null, r[1]); b.type = "button";
      b.addEventListener("click", function () { WRANGE = r[0]; renderRange(); });
      box.appendChild(b);
    });
    var bars = D.chart.bars, n = bars.length, from = 0;
    if (WRANGE === "all") { var t0 = win().chart_from; while (from < n && bars[from][0] < t0) from++; }
    else from = Math.max(0, n - 4 * (+WRANGE));
    WC.timeScale().setVisibleLogicalRange({ from: from, to: n + 3 });
  }

  function renderWinnerNow(w) {
    var box = $("cr-w-now"); box.textContent = "";
    var a = el("div");
    a.appendChild(el("h3", null, "Right now · last 2-hour close " + w.as_of + " IST"));
    var p = el("p"); p.appendChild(el("span", "state " + (w.open ? "in" : "wait"), w.open ? "IN TRADE · " + w.open.side : "WAITING"));
    p.appendChild(document.createTextNode("Nifty " + num(w.close, 2) + " · EMA 105 " + num(w.ema, 2)));
    a.appendChild(p);
    if (w.open) {
      var o = w.open;
      a.appendChild(el("p", null, o.side + " " + o.lots + " lots × " + o.lot_size + " from " + o.entry_time + " at " + num(o.entry, 2) +
        " · now " + (o.points > 0 ? "+" : "") + num(o.points, 2) + " points = " + sinr(o.pnl) + " · RSI " + num(o.rsi, 1)));
      a.appendChild(el("b", null, "It closes on the first of:"));
      var ul = el("ul"); o.exits.forEach(function (x) { ul.appendChild(el("li", null, x)); }); a.appendChild(ul);
    }
    box.appendChild(a);
    w.checks.forEach(function (c) {
      var d = el("div");
      d.appendChild(el("h3", null, c.side + " rule · " + (c.all_ok ? (c.waiting_for_pullback ? "all checks pass, but waiting for a pull-back to EMA 105 after its last exit" : "all checks pass at this close") : "not all checks pass")));
      d.appendChild(el("p", "muted", c.rule));
      var ul = el("ul");
      c.checks.forEach(function (x) { ul.appendChild(el("li", x.ok ? "ok" : "no", x.name + " — " + x.value)); });
      d.appendChild(ul); box.appendChild(d);
    });
  }

  function renderAll() { renderWin(); renderWinnerChart(); renderAnswer(); renderPorts(); renderDetail(); renderCombos(); }

  function boot() {
    fetch("crore.json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) { D = d; SEL = bestIndex(); renderAll(); renderHonest(); renderAudit(); renderJev(); renderText(); })
      .catch(function (e) { $("cr-sub").textContent = "Failed to load crore.json: " + e.message; });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
