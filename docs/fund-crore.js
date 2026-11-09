/* ₹1 crore one year back in the fund (fund_crore.json, built by fund_crore.py after each close) + the fund's automation status
   (fund.json). All text via textContent. */
(function () {
  "use strict";
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
  function pct(v) { return isNum(v) ? v.toFixed(1) + "%" : "-"; }
  function spct(v) { return isNum(v) ? (v > 0 ? "+" : "") + v.toFixed(2) + "%" : "-"; }
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
    var k = el("div", "fc-kpi " + (cls || ""));
    k.appendChild(el("small", null, label)); k.appendChild(el("strong", bigcls || null, big)); if (sub) k.appendChild(el("span", null, sub));
    return k;
  }
  function tags(list, cls) {
    var c = el("td");
    (list || []).forEach(function (s) { c.appendChild(el("span", "fc-tag " + (cls || ""), s)); });
    if (!list || !list.length) c.textContent = "-";
    return c;
  }

  function renderAuto(F) {
    var p = F.portfolio || {}, box = $("fc-auto"); box.textContent = "";
    box.appendChild(el("b", null, "AUTOMATED · REBUILT AFTER EVERY NSE CLOSE"));
    var ul = el("ul");
    [
      "Prices checked up to: " + F.as_of + " (daily, after the close)",
      "Last rebalance: decided " + p.decided_on + ", bought and sold at the close of " + p.executed_on,
      "Next rebalance: " + p.next_decision + " (last trading day of the month), traded at the next session's close",
      "Every day: a held stock that closes below its 200-day average is sold at the next close" +
        (p.selling_count ? " — " + p.selling_count + " selling next session" : " — none today"),
      "Market guard: " + (p.guard_on ? "ON, " + pct(p.cash_pct) + " in a liquid fund" : "off, fully invested"),
    ].forEach(function (t) { ul.appendChild(el("li", null, t)); });
    box.appendChild(ul);
  }

  function render(C, F) {
    var s = C.summary;
    $("fc-title").textContent = "₹1 crore → " + inr(s.end) + " (" + spct(s.return_pct) + ") in one year";
    $("fc-sub").textContent = "Put in at the close of " + C.start + ", valued at the close of " + C.as_of + ". Same rules as the fund, whole shares, " +
      C.cost_per_side_pct.toFixed(1) + "% cost on every rupee traded. The fund's own NAV did " + spct(s.fund_nav_return_pct) + " over the same days.";
    if (F) renderAuto(F);
    var k = $("fc-kpis"); k.textContent = "";
    k.appendChild(kpi("Fund · total P&L", sinr(s.profit), spct(s.return_pct), "main", s.profit > 0 ? "up" : "dn"));
    k.appendChild(kpi("Nifty 50 · same ₹1 crore", sinr(s.nifty50_end - C.capital), spct(s.nifty50_return_pct), "", s.nifty50_end > C.capital ? "up" : "dn"));
    k.appendChild(kpi("Equal-weight Nifty 100", sinr(s.ew100_end - C.capital), spct(s.ew100_return_pct), "", s.ew100_end > C.capital ? "up" : "dn"));
    k.appendChild(kpi("Booked (sold) P&L", sinr(s.realised_pnl), "on " + s.sells + " sells", "", s.realised_pnl > 0 ? "up" : "dn"));
    k.appendChild(kpi("Open P&L on today's stocks", sinr(s.unrealised_pnl), s.stocks_now + " stocks + " + inr(s.cash_now) + " cash", "", s.unrealised_pnl > 0 ? "up" : "dn"));
    k.appendChild(kpi("Costs paid", inr(s.fees), s.trades + " trades: " + s.rebalances + " rebalances, " + s.exits_200dma + " 200-DMA exits"));
    k.appendChild(kpi("Worst fall", pct(s.max_dd_pct), "low on " + s.dd_day));
    k.appendChild(kpi("Tax estimate", inr(s.tax_estimate), "after tax " + sinr(s.after_tax_profit)));

    if (typeof LightweightCharts !== "undefined") {
      var c = LightweightCharts.createChart($("fc-chart"), {
        autoSize: true, layout: { background: { color: "#ffffff" }, textColor: "#334155", fontSize: 12 },
        grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } }, rightPriceScale: { borderColor: "#e2e8f0" },
        timeScale: { borderColor: "#e2e8f0" }, localization: { priceFormatter: function (v) { return "₹" + v.toFixed(1) + " L"; } }
      });
      [[1, "#16a34a", 3, "Fund"], [2, "#94a3b8", 2, "Nifty 50"], [3, "#f59e0b", 2, "Equal-weight 100"]].forEach(function (z) {
        var l = c.addLineSeries({ color: z[1], lineWidth: z[2], priceLineVisible: false, title: z[3] });
        l.setData(C.curve.map(function (p) { return { time: p[0], value: p[z[0]] / 1e5 }; }));
      });
      c.timeScale().fitContent();
    } else { $("fc-chart").textContent = "Chart library failed to load."; }

    $("fc-rb-n").textContent = "· " + C.rebalances.length + " month-ends";
    var b = head($("fc-rebal"), [["Decided"], ["Traded"], ["Market guard"], ["Stocks", "num"], ["Bought new"], ["Dropped"], ["Rupees traded", "num"], ["Value after", "num"]]);
    C.rebalances.slice().reverse().forEach(function (r) {
      var tr = el("tr"); td(tr, r.decided); td(tr, r.executed); td(tr, r.guard_on ? "ON · " + pct(r.cash_pct) + " cash" : "off");
      td(tr, String(r.holdings), "num"); tr.appendChild(tags(r.added)); tr.appendChild(tags(r.removed, "out"));
      td(tr, inr(r.turnover), "num"); td(tr, inr(r.value_after), "num"); b.appendChild(tr);
    });
    var ex = C.trades.filter(function (t) { return t.why.indexOf("closed below") === 0; }).reverse();
    $("fc-ex-n").textContent = "· " + ex.length + " sales";
    b = head($("fc-exits"), [["Sold on"], ["Stock"], ["Shares", "num"], ["Price", "num"], ["Rupees", "num"], ["Held (days)", "num"], ["P&L", "num"]]);
    ex.forEach(function (t) {
      var tr = el("tr"); td(tr, t.date); td(tr, t.symbol); td(tr, num(t.shares), "num"); td(tr, num(t.price, 2), "num"); td(tr, inr(t.amount), "num");
      td(tr, num(t.held_days), "num"); td(tr, sinr(t.pnl), tone(t.pnl)); b.appendChild(tr);
    });
    b = head($("fc-months"), [["Month"], ["Value at month-end", "num"], ["Return", "num"]]);
    C.months.forEach(function (m) { var tr = el("tr"); td(tr, m.month); td(tr, inr(m.value), "num"); td(tr, spct(m.return_pct), tone(m.return_pct)); b.appendChild(tr); });
    $("fc-held-n").textContent = "· " + C.held.length + " stocks + " + inr(s.cash_now) + " in the liquid fund";
    b = head($("fc-held"), [["Stock"], ["Sector"], ["Shares", "num"], ["Price", "num"], ["Value", "num"], ["Cost", "num"], ["P&L", "num"], ["Since"]]);
    C.held.forEach(function (h) {
      var tr = el("tr"); td(tr, h.symbol); td(tr, h.sector); td(tr, num(h.shares), "num"); td(tr, num(h.price, 2), "num"); td(tr, inr(h.value), "num");
      td(tr, inr(h.cost), "num"); td(tr, sinr(h.pnl), tone(h.pnl)); td(tr, h.since); b.appendChild(tr);
    });
    $("fc-tr-n").textContent = "· " + C.trades.length + " (" + s.buys + " buys, " + s.sells + " sells), newest first";
    b = head($("fc-trades"), [["Date"], ["Side"], ["Stock"], ["Shares", "num"], ["Price", "num"], ["Rupees", "num"], ["Cost", "num"], ["P&L", "num"], ["Why"]]);
    C.trades.slice().reverse().forEach(function (t) {
      var tr = el("tr"); td(tr, t.date); td(tr, t.side, t.side === "BUY" ? "up" : "dn"); td(tr, t.symbol); td(tr, num(t.shares), "num");
      td(tr, num(t.price, 2), "num"); td(tr, inr(t.amount), "num"); td(tr, inr(t.fee), "num"); td(tr, t.pnl == null ? "" : sinr(t.pnl), tone(t.pnl)); td(tr, t.why);
      b.appendChild(tr);
    });
    var l = $("fc-limits"); l.textContent = ""; C.limits.forEach(function (x) { l.appendChild(el("li", null, x)); });
  }

  function boot() {
    var get = function (f) { return fetch(f + "?v=" + Date.now(), { cache: "no-store" }).then(function (r) { if (!r.ok) throw new Error(f + " HTTP " + r.status); return r.json(); }); };
    Promise.all([get("fund_crore.json"), get("fund.json").catch(function () { return null; })])
      .then(function (res) { render(res[0], res[1]); })
      .catch(function (e) { $("fc-title").textContent = "₹1 crore test not available: " + e.message; });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
