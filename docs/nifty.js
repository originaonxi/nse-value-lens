/* Nifty 50 — ONE EMA. Renders docs/nifty.json (version 2) with TradingView Lightweight Charts.
   One chart, one EMA line, ▲/▼ on every close that switches sides. All text via textContent. */
(function () {
  "use strict";
  var D = null, C = null, chart = null, candles = null, line = null;
  var state = { tf: null, win: 140, mode: "ema" };
  var pnl = null;
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
    kpi("Last " + D.recent + " sessions", signed(c.recent.net, 0) + " pts", c.recent.trades + (c.recent.trades === 1 ? " signal" : " signals"), c.recent.net > 0 ? "up" : "dn");
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
    candles.priceScale().applyOptions({ scaleMargins: { top: 0.05, bottom: 0.3 } });
    line = chart.addLineSeries({ color: "#2563eb", lineWidth: 2, priceLineVisible: false, lastValueVisible: true });
    pnl = chart.addBaselineSeries({
      priceScaleId: "pts", baseValue: { type: "price", price: 0 }, lineWidth: 2, priceLineVisible: false,
      topLineColor: "#16a34a", topFillColor1: "#16a34a33", topFillColor2: "#16a34a08",
      bottomLineColor: "#dc2626", bottomFillColor1: "#dc262608", bottomFillColor2: "#dc262633",
      title: "points made", priceFormat: { type: "price", precision: 0, minMove: 1 }
    });
    chart.priceScale("pts").applyOptions({ scaleMargins: { top: 0.75, bottom: 0.02 } });
    chart.subscribeCrosshairMove(legend);
  }

  /* Running points of a set of trades, marked to market on every candle of the chart (after costs). */
  function toTime(s) { return Math.floor(Date.parse(s.replace(" ", "T") + ":00Z") / 1000); }
  function equity(bars, trades, cost) {
    var idx = {}; bars.forEach(function (b, i) { idx[b[0]] = i; });
    var step = new Array(bars.length).fill(0), total = 0, n = 0, wins = 0;
    trades.forEach(function (t) {
      var a = idx[toTime(t[0])], z = t[6] === "open" || t[6] === false ? bars.length - 1 : idx[toTime(t[3])];
      if (a == null) return;                      // trade started before the chart window
      if (z == null) z = bars.length - 1;
      step[a] -= cost * bars[a][4];
      for (var k = a + 1; k <= z; k++) step[k] += t[1] * (bars[k][4] - bars[k - 1][4]);
      n++; if (t[5] > 0) wins++;
    });
    var out = [];
    bars.forEach(function (b, i) { total += step[i]; out.push({ time: b[0], value: Math.round(total * 10) / 10 }); });
    return { data: out, total: total, n: n, wins: wins };
  }
  function currentTrades() {
    var useCombo = state.mode === "combo" && C && C.chart && state.tf === C.tf;
    if (useCombo) return C.trades;
    return D.chosen.signals.map(function (s) { return [s[0], s[1], s[2], s[3], s[4], s[5], s[6] ? "closed" : "open"]; });
  }

  function legend(p) {
    var c = D.charts[state.tf], lg = $("nf-legend");
    var bar = null, ev = null, pv = null, i;
    if (p && p.time != null) {
      for (i = c.bars.length - 1; i >= 0; i--) if (c.bars[i][0] === p.time) { bar = c.bars[i]; ev = c.ema_values[i]; break; }
    }
    if (!bar) { i = c.bars.length - 1; bar = c.bars[i]; ev = c.ema_values[i]; }
    if (state.eq && state.eq.data[i]) pv = state.eq.data[i].value;
    var t = typeof bar[0] === "string" ? bar[0] : new Date(bar[0] * 1000).toISOString().slice(0, 16).replace("T", " ");
    lg.textContent = TF_NAME[state.tf] + " " + t + "  O " + num(bar[1], 2) + "  H " + num(bar[2], 2) + "  L " +
      num(bar[3], 2) + "  C " + num(bar[4], 2) + "   EMA " + c.ema + ": " + num(ev, 2) +
      (ev != null ? (bar[4] > ev ? "  ▲ close above" : "  ▼ close below") : "") +
      (pv != null ? "   ·  points made so far: " + signed(pv, 0) : "");
  }

  function showWinner() {
    var tf = D.chosen.tf;
    state.tf = tf;
    var c = D.charts[tf];
    candles.setData(c.bars.map(function (b) { return { time: b[0], open: b[1], high: b[2], low: b[3], close: b[4] }; }));
    var ld = [];
    c.bars.forEach(function (b, i) { if (c.ema_values[i] != null) ld.push({ time: b[0], value: c.ema_values[i] }); });
    line.setData(ld);
    line.applyOptions({ title: "EMA " + c.ema });
    $("nf-title").textContent = "NIFTY 50 · " + TF_NAME[tf] + " candles · EMA " + c.ema + " (the winner)";
    applyMarkers();
    setWindow(state.win);
    legend(null);
  }

  var EXIT_TXT = { top: "TOP", cross: "EXIT", st: "EXIT", trail: "EXIT", target: "TARGET" };
  function applyMarkers() {
    var c = D.charts[state.tf], first = c.bars.length ? c.bars[0][0] : null, note = $("nf-chart-note");
    var useCombo = state.mode === "combo" && C && C.chart && state.tf === C.tf;
    var mk;
    if (useCombo) {
      mk = C.chart.markers.filter(function (m) { return first == null || m[0] >= first; }).map(function (m) {
        var buy = m[1] === "buy", sell = m[1] === "sell";
        if (buy) return { time: m[0], position: "belowBar", color: "#16a34a", shape: "arrowUp", size: 1.1, text: "BUY" };
        if (sell) return { time: m[0], position: "aboveBar", color: "#dc2626", shape: "arrowDown", size: 1.1, text: "SELL" };
        return { time: m[0], position: "aboveBar", color: m[1] === "top" ? "#f59e0b" : "#64748b", shape: "circle", size: 0.9,
                 text: (EXIT_TXT[m[1]] || "EXIT") + " " + signed(m[3], 0) };
      });
      note.textContent = "BUY = close above EMA 105 with " + C.winner.filters.join(" + ") +
        " all agreeing. TOP = " + C.exits[C.winner.exit].replace(/the level/, String(C.winner.p)) +
        " (sell the long, then wait for price to come back near EMA 105). EXIT = close back below EMA 105. Numbers = points after costs.";
    } else {
      mk = c.markers.filter(function (m) { return first == null || m[0] >= first; }).map(function (m) {
        var up = m[1] > 0;
        return { time: m[0], position: up ? "belowBar" : "aboveBar", color: up ? "#16a34a" : "#dc2626",
                 shape: up ? "arrowUp" : "arrowDown", size: 0.6 };
      });
      note.textContent = "EMA 105 only. ▲ = a candle closed above it (view turns up). ▼ = a candle closed below it (view turns down).";
    }
    candles.setMarkers(mk);
    var cost = (C && C.cost_pct != null ? C.cost_pct : D.cost_pct) / 100;
    state.eq = equity(c.bars, currentTrades(), cost);
    pnl.setData(state.eq.data);
    var e = state.eq, sum = $("nf-pts");
    sum.textContent = "";
    sum.className = "nf-pts " + (e.total >= 0 ? "up" : "dn");
    sum.appendChild(el("b", null, signed(e.total, 0) + " points"));
    sum.appendChild(document.createTextNode(" made by " + (useCombo ? "EMA 105 + confirmations (buy only)" : "EMA 105 (buy above, sell below)") +
      " over the last " + D.window + " sessions, after costs · " + e.n + " trades, " + e.wins + " winners · ≈ ₹" +
      num(Math.round(e.total * 75), 0) + " per Nifty lot of 75"));
    Array.prototype.forEach.call($("nf-mode").children, function (b) { b.classList.toggle("on", b.dataset.mode === state.mode); });
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


  function renderControls() {
    Array.prototype.forEach.call($("nf-win").children, function (b) {
      b.addEventListener("click", function () { setWindow(+b.dataset.win); });
    });
    Array.prototype.forEach.call($("nf-mode").children, function (b) {
      b.addEventListener("click", function () { state.mode = b.dataset.mode; applyMarkers(); });
    });
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
  /* ── combination research (nifty_combo.json) ─────────────────────────── */
  function sline(s) { return s && s.n ? s.n + " trades · " + pct(s.win) + " win · PF " + num(s.pf, 2) + " · " + signed(s.net, 0) + " pts" : "—"; }
  function statCells(tr, s) {
    cell(tr, s && s.n ? String(s.n) : "0", "num");
    cell(tr, pct(s && s.win), "num");
    cell(tr, s && s.pf != null ? num(s.pf, 2) : "—", "num");
    cell(tr, signed(s && s.net, 0), tone(s && s.net));
    cell(tr, s && s.dd != null ? num(s.dd, 0) : "—", "num");
  }
  var STAT_COLS = [["Trades", "num"], ["Win %", "num"], ["PF", "num", "winning points ÷ losing points"], ["Net pts", "num", "after costs"], ["Worst DD", "num", "worst drawdown in points"]];

  function renderCombo() {
    var w = C.winner, now = C.now, box = $("cb-now");
    box.textContent = "";
    box.className = "nf-combo-now " + (now.state.indexOf("BUY") >= 0 ? "long" : "wait");
    box.appendChild(el("small", null, "EMA 105 + CONFIRMATIONS · " + C.as_of));
    box.appendChild(el("b", null, now.state));
    box.appendChild(el("p", null, now.note));
    var ul = el("ul", "nf-checks");
    now.checks.forEach(function (ch) {
      var li = el("li", ch.ok ? "ok" : "no");
      li.appendChild(el("span", null, ch.ok ? "✓ " : "✗ "));
      li.appendChild(document.createTextNode(ch.name + " — " + ch.value));
      ul.appendChild(li);
    });
    box.appendChild(ul);
    box.appendChild(el("p", "fd-note", "RSI now " + num(now.rsi, 1) + " · price " + num(now.atr_from_ema, 1) + " ATR above EMA 105."));

    $("cb-period").textContent = "(" + C.period.from + " → " + C.period.to + ", 2-hour candles, long only, after costs)";
    var tb = head($("cb-cmp"), [["Rule"]].concat(STAT_COLS));
    [["EMA 105 alone (close above = buy, close below = exit)", C.base.long_only.all],
     ["EMA 105 + " + w.filters.join(" + ") + " + RSI-" + w.p + " top exit", w.all],
     ["… same, unseen part only (" + C.period.split + " →)", w.os]].forEach(function (row, i) {
      var tr = el("tr", i === 1 ? "nf-chosen" : null); cell(tr, row[0]); statCells(tr, row[1]); tb.appendChild(tr);
    });
    var b = C.base.long_only.all;
    $("cb-cmp-note").textContent = "Win rate " + pct(b.win) + " → " + pct(w.all.win) + ", profit factor " + num(b.pf, 2) + " → " +
      num(w.all.pf, 2) + ", net " + signed(b.net, 0) + " → " + signed(w.all.net, 0) + " points with " + w.all.n + " instead of " + b.n +
      " trades. Tested " + num(C.tested) + " combinations; " + num(C.robust_count) + " made money in both the tested and the unseen part.";

    $("cb-fin-note").textContent = "Ranked by the WEAKER of the two parts (tested " + C.period.from + " → " + C.period.split +
      ", unseen " + C.period.split + " → " + C.period.to + "). Final = 60% numbers + 40% Jev (" + (C.jev.model || "—") + ", " + C.jev.status + ").";
    tb = head($("cb-fin"), [["#"], ["Indicators"], ["Exit"], ["Tested part", null], ["Unseen part", null], ["Whole period", null], ["Jev"], ["Final", "num"]]);
    C.finalists.forEach(function (r, i) {
      var tr = el("tr", i === 0 ? "nf-chosen" : null), j = r.jev || {};
      cell(tr, String(i + 1)); cell(tr, "EMA 105 + " + r.filters.join(" + "));
      cell(tr, r.exit + (r.p != null ? " " + r.p : "")); cell(tr, sline(r.is)); cell(tr, sline(r.os)); cell(tr, sline(r.all));
      cell(tr, j.reliability ? j.reliability + " · overfit " + j.overfit : (j.error ? "error" : "—"));
      cell(tr, num(r.final, 1), "num"); tb.appendChild(tr);
    });

    var best = 0;
    (C.top_robust || []).forEach(function (r) { if (r.all.n >= 20 && r.all.win > best) best = r.all.win; });
    $("cb-trap-note").textContent = "Highest win rate of any robust combination with 20+ trades: " + pct(best) +
      ". Rules that showed 74-76% in the tested part fell to 44-50% on unseen data and LOST money. The ones below are the highest tested-part win rates - look at the unseen column.";
    tb = head($("cb-trap"), [["Rule"], ["Tested part"], ["Unseen part"]]);
    C.trap.slice(0, 6).forEach(function (r) {
      var tr = el("tr"); cell(tr, r.label); cell(tr, sline(r.is), "up"); cell(tr, sline(r.os), tone(r.os.net)); tb.appendChild(tr);
    });

    var tv = C.top_reversion;
    $("cb-top-note").textContent = tv.n + " TOP signals. Within the next 10 candles (≈ 2.5 sessions) Nifty fell at least 1 ATR after " +
      pct(tv.fell_1atr_pct) + " of them and went all the way back to EMA 105 after " + pct(tv.reached_ema_pct) +
      ". Median move back toward EMA 105: " + pct(tv.median_pct_back) + " of the gap.";
    tb = head($("cb-top"), [["TOP at"], ["Close", "num"], ["ATR above EMA", "num"], ["Fell (pts, 10 bars)", "num"], ["% of gap to EMA", "num"]]);
    tv.tops.slice().reverse().forEach(function (t) {
      var tr = el("tr"); cell(tr, t.date); cell(tr, num(t.close, 2), "num"); cell(tr, num(t.atr_above_ema, 1), "num");
      cell(tr, num(t.drop_10bars, 0), "num"); cell(tr, pct(t.pct_back_to_ema), t.pct_back_to_ema >= 100 ? "num up" : "num"); tb.appendChild(tr);
    });

    var bl = C.base.long_short.all;
    $("cb-short-note").textContent = "Selling every close below EMA 105 lost money in the tested part and made money only in the unseen part - not consistent. " +
      "Long + short together: " + sline(bl) + ". The page therefore shows BUY signals plus TOP/EXIT; a close below EMA 105 means stay out.";
    tb = head($("cb-short"), [["Sell rule"], ["Tested part"], ["Unseen part"], ["Whole period"]]);
    C.short_side.slice(0, 9).forEach(function (r) {
      var tr = el("tr"); cell(tr, r.label); cell(tr, sline(r.is), tone(r.is.net)); cell(tr, sline(r.os), tone(r.os.net)); cell(tr, sline(r.all), tone(r.all.net)); tb.appendChild(tr);
    });

    var levels = [], adxs = [];
    C.sensitivity.forEach(function (s) { if (levels.indexOf(s.rsi_top) < 0) levels.push(s.rsi_top); if (adxs.indexOf(s.adx) < 0) adxs.push(s.adx); });
    tb = head($("cb-sens"), [["ADX above"]].concat(levels.map(function (l) { return ["RSI top " + l, "num"]; })));
    adxs.forEach(function (a) {
      var tr = el("tr"); cell(tr, String(a));
      levels.forEach(function (l) {
        var s = C.sensitivity.filter(function (x) { return x.adx === a && x.rsi_top === l; })[0];
        var td = cell(tr, s ? pct(s.win) + " (" + num(s.pf, 2) + ")" : "—", "num");
        if (s && a === 20 && l === w.p) td.className = "num nf-hit";
      });
      tb.appendChild(tr);
    });

    var dc = C.daily_check;
    tb = head($("cb-daily"), [["Rule (" + dc.from + " → " + dc.to + ")"]].concat(STAT_COLS));
    [["Daily EMA 26 alone", dc.ema_only], ["+ ADX>20 + Supertrend + trend gate, RSI-70 top exit", dc.combo_rsi_top],
     ["+ ADX>20 + Supertrend + trend gate, exit on close below", dc.combo_cross_exit]].forEach(function (row) {
      var tr = el("tr"); cell(tr, row[0]); statCells(tr, row[1]); tb.appendChild(tr);
    });
    $("cb-daily-note").textContent = dc.note + " Years the 2-hour test never saw. The confirmations roughly double the win rate here too (" +
      pct(dc.ema_only.win) + " → " + pct(dc.combo_cross_exit.win) + ") and cut the drawdown, but the total points are lower because fewer trades are taken.";

    tb = head($("cb-trades"), [["Buy at"], ["Price", "num"], ["Exit at"], ["Price", "num"], ["Why"], ["Points", "num"]]);
    C.trades.slice().reverse().forEach(function (t) {
      var tr = el("tr"); cell(tr, t[0]); cell(tr, num(t[2], 2), "num"); cell(tr, t[6] === "open" ? "open" : t[3]);
      cell(tr, num(t[4], 2), "num"); cell(tr, t[6] === "open" ? "still holding" : t[6]); cell(tr, signed(t[5], 0), tone(t[5])); tb.appendChild(tr);
    });
  }

  /* ── Day vs night (nifty_daynight.json) - its own chart, never touches the main one ─────────── */
  var N2 = null, dnChart = null, dnSeries = [];
  function dnPlot(view) {
    dnSeries.forEach(function (s) { dnChart.removeSeries(s); }); dnSeries = [];
    var rows = N2.series, cn = 0, cd = 0;
    if (view === "bars") {
      var hn = dnChart.addHistogramSeries({ priceScaleId: "right", title: "night", priceFormat: { type: "price", precision: 0, minMove: 1 } });
      var hd = dnChart.addHistogramSeries({ priceScaleId: "left", title: "day", priceFormat: { type: "price", precision: 0, minMove: 1 } });
      hn.setData(rows.map(function (r) { return { time: r[0], value: r[3], color: r[3] >= 0 ? "#6366f1" : "#c7d2fe" }; }));
      hd.setData(rows.map(function (r) { return { time: r[0], value: r[4], color: r[4] >= 0 ? "#f59e0b" : "#fde68a" }; }));
      dnChart.applyOptions({ leftPriceScale: { visible: true } });
      dnSeries = [hn, hd];
      $("dn-note").textContent = "Right scale, blue: each night's gap (open − previous close). Left scale, orange: each day's move (close − open). Pale = negative.";
    } else {
      var sn = dnChart.addLineSeries({ color: "#6366f1", lineWidth: 2, title: "night (close → next open)", priceFormat: { type: "price", precision: 0, minMove: 1 } });
      var sd = dnChart.addLineSeries({ color: "#f59e0b", lineWidth: 2, title: "day (open → close)", priceFormat: { type: "price", precision: 0, minMove: 1 } });
      var sc = dnChart.addLineSeries({ color: "#0f172a", lineWidth: 1, lineStyle: 2, title: "Nifty (close − start)", priceFormat: { type: "price", precision: 0, minMove: 1 } });
      var a = [], b = [], c = [], base = rows[0][2] - rows[0][3] - rows[0][4];
      rows.forEach(function (r) {
        cn += r[3]; cd += r[4];
        a.push({ time: r[0], value: Math.round(cn) }); b.push({ time: r[0], value: Math.round(cd) }); c.push({ time: r[0], value: Math.round(r[2] - base) });
      });
      sn.setData(a); sd.setData(b); sc.setData(c);
      dnChart.applyOptions({ leftPriceScale: { visible: false } });
      dnSeries = [sn, sd, sc];
      $("dn-note").textContent = "Points Nifty made only overnight (blue) and only during market hours (orange), added up session by session. " +
        "Blue + orange = the dashed Nifty line exactly. No costs here: this is the market itself, not a trade.";
    }
    dnChart.timeScale().fitContent();
    Array.prototype.forEach.call($("dn-view").children, function (x) { x.classList.toggle("on", x.dataset.v === view); });
  }

  function renderDayNight() {
    var t = N2.totals;
    $("dn-n").textContent = N2.sessions;
    dnChart = LightweightCharts.createChart($("chart-dn"), {
      autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
      grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } },
      rightPriceScale: { borderColor: "#e2e8f0" }, leftPriceScale: { borderColor: "#e2e8f0" },
      timeScale: { borderColor: "#e2e8f0" }
    });
    dnChart.subscribeCrosshairMove(function (p) {
      var r = null;
      if (p && p.time) { for (var i = 0; i < N2.series.length; i++) if (N2.series[i][0] === (typeof p.time === "string" ? p.time : "")) { r = N2.series[i]; break; } }
      if (!r && p && p.time && typeof p.time === "object") {
        var s = p.time.year + "-" + String(p.time.month).padStart(2, "0") + "-" + String(p.time.day).padStart(2, "0");
        N2.series.forEach(function (x) { if (x[0] === s) r = x; });
      }
      if (!r) r = N2.series[N2.series.length - 1];
      $("dn-legend").textContent = r[0] + "   open " + num(r[1], 2) + "   close " + num(r[2], 2) + "   night " + signed(r[3], 1) + "   day " + signed(r[4], 1);
    });
    Array.prototype.forEach.call($("dn-view").children, function (b) { b.addEventListener("click", function () { dnPlot(b.dataset.v); }); });
    dnPlot("split");
    $("dn-legend").textContent = N2.from + " → " + N2.to;

    var k = $("dn-kpis"); k.textContent = "";
    function kpi(label, val, sub, cls) {
      var b = el("div", "nf-kpi" + (cls ? " " + cls : "")); b.appendChild(el("small", null, label));
      b.appendChild(el("strong", null, val)); if (sub) b.appendChild(el("span", null, sub)); k.appendChild(b);
    }
    kpi("Night points", signed(t.night, 0), t.night_up_days + " of " + N2.sessions + " nights up · avg size " + num(t.night_abs_avg, 0), t.night >= 0 ? "up" : "dn");
    kpi("Day points", signed(t.day, 0), t.day_up_days + " of " + N2.sessions + " days up · avg size " + num(t.day_abs_avg, 0), t.day >= 0 ? "up" : "dn");
    kpi("Nifty (close to close)", signed(t.cc, 0), N2.from + " → " + N2.to, t.cc >= 0 ? "up" : "dn");
    var y10 = N2.years.filter(function (y) { return y.sessions > 100; });
    var nUp = y10.filter(function (y) { return y.night > y.day; }).length;
    kpi("Ten years", nUp + " of " + y10.length, "years where the night beat the day");

    var tb = head($("dn-ema"), [["Rule (unchanged)"], ["Trades", "num"], ["Night pts", "num"], ["Day pts", "num"], ["Last 200 sessions: night", "num"], ["day", "num"]]);
    N2.ema_split.forEach(function (r) {
      var tr = el("tr"); cell(tr, r.rule); cell(tr, String(r.all.trades), "num");
      cell(tr, signed(r.all.night, 0), tone(r.all.night)); cell(tr, signed(r.all.day, 0), tone(r.all.day));
      cell(tr, signed(r.last200.night, 0), tone(r.last200.night)); cell(tr, signed(r.last200.day, 0), tone(r.last200.day)); tb.appendChild(tr);
    });

    $("dn-sub").textContent = "(" + N2.from + " → " + N2.to + ", after " + num(N2.cost_pct, 3) + "% cost per trade)";
    $("dn-rules-note").textContent = "\"Holds up\" = made money in BOTH the first 100 and the last 100 sessions (split " + N2.half_split +
      "). " + N2.holds.length + " of " + N2.rules.length + " rules hold up. Sorted by points after costs.";
    tb = head($("dn-rules"), [["Idea"], ["Rule"], ["Side"], ["Trades", "num"], ["Win %", "num"], ["PF", "num"], ["Net pts", "num"],
      ["Worst DD", "num"], ["1st 100", "num"], ["Last 100", "num"], ["Holds up"]]);
    N2.rules.slice().sort(function (a, b) { return b.net - a.net; }).forEach(function (r) {
      var tr = el("tr", r.holds ? "nf-chosen" : null);
      cell(tr, r.idea); cell(tr, r.rule); cell(tr, r.side, r.side === "BUY" ? "up" : r.side === "SELL" ? "dn" : null);
      cell(tr, String(r.n), "num"); cell(tr, pct(r.win), "num"); cell(tr, num(r.pf, 2), "num");
      cell(tr, signed(r.net, 0), tone(r.net)); cell(tr, num(r.dd, 0), "num");
      cell(tr, signed(r.h1, 0), tone(r.h1)); cell(tr, signed(r.h2, 0), tone(r.h2)); cell(tr, r.holds ? "✓" : "—", r.holds ? "up" : null);
      tb.appendChild(tr);
    });

    var o = N2.orb;
    tb = head($("dn-orb"), [["Version"], ["Trades", "num"], ["Win %", "num"], ["PF", "num"], ["Net pts", "num"], ["Worst DD", "num"]]);
    [["Hourly candles, first hour, all " + N2.sessions + " sessions", o.first_hour_1h_200],
     ["… first 100 sessions", o.first_hour_1h_h1], ["… last 100 sessions", o.first_hour_1h_h2],
     ["Hourly candles, only the " + o.sessions_5m + " sessions that have 5-minute data", o.first_hour_1h_same_days_as_5m],
     ["5-minute candles, first hour (second check)", o.first_hour_5m],
     ["5-minute candles, first 15 minutes", o.first_15m_5m], ["5-minute candles, first 30 minutes", o.first_30m_5m]].forEach(function (row) {
      var s = row[1] || {}, tr = el("tr"); cell(tr, row[0]); cell(tr, String(s.n || 0), "num"); cell(tr, pct(s.win), "num");
      cell(tr, num(s.pf, 2), "num"); cell(tr, signed(s.net, 0), tone(s.net)); cell(tr, num(s.dd, 0), "num"); tb.appendChild(tr);
    });

    tb = head($("dn-years"), [["Year"], ["Sessions", "num"], ["Night pts", "num"], ["Day pts", "num"], ["Night %", "num"], ["Day %", "num"], ["Nights up", "num"], ["Days up", "num"]]);
    N2.years.forEach(function (y) {
      var tr = el("tr"); cell(tr, String(y.year)); cell(tr, String(y.sessions), "num");
      cell(tr, signed(y.night, 0), tone(y.night)); cell(tr, signed(y.day, 0), tone(y.day));
      cell(tr, signed(y.night_pct, 1) + "%", tone(y.night_pct)); cell(tr, signed(y.day_pct, 1) + "%", tone(y.day_pct));
      cell(tr, pct(y.night_up_pct), "num"); cell(tr, pct(y.day_up_pct), "num"); tb.appendChild(tr);
    });
    var ch = N2.checks;
    $("dn-checks").textContent = "Checks: night + day = close-to-close on every session (max error " + ch.identity_max_error +
      " points). Daily open vs first hourly candle open: median gap " + num(ch.open_vs_first_hour_median, 2) + " points (95% within " +
      num(ch.open_vs_first_hour_p95, 1) + "). Idea from " + N2.source;
  }

  function boot() {
    var get = function (f) {
      return fetch(f + "?v=" + Date.now(), { cache: "no-store" })
        .then(function (r) { if (!r.ok) throw new Error(f + " HTTP " + r.status); return r.json(); });
    };
    var opt = function (f) { return get(f).catch(function () { return null; }); };
    Promise.all([get("nifty.json"), opt("nifty_combo.json"), opt("nifty_daynight.json")])
      .then(function (res) {
        D = res[0]; C = res[1]; N2 = res[2];
        if (!C) { state.mode = "ema"; $("nf-combo").textContent = "Combination research not available yet."; }
        renderHead(); renderFinalists(); renderAsked(); renderSignals(); renderMethod(); renderControls();
        if (C) renderCombo();
        if (typeof LightweightCharts === "undefined") { $("chart-main").textContent = "Chart library failed to load."; return; }
        buildChart();
        showWinner();
        if (N2) { try { renderDayNight(); } catch (e) { $("dn-note").textContent = "Day vs night failed: " + e.message; } }
        else $("nf-dn").textContent = "Day vs night research not available yet.";
      })
      .catch(function (e) { $("nf-asof").textContent = "Failed to load: " + e.message; });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
