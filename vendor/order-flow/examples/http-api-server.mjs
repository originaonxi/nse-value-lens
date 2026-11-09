#!/usr/bin/env node
/**
 * A reference API for the `http` provider: the three routes Order Flow asks
 * for, in Order Flow's own shapes, served from a session on disk (the newest
 * file in data/archive or data/recorded). Use it to see exactly what your API
 * should answer, or as a starting point for a bridge in front of your broker.
 *
 *   node examples/http-api-server.mjs              # http://127.0.0.1:9000
 *   MF_PROVIDER=http MF_HTTP_BASE_URL=http://127.0.0.1:9000 npm run dev
 *
 *   GET /expiries/:symbol                    → ["2026-11-09", "2026-11-16", …]
 *   GET /chain/:symbol?expiry=YYYY-MM-DD     → { expiry, at, spot, prevClose, atm, strikes: [{ strike, call, put }] }
 *   GET /futures/:symbol?session=YYYY-MM-DD  → [{ date, prevClose, prevOi, candles: [{ at, close, oi }] }]
 */
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { gunzipSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PORT = Number(process.env.PORT || 9000);

const files = ['data/archive', 'data/recorded'].flatMap(dir => {
  const full = path.join(ROOT, dir);
  return fs.existsSync(full) ? fs.readdirSync(full).filter(f => /^\d{4}-\d{2}-\d{2}\.json\.gz$/.test(f)).map(f => path.join(full, f)) : [];
}).sort((a, b) => path.basename(a).localeCompare(path.basename(b)));
if (!files.length) { console.error('No session on disk: run `npm run fetch:nse` first.'); process.exit(1); }
const day = JSON.parse(gunzipSync(fs.readFileSync(files.at(-1))).toString('utf8'));

const send = (res, status, body) => {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
};

http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const [, route, raw] = url.pathname.split('/');
  const symbol = decodeURIComponent(raw || '').toUpperCase();
  if (route === 'expiries') return send(res, 200, day.chains[symbol]?.ladder ?? []);
  if (route === 'chain') {
    const held = day.chains[symbol];
    return held ? send(res, 200, held.chain) : send(res, 404, { error: `${symbol} not found` });
  }
  if (route === 'futures') {
    const session = url.searchParams.get('session');
    return send(res, 200, !session || session === day.date ? day.futures[symbol] ?? [] : []);
  }
  send(res, 404, { error: 'Routes: /expiries/:symbol, /chain/:symbol?expiry=, /futures/:symbol?session=' });
}).listen(PORT, '127.0.0.1', () => console.log(`Reference API for ${day.date} on http://127.0.0.1:${PORT}`));
