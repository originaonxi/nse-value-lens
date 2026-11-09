# Vendored copy of MrChartist/order-flow

Required Notice: Copyright (c) 2026 Mr. Chartist (https://mrchartist.com)

- Source: https://github.com/MrChartist/order-flow at commit `767b9db2cfb2bbf2ad4ce87566dc2b83860e6ba6`
- Licence: PolyForm Noncommercial License 1.0.0 (see `LICENSE` in this folder). Free for personal, non-commercial use;
  any commercial use needs a separate licence from Mr. Chartist.
- Guide: https://mrchartist.com/open-source/order-flow

## What is here
The app's own code exactly as published: `src/`, `server/`, `scripts/`, `examples/`, `package.json`, configs, `README.md`,
`PROVIDERS.md`, `NOTICE.md`, `LICENSE`. Run it locally from this folder: `npm install`, `npm run fetch:nse`, `npm run dev:archive`,
then open http://127.0.0.1:5195.

## What was left out, and why
- `public/brand/underlyings/` - company logos, trademarks of their owners, not covered by the Order Flow licence (see NOTICE.md).
  The app falls back to text marks without them.
- `data/recorded/`, `data/archive/` session files - exchange/vendor data under their own terms (see NOTICE.md); `npm run fetch:nse`
  rebuilds a session from NSE's public archive.
- `docs/media`, screenshots and `.github/` - not needed to run it.

## How NSE Value Lens uses it
`order_flow.py` ports the board's maths (build-up, the conviction checks, strength, option-OI levels) to Python and runs it on
NSE's F&O bhavcopy after every close for `docs/orderflow.html`. The live minute-by-minute board stays in this folder.
