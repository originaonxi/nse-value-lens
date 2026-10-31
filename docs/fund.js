/* Value Lens Nifty 100 Fund. Renders docs/fund.json; stock charts from daily_setups_series.json.
   All text goes through textContent (no HTML injection). Paper research, not advice. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var el = function (tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
  var inr = function (n) { return n == null ? "—" : "₹" + Math.round(n).toLocaleString("en-IN"); };
  var cr = function (n) { return n >= 1e7 ? "₹" + (n / 1e7).toFixed(2) + " cr" : "₹" + (n / 1e5).toFixed(2) + " L"; };
  var pc = function (v, dp) { return v == null ? "—" : (v > 0 ? "+" : "") + v.toFixed(dp == null ? 1 : dp) + "%"; };
  var tone = function (v) { return v == null ? "" : v >= 0 ? "up" : "down"; };
  var BULL = { breakout: 1, breakout_today: 1, ready_to_break: 1, uptrend: 1, turning_up: 1 };
  var BEAR = { downtrend: 1, structure_exit: 1, breakdown: 1, breakdown_today: 1, turning_down: 1 };
  var nice = function (c) { return c ? c.replace(/_/g, " ") : "—"; };
  // The fund only buys. A daily-setups plan on the short side has a target below the price, so it is not shown.
  var longTarget = function (h) { return h.plan_side === "long" ? h.next_target : null; };
  var D, SERIES = null, selected = null, allFilter = "all";

  fetch("./fund.json?v=" + Date.now()).then(function (r) { return r.json(); }).then(function (d) { D = d; render(); })
    .catch(function (e) { $("fd-banner").textContent = "Could not load fund data: " + e; });

  function td(tr, txt, cls) { var c = el("td", cls, txt); tr.appendChild(c); return c; }
  function badge(text, t) { var s = el("span", "fd-cat", text); s.setAttribute("data-tone", t); return s; }
  function catBadge(c) { return badge(nice(c), BULL[c] ? "bull" : BEAR[c] ? "bear" : "neutral"); }
  function jevBadge(dir) { return badge(dir || "—", dir === "up" ? "bull" : dir === "down" ? "bear" : "neutral"); }
  function jevScoreCell(tr, v) {
    var c = td(tr, v == null ? "—" : v.toFixed(0), "num fd-jev");
    if (v != null) c.setAttribute("data-tone", v >= 60 ? "bull" : v < 40 ? "bear" : "neutral");
    return c;
  }

  function render() {
    var p = D.portfolio, st = D.stats, J = D.jev;
    $("fd-nav-val").textContent = D.nav.toFixed(2);
    $("fd-asof").textContent = "After the " + D.as_of + " close · started " + D.inception;

    var b = $("fd-banner");
    b.textContent = "";
    b.className = "fd-banner " + (p.guard_on ? "guard" : "open");
    b.appendChild(el("b", null, (p.guard_on ? "Market guard ON: " : "") + p.holdings_count + " stocks " + p.stock_pct + "%" +
      (p.cash_pct ? " + liquid fund " + p.cash_pct + "%" : "") + " = 100%"));
    var only = p.holdings_count < D.rules.holdings
      ? " Only " + p.holdings_count + " of the 100 stocks are above their 200-day average today, so the fund holds " + p.holdings_count + ", not " + D.rules.holdings + "."
      : "";
    b.appendChild(document.createTextNode(p.guard_words + only + " " + p.status + " Next rebalance: " + p.next_decision + "."));

    $("k-cagr").textContent = pc(st.cagr.fund);
    $("k-cagr-sub").textContent = "Nifty 50 " + pc(st.cagr.nifty50) + " · EW Nifty 100 " + pc(st.cagr.ew100) + " · " + st.years + " years";
    $("k-growth").textContent = inr(st.growth_of_1L.fund);
    $("k-growth-sub").textContent = "Nifty 50: " + inr(st.growth_of_1L.nifty50) + " · since " + D.inception;
    $("k-dd").textContent = pc(st.max_drawdown.fund);
    $("k-dd").className = "down";
    $("k-dd-sub").textContent = "Nifty 50 " + pc(st.max_drawdown.nifty50) + " · EW Nifty 100 " + pc(st.max_drawdown.ew100);
    $("k-jev").textContent = J.avg_score == null ? "—" : J.avg_score.toFixed(0) + " / 100";
    $("k-jev-sub").textContent = "Average Jev score · Jev says up on " + J.views.up + ", down on " + J.views.down + " of " + J.held + " holdings";

    $("p-sub").textContent = "rebalanced " + p.decided_on + " · " + p.holdings_count + " stocks" + (p.cash_pct ? " + " + p.cash_pct + "% cash" : "") + " = " + p.total_pct + "%";
    $("p-note").textContent = "Weight = share of every rupee you invest now. The same weights apply to a lump sum or a SIP instalment. Stocks are chosen by momentum; Jev columns are a second opinion.";

    renderHoldings();
    $("sip-amt").addEventListener("input", function () { renderHoldings(); renderGoal(); });
    Array.prototype.forEach.call(document.querySelectorAll(".chips button"), function (btn) {
      btn.addEventListener("click", function () { $("sip-amt").value = btn.getAttribute("data-amt"); renderHoldings(); renderGoal(); });
    });

    var sold = D.changes.sold.concat(D.changes.selling).map(function (e) { return e.symbol + " (below 200-day)"; });
    pills($("c-added"), D.changes.added, "in", "No new stocks this month.");
    pills($("c-removed"), D.changes.removed.concat(sold), "out", "Nothing sold this month.");

    renderAll(); renderReturns(); renderNav(); renderYears(); renderHeat(); renderRealWorld(); renderVariants();
    renderSectors(); renderSipSim(); renderGoal(); renderHistory();
    D.rules.text.forEach(function (t) { $("rules").appendChild(el("li", null, t)); });
    $("jev-words").textContent = J.words;
    D.limits.forEach(function (t) { $("limits").appendChild(el("li", null, t)); });
  }

  function amount() { var v = parseFloat($("sip-amt").value); return isFinite(v) && v > 0 ? v : 0; }

  function renderHoldings() {
    var amt = amount(), body = $("h-rows"), foot = $("h-foot"), used = 0;
    body.textContent = ""; foot.textContent = "";
    D.holdings.forEach(function (h) {
      var tr = el("tr", h.status !== "held" ? "fd-sold" : null);
      tr.setAttribute("aria-selected", selected === h.symbol ? "true" : "false");
      var rupees = amt * h.weight_pct / 100, shares = h.close ? Math.floor(rupees / h.close) : 0;
      used += shares * h.close;
      td(tr, String(h.rank));
      var s = td(tr, null, "fd-sym"); s.appendChild(el("strong", null, h.symbol));
      s.appendChild(el("small", null, h.status === "held" ? h.sector : h.status === "sold" ? "Sold: closed below 200-day average" : "Selling next session: below 200-day average"));
      var w = td(tr, null, "num"); var wb = el("div", "fd-wbar"); var bar = el("i"); var fill = el("b");
      fill.style.width = Math.min(100, h.weight_pct / 6 * 100) + "%"; bar.appendChild(fill); wb.appendChild(bar);
      wb.appendChild(el("strong", null, h.weight_pct.toFixed(2) + "%")); w.appendChild(wb);
      td(tr, inr(rupees), "num");
      td(tr, String(shares), "num");
      td(tr, h.close.toLocaleString("en-IN"), "num");
      td(tr, (h.div_yield && h.div_yield > 0) ? h.div_yield.toFixed(1) + "%" : "—", "num");
      ["6M", "1Y", "3Y", "5Y"].forEach(function (k) { var v = h.returns[k]; td(tr, pc(v, 0), "num " + tone(v)); });
      jevScoreCell(tr, h.jev_score);
      td(tr, h.jev_rank ? "#" + h.jev_rank + "/" + (h.jev_of || 200) : "—", "num");
      td(tr).appendChild(jevBadge(h.jev_direction));
      td(tr).appendChild(catBadge(h.category));
      td(tr, h.dma200 != null ? h.dma200.toLocaleString("en-IN") : "—", "num");
      var t = longTarget(h); td(tr, t != null ? t.toLocaleString("en-IN") : "—", "num");
      tr.addEventListener("click", function () { showDetail(h); });
      body.appendChild(tr);
    });
    if (D.portfolio.cash_pct) {
      var tr = el("tr", "cash");
      td(tr, "—");
      var s = td(tr, null, "fd-sym"); s.appendChild(el("strong", null, "Liquid fund (cash)")); s.appendChild(el("small", null, "Market guard and sold stocks · any liquid / overnight fund at Kotak"));
      td(tr, D.portfolio.cash_pct.toFixed(2) + "%", "num");
      td(tr, inr(amt * D.portfolio.cash_pct / 100), "num");
      for (var i = 0; i < 12; i++) td(tr, "", "num");
      body.appendChild(tr);
      used += amt * D.portfolio.cash_pct / 100;
    }
    var ft = el("tr");
    td(ft, ""); td(ft, "Total · " + D.portfolio.holdings_count + " stocks" + (D.portfolio.cash_pct ? " + cash" : ""));
    td(ft, D.portfolio.total_pct.toFixed(2) + "%", "num"); td(ft, inr(amt), "num");
    var left = td(ft, "Left over after whole shares: " + inr(amt - used)); left.colSpan = 12;
    foot.appendChild(ft);
  }

  function pills(box, list, cls, empty) {
    box.textContent = "";
    if (!list.length) { box.appendChild(el("span", "fd-note", empty)); return; }
    list.forEach(function (s) { box.appendChild(el("span", "fd-pill " + cls, s)); });
  }

  function renderAll() {
    var counts = { all: D.all100.length, fund: 0, wait: 0, out: 0 };
    D.all100.forEach(function (r) { if (r.in_fund) counts.fund++; else if (r.momentum_rank) counts.wait++; else counts.out++; });
    $("a-note").textContent = counts.fund + " in the fund, " + counts.wait + " qualify but rank lower, " + counts.out +
      " not eligible (below their 200-day average or under a year of prices). Jev rank here is among these 100 stocks.";
    var f = $("a-filters");
    [["all", "All 100"], ["fund", "In the fund"], ["out", "Not eligible"], ["jev", "Sorted by Jev"]].forEach(function (x) {
      var btn = el("button", x[0] === allFilter ? "on" : null, x[1] + (counts[x[0]] != null ? " (" + counts[x[0]] + ")" : ""));
      btn.onclick = function () { allFilter = x[0]; Array.prototype.forEach.call(f.children, function (b) { b.className = ""; }); btn.className = "on"; drawAll(); };
      f.appendChild(btn);
    });
    drawAll();
  }

  function drawAll() {
    var body = $("a-rows"); body.textContent = "";
    var rows = D.all100.filter(function (r) {
      return allFilter === "fund" ? r.in_fund : allFilter === "out" ? !r.momentum_rank && !r.in_fund : true;
    });
    if (allFilter === "jev") rows = rows.slice().sort(function (a, b) { return (b.jev_score == null ? -1 : b.jev_score) - (a.jev_score == null ? -1 : a.jev_score); });
    rows.forEach(function (r, i) {
      var tr = el("tr", r.in_fund ? "fd-in" : null);
      td(tr, String(allFilter === "jev" ? i + 1 : r.position));
      var s = td(tr, null, "fd-sym"); s.appendChild(el("strong", null, r.symbol)); s.appendChild(el("small", null, r.sector));
      td(tr).appendChild(badge(r.status, r.in_fund ? "bull" : r.momentum_rank ? "neutral" : "bear"));
      td(tr, r.weight_pct ? r.weight_pct.toFixed(2) + "%" : "—", "num");
      td(tr, r.momentum_rank ? "#" + r.momentum_rank : "—", "num");
      jevScoreCell(tr, r.jev_score);
      td(tr, r.jev_rank100 ? "#" + r.jev_rank100 : "—", "num");
      td(tr).appendChild(jevBadge(r.jev_direction));
      td(tr, pc(r.returns["6M"], 0), "num " + tone(r.returns["6M"]));
      td(tr, pc(r.returns["1Y"], 0), "num " + tone(r.returns["1Y"]));
      td(tr).appendChild(badge(r.above_200dma ? "above" : "below", r.above_200dma ? "bull" : "bear"));
      td(tr).appendChild(badge(r.supertrend_up ? "up" : "down", r.supertrend_up ? "bull" : "bear"));
      td(tr).appendChild(catBadge(r.category));
      body.appendChild(tr);
    });
  }

  function showDetail(h) {
    selected = h.symbol;
    renderHoldings();
    var box = $("fd-detail"); box.hidden = false;
    $("d-title").textContent = "#" + h.rank + " " + h.symbol + " · " + h.name;
    $("d-sub").textContent = h.sector + " · momentum rank " + (h.momentum_rank || "—") + " · Jev " + (h.jev_score == null ? "—" : h.jev_score.toFixed(0) + "/100, rank " + h.jev_rank + "/" + h.jev_of + ", view " + (h.jev_direction || "—") + (h.jev_confidence != null ? ", confidence " + h.jev_confidence.toFixed(0) + "%" : "")) + " · Supertrend " + (h.supertrend_up ? "up" : "down");
    $("d-weight").textContent = h.weight_pct.toFixed(2) + "% of the fund";
    var lv = $("d-levels"); lv.textContent = "";
    [["Close", h.close], ["Sell below (200-day avg)", h.dma200], ["Structure exit", h.structure_exit], ["Next target", longTarget(h), h.plan_side === "long" ? null : "No buy plan today"], ["Return 1Y", null, pc(h.returns["1Y"])], ["Return 3Y", null, pc(h.returns["3Y"])]]
      .forEach(function (x) { var d = el("div"); d.appendChild(document.createTextNode(x[0])); d.appendChild(el("b", null, x[1] != null ? "₹" + x[1].toLocaleString("en-IN") : (x[2] || "—"))); lv.appendChild(d); });
    $("d-summary").textContent = h.summary || "No daily-setups summary for this stock today.";
    $("d-link").href = "setups.html#" + encodeURIComponent(h.symbol);
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
    var draw = function () { drawCandles($("d-chart"), SERIES && SERIES[h.symbol], h); };
    if (SERIES) draw();
    else fetch("./daily_setups_series.json?v=" + Date.now()).then(function (r) { return r.json(); })
      .then(function (s) { SERIES = s.series || {}; draw(); }).catch(function () { SERIES = {}; draw(); });
  }

  function drawCandles(cv, ser, h) {
    var dpr = window.devicePixelRatio || 1, w = cv.clientWidth || 800, ht = cv.clientHeight || 300;
    cv.width = w * dpr; cv.height = ht * dpr;
    var ctx = cv.getContext("2d"); ctx.scale(dpr, dpr); ctx.clearRect(0, 0, w, ht);
    if (!ser || !ser.c || !ser.c.length) {
      ctx.fillStyle = "#65716a"; ctx.font = "13px sans-serif"; ctx.fillText("No chart series for this stock today.", 14, ht / 2); return;
    }
    var n = ser.c.length, padL = 8, padR = 62, padT = 10, padB = 22, gw = w - padL - padR, gh = ht - padT - padB, i;
    var lines = [[h.dma200, "#b8860b", "Sell below "], [longTarget(h), "#15803d", "Target "]];
    var vals = [];
    for (i = 0; i < n; i++) { if (ser.h[i] != null) vals.push(ser.h[i]); if (ser.l[i] != null) vals.push(ser.l[i]); if (ser.supertrend && ser.supertrend[i] != null) vals.push(ser.supertrend[i]); }
    lines.forEach(function (L) { if (L[0] != null) vals.push(L[0]); });
    var min = Math.min.apply(null, vals), max = Math.max.apply(null, vals), rng = (max - min) || 1;
    min -= rng * 0.03; max += rng * 0.03; rng = max - min;
    var y = function (v) { return padT + (1 - (v - min) / rng) * gh; }, cw = gw / n, bw = Math.max(1, cw * 0.62);
    ctx.font = "10px sans-serif"; ctx.fillStyle = "#65716a"; ctx.strokeStyle = "#eef1ec"; ctx.lineWidth = 1;
    for (var g = 0; g <= 4; g++) {
      var gv = min + rng * g / 4, gy = y(gv);
      ctx.beginPath(); ctx.moveTo(padL, gy); ctx.lineTo(padL + gw, gy); ctx.stroke();
      ctx.fillText(gv.toFixed(gv > 1000 ? 0 : 1), padL + gw + 6, gy + 3);
    }
    [0, Math.floor(n / 2), n - 1].forEach(function (k) { if (ser.dates && ser.dates[k]) ctx.fillText(ser.dates[k], Math.min(padL + k * cw, padL + gw - 56), ht - 6); });
    for (i = 0; i < n; i++) {
      if (ser.c[i] == null) continue;
      var x = padL + i * cw + cw / 2, upc = ser.c[i] >= ser.o[i];
      ctx.strokeStyle = ctx.fillStyle = upc ? "#1f7a52" : "#b4473c";
      ctx.beginPath(); ctx.moveTo(x, y(ser.h[i])); ctx.lineTo(x, y(ser.l[i])); ctx.stroke();
      var yo = y(ser.o[i]), yc = y(ser.c[i]);
      ctx.fillRect(x - bw / 2, Math.min(yo, yc), bw, Math.max(1, Math.abs(yc - yo)));
    }
    if (ser.supertrend) {
      ctx.lineWidth = 1.6; var prev = null;
      for (i = 0; i < n; i++) {
        var sv = ser.supertrend[i]; if (sv == null) { prev = null; continue; }
        var sx = padL + i * cw + cw / 2, dir = ser.supertrend_dir ? ser.supertrend_dir[i] : 1;
        if (prev && prev.dir === dir) {
          ctx.strokeStyle = dir === 1 ? "rgba(124,58,237,.9)" : "rgba(180,71,60,.75)";
          ctx.beginPath(); ctx.moveTo(prev.x, prev.y); ctx.lineTo(sx, y(sv)); ctx.stroke();
        }
        prev = { x: sx, y: y(sv), dir: dir };
      }
    }
    (ser.swings || []).forEach(function (s) {
      var k = ser.dates.indexOf(s.d); if (k < 0 || !s.t) return;
      var sx = padL + k * cw + cw / 2, sy = y(s.p) + (s.k === "high" ? -6 : 13);
      ctx.fillStyle = (s.t === "HH" || s.t === "HL") ? "#1f7a52" : "#b4473c"; ctx.font = "bold 10px sans-serif";
      ctx.fillText(s.t, sx - 7, sy);
    });
    lines.forEach(function (L) {
      if (L[0] == null) return;
      var ly = y(L[0]); ctx.strokeStyle = L[1]; ctx.setLineDash([5, 4]); ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(padL, ly); ctx.lineTo(padL + gw, ly); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = L[1]; ctx.font = "bold 10px sans-serif"; ctx.fillText(L[2] + L[0], padL + 4, ly - 4);
    });
  }

  function renderReturns() {
    var body = $("r-rows");
    D.returns.forEach(function (r) {
      var tr = el("tr");
      td(tr, r.period + (r.annualised ? " (a year)" : ""));
      td(tr, pc(r.fund), "num " + tone(r.fund)).style.fontWeight = "800";
      td(tr, pc(r.nifty50), "num " + tone(r.nifty50));
      td(tr, pc(r.ew100), "num " + tone(r.ew100));
      var diff = r.fund != null && r.nifty50 != null ? r.fund - r.nifty50 : null;
      td(tr, pc(diff), "num " + tone(diff));
      body.appendChild(tr);
    });
  }

  function svg(tag, attrs) { var e = document.createElementNS("http://www.w3.org/2000/svg", tag); for (var k in attrs) e.setAttribute(k, attrs[k]); return e; }

  function renderNav() {
    var s = D.nav_series, W = 640, H = 260, pl = 6, pr = 44, pt = 10, pb = 22, n = s.dates.length;
    var all = s.fund.concat(s.nifty50, s.ew100), min = Math.min.apply(null, all) * 0.97, max = Math.max.apply(null, all) * 1.02;
    var X = function (i) { return pl + i / (n - 1) * (W - pl - pr); }, Y = function (v) { return pt + (1 - (v - min) / (max - min)) * (H - pt - pb); };
    var root = svg("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Fund NAV against Nifty 50 and equal-weight Nifty 100, all starting at 100" });
    [100, 150, 200, 250, 300].forEach(function (v) {
      if (v < min || v > max) return;
      root.appendChild(svg("line", { x1: pl, x2: W - pr, y1: Y(v), y2: Y(v), stroke: "#eef1ec" }));
      var t = svg("text", { x: W - pr + 4, y: Y(v) + 3, "font-size": 10, fill: "#65716a" }); t.textContent = v; root.appendChild(t);
    });
    [["ew100", "#b8860b", 1.4], ["nifty50", "#64748b", 1.4], ["fund", "#246c4e", 2.4]].forEach(function (L) {
      var d = s[L[0]].map(function (v, i) { return (i ? "L" : "M") + X(i).toFixed(1) + "," + Y(v).toFixed(1); }).join("");
      root.appendChild(svg("path", { d: d, fill: "none", stroke: L[1], "stroke-width": L[2] }));
    });
    var years = {};
    s.dates.forEach(function (d, i) { var yv = d.slice(0, 4); if (!years[yv]) { years[yv] = 1; var t = svg("text", { x: X(i), y: H - 6, "font-size": 10, fill: "#65716a" }); t.textContent = yv; root.appendChild(t); } });
    $("fd-nav").appendChild(root);
    $("nav-note").textContent = "All three start at 100 on " + D.inception + ". Today: fund " + s.fund[n - 1].toFixed(0) + ", Nifty 50 " + s.nifty50[n - 1].toFixed(0) + ", equal-weight Nifty 100 " + s.ew100[n - 1].toFixed(0) + ".";
  }

  function renderYears() {
    var body = $("y-rows");
    D.calendar_years.forEach(function (y) {
      var tr = el("tr");
      td(tr, y.year + (y.partial ? (y.year === +D.inception.slice(0, 4) ? " (from " + D.inception.slice(5) + ")" : " (to date)") : ""));
      td(tr, pc(y.fund), "num " + tone(y.fund)).style.fontWeight = "800";
      td(tr, pc(y.nifty50), "num " + tone(y.nifty50));
      td(tr, pc(y.ew100), "num " + tone(y.ew100));
      var diff = y.fund != null && y.nifty50 != null ? y.fund - y.nifty50 : null; td(tr, pc(diff), "num " + tone(diff));
      body.appendChild(tr);
    });
  }

  function heatColor(v) {
    if (v == null) return "transparent";
    var a = Math.min(1, Math.abs(v) / 8);
    return v >= 0 ? "rgba(31,122,82," + (0.12 + 0.6 * a) + ")" : "rgba(180,71,60," + (0.12 + 0.6 * a) + ")";
  }

  function renderHeat() {
    var box = $("m-heat"), months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], by = {};
    D.monthly_returns.forEach(function (m) { var y = m.month.slice(0, 4); (by[y] = by[y] || {})[+m.month.slice(5) - 1] = m.fund; });
    box.appendChild(el("div", "h", ""));
    months.forEach(function (m) { box.appendChild(el("div", "h", m)); });
    box.appendChild(el("div", "h", "Year"));
    var yearRet = {}; D.calendar_years.forEach(function (y) { yearRet[y.year] = y.fund; });
    Object.keys(by).sort().forEach(function (y) {
      box.appendChild(el("div", "h", y));
      for (var i = 0; i < 12; i++) {
        var v = by[y][i], c = el("div", null, v == null ? "" : pc(v, 1));
        c.style.background = heatColor(v); box.appendChild(c);
      }
      var t = el("div", null, pc(yearRet[y], 1)); t.style.fontWeight = "800"; t.style.background = heatColor(yearRet[y] / 3); box.appendChild(t);
    });
  }

  function renderRealWorld() {
    var body = $("rw-rows"), st = D.stats;
    $("rw-note").textContent = "40–50% a year for 5 years would turn ₹1 lakh into ₹5–7.6 lakh. No momentum index, smallcase or fund below has done that over a full cycle. " +
      "The best long-run results are 18–25% a year, and they came with years of −17% to −61%. This fund's own " + st.years + "-year backtest is " + pc(st.cagr.fund) +
      " a year, but those years had no crash. Plan your retirement on 12–15%; treat anything above that as a bonus.";
    D.real_world.forEach(function (r) {
      var tr = el("tr");
      var c = td(tr); var a = el("a", null, r.name); a.href = r.url; a.target = "_blank"; a.rel = "noopener"; c.appendChild(a);
      td(tr, r.period); td(tr, pc(r.cagr), "num up").style.fontWeight = "800"; td(tr, r.note);
      body.appendChild(tr);
    });
    var tr = el("tr", "fd-live");
    td(tr, "This fund (backtest, live rules)"); td(tr, D.inception + " – " + D.as_of); td(tr, pc(st.cagr.fund), "num up");
    td(tr, "Worst fall " + pc(st.max_drawdown.fund) + " · no 2008-style crash in this window · survivorship bias");
    body.appendChild(tr);
  }

  function renderVariants() {
    var body = $("v-rows");
    D.variants.forEach(function (r) {
      var tr = el("tr", r.live ? "fd-live" : null);
      td(tr, r.holdings + (r.live ? " (live)" : "")); td(tr, r.freq); td(tr, r.exit);
      td(tr, r.cash_guard_pct ? r.cash_guard_pct + "% cash when Nifty < 200-day avg" : "none");
      td(tr, pc(r.cagr), "num " + tone(r.cagr)); td(tr, pc(r.max_drawdown), "num down");
      td(tr, pc(r.worst_year), "num " + tone(r.worst_year)); td(tr, pc(r.best_year), "num up");
      td(tr, pc(r.one_year), "num " + tone(r.one_year)); td(tr, String(r.exits_per_year), "num");
      body.appendChild(tr);
    });
    $("v-note").textContent = "Selling on every Supertrend + 50-day downturn cut the worst fall, but it sold almost 300 times a year and lowered returns: the fund sold dips that recovered. " +
      "Quarterly rebalancing also earned less. The 200-day average exit keeps returns while removing stocks in a real downtrend.";
  }

  function renderSectors() {
    var box = $("s-rows");
    Object.keys(D.sector_allocation).forEach(function (k) {
      var v = D.sector_allocation[k], left = el("div");
      left.appendChild(document.createTextNode(k));
      var bar = el("div", "bar"), bb = el("b", /^Cash/.test(k) ? "cash" : null); bb.style.width = Math.min(100, v) + "%"; bar.appendChild(bb); left.appendChild(bar);
      box.appendChild(left); box.appendChild(el("div", "num", v.toFixed(2) + "%"));
    });
  }

  function renderSipSim() {
    var s = D.sip, box = $("sip-sim"), t = el("table", "fd-table");
    var head = el("tr"); ["", "Value now", "XIRR"].forEach(function (h) { head.appendChild(el("th", h ? "num" : null, h)); }); t.appendChild(head);
    [["Our fund", s.fund], ["Nifty 50", s.nifty50], ["Nifty 100 equal-weight", s.ew100]].forEach(function (r, i) {
      var tr = el("tr"); var nm = td(tr, r[0]); if (!i) nm.style.fontWeight = "800";
      td(tr, cr(r[1].value), "num"); td(tr, pc(r[1].xirr), "num " + tone(r[1].xirr)); t.appendChild(tr);
    });
    box.appendChild(el("p", "fd-note", inr(s.monthly) + " on the first trading day of every month since " + s.since + " = " + s.months + " instalments, " + cr(s.invested) + " invested."));
    box.appendChild(t);
  }

  function renderGoal() {
    var box = $("g-rows"); box.textContent = "";
    var asof = new Date(D.as_of + "T00:00:00"), end = new Date("2031-02-15T00:00:00");
    var months = (end.getFullYear() - asof.getFullYear()) * 12 + (end.getMonth() - asof.getMonth()) + 1;
    var fv1 = function (r) { var m = Math.pow(1 + r, 1 / 12) - 1; return ((Math.pow(1 + m, months) - 1) / m) * (1 + m); };
    var amt = amount() || 400000, rates = [0.10, 0.12, 0.15, D.stats.cagr.fund / 100];
    rates.forEach(function (r, i) {
      var d = el("div", i === 3 ? "flag" : null);
      d.appendChild(el("small", null, (r * 100).toFixed(1) + "% a year" + (i === 3 ? " (this fund's backtest, not a promise)" : "")));
      d.appendChild(el("b", null, inr(5e7 / fv1(r)) + " / month"));
      d.appendChild(el("small", null, "needed for ₹5 cr · " + inr(amt) + "/month becomes " + cr(amt * fv1(r))));
      box.appendChild(d);
    });
    $("g-note").textContent = months + " monthly instalments from now to 15 Feb 2031, invested at the start of each month, before tax. Plan with 10–12%; anything above that is a bonus, not a plan.";
  }

  function renderHistory() {
    var pick = $("m-pick");
    D.history.forEach(function (h, i) { var o = el("option", null, h.date + (i === 0 ? " (current)" : "")); o.value = i; pick.appendChild(o); });
    var show = function () {
      var h = D.history[+pick.value], body = $("m-rows"), ex = $("m-exits"), total = 0;
      body.textContent = ""; ex.textContent = "";
      Object.keys(h.weights).forEach(function (k, i) {
        var tr = el("tr", k === "CASH" ? "cash" : null); total += h.weights[k];
        td(tr, k === "CASH" ? "—" : String(i + 1)); td(tr, k === "CASH" ? "Liquid fund (market guard)" : k); td(tr, h.weights[k].toFixed(2) + "%", "num");
        body.appendChild(tr);
      });
      var ft = el("tr"); td(ft, ""); td(ft, "Total"); td(ft, total.toFixed(2) + "%", "num"); ft.style.fontWeight = "800"; body.appendChild(ft);
      if (!h.exits.length) { var none = el("tr"); var c = td(none, "No downtrend exits this month."); c.colSpan = 3; ex.appendChild(none); }
      h.exits.forEach(function (e) { var tr = el("tr"); td(tr, e.symbol); td(tr, e.signal_date + " at ₹" + e.close.toLocaleString("en-IN")); td(tr, e.sold_on || "next session"); ex.appendChild(tr); });
      $("m-info").textContent = (h.executed ? "bought " + h.executed : "to be bought next session") + (h.turnover_pct != null ? " · " + h.turnover_pct + "% of the fund traded" : "") + (h.guard_on ? " · market guard ON" : "") + " · " + h.exits.length + " downtrend exits";
    };
    pick.addEventListener("change", show); show();
  }
})();
