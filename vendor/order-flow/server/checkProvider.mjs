#!/usr/bin/env node
/**
 * `npm run check:provider`: asks the configured provider (MF_PROVIDER) for a
 * few underlyings and checks every answer against the contract in
 * server/providers/types.mjs. Run it after wiring a broker; fix what it says.
 *
 *   MF_PROVIDER=upstox UPSTOX_ACCESS_TOKEN=... npm run check:provider
 *   npm run check:provider -- RELIANCE TCS     (just these symbols)
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { encodeSeries } from './marketFile.mjs';
import { createProvider } from './providers/index.mjs';
import { filterLiveExpiries, getLatestTradingSessionDate } from '../src/lib/marketSession.ts';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const universe = JSON.parse(fs.readFileSync(path.join(ROOT, 'public/underlyings.json'), 'utf8')).underlyings;
const asked = process.argv.slice(2).map(s => s.toUpperCase());
const sample = (asked.length ? universe.filter(u => asked.includes(u.symbol)) : universe.filter(u => ['NIFTY', 'BANKNIFTY', 'RELIANCE', 'HDFCBANK', 'TCS'].includes(u.symbol)));

const problems = [];
const ok = [];
const fail = (symbol, what) => problems.push(`${symbol}: ${what}`);
const DATE = /^\d{4}-\d{2}-\d{2}$/;

const provider = createProvider(universe);
console.log(`Checking provider "${provider.id}" (${provider.label}) on ${sample.map(u => u.symbol).join(', ')}\n`);
await provider.init?.();
const clock = provider.now ? provider.now() : Date.now();
const session = getLatestTradingSessionDate(new Date(clock));

for (const u of sample) {
  try {
    const expiries = await provider.expiries(u);
    if (!Array.isArray(expiries) || !expiries.length) { fail(u.symbol, 'expiries() returned none'); continue; }
    if (!expiries.every(d => DATE.test(d))) fail(u.symbol, `expiries must be YYYY-MM-DD, got ${expiries.slice(0, 3).join(', ')}`);
    if ([...expiries].sort().join() !== expiries.join()) fail(u.symbol, 'expiries must be ascending');
    const live = filterLiveExpiries(expiries, clock);
    if (!live.length) { fail(u.symbol, 'no live expiry today or later'); continue; }

    const chain = await provider.optionChain(u, live[0]);
    if (!(chain.spot > 0)) fail(u.symbol, 'optionChain().spot must be a positive rupee price');
    if (chain.prevClose == null) fail(u.symbol, 'optionChain().prevClose is missing: the board cannot measure a spot move without it');
    else if (Math.abs(chain.spot / chain.prevClose - 1) > 0.25) fail(u.symbol, `spot ${chain.spot} vs prevClose ${chain.prevClose}: more than 25% apart, check units (paise vs rupees)`);
    if (!chain.strikes?.length) fail(u.symbol, 'optionChain().strikes is empty');
    const withOi = chain.strikes.filter(s => (s.call?.oi ?? 0) > 0 || (s.put?.oi ?? 0) > 0).length;
    if (withOi < 3) fail(u.symbol, `only ${withOi} strikes carry open interest`);
    const near = chain.strikes.map(s => s.strike).filter(k => Math.abs(k / chain.spot - 1) < 0.2).length;
    if (near < 3) fail(u.symbol, 'fewer than 3 strikes within 20% of spot: check strike units');
    if (!encodeSeries(u, { ...chain, expiry: live[0] }, clock)) fail(u.symbol, 'the chain does not encode into the market file');

    const months = await provider.futures(u, session);
    if (!Array.isArray(months)) { fail(u.symbol, 'futures() must return an array'); continue; }
    if (!months.length) { ok.push(`${u.symbol}: no futures listed (fine for a few indices)`); continue; }
    const near1 = months[0];
    if (!DATE.test(near1.date)) fail(u.symbol, 'futures month date must be YYYY-MM-DD');
    if (near1.prevClose == null) fail(u.symbol, 'futures prevClose is missing: the day move cannot be measured');
    const c = near1.candles ?? [];
    if (c.some((x, i) => i && x.at <= c[i - 1].at)) fail(u.symbol, 'futures candles must be ascending by `at`');
    if (c.length && new Date(c[0].at).toISOString().slice(11, 16) !== '03:45') ok.push(`${u.symbol}: first candle starts ${new Date(c[0].at + 330 * 60_000).toISOString().slice(11, 16)} IST (09:15 expected at the open)`);
    if (c.length && near1.prevClose && Math.abs(c.at(-1).close / near1.prevClose - 1) > 0.25) fail(u.symbol, 'futures close vs prevClose more than 25% apart: check units');
    ok.push(`${u.symbol}: ${expiries.length} expiries, ${chain.strikes.length} strikes, spot ${chain.spot}, ${months.length} futures months, ${c.length} candles`);
  } catch (error) {
    fail(u.symbol, `threw: ${error?.message || error}`);
  }
}

for (const line of ok) console.log(`  ok   ${line}`);
for (const line of problems) console.log(`  FIX  ${line}`);
console.log(problems.length ? `\n${problems.length} problem(s).` : '\nAll checks passed.');
process.exit(problems.length ? 1 : 0);
