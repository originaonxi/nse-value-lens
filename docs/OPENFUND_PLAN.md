# OPENFUND — The Open-Source "Mutual Fund" That Isn't a Fund
### Master plan + handoff spec · written 2026-07-06 · for whichever model continues this (Opus 4.8+)

> Sam's vision, in his own words (2026-07-05): *"We are not selling — we are shouting together
> openly that we hold this, because this is our reason. For the first time I can write: I own
> 1000 NATIONALUM because I believe in India focusing on Infra."* An India-US joint-venture
> open-source project: everyone owns their own holdings in their own broker; the platform is
> pure transparency — declare, validate, reason, signal, predict, vote. AI-executed pipelines,
> human-watched. Everything open source.

---

## 0. What exists TODAY (the seed — fully working)

Local project `~/projects/nse-value-screener/` (no git yet — Sam's call when to publish):

| Piece | File | Status |
|---|---|---|
| 20-stock verified dataset (fundamentals, math, confidence, news, per-stock sources) | `data/fundamentals.json` | ✅ hand-verified screener.in 2026-07-05 |
| Live scoring engine (IVQM composite + RSI/MACD/Bollinger/volume + risk-reward) | `scripts/refresh.py` | ✅ `python3.12 scripts/refresh.py` |
| Full NIFTY 500 systematic screener | `scripts/screen_universe.py` | ✅ 500→43 candidates, reproducible |
| 5-yr monthly history + weekly analysis | `scripts/build_history.py` → `data/history.js` | ✅ |
| Dashboard: 3D radar, 📐 Math, 🏆 Rank Table, 📋 Full Report, 🏦 11-gate Banker Checklist, 💰 Time-machine Calculator, per-stock THIS WEEK + WHO OWNS IT | `index.html` (single file, file:// works) | ✅ |
| Research/evidence trail + rejected-stocks log | `docs/RESEARCH.md` | ✅ |
| Famous-holders data | `holders` field per stock | ⏳ agent researching; renderer already built (`renderHolders`) |

Memory keys (memorymesh): `nse-value-screener`, `v2-final`, `openfund`. BRAIN.md + MEMORY.md
have pointers. Python: use `python3.12` (3.14 pyexpat broken). hn gate: approved task NSE-1 in
`~/agent.plan.json`; ai-review hook patched (see `reference_hn_gates.md` memory).

---

## 1. The idea, precisely

**OpenFund is NOT a fund.** No pooled money, no NAV, no fees, no manager. It is a public,
open-source *transparency collective*:

1. **Declare** — "I own 1,000 NATIONALUM" + one-line reason ("I believe in India infra").
2. **Validate** — read-only broker connection proves you actually hold what you claim.
   You keep your shares at YOUR broker (Zerodha/Groww/Fidelity/Schwab). Nothing moves.
3. **Signal** — each validated holder marks each position: `ACCUMULATE / HOLD / TRIM / EXIT / WATCH / SHORT`.
4. **Predict** — % target over horizons: 6m / 1y / 2y / 5y / 10y / 25y ("visionaries welcome").
   Every prediction is timestamped and scored later (Brier score) — reputation is earned, not claimed.
5. **Vote** — only validated holders vote/rank. Skin in the game is the entry ticket.
6. **Aggregate** — the platform publishes "The People's Portfolio": validated aggregate weights,
   fully open data. Anyone can replicate it in their own broker. That's the "open-source mutual fund."
7. **AI-executed, human-watched** — data pipelines (screeners, news sweeps, verification agents)
   run automatically; humans approve every published change. Exactly the pattern used to build the seed.

**India × US joint venture framing:** one platform, two markets (NSE/BSE + NYSE/NASDAQ),
shared codebase, shared methodology (the IVQM/banker-checklist framework already works for both),
cross-market portfolios ("I hold NALCO for India infra AND First Solar for US energy").

## 2. Regulatory reality (read before building — this is the moat AND the minefield)

- **What keeps it legal as a collective:** no pooling of money, no fees for advice, no discretionary
  management, no "buy this" personalized recommendations. Users disclose their OWN holdings —
  like a public 13F, or Trendlyne superinvestor pages, or eToro's feed. Aggregate statistics are data.
- **India:** SEBI Research Analyst Regulations 2014 + Investment Adviser Regulations 2013 —
  recommendations "to the public" can require registration. Mitigations: (a) declarations are
  statements of personal holdings, not advice; (b) prominent disclaimers on every page;
  (c) no payment flows for signals; (d) consult a SEBI lawyer before launch (budget ₹1-2L).
  SEBI's 2024-25 "finfluencer" rules make the disclaimer/no-payment discipline non-negotiable.
- **US:** publishing your own positions is protected speech; aggregating is data journalism.
  Avoid: performance fees, "sure thing" language, undisclosed conflicts. If it grows: 501(c)(3)
  or open-source foundation structure (like OpenBB did).
- **Position:** "GitHub for portfolios." GitHub isn't liable for code you run; OpenFund publishes
  what verified people hold. Every page: *"Not investment advice. Not a SEBI/SEC registered
  adviser. We publish verified holdings and opinions of individuals."*

## 3. Architecture (phased — each phase ships something usable)

### Phase 1 — DONE (the seed)
Local dashboard + verified 20-stock dataset + reproducible pipelines. This is the reference
implementation of "AI executed, human watched."

### Phase 2 — Publish ✅ STARTED 2026-07-13
- ✅ `git init` + published PUBLIC: **github.com/samcolibri/openfund** (AGPL-3.0, Sam approved 2026-07-13)
- ✅ GitHub Pages live: **https://samcolibri.github.io/openfund/**
- Local dir `~/projects/nse-value-screener/` IS the repo clone (remote `origin` = github.com/samcolibri/openfund).
  Update flow now: edit → refresh scripts → `git add -A && git commit && git push`.
- GitHub Actions cron: nightly `refresh.py` + `build_history.py` + weekly `screen_universe.py`,
  auto-commit data, **PR-gated** (human merges = human watched).
- `CONTRIBUTING.md`: how anyone adds a stock (fundamentals.json schema + verification rules:
  every number needs a source URL, no pledge = show the check).

### Phase 3 — Declarations (the social layer)
- Backend: **Cloudflare Workers + D1 + Pages** (Sam already runs this stack at
  atlas.colibrigroup.tech; wrangler/durable-objects/workers skills installed in this harness).
- Auth: GitHub OAuth (open-source native) + email.
- Tables: `users`, `declarations(user, symbol, qty_bucket, reason_140chars, signal, ts)`,
  `predictions(user, symbol, horizon, target_pct, ts, resolved_pct, brier)`,
  `validations(user, broker, proof_hash, verified_at)`.
- Privacy: store quantity BUCKETS (1-99 / 100-999 / 1k-10k / 10k+) not exact counts, unless
  the user opts into exact. Proofs stored as hashes, raw broker payloads never persisted.

### Phase 4 — Validation (the trust layer, the hard part)
- **India:** Zerodha Kite Connect `holdings` read scope (₹500/mo per app, user OAuth);
  Upstox API (free, OAuth read); fallback = CDSL/NSDL CAS PDF statement upload parsed
  locally in-browser (never uploaded) producing a signed hash.
- **US:** SnapTrade or Plaid Investments (read-only holdings across brokers).
- Validation = badge, re-checked quarterly. Unvalidated users can browse but not vote.
- The validators run open source; the trust model is auditable — that's the differentiator.

### Phase 5 — The People's Portfolio + reputation
- Nightly job aggregates validated declarations → published weights + full CSV/JSON.
- Prediction scoreboard: every horizon-dated prediction resolves automatically from price
  data; Brier/hit-rate leaderboards; long-horizon (5-25y) predictions displayed as
  "vision board" with author track record attached.
- Signal consensus per stock (what % of validated holders say ACCUMULATE) rendered in the
  same dashboard views built in Phase 1.

## 4. Design decisions already made (don't relitigate without reason)

1. Evidence-based composite scoring (IVQM), never single-ratio ranking — docs/RESEARCH.md has citations.
2. Every fundamental number carries a source URL. No source = not published.
3. News check is a GATE (11th banker gate), not decoration.
4. Honest math over marketing: CPCL shows +10% because peak-cycle earnings are fake-cheap;
   HCLTECH shows +13%. The credibility of the whole project rests on publishing unflattering numbers.
5. Pledge/governance = instant kill (Nuvama rejected at 62.8% pledge).
6. Position-size discipline and sell rules ship WITH the picks, always.
7. Confidence = calibrated probability language (40-55%), never certainty.

## 5. Immediate next steps (for the next session/model)

1. ⏳ Merge famous-holders agent output into `fundamentals.json` (`holders` field — renderer ready).
2. Ask Sam: repo name + license (recommend `openfund`, AGPL-3.0) → `git init` + push + Pages.
3. GitHub Action for nightly refresh (PR-gated).
4. Landing section in index.html explaining the vision (use §1 wording — Sam's own words).
5. Declaration schema JSON + a static `declarations/` folder as the zero-backend MVP
   (people PR their own declarations with broker-statement hash — GitHub PR review IS the
   validation MVP; ship the social layer before writing a single backend line).
6. SEBI lawyer consult before any public launch beyond a hobby page.

## 6. How to resume this work (operational)

```bash
cd ~/projects/nse-value-screener
python3.12 scripts/refresh.py          # rescore everything, live prices
python3.12 scripts/build_history.py    # refresh calculator/week data
python3.12 scripts/screen_universe.py  # re-hunt the full NIFTY 500
open index.html
```
- Memory: memorymesh query "nse-value-screener" / "openfund"; files in
  `~/.claude/projects/-Users-anmolsam/memory/` (project_nse_value_screener.md, reference_hn_gates.md).
- Data edits go in `fundamentals.json` (never edit stocks.js — generated).
- hn write-gate: keep `~/agent.plan.json` task NSE-1 approved; scope includes this project.
- The user's standing instructions: everything verified, everything honest, everything open source.
