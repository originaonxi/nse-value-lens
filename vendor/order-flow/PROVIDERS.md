# Connecting a market data provider

Order Flow's page talks only to its own server. The server gets every number from one **provider**: a small module with three methods. Write one for your broker and the whole board runs on it.

- The contract, with units and field meanings: [`server/providers/types.mjs`](server/providers/types.mjs)
- A working example (simulated): [`server/providers/demo.mjs`](server/providers/demo.mjs)
- A real broker example: [`server/providers/upstox.mjs`](server/providers/upstox.mjs)
- The starting point: [`server/providers/template.mjs`](server/providers/template.mjs)

## The quick way: any API, no code

Before you write an adapter, try the built-in `http` provider. It connects to any JSON API with settings and, if your API's shapes differ from ours, one small map file with up to three functions:

```bash
MF_PROVIDER=http
MF_HTTP_BASE_URL=https://api.example.com
MF_HTTP_CHAIN=/v1/optionchain?underlying={symbol}&expiry={expiry}
MF_HTTP_MAP=./my-api-map.mjs          # copy examples/http-map.example.mjs
npm run check:provider
```

The full list of settings is in the README, under [Connect any API](README.md#connect-any-api); `node examples/http-api-server.mjs` serves the exact shapes Order Flow expects. Write a full adapter (below) when your broker needs an instrument map, a login flow or batching that a plain URL cannot express.

## What a provider must return

| Method | Called | Returns |
|---|---|---|
| `init()` *(optional)* | once at start | Load instrument lists, check credentials. Throw with a clear message if something is missing. |
| `expiries(u)` | once per session per underlying | Live option expiries, ascending `YYYY-MM-DD`. |
| `optionChain(u, expiry)` | every minute per underlying | `{ expiry, at, spot, prevClose, atm, strikes: [{ strike, call, put }] }`. Each leg: `ltp, prevClose, oi, prevOi, volume, prevVolume, avgPrice, iv, bid, ask, bidQty, askQty, dayHigh, dayLow, lastTradeAt, delta` (unknown → `null`). |
| `futures(u, session)` | every 1–2 minutes per underlying | Up to three futures months, nearest first: `{ date, prevClose, prevOi, candles: [{ at, close, oi }] }`. `at` is the candle **start**, epoch ms, ascending; 09:15 is the first minute. |

Units: prices in **rupees** (not paise), open interest and volume in **units** (shares, not lots), times in **epoch milliseconds**, dates as IST `YYYY-MM-DD`. `u` is a row of `public/underlyings.json`: `{ symbol, name, kind: 'index'|'stock', exch: 'NSE'|'BSE', lot, sector }`.

What matters most for the board:

- `optionChain().spot` and `prevClose`: the spot move, until the future is read.
- `futures()` months with `prevClose`, `prevOi` and 1-minute candles: the direction, the move and the build-up.
- Option `oi` (and `prevOi` if you have it) by strike: support, resistance and the zone.

## Checklist

1. **Copy the template.** `cp server/providers/template.mjs server/providers/<broker>.mjs`, rename `createTemplateProvider`, set `id` and `label`.
2. **Register it** in `server/providers/index.mjs`: add `<broker>: create<Broker>Provider` to `PROVIDERS`.
3. **Credentials.** Read them from environment variables; add them, commented, to `.env.example`. Never commit real keys.
4. **Instrument map** (`init`). Most brokers publish an instrument list (CSV or JSON). From it, map each `symbol` in `public/underlyings.json` to the broker's id for:
   - the underlying (index or stock), for its option chain and quote;
   - its futures contracts with their expiry dates;
   - its option expiries.

   Index names differ between brokers (`NIFTY` / `Nifty 50` / `NIFTY 50`, `BANKNIFTY` / `Nifty Bank`). Map them explicitly. Log every symbol you could not map.
5. **`expiries(u)`.** From the instrument list if it has them (no API call needed), else from the broker's expiry endpoint.
6. **`optionChain(u, expiry)`.** Use the broker's option-chain endpoint if it has one. If it does not (Zerodha Kite, for example), build the chain from the instrument list plus batched quote calls for the strikes around spot (±20 strikes is plenty). Get `prevClose` of the underlying from a quote (`last price − net change`, or the previous day's close).
7. **`futures(u, session)`.** The nearest two or three futures with expiry on or after `session`. For each:
   - `prevClose`, `prevOi`: the previous session's daily candle;
   - `candles`: the session's 1-minute candles (the intraday endpoint for today, the historical endpoint for an earlier date), as `{ at: start ms, close, oi }`, ascending.
8. **Units.** Convert paise to rupees, lots to units, ISO strings to epoch ms, and sort candles ascending (many APIs return newest first).
9. **Rate limits.** The server reads about 220 chains a minute (8 at a time) and each underlying's futures every minute or two. Throttle inside your provider to the broker's limit (see the token bucket in `upstox.mjs`). If the limit is too low for the whole universe, use **Nifty 50** in the page, or cut `public/underlyings.json` down.
10. **Check it.** `MF_PROVIDER=<broker> npm run check:provider`, then fix every `FIX` line. Then `MF_PROVIDER=<broker> npm run dev`, open the page and confirm the status line names your broker.

## Verifying the Upstox adapter

`upstox.mjs` follows Upstox's documentation but has not yet been run against a live account. With your token:

```bash
MF_PROVIDER=upstox UPSTOX_ACCESS_TOKEN=... npm run check:provider
```

Things to confirm (each is marked `TODO` in the file where it applies):

- [ ] The instrument files load, and `underlying_symbol` matches our symbols for indices (`NIFTY`, `BANKNIFTY`, `SENSEX`, …).
- [ ] `/v2/option/chain` returns strikes for the nearest expiry; `market_data.oi` and `prev_oi` are in units.
- [ ] `/v2/market-quote/quotes` gives `last_price` and `net_change` for the underlying (the previous close).
- [ ] `/v3/historical-candle/intraday/.../minutes/1` returns today's 1-minute futures candles with OI; `/v3/historical-candle/.../minutes/1/<date>/<date>` returns an earlier session's.
- [ ] The token bucket keeps under the account's rate limit with all 217 underlyings.

## A prompt for your AI assistant

Paste this into Claude Code, Cursor, Copilot or any coding assistant, in this repository:

> Connect Order Flow to **<my broker>** (API docs: <link>). Read `PROVIDERS.md`, `server/providers/types.mjs`, `server/providers/template.mjs` and `server/providers/upstox.mjs`. Create `server/providers/<broker>.mjs` implementing `init`, `expiries`, `optionChain` and `futures` exactly as the contract describes (rupees, units, epoch ms, ascending candles with start times). Map every symbol in `public/underlyings.json` to the broker's instruments, with explicit index-name mapping. Read credentials from environment variables, add them to `.env.example`, register the provider in `server/providers/index.mjs`, throttle to the broker's rate limit, then run `MF_PROVIDER=<broker> npm run check:provider` and fix everything it reports. Do not change the page.

## How the server uses a provider

- At start: `init()`, then a first build of the market file.
- Every minute while the market moves (or always, for `alwaysLive` providers like the demo): `expiries` (cached per session) and `optionChain` for every underlying, eight at a time, encoded into `/api/market`. In market hours each build is also kept as a minute snapshot for the 15m and 1h windows.
- On demand: `futures` for `/api/futures/<SYMBOL>`, kept for a minute.
- `now()` *(optional)*: the provider's clock. Only the demo overrides it, to replay a session outside market hours.
