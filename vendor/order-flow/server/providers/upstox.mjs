/**
 * Upstox (https://upstox.com/developer/api-documentation/).
 *
 * STATUS: written against Upstox's documented v2/v3 REST API, not yet run
 * against a live account. The first person to run it should work through the
 * "Verify" list in PROVIDERS.md and fix anything marked TODO below.
 *
 * Setup:
 *   MF_PROVIDER=upstox
 *   UPSTOX_ACCESS_TOKEN=<the day's access token from the OAuth login flow>
 *
 * How it maps onto the contract (./types.mjs):
 *   instruments  the public NSE + BSE instrument files (no auth), read once at
 *                start: symbol → underlying key, futures and option expiries.
 *   expiries     the option expiries listed for the underlying in those files.
 *   optionChain  GET /v2/option/chain, plus the underlying's previous close
 *                from GET /v2/market-quote/quotes.
 *   futures      the nearest two futures; 1-minute candles from
 *                /v3/historical-candle/intraday (today) or /v3/historical-candle
 *                (an earlier session); the previous close and OI from daily candles.
 */
import { gunzipSync } from 'node:zlib';

const API = 'https://api.upstox.com';
const INSTRUMENTS = [
  'https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz',
  'https://assets.upstox.com/market-quote/instruments/exchange/BSE.json.gz',
];
/** Upstox allows about 25 requests a second per user; stay well under. */
const MAX_PER_SECOND = 10;
const DAY = 86_400_000;

const ymdIst = ms => new Date(ms + 330 * 60_000).toISOString().slice(0, 10);

/** Index symbols as Upstox names them in `underlying_symbol` (TODO: verify against the instrument files). */
const INDEX_NAME = { NIFTY: 'NIFTY', BANKNIFTY: 'BANKNIFTY', FINNIFTY: 'FINNIFTY', MIDCPNIFTY: 'MIDCPNIFTY', NIFTYNXT50: 'NIFTYNXT50', SENSEX: 'SENSEX', BANKEX: 'BANKEX', SENSEX50: 'SENSEX50' };

export function createUpstoxProvider(universe) {
  const token = process.env.UPSTOX_ACCESS_TOKEN;
  /** symbol → { key, futures: [{ key, expiry }], expiries: Set } */
  const map = new Map();
  let slots = [];

  async function get(path) {
    // A small token bucket: at most MAX_PER_SECOND requests in any second.
    const now = Date.now();
    slots = slots.filter(t => now - t < 1000);
    if (slots.length >= MAX_PER_SECOND) await new Promise(resolve => setTimeout(resolve, 1000 - (now - slots[0])));
    slots.push(Date.now());
    const res = await fetch(`${API}${path}`, { headers: { Accept: 'application/json', Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(20_000) });
    if (!res.ok) throw new Error(`Upstox ${res.status} ${path}: ${(await res.text()).slice(0, 200)}`);
    const body = await res.json();
    if (body.status && body.status !== 'success') throw new Error(`Upstox ${path}: ${JSON.stringify(body.errors ?? body).slice(0, 200)}`);
    return body.data;
  }

  const entry = symbol => {
    const held = map.get(symbol);
    if (!held?.key) throw new Error(`Upstox has no instrument for ${symbol}`);
    return held;
  };

  return {
    id: 'upstox',
    label: 'Upstox',

    async init() {
      if (!token) throw new Error('Set UPSTOX_ACCESS_TOKEN (see PROVIDERS.md).');
      const wanted = new Map(universe.map(u => [INDEX_NAME[u.symbol] ?? u.symbol, u.symbol]));
      for (const url of INSTRUMENTS) {
        const res = await fetch(url, { signal: AbortSignal.timeout(60_000) });
        if (!res.ok) throw new Error(`Upstox instruments ${res.status}: ${url}`);
        const rows = JSON.parse(gunzipSync(Buffer.from(await res.arrayBuffer())).toString('utf8'));
        for (const row of rows) {
          if (!['NSE_FO', 'BSE_FO'].includes(row.segment)) continue;
          const symbol = wanted.get(row.underlying_symbol);
          if (!symbol) continue;
          const held = map.get(symbol) ?? { key: row.underlying_key, futures: [], expiries: new Set() };
          const expiry = ymdIst(Number(row.expiry));
          if (row.instrument_type === 'FUT') held.futures.push({ key: row.instrument_key, expiry });
          else if (row.instrument_type === 'CE' || row.instrument_type === 'PE') held.expiries.add(expiry);
          map.set(symbol, held);
        }
      }
      for (const held of map.values()) held.futures.sort((a, b) => a.expiry.localeCompare(b.expiry));
      const missing = universe.filter(u => !map.has(u.symbol)).map(u => u.symbol);
      if (missing.length) console.warn(`upstox: no F&O instruments for ${missing.length} symbols: ${missing.slice(0, 20).join(' ')}`);
    },

    async expiries(u) {
      return [...(map.get(u.symbol)?.expiries ?? [])].sort();
    },

    async optionChain(u, expiry) {
      const { key } = entry(u.symbol);
      const q = encodeURIComponent(key);
      const [rows, quotes] = await Promise.all([
        get(`/v2/option/chain?instrument_key=${q}&expiry_date=${expiry}`),
        get(`/v2/market-quote/quotes?instrument_key=${q}`),
      ]);
      // The quotes answer is keyed by "NSE_INDEX:Nifty 50"-style names, not the request key: take its only entry.
      const quote = Object.values(quotes ?? {})[0];
      const spot = Number(rows?.[0]?.underlying_spot_price ?? quote?.last_price);
      const prevClose = quote && Number.isFinite(quote.net_change) ? Number(quote.last_price) - Number(quote.net_change) : null;
      const leg = side => {
        if (!side?.market_data) return undefined;
        const m = side.market_data;
        const g = side.option_greeks ?? {};
        return {
          ltp: Number(m.ltp) || 0,
          prevClose: Number(m.close_price) || null,
          oi: Number(m.oi) || 0,
          prevOi: Number.isFinite(m.prev_oi) ? Number(m.prev_oi) : null,
          volume: Number(m.volume) || 0,
          prevVolume: null,
          avgPrice: Number(m.ltp) || 0, // TODO: the chain has no average price; read it from market quotes if it matters.
          iv: Number.isFinite(g.iv) ? Number(g.iv) : null,
          bid: Number(m.bid_price) || 0,
          ask: Number(m.ask_price) || 0,
          bidQty: Number(m.bid_qty) || 0,
          askQty: Number(m.ask_qty) || 0,
          dayHigh: null,
          dayLow: null,
          lastTradeAt: null,
          delta: Number.isFinite(g.delta) ? Number(g.delta) : null,
        };
      };
      return {
        expiry, at: Date.now(), spot, prevClose, atm: null,
        strikes: (rows ?? []).map(row => ({ strike: Number(row.strike_price), call: leg(row.call_options), put: leg(row.put_options) })),
      };
    },

    async futures(u, session) {
      const held = map.get(u.symbol);
      const months = (held?.futures ?? []).filter(f => f.expiry >= session).slice(0, 2);
      const today = ymdIst(Date.now());
      return Promise.all(months.map(async ({ key, expiry }) => {
        const q = encodeURIComponent(key);
        const before = ymdIst(Date.parse(`${session}T00:00:00+05:30`) - DAY);
        const from = ymdIst(Date.parse(`${session}T00:00:00+05:30`) - 15 * DAY);
        // Candles arrive newest first as [time, open, high, low, close, volume, oi].
        const [daily, minute] = await Promise.all([
          get(`/v3/historical-candle/${q}/days/1/${before}/${from}`).catch(() => ({ candles: [] })),
          session === today
            ? get(`/v3/historical-candle/intraday/${q}/minutes/1`)
            : get(`/v3/historical-candle/${q}/minutes/1/${session}/${session}`),
        ]);
        const last = (daily?.candles ?? [])[0];
        const candles = (minute?.candles ?? [])
          .map(c => ({ at: Date.parse(c[0]), close: Number(c[4]), oi: Number(c[6]) }))
          .filter(c => Number.isFinite(c.at) && c.close > 0 && Number.isFinite(c.oi))
          .sort((a, b) => a.at - b.at);
        return { date: expiry, prevClose: last ? Number(last[4]) : null, prevOi: last ? Number(last[6]) : null, candles };
      }));
    },
  };
}
