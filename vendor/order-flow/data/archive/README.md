# NSE archive sessions

Real Indian F&O sessions built from the exchanges' public end-of-day files, replayed by the `archive` provider (`npm run dev:archive`).

| File | Session | What it holds |
|---|---|---|
| `2026-11-06.json.gz` | Fri 6 Nov 2026 | Real closing option chains (nearest expiry, 30 strikes either side of spot) for 213 underlyings; futures for 214 with real open, high, low, close, previous close and open interest |

**Source.** The F&O bhavcopy (UDiFF) published by NSE (`nsearchives.nseindia.com`) and BSE (`bseindia.com`), built with `npm run fetch:nse` (`scripts/fetch-nse-archive.mjs`). BAJAJHLDNG, DALBHARAT and ICICIPRULI were not in that day's file and are absent.

**What is real and what is rebuilt.** Every closing figure is the exchange's own: option open interest and its change, premiums, volume, the underlying's price, and each future's open, high, low, close, previous close and open interest. A bhavcopy has no intraday data, so each future's 1-minute path is rebuilt between those real points (it opens at the open, touches the high and low, closes at the close), deterministically.

**Build your own.** `npm run fetch:nse` (the latest published session) or `npm run fetch:nse -- 2026-11-06 2026-11-05`. Downloads are cached in `.cache/`, which git ignores.

**Terms.** This data is included to demonstrate the software. It is not covered by the Order Flow licence, is not investment advice and must not be used for trading. Exchange and index data remain subject to the terms of NSE and BSE; if you redistribute this repository, you are responsible for complying with them, or you can delete this folder (the app falls back to the recorded sessions and the simulated demo market).

**Format** (`schema: 1`, `kind: "archive"`, gzipped JSON): the recorded-session format (`data/recorded/README.md`).
