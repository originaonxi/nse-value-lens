/* Stock formula lab. Renders stock_lab.json + stocklab/<SYMBOL>.json (built by stock_lab.py after every close).
   All text via textContent. */
(function () {
  "use strict";
  var D = null, S = null, CH = null, SER = null, RANGE = "120", SIDE = "buy";
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
  function lakh(v) { return isNum(v) ? (v > 0 ? "+" : v < 0 ? "-" : "") + "₹" + (Math.abs(v) / 1e5).toFixed(1) + "L" : "-"; }
  function sinr(v) { return isNum(v) && v > 0 ? "+" + inr(v) : inr(v); }
  function num(v, d) { return isNum(v) ? v.toLocaleString("en-IN", { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }) : "-"; }
  function tone(v) { return isNum(v) ? (v > 0 ? "num up" : v < 0 ? "num dn" : "num") : "num"; }
  function td(tr, t, c) { tr.appendChild(el("td", c || null, t)); }
  function head(tb, cols) {
    tb.textContent = "";
    var th = el("thead"), tr = el("tr");
    cols.forEach(function (c) { tr.appendChild(el("th", c[1] || null, c[0])); });
    th.appendChild(tr); tb.appendChild(th);
    var b = el("tbody"); tb.appendChild(b); return b;
  }
  function ts(s) { return Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10), +s.slice(11, 13) || 0, +s.slice(14, 16) || 0) / 1000; }
  function kpi(box, label, big, sub, cls, bigcls) {
    var k = el("div", "e9-kpi " + (cls || ""));
    k.appendChild(el("small", null, label)); k.appendChild(el("strong", bigcls || null, big)); if (sub) k.appendChild(el("span", null, sub));
    box.appendChild(k);
  }
  function rowOf(side, f) { return D.table[side].filter(function (r) { return r.formula === f; })[0]; }

  function renderTop() {
    $("sl-sub").textContent = D.from + " → " + D.last_candle + " IST · " + D.universe.length + " stocks × " + D.formulas.length +
      " formulas × BUY and SELL · split for the honest test on " + D.split + " · rebuilt " + D.generated_at.replace("T", " ").slice(0, 16);
    var pb = rowOf("buy", D.pick.buy), ps = rowOf("sell", D.pick.sell);
    var sellOk = D.table.sell.filter(function (r) { return r.test.rs > 0; }).length;
    var sellBoth = D.table.sell.filter(function (r) { return r.test.rs > 0 && r.train.rs > 0; }).length;
    var buyBoth = D.table.buy.filter(function (r) { return r.test.rs > 0 && r.train.rs > 0; }).length;
    var bestTest = D.table.buy.slice().sort(function (a, b) { return b.test.rs - a.test.rs; })[0];
    var box = $("sl-answer"); box.textContent = "";
    box.className = "sl-answer" + (pb.test.rs + ps.test.rs < 0 ? " warn" : "");
    box.appendChild(el("b", "big", "Most money: BUY with " + D.pick.buy + ", and do not short. " +
      "Holding all 30 stocks still made more (" + lakh(D.hold.rs) + ")."));
    var ul = el("ul");
    [
      "BUY: " + D.pick.buy + " made the most on the first half (" + lakh(pb.train.rs) + ", " + pb.train.n + " trades) and then " +
        lakh(pb.test.rs) + " on the second half it never saw (" + pb.test.n + " trades, " + pb.test.stocks_up + "/30 stocks up).",
      "SELL (short): the best short formula on the first half (" + D.pick.sell + ", " + lakh(ps.train.rs) + ") lost " + lakh(ps.test.rs) +
        " on the second half. " + sellOk + " of " + D.table.sell.length + " short formulas made money on the second half; " + sellBoth + " made money in both halves.",
      "BUY + SELL together (the pair picked on the first half): " + lakh(D.combo.train) + " then " + lakh(D.combo.test) + ". Shorting turned a profit into a loss.",
      buyBoth + " of " + D.table.buy.length + " BUY formulas made money in both halves. The best BUY formula on the second half alone was " + bestTest.formula +
        " (" + lakh(bestTest.test.rs) + "), but choosing it after seeing that half is hindsight.",
      "Holding 1 lot of each of the 30 stocks for the whole period: " + lakh(D.hold.rs) + ". No formula beat simply holding in this rising market.",
    ].forEach(function (t) { ul.appendChild(el("li", null, t)); });
    box.appendChild(ul);

    var k = $("sl-kpis"); k.textContent = "";
    kpi(k, "BUY book · " + D.pick.buy, lakh(pb.all.rs), pb.all.n + " trades · all dates", "main", pb.all.rs > 0 ? "up" : "dn");
    kpi(k, "SELL book · " + D.pick.sell, lakh(ps.all.rs), ps.all.n + " trades · all dates", "", ps.all.rs > 0 ? "up" : "dn");
    kpi(k, "BUY on unseen half", lakh(pb.test.rs), "win " + pb.test.win + "% · PF " + (pb.test.pf == null ? "-" : pb.test.pf), "", pb.test.rs > 0 ? "up" : "dn");
    kpi(k, "SELL on unseen half", lakh(ps.test.rs), "win " + ps.test.win + "% · PF " + (ps.test.pf == null ? "-" : ps.test.pf), "", ps.test.rs > 0 ? "up" : "dn");
    kpi(k, "Hold all 30", lakh(D.hold.rs), "1 lot each, no trading", "", D.hold.rs > 0 ? "up" : "dn");
    kpi(k, "Trades per stock", num(Math.min.apply(null, D.stocks.map(function (s) { return s.trades; }))) + "+", "BUY + SELL books, at least");
  }

  function formulaTable(id, side) {
    var b = head($(id), [["Formula"], ["1st half ₹", "num"], ["2nd half ₹ (unseen)", "num"], ["Trades", "num"], ["Win %", "num"], ["Stocks up", "num"], ["All dates ₹", "num"]]);
    D.table[side].slice().sort(function (a, c) { return c.train.rs - a.train.rs; }).forEach(function (r) {
      var tr = el("tr", r.formula === D.pick[side] ? "pick" : null);
      var name = el("td", null, r.formula); if (r.formula === D.pick[side]) name.appendChild(el("span", "sl-tag", "picked on 1st half"));
      tr.appendChild(name); td(tr, lakh(r.train.rs), tone(r.train.rs)); td(tr, lakh(r.test.rs), tone(r.test.rs));
      td(tr, num(r.all.n), "num"); td(tr, r.test.win + "%", "num"); td(tr, r.test.stocks_up + "/30", "num"); td(tr, lakh(r.all.rs), tone(r.all.rs));
      b.appendChild(tr);
    });
  }

  function stocksTable() {
    $("sl-stocks-sub").textContent = "· BUY " + D.pick.buy + " · SELL " + D.pick.sell + " · 1 lot each · sorted by BUY P&L";
    var b = head($("sl-stocks"), [["Stock"], ["Weight", "num"], ["Lot", "num"], ["BUY ₹", "num"], ["BUY trades", "num"], ["BUY win", "num"],
      ["SELL ₹", "num"], ["SELL trades", "num"], ["Total ₹", "num"], ["Hold ₹", "num"], ["Best BUY formula (hindsight)"], ["Now"]]);
    D.stocks.slice().sort(function (a, c) { return c.buy.rs - a.buy.rs; }).forEach(function (s) {
      var tr = el("tr", S && S.symbol === s.symbol ? "on" : null);
      td(tr, s.symbol); td(tr, s.weight_pct.toFixed(2) + "%", "num"); td(tr, String(s.lot), "num");
      td(tr, sinr(s.buy.rs), tone(s.buy.rs)); td(tr, String(s.buy.n), "num"); td(tr, s.buy.win + "%", "num");
      td(tr, sinr(s.sell.rs), tone(s.sell.rs)); td(tr, String(s.sell.n), "num"); td(tr, sinr(s.total_rs), tone(s.total_rs)); td(tr, sinr(s.hold_rs), tone(s.hold_rs));
      td(tr, s.best_buy.formula + " " + lakh(s.best_buy.rs));
      td(tr, s.open_buy ? "IN BUY since " + s.open_buy.in.slice(0, 10) : s.open_sell ? "IN SELL since " + s.open_sell.in.slice(0, 10) : "flat");
      tr.addEventListener("click", function () { $("sl-sym").value = s.symbol; loadStock(s.symbol, true); });
      b.appendChild(tr);
    });
  }

  function loadStock(sym, scroll) {
    fetch("stocklab/" + encodeURIComponent(sym) + ".json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (s) { S = s; renderStock(); stocksTable(); if (scroll) $("sl-chart").scrollIntoView({ behavior: "smooth", block: "center" }); })
      .catch(function (e) { $("sl-chart-note").textContent = "Failed to load " + sym + ": " + e.message; });
  }

  function visibleTrades() { return S.trades.filter(function (t) { return SIDE === "both" || t.side.toLowerCase() === SIDE; }); }

  function renderStock() {
    var row = D.stocks.filter(function (x) { return x.symbol === S.symbol; })[0];
    $("sl-chart-sub").textContent = S.symbol + " · 1-hour · BUY = " + S.buy_formula + " · SELL = " + S.sell_formula + " · 1 lot = " + S.lot + " shares";
    if (typeof LightweightCharts === "undefined") { $("sl-chart").textContent = "Chart library failed to load."; return; }
    if (!CH) {
      CH = LightweightCharts.createChart($("sl-chart"), {
        autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
        grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } }, rightPriceScale: { borderColor: "#e2e8f0" },
        timeScale: { borderColor: "#e2e8f0", timeVisible: true, secondsVisible: false, rightOffset: 4 }
      });
      SER = CH.addCandlestickSeries({ upColor: "#16a34a", downColor: "#dc2626", borderUpColor: "#16a34a", borderDownColor: "#dc2626", wickUpColor: "#16a34a", wickDownColor: "#dc2626" });
    }
    SER.setData(S.bars.map(function (b) { return { time: ts(b[0]), open: b[1], high: b[2], low: b[3], close: b[4] }; }));
    drawMarkers(); renderRange();
    $("sl-chart-note").textContent = S.bars.length + " one-hour candles from " + S.bars[0][0].slice(0, 10) + ". Arrows sit on the candle the order fills at (the open after the signal).";

    var k = $("sl-stock-kpis"); k.textContent = "";
    kpi(k, "BUY book", sinr(row.buy.rs), row.buy.n + " trades · won " + row.buy.win + "%", "main", row.buy.rs > 0 ? "up" : "dn");
    kpi(k, "SELL book", sinr(row.sell.rs), row.sell.n + " trades · won " + row.sell.win + "%", "", row.sell.rs > 0 ? "up" : "dn");
    kpi(k, "BUY on unseen half", sinr(row.buy_test.rs), row.buy_test.n + " trades", "", row.buy_test.rs > 0 ? "up" : "dn");
    kpi(k, "Hold 1 lot", sinr(row.hold_rs), "no trading", "", row.hold_rs > 0 ? "up" : "dn");

    var tr0 = visibleTrades().slice().reverse(), acc = 0, run = {};
    visibleTrades().forEach(function (t) { acc += t.rs; run[t.side + t.in] = acc; });
    $("sl-tr-n").textContent = "· " + tr0.length + " trades, newest first";
    var b = head($("sl-trades"), [["Side"], ["Entry (open)"], ["Entry price", "num"], ["Exit (open)"], ["Exit price", "num"], ["Points", "num"], ["%", "num"], ["P&L ₹", "num"], ["Running ₹", "num"]]);
    tr0.forEach(function (t) {
      var r = el("tr", t.open ? "pick" : null);
      td(r, t.side, t.side === "BUY" ? "up" : "dn"); td(r, t.in); td(r, num(t.entry, 2), "num"); td(r, t.open ? "OPEN · last close" : t.out); td(r, num(t.exit, 2), "num");
      td(r, num(t.pts, 2), tone(t.pts)); td(r, num(t.pct, 2) + "%", tone(t.pct)); td(r, sinr(t.rs), tone(t.rs)); td(r, sinr(run[t.side + t.in]), tone(run[t.side + t.in]));
      b.appendChild(r);
    });
    var p = head($("sl-perf"), [["Formula"], ["BUY ₹", "num"], ["BUY trades", "num"], ["BUY win", "num"], ["SELL ₹", "num"], ["SELL trades", "num"], ["SELL win", "num"]]);
    S.per_formula.slice().sort(function (a, c) { return c.buy.rs - a.buy.rs; }).forEach(function (f) {
      var r = el("tr", f.formula === S.buy_formula ? "pick" : null);
      td(r, f.formula); td(r, sinr(f.buy.rs), tone(f.buy.rs)); td(r, String(f.buy.n), "num"); td(r, f.buy.win + "%", "num");
      td(r, sinr(f.sell.rs), tone(f.sell.rs)); td(r, String(f.sell.n), "num"); td(r, f.sell.win + "%", "num");
      p.appendChild(r);
    });
  }

  function drawMarkers() {
    var zoom = RANGE !== "all", m = [];
    visibleTrades().forEach(function (t) {
      var buy = t.side === "BUY";
      m.push({ time: ts(t.in), position: buy ? "belowBar" : "aboveBar", color: buy ? "#16a34a" : "#dc2626", shape: buy ? "arrowUp" : "arrowDown",
        text: zoom ? t.side + " " + num(t.entry, 0) : "" });
      if (!t.open) m.push({ time: ts(t.out), position: buy ? "aboveBar" : "belowBar", color: t.rs > 0 ? "#15803d" : "#b91c1c", shape: "circle",
        text: zoom ? sinr(t.rs) : "", size: 0.8 });
    });
    SER.setMarkers(m.sort(function (a, b) { return a.time - b.time; }));
  }

  function renderRange() {
    var box = $("sl-range"); box.textContent = "";
    [["35", "1 week"], ["120", "1 month"], ["360", "3 months"], ["720", "6 months"], ["all", "Everything"]].forEach(function (r) {
      var b = el("button", RANGE === r[0] ? "on" : null, r[1]); b.type = "button";
      b.addEventListener("click", function () { RANGE = r[0]; renderRange(); drawMarkers(); });
      box.appendChild(b);
    });
    var n = S.bars.length;
    if (RANGE === "all") CH.timeScale().fitContent();
    else CH.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - (+RANGE)), to: n + 3 });
  }

  function renderFoot() {
    var r = $("sl-rules"); r.textContent = ""; D.rules.forEach(function (x) { r.appendChild(el("li", null, x)); });
    var l = $("sl-limits"); l.textContent = ""; D.limits.forEach(function (x) { l.appendChild(el("li", null, x)); });
    var u = $("sl-data"); u.textContent = "";
    var ok = D.stocks.filter(function (s) { return s.check && s.check.days && s.check.days_within_0_1pct === s.check.days; }).length;
    var days = D.stocks.length ? (D.stocks[0].check || {}).days : 0;
    u.appendChild(el("li", null, "Candles: Upstox 1-hour candles for all " + D.stocks.length + " stocks, " + D.from + " → " + D.last_candle + "."));
    u.appendChild(el("li", null, "Against NSE's CM bhavcopy (official open, high, low and last price) for the last " + days + " sessions: " + ok + " of " +
      D.stocks.length + " stocks match within 0.1% on every day."));
    var sp = D.stocks.filter(function (s) { return s.splits && s.splits.length; });
    u.appendChild(el("li", null, sp.length ? "Split / bonus adjusted: " + sp.map(function (s) { return s.symbol + " " + s.splits.map(function (e) { return e.date + " ÷" + e.factor; }).join(", "); }).join("; ") + "."
      : "No split or bonus found in these stocks during this period."));
    if (D.missing && D.missing.length) u.appendChild(el("li", null, "No data for: " + D.missing.join(", ") + "."));
    u.appendChild(el("li", null, "Universe: the 30 biggest Nifty 50 stocks by estimated index weight (free-float market cap): " +
      D.universe.map(function (x) { return x.symbol + " " + x.weight_pct.toFixed(1) + "%"; }).join(", ") + "."));
  }

  function boot() {
    fetch("stock_lab.json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        D = d;
        renderTop(); formulaTable("sl-buy", "buy"); formulaTable("sl-sell", "sell"); renderFoot();
        var sel = $("sl-sym");
        D.stocks.slice().sort(function (a, c) { return c.weight_pct - a.weight_pct; }).forEach(function (s) {
          var o = el("option", null, s.symbol + " · " + s.weight_pct.toFixed(1) + "%"); o.value = s.symbol; sel.appendChild(o);
        });
        sel.addEventListener("change", function () { loadStock(sel.value); });
        $("sl-side").addEventListener("change", function () { SIDE = $("sl-side").value; if (S) renderStock(); });
        stocksTable();
        loadStock(sel.value);
        document.body.dataset.ready = "true";
      })
      .catch(function (e) { $("sl-sub").textContent = "Failed to load stock_lab.json: " + e.message; document.body.dataset.ready = "error"; });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
