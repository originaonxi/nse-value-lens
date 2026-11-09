/**
 * HTTP: connect Order Flow to ANY JSON API with environment variables only.
 *
 *   MF_PROVIDER=http
 *   MF_HTTP_BASE_URL=http://127.0.0.1:9000        (required)
 *   MF_HTTP_TOKEN=...                              (optional: sent as Authorization: Bearer …)
 *   MF_HTTP_HEADERS={"x-api-key":"..."}            (optional: any extra headers, as JSON)
 *   MF_HTTP_EXPIRIES=/expiries/{symbol}            (optional: the three paths, as templates)
 *   MF_HTTP_CHAIN=/chain/{symbol}?expiry={expiry}
 *   MF_HTTP_FUTURES=/futures/{symbol}?session={session}
 *   MF_HTTP_MAP=./my-api-map.mjs                   (optional: reshape another API's JSON)
 *   MF_HTTP_RPS=10                                 (optional: requests per second, default 10)
 *
 * Templates take {symbol}, {exch}, {kind}, {apiKey}, {expiry} and {session}.
 *
 * Two ways to use it:
 *
 *   1. Your API already answers in Order Flow's shapes (server/providers/types.mjs):
 *      set MF_HTTP_BASE_URL (and the paths if yours differ). Done.
 *   2. Your API answers in its own shapes: write a small map module with up to
 *      three functions that turn its JSON into ours, and point MF_HTTP_MAP at
 *      it. See examples/http-map.example.mjs. No provider code to write.
 *
 * Either way the answers are normalised and checked: ISO dates and epoch
 * seconds become epoch milliseconds, missing option fields become null or 0,
 * candles are sorted ascending, `{ data: … }` / `{ result: … }` wrappers are
 * unwrapped. Run
 * `MF_PROVIDER=http npm run check:provider` to see what still needs fixing.
 */
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const DEFAULT_PATHS = {
  expiries: '/expiries/{symbol}',
  chain: '/chain/{symbol}?expiry={expiry}',
  futures: '/futures/{symbol}?session={session}',
};

/** Fill a path template; every value is URL-encoded. */
export function fillTemplate(template, values) {
  return template.replace(/\{(\w+)\}/g, (whole, key) => (values[key] == null ? whole : encodeURIComponent(String(values[key]))));
}

/** Epoch ms from epoch ms, epoch seconds or an ISO string. */
export function toMs(value) {
  if (value == null || value === '') return null;
  if (typeof value === 'number') return value < 1e11 ? value * 1000 : value;
  const n = Number(value);
  if (Number.isFinite(n)) return toMs(n);
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

const numOr = (value, fallback) => {
  const n = typeof value === 'string' ? Number(value) : value;
  return typeof n === 'number' && Number.isFinite(n) ? n : fallback;
};
/** `{ data: … }` and `{ result: … }` wrappers, as many APIs send them. */
const unwrap = json => {
  if (!json || typeof json !== 'object' || Array.isArray(json)) return json;
  if ('data' in json) return json.data;
  if ('result' in json) return json.result;
  return json;
};
const isoDate = value => {
  if (typeof value !== 'string') return null;
  const m = value.match(/^(\d{4}-\d{2}-\d{2})/);
  return m ? m[1] : null;
};

export function normaliseExpiries(json) {
  const list = unwrap(json);
  const raw = Array.isArray(list) ? list : list?.expiries ?? [];
  return [...new Set(raw.map(isoDate).filter(Boolean))].sort();
}

function normaliseLeg(leg) {
  if (!leg || typeof leg !== 'object') return undefined;
  const ltp = numOr(leg.ltp ?? leg.last_price ?? leg.lastPrice ?? leg.close, 0);
  return {
    ltp,
    prevClose: numOr(leg.prevClose ?? leg.prev_close ?? leg.close_price, null),
    oi: numOr(leg.oi ?? leg.openInterest ?? leg.open_interest, 0),
    prevOi: numOr(leg.prevOi ?? leg.prev_oi, null),
    volume: numOr(leg.volume, 0),
    prevVolume: numOr(leg.prevVolume, null),
    avgPrice: numOr(leg.avgPrice ?? leg.average_price ?? leg.vwap, ltp),
    iv: numOr(leg.iv, null),
    bid: numOr(leg.bid, 0),
    ask: numOr(leg.ask, 0),
    bidQty: numOr(leg.bidQty, 0),
    askQty: numOr(leg.askQty, 0),
    dayHigh: numOr(leg.dayHigh ?? leg.high, null),
    dayLow: numOr(leg.dayLow ?? leg.low, null),
    lastTradeAt: toMs(leg.lastTradeAt),
    delta: numOr(leg.delta, null),
  };
}

export function normaliseChain(json, expiry) {
  const c = unwrap(json) ?? {};
  const strikes = (c.strikes ?? [])
    .map(row => ({ strike: numOr(row.strike ?? row.strike_price, NaN), call: normaliseLeg(row.call ?? row.CE ?? row.ce), put: normaliseLeg(row.put ?? row.PE ?? row.pe) }))
    .filter(row => Number.isFinite(row.strike) && (row.call || row.put))
    .sort((a, b) => a.strike - b.strike);
  return {
    expiry: isoDate(c.expiry) ?? expiry,
    at: toMs(c.at) ?? Date.now(),
    spot: numOr(c.spot ?? c.underlying_price ?? c.ltp, 0),
    prevClose: numOr(c.prevClose ?? c.prev_close, null),
    atm: numOr(c.atm, null),
    strikes,
  };
}

export function normaliseFutures(json) {
  const list = unwrap(json);
  const raw = Array.isArray(list) ? list : list?.months ?? [];
  return raw
    .map(month => ({
      date: isoDate(month.date ?? month.expiry),
      prevClose: numOr(month.prevClose ?? month.prev_close, null),
      prevOi: numOr(month.prevOi ?? month.prev_oi, null),
      candles: (month.candles ?? [])
        .map(c => (Array.isArray(c)
          // [time, close, oi] or OHLC rows [time, open, high, low, close, volume, oi]
          ? { at: toMs(c[0]), close: numOr(c.length >= 5 ? c[4] : c[1], NaN), oi: numOr(c.length >= 7 ? c[6] : c[2], 0) }
          : { at: toMs(c.at ?? c.time ?? c.timestamp), close: numOr(c.close, NaN), oi: numOr(c.oi, 0) }))
        .filter(c => c.at != null && Number.isFinite(c.close))
        .sort((a, b) => a.at - b.at),
    }))
    .filter(month => month.date)
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(0, 3);
}

export function createHttpProvider(universe, env = process.env, fetcher = globalThis.fetch) {
  const base = (env.MF_HTTP_BASE_URL || '').replace(/\/+$/, '');
  const paths = {
    expiries: env.MF_HTTP_EXPIRIES || DEFAULT_PATHS.expiries,
    chain: env.MF_HTTP_CHAIN || DEFAULT_PATHS.chain,
    futures: env.MF_HTTP_FUTURES || DEFAULT_PATHS.futures,
  };
  const perSecond = Math.max(1, numOr(env.MF_HTTP_RPS, 10));
  let map = {};

  const headers = { Accept: 'application/json' };
  if (env.MF_HTTP_TOKEN) headers.Authorization = `Bearer ${env.MF_HTTP_TOKEN}`;

  // A token bucket: at most `perSecond` requests in any second.
  const stamps = [];
  async function slot() {
    for (;;) {
      const now = Date.now();
      while (stamps.length && now - stamps[0] >= 1000) stamps.shift();
      if (stamps.length < perSecond) { stamps.push(now); return; }
      await new Promise(resolve => setTimeout(resolve, 1000 - (now - stamps[0]) + 5));
    }
  }

  async function get(template, u, extra = {}) {
    await slot();
    const url = base + fillTemplate(template, { symbol: u.symbol, exch: u.exch, kind: u.kind, apiKey: u.apiKey, ...extra });
    const response = await fetcher(url, { headers });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText || ''} from ${url.replace(base, '')}`.trim());
    return response.json();
  }

  return {
    id: 'http',
    label: env.MF_HTTP_LABEL || 'Your API',

    async init() {
      if (!base) throw new Error('Set MF_HTTP_BASE_URL to your API (see PROVIDERS.md, "Any API").');
      if (env.MF_HTTP_HEADERS) {
        try { Object.assign(headers, JSON.parse(env.MF_HTTP_HEADERS)); } catch { throw new Error('MF_HTTP_HEADERS must be JSON, e.g. {"x-api-key":"..."}'); }
      }
      if (env.MF_HTTP_MAP) {
        const mod = await import(pathToFileURL(path.resolve(env.MF_HTTP_MAP)).href);
        map = mod.default ?? mod;
      }
    },

    async expiries(u) {
      const json = await get(paths.expiries, u);
      return normaliseExpiries(map.expiries ? map.expiries(json, u) : json);
    },

    async optionChain(u, expiry) {
      const json = await get(paths.chain, u, { expiry });
      return normaliseChain(map.optionChain ? map.optionChain(json, u, expiry) : json, expiry);
    },

    async futures(u, session) {
      const json = await get(paths.futures, u, { session });
      return normaliseFutures(map.futures ? map.futures(json, u, session) : json);
    },
  };
}
