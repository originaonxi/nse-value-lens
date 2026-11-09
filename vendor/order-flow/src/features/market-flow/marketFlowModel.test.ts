import { describe, expect, it } from 'vitest';
import type { Underlying } from '@/lib/underlyings';
import type { ContractMarket, ContractQuote, ContractSeries } from '../options-scanner/contractScanModel';
import type { FuturesSeries } from '../options-scanner/futuresModel';
import { findAdvisoryPhrase } from '@/utils/marketVocabulary';
import {
  buildMarketFlow, compactUnits, oiProfile, DEFAULT_FLOW_SETTINGS, flowWhy, heaviestLevels, nearSeries, readZone, trimToSession, ZONE_SPAN_MINUTES, type FlowCandle, type FlowSettings,
} from './marketFlowModel';

const DATE = '2026-10-09';
const OPEN = Date.parse(`${DATE}T09:15:00+05:30`);
const MINUTE = 60_000;

const quote = (strike: number, side: 'CE' | 'PE', oi: number, prevOi: number | null = oi): ContractQuote => ({
  strike, side, ltp: 10, prevClose: 9, oi, prevOi, volume: 100, prevVolumeLots: 1, avgPrice: 10, iv: 20, bid: 9.9, ask: 10.1, bidQty: 1, askQty: 1,
  dayHigh: 11, dayLow: 9, lastTradeAt: OPEN, delta: 0.5,
});

function series(symbol: string, spot: number, prevClose: number | null, quotes: ContractQuote[], kind: 'index' | 'stock' = 'stock', expiry = '2026-10-27'): ContractSeries {
  return { symbol, kind, expiry, lot: 100, lotSource: 'catalogue', at: OPEN + 60 * MINUTE, spot, spotPrevClose: prevClose, atm: Math.round(spot / 10) * 10, quotes };
}

function market(list: ContractSeries[]): ContractMarket {
  return { at: OPEN + 60 * MINUTE, date: DATE, series: list, minutes: [], ladders: {} };
}

const underlying = (symbol: string, sector: string, kind: 'index' | 'stock' = 'stock'): Underlying =>
  ({ symbol, name: `${symbol} Ltd`, apiKey: `NSE:${symbol}`, lot: 100, kind, exch: 'NSE', sector });

/** A session of futures candles: price drifting by `drift` per minute, open interest by `oiStep`, over `minutes`. */
function candles(start: number, drift: number, oiStart: number, oiStep: number, minutes: number): FlowCandle[] {
  return Array.from({ length: minutes }, (_, i) => ({ at: OPEN + i * MINUTE, close: start + drift * i, oi: oiStart + oiStep * i }));
}

function futures(symbol: string, prevClose: number, prevOi: number, rows: FlowCandle[]): FuturesSeries {
  return { symbol, contractDate: '2026-10-27', months: ['2026-10-27'], prevClose, prevOi, candles: rows };
}

const SECTORS = { banks: 'Banks', metals: 'Metals' };

describe('readZone', () => {
  it('finds the stretch that added the most open interest while the price moved the side’s way', () => {
    // Twenty quiet minutes, then fifteen where price rises and open interest jumps, then quiet again.
    const quiet = candles(100, 0, 1000, 0, 20);
    const burst = Array.from({ length: 15 }, (_, i) => ({ at: OPEN + (20 + i) * MINUTE, close: 100 + i * 0.5, oi: 1000 + i * 100 }));
    const after = Array.from({ length: 10 }, (_, i) => ({ at: OPEN + (35 + i) * MINUTE, close: 107, oi: 2400 }));
    const { zone, note } = readZone([...quiet, ...burst, ...after], 'bullish');
    expect(note).toBeNull();
    expect(zone).not.toBeNull();
    expect(zone!.low).toBe(100);
    expect(zone!.high).toBe(107);
    expect(zone!.oiAdded).toBe(1400);
    expect(zone!.from).toBe(OPEN + 20 * MINUTE);
    expect(zone!.to).toBe(OPEN + 35 * MINUTE);
  });

  it('reads no zone when open interest only fell, and says so', () => {
    const { zone, note } = readZone(candles(100, 0.1, 5000, -10, 40), 'bullish');
    expect(zone).toBeNull();
    expect(note).toContain(`${ZONE_SPAN_MINUTES}-minute`);
  });

  it('needs the price to move the side’s way, not just open interest to grow', () => {
    const { zone } = readZone(candles(100, -0.1, 1000, 10, 40), 'bullish');
    expect(zone).toBeNull();
    expect(readZone(candles(100, -0.1, 1000, 10, 40), 'bearish').zone).not.toBeNull();
  });
});

describe('heaviestLevels', () => {
  it('takes the heaviest put at or below spot and the heaviest call at or above it', () => {
    const s = series('X', 1005, 1000, [
      quote(980, 'PE', 500), quote(1000, 'PE', 900, 700), quote(1020, 'PE', 2000),
      quote(1000, 'CE', 3000), quote(1020, 'CE', 1200, 1000), quote(1040, 'CE', 1500),
    ]);
    const [support, support2] = heaviestLevels(s, 'PE', 1005);
    const [resistance, resistance2] = heaviestLevels(s, 'CE', 1005);
    expect(support?.strike).toBe(1000);
    expect(support?.oiChange).toBe(200);
    expect(support2?.strike).toBe(980);
    expect(resistance?.strike).toBe(1040);
    expect(resistance2?.strike).toBe(1020);
    expect(resistance?.distancePct).toBeCloseTo(3.48, 2);
  });
});

describe('buildMarketFlow', () => {
  const universe = [underlying('AAA', 'banks'), underlying('BBB', 'banks'), underlying('CCC', 'banks'), underlying('DDD', 'metals'), underlying('NIFTY', '', 'index')];
  const quotes = [quote(95, 'PE', 1000, 800), quote(100, 'PE', 500), quote(105, 'CE', 1200, 1300), quote(110, 'CE', 800)];
  const file = market([
    series('AAA', 102, 100, quotes),
    series('BBB', 101, 100, quotes),
    series('CCC', 98, 100, quotes),
    series('DDD', 100.1, 100, quotes),
    series('NIFTY', 25000, 24800, quotes, 'index'),
  ]);
  const reads = new Map<string, FuturesSeries | null>([
    ['AAA', futures('AAA', 100, 10000, candles(100, 0.05, 10000, 20, 60))],   // up 3% with open interest up: Long build-up
    ['BBB', futures('BBB', 100, 10000, candles(100, 0.02, 10000, -10, 60))],  // up 1.2% with open interest down: Short covering
    ['CCC', futures('CCC', 100, 10000, candles(100, -0.04, 10000, 30, 60))],  // down 2.4% with open interest up: Short build-up
    ['DDD', null],                                                            // no future listed
  ]);
  const settings: FlowSettings = { ...DEFAULT_FLOW_SETTINGS };

  it('sorts every underlying onto a side from its future, spot standing in until the future is read', () => {
    const flow = buildMarketFlow(file, reads, universe, SECTORS, settings);
    const by = Object.fromEntries(flow.stocks.map(stock => [stock.symbol, stock]));
    expect(by.AAA.side).toBe('bullish');
    expect(by.AAA.source).toBe('futures');
    expect(by.AAA.buildUp).toBe('LONG_BUILD');
    expect(by.BBB.buildUp).toBe('SHORT_COVER');
    expect(by.CCC.side).toBe('bearish');
    expect(by.CCC.buildUp).toBe('SHORT_BUILD');
    // DDD: no future, so the spot's +0.1% stands in, which is inside the floor.
    expect(by.DDD.source).toBe('spot');
    expect(by.DDD.side).toBe('rangebound');
    expect(by.DDD.futures).toBe('unavailable');
    // NIFTY: not read yet; its spot (+0.81%) stands in on the Day window.
    expect(by.NIFTY.futures).toBe('pending');
    expect(by.NIFTY.side).toBe('bullish');
    expect(by.NIFTY.buildUp).toBeNull();
    expect(flow.futures).toMatchObject({ read: 3, unavailable: 1, failed: 0, pending: 1, total: 5 });
    expect(flow.futures.latestAt).toBe(OPEN + 60 * MINUTE);
  });

  it('keeps the build-up columns to futures that were read, and ranks each side by the size of the move, futures before spot', () => {
    const flow = buildMarketFlow(file, reads, universe, SECTORS, settings);
    expect(flow.buckets.LONG_BUILD.map(stock => stock.symbol)).toEqual(['AAA']);
    expect(flow.buckets.SHORT_COVER.map(stock => stock.symbol)).toEqual(['BBB']);
    expect(flow.buckets.SHORT_BUILD.map(stock => stock.symbol)).toEqual(['CCC']);
    expect(flow.buckets.LONG_UNWIND).toEqual([]);
    // NIFTY is bullish on its spot but has no future yet, so it is on the side and in no column.
    expect(flow.bullish.map(stock => stock.symbol)).toContain('NIFTY');
    // AAA (+3%) before BBB (+1.2%), both futures; NIFTY (+0.81% on the spot) after them.
    expect(flow.bullish.map(stock => [stock.symbol, stock.rank])).toEqual([['AAA', 1], ['BBB', 2], ['NIFTY', 3]]);
  });

  it('counts each sector’s sides and reads its lean', () => {
    const flow = buildMarketFlow(file, reads, universe, SECTORS, settings);
    const banks = flow.sectors.find(sector => sector.id === 'banks')!;
    expect(banks.label).toBe('Banks');
    expect(banks).toMatchObject({ count: 3, bullish: 2, bearish: 1, rangebound: 0 });
    expect(banks.lean).toBe('bullish');
    // Leader to laggard by the median move: banks (+1.2%), the index (+0.8% on its spot), metals (+0.1%).
    expect(flow.sectors.map(sector => sector.id)).toEqual(['banks', 'index', 'metals']);
    expect(flow.sectors[1].label).toBe('Indices');
    expect(banks.changePct).toBeCloseTo(1.18, 1);
  });

  it('leaves a check out, never fails it, when the figure it needs is missing', () => {
    const flow = buildMarketFlow(file, reads, universe, SECTORS, settings);
    const nifty = flow.stocks.find(stock => stock.symbol === 'NIFTY')!;
    const fresh = nifty.checks.find(check => check.id === 'fresh')!;
    expect(fresh.pass).toBeNull();
    expect(fresh.note).toBe('the future is not loaded yet');
    const aaa = flow.stocks.find(stock => stock.symbol === 'AAA')!;
    expect(aaa.checks.find(check => check.id === 'fresh')!.pass).toBe(true);
    expect(aaa.checks.find(check => check.id === 'spot')!.pass).toBe(true);
    // Puts added 200, calls closed 100: writers lean the bullish way.
    expect(aaa.checks.find(check => check.id === 'options')!.pass).toBe(true);
    expect(aaa.checks.find(check => check.id === 'sector')!.pass).toBe(true);
  });

  it('respects the floor and the scope', () => {
    const strict = buildMarketFlow(file, reads, universe, SECTORS, { ...settings, floorPct: 2 });
    expect(strict.bullish.map(stock => stock.symbol)).toEqual(['AAA']);
    expect(strict.bearish.map(stock => stock.symbol)).toEqual(['CCC']);
    expect(strict.rangebound.map(stock => stock.symbol).sort()).toEqual(['BBB', 'DDD', 'NIFTY']);
    const indices = buildMarketFlow(file, reads, universe, SECTORS, { ...settings, scope: 'indices' });
    expect(indices.stocks.map(stock => stock.symbol)).toEqual(['NIFTY']);
  });

  it('measures intraday windows from the candles and leaves unread futures without a side', () => {
    const hour = buildMarketFlow(file, reads, universe, SECTORS, { ...settings, window: '1h', floorPct: 0.5 });
    const aaa = hour.stocks.find(stock => stock.symbol === 'AAA')!;
    expect(aaa.fut?.priceChangePct).toBeCloseTo(3, 1);
    expect(aaa.checks.map(check => check.id)).toEqual(['fresh', 'day', 'quarter', 'options', 'sector']);
    const nifty = hour.stocks.find(stock => stock.symbol === 'NIFTY')!;
    expect(nifty.side).toBeNull();
    expect(hour.unread.map(stock => stock.symbol)).toEqual(['DDD', 'NIFTY']);
  });

  it('writes the reading in plain, descriptive words', () => {
    const flow = buildMarketFlow(file, reads, universe, SECTORS, settings);
    for (const stock of flow.stocks) {
      const copy = flowWhy(stock, 'day').join(' ');
      expect(findAdvisoryPhrase(copy), copy).toBeNull();
      for (const check of stock.checks) expect(findAdvisoryPhrase(`${check.label}. ${check.note}`), check.note).toBeNull();
    }
    const aaa = flow.stocks.find(stock => stock.symbol === 'AAA')!;
    const lines = flowWhy(aaa, 'day');
    expect(lines[0]).toMatch(/^AAA's future is \+2\.9\d% since the previous close with open interest \+11\.8\d%: a long build-up\.$/);
    expect(lines.some(line => line.startsWith('Open interest was added fastest between'))).toBe(true);
    expect(lines.at(-1)).toContain('heaviest put open interest at or below spot sits at 95');
  });
});

describe('data fixes', () => {
  const universe = [underlying('AAA', 'banks'), underlying('BBB', 'banks'), underlying('FINNIFTY', '', 'index'), underlying('CCC', 'metals')];
  const quotes = [quote(95, 'PE', 1000, 800), quote(105, 'CE', 1200, 1300)];
  const file = market([series('AAA', 102, 100, quotes), series('BBB', 97, 100, quotes), series('FINNIFTY', 24000, 24300, quotes, 'index'), series('CCC', 99, 100, quotes)]);

  it('tells a failed futures read apart from a future that is not listed', () => {
    const reads = new Map<string, FuturesSeries | null>([['AAA', null], ['FINNIFTY', null]]);
    const flow = buildMarketFlow(file, reads, universe, SECTORS, DEFAULT_FLOW_SETTINGS, { failed: new Set(['FINNIFTY']) });
    const by = Object.fromEntries(flow.stocks.map(stock => [stock.symbol, stock]));
    expect(by.FINNIFTY.futures).toBe('failed');
    expect(by.AAA.futures).toBe('unavailable');
    expect(by.FINNIFTY.zoneNote).toBe('its future could not be loaded');
    expect(flowWhy(by.FINNIFTY, 'day')[0]).toContain('its future could not be loaded');
    expect(flowWhy(by.AAA, 'day')[0]).toContain('no future is listed for it');
    expect(flow.futures).toMatchObject({ failed: 1, unavailable: 1, pending: 2 });
  });

  it('marks the counts provisional, and holds the large cards, until nearly every future is settled', () => {
    const one = new Map<string, FuturesSeries | null>([['AAA', futures('AAA', 100, 10000, candles(100, 0.05, 10000, 20, 60))]]);
    const early = buildMarketFlow(file, one, universe, SECTORS, DEFAULT_FLOW_SETTINGS);
    expect(early.provisional).toBe(true);
    expect(early.featured.bullish).toEqual([]);
    const all = new Map<string, FuturesSeries | null>([
      ['AAA', futures('AAA', 100, 10000, candles(100, 0.05, 10000, 20, 60))],
      ['BBB', futures('BBB', 100, 10000, candles(100, -0.05, 10000, 20, 60))],
      ['FINNIFTY', null],
      ['CCC', futures('CCC', 100, 10000, candles(100, -0.02, 10000, -10, 60))],
    ]);
    const done = buildMarketFlow(file, all, universe, SECTORS, DEFAULT_FLOW_SETTINGS);
    expect(done.provisional).toBe(false);
    // The strongest positions opened with the move lead; the side's largest futures moves fill in.
    expect(done.featured.bullish.map(stock => stock.symbol)).toEqual(['AAA']);
    expect(done.featured.bearish.map(stock => stock.symbol)).toEqual(['BBB', 'CCC']);
  });

  it('reads the levels from the next live expiry once the expiry dated today has settled', () => {
    const day = '2026-10-20';
    const close = Date.parse(`${day}T15:40:00+05:30`);
    const expiring = { ...series('NIFTY', 25000, 24900, quotes, 'index', day), at: close };
    const next = { ...series('NIFTY', 25000, 24900, quotes, 'index', '2026-10-27'), at: close };
    const file2 = { ...market([expiring, next]), date: day, at: close };
    // At 15:40 the file is the expiring series' final print: the next expiry is taken.
    expect(nearSeries(file2, 'NIFTY', close)?.expiry).toBe('2026-10-27');
    // During the session the expiring series is still live.
    const midday = Date.parse(`${day}T11:00:00+05:30`);
    expect(nearSeries({ ...file2, at: midday }, 'NIFTY', midday)?.expiry).toBe(day);
    // Nothing else listed: the expiring one is kept rather than nothing.
    expect(nearSeries({ ...file2, series: [expiring] }, 'NIFTY', close)?.expiry).toBe(day);
  });

  it('reads the futures up to 15:30, so the readings and the chart end together', () => {
    const late = futures('AAA', 100, 10000, Array.from({ length: 20 }, (_, i) => ({ at: Date.parse(`${DATE}T15:20:00+05:30`) + i * MINUTE, close: 100 + i, oi: 10000 })));
    const trimmed = trimToSession(late, DATE);
    expect(trimmed.candles).toHaveLength(10);
    expect(trimmed.candles.at(-1)!.at + MINUTE).toBe(Date.parse(`${DATE}T15:30:00+05:30`));
    const flow = buildMarketFlow(file, new Map([['AAA', late]]), universe, SECTORS, DEFAULT_FLOW_SETTINGS);
    expect(flow.stocks.find(stock => stock.symbol === 'AAA')!.fut!.price).toBe(109);
  });

  it('writes open interest in lakh and crore without trailing zeros', () => {
    expect(compactUnits(2_500_000)).toBe('25 L');
    expect(compactUnits(12_340_000)).toBe('1.23 Cr');
    expect(compactUnits(150_000)).toBe('1.5 L');
    expect(compactUnits(2_000)).toBe('2 K');
  });
});

describe('oiProfile', () => {
  it('keeps the strikes either side of spot with puts and calls added, low to high', () => {
    const rows = oiProfile({ spot: 101, quotes: [quote(95, 'PE', 100), quote(100, 'PE', 300), quote(100, 'CE', 50), quote(105, 'CE', 400), quote(110, 'CE', 0)] }, 1);
    expect(rows).toEqual([{ strike: 100, put: 300, call: 50 }, { strike: 105, put: 0, call: 400 }]);
  });
});
