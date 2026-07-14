'use strict';

const path = require('path');
const express = require('express');
const { marked } = require('marked');
const sanitizeHtml = require('sanitize-html');
const { analyzeSymbol, BUDGET_THEMES, getShortlist } = require('./analyzer');
const { getNifty200Constituents } = require('./adapters');
const fs = require('fs');
const { execFile } = require('child_process');
const cron = require('node-cron');

const app = express();
const port = process.env.PORT || 3000;
const hits = new Map();
const WINDOW_MS = 60 * 1000;
const MAX_REQUESTS = 30;

function rateLimit(req, res, next) {
  const key = req.headers['x-forwarded-for'] || req.socket.remoteAddress || 'unknown';
  const now = Date.now();
  const row = hits.get(key) || [];
  const fresh = row.filter((t) => now - t < WINDOW_MS);
  fresh.push(now);
  hits.set(key, fresh);
  if (fresh.length > MAX_REQUESTS) {
    return res.status(429).json({ ok: false, error: 'Too many requests. Please wait a minute and retry.' });
  }
  return next();
}

function renderSafeMarkdown(markdown) {
  return sanitizeHtml(marked.parse(markdown), {
    allowedTags: sanitizeHtml.defaults.allowedTags.concat(['h1', 'h2', 'table', 'thead', 'tbody', 'tr', 'th', 'td']),
    allowedAttributes: {
      a: ['href', 'name', 'target', 'rel'],
    },
    transformTags: {
      a: sanitizeHtml.simpleTransform('a', { rel: 'noopener noreferrer', target: '_blank' }),
    },
  });
}


app.use(express.json({ limit: '256kb' }));
app.use(express.static(path.join(__dirname, '..', 'public'), {
  setHeaders(res, filePath) {
    if (filePath.endsWith('.html')) {
      res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
      res.setHeader('Pragma', 'no-cache');
      res.setHeader('Expires', '0');
    }
  }
}));

app.get('/health', (_req, res) => {
  res.json({ ok: true, name: 'nse-value-lens' });
});

app.get('/api/constituents', rateLimit, async (_req, res) => {
  try {
    const rows = await getNifty200Constituents();
    res.json({ ok: true, count: rows.length, rows });
  } catch (err) {
    res.status(502).json({ ok: false, error: err.message });
  }
});

app.get('/api/themes', (_req, res) => {
  res.json({ ok: true, themes: BUDGET_THEMES });
});

app.get('/api/shortlist', (_req, res) => {
  res.json({ ok: true, shortlist: getShortlist() });
});

app.get('/api/openfund', (_req, res) => {
  try {
    const raw = fs.readFileSync(path.join(__dirname, '..', 'data', 'openfund_picks.json'), 'utf8');
    const payload = JSON.parse(raw);
    res.json({ ok: true, as_of: payload.as_of, method: payload.method, stocks: payload.stocks });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

app.post('/api/analyze', rateLimit, async (req, res) => {
  const symbol = String(req.body?.symbol || '').trim().toUpperCase();
  if (!symbol) return res.status(400).json({ ok: false, error: 'symbol is required' });
  const manual = req.body?.manual && typeof req.body.manual === 'object' ? req.body.manual : {};
  try {
    const result = await analyzeSymbol(symbol, manual);
    res.json({
      ok: true,
      symbol,
      markdown: result.markdown,
      html: renderSafeMarkdown(result.markdown),
      data: result.data,
      prompt: result.prompt,
    });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message, symbol });
  }
});

/* ── S/R alerts endpoint ── */
const STOCKS_PUB = path.join(__dirname, '..', 'public', 'data', 'stocks.js');
function loadStocksData() {
  try {
    const raw = fs.readFileSync(STOCKS_PUB, 'utf8');
    const m = raw.match(/window\.STOCK_DATA\s*=\s*(\{[\s\S]*\})\s*;?\s*$/);
    return m ? JSON.parse(m[1]) : null;
  } catch { return null; }
}

app.get('/api/sr-alerts', (_req, res) => {
  const data = loadStocksData();
  if (!data) return res.status(500).json({ ok: false, error: 'stocks not loaded' });
  const THRESH = 5;
  const alerts = data.stocks
    .filter(s => s.math_detail && s.math_detail.support_resistance)
    .map(s => {
      const sr = s.math_detail.support_resistance;
      const pz = s.math_detail.price_zones;
      const supDist = sr.support_dist_pct;
      const resDist = sr.resistance_dist_pct;
      const nearSup = supDist != null && supDist >= -THRESH && supDist <= 0;
      const nearRes = resDist != null && resDist >= 0 && resDist <= THRESH;
      if (!nearSup && !nearRes && !sr.breaking_out && !sr.breaking_down) return null;
      return {
        symbol: s.symbol, name: s.name, sector: s.sector, price: s.price,
        near_support: nearSup, near_resistance: nearRes,
        breaking_out: sr.breaking_out, breaking_down: sr.breaking_down,
        support_dist_pct: supDist, resistance_dist_pct: resDist,
        near_support_level: sr.near_support, near_resistance_level: sr.near_resistance,
        zone: pz ? pz.zone : null,
        composite: s.scores ? s.scores.composite : null,
        overall_score: s.math_detail.overall_score,
        overall_verdict: s.math_detail.overall_verdict,
      };
    })
    .filter(Boolean);
  res.json({ ok: true, as_of: data.as_of, count: alerts.length, alerts });
});

/* ── Token-gated manual refresh ── */
app.post('/api/refresh', (req, res) => {
  const secret = process.env.REFRESH_SECRET;
  const auth = (req.headers['authorization'] || '').replace('Bearer ', '').trim();
  if (!secret || auth !== secret)
    return res.status(401).json({ ok: false, error: 'unauthorized' });
  runRefresh((err, out) => {
    if (err) return res.status(500).json({ ok: false, error: err.message });
    res.json({ ok: true, output: out });
  });
});

/* ── Shared refresh runner ── */
function runRefresh(cb) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const script = path.join(__dirname, '..', 'scripts', 'enhance_math.py');
  execFile(py, [script], { cwd: path.join(__dirname, '..'), timeout: 300000 },
    (err, stdout, stderr) => cb(err, (stdout + stderr).trim().split('\n').pop()));
}

/* ── Daily cron 06:30 IST = 01:00 UTC ── */
cron.schedule('0 1 * * *', () => {
  console.log('[cron] daily S/R refresh starting…');
  runRefresh((err, out) => {
    if (err) console.error('[cron] failed:', err.message);
    else console.log('[cron] done:', out);
  });
});

app.listen(port, () => {
  console.log(`NSE Value Lens running on http://localhost:${port}`);
});
