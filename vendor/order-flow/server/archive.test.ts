import { describe, expect, it } from 'vitest';
import { buildSession, marketWalk, parseBhavcopy, rebuildOi, rebuildPath, unitsTraded } from '../scripts/fetch-nse-archive.mjs';

const HEAD = 'TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4';
const CSV = [
  HEAD,
  '2026-11-06,2026-11-06,FO,NSE,STF,1,,RELIANCE,,2026-11-23,2026-11-23,,,RELIANCE26NOVFUT,1301.00,1325.00,1301.00,1323.00,1321.20,1315.90,1319.99,1323.00,136395500,61000,29287,19271864800.00,,F1,500,,,,,',
  '2026-11-06,2026-11-06,FO,NSE,STO,2,,RELIANCE,,2026-11-23,2026-11-23,1320.00,CE,RELIANCE26NOV1320CE,20,30,18,24.85,24.85,21.45,1319.99,24.85,10355000,-385500,4434,2946000000,,F1,500,,,,,',
  '2026-11-06,2026-11-06,FO,NSE,STO,3,,RELIANCE,,2026-11-23,2026-11-23,1320.00,PE,RELIANCE26NOV1320PE,25,34,21.4,22.3,22.3,25.45,1319.99,22.3,1407500,-13500,11650,15530000000,,F1,500,,,,,',
].join('\n');

describe('NSE archive builder', () => {
  it('parses a UDiFF bhavcopy', () => {
    const rows = parseBhavcopy(CSV);
    expect(rows).toHaveLength(3);
    expect(rows[0]).toMatchObject({ type: 'STF', symbol: 'RELIANCE', expiry: '2026-11-23', open: 1301, high: 1325, close: 1323, oi: 136395500, lot: 500 });
  });

  it('reads volume in units whether the exchange reports contracts or units', () => {
    const [fut] = parseBhavcopy(CSV);
    expect(unitsTraded(fut)).toBe(29287 * 500);
    expect(unitsTraded({ ...fut, volume: 29287 * 500 })).toBe(29287 * 500);
  });

  it('rebuilds a path that opens, peaks, bottoms and closes on the real figures', () => {
    const bar = { open: 1301, high: 1325, low: 1298, close: 1323 };
    const path = rebuildPath(bar, 'x', marketWalk('2026-11-06'));
    expect(path).toHaveLength(375);
    expect(path[0]).toBe(1301);
    expect(path.at(-1)).toBe(1323);
    expect(Math.max(...path)).toBe(1325);
    expect(Math.min(...path)).toBe(1298);
    expect(rebuildPath(bar, 'x', marketWalk('2026-11-06'))).toEqual(path); // deterministic
  });

  it('moves open interest from the previous OI to the real closing OI in whole lots', () => {
    const oi = rebuildOi(136334500, 136395500, 500, 'x');
    expect(oi.at(-1)).toBe(136395500);
    expect(oi.every(v => v % 500 === 0)).toBe(true);
  });

  it('builds the chain and futures in the recorded-session shape', () => {
    const u = { symbol: 'RELIANCE', name: 'Reliance', kind: 'stock', exch: 'NSE', lot: 500 };
    const { chains, futures } = buildSession('2026-11-06', { NSE: parseBhavcopy(CSV) }, {}, [u]);
    const chain = chains.RELIANCE.chain;
    expect(chain).toMatchObject({ expiry: '2026-11-23', spot: 1319.99 });
    expect(chain.strikes[0].call).toMatchObject({ ltp: 24.85, oi: 10355000, prevOi: 10740500, volume: 4434 * 500 });
    expect(futures.RELIANCE[0]).toMatchObject({ date: '2026-11-23', prevClose: 1315.9, prevOi: 136334500 });
    expect(futures.RELIANCE[0].candles[0].at).toBe(Date.parse('2026-11-06T09:15:00+05:30'));
  });
});
