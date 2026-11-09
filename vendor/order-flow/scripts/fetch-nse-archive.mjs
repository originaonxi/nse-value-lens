#!/usr/bin/env node
/**
 * Build a replayable session from the exchanges' public F&O archives (no keys).
 *
 *   npm run fetch:nse                     # the latest session the archive has
 *   npm run fetch:nse -- 2026-11-06       # one or more sessions
 *   npm run dev:archive                   # replay the newest one live
 *
 * The flow, step by step:
 *
 *   1. Download   NSE's F&O bhavcopy (UDiFF CSV) for the session and for the
 *                 session before it; BSE's for SENSEX, BANKEX and the other
 *                 BSE contracts. Files are cached in data/archive/.cache.
 *   2. Parse      one row per contract: futures (IDF/STF) and options (IDO/STO),
 *                 with open, high, low, close, previous close, open interest,
 *                 change in OI, volume (contracts) and lot size.
 *   3. Chains     each underlying's nearest live expiry: every strike's call and
 *                 put, with real closing OI, previous OI (OI minus its change),
 *                 premiums and volume in units. Spot is the exchange's
 *                 underlying price; its previous close comes from the session
 *                 before.
 *   4. Futures    the nearest three months with their real previous close and
 *                 previous OI. A bhavcopy is end of day, so the 1-minute path
 *                 is rebuilt: it opens at the real open, touches the real high
 *                 and low, and closes at the real close, with a market-wide
 *                 component shared by every name so the board moves as one
 *                 market. Open interest moves from the previous OI to the real
 *                 closing OI. Deterministic: the same file on every machine.
 *   5. Write      data/archive/<date>.json.gz, in the recorded-session format
 *                 (server/providers/recorded.mjs), marked kind: "archive".
 *
 * Every closing figure on the board is the exchange's own; only the shape of
 * the path between the open and the close is rebuilt.
 */
import fs from 'node:fs';
import path from 'node:path';
import { gzipSync, inflateRawSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';
import { filterLiveExpiries, getLatestTradingSessionDate } from '../src/lib/marketSession.ts';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUT = path.resolve(ROOT, process.env.MF_ARCHIVE_DIR || 'data/archive');
const CACHE = path.join(OUT, '.cache');
const MINUTE = 60_000;
const SESSION_MINUTES = 375;
const UA = 'Mozilla/5.0 (Order Flow archive reader; +https://github.com/MrChartist/order-flow)';

const compact = date => date.replaceAll('-', '');
const SOURCES = {
  NSE: date => `https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_${compact(date)}_F_0000.csv.zip`,
  BSE: date => `https://www.bseindia.com/download/Bhavcopy/Derivative/BhavCopy_BSE_FO_0_0_0_${compact(date)}_F_0000.CSV`,
};

// ── 1. Download ─────────────────────────────────────────────────────────────

/** The first file in a ZIP, without a dependency (stored or deflated). */
export function unzipFirst(buffer) {
  if (buffer.readUInt32LE(0) !== 0x04034b50) return buffer; // not a zip: already the CSV
  const method = buffer.readUInt16LE(8);
  let size = buffer.readUInt32LE(18);
  const start = 30 + buffer.readUInt16LE(26) + buffer.readUInt16LE(28);
  if (!size) {
    // A streamed entry stores its size after the data: read it from the central directory.
    const central = buffer.indexOf(Buffer.from([0x50, 0x4b, 0x01, 0x02]), start);
    if (central > 0) size = buffer.readUInt32LE(central + 20);
  }
  const body = buffer.subarray(start, start + size);
  return method === 0 ? body : inflateRawSync(body);
}

async function download(exch, date) {
  const file = path.join(CACHE, `${exch}-${date}.csv`);
  if (fs.existsSync(file)) return fs.readFileSync(file, 'utf8');
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const response = await fetch(SOURCES[exch](date), { headers: { 'User-Agent': UA, Accept: '*/*' } });
      if (response.status === 404) return null; // a holiday or not published yet
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const text = unzipFirst(Buffer.from(await response.arrayBuffer())).toString('utf8');
      if (!text.startsWith('TradDt')) return null; // an error page, not a bhavcopy
      fs.mkdirSync(CACHE, { recursive: true });
      fs.writeFileSync(file, text);
      return text;
    } catch (error) {
      if (attempt === 3) throw new Error(`${exch} ${date}: ${error.message}`);
      await new Promise(resolve => setTimeout(resolve, 1000 * 2 ** attempt));
    }
  }
  return null;
}

// ── 2. Parse ────────────────────────────────────────────────────────────────

const num = value => {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
};

/** UDiFF bhavcopy rows → contracts. */
export function parseBhavcopy(text) {
  const lines = text.trim().split(/\r?\n/);
  const head = lines[0].split(',');
  const col = name => head.indexOf(name);
  const c = {
    type: col('FinInstrmTp'), symbol: col('TckrSymb'), expiry: col('XpryDt'), strike: col('StrkPric'), side: col('OptnTp'),
    open: col('OpnPric'), high: col('HghPric'), low: col('LwPric'), close: col('ClsPric'), last: col('LastPric'),
    prevClose: col('PrvsClsgPric'), spot: col('UndrlygPric'), oi: col('OpnIntrst'), oiChange: col('ChngInOpnIntrst'),
    volume: col('TtlTradgVol'), value: col('TtlTrfVal'), lot: col('NewBrdLotQty'),
  };
  return lines.slice(1).map(line => {
    const f = line.split(',');
    return {
      type: f[c.type], symbol: f[c.symbol], expiry: f[c.expiry], strike: num(f[c.strike]), side: f[c.side],
      open: num(f[c.open]), high: num(f[c.high]), low: num(f[c.low]), close: num(f[c.close]) || num(f[c.last]),
      prevClose: num(f[c.prevClose]), spot: num(f[c.spot]), oi: num(f[c.oi]), oiChange: num(f[c.oiChange]),
      volume: num(f[c.volume]), value: num(f[c.value]), lot: num(f[c.lot]) || 1,
    };
  }).filter(r => r.symbol && r.expiry);
}

// ── 4. The rebuilt 1-minute path ────────────────────────────────────────────

function seeded(text) {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return () => {
    h = Math.imul(h ^ (h >>> 15), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    return ((h ^= h >>> 16) >>> 0) / 4294967296;
  };
}
const gaussOf = random => () => Math.sqrt(-2 * Math.log(Math.max(1e-12, random()))) * Math.cos(2 * Math.PI * random());
const round2 = v => Math.round(v * 100) / 100;

/** A unit random walk of `n` steps (the market-wide component, shared by every name in a session). */
export function marketWalk(date, n = SESSION_MINUTES) {
  const gauss = gaussOf(seeded(`market:${date}`));
  const walk = [0];
  for (let i = 1; i < n; i++) walk.push(walk[i - 1] + gauss());
  return walk;
}

/**
 * A 1-minute close path that opens at `open`, reaches `high` and `low` once
 * each and closes at `close`. Between those anchors it is a Brownian bridge
 * mixing the shared market walk with the name's own noise, kept inside the
 * day's range.
 */
export function rebuildPath({ open, high, low, close }, seed, market, n = SESSION_MINUTES) {
  if (!(open > 0 && high > 0 && low > 0 && close > 0) || high < low) return Array(n).fill(close || open || 0);
  const random = seeded(seed);
  const gauss = gaussOf(random);
  const last = n - 1;
  // The high and the low each land once, at least an hour apart and away from
  // the open and close, so the path never leaps the day's range in a minute.
  const GAP = 60;
  const EDGE = 15;
  const pick = (from, to) => from + Math.floor(random() * Math.max(1, to - from));
  let tHigh = high === open ? 0 : high === close ? last : null;
  let tLow = low === open ? 0 : low === close ? last : null;
  // An up day tends to make its low first and its high later; a down day the reverse.
  const lowFirst = close >= open ? random() < 0.75 : random() < 0.25;
  if (tHigh == null && tLow == null) {
    const first = pick(EDGE, last - EDGE - GAP);
    const second = pick(first + GAP, last - EDGE);
    [tLow, tHigh] = lowFirst ? [first, second] : [second, first];
  } else if (tHigh == null) {
    tHigh = tLow === 0 ? pick(GAP, last - EDGE) : pick(EDGE, last - GAP);
  } else if (tLow == null) {
    tLow = tHigh === 0 ? pick(GAP, last - EDGE) : pick(EDGE, last - GAP);
  }
  if (tHigh === tLow) tLow = Math.min(last, tLow + GAP);

  const anchors = new Map([[0, open], [last, close]]);
  anchors.set(tHigh, high);
  anchors.set(tLow, low);
  const points = [...anchors.entries()].sort((a, b) => a[0] - b[0]);

  const own = [0];
  for (let i = 1; i < n; i++) own.push(own[i - 1] + gauss());
  const mix = market.map((m, i) => 0.65 * m + 0.75 * own[i]);
  const range = high - low;
  const path = Array(n);
  for (let k = 0; k < points.length - 1; k++) {
    const [t0, v0] = points[k];
    const [t1, v1] = points[k + 1];
    const span = Math.max(1, t1 - t0);
    // Scale the noise so a segment wanders about a quarter of the day's range.
    const scale = (range * 0.25) / Math.sqrt(span + 30);
    for (let t = t0; t <= t1; t++) {
      const f = (t - t0) / span;
      const bridge = (mix[t] - mix[t0]) - f * (mix[t1] - mix[t0]);
      path[t] = v0 + (v1 - v0) * f + bridge * scale * Math.sin(Math.PI * f) ** 0.5;
    }
  }
  // Keep inside the day's range by folding back from an edge (a clamp would flat-line along it).
  const fold = v => {
    if (v > high) v = high - (v - high) * 0.6;
    if (v < low) v = low + (low - v) * 0.6;
    return Math.min(high, Math.max(low, v));
  };
  return path.map((v, t) => (anchors.has(t) ? anchors.get(t) : round2(fold(v))));
}

/** Open interest from the previous close to the real closing OI, mostly in the first hours, in whole lots. */
export function rebuildOi(prevOi, oi, lot, seed, n = SESSION_MINUTES) {
  const gauss = gaussOf(seeded(`oi:${seed}`));
  const step = Math.max(1, lot);
  const out = [];
  let wobble = 0;
  for (let t = 0; t < n; t++) {
    const f = t / (n - 1);
    const eased = 1 - (1 - f) ** 1.6;
    wobble = wobble * 0.9 + gauss() * 0.004;
    const v = prevOi + (oi - prevOi) * eased + (t === n - 1 ? 0 : wobble * Math.abs(oi - prevOi));
    out.push(t === n - 1 ? oi : Math.max(0, Math.round(v / step) * step));
  }
  return out;
}

// ── 3–5. Build one session ──────────────────────────────────────────────────

/**
 * Traded quantity in units. NSE reports contracts and BSE reports units, so
 * read it off the turnover: an option's turnover is (strike + premium) x units,
 * a future's is price x units.
 */
export function unitsTraded(r) {
  if (!(r.volume > 0)) return 0;
  const price = (r.side === 'CE' || r.side === 'PE') ? r.strike + r.close : r.close;
  if (!(r.value > 0 && price > 0)) return r.volume * r.lot;
  const perVolume = r.value / (r.volume * price);
  return perVolume > Math.max(1.5, r.lot / 2) ? r.volume * r.lot : r.volume;
}

function optionLeg(r) {
  const units = unitsTraded(r);
  const ltp = r.close;
  const avg = units > 0 && r.value > 0 ? round2(r.value / units - r.strike) : 0;
  return {
    ltp,
    prevClose: r.prevClose || null,
    oi: r.oi,
    prevOi: Math.max(0, r.oi - r.oiChange),
    volume: units,
    prevVolume: null,
    avgPrice: avg > 0 ? avg : ltp,
    iv: null,
    bid: ltp, ask: ltp, bidQty: 0, askQty: 0,
    dayHigh: r.high || null,
    dayLow: r.low || null,
    lastTradeAt: null,
    delta: null,
  };
}

/** The strikes around spot (the board reads support, resistance and the zone from these), ascending. */
const STRIKES_EACH_SIDE = 30;
function nearestStrikes(rows, spot) {
  const sorted = rows.sort((a, b) => a.strike - b.strike);
  const at = sorted.reduce((best, row, i) => (Math.abs(row.strike - spot) < Math.abs(sorted[best].strike - spot) ? i : best), 0);
  return sorted.slice(Math.max(0, at - STRIKES_EACH_SIDE), at + STRIKES_EACH_SIDE + 1);
}

export function buildSession(date, rowsByExch, prevRowsByExch, universe) {
  const open = Date.parse(`${date}T09:15:00+05:30`);
  const market = marketWalk(date);
  const chains = {};
  const futures = {};
  const missing = [];

  for (const u of universe) {
    const rows = (rowsByExch[u.exch] ?? []).filter(r => r.symbol === u.symbol);
    if (!rows.length) { missing.push(u.symbol); continue; }
    const options = rows.filter(r => r.type === 'IDO' || r.type === 'STO');
    const futs = rows.filter(r => r.type === 'IDF' || r.type === 'STF').filter(r => r.expiry >= date).sort((a, b) => a.expiry.localeCompare(b.expiry));

    const ladder = [...new Set(options.map(r => r.expiry))].filter(e => e >= date).sort();
    const live = filterLiveExpiries(ladder, Date.parse(`${date}T10:00:00+05:30`));
    if (live[0]) {
      const legs = options.filter(r => r.expiry === live[0]);
      const byStrike = new Map();
      for (const r of legs) {
        const row = byStrike.get(r.strike) ?? { strike: r.strike };
        row[r.side === 'CE' ? 'call' : 'put'] = optionLeg(r);
        byStrike.set(r.strike, row);
      }
      const spot = legs.find(r => r.spot > 0)?.spot ?? futs[0]?.close ?? 0;
      // The previous close of the underlying: from the session before, else read off the near future's own move.
      const near = futs[0];
      const prevSpot = (prevRowsByExch[u.exch] ?? []).find(r => r.symbol === u.symbol && r.spot > 0)?.spot
        ?? (near?.close > 0 && near.prevClose > 0 ? round2(spot * near.prevClose / near.close) : null);
      if (spot > 0 && byStrike.size) {
        chains[u.symbol] = {
          ladder,
          chain: { expiry: live[0], at: open + SESSION_MINUTES * MINUTE, spot, prevClose: prevSpot, atm: null, strikes: nearestStrikes([...byStrike.values()], spot) },
        };
      }
    }

    const months = futs.slice(0, 3).map(r => {
      const closes = rebuildPath(r, `${date}:${u.symbol}:${r.expiry}`, market);
      const ois = rebuildOi(Math.max(0, r.oi - r.oiChange), r.oi, r.lot, `${date}:${u.symbol}:${r.expiry}`);
      return {
        date: r.expiry,
        prevClose: r.prevClose || null,
        prevOi: Math.max(0, r.oi - r.oiChange),
        candles: closes.map((close, i) => ({ at: open + i * MINUTE, close, oi: ois[i] })),
      };
    });
    if (months.length && months[0].candles.length) futures[u.symbol] = months;
  }
  return { chains, futures, missing };
}

// ── Command line ────────────────────────────────────────────────────────────

const previousWeekday = date => {
  const d = new Date(`${date}T00:00:00Z`);
  do d.setUTCDate(d.getUTCDate() - 1); while (d.getUTCDay() === 0 || d.getUTCDay() === 6);
  return d.toISOString().slice(0, 10);
};

async function bhavcopies(date) {
  const out = {};
  for (const exch of Object.keys(SOURCES)) {
    try {
      const text = await download(exch, date);
      if (text) out[exch] = parseBhavcopy(text);
    } catch (error) {
      console.warn(`  ${error.message}`);
    }
  }
  return out;
}

/** The session before `date` that the archive has (skips holidays). */
async function previousSession(date) {
  let d = date;
  for (let i = 0; i < 5; i++) {
    d = previousWeekday(d);
    const rows = await bhavcopies(d);
    if (rows.NSE) return { date: d, rows };
  }
  return { date: null, rows: {} };
}

async function main() {
  const asked = process.argv.slice(2).filter(a => /^\d{4}-\d{2}-\d{2}$/.test(a));
  const universe = JSON.parse(fs.readFileSync(path.join(ROOT, 'public/underlyings.json'), 'utf8')).underlyings;
  let sessions = asked;
  if (!sessions.length) {
    // The latest session the archive has published (today's appears after the close).
    let d = getLatestTradingSessionDate(new Date());
    for (let i = 0; i < 10 && !(await bhavcopies(d)).NSE; i++) d = previousWeekday(d);
    sessions = [d];
  }
  fs.mkdirSync(OUT, { recursive: true });
  for (const date of sessions) {
    console.log(`${date}: downloading the NSE and BSE F&O bhavcopies…`);
    const rows = await bhavcopies(date);
    if (!rows.NSE) { console.error(`  no NSE bhavcopy for ${date} (a holiday, or not published yet)`); process.exitCode = 1; continue; }
    const prev = await previousSession(date);
    const { chains, futures, missing } = buildSession(date, rows, prev.rows, universe);
    const body = {
      schema: 1,
      kind: 'archive',
      date,
      recordedAt: new Date().toISOString(),
      source: `NSE${rows.BSE ? ' and BSE' : ''} F&O bhavcopy`,
      note: `Closing figures are the exchanges' own end-of-day bhavcopy for ${date} (previous session ${prev.date ?? 'not found'}). Futures open, high, low, close, previous close and open interest are real; the 1-minute path between them is rebuilt. Option chains are the real closing chains of the nearest expiry.`,
      chains,
      futures,
    };
    const file = path.join(OUT, `${date}.json.gz`);
    fs.writeFileSync(file, gzipSync(JSON.stringify(body), { level: 9 }));
    console.log(`  wrote ${path.relative(ROOT, file)}: ${Object.keys(chains).length} chains, ${Object.keys(futures).length} futures, ${(fs.statSync(file).size / 1024).toFixed(0)} KB`);
    if (missing.length) console.log(`  not in the archive: ${missing.join(', ')}`);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { console.error(error.message); process.exit(1); });
}
