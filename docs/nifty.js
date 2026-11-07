/* Nifty 50 — ONE EMA. Renders docs/nifty.json (version 2) with TradingView Lightweight Charts.
   One chart, one EMA line, ▲/▼ on every close that switches sides. All text via textContent. */
(function () {
  "use strict";
  var D = null, chart = null, candles = null, line = null, flipLine = null, userLines = [];
  var state = { tf: null, win: 140, drawing: false };
  var LS_KEY = "nifty-one-ema-lines";
  var TF_NAME = { "5m": "5 min", "15m": "15 min", "30m": "30 min", "75m": "75 min", "1h": "1 hour", "2h": "2 hour", "1D": "Daily" };

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, txt) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt != null) e.textContent = txt;
    return e;
  }
  function num(v, d) {
    if (v == null || !isFinite(v)) return "—";
    return Number(v).toLocaleString("en-IN", { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 });
  }
  function pct(v) { return v == null ? "—" : num(v, 1) + "%"; }
  function signed(v, d) { return v == null ? "—" : (v > 0 ? "+" : "") + num(v, d == null ? 1 : d); }
  function cell(tr, txt, cls) { var td = el("td", cls || null, txt); tr.appendChild(td); return td; }
  function head(tbl, cols) {
    tbl.textContent = "";
    var th = el("thead"), tr = el("tr");
    cols.forEach(function (c) { var h = el("th", c[1] || null, c[0]); if (c[2]) h.title = c[2]; tr.appendChild(h); });
    th.appendChild(tr); tbl.appendChild(th);
    var tb = el("tbody"); tbl.appendChild(tb); return tb;
  }
  function tone(v) { return v == null ? "num" : v > 0 ? "num up" : v < 0 ? "num dn" : "num"; }

  /* ── header + answer ─────────────────────────────────────────────────── */
  function renderHead() {
    $("nf-close").textContent = num(D.last_close, 2);
    var chg = $("nf-chg"); chg.textContent = signed(D.change_pct, 2) + "%";
    chg.className = D.change_pct >= 0 ? "up" : "dn";
    $("nf-asof").textContent = "Last close " + D.as_of + " · updated " + D.generated_at.replace("T", " ") +
      " IST · " + num(D.tested.rules) + " EMA rules tested (EMA " + D.tested.ema_from + "–" + D.tested.ema_to +
      " × " + D.tested.timeframes.length + " timeframes)";

    var c = D.chosen, n = c.now, s = $("nf-signal");
    s.textContent = "";
    var up = n.side === "ABOVE";
    s.className = "nf-signal " + (up ? "long" : "short");
    s.appendChild(el("b", null, (up ? "▲ ABOVE" : "▼ BELOW") + " · " + TF_NAME[c.tf] + " EMA " + c.ema));
    s.appendChild(el("span", null, "Close " + num(n.close, 2) + " vs EMA " + num(n.ema, 2) +
      " (" + signed(n.close - n.ema, 1) + " pts)"));
    s.appendChild(el("span", null, (up ? "View is UP" : "View is DOWN") + " since " + (n.since || "—") +
      " · flips if a " + TF_NAME[c.tf] + " candle closes " + (up ? "below " : "above ") + num(n.flip_level, 0)));

    var a = $("nf-answer"), m = c.main, j = c.jev || {};
    a.textContent = "";
    var h = el("h2", null, "The one EMA: " + TF_NAME[c.tf] + " candles, EMA " + c.ema);
    a.appendChild(h);
    a.appendChild(el("p", null,
      "When a " + TF_NAME[c.tf] + " candle closes above EMA " + c.ema + ", treat Nifty as going up; when one closes below, " +
      "treat it as going down. Keep that view until the opposite close."));
    var k = el("div", "nf-kpis");
    function kpi(label, val, sub, cls) {
      var b = el("div", "nf-kpi" + (cls ? " " + cls : ""));
      b.appendChild(el("small", null, label)); b.appendChild(el("strong", null, val));
      if (sub) b.appendChild(el("span", null, sub));
      k.appendChild(b);
    }
    kpi("Points after costs", signed(m.net, 0), m.sessions + " sessions (" + D.main_from + " →)", m.net > 0 ? "up" : "dn");
    kpi("Close-above signals", signed(m.up_net, 0) + " pts", m.up_n + " signals, " + pct(m.up_hit) + " went up", m.up_net > 0 ? "up" : "dn");
    kpi("Close-below signals", signed(m.down_net, 0) + " pts", m.down_n + " signals, " + pct(m.down_hit) + " went down", m.down_net > 0 ? "up" : "dn");
    kpi("Profit factor", num(m.pf, 2), "winning pts ÷ losing pts");
    kpi("Worst drawdown", num(m.max_dd, 0) + " pts", "");
    kpi("Last " + D.recent + " sessions", signed(c.recent.net, 0) + " pts", c.recent.trades + " signals", c.recent.net > 0 ? "up" : "dn");
    if (c.full && c.full.sessions > m.sessions)
      kpi("Longer history", signed(c.full.net, 0) + " pts", c.full.sessions + " sessions, PF " + num(c.full.pf, 2), c.full.net > 0 ? "up" : "dn");
    kpi("Jev", j.reliability ? j.reliability.toUpperCase() : "—",
      j.recent_edge ? "edge " + j.recent_edge + " · score " + num(j.jev_score, 0) : (D.jev && D.jev.status) || "not judged");
    a.appendChild(k);
    a.appendChild(el("p", "fd-note",
      "Most signals are small losses; the money comes from a few long runs. Profitable 10-session blocks: " +
      (m.blocks_pos != null ? m.blocks_pos + " of " + m.blocks : "—") + ". Costs: " + num(D.cost_pct, 3) +
      "% of price per signal (≈ " + num(D.cost_points_now, 1) + " points)."));
  }

  /* ── chart ───────────────────────────────────────────────────────────── */
  function dayOf(t) { return typeof t === "string" ? t : Math.floor(t / 86400); }

  function buildChart() {
    var box = $("chart-main");
    chart = LightweightCharts.createChart(box, {
      autoSize: true,
      layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
      grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } },
      rightPriceScale: { borderColor: "#e2e8f0" },
      timeScale: { borderColor: "#e2e8f0", timeVisible: true, secondsVisible: false, rightOffset: 4 },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal }
    });
    candles = chart.addCandlestickSeries({
      upColor: "#16a34a", downColor: "#dc2626", borderUpColor: "#16a34a", borderDownColor: "#dc2626",
      wickUpColor: "#16a34a", wickDownColor: "#dc2626"
    });
    line = chart.addLineSeries({ color: "#2563eb", lineWidth: 2, priceLineVisible: false, lastValueVisible: true });
    chart.subscribeCrosshairMove(legend);
    chart.subscribeClick(function (p) {
      if (!state.drawing || !p || !p.point) return;
      var price = candles.coordinateToPrice(p.point.y);
      if (price == null) return;
      var saved = loadLines(); saved.push(Math.round(price * 100) / 100); saveLines(saved);
      state.drawing = false; $("nf-draw").classList.remove("on");
      drawUserLines();
    });
  }

  function legend(p) {
    var c = D.charts[state.tf], lg = $("nf-legend");
    var bar = null, ev = null;
    if (p && p.time != null) {
      for (var i = c.bars.length - 1; i >= 0; i--) if (c.bars[i][0] === p.time) { bar = c.bars[i]; ev = c.ema_values[i]; break; }
    }
    if (!bar) { bar = c.bars[c.bars.length - 1]; ev = c.ema_values[c.ema_values.length - 1]; }
    var t = typeof bar[0] === "string" ? bar[0] : new Date(bar[0] * 1000).toISOString().slice(0, 16).replace("T", " ");
    lg.textContent = TF_NAME[state.tf] + " " + t + "  O " + num(bar[1], 2) + "  H " + num(bar[2], 2) + "  L " +
      num(bar[3], 2) + "  C " + num(bar[4], 2) + "   EMA " + c.ema + ": " + num(ev, 2) +
      (ev != null ? (bar[4] > ev ? "  ▲ close above" : "  ▼ close below") : "");
  }

  function showTf(tf) {
    state.tf = tf;
    var c = D.charts[tf];
    candles.setData(c.bars.map(function (b) { return { time: b[0], open: b[1], high: b[2], low: b[3], close: b[4] }; }));
    var ld = [];
    c.bars.forEach(function (b, i) { if (c.ema_values[i] != null) ld.push({ time: b[0], value: c.ema_values[i] }); });
    line.setData(ld);
    line.applyOptions({ title: "EMA " + c.ema });
    var first = c.bars.length ? c.bars[0][0] : null;
    candles.setMarkers(c.markers.filter(function (m) { return first == null || m[0] >= first; }).map(function (m) {
      var up = m[1] > 0;
      return { time: m[0], position: up ? "belowBar" : "aboveBar", color: up ? "#16a34a" : "#dc2626",
               shape: up ? "arrowUp" : "arrowDown", size: 0.6 };
    }));
    if (flipLine) candles.removePriceLine(flipLine);
    flipLine = candles.createPriceLine({ price: c.ema_now, color: "#2563eb", lineWidth: 1, lineStyle: 2,
      axisLabelVisible: true, title: "flip " + num(c.ema_now, 0) });
    drawUserLines();
    Array.prototype.forEach.call($("nf-tf").children, function (b) { b.classList.toggle("on", b.dataset.tf === tf); });
    setWindow(state.win);
    legend(null);
  }

  function setWindow(n) {
    state.win = n;
    var c = D.charts[state.tf], bars = c.bars;
    if (!bars.length) return;
    var days = [], seen = {};
    for (var i = bars.length - 1; i >= 0; i--) {
      var d = dayOf(bars[i][0]);
      if (!seen[d]) { seen[d] = 1; days.push(i); if (days.length >= n) break; }
    }
    var from = days[days.length - 1];
    if (state.tf === "1D") from = Math.max(0, bars.length - n);
    else { while (from > 0 && dayOf(bars[from - 1][0]) === dayOf(bars[from][0])) from--; }
    chart.timeScale().setVisibleLogicalRange({ from: from, to: bars.length + 3 });
    Array.prototype.forEach.call($("nf-win").children, function (b) { b.classList.toggle("on", +b.dataset.win === n); });
  }

  function loadLines() { try { return JSON.parse(localStorage.getItem(LS_KEY) || "[]"); } catch (e) { return []; } }
  function saveLines(a) { try { localStorage.setItem(LS_KEY, JSON.stringify(a)); } catch (e) { /* private mode */ } }
  function drawUserLines() {
    userLines.forEach(function (l) { candles.removePriceLine(l); });
    userLines = loadLines().map(function (p) {
      return candles.createPriceLine({ price: p, color: "#f59e0b", lineWidth: 1, lineStyle: 0, axisLabelVisible: true, title: "" });
    });
  }

  function renderControls() {
    var g = $("nf-tf"); g.textContent = "";
    D.tested.timeframes.forEach(function (tf) {
      if (!D.charts[tf]) return;
      var b = el("button", null, TF_NAME[tf] + " · EMA " + D.charts[tf].ema);
      b.type = "button"; b.dataset.tf = tf;
      b.addEventListener("click", function () { showTf(tf); });
      g.appendChild(b);
    });
    Array.prototype.forEach.call($("nf-win").children, function (b) {
      b.addEventListener("click", function () { setWindow(+b.dataset.win); });
    });
    $("nf-draw").addEventListener("click", function () {
      state.drawing = !state.drawing; this.classList.toggle("on", state.drawing);
    });
    $("nf-clear").addEventListener("click", function () { saveLines([]); drawUserLines(); });
  }

  /* ── tables ──────────────────────────────────────────────────────────── */
  function renderFinalists() {
    $("t-fin-note").textContent = "All rules ranked on the same " + D.main_sessions + " sessions (" + D.main_from +
      " → " + D.as_of + "). Final = 60% numbers + 40% Jev. ✓ = makes money on both close-above and close-below signals.";
    var tb = head($("t-fin"), [["#"], ["Candles"], ["EMA", "num"], ["Both ways", null, "Close-above AND close-below signals both made money"],
      ["Signals", "num"], ["Close above → up", "num"], ["Close below → down", "num"], ["Net pts", "num"], ["PF", "num"],
      ["Last 10", "num"], ["Jev", null], ["Final", "num"]]);
    D.finalists.forEach(function (r, i) {
      var m = r.main, j = r.jev || {}, tr = el("tr", r.key === D.chosen.key ? "nf-chosen" : null);
      cell(tr, String(i + 1)); cell(tr, TF_NAME[r.tf]); cell(tr, String(r.ema), "num");
      cell(tr, r.two_sided ? "✓" : "—", r.two_sided ? "up" : "dn");
      cell(tr, String(m.trades), "num");
      cell(tr, pct(m.up_hit) + " · " + signed(m.up_net, 0), tone(m.up_net));
      cell(tr, pct(m.down_hit) + " · " + signed(m.down_net, 0), tone(m.down_net));
      cell(tr, signed(m.net, 0), tone(m.net)); cell(tr, num(m.pf, 2), "num");
      cell(tr, signed(r.recent.net, 0), tone(r.recent.net));
      cell(tr, j.reliability ? j.reliability + " / " + j.recent_edge : (j.error ? "error" : "—"));
      cell(tr, num(r.final, 1), "num");
      tr.style.cursor = "pointer";
      tr.addEventListener("click", function () {
        if (D.charts[r.tf] && D.charts[r.tf].ema === r.ema) { showTf(r.tf); $("chart-main").scrollIntoView({ behavior: "smooth", block: "center" }); }
      });
      tb.appendChild(tr);
    });
  }

  function renderAsked() {
    var tb = head($("t-asked"), [["Candles"], ["EMA 5", "num"], ["EMA 6", "num"], ["EMA 9", "num"], ["EMA 10", "num"], ["EMA 11", "num"]]);
    var by = {};
    D.asked.forEach(function (r) { (by[r.tf] = by[r.tf] || {})[r.ema] = r; });
    D.tested.timeframes.forEach(function (tf) {
      if (!by[tf]) return;
      var tr = el("tr"); cell(tr, TF_NAME[tf]);
      [5, 6, 9, 10, 11].forEach(function (e) {
        var r = by[tf][e];
        if (!r) { cell(tr, "—", "num"); return; }
        var td = cell(tr, signed(r.main.net, 0) + " pts", tone(r.main.net));
        td.title = r.main.trades + " signals, PF " + num(r.main.pf, 2) + ", up " + pct(r.main.up_hit) + ", down " + pct(r.main.down_hit);
      });
      tb.appendChild(tr);
    });
  }

  function renderSignals() {
    var c = D.chosen, sig = c.signals.slice().reverse();
    $("t-sig-sub").textContent = "(" + TF_NAME[c.tf] + " EMA " + c.ema + ", last " + D.window + " sessions, " + sig.length + " signals)";
    var tb = head($("t-sig"), [["Signal"], ["Close", "num"], ["Until"], ["Exit close", "num"], ["Points after cost", "num"]]);
    sig.forEach(function (s) {
      var tr = el("tr");
      cell(tr, (s[1] > 0 ? "▲ closed above · " : "▼ closed below · ") + s[0], s[1] > 0 ? "up" : "dn");
      cell(tr, num(s[2], 2), "num");
      cell(tr, s[6] ? s[3] : "running (" + s[3] + ")");
      cell(tr, num(s[4], 2), "num");
      cell(tr, signed(s[5], 1), tone(s[5]));
      tb.appendChild(tr);
    });
  }

  function renderMethod() {
    var ol = $("nf-method"); ol.textContent = "";
    [
      "Rule: a candle closes above EMA(n) → view up. A candle closes below → view down. The view only changes on the opposite close.",
      "Tested every EMA from " + D.tested.ema_from + " to " + D.tested.ema_to + " on " + D.tested.timeframes.map(function (t) { return TF_NAME[t]; }).join(", ") + " candles (" + num(D.tested.rules) + " rules).",
      "Each signal is measured from its close to the next opposite close (the running one at the latest close), after costs.",
      "Score: points per session, profit factor, how many 10-session blocks were profitable, next-session follow-through, and whether BOTH the up and the down signals made money. Rules that work only one way are marked down.",
      "Jev (" + ((D.jev && D.jev.model) || "—") + ", " + ((D.jev && D.jev.status) || "—") + ") judged the best EMA of each timeframe on reliability and recent edge.",
      "Re-run automatically after every NSE close; the chart, EMA and flip level update with it."
    ].forEach(function (t) { ol.appendChild(el("li", null, t)); });
    var ul = $("nf-limits"); ul.textContent = "";
    (D.limits || []).forEach(function (t) { ul.appendChild(el("li", null, t)); });
  }

  function boot() {
    fetch("nifty.json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        D = d;
        renderHead(); renderFinalists(); renderAsked(); renderSignals(); renderMethod(); renderControls();
        if (typeof LightweightCharts === "undefined") { $("chart-main").textContent = "Chart library failed to load."; return; }
        buildChart();
        showTf(D.chosen.tf);
      })
      .catch(function (e) { $("nf-asof").textContent = "Failed to load nifty.json: " + e.message; });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
