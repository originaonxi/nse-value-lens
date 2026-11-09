/* Homepage: NIFTY 50 best setup (nifty_best.json, built after each close by nifty_best.py).
   Chart: TradingView Lightweight Charts (vendor). All text via textContent. */
(function () {
  "use strict";
  var D = null;
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
  function fin(v) { return typeof v === "number" && isFinite(v); }
  function num(v, d) { return fin(v) ? v.toLocaleString("en-IN", { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }) : "—"; }
  function sg(v, d) { return fin(v) ? (v > 0 ? "+" : "") + num(v, d == null ? 2 : d) : "—"; }
  function pc(v, d) { return fin(v) ? num(v, d == null ? 1 : d) + "%" : "—"; }
  function td(tr, t, c) { var x = el("td", c || null, t); tr.appendChild(x); return x; }
  function head(tbl, cols) {
    tbl.textContent = ""; var th = el("thead"), tr = el("tr");
    cols.forEach(function (c) { var h = el("th", c[1] || null, c[0]); if (c[2]) h.title = c[2]; tr.appendChild(h); });
    th.appendChild(tr); tbl.appendChild(th); var tb = el("tbody"); tbl.appendChild(tb); return tb;
  }
  function sline(s) { return s && s.n ? s.n + " · " + pc(s.win) + " · PF " + num(s.pf, 2) + " · " + sg(s.net, 1) + "%" : "—"; }

  function live(L, b, boxId) {
    var box = $(boxId);
    box.textContent = "";
    var cls = /BUY|IN TRADE/.test(L.state) ? (b.side === 1 ? "long" : "short") : /EXIT/.test(L.state) ? "exit" : "wait";
    box.className = "hn-live " + cls;
    box.appendChild(el("small", null, "NIFTY 50 · LAST 2-HOUR CLOSE " + L.bar + " IST"));
    box.appendChild(el("b", null, L.state + " · " + (b.side === 1 ? "BUY setup" : "SELL setup")));
    box.appendChild(el("p", null, L.note));
    var ul = el("ul", "hn-checks");
    L.checks.forEach(function (c) {
      var li = el("li", c.ok ? "ok" : "no"); li.appendChild(el("span", null, c.ok ? "✓ " : "✗ "));
      li.appendChild(document.createTextNode(c.name + " — " + c.value)); ul.appendChild(li);
    });
    box.appendChild(ul);
    box.appendChild(el("p", "fd-note", "Close " + num(L.close, 2) + " · EMA 105 " + num(L.ema, 2) + " · RSI " + num(L.rsi, 1) + " · ATR " + num(L.atr, 0) + " points"));
  }

  function setup(b, ruleId, kpiId) {
    var a = b.all;
    $(ruleId).textContent = b.label;
    var k = $(kpiId); k.textContent = "";
    function kpi(label, val, sub, cls) {
      var d = el("div", "hn-kpi" + (cls ? " " + cls : "")); d.appendChild(el("small", null, label));
      d.appendChild(el("strong", null, val)); if (sub) d.appendChild(el("span", null, sub)); k.appendChild(d);
    }
    kpi("Win rate", pc(a.win), a.n + " trades · Bayesian " + pc(b.bayes), a.win >= 80 ? "good" : "");
    kpi("Profit factor", num(a.pf, 2), "winning % ÷ losing %");
    kpi("Net", sg(a.net, 1) + "%", sg(b.points, 0) + " Nifty points after costs", a.net > 0 ? "good" : "bad");
    kpi("Avg win / avg loss", sg(a.avg_win, 2) + "% / −" + num(a.avg_loss, 2) + "%", "per trade");
    kpi("Worst drawdown", pc(a.dd), "sum of trade %");
    kpi("Every third profitable", b.every_third ? "yes" : "no", b.thirds.map(function (t) { return pc(t.win, 0); }).join(" / ") + " win by third");
    kpi("t-stat", num(b.t, 2), b.t >= 2 ? "beyond luck on its own" : "below 2: could be luck");
    if (b.jev && b.jev.reliability) kpi("Jev", b.jev.reliability.toUpperCase(), "overfit risk " + b.jev.overfit);
  }

  function setups() {
    live(D.live, D.best, "hn-live");
    setup(D.best, "hn-rule", "hn-kpis");
    if (D.setup80) {
      $("hn-80wrap").hidden = false;
      live(D.setup80.live, D.setup80, "hn-live80");
      setup(D.setup80, "hn-rule80", "hn-kpis80");
    }
    if (D.sell) {
      $("hn-sellwrap").hidden = false;
      live(D.sell.live, D.sell, "hn-livesell");
      setup(D.sell, "hn-rulesell", "hn-kpissell");
    }
    $("hn-period").textContent = D.period.from + " → " + D.period.to + " · " + D.period.sessions + " sessions · " + num(D.tried, 0) +
      " rules tried · " + num(D.robust_count, 0) + " made money in every third · luck level Sharpe " + num(D.luck_sharpe, 2);
  }

  var CH = null, SER = null, WIN = null;
  var SETS = [["A", "Setup A · best by the maths"], ["B", "Setup B · 80% win"], ["S", "Setup C · best SELL"]];
  var WHY = { ema: "close through EMA 105", top: "RSI top", target: "ATR target", stop: "ATR stop", time: "time limit" };

  function setupFor(key) { return key === "A" ? D.best : key === "B" ? D.setup80 : D.sell; }

  function showWinner() {
    var times = {}; D.chart.bars.forEach(function (b) { times[b[0]] = 1; });
    var ms = WIN.markers.filter(function (m) { return times[m[0]]; });
    SER.setMarkers(ms.map(function (m) {
      var buy = m[2] === "BUY";
      if (m[1] === "entry") return { time: m[0], position: buy ? "belowBar" : "aboveBar", color: buy ? "#16a34a" : "#dc2626",
        shape: buy ? "arrowUp" : "arrowDown", text: m[4], size: 1.2 };
      var good = m[4].charAt(0) === "+";
      return { time: m[0], position: buy ? "aboveBar" : "belowBar", color: good ? "#15803d" : "#b91c1c", shape: "circle", text: m[4], size: 0.9 };
    }).sort(function (a, b) { return a.time - b.time; }));
    Array.prototype.forEach.call($("hn-switch").children, function (x) { x.classList.toggle("on", x.dataset.k === "W"); });
    $("hn-chart-note").textContent = "₹1 crore winner (" + WIN.name + "): " + WIN.rules.join("  ‖  ") +
      ". ▲ = BUY, ▼ = SELL (short), ● = exit with the rupee result on ₹1 crore of whole NIFTY lots. " +
      ms.filter(function (m) { return m[1] === "entry"; }).length + " entries in the last 140 sessions; the whole 2 years are on the ₹1 crore page.";
  }

  function addWinner() {
    fetch("crore.json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (c) {
        WIN = c.windows && c.windows["2y"] && c.windows["2y"].winner;
        if (!WIN || !SER) return;
        var bt = el("button", null, "₹1 crore winner · " + (WIN.return_pct > 0 ? "+" : "") + WIN.return_pct.toFixed(1) + "% in 2 years");
        bt.type = "button"; bt.dataset.k = "W";
        bt.addEventListener("click", showWinner);
        $("hn-switch").insertBefore(bt, $("hn-switch").firstChild);
        showWinner();
      })
      .catch(function () { /* the A/B/C setups still work without it */ });
  }

  function showSet(key) {
    var ch = D.chart, set = (ch.sets || {})[key] || ch.markers || [], b = setupFor(key);
    SER.setMarkers(set.map(function (m) {
      var buy = m[1] === "buy", entry = m[3] == null;
      var txt = (buy ? "BUY" : "SELL") + (entry ? "" : " " + sg(m[3], 2) + "%");
      return { time: m[0], position: buy ? "belowBar" : "aboveBar", color: buy ? "#16a34a" : "#dc2626",
               shape: buy ? "arrowUp" : "arrowDown", text: txt, size: entry ? 1.2 : 0.9 };
    }));
    Array.prototype.forEach.call($("hn-switch").children, function (x) { x.classList.toggle("on", x.dataset.k === key); });
    var entries = set.filter(function (m) { return m[3] == null; }).length, exits = set.length - entries;
    $("hn-chart-note").textContent = (b ? b.label + ". " : "") + (b && b.side === -1
      ? "SELL ▼ = short Nifty at that 2-hour close; BUY ▲ with a % = buy back (exit), result after costs."
      : "BUY ▲ = buy at that 2-hour close; SELL ▼ with a % = sell (exit), result after costs.") +
      " " + entries + " entries and " + exits + " exits in the last 140 sessions. Exit reasons: " +
      Object.keys(WHY).map(function (k) { return WHY[k]; }).join(", ") + ".";
  }

  function chart() {
    var box = $("hn-chart");
    if (typeof LightweightCharts === "undefined") { box.textContent = "Chart library failed to load."; return; }
    CH = LightweightCharts.createChart(box, {
      autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
      grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } },
      rightPriceScale: { borderColor: "#e2e8f0" }, timeScale: { borderColor: "#e2e8f0", timeVisible: true, secondsVisible: false, rightOffset: 4 }
    });
    SER = CH.addCandlestickSeries({ upColor: "#16a34a", downColor: "#dc2626", borderUpColor: "#16a34a", borderDownColor: "#dc2626", wickUpColor: "#16a34a", wickDownColor: "#dc2626" });
    var ch = D.chart;
    SER.setData(ch.bars.map(function (b) { return { time: b[0], open: b[1], high: b[2], low: b[3], close: b[4] }; }));
    var l = CH.addLineSeries({ color: "#2563eb", lineWidth: 2, priceLineVisible: false, title: "EMA 105" });
    l.setData(ch.bars.map(function (b, i) { return { time: b[0], value: ch.ema[i] }; }));
    var sw = $("hn-switch"); sw.textContent = "";
    SETS.forEach(function (s) {
      if (!setupFor(s[0]) || !(ch.sets || {})[s[0]]) return;
      var bt = el("button", null, s[1]); bt.type = "button"; bt.dataset.k = s[0];
      bt.addEventListener("click", function () { showSet(s[0]); });
      sw.appendChild(bt);
    });
    showSet("A");
    addWinner();
    var n = ch.bars.length;
    CH.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 300), to: n + 3 });
    // why 2-hour candles
    var T = D.timeframes || [];
    if (T.length) {
      var top = T[0], tfname = { "5m": "5 min", "15m": "15 min", "30m": "30 min", "75m": "75 min", "1h": "1 hour", "2h": "2 hour", "1D": "daily" };
      $("hn-tf").textContent = " · the best timeframe: " + tfname[top.tf] + " candles ranked first of " + T.length + " timeframes tested (EMA 3-200 on each)";
      $("hn-tf-wrap").hidden = false;
      var tb = head($("hn-tf-table"), [["Rank"], ["Candles"], ["Best EMA", "num"], ["Signals", "num"], ["Profit factor", "num"], ["Net points", "num"], ["Score", "num"]]);
      T.forEach(function (t, i) {
        var tr = el("tr", i === 0 ? "hn-best" : null);
        td(tr, String(i + 1)); td(tr, tfname[t.tf] || t.tf); td(tr, String(t.ema), "num"); td(tr, num(t.trades, 0), "num");
        td(tr, num(t.pf, 2), "num"); td(tr, sg(t.net, 0), t.net > 0 ? "num up" : "num dn"); td(tr, num(t.final, 1), "num");
        tb.appendChild(tr);
      });
    }
  }

  function tables() {
    var tb = head($("hn-comp"), [["Rule"], ["Trades", "num"], ["Win %", "num"], ["Bayes win %", "num"], ["PF", "num"], ["Net %", "num"], ["Points", "num"], ["Last 200 sessions: trades · win · PF · net", null]]);
    D.comparison.forEach(function (r, i) {
      var tr = el("tr", i >= 2 ? "hn-best" : null), a = r.all, z = r.last200;
      td(tr, r.rule); td(tr, String(a.n), "num"); td(tr, pc(a.win), "num"); td(tr, pc(a.bayes), "num"); td(tr, num(a.pf, 2), "num");
      td(tr, sg(a.net, 1), a.net > 0 ? "num up" : "num dn"); td(tr, sg(a.points, 0), "num"); td(tr, sline(z)); tb.appendChild(tr);
    });
    var w = D.win80;
    $("hn-80").textContent = num(w.count, 0) + " of " + num(D.tried, 0) + " rules won 80% or more of their trades (" + num(20, 0) + "+ trades). " +
      w.every_third + " of them also made money in every third of the " + D.period.sessions + " sessions. High win rates come from small targets: " +
      "they win often and lose big, so look at the profit factor and the net, not the win rate alone.";
    tb = head($("hn-80t"), [["Rule"], ["Whole: trades · win · PF · net"], ["1st third"], ["2nd third"], ["3rd third (unseen)"], ["Every third"]]);
    (w.robust_rules.length ? w.robust_rules : w.rules).slice(0, 12).forEach(function (r) {
      var tr = el("tr", r.every_third ? "hn-best" : null);
      td(tr, r.label); td(tr, sline(r.all)); r.thirds.forEach(function (t) { td(tr, sline(t), t.pf > 1 ? "up" : "dn"); }); td(tr, r.every_third ? "✓" : "✗");
      tb.appendChild(tr);
    });
    tb = head($("hn-fin"), [["#"], ["Rule"], ["Whole"], ["Unseen third"], ["Jev"], ["Score", "num"]]);
    D.finalists.forEach(function (r, i) {
      var tr = el("tr", i === 0 ? "hn-best" : null), j = r.jev || {};
      td(tr, String(i + 1)); td(tr, r.label); td(tr, sline(r.all)); td(tr, sline(r.thirds[2]));
      td(tr, j.reliability ? j.reliability + " · overfit " + j.overfit : "—"); td(tr, num(r.final, 1), "num"); tb.appendChild(tr);
    });
    tb = head($("hn-tr"), [["Entry"], ["Price", "num"], ["Exit"], ["Price", "num"], ["Why"], ["Result %", "num"]]);
    D.trades.slice().reverse().slice(0, 25).forEach(function (t) {
      var tr = el("tr"); td(tr, t[0]); td(tr, num(t[1], 2), "num"); td(tr, t[5] === "open" ? "still open" : t[2]); td(tr, num(t[3], 2), "num");
      td(tr, t[5]); td(tr, sg(t[4], 2), t[4] > 0 ? "num up" : "num dn"); tb.appendChild(tr);
    });
    var lim = $("hn-limits"); lim.textContent = ""; D.limits.forEach(function (x) { lim.appendChild(el("li", null, x)); });
  }

  function boot() {
    if (!$("hn-section")) return;
    fetch("nifty_best.json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) { D = d; setups(); tables(); chart(); })
      .catch(function (e) { $("hn-period").textContent = "Failed to load the Nifty 50 setup: " + e.message; });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
