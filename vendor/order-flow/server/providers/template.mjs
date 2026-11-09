/**
 * TEMPLATE: connect Order Flow to your broker or data vendor.
 *
 * Copy this file to ./<broker>.mjs, register it in ./index.mjs, set
 * MF_PROVIDER=<broker>, and fill in the three methods. The contract (units,
 * shapes, what each field means) is in ./types.mjs; the full checklist,
 * written so an AI assistant can follow it, is in PROVIDERS.md.
 *
 * TODO list:
 *   [ ] 1. Credentials: read them from environment variables (never commit them).
 *   [ ] 2. init(): load your broker's instrument list and map each F&O symbol in
 *          public/underlyings.json to the broker's ids: the underlying (for
 *          its option chain and quote) and its futures contracts.
 *   [ ] 3. expiries(u): the live option expiries for `u`, ascending 'YYYY-MM-DD'.
 *   [ ] 4. optionChain(u, expiry): every strike's call and put for that expiry,
 *          in rupees and units, plus spot and the underlying's previous close.
 *   [ ] 5. futures(u, session): the nearest futures months (up to three) with
 *          their previous close and OI and the session's 1-minute candles
 *          (candle START times, ascending, close price and OI at the close).
 *   [ ] 6. Rate limits: the server reads ~220 chains a minute and futures for
 *          every underlying every two minutes; throttle to your broker's limit.
 *   [ ] 7. Run `npm run check:provider` and fix what it reports.
 */

export function createTemplateProvider(universe) {
  // TODO 1: credentials
  const apiKey = process.env.MYBROKER_API_KEY;

  return {
    id: 'template',
    label: 'My broker',

    async init() {
      if (!apiKey) throw new Error('Set MYBROKER_API_KEY.');
      // TODO 2: download the instrument list and build symbol → ids.
      throw new Error('template provider: fill in server/providers/template.mjs (see PROVIDERS.md).');
    },

    // TODO 3
    async expiries(u) {
      return [];
    },

    // TODO 4
    async optionChain(u, expiry) {
      return { expiry, at: Date.now(), spot: 0, prevClose: null, atm: null, strikes: [] };
    },

    // TODO 5
    async futures(u, session) {
      return [];
    },
  };
}
