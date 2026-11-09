/**
 * A map for the `http` provider: turn YOUR API's JSON into Order Flow's
 * shapes. Copy this file, change the three functions to match your API, then:
 *
 *   MF_PROVIDER=http
 *   MF_HTTP_BASE_URL=https://api.example.com
 *   MF_HTTP_EXPIRIES=/v1/expiries?underlying={symbol}
 *   MF_HTTP_CHAIN=/v1/optionchain?underlying={symbol}&expiry={expiry}
 *   MF_HTTP_FUTURES=/v1/futures/candles?underlying={symbol}&date={session}&interval=1m
 *   MF_HTTP_MAP=./examples/http-map.example.mjs
 *
 * Each function gets the parsed JSON of one response (and the underlying row
 * from public/underlyings.json) and returns Order Flow's shape. You may leave
 * a function out when the API already answers in that shape. Units still
 * matter: prices in rupees, open interest and volume in units (not lots).
 * Times may be epoch ms, epoch seconds or ISO strings; they are converted.
 */
export default {
  /** → ['YYYY-MM-DD', …] */
  expiries(json) {
    return json.result.expiry_dates;
  },

  /** → { expiry, at, spot, prevClose, atm, strikes: [{ strike, call: { ltp, oi, prevOi, volume, iv, … }, put: { … } }] } */
  optionChain(json, u, expiry) {
    return {
      expiry,
      at: json.result.timestamp,
      spot: json.result.underlying_ltp,
      prevClose: json.result.underlying_prev_close,
      strikes: json.result.rows.map(row => ({
        strike: row.strike_price,
        call: { ltp: row.ce.ltp, oi: row.ce.oi * u.lot, prevOi: row.ce.prev_oi * u.lot, volume: row.ce.volume * u.lot, iv: row.ce.iv },
        put: { ltp: row.pe.ltp, oi: row.pe.oi * u.lot, prevOi: row.pe.prev_oi * u.lot, volume: row.pe.volume * u.lot, iv: row.pe.iv },
      })),
    };
  },

  /** → [{ date, prevClose, prevOi, candles: [{ at, close, oi }] }], nearest month first */
  futures(json) {
    return json.result.contracts.map(contract => ({
      date: contract.expiry,
      prevClose: contract.prev_close,
      prevOi: contract.prev_oi,
      // [time, open, high, low, close, volume, oi] rows are understood as they are.
      candles: contract.candles,
    }));
  },
};
