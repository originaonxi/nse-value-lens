'use strict';

const path = require('path');
const express = require('express');
const { marked } = require('marked');
const sanitizeHtml = require('sanitize-html');
const { analyzeSymbol, BUDGET_THEMES, getShortlist } = require('./analyzer');
const { getNifty200Constituents } = require('./adapters');
const fs = require('fs');

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
app.use(express.static(path.join(__dirname, '..', 'public')));

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

app.listen(port, () => {
  console.log(`NSE Value Lens running on http://localhost:${port}`);
});
