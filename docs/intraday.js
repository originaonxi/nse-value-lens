/* Nifty 50 intraday page. Renders intraday.json (built by intraday15.py after each NSE close). All text via textContent. */
(function () {
  "use strict";
  var D = null, CH = null, SER = null, RANGE = "5";
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

  function renderTop() {
    var w = D.portfolios[0], h = D.extra[2], hon = D.portfolios.filter(function (p) { return /honest/.test(p.name); })[0];
    $("id-sub").textContent = "Last 15-min candle " + D.last_candle + " IST · " + num(D.rules_tried) + " rules tested on " +
      D.data.sessions + " sessions of 15-minute candles · ₹1 crore put in on " + D.windows.year_from;
    var box = $("id-kpis"); box.textContent = "";
    box.appendChild(kpi("Total P&L · the winner · 1 year", sinr(w.profit), "₹1 crore → " + inr(w.end) + " (" + spct(w.return_pct) + ")", "main", w.profit > 0 ? "up" : "dn"));
    box.appendChild(kpi("Money made (winning trades)", "+" + inr(w.made), w.wins + " winning trades", "", "up"));
    box.appendChild(kpi("Money lost (losing trades)", inr(w.lost), (w.trades - w.wins) + " losing trades", "", "dn"));
    box.appendChild(kpi("Trades · win rate", w.trades + " · " + pct(w.win_pct), w.green_days + " green days, " + w.red_days + " red days"));
    box.appendChild(kpi("Worst fall", pct(w.max_dd_pct), inr(w.max_dd) + " from the peak"));
    if (hon) box.appendChild(kpi("Honest test (picked before)", sinr(hon.profit), spct(hon.return_pct) + " in the same year", "", hon.profit > 0 ? "up" : "dn"));
    box.appendChild(kpi("Nifty 50 bought and held", sinr(h.profit), spct(h.return_pct) + " in the same year", "", h.profit > 0 ? "up" : "dn"));
  }

  function renderNext() {
    var n = D.next, box = $("id-next"); box.textContent = "";
    var p = el("p"); p.appendChild(el("b", "t", "SIGNALS FOR THE NEXT SESSION · "));
    p.appendChild(document.createTextNode("the winner's rule · Nifty " + num(n.close, 2) + " at the last close · daily trend " + n.daily_trend));
    box.appendChild(p);
    var ul = el("ul"); n.lines.forEach(function (l) { ul.appendChild(el("li", null, l)); }); box.appendChild(ul);
    if (D.today && D.today.length) {
      var t = el("p", "muted", "Today (" + D.as_of + "): " + D.today.map(function (x) {
        return x.side + " " + x.in_time + " at " + num(x.in, 2) + " → " + x.out_time + " at " + num(x.out, 2) + " = " + sinr(x.pnl);
      }).join(" · "));
      box.appendChild(t);
    }
  }

  function renderChart() {
    var ch = D.chart, box = $("id-chart");
    $("id-rule").textContent = "The winner: " + D.best.label + ". Picked as the rule with the most Nifty points over the last 200 sessions among " +
      "rules with 60+ trades that made money in both 100-session halves.";
    if (typeof LightweightCharts === "undefined") { box.textContent = "Chart library failed to load."; return; }
    CH = LightweightCharts.createChart(box, {
      autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
      grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } },
      rightPriceScale: { borderColor: "#e2e8f0" }, timeScale: { borderColor: "#e2e8f0", timeVisible: true, secondsVisible: false, rightOffset: 4 }
    });
    SER = CH.addCandlestickSeries({ upColor: "#16a34a", downColor: "#dc2626", borderUpColor: "#16a34a", borderDownColor: "#dc2626", wickUpColor: "#16a34a", wickDownColor: "#dc2626" });
    SER.setData(ch.bars.map(function (b) { return { time: b[0], open: b[1], high: b[2], low: b[3], close: b[4] }; }));
    var colors = ["#2563eb", "#f59e0b"], leg = [];
    Object.keys(ch.emas).forEach(function (k, i) {
      var l = CH.addLineSeries({ color: colors[i % 2], lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: "EMA " + k });
      l.setData(ch.bars.map(function (b, j) { return { time: b[0], value: ch.emas[k][j] }; }));
      leg.push("EMA " + k + (i ? " (orange)" : " (blue)"));
    });
    $("id-ema-legend").textContent = leg.join(" · ");
    var days = CH.addHistogramSeries({ color: "#cbd5e1", priceScaleId: "days", lastValueVisible: false, priceLineVisible: false });
    CH.priceScale("days").applyOptions({ scaleMargins: { top: 0, bottom: 0 }, visible: false });
    var ds = {}; ch.day_starts.forEach(function (t) { ds[t] = 1; });
    days.setData(ch.bars.map(function (b) { return { time: b[0], value: ds[b[0]] ? 1 : 0, color: ds[b[0]] ? "#e2e8f099" : "#00000000" }; }));
    drawMarkers(); renderRange();
  }

  function drawMarkers() {
    var zoom = RANGE !== "60";
    SER.setMarkers(D.chart.markers.map(function (m) {
      var buy = m[2] === "BUY";
      if (m[1] === "in") return { time: m[0], position: buy ? "belowBar" : "aboveBar", color: buy ? "#16a34a" : "#dc2626",
        shape: buy ? "arrowUp" : "arrowDown", text: zoom ? m[3] : "" };
      var good = m[3].charAt(0) === "+";
      return { time: m[0], position: buy ? "aboveBar" : "belowBar", color: good ? "#15803d" : "#b91c1c", shape: "circle", text: zoom ? m[3] : "", size: 0.8 };
    }).sort(function (a, b) { return a.time - b.time; }));
  }

  function renderRange() {
    var box = $("id-range"); box.textContent = "";
    [["1", "Today"], ["5", "5 sessions"], ["20", "20 sessions"], ["60", "60 sessions"]].forEach(function (r) {
      var b = el("button", RANGE === r[0] ? "on" : null, r[1]); b.type = "button";
      b.addEventListener("click", function () { RANGE = r[0]; renderRange(); drawMarkers(); });
      box.appendChild(b);
    });
    var n = D.chart.bars.length;
    CH.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 25 * (+RANGE)), to: n + 2 });
  }

  function renderPort() {
    var b = head($("id-port"), [["Strategy"], ["₹1 crore became", "num"], ["Total P&L", "num"], ["Return", "num"], ["Made (winners)", "num"],
      ["Lost (losers)", "num"], ["Costs", "num"], ["Trades", "num"], ["Win %", "num"], ["Worst fall", "num"], ["Best day", "num"], ["Worst day", "num"]]);
    D.portfolios.concat(D.extra.slice(0, 2)).forEach(function (p, i) {
      var tr = el("tr", i === 0 ? "win-row" : null);
      td(tr, p.name); td(tr, inr(p.end), "num"); td(tr, sinr(p.profit), tone(p.profit)); td(tr, spct(p.return_pct), tone(p.return_pct));
      td(tr, "+" + inr(p.made), "num up"); td(tr, inr(p.lost), "num dn"); td(tr, inr(p.costs), "num"); td(tr, String(p.trades), "num");
      td(tr, pct(p.win_pct), "num"); td(tr, pct(p.max_dd_pct), "num"); td(tr, sinr(p.best_day), "num up"); td(tr, sinr(p.worst_day), "num dn");
      b.appendChild(tr);
    });
    var h = D.extra[2], tr = el("tr");
    td(tr, h.name); td(tr, inr(h.end), "num"); td(tr, sinr(h.profit), tone(h.profit)); td(tr, spct(h.return_pct), tone(h.return_pct));
    for (var i = 0; i < 8; i++) td(tr, "-", "num");
    b.appendChild(tr);
    $("id-year").textContent = "· " + D.windows.year_from + " → " + D.as_of + " · whole NIFTY lots, no leverage, gains compound";
    $("id-port-note").textContent = "Made = sum of all winning trades after costs; Lost = sum of all losing trades after costs; Total P&L = Made + Lost. " +
      "Rule details: " + D.portfolios.map(function (p) { return p.name + ": " + p.rule; }).join(" | ");
    if (typeof LightweightCharts === "undefined") return;
    var c = LightweightCharts.createChart($("id-curve"), {
      autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
      grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } }, rightPriceScale: { borderColor: "#e2e8f0" },
      timeScale: { borderColor: "#e2e8f0" }, localization: { priceFormatter: function (v) { return "₹" + v.toFixed(1) + " L"; } }
    });
    var cols = ["#16a34a", "#f59e0b", "#94a3b8", "#dc2626", "#7c3aed"];
    D.portfolios.forEach(function (p, i) {
      var s = c.addLineSeries({ color: cols[i % cols.length], lineWidth: i ? 1 : 3, priceLineVisible: false, title: p.name.split(" (")[0].slice(0, 28) });
      s.setData(p.curve.map(function (x) { return { time: x[0], value: x[1] / 1e5 }; }));
    });
    c.timeScale().fitContent();
  }

  function renderMonths() {
    var w = D.portfolios[0], b = head($("id-months"), [["Month"], ["Days traded", "num"], ["P&L", "num"]]);
    w.months.forEach(function (m) { var tr = el("tr"); td(tr, m.month); td(tr, String(m.days_traded), "num"); td(tr, sinr(m.pnl), tone(m.pnl)); b.appendChild(tr); });
  }

  function renderLast200() {
    $("id-200").textContent = "· " + D.windows.last200_from + " → " + D.as_of + " · Nifty points after costs, per 1 unit of the index";
    var b = head($("id-200t"), [["Rule"], ["Trades", "num"], ["Win %", "num"], ["Profit factor", "num"], ["Net points", "num"], ["1st 100 sessions", "num"],
      ["2nd 100 sessions", "num"], ["The 200 sessions before", "num"], ["Worst fall (pts)", "num"]]);
    D.portfolios.forEach(function (p) {
      var a = p.last200, tr = el("tr");
      td(tr, p.name); td(tr, String(a.n), "num"); td(tr, pct(a.win), "num"); td(tr, num(a.pf, 2), "num"); td(tr, sg(a.net, 0), tone(a.net));
      td(tr, sg(p.h1.net, 0), tone(p.h1.net)); td(tr, sg(p.h2.net, 0), tone(p.h2.net)); td(tr, sg(p.pre.net, 0), tone(p.pre.net)); td(tr, num(a.dd, 0), "num");
      b.appendChild(tr);
    });
    var t = head($("id-top"), [["#", "num"], ["Rule"], ["Trades", "num"], ["Win %", "num"], ["PF", "num"], ["Net pts", "num"], ["Halves", "num"], ["Before", "num"]]);
    D.top.forEach(function (x, i) {
      var tr = el("tr"); td(tr, String(i + 1), "num"); td(tr, x.rule); td(tr, String(x.last200.n), "num"); td(tr, pct(x.last200.win), "num");
      td(tr, num(x.last200.pf, 2), "num"); td(tr, sg(x.last200.net, 0), tone(x.last200.net)); td(tr, sg(x.h1.net, 0) + " / " + sg(x.h2.net, 0), "num");
      td(tr, sg(x.pre.net, 0), tone(x.pre.net)); t.appendChild(tr);
    });
  }

  function renderTrades() {
    var T = D.trades.slice().reverse();
    $("id-tr-n").textContent = "· " + T.length + " trades in the year, newest first";
    var b = head($("id-trades"), [["Day"], ["Side"], ["In"], ["Price", "num"], ["Out"], ["Price", "num"], ["Lots", "num"], ["Points", "num"], ["Cost", "num"], ["P&L", "num"], ["Money after", "num"]]);
    T.forEach(function (t) {
      var tr = el("tr");
      td(tr, t.day); td(tr, t.side, t.side === "BUY" ? "up" : "dn"); td(tr, t.in_time); td(tr, num(t.in, 2), "num"); td(tr, t.out_time); td(tr, num(t.out, 2), "num");
      td(tr, t.lots + " × " + t.lot, "num"); td(tr, sg(t.points, 2), tone(t.points)); td(tr, inr(t.cost), "num"); td(tr, sinr(t.pnl), tone(t.pnl)); td(tr, inr(t.cash), "num");
      b.appendChild(tr);
    });
  }

  function renderData() {
    var c = D.data, ul = $("id-data"); ul.textContent = "";
    var add = function (t) { ul.appendChild(el("li", null, t)); };
    add(D.source + ": " + c.sessions + " sessions, " + c.from + " → " + c.to + ". Sessions with fewer than 25 candles: " + Object.keys(c.short_days).length + ".");
    if (c.vs_nse) {
      var f = c.vs_nse.fields;
      add("Against NSE's official daily Nifty 50 file on " + c.vs_nse.days + " days: open, high and low match (median gap " + f.open.median_pts + " / " +
        f.high.median_pts + " / " + f.low.median_pts + " pts; " + (f.open["days_over_0.05pct"] + f.high["days_over_0.05pct"] + f.low["days_over_0.05pct"]) +
        " days off by more than 0.05%). The last 15-minute close differs from NSE's official close by a median " + f.close.median_pts +
        " pts; the open, high and low match, so the gap is only in the closing value. The strategy never uses the official close.");
    }
    if (c.vs_yahoo_15m) add("Against the Yahoo Finance 15-minute candles we keep (" + c.vs_yahoo_15m.bars + " candles): median close gap " +
      c.vs_yahoo_15m.median_pts + " pts, 95% within " + c.vs_yahoo_15m.p95_pts + " pts.");
    var J = D.jev || {}, A = J.answers || {}, b = head($("id-jev"), [["Result (" + (J.model || "Jev") + " · " + (J.status || "") + ")"], ["Luck from fitting the past"], ["Real money?"]]);
    Object.keys(A).forEach(function (k) {
      var a = A[k], tr = el("tr"); td(tr, k);
      if (a.error) { td(tr, "not judged"); td(tr, a.error); } else { td(tr, a.overfit.choice + " (" + a.overfit.conf + "%)"); td(tr, a.real_money.choice + " (" + a.real_money.conf + "%)"); }
      b.appendChild(tr);
    });
    var l = $("id-limits"); l.textContent = ""; D.limits.forEach(function (x) { l.appendChild(el("li", null, x)); });
  }

  function boot() {
    fetch("intraday.json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) { D = d; renderTop(); renderNext(); renderChart(); renderPort(); renderMonths(); renderLast200(); renderTrades(); renderData(); })
      .catch(function (e) { $("id-sub").textContent = "Failed to load intraday.json: " + e.message; });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
