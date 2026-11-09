import { describe, expect, it } from 'vitest';
import { parseMarketFile } from '../src/features/options-scanner/contractScanModel';
import { encodeSeries, marketFile } from './marketFile.mjs';
import { createDemoProvider } from './providers/demo.mjs';

const leg = (over = {}) => ({
  ltp: 123.45, prevClose: 100, oi: 1500, prevOi: 1200, volume: 900, prevVolume: 40, avgPrice: 120, iv: 14.567,
  bid: 123, ask: 124, bidQty: 75, askQty: 150, dayHigh: 130, dayLow: 90, lastTradeAt: 1_790_000_000_000, delta: 0.4321, ...over,
});

describe('encodeSeries', () => {
  const nifty = { symbol: 'NIFTY', kind: 'index', lot: 65 } as const;
  const chain = {
    expiry: '2026-11-03', at: 1_790_000_100_000, spot: 24567.89, prevClose: 24500, atm: 24550,
    strikes: [
      { strike: 24600, call: leg(), put: leg({ oi: 0, volume: 0 }) },
      { strike: 24500, call: leg({ prevClose: null }), put: leg() },
      { strike: 0, call: leg() },
    ],
  };

  it('round-trips through the page parser', () => {
    const series = encodeSeries(nifty, chain, 1_790_000_200_000);
    const parsed = parseMarketFile(marketFile({ at: 1_790_000_200_000, date: '2026-10-30', series: [series], minutes: [['1502', 1_790_000_200_000]], ladders: { NIFTY: ['2026-11-03'] } }));
    expect(parsed).not.toBeNull();
    const [s] = parsed!.series;
    expect(s).toMatchObject({ symbol: 'NIFTY', kind: 'index', expiry: '2026-11-03', lot: 65, spot: 24567.89, spotPrevClose: 24500, atm: 24550, tape: 1_790_000_100_000 });
    expect(s.ladder).toEqual([24500, 24600]);
    // Strike order, call before put; the idle put sits apart in "z".
    expect(s.quotes.map(q => `${q.strike}${q.side}`)).toEqual(['24500CE', '24500PE', '24600CE']);
    expect(s.idle.map(q => `${q.strike}${q.side}`)).toEqual(['24600PE']);
    expect(s.quotes[2]).toMatchObject({ ltp: 123.45, prevClose: 100, oi: 1500, prevOi: 1200, volume: 900, iv: 14.57, bid: 123, ask: 124, dayHigh: 130, dayLow: 90, lastTradeAt: 1_790_000_000_000, delta: 0.4321 });
    expect(s.quotes[0].prevClose).toBeNull();
    expect(parsed!.ladders).toEqual({ NIFTY: ['2026-11-03'] });
  });

  it('takes the listed strike nearest spot when the source gives no ATM', () => {
    expect(encodeSeries(nifty, { ...chain, atm: null }, 1)!.atm).toBe(24600);
  });

  it('drops a chain without a priced spot', () => {
    expect(encodeSeries(nifty, { ...chain, spot: 0 }, 1)).toBeNull();
  });
});

describe('the demo provider', () => {
  const universe = [
    { symbol: 'NIFTY', name: 'Nifty 50', kind: 'index', exch: 'NSE', lot: 65 },
    { symbol: 'RELIANCE', name: 'Reliance', kind: 'stock', exch: 'NSE', lot: 500, sector: 'oil-gas' },
  ] as const;
  const demo = createDemoProvider(universe as never);

  it('lists expiries on the exchange weekdays, ascending', async () => {
    const nifty = await demo.expiries(universe[0] as never);
    expect(nifty.length).toBeGreaterThan(3);
    for (const date of nifty) expect(new Date(`${date}T00:00:00Z`).getUTCDay()).toBe(2);
    expect([...nifty].sort()).toEqual(nifty);
  });

  it('prices a chain the market file accepts, with calls above spot and puts below holding the most OI', async () => {
    const [expiry] = await demo.expiries(universe[1] as never);
    const chain = await demo.optionChain(universe[1] as never, expiry);
    const series = encodeSeries(universe[1], chain, chain.at)!;
    const parsed = parseMarketFile(marketFile({ at: chain.at, date: '2026-10-30', series: [series], minutes: [], ladders: {} }))!;
    const quotes = parsed.series[0].quotes;
    const top = (side: string) => quotes.filter(q => q.side === side).sort((a, b) => b.oi - a.oi)[0].strike;
    expect(top('CE')).toBeGreaterThan(chain.spot);
    expect(top('PE')).toBeLessThan(chain.spot);
  });

  it('gives futures months with ascending minute candles, the same on every read', async () => {
    const first = await demo.futures(universe[1] as never, '2026-10-30');
    const again = await demo.futures(universe[1] as never, '2026-10-30');
    expect(first).toEqual(again);
    expect(first[0].prevClose).toBeGreaterThan(0);
    const at = first[0].candles.map(c => c.at);
    expect([...at].sort((a, b) => a - b)).toEqual(at);
  });
});
