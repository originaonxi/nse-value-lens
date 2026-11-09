# Contributing

Thanks for helping. Order Flow is small on purpose: one page, one server, a provider per data source.

## Set up

```bash
npm install
npm run dev          # server with the demo market on :8787, page on :5195
```

Node 22.18 or newer. No keys are needed: the demo market feeds everything.

## Before you open a pull request

```bash
npm run lint
npm test
npm run build
npm audit
```

All four must pass; CI runs the same.

## What makes a good change

- **A new broker.** Add `server/providers/<broker>.mjs` following [PROVIDERS.md](PROVIDERS.md), register it in `server/providers/index.mjs`, and include the output of `MF_PROVIDER=<broker> npm run check:provider`. Never commit credentials; read them from environment variables and add them, commented, to `.env.example`.
- **The board.** Keep it readable at a glance: one idea per change, screenshots in light and dark for anything visual, and tests for model changes (`src/features/market-flow/*.test.ts`).
- **The server.** It is public-facing when deployed. Keep it read-only (GET/HEAD), validate every input, and never send provider errors or secrets to the browser. See the Security section of the README.

## Style

TypeScript in the page, plain ESM JavaScript in the server (no build step there). Match the surrounding code: comments explain why, names say what. `npm run lint` catches the rest.

## Licence of contributions

Order Flow is free for personal, non-commercial use under the PolyForm Noncommercial License, and [Mr. Chartist](https://mrchartist.com) offers commercial licences. By opening a pull request you agree that your contribution is licensed under the same terms, and that Mr. Chartist may also include it in commercially licensed versions.

## Reporting security issues

Please don't open a public issue. See [SECURITY.md](SECURITY.md).
