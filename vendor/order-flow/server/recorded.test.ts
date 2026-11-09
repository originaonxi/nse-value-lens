import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { gzipSync } from 'node:zlib';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRecordedProvider } from './providers/recorded.mjs';

const DATE = '2026-10-30';
const OPEN = Date.parse(`${DATE}T09:15:00+05:30`);
const MIN = 60_000;
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'of-recorded-'));
const reliance = { symbol: 'RELIANCE', name: 'Reliance', kind: 'stock', exch: 'NSE', lot: 500 } as never;

beforeAll(() => {
  // A full session of futures rising 1 rupee a minute from 1000; the chain snapshot taken at the close.
  const candles = Array.from({ length: 375 }, (_, i) => ({ at: OPEN + i * MIN, close: 1000 + i, oi: 1_000_000 + i * 100 }));
  const chain = { expiry: '2026-11-24', at: OPEN + 375 * MIN, spot: (1000 + 374) * 0.998, prevClose: 990, atm: 1370, strikes: [{ strike: 1370, call: { ltp: 10, oi: 5000 }, put: { ltp: 9, oi: 4000 } }] };
  const day = { schema: 1, date: DATE, recordedAt: '', source: 'test', note: '', chains: { RELIANCE: { ladder: ['2026-11-24', '2026-12-29'], chain } }, futures: { RELIANCE: [{ date: '2026-11-24', prevClose: 995, prevOi: 1_000_000, candles }] } };
  fs.writeFileSync(path.join(dir, `${DATE}.json.gz`), gzipSync(JSON.stringify(day)));
  process.env.MF_RECORDED_DIR = dir;
});
afterAll(() => { delete process.env.MF_RECORDED_DIR; fs.rmSync(dir, { recursive: true, force: true }); });

describe('the recorded provider', () => {
  it('replays the recorded day on a session clock, naming it', async () => {
    const recorded = createRecordedProvider();
    await recorded.init();
    expect(recorded.label).toBe('Recorded 30 Oct 2026');
    const at = recorded.now();
    expect(at).toBeGreaterThanOrEqual(OPEN + 5 * MIN);
    expect(at).toBeLessThan(OPEN + 375 * MIN);
    expect(await recorded.expiries(reliance)).toEqual(['2026-11-24', '2026-12-29']);
  });

  it('shows futures only up to the replay clock, and only for its own session', async () => {
    const recorded = createRecordedProvider();
    await recorded.init();
    const [near] = await recorded.futures(reliance, DATE);
    const at = recorded.now();
    expect(near.candles.length).toBeGreaterThan(0);
    expect(near.candles.every(c => c.at + MIN <= at)).toBe(true);
    expect(await recorded.futures(reliance, '2026-10-29')).toEqual([]);
  });

  it('moves the chain\'s spot with the future, keeping the snapshot\'s ratio', async () => {
    const recorded = createRecordedProvider();
    await recorded.init();
    const chain = await recorded.optionChain(reliance, '2026-11-24');
    const [near] = await recorded.futures(reliance, DATE);
    const last = near.candles.at(-1)!.close;
    expect(chain.spot).toBeCloseTo(last * 0.998, 1);
    expect(chain.prevClose).toBeCloseTo(995 * 0.998, 1);
    expect(chain.strikes).toHaveLength(1);
  });

  it('says how to fix a missing recording', async () => {
    process.env.MF_RECORDED_DATE = '2020-01-01';
    try {
      await expect(createRecordedProvider().init()).rejects.toThrow(/No recorded session for 2020-01-01/);
    } finally {
      delete process.env.MF_RECORDED_DATE;
    }
  });
});
