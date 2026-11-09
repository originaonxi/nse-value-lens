/**
 * The market file (schema 1): every underlying's option chain at its nearest
 * live expiry, one series each, in the compact form the page reads with
 * `parseMarketFile` (src/features/options-scanner/contractScanModel.ts). The
 * round trip is pinned by marketFile.test.ts.
 *
 * Input is a provider's OptionChain (server/providers/types.mjs): rupees and
 * units. Each row is an 18-field array:
 *   [strike, side(0 call | 1 put), ltp, prevClose, oi, prevOi, volume, prevVolume,
 *    avgPrice, iv, bid, ask, bidQty, askQty, dayHigh, dayLow, lastTradeAt, delta]
 */

const finite = value => typeof value === 'number' && Number.isFinite(value);
const num = value => (finite(value) ? value : 0);
const orNull = value => (finite(value) ? value : null);
const positiveOrNull = value => (finite(value) && value > 0 ? value : null);
const round2 = value => Math.round(value * 100) / 100;

/** One side of one strike as a row, or null when it has neither OI nor volume (unless kept idle). */
export function legRow(strike, side, leg, keepIdle = false) {
  const oi = num(leg.oi);
  const volume = num(leg.volume);
  if (!keepIdle && !(oi > 0) && !(volume > 0)) return null;
  return [
    strike, side, round2(num(leg.ltp)), positiveOrNull(leg.prevClose), oi, orNull(leg.prevOi), volume, orNull(leg.prevVolume),
    round2(num(leg.avgPrice) || num(leg.ltp)), finite(leg.iv) ? round2(leg.iv) : null, round2(num(leg.bid)), round2(num(leg.ask)),
    num(leg.bidQty), num(leg.askQty), positiveOrNull(leg.dayHigh), positiveOrNull(leg.dayLow), orNull(leg.lastTradeAt), orNull(leg.delta),
  ];
}

const byStrikeThenSide = (a, b) => a[0] - b[0] || a[1] - b[1];

/** One chain → one series, or null when it has no priced spot. */
export function encodeSeries(underlying, chain, readAt) {
  const spot = num(chain?.spot);
  if (!(spot > 0)) return null;
  const rows = [];
  const idle = [];
  const ladder = [];
  for (const row of chain.strikes ?? []) {
    const strike = num(row?.strike);
    if (!(strike > 0)) continue;
    let listed = false;
    for (const [side, leg] of [[0, row.call], [1, row.put]]) {
      if (!leg) continue;
      listed = true;
      const encoded = legRow(strike, side, leg);
      if (encoded) rows.push(encoded);
      else idle.push(legRow(strike, side, leg, true));
    }
    if (listed) ladder.push(strike);
  }
  ladder.sort((a, b) => a - b);
  // No at-the-money strike from the source: the listed strike nearest spot.
  const atm = positiveOrNull(chain.atm) ?? (ladder.length ? ladder.reduce((best, k) => (Math.abs(k - spot) < Math.abs(best - spot) ? k : best)) : null);
  return {
    s: underlying.symbol,
    k: underlying.kind === 'index' ? 'index' : 'stock',
    e: chain.expiry,
    lot: underlying.lot,
    ls: 'catalogue',
    t: Math.round(readAt),
    tp: positiveOrNull(chain.at),
    sp: round2(spot),
    pc: positiveOrNull(chain.prevClose),
    atm,
    r: rows.sort(byStrikeThenSide),
    ks: ladder,
    z: idle.sort(byStrikeThenSide),
  };
}

/** The whole file: every series read this tick, the stored minutes, and each symbol's live expiries. */
export function marketFile({ at, date, series, minutes, ladders }) {
  return { schema: 1, t: Math.round(at), date, series, minutes, ladders };
}
