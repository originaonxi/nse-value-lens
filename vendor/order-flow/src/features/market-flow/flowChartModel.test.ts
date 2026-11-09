import { describe, expect, it } from 'vitest';
import { bandOf, changeTicks, chartReach, chartSpan, endLabel, lineOf, MINUTE, namedLines, pathOf, timeTicks, type FlowLine } from './flowChartModel';
import type { FlowStock, MarketFlow } from './marketFlowModel';

const DATE = '2026-10-09';
const OPEN = Date.parse(`${DATE}T09:15:00+05:30`);
const CLOSE = Date.parse(`${DATE}T15:30:00+05:30`);
const clock = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: false });

const stock = (symbol: string, minutes: number, from: number | null = null) => ({
  symbol,
  fut: { priceFrom: 100, from } as FlowStock['fut'],
  candles: Array.from({ length: minutes }, (_, i) => ({ at: OPEN + i * MINUTE, close: 100 + i * 0.1, oi: 1 })),
});

describe('the flow chart', () => {
  it('spans the session 09:15 to 15:30 for the day, and the last hour or 15 minutes read for the others', () => {
    const futures = { read: 1, unavailable: 0, failed: 0, pending: 0, total: 1, latestAt: Date.parse(`${DATE}T14:00:00+05:30`) };
    expect(chartSpan({ date: DATE, window: 'day', futures })).toEqual([OPEN, CLOSE]);
    expect(chartSpan({ date: DATE, window: '1h', futures })).toEqual([futures.latestAt - 60 * MINUTE, futures.latestAt]);
    expect(chartSpan({ date: DATE, window: '15m', futures: { ...futures, latestAt: CLOSE + 10 * MINUTE } })[1]).toBe(CLOSE);
  });

  it('starts a line at nought at the window start and ends it at its last candle, never stretched to the edge', () => {
    const line = lineOf(stock('AAA', 30), OPEN, CLOSE)!;
    expect(line.t[0]).toBe(OPEN);
    expect(line.v[0]).toBe(0);
    expect(line.t).toHaveLength(31);
    expect(line.t.at(-1)).toBe(OPEN + 30 * MINUTE);
    expect(line.v.at(-1)).toBeCloseTo(2.9, 5);
    const xOf = (ms: number) => (ms - OPEN) / MINUTE;
    const d = pathOf(line, xOf, v => -v);
    // Every minute drawn, and the last point is the last candle (x 30), not the right edge (x 375).
    expect(d.match(/L/g)).toHaveLength(30);
    expect(d.endsWith('L30.0,-2.9')).toBe(true);
  });

  it('restarts a 1h line from the reading’s own start, and has no line without a futures reading', () => {
    const from = OPEN + 10 * MINUTE;
    const line = lineOf(stock('AAA', 30, from), from, OPEN + 70 * MINUTE)!;
    expect(line.t[0]).toBe(from);
    expect(line.t[1]).toBe(OPEN + 11 * MINUTE);
    expect(lineOf({ symbol: 'X', fut: null, candles: [] }, OPEN, CLOSE)).toBeNull();
  });

  it('reaches the farthest point of a named line, never clamping it, with headroom', () => {
    const lines: FlowLine[] = [
      { symbol: 'BIG', t: [0, 1], v: [0, 6] },
      ...Array.from({ length: 100 }, (_, i) => ({ symbol: `S${i}`, t: [0, 1], v: [0, (i % 10) / 10] })),
    ];
    expect(chartReach(lines, new Set(['BIG']), 0.5)).toBeCloseTo(6 * 1.08, 5);
    expect(chartReach(lines, new Set(), 0.5)).toBeLessThan(2);
    expect(chartReach([], new Set(), 0.5)).toBeCloseTo(1.08, 5);
  });

  it('ticks whole percents for the day, quarters for an hour, tenths for 15 minutes, widening when crowded', () => {
    expect(changeTicks(3.2, 300, 'day')).toEqual([1, 2, 3]);
    expect(changeTicks(0.6, 300, '1h')).toEqual([0.25, 0.5]);
    expect(changeTicks(0.35, 300, '15m')).toEqual([0.1, 0.2, 0.3]);
    expect(changeTicks(8, 60, 'day').length).toBeLessThan(8);
  });

  it('puts day ticks at 09:15, the half hours and 15:30, fewer when narrow', () => {
    const wide = timeTicks(OPEN, CLOSE, 900, 'day').map(t => clock.format(t));
    expect(wide[0]).toBe('09:15');
    expect(wide.at(-1)).toBe('15:30');
    expect(wide).toContain('12:30');
    const narrow = timeTicks(OPEN, CLOSE, 300, 'day').map(t => clock.format(t));
    expect(narrow.length).toBeLessThan(wide.length);
    expect(narrow).not.toContain('15:00');
  });

  it('names the largest moves each side in the tiles’ order, futures only, never the index', () => {
    const s = (symbol: string, source: 'futures' | 'spot' = 'futures') => ({ symbol, source }) as FlowStock;
    const flow = { bullish: [s('A'), s('NIFTY'), s('B', 'spot'), s('C'), s('D')], bearish: [s('X'), s('Y')] } as unknown as MarketFlow;
    const named = namedLines(flow, 2, new Set(['A', 'NIFTY', 'B', 'C', 'D', 'X', 'Y']), 'NIFTY');
    expect(named.up.map(item => item.symbol)).toEqual(['A', 'C']);
    expect(named.down.map(item => item.symbol)).toEqual(['X', 'Y']);
  });

  it('summarises the lines as the middle 80% and the median, minute by minute', () => {
    const lines: FlowLine[] = Array.from({ length: 11 }, (_, i) => ({ symbol: `S${i}`, t: [OPEN, OPEN + MINUTE], v: [0, i - 5] }));
    const band = bandOf(lines, OPEN, OPEN + MINUTE);
    expect(band.mid.at(-1)).toBe(0);
    expect(band.lo.at(-1)).toBe(-4);
    expect(band.hi.at(-1)).toBe(4);
  });

  it('labels a line end as "PNB +5.21%"', () => {
    expect(endLabel('PNB', 5.211)).toBe('PNB +5.21%');
    expect(endLabel('IRFC', -2.98)).toBe('IRFC −2.98%');
  });
});
