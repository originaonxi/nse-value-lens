/**
 * The demo market: a live, simulated session for every F&O underlying, so
 * Order Flow runs with no broker and no keys.
 *
 * Every number is generated, deterministically: the same session plays out
 * the same way on every machine and every restart. A session has a market
 * mood, a mood per sector and each stock's own move; prices walk through the
 * day toward that move (a Brownian bridge with most of the move in the first
 * hour or two, as on a trending day); futures carry a basis and an open-interest build-up that
 * agrees with the move most of the time; option chains are priced with
 * Black-Scholes on a volatility smile, with open interest piled on round
 * strikes, calls above spot and puts below.
 *
 * The clock: in market hours it is the real clock. Outside them the latest
 * session is replayed in real time, from 09:20 to 15:30 and round again, so
 * the board is always moving. Nothing here is a real price.
 */
import fs from 'node:fs';
import path from 'node:path';
import { gunzipSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';
import { getLatestTradingSessionDate, isMarketSessionTime } from '../../src/lib/marketSession.ts';

const MINUTE = 60_000;
const SESSION_MINUTES = 375; // 09:15 to 15:30
const REPLAY_FROM = 5; // the replay starts at 09:20, with a few minutes already drawn

// ── Randomness ──────────────────────────────────────────────────────────────

function seeded(text) {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return () => {
    h = Math.imul(h ^ (h >>> 15), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    return ((h ^= h >>> 16) >>> 0) / 4294967296;
  };
}
const gaussOf = random => () => {
  const u = Math.max(1e-12, random());
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * random());
};
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
const round2 = value => Math.round(value * 100) / 100;

// ── Clock and calendar ──────────────────────────────────────────────────────

const openOf = session => Date.parse(`${session}T09:15:00+05:30`);

export function demoNow(real = Date.now()) {
  if (isMarketSessionTime(real)) return real;
  const session = getLatestTradingSessionDate(new Date(real));
  const loop = (SESSION_MINUTES - REPLAY_FROM) * MINUTE;
  return openOf(session) + REPLAY_FROM * MINUTE + (real % loop);
}

const ymd = ms => new Date(ms).toISOString().slice(0, 10);
const dayMs = date => Date.parse(`${date}T00:00:00Z`);

/** The last given weekday (0 Sunday … 6 Saturday) of a month. */
function lastWeekday(year, month, weekday) {
  const last = new Date(Date.UTC(year, month + 1, 0));
  last.setUTCDate(last.getUTCDate() - ((last.getUTCDay() - weekday + 7) % 7));
  return ymd(last.getTime());
}
/** Monthly expiries on or after `from`: the last Tuesday of each month (NSE), the last Thursday on BSE. */
function monthlies(from, count, weekday = 2) {
  const out = [];
  const d = new Date(dayMs(from));
  let year = d.getUTCFullYear();
  let month = d.getUTCMonth();
  while (out.length < count) {
    const date = lastWeekday(year, month, weekday);
    if (date >= from) out.push(date);
    month += 1;
    if (month > 11) { month = 0; year += 1; }
  }
  return out;
}
/** Weekly expiries on or after `from` on the given weekday. */
function weeklies(from, count, weekday) {
  const out = [];
  let t = dayMs(from);
  while (out.length < count) {
    if (new Date(t).getUTCDay() === weekday) out.push(ymd(t));
    t += 86_400_000;
  }
  return out;
}

// ── The session: one path per underlying ─────────────────────────────────────

const INDEX_PRICE = { NIFTY: 24600, BANKNIFTY: 52800, FINNIFTY: 24100, MIDCPNIFTY: 12750, NIFTYNXT50: 66800, SENSEX: 80900, SENSEX50: 26100, BANKEX: 59800, FOCIT: 41200 };

/** Rough levels for well-known names, so the demo reads plausibly. Illustrative only, not quotes. */
const STOCK_PRICE = {
  RELIANCE: 1420, HDFCBANK: 980, ICICIBANK: 1380, INFY: 1520, TCS: 3050, SBIN: 860, BHARTIARTL: 1950, ITC: 410, LT: 3700,
  KOTAKBANK: 2100, AXISBANK: 1180, HINDUNILVR: 2450, BAJFINANCE: 1000, MARUTI: 15800, SUNPHARMA: 1650, TITAN: 3550,
  ULTRACEMCO: 12100, NTPC: 340, POWERGRID: 290, ONGC: 245, TMPV: 410, TATASTEEL: 170, WIPRO: 245, HCLTECH: 1480,
  TECHM: 1450, ASIANPAINT: 2400, NESTLEIND: 1230, ADANIENT: 2450, ADANIPORTS: 1450, COALINDIA: 390, JSWSTEEL: 1150,
  HINDALCO: 780, GRASIM: 2800, CIPLA: 1530, DRREDDY: 1270, EICHERMOT: 6900, 'BAJAJ-AUTO': 8900, 'M&M': 3450, HEROMOTOCO: 5400,
  TRENT: 4750, ETERNAL: 330, JIOFIN: 310, BEL: 410, INDIGO: 5700, APOLLOHOSP: 7600, MAXHEALTH: 1150, SHRIRAMFIN: 680,
  SBILIFE: 1850, HDFCLIFE: 760, TATACONSUM: 1150, BAJAJFINSV: 2050, DMART: 4300, IRFC: 125, SUZLON: 58, YESBANK: 21,
};

/**
 * Real price levels from the newest real session on disk (data/archive, built
 * from the exchanges' bhavcopy by `npm run fetch:nse`, or data/recorded), when
 * there is one: the demo then sits near real prices.
 */
const RECORDED_PRICE = (() => {
  try {
    const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
    const files = ['data/archive', 'data/recorded'].flatMap(dir => {
      const full = path.join(root, dir);
      return fs.existsSync(full) ? fs.readdirSync(full).filter(f => /^\d{4}-\d{2}-\d{2}\.json\.gz$/.test(f)).map(f => path.join(full, f)) : [];
    });
    const latest = files.sort((a, b) => path.basename(a).localeCompare(path.basename(b))).at(-1);
    if (!latest) return {};
    const day = JSON.parse(gunzipSync(fs.readFileSync(latest)).toString('utf8'));
    return Object.fromEntries(Object.entries(day.chains ?? {}).map(([symbol, held]) => [symbol, held.chain?.spot]).filter(([, spot]) => spot > 0));
  } catch {
    return {};
  }
})();

function basePrice(u) {
  if (RECORDED_PRICE[u.symbol]) return RECORDED_PRICE[u.symbol];
  if (INDEX_PRICE[u.symbol]) return INDEX_PRICE[u.symbol];
  if (STOCK_PRICE[u.symbol]) return STOCK_PRICE[u.symbol];
  // Log-uniform between ₹80 and ₹6,000, the same for a symbol every session.
  const r = seeded(`price|${u.symbol}`)();
  return Math.exp(Math.log(80) + r * (Math.log(6000) - Math.log(80)));
}

const sessions = new Map();

/** Each underlying's minute path for a session: prevClose and 376 prices (09:15 … 15:30). */
function sessionOf(session, universe) {
  let held = sessions.get(session);
  if (held) return held;
  if (sessions.size > 4) sessions.clear();
  const mood = gaussOf(seeded(`mood|${session}`));
  const market = mood() * 0.7 - 0.1;
  const sectorMood = new Map();
  held = new Map();
  for (const u of universe) {
    const random = seeded(`${session}|${u.symbol}`);
    const gauss = gaussOf(random);
    const index = u.kind === 'index';
    if (u.sector && !sectorMood.has(u.sector)) sectorMood.set(u.sector, gaussOf(seeded(`sector|${session}|${u.sector}`))() * 0.9);
    const beta = index ? 0.85 : 0.6 + random() * 0.8;
    const move = clamp(index ? market * beta + gauss() * 0.25 : market * beta + (sectorMood.get(u.sector) ?? 0) * 1.3 + gauss() * 2.2, -9.5, 9.5);
    const prevClose = basePrice(u) * Math.exp(gaussOf(seeded(`prev|${session}|${u.symbol}`))() * 0.04);
    const sigma = prevClose * (index ? 0.0045 : 0.009) / Math.sqrt(SESSION_MINUTES);
    const walk = [0];
    for (let i = 1; i <= SESSION_MINUTES; i++) walk.push(walk[i - 1] + gauss() * sigma);
    const path = walk.map((w, i) => {
      const t = i / SESSION_MINUTES;
      const drift = prevClose * (1 + (move / 100) * (1 - Math.pow(1 - t, 3)));
      return Math.max(prevClose * 0.5, drift + (w - walk[SESSION_MINUTES] * t));
    });
    // Open interest agrees with the move about seven times in ten: a build-up, else covering or unwinding.
    const agrees = random() < 0.7;
    const oiMove = (agrees ? 1 : -1) * (0.02 + random() * 0.1);
    // Near-month open interest at the previous close, in lots.
    const oiLots = index ? 60_000 + random() * 140_000 : 2_000 + random() * 9_000;
    held.set(u.symbol, { u, prevClose, path, oiMove, oiLots });
  }
  sessions.set(session, held);
  return held;
}

const minuteIndex = (session, now) => clamp(Math.floor((now - openOf(session)) / MINUTE), 0, SESSION_MINUTES);

// ── Pricing ────────────────────────────────────────────────────────────────

function cdf(x) {
  // Abramowitz and Stegun 7.1.26.
  const t = 1 / (1 + 0.3275911 * Math.abs(x) / Math.SQRT2);
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-(x * x) / 2);
  return x >= 0 ? 0.5 * (1 + y) : 0.5 * (1 - y);
}
function blackScholes(spot, strike, years, vol, call) {
  const t = Math.max(years, 0.5 / 365);
  const d1 = (Math.log(spot / strike) + 0.5 * vol * vol * t) / (vol * Math.sqrt(t));
  const d2 = d1 - vol * Math.sqrt(t);
  const price = call ? spot * cdf(d1) - strike * cdf(d2) : strike * cdf(-d2) - spot * cdf(-d1);
  return { price: Math.max(0.05, price), delta: call ? cdf(d1) : cdf(d1) - 1 };
}

function stepOf(u, price) {
  if (u.kind === 'index') return price > 40000 ? 100 : 50;
  if (price < 250) return 2.5;
  if (price < 500) return 5;
  if (price < 1000) return 10;
  if (price < 2500) return 20;
  if (price < 5000) return 50;
  return 100;
}

// ── The provider ───────────────────────────────────────────────────────────

export function createDemoProvider(universe) {
  const bySymbol = new Map(universe.map(u => [u.symbol, u]));
  return {
    id: 'demo',
    label: 'Demo market',
    alwaysLive: true,
    now: () => demoNow(),

    async expiries(u) {
      const today = getLatestTradingSessionDate(new Date(demoNow()));
      if (u.kind === 'index') {
        const weekday = u.exch === 'BSE' ? 4 : 2;
        const weekly = ['NIFTY', 'SENSEX'].includes(u.symbol) ? weeklies(today, 4, weekday) : [];
        return [...new Set([...weekly, ...monthlies(today, 3, weekday)])].sort();
      }
      return monthlies(today, 3);
    },

    async optionChain(u, expiry) {
      const now = demoNow();
      const session = getLatestTradingSessionDate(new Date(now));
      const day = sessionOf(session, universe).get(u.symbol) ?? sessionOf(session, [...universe, u]).get(u.symbol);
      const spot = day.path[minuteIndex(session, now)];
      const random = seeded(`chain|${session}|${u.symbol}|${expiry}`);
      const step = stepOf(u, day.prevClose);
      const atm = Math.round(spot / step) * step;
      const years = Math.max(0, (Date.parse(`${expiry}T15:30:00+05:30`) - now) / (365 * 86_400_000));
      const baseIv = u.kind === 'index' ? 0.13 : 0.26 + random() * 0.12;
      const scale = day.u.lot * (u.kind === 'index' ? 9000 : 1400) * (0.6 + random() * 0.8);
      const strikes = [];
      for (let k = -20; k <= 20; k++) {
        const strike = round2(atm + k * step);
        if (strike <= 0) continue;
        const m = strike / spot - 1;
        const iv = baseIv + 0.9 * m * m + (m < 0 ? -0.15 * m : 0);
        const round = strike % (step * 5) === 0 ? 1.9 : strike % (step * 2) === 0 ? 1.25 : 1;
        const leg = call => {
          const center = spot * (call ? 1.025 : 0.975);
          // Writers sell out of the money: an in-the-money strike carries much less open interest.
          const itm = call ? strike < spot : strike > spot;
          const oi = Math.round(scale * round * (itm ? 0.35 : 1) * Math.exp(-(((strike - center) / (spot * 0.035)) ** 2)) * (0.75 + random() * 0.5) / day.u.lot) * day.u.lot;
          const now$ = blackScholes(spot, strike, years, iv, call);
          const prev = blackScholes(day.prevClose, strike, years + 1 / 365, iv, call);
          const ltp = round2(now$.price);
          const spread = Math.max(0.05, round2(ltp * 0.004));
          const volume = Math.round(oi * (0.3 + random() * 1.4) / day.u.lot) * day.u.lot;
          return {
            ltp, prevClose: round2(prev.price), oi, prevOi: Math.round(oi / (1 + (random() - 0.35) * 0.3)),
            volume, prevVolume: Math.round(volume * (0.6 + random() * 0.8)), avgPrice: round2((ltp + prev.price) / 2),
            iv: round2(iv * 100), bid: round2(Math.max(0.05, ltp - spread)), ask: round2(ltp + spread),
            bidQty: day.u.lot * (1 + Math.floor(random() * 40)), askQty: day.u.lot * (1 + Math.floor(random() * 40)),
            dayHigh: round2(Math.max(ltp, prev.price) * 1.06), dayLow: round2(Math.min(ltp, prev.price) * 0.94),
            lastTradeAt: now - Math.floor(random() * 20_000), delta: now$.delta,
          };
        };
        strikes.push({ strike, call: leg(true), put: leg(false) });
      }
      return { expiry, at: now, spot: round2(spot), prevClose: round2(day.prevClose), atm, strikes };
    },

    async futures(u, session) {
      const now = demoNow();
      const day = sessionOf(session, universe).get(u.symbol) ?? sessionOf(session, [...universe, bySymbol.get(u.symbol) ?? u]).get(u.symbol);
      const open = openOf(session);
      // Candles that have closed by now: the one starting at 09:15 closes at 09:16.
      const closed = now >= open + SESSION_MINUTES * MINUTE ? SESSION_MINUTES : minuteIndex(session, now);
      const months = monthlies(session, 3, u.exch === 'BSE' ? 4 : 2).slice(0, 2);
      return months.map((date, m) => {
        const days = Math.max(0, (dayMs(date) - dayMs(session)) / 86_400_000);
        const basis = 1 + 0.0004 + days * 0.00022;
        const prevOi = Math.round(day.oiLots * (m === 0 ? 1 : 0.18)) * day.u.lot;
        const candles = [];
        for (let i = 0; i < closed; i++) {
          const t = (i + 1) / SESSION_MINUTES;
          const oi = Math.round(prevOi * (1 + day.oiMove * (1 - Math.pow(1 - t, 1.4))));
          candles.push({ at: open + i * MINUTE, close: round2(day.path[i + 1] * basis), oi });
        }
        return { date, prevClose: round2(day.prevClose * basis), prevOi, candles };
      });
    },
  };
}
