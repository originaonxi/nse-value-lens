/* Retirement 2031 cockpit — renders docs/retirement.json + charts from daily_setups_series.json.
   Paper research, not advice. All data rendered via textContent / typed drawing (no HTML injection). */
(function () {
  "use strict";
  var cr = function (n) { return "₹" + (n / 1e7).toFixed(2) + " cr"; };
  var pct = function (n) { return (n == null ? "—" : (n > 0 ? "+" : "") + n.toFixed(2) + "%"); };
  var el = function (tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
  var scoreColor = function (s) { return s >= 65 ? "#2fb87a" : s >= 50 ? "#4a90d9" : s >= 40 ? "#d8a43a" : "#e5565b"; };
  var sectorColor = function (avg) { return avg >= 65 ? "#2fb87a" : avg >= 55 ? "#6ea8fe" : avg >= 45 ? "#d8a43a" : "#e5565b"; };

  Promise.all([
    fetch("./retirement.json?v=" + Date.now()).then(function (r) { return r.json(); }),
    fetch("./daily_setups_series.json?v=" + Date.now()).then(function (r) { return r.json(); }).catch(function () { return { series: {} }; })
  ]).then(function (res) {
    render(res[0], (res[1] && res[1].series) || {});
  }).catch(function (e) {
    document.getElementById("grid").appendChild(el("div", "err", "Could not load retirement data: " + e));
  });

  function render(d, series) {
    var g = d.goal, a = d.allocation;
    document.getElementById("asof").textContent =
      "As of " + d.as_of + " · " + g.months_left + " months to 15 Feb 2031 · " + d.fund_size + " of 100 names held";

    // ── Cockpit: progress, required return, capital plan ──
    var cp = document.getElementById("cockpit");
    var best = g.projections[g.projections.length - 1].value;
    var mid = g.projections.find(function (p) { return p.cagr === 0.12; }) || g.projections[2];
    var prog = Math.min(100, Math.round(mid.value / g.target * 100));

    var c1 = el("div", "card");
    c1.appendChild(el("h3", null, "Target by your birthday"));
    var b1 = el("div", "big"); b1.appendChild(document.createTextNode("₹5.00 cr ")); b1.appendChild(el("small", null, "15 Feb 2031")); c1.appendChild(b1);
    var bar = el("div", "bar"); var fill = el("i"); fill.style.width = prog + "%"; bar.appendChild(fill); c1.appendChild(bar);
    var r2 = el("div", "row2"); r2.appendChild(el("span", null, "At 12%/yr → " + cr(mid.value))); r2.appendChild(el("span", null, "At 20%/yr → " + cr(best))); c1.appendChild(r2);
    cp.appendChild(c1);

    var c2 = el("div", "card");
    c2.appendChild(el("h3", null, "Return you actually need"));
    var gg = el("div", "gauge"); gg.style.color = scoreColor(g.required_cagr_pct >= 25 ? 30 : 70);
    gg.appendChild(document.createTextNode(g.required_cagr_pct + "% ")); gg.appendChild(el("small", null, "CAGR")); c2.appendChild(gg);
    c2.appendChild(el("div", "sub", g.note));
    cp.appendChild(c2);

    var c3 = el("div", "card");
    c3.appendChild(el("h3", null, "Capital plan"));
    var plan = el("div", "plan");
    [["Lump now", cr(g.lump)], ["Monthly SIP", "₹" + (g.monthly_sip / 1e5).toFixed(1) + "L"], ["You contribute", cr(g.total_contribution)]].forEach(function (p) {
      var dv = el("div"); dv.appendChild(el("b", null, p[1])); dv.appendChild(document.createTextNode(p[0])); plan.appendChild(dv);
    });
    c3.appendChild(plan);
    var pt = el("table", "proj");
    g.projections.forEach(function (p) {
      var tr = el("tr");
      tr.appendChild(el("td", null, Math.round(p.cagr * 100) + "% / yr"));
      var td = el("td", p.hits_target ? "hit" : null, cr(p.value) + (p.hits_target ? " ✓" : "")); tr.appendChild(td);
      pt.appendChild(tr);
    });
    c3.appendChild(pt);
    cp.appendChild(c3);

    // ── Allocation ──
    var al = document.getElementById("alloc");
    var core = el("div", "card core");
    core.appendChild(el("div", "pct", Math.round(a.core_fraction * 100) + "% · Safe core"));
    core.appendChild(el("div", "sub", a.core));
    al.appendChild(core);
    var sat = el("div", "card sat");
    sat.appendChild(el("div", "pct", Math.round(a.satellite_fraction * 100) + "% · Our Top 50"));
    sat.appendChild(el("div", "sub", a.satellite));
    al.appendChild(sat);

    // ── Strip: VIX + sector heatmap ──
    var strip = document.getElementById("strip");
    if (d.vix && d.vix.value != null) strip.appendChild(el("span", "chip", "India VIX " + d.vix.value + (d.vix.change_pct != null ? " (" + pct(d.vix.change_pct) + ")" : "")));
    var act = d.action_summary || {};
    strip.appendChild(el("span", "chip", "Buyable now: " + ((act.ADD || 0) + (act.HOLD || 0)) + " · Wait: " + ((act.TRIM || 0) + (act.EXIT || 0))));
    (d.sector_heatmap || []).slice(0, 8).forEach(function (s) {
      var sp = el("span", "sector chip");
      var dot = el("span", "dot"); dot.style.background = sectorColor(s.avg_score); sp.appendChild(dot);
      sp.appendChild(document.createTextNode(s.sector + " · " + s.count + " · " + s.avg_score));
      strip.appendChild(sp);
    });

    // ── Fund grid ──
    document.getElementById("fundnote").textContent =
      d.disclaimer + " Ranked by a composite of the pipeline's own buy/sell strength, Jev quality, trend, momentum and reward:risk. " +
      "ADD/HOLD = own now · TRIM/EXIT = park in the safe core until the signal turns.";

    var filters = document.getElementById("filters");
    var grid = document.getElementById("grid");
    var current = "ALL";
    [["ALL", "All 50"], ["BUYABLE", "Buyable now"], ["ADD", "Add"], ["HOLD", "Hold"], ["TRIM", "Trim"], ["EXIT", "Exit"]].forEach(function (f, i) {
      var btn = el("button", i === 0 ? "on" : null, f[1]);
      btn.onclick = function () {
        current = f[0];
        Array.prototype.forEach.call(filters.children, function (b) { b.className = ""; });
        btn.className = "on";
        draw();
      };
      filters.appendChild(btn);
    });

    function keep(p) {
      if (current === "ALL") return true;
      if (current === "BUYABLE") return p.action === "ADD" || p.action === "HOLD";
      return p.action === current;
    }

    function draw() {
      grid.textContent = "";
      d.picks.filter(keep).forEach(function (p) { grid.appendChild(card(p, series[p.symbol])); });
    }
    draw();

    document.getElementById("foot").textContent =
      "Selection is technical + sentiment (trend, Supertrend, Jev, momentum), not fundamental valuation. " +
      "Universe: official Nifty 100 (" + d.membership_source + " membership). Charts: 120 daily candles with Supertrend and HH/HL swings. " +
      "This is paper research for your own decisions at Kotak, not investment advice.";
  }

  function card(p, ser) {
    var c = el("div", "stock");
    var head = el("div", "shead");
    var left = el("div");
    left.appendChild(el("span", "sym", "#" + p.fund_rank + "  " + p.symbol));
    left.appendChild(el("span", "nm", "  " + (p.name || "")));
    head.appendChild(left);
    var chg = el("span", "chg " + ((p.change_pct || 0) >= 0 ? "up" : "down"), pct(p.change_pct) + "  ₹" + (p.close != null ? p.close : "—"));
    head.appendChild(chg);
    c.appendChild(head);

    var meta = el("div", "meta");
    meta.appendChild(el("span", null, (p.sector || "") + " · " + (p.category || "")));
    meta.appendChild(el("span", "badge b-" + p.action, p.action));
    c.appendChild(meta);

    var sbar = el("div", "sbar"); var si = el("i"); si.style.width = Math.max(4, p.retire_score) + "%"; si.style.background = scoreColor(p.retire_score); sbar.appendChild(si); c.appendChild(sbar);

    var cv = el("canvas"); c.appendChild(cv);
    requestAnimationFrame(function () { drawChart(cv, ser, p); });

    var lv = el("div", "levels");
    [["Entry", p.entry], ["Stop", p.stop], ["Struct. exit", p.structure_exit], ["Target", p.next_target]].forEach(function (x) {
      var d1 = el("div"); d1.appendChild(document.createTextNode(x[0] + " ")); d1.appendChild(el("b", null, x[1] != null ? "₹" + x[1] : "—")); lv.appendChild(d1);
    });
    var j = p.jev || {};
    if (j.composite != null) { var jd = el("div"); jd.appendChild(document.createTextNode("Jev ")); jd.appendChild(el("b", null, "#" + (j.rank || "?") + "/" + (j.of || 200))); lv.appendChild(jd); }
    var sd = el("div"); sd.appendChild(document.createTextNode("Score ")); sd.appendChild(el("b", null, p.retire_score)); lv.appendChild(sd);
    c.appendChild(lv);

    if (j.words) c.appendChild(el("div", "jev", (j.regime || "") + " · " + (j.direction || "") + " · conf " + (j.confidence != null ? Math.round(j.confidence * 100) + "%" : "—") + (j.agrees === false ? " · Jev disagrees" : "")));
    return c;
  }

  function drawChart(cv, ser, p) {
    var dpr = window.devicePixelRatio || 1;
    var w = cv.clientWidth || 300, h = cv.clientHeight || 92;
    cv.width = w * dpr; cv.height = h * dpr;
    var ctx = cv.getContext("2d"); ctx.scale(dpr, dpr);
    if (!ser || !ser.c || !ser.c.length) { ctx.fillStyle = "#5c6675"; ctx.font = "11px sans-serif"; ctx.fillText("no chart series", 8, h / 2); return; }
    var n = Math.min(ser.c.length, 90), start = ser.c.length - n;
    var o = ser.o.slice(start), hi = ser.h.slice(start), lo = ser.l.slice(start), cl = ser.c.slice(start);
    var st = (ser.supertrend || []).slice(start), dir = (ser.supertrend_dir || []).slice(start);
    var lows = lo.filter(function (x) { return x != null; }), highs = hi.filter(function (x) { return x != null; });
    st.forEach(function (x) { if (x != null) { lows.push(x); highs.push(x); } });
    var min = Math.min.apply(null, lows), max = Math.max.apply(null, highs), rng = (max - min) || 1;
    var padT = 6, padB = 6, gh = h - padT - padB;
    var y = function (v) { return padT + (1 - (v - min) / rng) * gh; };
    var cw = w / n, bw = Math.max(1, cw * 0.6);

    // candles
    for (var i = 0; i < n; i++) {
      if (cl[i] == null) continue;
      var x = i * cw + cw / 2, up = cl[i] >= o[i];
      ctx.strokeStyle = up ? "#2fb87a" : "#e5565b"; ctx.fillStyle = up ? "#2fb87a" : "#e5565b";
      ctx.beginPath(); ctx.moveTo(x, y(hi[i])); ctx.lineTo(x, y(lo[i])); ctx.stroke();
      var yo = y(o[i]), yc = y(cl[i]); ctx.fillRect(x - bw / 2, Math.min(yo, yc), bw, Math.max(1, Math.abs(yc - yo)));
    }
    // supertrend line (color by direction)
    var prevDir = null;
    for (var k = 0; k < n; k++) {
      if (st[k] == null) continue;
      var xx = k * cw + cw / 2;
      if (prevDir === null) { ctx.beginPath(); ctx.moveTo(xx, y(st[k])); }
      else if (dir[k] !== prevDir) { ctx.stroke(); ctx.beginPath(); ctx.moveTo(xx, y(st[k])); }
      else ctx.lineTo(xx, y(st[k]));
      ctx.strokeStyle = dir[k] === 1 ? "rgba(47,184,122,.85)" : "rgba(229,86,91,.85)"; ctx.lineWidth = 1.4;
      prevDir = dir[k];
    }
    ctx.stroke();
    // entry / structure-exit guide lines
    [[p.structure_exit, "rgba(216,164,58,.5)"], [p.next_target, "rgba(110,168,254,.45)"]].forEach(function (g2) {
      if (g2[0] == null || g2[0] < min || g2[0] > max) return;
      ctx.strokeStyle = g2[1]; ctx.setLineDash([3, 3]); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(0, y(g2[0])); ctx.lineTo(w, y(g2[0])); ctx.stroke(); ctx.setLineDash([]);
    });
  }
})();
