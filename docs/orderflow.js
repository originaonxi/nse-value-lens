/* Order Flow page. Renders order_flow.json (built by order_flow.py after each NSE close).
   Maths ported from MrChartist/order-flow (PolyForm Noncommercial 1.0.0). All text via textContent. */
(function () {
  "use strict";
  var D = null, uni = "all", sel = null;
  var BU = { LONG_BUILD: "Long build-up", SHORT_COVER: "Short covering", SHORT_BUILD: "Short build-up", LONG_UNWIND: "Long unwinding", NEUTRAL: "No change" };
  var BU_CLS = { LONG_BUILD: "lb", SHORT_COVER: "sc", SHORT_BUILD: "sb", LONG_UNWIND: "lu", NEUTRAL: "nu" };
  var CHECK = { fresh: "Positions opened with the move", spot: "Spot moved the same way", options: "Option writers lean the same way", sector: "Its sector leans the same way" };

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
  function fin(v) { return typeof v === "number" && isFinite(v); }
  function num(v, d) { return fin(v) ? v.toLocaleString("en-IN", { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }) : "—"; }
  function sg(v, d) { return fin(v) ? (v > 0 ? "+" : "") + num(v, d == null ? 2 : d) : "—"; }
  function pc(v, d) { return fin(v) ? sg(v, d == null ? 2 : d) + "%" : "—"; }
  function units(v) {
    if (!fin(v)) return "—";
    var a = Math.abs(v), s = v > 0 ? "+" : v < 0 ? "−" : "";
    if (a >= 1e7) return s + (a / 1e7).toFixed(2) + " cr";
    if (a >= 1e5) return s + (a / 1e5).toFixed(2) + " L";
    return s + num(a, 0);
  }
  function td(tr, txt, cls) { var c = el("td", cls || null, txt); tr.appendChild(c); return c; }
  function head(tbl, cols) {
    tbl.textContent = "";
    var th = el("thead"), tr = el("tr");
    cols.forEach(function (c) { var h = el("th", c[1] || null, c[0]); if (c[2]) h.title = c[2]; tr.appendChild(h); });
    th.appendChild(tr); tbl.appendChild(th); var tb = el("tbody"); tbl.appendChild(tb); return tb;
  }
  function tone(v) { return fin(v) ? (v > 0 ? "num up" : v < 0 ? "num dn" : "num") : "num"; }
  function inUni(r) { return uni === "all" || r.n50; }

  /* ── board ────────────────────────────────────────────────────────── */
  function rows() { return D.rows.filter(inUni); }

  function renderStatus() {
    var R = rows(), up = R.filter(function (r) { return r.side === "bullish"; }).length,
      dn = R.filter(function (r) { return r.side === "bearish"; }).length, fl = R.length - up - dn;
    $("of-date").textContent = D.as_of;
    $("of-status").textContent = "NSE F&O bhavcopy · session " + D.as_of + " · " + up + " up · " + fl + " flat · " + dn + " down of " + R.length +
      " · a move under " + D.floor_pct + "% is rangebound · built " + D.generated_at.replace("T", " ");
    $("of-n-bull").textContent = up; $("of-n-bear").textContent = dn; $("of-n-flat").textContent = fl;
  }

  function renderSpread() {
    var box = $("of-spread"); box.textContent = "";
    var R = rows().filter(function (r) { return fin(r.move); });
    if (!R.length) return;
    var lo = Math.min(-3, Math.min.apply(null, R.map(function (r) { return r.move; }))),
      hi = Math.max(3, Math.max.apply(null, R.map(function (r) { return r.move; })));
    var W = 1000, H = 64, ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 " + W + " " + H); svg.setAttribute("width", "100%"); svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Every underlying placed by its futures move");
    function x(v) { return 10 + (v - lo) / (hi - lo) * (W - 20); }
    function line(x1, x2, y, col) { var l = document.createElementNS(ns, "line"); l.setAttribute("x1", x1); l.setAttribute("x2", x2); l.setAttribute("y1", y); l.setAttribute("y2", y); l.setAttribute("stroke", col); svg.appendChild(l); return l; }
    line(10, W - 10, H / 2, "#cbd5e1");
    var z = line(x(0), x(0), 6, "#64748b"); z.setAttribute("y2", H - 6);
    [-D.floor_pct, D.floor_pct].forEach(function (f) { var b = line(x(f), x(f), 14, "#cbd5e1"); b.setAttribute("y2", H - 14); b.setAttribute("stroke-dasharray", "3 3"); });
    R.forEach(function (r, i) {
      var c = document.createElementNS(ns, r.symbol === "NIFTY" ? "rect" : "circle");
      var cx = x(r.move), cy = H / 2 + ((i % 7) - 3) * 3.2;
      var col = r.side === "bullish" ? "#16a34a" : r.side === "bearish" ? "#dc2626" : "#94a3b8";
      if (r.symbol === "NIFTY") { c.setAttribute("x", cx - 6); c.setAttribute("y", H / 2 - 6); c.setAttribute("width", 12); c.setAttribute("height", 12); c.setAttribute("transform", "rotate(45 " + cx + " " + (H / 2) + ")"); c.setAttribute("fill", "#0f172a"); }
      else { c.setAttribute("cx", cx); c.setAttribute("cy", cy); c.setAttribute("r", 4); c.setAttribute("fill", col); c.setAttribute("fill-opacity", ".75"); }
      var t = document.createElementNS(ns, "title"); t.textContent = r.symbol + " " + pc(r.move) + " · " + BU[r.buildup]; c.appendChild(t);
      c.style.cursor = "pointer"; c.addEventListener("click", function () { detail(r.symbol, true); });
      svg.appendChild(c);
    });
    [[lo, "start"], [0, "middle"], [hi, "end"]].forEach(function (p) {
      var t = document.createElementNS(ns, "text"); t.setAttribute("x", x(p[0])); t.setAttribute("y", H - 1); t.setAttribute("font-size", "11");
      t.setAttribute("text-anchor", p[1]); t.setAttribute("fill", "#64748b"); t.textContent = pc(p[0], 1); svg.appendChild(t);
    });
    box.appendChild(svg);
    $("of-spread-note").textContent = "Every underlying as a dot, placed by its near-month futures move since the previous close. The diamond is NIFTY. Dashed lines = the ±" + D.floor_pct + "% floor. Click a dot for its card.";
  }

  function renderSectors() {
    var box = $("of-sectors"); box.textContent = "";
    D.sectors.forEach(function (s) {
      var p = el("div", "of-sector " + (s.lean || "mixed"));
      p.appendChild(el("b", null, s.sector));
      p.appendChild(el("span", s.median > 0 ? "up" : s.median < 0 ? "dn" : null, pc(s.median)));
      var bar = el("i"); var tot = s.up + s.down + s.flat || 1;
      [["u", s.up], ["f", s.flat], ["d", s.down]].forEach(function (x) { var q = el("em", x[0]); q.style.width = (x[1] / tot * 100) + "%"; bar.appendChild(q); });
      p.appendChild(bar);
      p.title = s.n + " stocks: " + s.up + " up, " + s.flat + " flat, " + s.down + " down · lean " + (s.lean || "too few to say");
      box.appendChild(p);
    });
    var b = $("of-buildups"); b.textContent = "";
    var R = rows();
    ["LONG_BUILD", "SHORT_COVER", "SHORT_BUILD", "LONG_UNWIND"].forEach(function (k) {
      var n = R.filter(function (r) { return r.buildup === k; }).length;
      var d = el("div", "of-bu " + BU_CLS[k]); d.appendChild(el("b", null, String(n))); d.appendChild(el("span", null, BU[k])); b.appendChild(d);
    });
  }

  function tile(r) {
    var t = el("button", "of-tile " + r.side + (r.symbol === sel ? " sel" : ""));
    t.type = "button";
    var strong = Math.min(1, Math.abs(r.move || 0) / 4);
    t.style.setProperty("--a", (0.08 + strong * 0.45).toFixed(2));
    t.appendChild(el("b", null, r.symbol));
    t.appendChild(el("span", "mv", pc(r.move)));
    var dot = el("i", "dot " + BU_CLS[r.buildup] + (r.buildup === "LONG_BUILD" || r.buildup === "SHORT_BUILD" ? " fill" : ""));
    dot.title = BU[r.buildup]; t.appendChild(dot);
    t.appendChild(el("small", null, r.checks_ok + "/" + r.checks_n + " · " + num((r.strength || 0) * 100, 0)));
    t.title = r.symbol + " · " + BU[r.buildup] + " · OI " + pc(r.oi_pct) + " · checks " + r.checks_ok + "/" + r.checks_n + " · strength " + num((r.strength || 0) * 100, 0);
    t.addEventListener("click", function () { detail(r.symbol, true); });
    return t;
  }

  function renderTiles() {
    ["bullish", "bearish"].forEach(function (side) {
      var box = $(side === "bullish" ? "of-bull" : "of-bear"); box.textContent = "";
      rows().filter(function (r) { return r.side === side; }).sort(function (a, b) { return Math.abs(b.move) - Math.abs(a.move); })
        .forEach(function (r) { box.appendChild(tile(r)); });
    });
  }

  /* ── one underlying ───────────────────────────────────────────────── */
  function detail(sym, scroll) {
    var r = D.rows.find(function (x) { return x.symbol === sym; });
    if (!r) return;
    sel = sym; renderTiles();
    var box = $("of-detail"); box.hidden = false;
    $("od-title").textContent = r.symbol + " · " + r.name;
    $("od-sub").textContent = (r.sector || "") + " · near-month future expiring " + r.expiry + " · lot " + num(r.lot, 0);
    var b = $("od-badge"); b.className = "of-badge " + r.side; b.textContent = r.side.toUpperCase() + " · " + BU[r.buildup];
    var kv = $("od-kv"); kv.textContent = "";
    [["Future", num(r.fut, 2), pc(r.move) + " since the previous close", tone(r.move)],
     ["Spot", num(r.spot, 2), pc(r.spot_move), tone(r.spot_move)],
     ["Open interest (all months)", units(r.oi), units(r.oi_chg) + " · " + pc(r.oi_pct), tone(r.oi_chg)],
     ["Support", num(r.support, 2), "heaviest put OI at or below spot · next " + num(r.support2, 2), ""],
     ["Resistance", num(r.resistance, 2), "heaviest call OI at or above spot · next " + num(r.resistance2, 2), ""],
     ["Option writers", "PCR " + num(r.pcr, 2), "puts " + units(r.put_add) + " · calls " + units(r.call_add) + " today", ""],
     ["Conviction", num(r.conviction, 2), "OI % with the move (opened full, closed half)", ""],
     ["Strength", r.side === "rangebound" ? "—" : num((r.strength || 0) * 100, 0) + " / 100", "rank " + (r.rank || "—") + " on its side", ""]
    ].forEach(function (x) {
      var d = el("div", "of-kvi"); d.appendChild(el("small", null, x[0])); d.appendChild(el("strong", x[3] ? x[3].replace("num ", "") : null, x[1]));
      d.appendChild(el("span", null, x[2])); kv.appendChild(d);
    });
    var ul = $("od-checks"); ul.textContent = "";
    Object.keys(CHECK).forEach(function (k) {
      var v = r.checks[k], li = el("li", v === true ? "ok" : v === false ? "no" : "na");
      li.appendChild(el("b", null, v === true ? "✓ " : v === false ? "✗ " : "– "));
      li.appendChild(document.createTextNode(CHECK[k] + (v == null ? " (not measured)" : "")));
      ul.appendChild(li);
    });
    ul.appendChild(el("li", "na", "– The last hour agrees (needs intraday data: not in a bhavcopy)"));
    var why = [];
    if (r.side !== "rangebound") why.push("The future moved " + pc(r.move) + " and open interest " + (r.oi_chg >= 0 ? "rose " : "fell ") + pc(r.oi_pct) +
      ": " + BU[r.buildup].toLowerCase() + (r.buildup === "LONG_BUILD" || r.buildup === "SHORT_BUILD" ? " (new positions opened)" : " (positions closed)") + ".");
    else why.push("The future moved " + pc(r.move) + ", inside the ±" + D.floor_pct + "% floor: rangebound.");
    why.push(r.checks_ok + " of " + r.checks_n + " measured checks hold.");
    $("od-why").textContent = why.join(" ");
    var c = D.charts[sym];
    if (c && window.VLChart) {
      var bars = c.d.map(function (d, i) { return { date: d, open: c.o[i], high: c.h[i], low: c.l[i], close: c.c[i] }; });
      var mk = [];
      c.d.forEach(function (d, i) {
        var bu = c.bu[i];
        if (bu === "LONG_BUILD") mk.push({ date: d, price: c.l[i], color: "#16a34a", label: d + " long build-up, OI " + pc(c.oi_pct[i]) });
        else if (bu === "SHORT_BUILD") mk.push({ date: d, price: c.h[i], color: "#dc2626", down: true, label: d + " short build-up, OI " + pc(c.oi_pct[i]) });
      });
      var zones = [];
      if (fin(r.support)) zones.push({ price: r.support, color: "#16a34a", label: "S " + num(r.support, 0) });
      if (fin(r.resistance)) zones.push({ price: r.resistance, color: "#dc2626", label: "R " + num(r.resistance, 0) });
      window.VLChart.render($("od-chart"), { bars: bars, zones: zones, markers: mk, title: sym + " near-month future, daily" });
      $("od-chart-note").textContent = "Near-month future, last " + c.d.length + " sessions (daily candles from the bhavcopy). ▲ green = long build-up day, ▼ red = short build-up day. Lines = today's option support and resistance.";
    }
    if (scroll) box.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* ── table ────────────────────────────────────────────────────────── */
  function renderTable() {
    var q = ($("of-q").value || "").trim().toUpperCase(), side = $("of-side").value, bu = $("of-bu").value;
    var R = rows().filter(function (r) {
      return (!q || r.symbol.indexOf(q) >= 0 || (r.sector || "").toUpperCase().indexOf(q) >= 0) && (!side || r.side === side) && (!bu || r.buildup === bu);
    }).sort(function (a, b) { return (b.move || 0) - (a.move || 0); });
    $("of-table-sub").textContent = "(" + R.length + " shown · click a row for its card)";
    var tb = head($("of-table"), [["Underlying"], ["Sector"], ["Future", "num"], ["Move", "num"], ["OI change", "num"], ["Build-up"],
      ["Checks", "num"], ["Strength", "num"], ["PCR", "num"], ["Support", "num"], ["Resistance", "num"]]);
    R.forEach(function (r) {
      var tr = el("tr", r.symbol === sel ? "sel" : null); tr.tabIndex = 0;
      td(tr, r.symbol); td(tr, r.sector || ""); td(tr, num(r.fut, 2), "num"); td(tr, pc(r.move), tone(r.move));
      td(tr, pc(r.oi_pct), tone(r.oi_pct)); td(tr, BU[r.buildup], "bu " + BU_CLS[r.buildup]);
      td(tr, r.side === "rangebound" ? "—" : r.checks_ok + "/" + r.checks_n, "num");
      td(tr, r.side === "rangebound" ? "—" : num((r.strength || 0) * 100, 0), "num");
      td(tr, num(r.pcr, 2), "num"); td(tr, num(r.support, 2), "num"); td(tr, num(r.resistance, 2), "num");
      var go = function () { detail(r.symbol, true); };
      tr.addEventListener("click", go); tr.addEventListener("keydown", function (e) { if (e.key === "Enter") go(); });
      tb.appendChild(tr);
    });
  }

  /* ── backtest ─────────────────────────────────────────────────────── */
  function renderBacktest() {
    var bt = D.backtest, sp = bt.span, rules = bt.rules;
    $("of-bt-sub").textContent = "(" + sp.sessions + " sessions, " + sp.from + " → " + sp.to + ", after " + D.cost_pct + "% cost a trade)";
    var all = rules[0].cc;
    $("of-bt-verdict").textContent = "Following every reading the next session lost money: " + num(all.n, 0) + " trades, " + all.win + "% won, average " +
      sg(all.avg, 3) + "% a trade, profit factor " + num(all.pf, 2) + " (t = " + num(all.t, 1) + "). The board describes what happened; it does not predict tomorrow. " +
      (bt.holds.length ? "Only " + bt.holds.length + " rule made money in both halves: " + bt.holds.join(", ") + "." : "No rule made money in both halves.");
    var tb = head($("of-bt"), [["Group"], ["Rule"], ["Trades", "num"], ["Hold the night: win · avg % · PF", null, "enter at the reading's close, exit next close"],
      ["1st half / 2nd half avg %", null], ["Next open → close: win · avg % · PF", null, "enter at the next open, exit at its close"], ["1st / 2nd half", null], ["t-stat", "num", "mean ÷ (σ/√n); below 2 assume luck"], ["Holds up"]]);
    rules.forEach(function (r) {
      if (!r.cc.n) return;
      var hold = r.holds_cc || r.holds_oc, tr = el("tr", hold ? "of-hold" : null);
      td(tr, r.group.replace(/^\d+ /, "")); td(tr, r.rule + (r.what !== "follow the side" ? " · " + r.what : ""));
      td(tr, num(r.cc.n, 0), "num");
      td(tr, r.cc.win + "% · " + sg(r.cc.avg, 3) + " · " + num(r.cc.pf, 2), tone(r.cc.avg));
      td(tr, sg(r.cc_h1.avg, 3) + " / " + sg(r.cc_h2.avg, 3), r.holds_cc ? "num up" : "num");
      td(tr, r.oc.win + "% · " + sg(r.oc.avg, 3) + " · " + num(r.oc.pf, 2), tone(r.oc.avg));
      td(tr, sg(r.oc_h1.avg, 3) + " / " + sg(r.oc_h2.avg, 3), r.holds_oc ? "num up" : "num");
      td(tr, num(r.cc.t, 2), tone(r.cc.t));
      td(tr, hold ? "✓" : "—", hold ? "up" : null);
      tb.appendChild(tr);
    });
    $("of-bt-note").textContent = "Each bullish reading is a buy of the future the next session, each bearish one a sell (the future still listed tomorrow, so expiry days roll to the next month). " +
      "Halves split at " + sp.half + ". \"Holds up\" = average after costs above zero in both halves. Win rate alone misleads: look at the average and the t-stat.";
  }

  function renderMethod() {
    var ol = $("of-method"); ol.textContent = "";
    [
      "Move: near-month future close vs its previous close. A move of " + D.floor_pct + "% or more is bullish or bearish; less is rangebound.",
      "Open interest: every listed futures month added together, so a roll from this month to the next cancels out.",
      "Build-up: price up + OI up = long build-up · price down + OI up = short build-up · price up + OI down = short covering · price down + OI down = long unwinding.",
      "Checks: positions opened with the move; spot moved the same way; option writers lean the same way (put OI added > call OI added for bullish); the sector leans the same way (3+ names, majority).",
      "Conviction: the OI % change with the move — new positions count in full, closing positions at half.",
      "Strength (0-100, within its side): 45% how big the move is, 35% conviction, 20% share of checks that hold — each as a percentile.",
      "Support and resistance: the heaviest put open interest at or below spot and the heaviest call open interest at or above it, nearest expiry."
    ].forEach(function (t) { ol.appendChild(el("li", null, t)); });
    var na = $("of-na"); na.textContent = ""; D.not_available.forEach(function (t) { na.appendChild(el("li", null, t)); });
    var li = $("of-limits"); li.textContent = ""; D.limits.forEach(function (t) { li.appendChild(el("li", null, t)); });
    $("of-credit").textContent = "Order-flow maths: " + D.upstream.repo + " (" + D.upstream.licence + "). " + D.upstream.notice +
      ". The full original app (live minute-by-minute board, your own broker feed) is kept in the repo under vendor/order-flow; run it on your computer with npm run dev:archive. Data: " + D.source + ".";
  }

  function renderAll() { renderStatus(); renderSpread(); renderSectors(); renderTiles(); renderTable(); }

  function boot() {
    fetch("order_flow.json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        D = d;
        renderAll(); renderBacktest(); renderMethod();
        Array.prototype.forEach.call(document.querySelectorAll(".of-switch button"), function (b) {
          b.addEventListener("click", function () {
            uni = b.dataset.u;
            Array.prototype.forEach.call(document.querySelectorAll(".of-switch button"), function (x) { x.classList.toggle("on", x === b); });
            renderAll();
          });
        });
        ["of-q", "of-side", "of-bu"].forEach(function (id) { $(id).addEventListener("input", renderTable); });
        var first = D.rows.filter(function (r) { return r.side === "bullish"; }).sort(function (a, b) { return (b.strength || 0) - (a.strength || 0); })[0] || D.rows[0];
        if (first) detail(first.symbol, false);
      })
      .catch(function (e) { $("of-status").textContent = "Failed to load order_flow.json: " + e.message; });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
