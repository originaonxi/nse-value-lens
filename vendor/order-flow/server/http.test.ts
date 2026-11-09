import { describe, expect, it } from 'vitest';
import { createHttpProvider, fillTemplate, normaliseChain, normaliseExpiries, normaliseFutures, toMs } from './providers/http.mjs';

const U = { symbol: 'M&M', name: 'Mahindra', kind: 'stock', exch: 'NSE', lot: 200, apiKey: 'NSE_EQ|INE101A01026' };

describe('http provider', () => {
  it('fills templates with encoded values', () => {
    expect(fillTemplate('/chain/{symbol}?expiry={expiry}&k={apiKey}', { symbol: 'M&M', expiry: '2026-11-23', apiKey: 'NSE_EQ|X' }))
      .toBe('/chain/M%26M?expiry=2026-11-23&k=NSE_EQ%7CX');
  });

  it('reads epoch ms, epoch seconds and ISO times', () => {
    expect(toMs(1793936700000)).toBe(1793936700000);
    expect(toMs(1793936700)).toBe(1793936700000);
    expect(toMs('2026-11-06T09:15:00+05:30')).toBe(Date.parse('2026-11-06T09:15:00+05:30'));
  });

  it('normalises expiries, chains and futures from loose shapes', () => {
    expect(normaliseExpiries({ data: ['2026-11-30T00:00:00Z', '2026-11-23', '2026-11-23'] })).toEqual(['2026-11-23', '2026-11-30']);
    const chain = normaliseChain({ spot: '3500.5', strikes: [{ strike: 3600, CE: { last_price: 12, oi: 1000 } }, { strike: 3400, pe: { ltp: 9 } }] }, '2026-11-23');
    expect(chain.expiry).toBe('2026-11-23');
    expect(chain.spot).toBe(3500.5);
    expect(chain.strikes.map(s => s.strike)).toEqual([3400, 3600]);
    expect(chain.strikes[1].call).toMatchObject({ ltp: 12, oi: 1000, prevOi: null, iv: null, avgPrice: 12 });
    const months = normaliseFutures({ months: [{ expiry: '2026-12-29', candles: [] }, { date: '2026-11-23', prevClose: 10, candles: [[1793936760, 1, 2, 0.5, 1.5, 100, 4000], [1793936700, 1, 2, 0.5, 1.2, 100, 3800]] }] });
    expect(months.map(m => m.date)).toEqual(['2026-11-23', '2026-12-29']);
    expect(months[0].candles).toEqual([{ at: 1793936700000, close: 1.2, oi: 3800 }, { at: 1793936760000, close: 1.5, oi: 4000 }]);
  });

  it('calls the configured routes with the token and reshapes through a map', async () => {
    const seen: { url: string; auth?: string }[] = [];
    const fetcher = async (url: string, init: { headers: Record<string, string> }) => {
      seen.push({ url, auth: init.headers.Authorization });
      return { ok: true, status: 200, json: async () => ({ result: ['2026-11-23'] }) } as Response;
    };
    const provider = createHttpProvider([U], { MF_HTTP_BASE_URL: 'https://api.example.com/', MF_HTTP_TOKEN: 't0k', MF_HTTP_EXPIRIES: '/x/{symbol}/{exch}' }, fetcher);
    await provider.init();
    expect(await provider.expiries(U)).toEqual(['2026-11-23']);
    expect(seen[0]).toEqual({ url: 'https://api.example.com/x/M%26M/NSE', auth: 'Bearer t0k' });
  });

  it('asks for a base URL', async () => {
    await expect(createHttpProvider([U], {}).init()).rejects.toThrow(/MF_HTTP_BASE_URL/);
  });
});
