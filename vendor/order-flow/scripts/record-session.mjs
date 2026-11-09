#!/usr/bin/env node
/**
 * Record real sessions from a provider, so the "recorded" provider can replay them.
 *
 *   MF_PROVIDER=upstox UPSTOX_ACCESS_TOKEN=... npm run record -- 2026-10-29 2026-10-30
 *   npm run record -- --provider-file ./my-broker.mjs 2026-10-30
 *
 * Writes data/recorded/<date>.json.gz per session:
 *   { schema: 1, date, recordedAt, source, note,
 *     chains:  { SYMBOL: { ladder: [expiries…], chain: OptionChain } },
 *     futures: { SYMBOL: FuturesMonth[] } }
 *
 * Futures are read for each session asked. Option chains can only be read as
 * they are now (brokers keep no history of chains), so every session in one
 * run carries the same chain snapshot; the recorded provider rescales its spot
 * to each minute of the futures. Record on the day for an exact chain.
 *
 * `--provider-file` loads a module exporting a provider factory (any export
 * whose name starts with "create"), for a source you do not want to register.
 */
import fs from 'node:fs';
import path from 'node:path';
import { gzipSync } from 'node:zlib';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createProvider } from '../server/providers/index.mjs';
import { filterLiveExpiries } from '../src/lib/marketSession.ts';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUT = path.join(ROOT, 'data/recorded');
const WORKERS = 4;

const args = process.argv.slice(2);
const fileAt = args.indexOf('--provider-file');
const providerFile = fileAt >= 0 ? args[fileAt + 1] : null;
const sourceAt = args.indexOf('--source');
const optionValues = new Set([fileAt, sourceAt].filter(i => i >= 0).map(i => i + 1));
const sessions = args.filter((a, i) => /^\d{4}-\d{2}-\d{2}$/.test(a) && !optionValues.has(i));
if (!sessions.length) {
  console.error('Usage: npm run record -- [--provider-file file.mjs] [--source "label"] YYYY-MM-DD [YYYY-MM-DD …]');
  process.exit(1);
}

const universe = JSON.parse(fs.readFileSync(path.join(ROOT, 'public/underlyings.json'), 'utf8')).underlyings;
let provider;
if (providerFile) {
  const mod = await import(pathToFileURL(path.resolve(providerFile)).href);
  const create = Object.entries(mod).find(([name, value]) => name.startsWith('create') && typeof value === 'function')?.[1];
  if (!create) throw new Error(`${providerFile} exports no create…Provider function.`);
  provider = create(universe);
} else {
  provider = createProvider(universe);
}
const source = sourceAt >= 0 ? args[sourceAt + 1] : provider.label;
await provider.init?.();

async function pool(items, work) {
  let cursor = 0;
  let done = 0;
  await Promise.all(Array.from({ length: WORKERS }, async () => {
    while (cursor < items.length) {
      const item = items[cursor++];
      await work(item);
      done += 1;
      if (done % 25 === 0 || done === items.length) process.stdout.write(`  ${done}/${items.length}\r`);
    }
  }));
  process.stdout.write('\n');
}

// One chain snapshot, now, at each underlying's nearest expiry live on the earliest session asked.
console.log(`Recording ${sessions.join(', ')} from ${source}: option chains…`);
const first = [...sessions].sort()[0];
const chains = {};
const failed = [];
await pool(universe, async u => {
  try {
    const ladder = await provider.expiries(u);
    const live = filterLiveExpiries(ladder, Date.parse(`${first}T10:00:00+05:30`));
    if (!live[0]) return;
    const chain = await provider.optionChain(u, live[0]);
    if (chain?.spot > 0 && chain.strikes?.length) chains[u.symbol] = { ladder, chain: { ...chain, expiry: chain.expiry || live[0] } };
  } catch (error) {
    failed.push(`${u.symbol} chain: ${error.message}`);
  }
});

fs.mkdirSync(OUT, { recursive: true });
for (const session of sessions) {
  console.log(`${session}: futures…`);
  const futures = {};
  await pool(universe, async u => {
    try {
      const months = await provider.futures(u, session);
      if (months?.length && months[0].candles?.length) futures[u.symbol] = months;
    } catch (error) {
      failed.push(`${u.symbol} futures ${session}: ${error.message}`);
    }
  });
  const file = path.join(OUT, `${session}.json.gz`);
  const body = {
    schema: 1, date: session, recordedAt: new Date().toISOString(), source,
    note: 'Futures: the session\'s own 1-minute candles. Option chains: one snapshot taken at recording time, shared by every session recorded in the same run.',
    chains, futures,
  };
  fs.writeFileSync(file, gzipSync(JSON.stringify(body), { level: 9 }));
  console.log(`  wrote ${path.relative(ROOT, file)}: ${Object.keys(chains).length} chains, ${Object.keys(futures).length} futures, ${(fs.statSync(file).size / 1024).toFixed(0)} KB`);
}
if (failed.length) console.log(`${failed.length} reads failed, e.g.\n  ${failed.slice(0, 8).join('\n  ')}`);
