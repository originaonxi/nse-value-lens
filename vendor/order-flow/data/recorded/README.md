# Recorded sessions

Real Indian F&O sessions, replayed by the `recorded` provider (`npm run dev:recorded`).

| File | Session | What it holds |
|---|---|---|
| `2026-10-29.json.gz` | Thu 29 Oct 2026 | 1-minute futures candles (near and next month, with open interest) for 211 underlyings; option chains for 213 |
| `2026-10-30.json.gz` | Fri 30 Oct 2026 | the same for Friday |

**Source.** Recorded on 31 Oct 2026 from a licensed live market-data feed with `scripts/record-session.mjs`. Futures are each session's own candles. Option chains could only be read as they stood after Friday's close, so both files carry that same chain snapshot; the provider moves each chain's spot with the day's futures, minute by minute. ICICIPRULI could not be read and is absent.

**Terms.** This data is included to demonstrate the software. It is not covered by the Order Flow licence, is not investment advice and must not be used for trading. Exchange and index data remain subject to the terms of NSE, BSE and the data vendor; if you redistribute this repository, you are responsible for complying with them, or you can delete this folder (the app falls back to the simulated demo market).

**Format** (`schema: 1`, gzipped JSON): `{ date, recordedAt, source, note, chains: { SYMBOL: { ladder, chain } }, futures: { SYMBOL: FuturesMonth[] } }`. Shapes as in `server/providers/types.mjs`.

**Record your own.** With your broker connected (see PROVIDERS.md), on or after the day:

```bash
MF_PROVIDER=upstox UPSTOX_ACCESS_TOKEN=... npm run record -- 2026-11-03
```
