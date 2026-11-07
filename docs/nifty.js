/* Nifty 50 page — TradingView Lightweight Charts + EMA Lab tables. Renders docs/nifty.json. */
(function () {
  'use strict';
  var D, LWC, main, candles, vol, panes = {}, series = {}, priceLines = [], fibLines = [], pivotLines = [], userLines = [];
  var state = { tf: null, win: '70', ema: null, drawing: false, extra: [] };
  var TF_ORDER = ['5m', '15m', '30m', '1h', '2h', '1D'];
  var LINES_KEY = 'nf-hlines-v1';

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
  function fmt(v, d) { return v == null || isNaN(v) ? '—' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: d == null ? 2 : d, minimumFractionDigits: 0 }); }
  function sgn(v, d) { return v == null ? '—' : (v > 0 ? '+' : '') + fmt(v, d == null ? 1 : d); }
  function cls(v) { return v == null ? '' : v > 0 ? 'nf-pos' : v < 0 ? 'nf-neg' : ''; }
  function tfLabel(tf) { return tf === '1D' ? 'Daily' : tf; }
  function timeStr(t) {
    if (typeof t === 'string') return t;
    return new Date(t * 1000).toISOString().slice(0, 16).replace('T', ' ');
  }
  function sessionOf(t) { return typeof t === 'string' ? t : new Date(t * 1000).toISOString().slice(0, 10); }

  /* ── maths (same definitions as the Python engine) ───────────── */
  function ema(arr, p) {
    var out = new Array(arr.length), a = 2 / (p + 1), e = arr[0];
    for (var i = 0; i < arr.length; i++) { e = i === 0 ? arr[0] : a * arr[i] + (1 - a) * e; out[i] = e; }
    return out;
  }
  function sma(arr, p) {
    var out = new Array(arr.length), s = 0;
    for (var i = 0; i < arr.length; i++) { s += arr[i]; if (i >= p) s -= arr[i - p]; out[i] = i >= p - 1 ? s / p : null; }
    return out;
  }
  function bollinger(arr, p, k) {
    var mid = sma(arr, p), up = [], lo = [];
    for (var i = 0; i < arr.length; i++) {
      if (mid[i] == null) { up.push(null); lo.push(null); continue; }
      var v = 0; for (var j = i - p + 1; j <= i; j++) v += Math.pow(arr[j] - mid[i], 2);
      var sd = Math.sqrt(v / p); up.push(mid[i] + k * sd); lo.push(mid[i] - k * sd);
    }
    return { mid: mid, up: up, lo: lo };
  }
  function rsi(arr, p) {
    var out = new Array(arr.length).fill(null), g = 0, l = 0;
    for (var i = 1; i < arr.length; i++) {
      var d = arr[i] - arr[i - 1], up = Math.max(d, 0), dn = Math.max(-d, 0);
      if (i <= p) { g += up / p; l += dn / p; if (i === p) out[i] = l === 0 ? 100 : 100 - 100 / (1 + g / l); continue; }
      g = (g * (p - 1) + up) / p; l = (l * (p - 1) + dn) / p; out[i] = l === 0 ? 100 : 100 - 100 / (1 + g / l);
    }
    return out;
  }
  function macd(arr) {
    var f = ema(arr, 12), s = ema(arr, 26), m = f.map(function (v, i) { return v - s[i]; });
    var sig = ema(m, 9); return { m: m, sig: sig, hist: m.map(function (v, i) { return v - sig[i]; }) };
  }
  function supertrend(bars, p, mult) {
    var n = bars.length, atr = new Array(n), out = new Array(n).fill(null), dir = new Array(n).fill(1);
    var fu = 0, fl = 0;
    for (var i = 0; i < n; i++) {
      var h = bars[i][2], l = bars[i][3], pc = i ? bars[i - 1][4] : bars[i][4];
      var tr = Math.max(h - l, Math.abs(h - pc), Math.abs(l - pc));
      atr[i] = i === 0 ? tr : (atr[i - 1] * (p - 1) + tr) / p;
      var hl2 = (h + l) / 2, ub = hl2 + mult * atr[i], lb = hl2 - mult * atr[i];
      if (i === 0) { fu = ub; fl = lb; continue; }
      var c1 = bars[i - 1][4];
      fu = (ub < fu || c1 > fu) ? ub : fu;
      fl = (lb > fl || c1 < fl) ? lb : fl;
      var c = bars[i][4];
      dir[i] = dir[i - 1] === 1 ? (c < fl ? -1 : 1) : (c > fu ? 1 : -1);
      if (i >= p) out[i] = dir[i] === 1 ? fl : fu;
    }
    return { line: out, dir: dir };
  }

  /* ── indicator registry ──────────────────────────────────────── */
  var IND = [
    { id: 'rule', label: 'Rule EMA', color: '#7c3aed', on: true },
    { id: 'signals', label: 'Rule signals ▲▼', color: '#0f766e', on: true },
    { id: 'ema9', label: 'EMA 9', color: '#0ea5e9', on: false },
    { id: 'ema20', label: 'EMA 20', color: '#2563eb', on: true },
    { id: 'ema50', label: 'EMA 50', color: '#f59e0b', on: true },
    { id: 'ema200', label: 'EMA 200', color: '#dc2626', on: false },
    { id: 'bb', label: 'Bollinger 20,2', color: '#94a3b8', on: false },
    { id: 'st', label: 'Supertrend 10,3', color: '#16a34a', on: false },
    { id: 'fib', label: 'Fibonacci (window)', color: '#b45309', on: true },
    { id: 'pivot', label: 'Pivots (next session)', color: '#475569', on: false },
    { id: 'vol', label: 'Volume', color: '#64748b', on: false },
    { id: 'rsi', label: 'RSI 14', color: '#9333ea', on: false },
    { id: 'macd', label: 'MACD 12,26,9', color: '#0891b2', on: false }
  ];
  var ON = {}; IND.forEach(function (x) { ON[x.id] = x.on; });

  function chartOpts(h) {
    return {
      autoSize: true, height: h,
      layout: { background: { color: '#ffffff' }, textColor: '#334155', fontSize: 11 },
      grid: { vertLines: { color: '#f1f5f9' }, horzLines: { color: '#f1f5f9' } },
      rightPriceScale: { borderColor: '#e2e8f0' },
      timeScale: { borderColor: '#e2e8f0', timeVisible: true, secondsVisible: false, rightOffset: 4 },
      crosshair: { mode: 0 }
    };
  }

  function lineData(times, vals) {
    return times.map(function (t, i) { return vals[i] == null || isNaN(vals[i]) ? { time: t } : { time: t, value: +vals[i].toFixed(2) }; });
  }

  function addLine(key, color, width, style) {
    series[key] = main.addLineSeries({ color: color, lineWidth: width || 1.5, lineStyle: style || 0, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    return series[key];
  }

  function buildMain() {
    main = LWC.createChart($('chart-main'), chartOpts(520));
    candles = main.addCandlestickSeries({ upColor: '#2b8666', downColor: '#c26859', borderUpColor: '#2b8666', borderDownColor: '#c26859', wickUpColor: '#2b8666', wickDownColor: '#c26859' });
    vol = main.addHistogramSeries({ priceScaleId: 'vol', priceFormat: { type: 'volume' }, color: '#cbd5e1' });
    main.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    addLine('rule', '#7c3aed', 2.2); addLine('ema9', '#0ea5e9'); addLine('ema20', '#2563eb'); addLine('ema50', '#f59e0b');
    addLine('ema200', '#dc2626', 1.8); addLine('bbU', '#94a3b8', 1, 2); addLine('bbM', '#94a3b8', 1, 2); addLine('bbL', '#94a3b8', 1, 2);
    addLine('stU', '#16a34a', 1.6); addLine('stD', '#dc2626', 1.6);

    main.subscribeCrosshairMove(function (p) {
      var b = p && p.seriesData ? p.seriesData.get(candles) : null;
      if (!b) { legendLast(); return; }
      setLegend(p.time, b.open, b.high, b.low, b.close);
    });
    main.subscribeClick(function (p) {
      if (!state.drawing || !p || !p.point) return;
      var price = candles.coordinateToPrice(p.point.y);
      if (price == null) return;
      userLines.push({ price: +price.toFixed(2), color: '#2563eb' });
      saveLines(); drawUserLines(); setDrawing(false);
    });
    main.timeScale().subscribeVisibleLogicalRangeChange(function (r) {
      if (!r) return;
      Object.keys(panes).forEach(function (k) { if (panes[k].chart && !$('chart-' + k).hidden) panes[k].chart.timeScale().setVisibleLogicalRange(r); });
    });
  }

  function ensurePane(kind) {
    if (panes[kind]) return panes[kind];
    var c = LWC.createChart($('chart-' + kind), chartOpts(130));
    var p = { chart: c };
    if (kind === 'rsi') {
      p.line = c.addLineSeries({ color: '#9333ea', lineWidth: 1.5, priceLineVisible: false, lastValueVisible: true });
      [70, 50, 30].forEach(function (lv) { p.line.createPriceLine({ price: lv, color: '#cbd5e1', lineWidth: 1, lineStyle: 2, axisLabelVisible: false }); });
    } else {
      p.hist = c.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false });
      p.m = c.addLineSeries({ color: '#0891b2', lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false });
      p.s = c.addLineSeries({ color: '#f97316', lineWidth: 1.2, priceLineVisible: false, lastValueVisible: false });
    }
    panes[kind] = p; return p;
  }

  /* ── data per timeframe ──────────────────────────────────────── */
  function bars() { return D.bars[state.tf] || []; }

  function render() {
    var b = bars(); if (!b.length) return;
    var times = b.map(function (x) { return x[0]; }), close = b.map(function (x) { return x[4]; });
    candles.setData(b.map(function (x) { return { time: x[0], open: x[1], high: x[2], low: x[3], close: x[4] }; }));
    var hasVol = b.some(function (x) { return x[5] > 0; });
    vol.setData(hasVol ? b.map(function (x) { return { time: x[0], value: x[5], color: x[4] >= x[1] ? '#86efac88' : '#fca5a588' }; }) : []);

    var p = state.ema;
    series.rule.setData(lineData(times, ema(close, p)));
    series.rule.applyOptions({ title: 'EMA ' + p });
    series.ema9.setData(lineData(times, ema(close, 9)));
    series.ema20.setData(lineData(times, ema(close, 20)));
    series.ema50.setData(lineData(times, ema(close, 50)));
    series.ema200.setData(lineData(times, ema(close, 200)));
    var bb = bollinger(close, 20, 2);
    series.bbU.setData(lineData(times, bb.up)); series.bbM.setData(lineData(times, bb.mid)); series.bbL.setData(lineData(times, bb.lo));
    var st = supertrend(b, 10, 3);
    series.stU.setData(lineData(times, st.line.map(function (v, i) { return st.dir[i] === 1 ? v : null; })));
    series.stD.setData(lineData(times, st.line.map(function (v, i) { return st.dir[i] === -1 ? v : null; })));
    state.extra.forEach(function (x) { x.s.setData(lineData(times, ema(close, x.p))); });

    var r = rsi(close, 14); ensurePane('rsi').line.setData(lineData(times, r));
    var m = macd(close), mp = ensurePane('macd');
    mp.hist.setData(times.map(function (t, i) { return { time: t, value: +m.hist[i].toFixed(2), color: m.hist[i] >= 0 ? '#86efac' : '#fca5a5' }; }));
    mp.m.setData(lineData(times, m.m)); mp.s.setData(lineData(times, m.sig));

    candles.setMarkers(ON.signals ? signalMarkers(times, close, p) : []);
    applyVisibility();
    applyWindow();
    drawPivots(); drawUserLines();
    legendLast();
    $('nf-legend').title = 'Rule: ' + tfLabel(state.tf) + ' candle close vs EMA ' + p;
  }

  function signalMarkers(times, close, p) {
    var e = ema(close, p), out = [], prev = 0, warm = Math.min(3 * p, close.length - 1);
    for (var i = warm; i < close.length; i++) {
      var s = Math.sign(close[i] - e[i]) || prev;
      if (prev !== 0 && s !== prev) {
        out.push(s > 0 ? { time: times[i], position: 'belowBar', color: '#15803d', shape: 'arrowUp', text: '' }
                       : { time: times[i], position: 'aboveBar', color: '#b91c1c', shape: 'arrowDown', text: '' });
      }
      prev = s;
    }
    return out.length > 400 ? out.slice(-400) : out;
  }

  function applyVisibility() {
    series.rule.applyOptions({ visible: !!ON.rule });
    series.ema9.applyOptions({ visible: !!ON.ema9 }); series.ema20.applyOptions({ visible: !!ON.ema20 });
    series.ema50.applyOptions({ visible: !!ON.ema50 }); series.ema200.applyOptions({ visible: !!ON.ema200 });
    ['bbU', 'bbM', 'bbL'].forEach(function (k) { series[k].applyOptions({ visible: !!ON.bb }); });
    series.stU.applyOptions({ visible: !!ON.st }); series.stD.applyOptions({ visible: !!ON.st });
    vol.applyOptions({ visible: !!ON.vol });
    ['rsi', 'macd'].forEach(function (k) {
      var box = $('chart-' + k), want = !!ON[k];
      if (box.hidden === want) { box.hidden = !want; if (want) { ensurePane(k); var r = main.timeScale().getVisibleLogicalRange(); if (r) panes[k].chart.timeScale().setVisibleLogicalRange(r); } }
    });
  }

  /* ── windows: 35 / 70 / 140 sessions ─────────────────────────── */
  function windowStart() {
    var b = bars(); if (state.win === 'all') return 0;
    var n = +state.win, seen = [], idx = 0;
    for (var i = b.length - 1; i >= 0; i--) {
      var s = sessionOf(b[i][0]);
      if (seen[seen.length - 1] !== s) { seen.push(s); if (seen.length > n) break; }
      idx = i;
    }
    return idx;
  }
  function applyWindow() {
    var b = bars(), from = windowStart();
    main.timeScale().setVisibleLogicalRange({ from: from - 0.5, to: b.length - 1 + 4 });
    drawFib(from);
  }

  function clearLines(list) { list.forEach(function (pl) { candles.removePriceLine(pl); }); list.length = 0; }
  function drawFib(from) {
    clearLines(fibLines); if (!ON.fib) return;
    var b = bars().slice(from), hi = -Infinity, lo = Infinity, hiI = 0, loI = 0;
    b.forEach(function (x, i) { if (x[2] > hi) { hi = x[2]; hiI = i; } if (x[3] < lo) { lo = x[3]; loI = i; } });
    var upMove = loI < hiI;   // retracement measured against the latest swing direction
    [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1].forEach(function (r) {
      var price = upMove ? hi - (hi - lo) * r : lo + (hi - lo) * r;
      fibLines.push(candles.createPriceLine({ price: price, color: r === 0.618 || r === 0.5 ? '#b45309' : '#d6a35c', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'Fib ' + (r * 100).toFixed(1) + '%' }));
    });
  }
  function drawPivots() {
    clearLines(pivotLines); if (!ON.pivot) return;
    var d = D.bars['1D'], x = d[d.length - 1], h = x[2], l = x[3], c = x[4], P = (h + l + c) / 3;
    [['P', P], ['R1', 2 * P - l], ['S1', 2 * P - h], ['R2', P + (h - l)], ['S2', P - (h - l)]].forEach(function (lv) {
      pivotLines.push(candles.createPriceLine({ price: lv[1], color: lv[0] === 'P' ? '#475569' : lv[0][0] === 'R' ? '#b91c1c' : '#15803d', lineWidth: 1, lineStyle: 1, axisLabelVisible: true, title: lv[0] }));
    });
  }

  /* ── horizontal-line drawing tool ───────────────────────────── */
  function loadLines() { try { userLines = JSON.parse(localStorage.getItem(LINES_KEY) || '[]'); } catch (e) { userLines = []; } }
  function saveLines() { try { localStorage.setItem(LINES_KEY, JSON.stringify(userLines)); } catch (e) {} }
  var userPL = [];
  function drawUserLines() {
    userPL.forEach(function (pl) { candles.removePriceLine(pl); }); userPL = [];
    var box = $('nf-lines'); box.textContent = '';
    userLines.forEach(function (ln, i) {
      userPL.push(candles.createPriceLine({ price: ln.price, color: ln.color, lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: 'My line' }));
      var tag = el('span', null, '— ₹' + fmt(ln.price) + ' ');
      var x = el('button', null, '×'); x.title = 'Delete line';
      x.addEventListener('click', function () { userLines.splice(i, 1); saveLines(); drawUserLines(); });
      tag.appendChild(x); box.appendChild(tag);
    });
    if (userLines.length) box.insertBefore(el('span', null, 'Your lines (all timeframes):'), box.firstChild);
  }
  function setDrawing(on) {
    state.drawing = on; $('tool-hline').classList.toggle('armed', on);
    $('chart-main').classList.toggle('drawing', on);
    $('tool-hline').textContent = on ? '✏️ Click the chart…' : '✏️ Horizontal line';
  }

  /* ── legend ──────────────────────────────────────────────────── */
  function setLegend(t, o, h, l, c) {
    $('nf-legend').textContent = tfLabel(state.tf) + '  ' + timeStr(t) + '   O ' + fmt(o) + '  H ' + fmt(h) + '  L ' + fmt(l) + '  C ' + fmt(c) +
      '   ·  Rule: close vs EMA ' + state.ema;
  }
  function legendLast() { var b = bars(); if (b.length) { var x = b[b.length - 1]; setLegend(x[0], x[1], x[2], x[3], x[4]); } }

  /* ── controls ────────────────────────────────────────────────── */
  function buildControls() {
    var g = $('tf-group');
    TF_ORDER.forEach(function (tf) {
      if (!D.bars[tf] || !D.bars[tf].length) return;
      var b = el('button', null, tfLabel(tf)); b.dataset.tf = tf;
      b.addEventListener('click', function () { setTf(tf); });
      g.appendChild(b);
    });
    document.querySelectorAll('#win-group button').forEach(function (b) {
      b.addEventListener('click', function () {
        state.win = b.dataset.win;
        document.querySelectorAll('#win-group button').forEach(function (x) { x.classList.toggle('on', x === b); });
        applyWindow();
      });
    });
    var tg = $('ind-toggles');
    IND.forEach(function (x) {
      var b = el('button', ON[x.id] ? 'on' : null); b.style.color = x.color;
      var sw = el('i'); sw.style.background = x.color; b.appendChild(sw); b.appendChild(document.createTextNode(x.label));
      b.addEventListener('click', function () {
        ON[x.id] = !ON[x.id]; b.classList.toggle('on', ON[x.id]);
        if (x.id === 'fib') drawFib(windowStart());
        else if (x.id === 'pivot') drawPivots();
        else if (x.id === 'signals') render();
        else applyVisibility();
      });
      tg.appendChild(b);
    });
    var add = el('span'); add.style.marginLeft = '.4rem';
    var inp = el('input'); inp.type = 'number'; inp.min = 2; inp.max = 400; inp.placeholder = 'EMA n'; inp.style.width = '5.5em';
    var go = el('button', null, '+ Add EMA');
    go.addEventListener('click', function () {
      var p = parseInt(inp.value, 10); if (!(p >= 2 && p <= 400)) return;
      var colors = ['#db2777', '#65a30d', '#0d9488', '#ea580c', '#4f46e5'];
      var s = main.addLineSeries({ color: colors[state.extra.length % colors.length], lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false, title: 'EMA ' + p });
      state.extra.push({ p: p, s: s }); inp.value = ''; render();
    });
    add.appendChild(inp); add.appendChild(go); tg.appendChild(add);
    $('tool-hline').addEventListener('click', function () { setDrawing(!state.drawing); });
    $('tool-clear').addEventListener('click', function () { userLines = []; saveLines(); drawUserLines(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') setDrawing(false); });
  }

  function setTf(tf, emaP) {
    state.tf = tf; if (emaP) state.ema = emaP;
    document.querySelectorAll('#tf-group button').forEach(function (b) { b.classList.toggle('on', b.dataset.tf === tf); });
    render();
  }

  function loadRule(key) {
    var parts = key.split('|'), tf = parts[0], p = parseInt(parts[1], 10);
    if (!D.bars[tf]) return;
    ON.rule = true; ON.signals = true;
    document.querySelectorAll('#ind-toggles button').forEach(function (b, i) { if (IND[i] && (IND[i].id === 'rule' || IND[i].id === 'signals')) b.classList.add('on'); });
    setTf(tf, p);
    $('chart-main').scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  /* ── header + chosen card ───────────────────────────────────── */
  function renderHead() {
    $('nf-close').textContent = fmt(D.last_close);
    var ch = $('nf-chg'); ch.textContent = sgn(D.change_pct, 2) + '%'; ch.className = cls(D.change_pct);
    $('nf-asof').textContent = 'Last daily close ' + D.as_of + ' · page built ' + D.generated_at.replace('T', ' ') + ' IST';
    var c = D.chosen, cur = c.current, box = $('nf-signal');
    var badge = el('span', 'nf-badge ' + (cur.side === 'LONG' ? 'long' : 'short'), (cur.side === 'LONG' ? '▲ ' : '▼ ') + cur.side + ' · ' + tfLabel(c.tf) + ' close vs EMA ' + c.ema);
    box.appendChild(badge);
    box.appendChild(el('span', 'fd-note', 'Close ' + fmt(cur.close) + ' vs EMA ' + fmt(cur.ema) + ' (' + sgn(cur.distance) + ' pts) since ' + cur.since));
  }

  function kpi(parent, label, value, extra, wide) {
    var k = el('div', 'kpi' + (wide ? ' wide' : '')); k.appendChild(el('span', null, label));
    var s = el('strong', extra || null, value); k.appendChild(s); parent.appendChild(k); return k;
  }

  function renderChosen() {
    var c = D.chosen, j = c.jev || {}, cur = c.current, box = $('chosen-card');
    $('lab-intro').textContent = 'Tested ' + D.tested.combinations + ' "candle closes above/below EMA" rules (EMA ' + D.tested.ema_periods[0] + '–' +
      D.tested.ema_periods[D.tested.ema_periods.length - 1] + ' on ' + D.tested.timeframes.join(', ') + ') plus ' + D.tested.pair_combinations +
      ' EMA crossover pairs. Long when the candle closes above the EMA, short when it closes below, flip on the opposite close; intraday rules are flat at each session close; ' +
      D.cost_points + ' points cost per round trip. Comparison window: ' + D.windows.common_sessions + ' (60 sessions) and the last 10 sessions.';
    kpi(box, 'Chosen rule', tfLabel(c.tf) + ' candle · EMA ' + c.ema);
    kpi(box, 'Right now', cur.side + ' since ' + cur.since, cur.side === 'LONG' ? 'nf-pos' : 'nf-neg');
    kpi(box, 'Rule points since signal', sgn(cur.rule_points_since), cls(cur.rule_points_since));
    kpi(box, 'Nifty move since signal', sgn(cur.points_since), cls(cur.points_since));
    kpi(box, '60 sessions: trades / win', c.common.trades + ' / ' + fmt(c.common.win_rate, 1) + '%');
    kpi(box, '60 sessions: profit factor', fmt(c.common.pf));
    kpi(box, '60 sessions: net points', sgn(c.common.net), cls(c.common.net));
    kpi(box, 'Max drawdown (pts)', fmt(c.common.max_dd, 1));
    kpi(box, 'Last 10 sessions net', sgn(c.recent.net), cls(c.recent.net));
    kpi(box, 'Next-candle follow-through', fmt(c.common.follow, 1) + '%');
    kpi(box, 'Jev reliability', (j.reliability || '—') + (j.reliability_conf != null ? ' (' + j.reliability_conf + '%)' : ''));
    kpi(box, 'Jev recent edge', (j.recent_edge || '—') + (j.recent_edge_conf != null ? ' (' + j.recent_edge_conf + '%)' : ''));
    kpi(box, 'Final score', fmt(c.final, 1) + ' / 100');
    kpi(box, 'How to read it',
      'When a ' + tfLabel(c.tf) + ' candle closes above EMA ' + c.ema + ', Nifty tended to keep moving up; below it, down. Over the last 60 sessions this rule won ' +
      fmt(c.common.win_rate, 1) + '% of trades but winners were ' + fmt(c.common.pf) + '× the size of losers in total — a trend rule that wins big and loses small, not a high-hit-rate rule. ' +
      cur.note, null, true);
    var btn = el('button', null, 'Show this rule on the chart'); btn.addEventListener('click', function () { loadRule(c.key); });
    box.lastChild.appendChild(document.createElement('br')); box.lastChild.appendChild(btn);
  }

  /* ── tables ──────────────────────────────────────────────────── */
  function spark(arr) {
    var s = el('span', 'nf-spark'), mx = Math.max.apply(null, arr.map(Math.abs).concat([1]));
    arr.forEach(function (v) { var i = el('i'); i.style.height = Math.max(2, Math.abs(v) / mx * 18) + 'px'; i.style.background = v >= 0 ? '#22c55e' : '#ef4444'; i.title = sgn(v); s.appendChild(i); });
    return s;
  }
  function table(id, head, rows) {
    var t = $(id); t.textContent = '';
    var th = el('thead'), tr = el('tr');
    head.forEach(function (h) { var c = el('th', h[1] ? 'num' : null, h[0]); if (h[2]) c.title = h[2]; tr.appendChild(c); });
    th.appendChild(tr); t.appendChild(th);
    var tb = el('tbody'); rows.forEach(function (r) { tb.appendChild(r); }); t.appendChild(tb);
  }
  function td(tr, v, num, c) { var x = el('td', (num ? 'num ' : '') + (c || ''), v); tr.appendChild(x); return x; }
  function ruleRow(r, extra) {
    var tr = el('tr'); tr.dataset.key = r.key; if (r.key === D.chosen.key) tr.className = 'pick';
    tr.addEventListener('click', function () { loadRule(r.key); });
    td(tr, tfLabel(r.tf)); td(tr, 'EMA ' + r.ema);
    td(tr, r.code_score == null ? '—' : fmt(r.code_score, 1), true);
    (extra || []).forEach(function (f) { f(tr); });
    td(tr, r.common.trades, true); td(tr, fmt(r.common.win_rate, 1) + '%', true); td(tr, fmt(r.common.pf), true);
    td(tr, sgn(r.common.net), true, cls(r.common.net)); td(tr, fmt(r.common.max_dd, 1), true);
    td(tr, sgn(r.recent.net), true, cls(r.recent.net));
    var sp = td(tr, ''); if (r.recent_by_session) sp.appendChild(spark(r.recent_by_session));
    td(tr, fmt(r.full.pf), true); td(tr, r.sessions_full, true);
    return tr;
  }
  var RULE_HEAD = [['60s trades', 1], ['60s win %', 1], ['60s PF', 1, 'Profit factor: total points won ÷ total points lost'], ['60s net pts', 1], ['Max DD', 1],
    ['10s net pts', 1], ['Last 10 sessions'], ['Full PF', 1, 'Profit factor over the whole history available for this timeframe'], ['Sessions', 1]];

  function renderTables() {
    table('t-finalists', [['TF'], ['EMA'], ['Code', 1], ['Jev', 1], ['Jev reliability'], ['Jev edge'], ['Final', 1]].concat(RULE_HEAD),
      D.finalists.map(function (r) {
        var j = r.jev || {};
        return ruleRow(r, [
          function (tr) { td(tr, j.jev_score == null ? '—' : fmt(j.jev_score, 1), true); },
          function (tr) { td(tr, j.reliability ? j.reliability + ' ' + j.reliability_conf + '%' : (j.error ? 'error' : '—')); },
          function (tr) { td(tr, j.recent_edge ? j.recent_edge + ' ' + j.recent_edge_conf + '%' : '—'); },
          function (tr) { td(tr, fmt(r.final, 1), true); }]);
      }));
    table('t-last10', [['TF'], ['EMA'], ['Code', 1]].concat(RULE_HEAD), D.last10_leaderboard.map(function (r) { return ruleRow(r); }));
    var asked = D.asked.slice().sort(function (a, b) { return TF_ORDER.indexOf(a.tf) - TF_ORDER.indexOf(b.tf) || a.ema - b.ema; });
    table('t-asked', [['TF'], ['EMA'], ['Code', 1]].concat(RULE_HEAD), asked.map(function (r) { return ruleRow(r); }));
    var bytf = TF_ORDER.filter(function (tf) { return D.by_timeframe[tf]; }).map(function (tf) { return D.by_timeframe[tf]; });
    table('t-bytf', [['TF'], ['Best EMA'], ['Code', 1]].concat(RULE_HEAD), bytf.map(function (r) { return ruleRow(r); }));

    table('t-pairs', [['TF'], ['Fast/slow'], ['60s trades', 1], ['60s win %', 1], ['60s PF', 1], ['60s net', 1], ['10s net', 1], ['Full PF', 1]],
      D.pairs.map(function (p) {
        var tr = el('tr'); td(tr, tfLabel(p.tf)); td(tr, 'EMA ' + p.fast + ' × ' + p.slow);
        td(tr, p.common.trades, true); td(tr, fmt(p.common.win_rate, 1) + '%', true); td(tr, fmt(p.common.pf), true);
        td(tr, sgn(p.common.net), true, cls(p.common.net)); td(tr, sgn(p.recent.net), true, cls(p.recent.net)); td(tr, fmt(p.full.pf), true);
        return tr;
      }));

    var trades = D.chosen.trades.slice().reverse();
    table('t-trades', [['Entry time'], ['Side'], ['Entry', 1], ['Exit time'], ['Exit', 1], ['Net pts', 1], ['Exit reason']],
      trades.map(function (t) {
        var tr = el('tr'); td(tr, timeStr(t[0])); td(tr, t[1] > 0 ? 'LONG' : 'SHORT', false, t[1] > 0 ? 'nf-pos' : 'nf-neg');
        td(tr, fmt(t[2]), true); td(tr, timeStr(t[3])); td(tr, fmt(t[4]), true); td(tr, sgn(t[5]), true, cls(t[5]));
        td(tr, t[6] === 'session_end' ? 'Session close' : 'Opposite close'); return tr;
      }));
  }

  function renderHeat() {
    var t = $('t-heat'); t.textContent = '';
    var periods = D.tested.ema_periods, hr = el('tr'); hr.appendChild(el('th', null, 'EMA →'));
    periods.forEach(function (p) { hr.appendChild(el('th', null, String(p))); });
    var th = el('thead'); th.appendChild(hr); t.appendChild(th);
    var tb = el('tbody');
    TF_ORDER.forEach(function (tf) {
      var row = D.heatmap[tf]; if (!row) return;
      var tr = el('tr'); tr.appendChild(el('th', null, tfLabel(tf)));
      periods.forEach(function (p) {
        var v = row[String(p)], c = el('td');
        if (v == null) { c.className = 'na'; c.textContent = '·'; c.title = tfLabel(tf) + ' EMA ' + p + ': too few trades or ineligible'; }
        else {
          var a = Math.max(0, Math.min(1, v / 100));
          c.style.background = 'rgba(22,163,74,' + (0.08 + 0.85 * a * a).toFixed(2) + ')';
          if (a > 0.75) c.style.color = '#fff';
          c.textContent = Math.round(v); c.title = tfLabel(tf) + ' EMA ' + p + ': score ' + v;
          c.addEventListener('click', function () { loadRule(tf + '|' + p); });
        }
        tr.appendChild(c);
      });
      tb.appendChild(tr);
    });
    t.appendChild(tb);
  }

  function renderLimits() {
    var ul = $('nf-limits'); D.limits.forEach(function (s) { ul.appendChild(el('li', null, s)); });
    $('nf-coverage').textContent = 'Data: ' + TF_ORDER.filter(function (tf) { return D.coverage[tf]; }).map(function (tf) {
      var c = D.coverage[tf]; return tfLabel(tf) + ' ' + c.sessions + ' sessions (' + c.from.slice(0, 10) + ' → ' + c.to.slice(0, 10) + ')';
    }).join(' · ') + '. Jev: ' + (D.jev.status || '—') + (D.jev.model ? ' (' + D.jev.model + ')' : '') + '.';
  }

  /* ── boot ────────────────────────────────────────────────────── */
  function boot() {
    LWC = window.LightweightCharts;
    fetch('nifty.json?' + Date.now()).then(function (r) { return r.json(); }).then(function (data) {
      D = data;
      state.tf = D.chosen.tf; state.ema = D.chosen.ema;
      renderHead(); renderChosen(); renderTables(); renderHeat(); renderLimits();
      if (!LWC) { $('chart-main').textContent = 'Chart library failed to load.'; return; }
      loadLines(); buildMain(); buildControls(); setTf(state.tf);
    }).catch(function (e) { $('nf-asof').textContent = 'Failed to load nifty.json: ' + e; });
  }
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', boot) : boot();
})();
