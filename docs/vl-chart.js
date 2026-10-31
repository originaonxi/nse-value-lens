/* VLChart — shared HHHL-style candlestick chart.
   VLChart.render(container, {
     bars:    [{date,open,high,low,close}, ...],   // oldest → newest
     overlays:[{values:[...], color, width, label}],// e.g. DMA lines, same length as bars
     zones:   [{price, color, label}],              // horizontal support/resistance bands
     markers: [{date, price, color, label, down}],  // crossover / event markers
     title:   "optional"
   })
   Pure SVG, responsive, no dependencies. Matches hhhl.js candle colours. */
'use strict';
(function (root) {
  var UP = '#2b8666', DOWN = '#c26859', GRID = '#e9eeea', AXIS = '#758176';

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function fmt(v) { return v == null ? '' : (v >= 1000 ? Math.round(v).toLocaleString('en-IN') : v.toFixed(1)); }

  function render(container, opts) {
    if (!container) return;
    container.textContent = '';
    var bars = (opts.bars || []).filter(function (b) { return b && b.close != null; });
    if (bars.length < 2) { container.textContent = 'Not enough price history to draw a chart.'; return; }

    var overlays = opts.overlays || [], zones = opts.zones || [], markers = opts.markers || [];
    var W = 1200, H = 460, LEFT = 18, RIGHT = 118, TOP = 28, BOT = 40;
    var plotRight = W - RIGHT, priceBottom = H - BOT, axis = plotRight;

    var vals = [];
    bars.forEach(function (b) { vals.push(b.high, b.low); });
    overlays.forEach(function (o) { (o.values || []).forEach(function (v) { if (v != null) vals.push(v); }); });
    zones.forEach(function (z) { if (z.price != null) vals.push(z.price); });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var pad = Math.max((hi - lo) * 0.12, 0.5); lo -= pad; hi += pad;

    var n = bars.length;
    var step = (plotRight - LEFT) / n;
    function x(i) { return LEFT + step * (i + 0.5); }
    function y(p) { return TOP + (hi - p) / (hi - lo) * (priceBottom - TOP); }
    var idxByDate = {}; bars.forEach(function (b, i) { idxByDate[b.date] = i; });

    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" role="img" aria-label="' +
              esc(opts.title || 'price chart') + '" style="display:block;background:#fff;border-radius:8px">';
    svg += '<rect width="' + W + '" height="' + H + '" fill="#fff"/>';

    // grid + price axis
    for (var g = 0; g <= 6; g++) {
      var price = lo + (hi - lo) * g / 6, py = y(price);
      svg += '<line x1="' + LEFT + '" y1="' + py.toFixed(1) + '" x2="' + axis + '" y2="' + py.toFixed(1) +
             '" stroke="' + GRID + '" stroke-dasharray="3 5"/>' +
             '<text x="' + (axis + 8) + '" y="' + (py + 4).toFixed(1) + '" font-size="12" fill="' + AXIS + '">' + fmt(price) + '</text>';
    }

    // zone bands (full width, dashed line + label on right)
    zones.forEach(function (z) {
      if (z.price == null) return;
      var zy = y(z.price);
      svg += '<rect x="' + LEFT + '" y="' + (zy - 5).toFixed(1) + '" width="' + (plotRight - LEFT) + '" height="10" fill="' + z.color + '" opacity="0.13"/>' +
             '<line x1="' + LEFT + '" y1="' + zy.toFixed(1) + '" x2="' + plotRight + '" y2="' + zy.toFixed(1) + '" stroke="' + z.color + '" stroke-width="1" stroke-dasharray="5 3" opacity="0.85"/>' +
             '<text x="' + (axis + 8) + '" y="' + (zy - 3).toFixed(1) + '" font-size="10" fill="' + z.color + '" font-weight="700">' + esc(z.label || '') + '</text>';
    });

    // overlay lines (DMAs)
    overlays.forEach(function (o) {
      var v = o.values || [], d = '', moveTo = true;
      for (var i = 0; i < v.length && i < n; i++) {
        if (v[i] == null) { moveTo = true; continue; }
        d += (moveTo ? 'M' : 'L') + x(i).toFixed(1) + ',' + y(v[i]).toFixed(1) + ' '; moveTo = false;
      }
      if (d) svg += '<path d="' + d + '" fill="none" stroke="' + o.color + '" stroke-width="' + (o.width || 1.4) + '" opacity="0.9"/>';
    });

    // candles
    bars.forEach(function (b, i) {
      var c = b.close >= b.open ? UP : DOWN;
      var bodyTop = Math.min(y(b.open), y(b.close));
      var bodyH = Math.max(1.4, Math.abs(y(b.open) - y(b.close)));
      svg += '<g><title>' + esc(b.date) + '  O ' + fmt(b.open) + ' H ' + fmt(b.high) + ' L ' + fmt(b.low) + ' C ' + fmt(b.close) + '</title>' +
             '<line x1="' + x(i).toFixed(1) + '" y1="' + y(b.high).toFixed(1) + '" x2="' + x(i).toFixed(1) + '" y2="' + y(b.low).toFixed(1) + '" stroke="' + c + '" stroke-width="1.2"/>' +
             '<rect x="' + (x(i) - step * 0.3).toFixed(1) + '" y="' + bodyTop.toFixed(1) + '" width="' + Math.max(1, step * 0.6).toFixed(1) + '" height="' + bodyH.toFixed(1) + '" rx="0.7" fill="' + c + '"/></g>';
    });

    // markers (crossovers / events)
    markers.forEach(function (m) {
      var i = idxByDate[m.date]; if (i == null) return;
      var mx = x(i), my = y(m.price), col = m.color || '#6b7280';
      if (m.down) svg += '<polygon points="' + mx + ',' + (my - 2) + ' ' + (mx - 6) + ',' + (my - 13) + ' ' + (mx + 6) + ',' + (my - 13) + '" fill="' + col + '"><title>' + esc(m.label || '') + '</title></polygon>';
      else svg += '<polygon points="' + mx + ',' + (my + 2) + ' ' + (mx - 6) + ',' + (my + 13) + ' ' + (mx + 6) + ',' + (my + 13) + '" fill="' + col + '"><title>' + esc(m.label || '') + '</title></polygon>';
    });

    // date axis (first, middle, last) + legend
    [0, Math.floor(n / 2), n - 1].forEach(function (i) {
      if (bars[i]) svg += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 8) + '" text-anchor="middle" font-size="11" fill="' + AXIS + '">' + esc(bars[i].date) + '</text>';
    });
    var lx = LEFT + 4;
    overlays.forEach(function (o) {
      if (!o.label) return;
      svg += '<line x1="' + lx + '" y1="12" x2="' + (lx + 18) + '" y2="12" stroke="' + o.color + '" stroke-width="2.2"/>' +
             '<text x="' + (lx + 22) + '" y="16" font-size="11" fill="' + AXIS + '">' + esc(o.label) + '</text>';
      lx += 26 + o.label.length * 7;
    });

    svg += '</svg>';
    container.innerHTML = svg;
  }

  // Convert parallel arrays {dates,opens,highs,lows,closes} → bars[]
  function barsFromArrays(h) {
    if (!h || !h.closes) return [];
    var out = [];
    for (var i = 0; i < h.closes.length; i++) {
      out.push({
        date: (h.dates || [])[i],
        open: (h.opens || h.closes)[i],
        high: (h.highs || h.closes)[i],
        low: (h.lows || h.closes)[i],
        close: h.closes[i]
      });
    }
    return out;
  }

  var api = { render: render, barsFromArrays: barsFromArrays, UP: UP, DOWN: DOWN };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.VLChart = api;
})(typeof globalThis === 'object' ? globalThis : this);
