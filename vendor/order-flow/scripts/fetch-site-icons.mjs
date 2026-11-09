#!/usr/bin/env node
/**
 * Site icons for the underlyings Commons has no mark for.
 *
 * fetch-underlying-logos.mjs prefers a Commons logo and falls back to the
 * issuer's site icon only when Wikidata records the website. For the rest,
 * OFFICIAL_SITE below names each issuer's own website, checked by hand, and
 * this fetches that site's 128px icon: the issuer's own artwork, shown to
 * identify the instrument being quoted (nominative use, never endorsement).
 *
 *   node scripts/fetch-site-icons.mjs            every symbol below not in the manifest
 *   node scripts/fetch-site-icons.mjs DABUR SRF  just these (replacing what is held)
 *
 * Review the result before shipping it: a site may serve a generic icon.
 * Left out after review (the icon was wrong or not clearly the issuer's, so
 * the monogram stands): AMBER, ASTRAL, COLPAL, DMART, KALYANKJIL, KAYNES,
 * LODHA, MFSL, POWERINDIA, PRESTIGE, RADICO, SONACOMS.
 */
import { readFile, rm, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT_DIR = join(ROOT, 'public/brand/underlyings');
const UA = 'OrderFlowLogoFetch/1.0 (+https://github.com/MrChartist/order-flow) node-fetch';

export const OFFICIAL_SITE = {
  '360ONE': '360.one', ABB: 'abb.com', ANGELONE: 'angelone.in', APLAPOLLO: 'aplapollo.com',
  APOLLOHOSP: 'apollohospitals.com', BAJAJHLDNG: 'bhil.in', BLUESTARCO: 'bluestarindia.com', BPCL: 'bharatpetroleum.in',
  CGPOWER: 'cgglobal.com', CONCOR: 'concorindia.co.in', CUMMINSIND: 'cumminsindia.com', DABUR: 'dabur.com', DIXON: 'dixoninfo.com',
  GAIL: 'gailonline.com', GMRAIRPORT: 'gmrgroup.in', 'GVT&D': 'gevernova.com', HAVELLS: 'havells.com',
  HDFCAMC: 'hdfcfund.com', HDFCLIFE: 'hdfclife.com', HINDPETRO: 'hindustanpetroleum.com', INDHOTEL: 'ihcltata.com', INDIGO: 'goindigo.in',
  INOXWIND: 'inoxwind.com', IREDA: 'ireda.in', JIOFIN: 'jfs.in',
  KEI: 'kei-ind.com', KFINTECH: 'kfintech.com', LICI: 'licindia.in', LTF: 'ltfs.com',
  LTM: 'ltimindtree.com', MANAPPURAM: 'manappuram.com', MARICO: 'marico.com', MAXHEALTH: 'maxhealthcare.in',
  MOTILALOFS: 'motilaloswal.com', 'NAM-INDIA': 'nipponindiaim.com', NATIONALUM: 'nalcoindia.com', NBCC: 'nbccindia.in', NESTLEIND: 'nestle.in',
  NMDC: 'nmdc.co.in', NYKAA: 'nykaa.com', OFSS: 'oracle.com', PATANJALI: 'patanjalifoods.com', PAYTM: 'paytm.com',
  PGEL: 'pgel.in', PIIND: 'piindustries.com', POLICYBZR: 'policybazaar.com', POWERGRID: 'powergrid.in',
  PREMIERENE: 'premierenergies.com', RECLTD: 'recindia.nic.in', SBICARD: 'sbicard.com',
  SBILIFE: 'sbilife.co.in', SOLARINDS: 'solargroup.com', SRF: 'srf.com', SUNPHARMA: 'sunpharma.com',
  TATAPOWER: 'tatapower.com', TIINDIA: 'tiindia.com', TRENT: 'trentlimited.com', UNOMINDA: 'unominda.com', UPL: 'upl-ltd.com',
  WAAREEENER: 'waaree.com',
};

async function icon(symbol, host) {
  const sources = [
    { url: `https://www.google.com/s2/favicons?sz=128&domain=${host}`, min: 700 },
    { url: `https://icons.duckduckgo.com/ip3/${host}.ico`, min: 400 },
  ];
  let last = 'no source';
  for (const source of sources) {
    try {
      const response = await fetch(source.url, { headers: { 'User-Agent': UA }, redirect: 'follow' });
      if (!response.ok) { last = `icon ${response.status}`; continue; }
      const bytes = Buffer.from(await response.arrayBuffer());
      if (bytes.length < source.min) { last = `icon too small (${bytes.length}B)`; continue; }
      const type = response.headers.get('content-type') ?? '';
      const ext = type.includes('png') ? 'png' : type.includes('svg') ? 'svg' : 'ico';
      await writeFile(join(OUT_DIR, `${symbol}.${ext}`), bytes);
      return `${symbol}.${ext}`;
    } catch (error) { last = error.message; }
  }
  throw new Error(last);
}

const manifestPath = join(OUT_DIR, 'manifest.json');
const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
const names = Object.fromEntries(JSON.parse(await readFile(join(ROOT, 'public/underlyings.json'), 'utf8')).underlyings.map(u => [u.symbol, u]));
const asked = process.argv.slice(2).filter(arg => /^[A-Z0-9&-]+$/.test(arg));
const todo = asked.length ? asked : Object.keys(OFFICIAL_SITE).filter(symbol => !manifest[symbol]);
const missed = [];
for (const symbol of todo) {
  const host = OFFICIAL_SITE[symbol];
  if (!host) { missed.push(`${symbol}: no site listed`); continue; }
  try {
    if (manifest[symbol]) await rm(join(OUT_DIR, manifest[symbol].file), { force: true });
    const file = await icon(symbol, host);
    manifest[symbol] = { file, name: names[symbol]?.name ?? symbol, kind: names[symbol]?.kind ?? 'stock', source: `https://${host}`, via: 'site-icon' };
    console.log(`ok   ${symbol.padEnd(12)} ${file.padEnd(18)} ← ${host}`);
  } catch (error) {
    missed.push(`${symbol}: ${error.message}`);
    console.log(`miss ${symbol.padEnd(12)} ${error.message}`);
  }
}
await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`${todo.length - missed.length} saved, ${missed.length} missed; manifest holds ${Object.keys(manifest).length}`);
