'use strict';

const path = require('path');
const express = require('express');
const { marked } = require('marked');
const { analyzeSymbol } = require('./analyzer');
const { getNifty200Constituents } = require('./adapters');

const app = express();
const port = process.env.PORT || 3000;

app.use(express.json({ limit: '256kb' }));
app.use(express.static(path.join(__dirname, '..', 'public')));

app.get('/health', (_req, res) => {
  res.json({ ok: true, name: 'nse-value-lens' });
});

app.get('/api/constituents', async (_req, res) => {
  try {
    const rows = await getNifty200Constituents();
    res.json({ ok: true, count: rows.length, rows });
  } catch (err) {
    res.status(502).json({ ok: false, error: err.message });
  }
});

app.post('/api/analyze', async (req, res) => {
  const symbol = String(req.body?.symbol || '').trim().toUpperCase();
  if (!symbol) return res.status(400).json({ ok: false, error: 'symbol is required' });
  const manual = req.body?.manual && typeof req.body.manual === 'object' ? req.body.manual : {};
  try {
    const result = await analyzeSymbol(symbol, manual);
    res.json({
      ok: true,
      symbol,
      markdown: result.markdown,
      html: marked.parse(result.markdown),
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
