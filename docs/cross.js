/* EMA cross lab page. Renders cross.json (built by cross_lab.py after each NSE close). All text via textContent. */
(function () {
  "use strict";
  var D = null, CH = null, SER = null, RANGE = "3";
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
  function num(v, d) { return isNum(v) ? v.toLocaleString("en-IN", { maximumFractionDigits: d || 0, minimumFractionDigits: d || 0 }) : "-"; }
  function sg(v, d) { return isNum(v) ? (v > 0 ? "+" : "") + num(v, d) : "-"; }
  function pct(v) { return isNum(v) ? v.toFixed(1) + "%" : "-"; }
  function spct(v) { return isNum(v) ? (v > 0 ? "+" : "") + v.toFixed(1) + "%" : "-"; }
  function tone(v) { return isNum(v) ? (v > 0 ? "num up" : v < 0 ? "num dn" : "num") : "num"; }
  function td(tr, t, c) { tr.appendChild(el("td", c || null, t)); }
  function head(tb, cols) {
    tb.textContent = "";
    var th = el("thead"), tr = el("tr");
    cols.forEach(function (c) { tr.appendChild(el("th", c[1] || null, c[0])); });
    th.appendChild(tr); tb.appendChild(th);
    var b = el("tbody"); tb.appendChild(b); return b;
  }
  function kpi(label, big, sub, cls, bigcls) {
    var k = el("div", "id-kpi " + (cls || ""));
    k.appendChild(el("small", null, label)); k.appendChild(el("strong", bigcls || null, big)); if (sub) k.appendChild(el("span", null, sub));
    return k;
  }
  function chosen() { return D.finalists.filter(function (f) { return f.id === D.chosen; })[0] || D.finalists[0]; }
  function jevA(k) { return ((D.jev || {}).answers || {})[k]; }

  function renderTop() {
    var c = chosen(), y = c.year, l5 = c.ladder.filter(function (l) { return l.lev === 5; })[0] || {};
    $("cx-sub").textContent = "Last candle " + D.last_candle + " IST · " + num(D.rules_tried) + " cross rules on 5 / 15 / 30-minute candles · last 200 sessions from " +
      D.windows.last200 + " · " + (D.chosen_by === "Jev" ? "Jev picked " + c.id : "picked by " + D.chosen_by);
    var box = $("cx-kpis"); box.textContent = "";
    box.appendChild(kpi("Jev's pick · ₹1 crore · 1 year (1x)", sinr(y.profit), "₹1 crore → " + inr(y.end) + " (" + spct(y.return_pct) + ")", "main", y.profit > 0 ? "up" : "dn"));
    box.appendChild(kpi("Money made", "+" + inr(y.made), y.wins + " winning trades", "", "up"));
    box.appendChild(kpi("Money lost", inr(y.lost), (y.trades - y.wins) + " losing trades", "", "dn"));
    box.appendChild(kpi("Trades · win rate", y.trades + " · " + pct(y.win_pct), y.green_days + " green, " + y.red_days + " red days"));
    box.appendChild(kpi("At 5x margin", sinr(l5.end - D.capital), spct(l5.return_pct) + " · worst fall " + pct(l5.max_dd_pct), "", (l5.end - D.capital) > 0 ? "up" : "dn"));
    box.appendChild(kpi("₹2 crore needs", c.lev_for_2cr ? c.lev_for_2cr + "x" : "not reached", c.lev_for_2cr ? "leverage, in one year" : "even at " + D.levs[D.levs.length - 1] + "x"));
    box.appendChild(kpi("Worst fall (1x)", pct(y.max_dd_pct), inr(y.max_dd) + " from the peak"));
  }

  function renderChart() {
    var ch = D.chart, c = chosen(), box = $("cx-chart");
    $("cx-rule").textContent = "Jev's pick (" + c.id + "): " + c.rule + ".";
    if (typeof LightweightCharts === "undefined") { box.textContent = "Chart library failed to load."; return; }
    CH = LightweightCharts.createChart(box, {
      autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
      grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } },
      rightPriceScale: { borderColor: "#e2e8f0" }, timeScale: { borderColor: "#e2e8f0", timeVisible: true, secondsVisible: false, rightOffset: 4 }
    });
    SER = CH.addCandlestickSeries({ upColor: "#16a34a", downColor: "#dc2626", borderUpColor: "#16a34a", borderDownColor: "#dc2626", wickUpColor: "#16a34a", wickDownColor: "#dc2626" });
    SER.setData(ch.bars.map(function (b) { return { time: b[0], open: b[1], high: b[2], low: b[3], close: b[4] }; }));
    var colors = ["#2563eb", "#f59e0b"], leg = [];
    Object.keys(ch.emas).sort(function (a, b) { return a - b; }).forEach(function (k, i) {
      var l = CH.addLineSeries({ color: colors[i % 2], lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: "EMA " + k });
      l.setData(ch.bars.map(function (b, j) { return { time: b[0], value: ch.emas[k][j] }; }));
      leg.push("EMA " + k + (i ? " (orange)" : " (blue)"));
    });
    $("cx-ema-legend").textContent = leg.join(" · ") + " · " + ch.tf + "-min candles";
    var n = D.next;
    if (n && isNum(n.cross_price)) SER.createPriceLine({ price: n.cross_price, color: n.side_now === "buy" ? "#dc2626" : "#16a34a", lineWidth: 2, lineStyle: 2,
      axisLabelVisible: true, title: (n.side_now === "buy" ? "SELL" : "BUY") + " if a close crosses " + num(n.cross_price, 0) });
    drawMarkers(); renderRange();
  }

  function drawMarkers() {
    var zoom = RANGE !== "10";
    SER.setMarkers(D.chart.markers.map(function (m) {
      var buy = m[2] === "BUY";
      if (m[1] === "in") return { time: m[0], position: buy ? "belowBar" : "aboveBar", color: buy ? "#16a34a" : "#dc2626", shape: buy ? "arrowUp" : "arrowDown", text: zoom ? m[3] : "" };
      var good = m[3].indexOf("+₹") >= 0;
      return { time: m[0], position: buy ? "aboveBar" : "belowBar", color: good ? "#15803d" : "#b91c1c", shape: "circle", text: zoom ? m[3] : "", size: 0.8 };
    }).sort(function (a, b) { return a.time - b.time; }));
  }

  function renderRange() {
    var box = $("cx-range"); box.textContent = "";
    var per = Math.ceil(375 / D.chart.tf);
    [["1", "Last session"], ["3", "3 sessions"], ["10", "10 sessions"]].forEach(function (r) {
      var b = el("button", RANGE === r[0] ? "on" : null, r[1]); b.type = "button";
      b.addEventListener("click", function () { RANGE = r[0]; renderRange(); drawMarkers(); });
      box.appendChild(b);
    });
    var n = D.chart.bars.length;
    CH.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - per * (+RANGE)), to: n + 3 });
  }

  function renderNext() {
    var n = D.next, box = $("cx-next"); box.textContent = "";
    var p = el("p"); p.appendChild(el("b", "t", "NEXT CROSS · ")); p.appendChild(document.createTextNode("Jev's pick, from the last close"));
    box.appendChild(p);
    var ul = el("ul"); n.lines.forEach(function (l) { ul.appendChild(el("li", null, l)); }); box.appendChild(ul);
    if (D.today && D.today.length) box.appendChild(el("p", "muted", "Last session (" + D.as_of + "): " + D.today.map(function (x) {
      return x.side + " " + x.in_time + " " + num(x.in, 2) + " → " + x.out_time + " " + num(x.out, 2) + " " + sg(x.points, 0) + " pts " + sinr(x.pnl);
    }).join(" · ")));
  }

  function answer(cls, kicker, big, text) {
    var a = el("div", "cx-answer " + (cls || ""));
    a.appendChild(el("small", null, kicker)); a.appendChild(el("strong", null, big)); a.appendChild(el("p", null, text));
    return a;
  }

  function renderAnswers() {
    var box = $("cx-answers"); box.textContent = "";
    var c = chosen(), best = jevA("best"), dbl = jevA("double"), fif = jevA("fifty");
    var u = D.user_pairs.filter(function (x) { return x.tf === 15 && x.a === 9 && x.b === 14; })[0];
    var uc = (u && u.cross) || {};
    box.appendChild(answer("", "Which cross makes the most money? (Jev)", c.id + " · " + c.name,
      c.rule + ". Last 200 sessions " + sg(c.last200.net, 0) + " Nifty points after costs (" + c.last200.n + " trades); halves " + sg(c.h1.net, 0) + " / " +
      sg(c.h2.net, 0) + "; the 200 sessions before " + sg(c.pre.net, 0) + "." + (best ? " Jev: " + best.choice + " (" + best.conf + "% confident)." : "")));
    box.appendChild(answer(uc.first >= 60 ? "yes" : "no", "Does a cross always give 50 points?", fif ? (fif.choice === "yes" ? "Yes (Jev)" : "No (Jev)") : "Measured below",
      "15-min EMA 9 × 14, last 200 sessions: " + num(uc.n) + " crosses. " + pct(uc.reach) + " ever reached +50 points before the opposite cross or the close; " +
      pct(uc.first) + " reached +50 before −50. Median best move " + num(uc.mfe_median, 0) + " pts, median worst " + num(uc.mae_median, 0) + " pts, median result " + sg(uc.result_median, 0) + " pts."));
    box.appendChild(answer(c.lev_for_2cr ? "" : "no", "Can ₹1 crore become ₹2 crore in a year?", c.lev_for_2cr ? "Only with " + c.lev_for_2cr + "x" : "No, not even at " + D.levs[D.levs.length - 1] + "x",
      "Jev's pick at 1x: " + cr(c.year.end) + ". " + (c.lev_for_2cr ? "It reaches ₹2 crore only at " + c.lev_for_2cr + "x leverage, where its worst fall is " +
      pct((c.ladder.filter(function (l) { return l.lev === c.lev_for_2cr; })[0] || {}).max_dd_pct) + "." : "No leverage up to " + D.levs[D.levs.length - 1] + "x gets there.") +
      " With costs doubled at 1x: " + spct(c.dbl.return_pct) + "." + (dbl ? " Jev, asked about all finalists at up to " + D.levs[D.levs.length - 1] + "x: " + Object.keys(dbl.probs).map(function (k) { return k + " " + dbl.probs[k] + "%"; }).join(", ") + "." : "")));
    box.appendChild(answer("", "The 10% stop", "Only matters with leverage",
      "A 10% capital stop at 1x needs Nifty to move 10% inside one day, which never happened, so it never triggered. At 5x it is a 2% move, at 10x a 1% move. " +
      "Stops hit for Jev's pick at 5x: " + num((c.ladder.filter(function (l) { return l.lev === 5; })[0] || {}).stops_hit) + "."));
  }

  function renderFinalists() {
    var b = head($("cx-fin"), [["", null], ["Finalist"], ["Rule"], ["Trades", "num"], ["Win %", "num"], ["PF", "num"], ["Last 200 pts", "num"], ["Halves", "num"],
      ["200 before", "num"], ["2x cost", "num"], ["₹1 cr · 1 yr", "num"], ["Return", "num"], ["Jev: luck", null]]);
    D.finalists.forEach(function (f) {
      var tr = el("tr", f.id === D.chosen ? "pick" : null), lk = jevA("luck_" + f.id), pb = (jevA("best") || {}).probs || {};
      td(tr, f.id + (f.id === D.chosen ? " ✓" : "")); td(tr, f.name + (isNum(pb[f.id]) ? " · Jev " + pb[f.id] + "%" : "")); td(tr, f.rule, "rule");
      td(tr, String(f.last200.n), "num"); td(tr, pct(f.last200.win), "num"); td(tr, num(f.last200.pf, 2), "num"); td(tr, sg(f.last200.net, 0), tone(f.last200.net));
      td(tr, sg(f.h1.net, 0) + " / " + sg(f.h2.net, 0), "num"); td(tr, sg(f.pre.net, 0), tone(f.pre.net)); td(tr, sg(f.dbl_pts.net, 0), tone(f.dbl_pts.net));
      td(tr, inr(f.year.end), "num"); td(tr, spct(f.year.return_pct), tone(f.year.return_pct)); td(tr, lk ? lk.choice + " (" + lk.conf + "%)" : "-");
      b.appendChild(tr);
    });
    var J = D.jev || {};
    $("cx-jev-note").textContent = "· " + (J.model || "Jev") + " · " + (J.status || "") + " · points are Nifty points after costs, 1 unit";
  }

  function renderLadder() {
    var cols = [["Leverage", "num"]], b;
    D.finalists.forEach(function (f) { cols.push([f.id + ": ₹1 cr becomes", "num"]); cols.push([f.id + ": worst fall", "num"]); });
    b = head($("cx-ladder"), cols);
    D.levs.forEach(function (lev, i) {
      var tr = el("tr"); td(tr, lev + "x", "num");
      D.finalists.forEach(function (f) {
        var l = f.ladder[i];
        td(tr, inr(l.end), l.end >= 2 * D.capital ? "num up" : tone(l.end - D.capital)); td(tr, pct(l.max_dd_pct), "num");
      });
      b.appendChild(tr);
    });
    $("cx-ladder-note").textContent = "Each trade uses whole NIFTY lots worth up to leverage × the money in the account; a trade is cut once it has lost 10% of that money. " +
      "Green = ₹2 crore or more. Leverage needed for ₹2 crore: " + D.finalists.map(function (f) { return f.id + " " + (f.lev_for_2cr ? f.lev_for_2cr + "x" : "never (up to " + D.levs[D.levs.length - 1] + "x)"); }).join(" · ") + ".";
  }

  function renderFifty() {
    $("cx-fifty-note").textContent = "· every cross in the last 200 sessions, from the next candle's open until the opposite cross or the 15:00 close-out";
    var b = head($("cx-user"), [["Your cross"], ["Crosses", "num"], ["Ever +50 pts", "num"], ["+50 before −50", "num"], ["Median best move", "num"], ["Median worst move", "num"],
      ["Median result", "num"], ["Trading it (pts, 200 sessions)", "num"], ["With 50 stop / 50 target", "num"], ["200 before", "num"]]);
    D.user_pairs.forEach(function (u) {
      var c = u.cross || {}, tr = el("tr");
      td(tr, u.tf + "-min EMA " + u.a + " × " + u.b); td(tr, num(c.n), "num"); td(tr, pct(c.reach), "num"); td(tr, pct(c.first), "num");
      td(tr, sg(c.mfe_median, 0), "num up"); td(tr, "-" + num(c.mae_median, 0), "num dn"); td(tr, sg(c.result_median, 0), tone(c.result_median));
      td(tr, sg(u.last200.net, 0), tone(u.last200.net)); td(tr, u.with_50_50 ? sg(u.with_50_50.last200.net, 0) : "-", tone(u.with_50_50 && u.with_50_50.last200.net));
      td(tr, sg(u.pre.net, 0), tone(u.pre.net));
      b.appendChild(tr);
    });
    var t = head($("cx-fifty"), [["#", "num"], ["Candles"], ["EMA pair"], ["Crosses", "num"], ["Ever +50", "num"], ["+50 before −50", "num"], ["Median result", "num"]]);
    D.fifty.forEach(function (f, i) {
      var tr = el("tr"); td(tr, String(i + 1), "num"); td(tr, f.tf + "-min"); td(tr, "EMA " + f.a + " × " + f.b); td(tr, num(f.n), "num");
      td(tr, pct(f.reach), "num"); td(tr, pct(f.first), "num"); td(tr, sg(f.result_median, 0), tone(f.result_median)); t.appendChild(tr);
    });
  }

  function renderTf() {
    var b = head($("cx-tf"), [["Candles"], ["Best rule"], ["Trades", "num"], ["Win %", "num"], ["PF", "num"], ["Last 200 pts", "num"], ["Halves", "num"], ["200 before", "num"]]);
    D.timeframes.forEach(function (u) {
      var x = D.by_tf[String(u)], tr = el("tr");
      td(tr, u + "-min");
      if (!x) { var c = el("td", "muted", "no rule made money in both halves with 80+ trades"); c.colSpan = 7; tr.appendChild(c); b.appendChild(tr); return; }
      td(tr, x.rule, "rule"); td(tr, String(x.last200.n), "num"); td(tr, pct(x.last200.win), "num"); td(tr, num(x.last200.pf, 2), "num");
      td(tr, sg(x.last200.net, 0), tone(x.last200.net)); td(tr, sg(x.h1.net, 0) + " / " + sg(x.h2.net, 0), "num"); td(tr, sg(x.pre.net, 0), tone(x.pre.net));
      b.appendChild(tr);
    });
    var t = head($("cx-top"), [["#", "num"], ["Rule"], ["Trades", "num"], ["Win %", "num"], ["PF", "num"], ["Last 200 pts", "num"], ["Halves", "num"], ["200 before", "num"]]);
    D.top.forEach(function (x, i) {
      var tr = el("tr"); td(tr, String(i + 1), "num"); td(tr, x.rule, "rule"); td(tr, String(x.last200.n), "num"); td(tr, pct(x.last200.win), "num");
      td(tr, num(x.last200.pf, 2), "num"); td(tr, sg(x.last200.net, 0), tone(x.last200.net)); td(tr, sg(x.h1.net, 0) + " / " + sg(x.h2.net, 0), "num");
      td(tr, sg(x.pre.net, 0), tone(x.pre.net)); t.appendChild(tr);
    });
  }

  function renderTrades() {
    var T = D.trades.slice().reverse();
    $("cx-tr-n").textContent = "· " + T.length + " trades in the year at 1x, newest first";
    var b = head($("cx-trades"), [["Day"], ["Side"], ["In"], ["Price", "num"], ["Out"], ["Price", "num"], ["Lots", "num"], ["Points", "num"], ["Cost", "num"], ["P&L", "num"], ["Money after", "num"]]);
    T.forEach(function (t) {
      var tr = el("tr");
      td(tr, t.day); td(tr, t.side, t.side === "BUY" ? "up" : "dn"); td(tr, t.in_time); td(tr, num(t.in, 2), "num"); td(tr, t.out_time); td(tr, num(t.out, 2), "num");
      td(tr, t.lots + " × " + t.lot, "num"); td(tr, sg(t.points, 2), tone(t.points)); td(tr, inr(t.cost), "num"); td(tr, sinr(t.pnl), tone(t.pnl)); td(tr, inr(t.cash), "num");
      b.appendChild(tr);
    });
  }

  function renderData() {
    var ul = $("cx-data"); ul.textContent = "";
    D.data.forEach(function (c) {
      var t = c.tf + "-minute candles: " + c.sessions + " sessions, " + c.from + " → " + c.to + " (" + c.short_days + " short days).";
      if (c.vs_nse) t += " Against NSE's daily index file on " + c.vs_nse.days + " days: open/high/low median gap " + c.vs_nse.median_pts + " pts, " +
        c.vs_nse.days_within_1pt + " days within 1 point.";
      if (c.vs_yahoo) t += " Against Yahoo's 5-minute candles (" + c.vs_yahoo.bars + " candles): median close gap " + c.vs_yahoo.median_pts + " pts.";
      if (c.tf === 30) t += " Built from the 15-minute candles.";
      ul.appendChild(el("li", null, t));
    });
    var l = $("cx-limits"); l.textContent = ""; D.limits.forEach(function (x) { l.appendChild(el("li", null, x)); });
  }

  function boot() {
    fetch("cross.json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        D = d; renderTop(); renderChart(); renderNext(); renderAnswers(); renderFinalists(); renderLadder(); renderFifty(); renderTf(); renderTrades(); renderData();
      })
      .catch(function (e) { $("cx-sub").textContent = "Failed to load cross.json: " + e.message; });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
