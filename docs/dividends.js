/* Value Lens Dividend Desk. Renders docs/dividends.json. All text via textContent (no HTML injection).
   Paper research, not advice. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var el = function (tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
  var inr = function (n) { return n == null ? "—" : "₹" + Math.round(n).toLocaleString("en-IN"); };
  var pcv = function (v, dp) { return v == null ? "—" : v.toFixed(dp == null ? 1 : dp) + "%"; };
  var D, allFilter = "all", selected = null;

  fetch("./dividends.json?v=" + Date.now()).then(function (r) { return r.json(); }).then(function (d) { D = d; render(); })
    .catch(function (e) { $("d-banner").textContent = "Could not load dividend data: " + e; });

  function td(tr, txt, cls) { var c = el("td", cls, txt); tr.appendChild(c); return c; }
  function yclass(y) { return y >= 6 ? "up" : y >= 3 ? "" : "down"; }

  function render() {
    $("d-month").textContent = D.report_month;
    $("d-asof").textContent = "As of " + D.as_of + " · Nifty 200 · Yahoo Finance";
    var s = D.summary, p = D.portfolio;
    var b = $("d-banner"); b.className = "fd-banner open"; b.textContent = "";
    b.appendChild(el("b", null, "No Nifty 200 stock pays a steady 20% dividend yield."));
    var extra = D.answer_20pct.count ? " " + D.answer_20pct.count + " touched 20%+ in a single year through one-off special dividends, not a repeatable payout." : "";
    b.appendChild(document.createTextNode(" The best steady yields are about " + pcv(s.best_steady_yield) + "." + extra + " " + D.answer_20pct.verdict));

    $("k-cov").textContent = D.covered + " / 200";
    $("k-steady").textContent = s.steady_payers;
    $("k-best").textContent = pcv(s.best_steady_yield);
    $("k-yield").textContent = pcv(p.yield_on_cost, 2);
    $("k-yield-sub").textContent = inr(p.annual_income) + " a year on " + inr(p.invested);

    // 1) Portfolio
    $("p-note").textContent = p.words;
    var pb = $("p-rows");
    p.holdings.forEach(function (h, i) {
      var tr = el("tr");
      td(tr, String(i + 1));
      var c = td(tr, null, "fd-sym"); c.appendChild(el("strong", null, h.symbol)); c.appendChild(el("small", null, h.sector));
      td(tr, h.weight_pct.toFixed(1) + "%", "num");
      td(tr, h.close.toLocaleString("en-IN"), "num");
      td(tr, String(h.shares), "num");
      td(tr, inr(h.cost), "num");
      td(tr, pcv(h.current_yield), "num " + yclass(h.current_yield)).classList.add("fd-yield");
      td(tr, h.ttm_dividend.toFixed(2), "num");
      td(tr, inr(h.annual_income), "num");
      td(tr, h.income_score.toFixed(0), "num");
      pb.appendChild(tr);
    });
    var ft = el("tr");
    td(ft, ""); td(ft, "Total · " + p.holdings.length + " stocks"); td(ft, "");
    td(ft, ""); td(ft, ""); td(ft, inr(p.invested), "num");
    td(ft, pcv(p.yield_on_cost, 2), "num"); td(ft, ""); td(ft, inr(p.annual_income), "num"); td(ft, "");
    ft.style.fontWeight = "800"; pb.parentElement.appendChild(el("tfoot")).appendChild(ft);
    $("p-foot").appendChild(ft.cloneNode(true));
    ft.remove();
    var note = el("tr"); var nc = td(note, "Cash left after whole shares: " + inr(p.cash_left) + " · buy at Monday's open; prices will differ."); nc.colSpan = 10; nc.style.color = "var(--muted)"; $("p-foot").appendChild(note);

    // 2) The 20% answer
    var a = $("d-answer");
    a.appendChild(el("p", null, D.answer_20pct.verdict));
    if (D.answer_20pct.names.length) {
      a.appendChild(el("p", "fd-note", "Stocks that touched 20% in any single year (all special-dividend driven):"));
      var ul = el("div");
      D.answer_20pct.names.forEach(function (n) {
        ul.appendChild(el("span", "fd-pill out", n.symbol + " · peak " + pcv(n.max_yield_10y) + " · 10-yr avg " + pcv(n.avg_yield_10y)));
      });
      a.appendChild(ul);
    } else {
      a.appendChild(el("p", "fd-note", "Not one Nifty 200 stock even touched a 20% single-year yield in the last decade without it being a flagged special dividend."));
    }

    // 3) Full ranking
    var counts = { all: D.rows.length, steady: 0, high: 0, special: 0 };
    D.rows.forEach(function (m) { if (m.years_paid >= 8 && !m.special_heavy) counts.steady++; if (m.current_yield >= 5) counts.high++; if (m.special_heavy) counts.special++; });
    var f = $("d-filters");
    [["all", "All " + counts.all], ["steady", "Steady payers " + counts.steady], ["high", "Yield 5%+ " + counts.high], ["special", "Special-dividend " + counts.special]].forEach(function (x, i) {
      var btn = el("button", i === 0 ? "on" : null, x[1]);
      btn.onclick = function () { allFilter = x[0]; Array.prototype.forEach.call(f.children, function (c) { c.className = ""; }); btn.className = "on"; drawAll(); };
      f.appendChild(btn);
    });
    drawAll();

    D.score_method.forEach(function (t) { $("d-method").appendChild(el("li", null, t)); });
    D.limits.forEach(function (t) { $("d-limits").appendChild(el("li", null, t)); });
  }

  function drawAll() {
    var body = $("d-rows"); body.textContent = "";
    var rows = D.rows.filter(function (m) {
      return allFilter === "steady" ? (m.years_paid >= 8 && !m.special_heavy)
        : allFilter === "high" ? m.current_yield >= 5
        : allFilter === "special" ? m.special_heavy : true;
    });
    rows.forEach(function (m) {
      var tr = el("tr");
      td(tr, String(m.rank));
      var c = td(tr, null, "fd-sym"); c.appendChild(el("strong", null, m.symbol)); c.appendChild(el("small", null, m.name));
      td(tr, m.sector);
      td(tr, pcv(m.current_yield), "num " + yclass(m.current_yield)).classList.add("fd-yield");
      td(tr, pcv(m.avg_yield_10y), "num");
      td(tr, pcv(m.max_yield_10y), "num");
      td(tr, m.years_paid + "/10", "num");
      td(tr, pcv(m.ten_year_payback_pct, 0), "num");
      td(tr, m.dividend_growth_pct == null ? "—" : (m.dividend_growth_pct > 0 ? "+" : "") + m.dividend_growth_pct + "%", "num " + (m.dividend_growth_pct > 0 ? "up" : m.dividend_growth_pct < 0 ? "down" : ""));
      var note = td(tr); note.appendChild(m.special_heavy ? el("span", "dv-flag", "special div") : m.years_paid >= 8 ? el("span", "dv-steady", "steady") : el("span", "fd-note", "—"));
      td(tr, m.income_score.toFixed(0), "num").style.fontWeight = "800";
      tr.style.cursor = "pointer";
      tr.addEventListener("click", function () { showDetail(m); });
      body.appendChild(tr);
    });
  }

  function showDetail(m) {
    var box = $("d-detail"); box.hidden = false;
    $("x-title").textContent = "#" + m.rank + " " + m.symbol + " · " + m.name;
    $("x-sub").textContent = m.sector + " · price ₹" + m.close.toLocaleString("en-IN") + " · current yield " + pcv(m.current_yield) +
      " · paid " + m.years_paid + " of 10 years · 10-yr dividends ₹" + m.ten_year_total_per_share + "/share (" + pcv(m.ten_year_payback_pct, 0) + " of today's price)";
    $("x-score").textContent = "Income score " + m.income_score.toFixed(0) + "/100";
    var bars = $("x-bars"); bars.textContent = "";
    var years = Object.keys(m.by_year), vals = years.map(function (y) { return m.by_year[y]; });
    var mx = Math.max.apply(null, vals.concat([0.01]));
    var med = vals.filter(function (v) { return v > 0; }).sort(function (a, b) { return a - b; });
    var medv = 0; if (med.length) { var mid = med.length >> 1; medv = med.length % 2 ? med[mid] : (med[mid - 1] + med[mid]) / 2; }
    years.forEach(function (y) {
      var v = m.by_year[y], col = el("div", "col");
      col.appendChild(el("div", "v", v ? v.toFixed(1) : ""));
      var bar = el("div", "bar" + (medv && v > 2.5 * medv ? " special" : "")); bar.style.height = (v / mx * 110) + "px";
      col.appendChild(bar);
      col.appendChild(el("div", "yr", y.slice(2)));
      bars.appendChild(col);
    });
    $("x-summary").textContent = (m.special_heavy
      ? "Yellow bars are one-off special dividends — they lift a single year's yield but rarely repeat, so don't count on them."
      : "A steady payer: dividends across the years without a single-year spike doing the heavy lifting.") +
      " Dividend per share by calendar year; 10-year average yield " + pcv(m.avg_yield_10y) + ".";
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
})();
