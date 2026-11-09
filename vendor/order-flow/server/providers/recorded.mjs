/**
 * A recorded real session, replayed live: real futures minute by minute, real
 * option chains, no keys needed.
 *
 * Reads data/recorded/<date>.json.gz (written by `npm run record`; the repo
 * ships a sample). MF_RECORDED_DATE picks the session; the newest otherwise.
 * The session is replayed in real time from 09:20 to 15:30 and round again,
 * like the demo market, so the board always moves.
 *
 * Futures are the session's own 1-minute candles. A chain is one snapshot
 * taken when the session was recorded: its open interest stays as recorded,
 * and its spot follows the near-month future minute by minute (scaled by the
 * snapshot's spot-to-future ratio), so the moves on the board are the day's
 * real moves.
 *
 * Archive sessions (kind: "archive", from the exchanges' end-of-day bhavcopy)
 * carry the day's real closing chains and real futures open, high, low, close
 * and open interest; their 1-minute path is rebuilt between those points.
 */
import fs from 'node:fs';
import path from 'node:path';
import { gunzipSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const MINUTE = 60_000;
const SESSION_MINUTES = 375;
const REPLAY_FROM = 5;
const dateLabel = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Asia/Kolkata' });

/**
 * `options` lets the same replay serve another folder of sessions: the
 * `archive` provider replays data/archive (built by `npm run fetch:nse`).
 */
export function createRecordedProvider(universe, options = {}) {
  const {
    id = 'recorded',
    dir: defaultDir = 'data/recorded',
    dirEnv = 'MF_RECORDED_DIR',
    dateEnv = 'MF_RECORDED_DATE',
    label = 'Recorded',
    hint = 'Record one with `npm run record`',
  } = options;
  const dir = path.resolve(ROOT, process.env[dirEnv] || defaultDir);
  let day = null;
  /** symbol → { ratio, near } for scaling the snapshot's spot to each minute. */
  const scale = new Map();

  const openOf = date => Date.parse(`${date}T09:15:00+05:30`);
  const now = () => {
    if (!day) return Date.now();
    const loop = (SESSION_MINUTES - REPLAY_FROM) * MINUTE;
    return openOf(day.date) + REPLAY_FROM * MINUTE + (Date.now() % loop);
  };
  /** The near future's close at the last minute closed by `at`, or null. */
  const nearCloseAt = (symbol, at) => {
    const candles = day.futures[symbol]?.[0]?.candles;
    if (!candles?.length) return null;
    let close = null;
    for (const candle of candles) {
      if (candle.at + MINUTE > at) break;
      close = candle.close;
    }
    return close ?? candles[0].close;
  };

  const provider = {
    id,
    label: `${label} session`,
    alwaysLive: true,
    now,

    async init() {
      const files = fs.existsSync(dir) ? fs.readdirSync(dir).filter(f => /^\d{4}-\d{2}-\d{2}\.json\.gz$/.test(f)).sort() : [];
      if (!files.length) throw new Error(`No recorded sessions in ${path.relative(ROOT, dir) || dir}. ${hint}, or use MF_PROVIDER=demo.`);
      const wanted = process.env[dateEnv];
      const file = wanted ? files.find(f => f.startsWith(wanted)) : files.at(-1);
      if (!file) throw new Error(`No ${id} session for ${wanted}. Available: ${files.map(f => f.slice(0, 10)).join(', ')}.`);
      day = JSON.parse(gunzipSync(fs.readFileSync(path.join(dir, file))).toString('utf8'));
      if (day.schema !== 1) throw new Error(`${file}: unknown schema ${day.schema}.`);
      for (const [symbol, { chain }] of Object.entries(day.chains)) {
        const last = day.futures[symbol]?.[0]?.candles?.at(-1)?.close;
        scale.set(symbol, last ? chain.spot / last : null);
      }
      provider.label = `${label} ${dateLabel.format(openOf(day.date))}`;
    },

    async expiries(u) {
      return day.chains[u.symbol]?.ladder ?? [];
    },

    async optionChain(u, expiry) {
      const held = day.chains[u.symbol];
      if (!held) throw new Error(`${u.symbol} was not recorded.`);
      const at = now();
      const ratio = scale.get(u.symbol);
      const close = ratio ? nearCloseAt(u.symbol, at) : null;
      const near = day.futures[u.symbol]?.[0];
      return {
        ...held.chain,
        expiry: held.chain.expiry || expiry,
        at,
        spot: close ? Math.round(close * ratio * 100) / 100 : held.chain.spot,
        prevClose: ratio && near?.prevClose ? Math.round(near.prevClose * ratio * 100) / 100 : held.chain.prevClose,
      };
    },

    async futures(u, session) {
      if (session !== day.date) return [];
      const at = now();
      return (day.futures[u.symbol] ?? []).map(month => ({ ...month, candles: month.candles.filter(c => c.at + MINUTE <= at) }));
    },
  };
  return provider;
}
