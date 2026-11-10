/* Nifty 5 methods · daily race. Renders methods.json (methods5.py, after every close).
   All text via textContent; the pie charts are built as SVG nodes, no innerHTML. */
(function () {
  "use strict";
  var D = null, FILTER = "all";
  var COLORS = { sma5200: "#15803d", st1015: "#b45309", psma100: "#1d4ed8", don55: "#7c3aed", ema21105: "#be185d",
                 f_council: "#0f766e", f_twinpulse: "#ea580c", f_quorum: "#0891b2", f_heartbeat: "#9f1239", f_centreline: "#65a30d" };
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
  function ranked() { return D.ranking.map(function (k) { return D.methods.filter(function (m) { return m.key === k; })[0]; }); }
  function chip(m) {
    var s = el("span", "m5-chip", m.name);
    s.style.background = COLORS[m.key] || "#334155";
    return s;
  }

  function renderWhy() {
    var ul = $("m5-why"); ul.textContent = "";
    D.reasons.forEach(function (r) { ul.appendChild(el("li", null, r)); });
  }

  function renderJev() {
    fetch("methods_jev.json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        var b = head($("m5-jev"), [["Method"], ["Jev grade"], ["Sturdiness /100", "r"], ["Confidence", "r"]]);
        ranked().forEach(function (m) {
          var a = (j.answers || {})[m.key], tr = el("tr");
          var c = el("td"); c.appendChild(chip(m)); tr.appendChild(c);
          td(tr, a && !a.error ? a.grade : "-", a && a.grade === "sturdy" ? "num up" : a && a.grade === "fragile" ? "num dn" : null);
          td(tr, a && !a.error ? num(a.score, 1) : "-", "r");
          td(tr, a && !a.error ? a.conf + "%" : "-", "r");
          b.appendChild(tr);
        });
        $("m5-jev-note").textContent = (j.status || "") + " · " + String(j.generated_at || "").replace("T", " ").slice(0, 16) +
          " · Jev's view is display only: the ranking above uses net points and nothing else.";
      })
      .catch(function () { $("m5-jev-note").textContent = "No Jev assessment file yet."; });
  }

  function renderDiary() {
    fetch("methods_events.json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (ev) {
        var ul = $("m5-diary"); ul.textContent = "";
        if (!ev.length) { ul.appendChild(el("li", null, "No changes recorded yet. From the next refresh on, every opened and closed trade lands here automatically.")); return; }
        ev.slice(0, 60).forEach(function (x) {
          var li = el("li");
          li.appendChild(el("b", null, String(x.at).replace("T", " ").slice(0, 16) + " · " + x.name + ": "));
          li.appendChild(document.createTextNode(x.text));
          ul.appendChild(li);
        });
      })
      .catch(function () { $("m5-diary").textContent = "No diary file yet."; });
  }

  function renderBoard() {
    var b = head($("m5-board"), [["#"], ["Method"], ["Candles"], ["Net points", "r"], ["₹ 1 lot", "r"], ["Total plus", "r"],
      ["Total minus", "r"], ["Open trade", "r"], ["Trades", "r"], ["Won", "r"], ["Profit factor", "r"],
      ["Worst fall", "r"], ["2026", "r"], ["Last 20 sessions", "r"], ["Last session", "r"], ["Side now"]]);
    ranked().forEach(function (m, i) {
      var s = m.summary, tr = el("tr");
      td(tr, String(i + 1));
      var c = el("td"); c.appendChild(chip(m));
      var a = el("a", null, " chart + trades"); a.href = "method.html?m=" + m.key; c.appendChild(a);
      if (m.page) { var a2 = el("a", null, " · best page"); a2.href = m.page; c.appendChild(a2); }
      tr.appendChild(c);
      td(tr, m.tf + " · " + m.family);
      td(tr, spts(s.net_pts), "r " + tone(s.net_pts));
      td(tr, sinr(s.net_rs), "r " + tone(s.net_rs));
      td(tr, "+" + num(s.plus_pts, 0), "r num up");
      td(tr, num(s.minus_pts, 0), "r num dn");
      td(tr, spts(s.open_pts), "r " + tone(s.open_pts));
      td(tr, num(s.trades), "r");
      td(tr, num(s.win_pct, 1) + "%", "r");
      td(tr, s.profit_factor == null ? "-" : num(s.profit_factor, 2), "r");
      td(tr, "-" + num(s.max_dd_pts, 0), "r num dn");
      td(tr, spts(s.y2026_pts), "r " + tone(s.y2026_pts));
      td(tr, spts(s.last20_pts), "r " + tone(s.last20_pts));
      td(tr, spts(s.last_session_pts), "r " + tone(s.last_session_pts));
      td(tr, (m.now.side || "-") + (m.now.entry ? " @ " + num(m.now.entry, 0) : ""), m.now.side === "BUY" ? "num up" : "num dn");
      $("m5-board").lastChild.appendChild(tr);
    });
  }

  var SVGNS = "http://www.w3.org/2000/svg";
  function pie(m) {
    var s = m.summary, plus = s.plus_pts, minus = Math.abs(s.minus_pts), total = plus + minus;
    var box = el("figure", "m5-pie");
    var svg = document.createElementNS(SVGNS, "svg");
    svg.setAttribute("viewBox", "0 0 120 120"); svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", m.name + ": won " + Math.round(plus) + " points, lost " + Math.round(minus));
    var r = 44, C = 2 * Math.PI * r;
    [["#dc2626", C], ["#16a34a", C * (total ? plus / total : 0)]].forEach(function (z) {
      var c = document.createElementNS(SVGNS, "circle");
      c.setAttribute("cx", "60"); c.setAttribute("cy", "60"); c.setAttribute("r", String(r));
      c.setAttribute("fill", "none"); c.setAttribute("stroke", z[0]); c.setAttribute("stroke-width", "16");
      c.setAttribute("stroke-dasharray", z[1] + " " + C); c.setAttribute("transform", "rotate(-90 60 60)");
      svg.appendChild(c);
    });
    var t1 = document.createElementNS(SVGNS, "text");
    t1.setAttribute("x", "60"); t1.setAttribute("y", "57"); t1.setAttribute("text-anchor", "middle");
    t1.setAttribute("class", "m5-pienet " + (s.net_pts >= 0 ? "up" : "dn"));
    t1.textContent = spts(Math.round(s.net_pts));
    var t2 = document.createElementNS(SVGNS, "text");
    t2.setAttribute("x", "60"); t2.setAttribute("y", "73"); t2.setAttribute("text-anchor", "middle");
    t2.setAttribute("class", "m5-piesub"); t2.textContent = "net pts";
    svg.appendChild(t1); svg.appendChild(t2);
    box.appendChild(svg);
    var cap = el("figcaption");
    cap.appendChild(chip(m));
    var cl = el("a", null, "open chart →"); cl.href = "method.html?m=" + m.key; cap.appendChild(cl);
    cap.appendChild(el("div", "m5-capline", "+" + num(plus, 0) + " won · −" + num(minus, 0) + " lost"));
    cap.appendChild(el("div", "m5-capline", sinr(s.net_rs) + " on 1 lot · " + (m.now.side || "-") + " now"));
    box.appendChild(cap);
    return box;
  }
  function renderPies() {
    var w = $("m5-pies"); w.textContent = "";
    ranked().forEach(function (m) { w.appendChild(pie(m)); });
  }

  function renderRace() {
    var box = $("m5-race");
    if (typeof LightweightCharts === "undefined") { box.textContent = "Chart library failed to load."; return; }
    var ch = LightweightCharts.createChart(box, {
      autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
      grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } },
      rightPriceScale: { borderColor: "#e2e8f0" }, timeScale: { borderColor: "#e2e8f0" }
    });
    D.methods.forEach(function (m, j) {
      var ls = ch.addLineSeries({ color: COLORS[m.key], lineWidth: 2, priceLineVisible: false, title: m.name });
      ls.setData(D.race.map(function (r) { return { time: r[0], value: r[1 + j] }; }));
    });
    ch.timeScale().fitContent();
    var lg = $("m5-legend"); lg.textContent = "";
    ranked().forEach(function (m) {
      var s = el("span", "m5-lg");
      var dot = el("i"); dot.style.background = COLORS[m.key];
      s.appendChild(dot); s.appendChild(document.createTextNode(m.name + " " + spts(m.summary.net_pts)));
      lg.appendChild(s);
    });
  }

  function renderFilter() {
    var box = $("m5-filter"); box.textContent = "";
    [["all", "All 10 methods"]].concat(D.methods.map(function (m) { return [m.key, m.name]; })).forEach(function (f) {
      var b = el("button", FILTER === f[0] ? "on" : null, f[1]); b.type = "button";
      b.addEventListener("click", function () { FILTER = f[0]; renderFilter(); renderTrades(); });
      box.appendChild(b);
    });
  }

  function renderTrades() {
    var rows = [];
    D.methods.forEach(function (m) {
      if (FILTER !== "all" && m.key !== FILTER) return;
      m.trades.forEach(function (t) { rows.push({ m: m, t: t }); });
    });
    rows.sort(function (a, b) { return a.t.entry_time < b.t.entry_time ? 1 : -1; });
    var closed = rows.filter(function (r) { return !r.t.open; });
    var plus = 0, minus = 0, open_ = 0;
    rows.forEach(function (r) {
      if (r.t.open) open_ += r.t.net_pts;
      else if (r.t.net_pts > 0) plus += r.t.net_pts;
      else minus += r.t.net_pts;
    });
    $("m5-tr-n").textContent = closed.length + " closed trades" + (rows.length - closed.length ? " + " + (rows.length - closed.length) + " open" : "") +
      " · total plus +" + num(plus, 0) + " · total minus " + num(minus, 0) + " · open " + spts(open_) +
      " · net " + spts(plus + minus + open_) + " points = " + sinr((plus + minus + open_) * D.lot) + " on 1 lot";
    var b = head($("m5-trades"), [["Method"], ["Side"], ["Entry (IST)"], ["Entry", "r"], ["Exit (IST)"], ["Exit", "r"],
      ["Points", "r"], ["₹ 1 lot", "r"]]);
    rows.slice(0, 1500).forEach(function (r) {
      var tr = el("tr", r.t.open ? "open" : null);
      var c = el("td"); c.appendChild(chip(r.m)); tr.appendChild(c);
      td(tr, r.t.side, "side-" + r.t.side);
      td(tr, r.t.entry_time);
      td(tr, num(r.t.entry, 2), "r");
      td(tr, r.t.open ? "open" : r.t.exit_time);
      td(tr, num(r.t.exit, 2), "r");
      td(tr, spts(r.t.net_pts), "r " + tone(r.t.net_pts));
      td(tr, sinr(r.t.rupees), "r " + tone(r.t.rupees));
      $("m5-trades").lastChild.appendChild(tr);
    });
  }

  function renderFoot() {
    var l = $("m5-limits"); l.textContent = "";
    D.limits.forEach(function (x) { l.appendChild(el("li", null, x)); });
  }

  function boot() {
    fetch("methods.json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        D = d;
        $("m5-sub").textContent = "10 always-in rules (5 classics + 5 Fable originals), one trade at every close · " + D.from + " → " + D.last_candle + " IST · " +
          D.total_closed_trades + " closed trades · rebuilt " + D.generated_at.replace("T", " ").slice(0, 16);
        renderWhy(); renderBoard(); renderPies(); renderRace(); renderFilter(); renderTrades(); renderFoot(); renderJev(); renderDiary();
        document.body.dataset.ready = "true";
      })
      .catch(function (e) { $("m5-sub").textContent = "Failed to load methods.json: " + e.message; document.body.dataset.ready = "error"; });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
