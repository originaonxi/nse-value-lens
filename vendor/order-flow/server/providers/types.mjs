/**
 * The provider contract: what Order Flow needs from a market data source.
 *
 * A provider is a plain object with the members below. The server calls only
 * these; everything the page shows is built from what they return. Prices are
 * in rupees, open interest and volume in units (shares, not lots), times in
 * epoch milliseconds, dates as IST `YYYY-MM-DD`.
 *
 * To connect a new broker, copy ./template.mjs and follow PROVIDERS.md.
 *
 * @typedef {Object} Underlying       One row of public/underlyings.json.
 * @property {string} symbol          NSE/BSE F&O symbol: 'NIFTY', 'RELIANCE', 'M&M'.
 * @property {string} name
 * @property {'index'|'stock'} kind
 * @property {string} exch            'NSE' | 'BSE'
 * @property {number} lot             Contract lot size.
 *
 * @typedef {Object} OptionLeg        One side (call or put) of one strike.
 * @property {number} ltp
 * @property {number|null} prevClose  Previous session's close of this option, when known.
 * @property {number} oi
 * @property {number|null} prevOi     Previous session's closing open interest, when known.
 * @property {number} volume
 * @property {number|null} prevVolume
 * @property {number} avgPrice        Volume-weighted average traded price (ltp if the source has none).
 * @property {number|null} iv         Implied volatility, % (e.g. 14.2).
 * @property {number} bid
 * @property {number} ask
 * @property {number} bidQty
 * @property {number} askQty
 * @property {number|null} dayHigh
 * @property {number|null} dayLow
 * @property {number|null} lastTradeAt
 * @property {number|null} delta
 *
 * @typedef {Object} OptionChain      One expiry's chain.
 * @property {string} expiry          'YYYY-MM-DD'
 * @property {number} at              When the quotes were taken.
 * @property {number} spot            The underlying's last price.
 * @property {number|null} prevClose  The underlying's previous close.
 * @property {number|null} atm        At-the-money strike, if the source gives one (else the nearest strike is used).
 * @property {Array<{ strike: number, call?: OptionLeg, put?: OptionLeg }>} strikes
 *
 * @typedef {Object} FuturesCandle
 * @property {number} at              Candle START, epoch ms (09:15:00 for the first minute).
 * @property {number} close
 * @property {number} oi              Open interest at the candle's close, units.
 *
 * @typedef {Object} FuturesMonth     One futures contract for one session.
 * @property {string} date            The contract's expiry, 'YYYY-MM-DD'.
 * @property {number|null} prevClose  Its previous session's close.
 * @property {number|null} prevOi     Its previous session's closing open interest.
 * @property {FuturesCandle[]} candles The session's 1-minute candles, ascending.
 *
 * @typedef {Object} Provider
 * @property {string} id                         'demo', 'upstox', ...
 * @property {string} label                      Shown in the page's status line: 'Demo market', 'Upstox'.
 * @property {boolean} [alwaysLive]              True when the data moves outside market hours (the demo).
 * @property {() => Promise<void>} [init]        Called once at start (download instrument lists, check the token).
 * @property {() => number} [now]                The provider's clock; defaults to Date.now. The demo replays a session outside market hours.
 * @property {(u: Underlying) => Promise<string[]>} expiries         Live option expiries, ascending.
 * @property {(u: Underlying, expiry: string) => Promise<OptionChain>} optionChain
 * @property {(u: Underlying, session: string) => Promise<FuturesMonth[]>} futures
 *           The futures months listed on or after `session`, nearest first (at most three).
 *           An empty array means the underlying has no future.
 */
export {};
