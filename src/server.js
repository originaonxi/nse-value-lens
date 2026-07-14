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

const PUBLIC_DIR = path.join(__dirname, '..', 'public');
const INDEX_HTML = path.join(PUBLIC_DIR, 'index.html');
function setNoCacheHtml(res) {
  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
  res.setHeader('Surrogate-Control', 'no-store');
  res.setHeader('Pragma', 'no-cache');
  res.setHeader('Expires', '0');
}

// Explicit dynamic HTML routes so Railway edge always serves the latest command-center UI
app.get(['/', '/index.html'], (_req, res) => {
  setNoCacheHtml(res);
  res.type('html').send(fs.readFileSync(INDEX_HTML, 'utf8'));
});

app.use(express.static(PUBLIC_DIR, {
  setHeaders(res, filePath) {
    if (filePath.endsWith('.html')) setNoCacheHtml(res);
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
/* ── Net sellers endpoint (Airtable-backed) ── */
app.get('/api/net-sellers', async (_req, res) => {
  const AKEY = process.env.AIRTABLE_API_KEY;
  const BASE_ID = process.env.AIRTABLE_BASE_ID || 'appQsIke1wuAVOkpF';
  if (!AKEY) return res.json({ ok: false, error: 'AIRTABLE_API_KEY missing', sellers: [] });
  try {
    const sellers = [];
    let offset = '';
    while (true) {
      const u = new URL(`https://api.airtable.com/v0/${BASE_ID}/fo_tracker`);
      if (offset) u.searchParams.set('offset', offset);
      const r = await fetch(u.toString(), { headers: { Authorization: `Bearer ${AKEY}` } });
      if (!r.ok) throw new Error(`Airtable ${r.status}`);
      const d = await r.json();
      for (const rec of d.records || []) {
        const f = rec.fields || {};
        if (f.Signal === 'SELLING') {
          sellers.push({
            symbol: f.Symbol,
            fii_change_q: f.FII_Change_Q ?? null,
            dii_change_q: f.DII_Change_Q ?? null,
            promoter_change_q: f.Promoter_Change_Q ?? null,
            price: f.Price ?? null,
            updated: f.Last_Updated ?? null,
          });
        }
      }
      offset = d.offset || '';
      if (!offset) break;
    }
    sellers.sort((a, b) => {
      const aa = Math.min(a.fii_change_q ?? 0, a.dii_change_q ?? 0);
      const bb = Math.min(b.fii_change_q ?? 0, b.dii_change_q ?? 0);
      return aa - bb;
    });
    res.json({ ok: true, count: sellers.length, sellers });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message, sellers: [] });
  }
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

/* ── Shared refresh runners ── */
function runRefresh(cb) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const script = path.join(__dirname, '..', 'scripts', 'enhance_math.py');
  execFile(py, [script], { cwd: path.join(__dirname, '..'), timeout: 300000 },
    (err, stdout, stderr) => cb(err, (stdout + stderr).trim().split('\n').pop()));
}

function runInstitutionalRefresh(cb) {
  if (!process.env.AIRTABLE_API_KEY) {
    return cb(new Error('AIRTABLE_API_KEY missing; institutional cron skipped'));
  }
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const script = path.join(__dirname, '..', 'scripts', 'refresh_fo_institutional.py');
  execFile(py, [script], {
      cwd: path.join(__dirname, '..'),
      timeout: 1200000,
      env: process.env,
    },
    (err, stdout, stderr) => cb(err, (stdout + '\n' + stderr).trim().split('\n').slice(-3).join('\n')));
}

/* ── Daily cron 06:30 IST = 01:00 UTC ── */
cron.schedule('0 1 * * *', () => {
  console.log('[cron] daily S/R refresh starting…');
  runRefresh((err, out) => {
    if (err) console.error('[cron] S/R failed:', err.message);
    else console.log('[cron] S/R done:', out);
  });
});

/* ── Daily institutional refresh 08:00 IST = 02:30 UTC ── */
cron.schedule('30 2 * * *', () => {
  console.log('[cron] daily F&O institutional refresh starting…');
  runInstitutionalRefresh((err, out) => {
    if (err) console.error('[cron] F&O institutional failed:', err.message);
    else console.log('[cron] F&O institutional done:', out);
  });
});

app.listen(port, () => {
  console.log(`NSE Value Lens running on http://localhost:${port}`);
});
