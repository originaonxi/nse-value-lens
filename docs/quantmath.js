/* Bot Maths page. Renders quant_math.json (built by quant_math.py after each NSE close). All text via textContent. */
(function () {
  "use strict";
  var D = null;
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
  function fin(v) { return typeof v === "number" && isFinite(v); }
  function num(v, d) { return fin(v) ? v.toLocaleString("en-IN", { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }) : "—"; }
  function sg(v, d) { return fin(v) ? (v > 0 ? "+" : "") + num(v, d) : "—"; }
  function pc(v, d) { return fin(v) ? num(v, d == null ? 1 : d) + "%" : "—"; }
  function td(tr, t, c) { var x = el("td", c || null, t); tr.appendChild(x); return x; }
  function head(tbl, cols) {
    tbl.textContent = ""; var th = el("thead"), tr = el("tr");
    cols.forEach(function (c) { var h = el("th", c[1] || null, c[0]); if (c[2]) h.title = c[2]; tr.appendChild(h); });
    th.appendChild(tr); tbl.appendChild(th); var tb = el("tbody"); tbl.appendChild(tb); return tb;
  }
  function kv(box, items) {
    box.textContent = "";
    items.forEach(function (x) {
      var d = el("div", "of-kvi"); d.appendChild(el("small", null, x[0])); d.appendChild(el("strong", x[3] || null, x[1]));
      if (x[2]) d.appendChild(el("span", null, x[2])); box.appendChild(d);
    });
  }

  function catalogue() {
    var c = D.counts;
    $("qm-counts").textContent = "(" + c.APPLIED + " applied · " + c.ADAPTED + " adapted · " + c["NOT POSSIBLE"] + " not possible without live order-book data)";
    var tb = head($("qm-cat"), [["#"], ["Formula"], ["Maths"], ["On Nifty 50 / F&O"], ["How"]]);
    D.catalogue.forEach(function (f) {
      var tr = el("tr");
      td(tr, f.id); td(tr, f.name); td(tr, f.formula, "mono");
      td(tr, f.status, f.status === "APPLIED" ? "up" : f.status === "ADAPTED" ? "warn" : "dn"); td(tr, f.how);
      tb.appendChild(tr);
    });
  }

  function strategies() {
    var S = D.strategies.filter(function (s) { return fin(s.win); });
    var a = S[0], b = S[1], p = S[2];
    $("qm-verdict").textContent = a ? (
      "EMA 105 setup #1 on Nifty 50: " + a.n + " trades, " + a.win + "% won — the Bayesian win rate (formula 4.5) shrinks that to " + a.win_bayes + "%. " +
      "Its Sharpe is " + num(a.sharpe, 2) + " with t = " + num(a.sharpe_t, 2) + ", but it was picked from " + num(a.tested, 0) +
      " combinations, and the best of that many random strategies would show a Sharpe of about " + num(a.best_of_n_sr, 2) + " (formula 8.4). So it does not yet beat pure luck on its own numbers. " +
      (b ? "Filling at the next candle's open instead of the signal close (formula 1.6) changes almost nothing: " + b.win + "% win, PF " + num(b.pf, 2) + ". " : "") +
      (p ? "On all " + p.name.match(/\d+ stocks/)[0] + " (setup fixed, not re-fitted) the edge is small but statistically real: t = " + num(p.t_stat, 2) + " over " + num(p.n, 0) + " trades, " + p.win + "% won, average " + sg(p.ev, 2) + "% a trade." : "")
    ) : "";
    var tb = head($("qm-strat"), [["Strategy"], ["Trades", "num"], ["Win %", "num"], ["Bayes win %", "num", "4.5"], ["Breakeven win %", "num", "4.2"],
      ["EV % / trade", "num", "4.1"], ["Expectancy R", "num", "4.3"], ["PF", "num", "4.4"], ["Kelly / half", "num", "5.2"], ["Sharpe", "num", "8.1"],
      ["Sharpe t", "num", "8.2"], ["Best-of-N noise", "num", "8.4"], ["P(≥1 false)", "num", "8.3"], ["Max DD %", "num", "7.1"], ["MC 95% DD = kill switch", "num", "8.6 / 7.6"]]);
    S.forEach(function (s) {
      var tr = el("tr");
      td(tr, s.name); td(tr, num(s.n, 0), "num"); td(tr, pc(s.win), "num"); td(tr, pc(s.win_bayes), "num"); td(tr, pc(s.breakeven_win), "num");
      td(tr, sg(s.ev, 3), s.ev > 0 ? "num up" : "num dn"); td(tr, sg(s.expectancy_R, 2), "num"); td(tr, num(s.pf, 2), "num");
      td(tr, pc(s.kelly) + " / " + pc(s.half_kelly), "num"); td(tr, num(s.sharpe, 2), "num"); td(tr, num(s.sharpe_t, 2), "num");
      td(tr, num(s.best_of_n_sr, 2), s.sharpe_beats_noise ? "num up" : "num dn"); td(tr, pc(s.p_false), "num");
      td(tr, pc(s.max_dd_pts_pct) + (s.dd_note ? " (" + s.dd_note + ")" : ""), "num"); td(tr, pc(s.mc_dd95), "num");
      tb.appendChild(tr);
    });
    var no = D.next_open;
    $("qm-strat-note").textContent = "Returns are % of price per trade after 0.035% cost. Sharpe is per trade, annualised by trades a year. Best-of-N: the Sharpe the best of N random strategies would show by luck (σ_SR ≈ 1/√years). " +
      "Kill switch = stop the strategy if its drawdown passes the Monte Carlo 95th percentile. Next-open check on the Nifty setup: " + no.trades + " trades, " +
      num(no.same_close.pts, 0) + " points at the signal close vs " + num(no.next_open.pts, 0) + " points at the next open.";
  }

  function nifty() {
    var n = D.nifty;
    kv($("qm-nifty"), [
      ["Close", num(n.close, 2), n.to], ["Volatility a year (1.2)", pc(n.vol_year), "EWMA λ 0.94 (1.3): " + pc(n.ewma_vol_year)],
      ["ATR (1.4)", pc(n.atr_pct, 2), num(n.atr, 1) + " points"], ["Z-score vs 20-day (2.1)", num(n.zscore20, 2), Math.abs(n.zscore20) > 2 ? "stretched" : "normal", Math.abs(n.zscore20) > 2 ? "dn" : ""],
      ["RSI (2.4)", num(n.rsi, 1), n.rsi > 70 ? "overbought zone" : ""], ["Momentum 12-1 (2.3)", pc(n.mom_12_1), ""],
      ["t-stat, 1 year (3.1)", num(n.t_stat_1y, 2), Math.abs(n.t_stat_1y) < 2 ? "below 2: no drift beyond luck" : "significant drift"],
      ["Hurst (3.4)", num(n.hurst, 3), n.hurst > 0.55 ? "trends" : n.hurst < 0.45 ? "mean-reverts" : "near random walk"],
      ["Gap to 50-day mean: ADF (3.2)", n.df_gap_pass ? "reverts" : "no", "half-life " + num(n.half_life, 1) + " sessions (3.3)"],
      ["Regime (3.6)", n.regime, "σ20/σ252 = " + num(n.regime_ratio, 2)], ["Max drawdown, 3 years (7.1)", pc(n.max_dd_3y), "recovery needed " + pc(n.recovery_needed) + " (7.2)"],
      ["1-day VaR 95%, 1 lot (7.3)", "₹" + num(n.var95_lot, 0), "lot 75"], ["Futures carry (2.6 adapted)", pc(n.carry_apr, 2) + " a year", "basis " + pc(n.basis_pct, 3) + ", " + n.dte + " days to expiry"],
      ["Bad ticks > 6σ (1.5)", String(n.bad_ticks), (n.bad_tick_dates || []).join(", ") + " — real moves, kept"]
    ]);
  }

  var sortKey = "symbol";
  function rowsTable() {
    var q = ($("qm-q").value || "").trim().toUpperCase();
    var R = D.rows.filter(function (r) { return !q || r.symbol.indexOf(q) >= 0 || (r.sector || "").toUpperCase().indexOf(q) >= 0; });
    R.sort(function (a, b) { return sortKey === "symbol" ? a.symbol.localeCompare(b.symbol) : (b[sortKey] || -1e9) - (a[sortKey] || -1e9); });
    var tb = head($("qm-rows"), [["Stock"], ["Vol %", "num", "1.2"], ["ATR %", "num", "1.4"], ["Z20", "num", "2.1"], ["RSI", "num", "2.4"], ["Mom 12-1", "num", "2.3"],
      ["t 1y", "num", "3.1"], ["Hurst", "num", "3.4"], ["ADF gap", null, "3.2"], ["Half-life", "num", "3.3"], ["Corr Nifty", "num", "3.5"], ["Regime", null, "3.6"],
      ["Max DD 3y", "num", "7.1"], ["VaR/lot", "num", "7.3"], ["Margin wipe (ATRs)", "num", "5.6 adapted"], ["Impact 10 lots bp", "num", "6.3"], ["Carry %/yr", "num", "2.6 adapted"], ["Risk parity w%", "num", "5.5"]]);
    R.forEach(function (r) {
      var tr = el("tr");
      var c = td(tr, ""); c.appendChild(el("b", null, r.symbol)); c.appendChild(el("small", null, " " + (r.sector || "")));
      td(tr, num(r.vol_year, 1), "num"); td(tr, num(r.atr_pct, 2), "num"); td(tr, num(r.zscore20, 2), "num"); td(tr, num(r.rsi, 0), "num");
      td(tr, sg(r.mom_12_1, 1), r.mom_12_1 > 0 ? "num up" : "num dn"); td(tr, num(r.t_stat_1y, 2), Math.abs(r.t_stat_1y) >= 2 ? "num up" : "num");
      td(tr, num(r.hurst, 3), "num"); td(tr, r.df_gap_pass ? "reverts" : "—"); td(tr, num(r.half_life, 1), "num"); td(tr, num(r.corr_nifty, 2), "num");
      td(tr, r.regime, r.regime === "high-vol" ? "dn" : null); td(tr, pc(r.max_dd_3y), "num"); td(tr, "₹" + num(r.var95_lot, 0), "num");
      td(tr, num(r.margin_wipe_atr, 1), "num"); td(tr, num(r.impact_10lot_bp, 1), "num"); td(tr, num(r.carry_apr, 2), "num"); td(tr, num(r.risk_parity_w, 3), "num");
      tb.appendChild(tr);
    });
  }

  function summary() {
    var s = D.summary, p = D.portfolio;
    $("qm-sum").textContent = "(" + s.stocks + " stocks)";
    kv($("qm-port"), [
      ["Median volatility", pc(s.median_vol), "a year"], ["Median Hurst", num(s.median_hurst, 3), s.trending_hurst + " stocks above 0.55 (trend) · " + s.reverting_hurst + " below 0.45"],
      ["Price passes ADF", s.df_price_pass + " of " + s.stocks, "prices almost never mean-revert"], ["Gap to 50-day mean passes ADF", s.df_gap_pass + " of " + s.stocks, "median half-life " + num(s.median_half_life, 1) + " sessions"],
      ["1-year drift t ≥ 2", s.positive_t + " of " + s.stocks, "returns beyond luck in a year"], ["High-vol regime now", String(s.high_vol_regime), "σ20/σ252 > 1.5"],
      ["Average pair correlation (3.5)", num(p.avg_pair_corr, 3), "median vs Nifty " + num(s.median_corr_nifty, 2)],
      ["Portfolio vol (7.4)", pc(p.equal_weight_vol) + " equal · " + pc(p.risk_parity_vol) + " risk parity", "vs " + pc(p.avg_stock_vol) + " for one stock"]
    ]);
  }

  function sizing() {
    var st = D.settings;
    $("qm-size-sub").textContent = "(₹" + num(st.equity, 0) + " account, " + st.risk_pct + "% risk a trade, stop = EMA 105 on 2-hour candles · formula 5.1)";
    var tb = head($("qm-size"), [["Stock"], ["State"], ["Close", "num"], ["Stop (EMA 105)", "num"], ["Risk/share", "num"], ["Risk %", "num"], ["Shares for 1% risk", "num"], ["= lots", "num"], ["1 lot risks", "num"], ["… of equity", "num"]]);
    D.sizing.forEach(function (z) {
      var tr = el("tr");
      td(tr, z.symbol); td(tr, z.state); td(tr, num(z.close, 2), "num"); td(tr, num(z.stop, 2), "num"); td(tr, num(z.risk_per_share, 2), "num");
      td(tr, pc(z.risk_pct), "num"); td(tr, num(z.shares, 0), "num"); td(tr, num(z.lots, 2), "num"); td(tr, "₹" + num(z.one_lot_risk, 0), "num");
      td(tr, pc(z.one_lot_risk_pct_equity, 2), z.one_lot_risk_pct_equity > 1 ? "num dn" : "num");
      tb.appendChild(tr);
    });
  }

  function boot() {
    fetch("quant_math.json?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (d) {
        D = d;
        $("qm-date").textContent = D.as_of;
        $("qm-status").textContent = "Computed " + D.generated_at.replace("T", " ") + " IST from Nifty 50 daily candles, " + D.summary.stocks + " F&O stocks, the NSE F&O bhavcopy and this site's strategy trade lists.";
        catalogue(); strategies(); nifty(); summary(); rowsTable(); sizing();
        var lim = $("qm-limits"); D.limits.forEach(function (t) { lim.appendChild(el("li", null, t)); });
        $("qm-q").addEventListener("input", rowsTable);
        $("qm-sort").addEventListener("change", function (e) { sortKey = e.target.value; rowsTable(); });
      })
      .catch(function (e) { $("qm-status").textContent = "Failed to load quant_math.json: " + e.message; });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
