# Research Notes — 2026-07-05

Three parallel research sweeps (tools/repos, formula evidence, live H1-2026 candidates).
Everything marked [LIVE-TESTED] was executed on this Mac on 2026-07-05.

---

## 1. Data stack (what works in July 2026)

| Need | Use | Status |
|------|-----|--------|
| Daily OHLCV .NS | **yfinance v1.5.1** (`RELIANCE.NS` etc.) | [LIVE-TESTED] works; chunk ~50/batch |
| Official EOD cross-check | NSE UDiFF bhavcopy `https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip` | [LIVE-TESTED] plain curl + browser UA |
| Universe list | `https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv` | [LIVE-TESTED] 501 lines, needs UA header |
| Fundamentals (ROCE, promoter, pledging) | **screener.in** company pages / screen export (free login) | only reliable free source |
| Interactive technical scans | **PKScreener** (`pip install pkscreener`) — 366★, pushed daily | best maintained NSE screener |
| NSE-native prices | jugaad-data (536★, maintained) | works; timestamps need IST fix |
| AVOID | nsepy, nsetools (dead since 2023); nsepython (Akamai-blocked [LIVE-TESTED] `{}` response); www.nseindia.com/api directly | |

Smallcase methodology patterns (public): Windmill CANSLIM-esque/GEM-Q (EPS growth + momentum),
Value & Momentum (discount-to-peers × 6-12m momentum), Wright Research multifactor + regime ML.
All reduce to: rank NIFTY 500 on 2-3 factor z-scores, top 15-25, rebalance monthly.

## 2. Formula evidence (IVQM composite)

- **Magic Formula in India**: 30-stock portfolio 13.9% CAGR vs 9.3% Sensex FY12-20 (SSRN 3945468)
- **Piotroski F-Score**: strongest India value-trap filter — F 7-9 portfolios significantly beat index on top-500 NSE (IJEF 2015); screener.in computes it natively
- **Value+Momentum**: correlation −0.49, 50/50 combo ~doubles Sharpe (AQR JF 2013); Capitalmind Trending Value on NSE 2007-23: ₹100→₹1,921 vs ₹448 Nifty 50; beats in 59% of 1-yr / 70% of 3-yr windows
- **52-wk-high proximity**: George & Hwang JF 2004, works in 18/20 markets
- **Momentum in India**: significant at 6-12m in LIQUID stocks only (PBFJ 2023); Nifty200 Momentum 30 beat parent 13/16 years; raw momentum has −70% drawdowns → needs quality sleeve
- **India hard gates**: promoter pledging ≤5% (pledge cascades destroy 50-90% — Zee/ADAG/CG Power), promoter selling >2%/yr, CFO/PAT ≥0.8 (5-yr, catches Satyam-style books), auditor resignations, ASM/GSM surveillance lists, D/E<1, interest coverage>3
- Weights: Value 30 / Quality 30 / Momentum 25 / Safety 15. Composites beat single ratios 82% of the time (O'Shaughnessy)

Screener.in ready-to-paste base screen:
```
Market Capitalization > 2000 AND Pledged percentage < 5 AND Promoter holding > 40 AND
Debt to equity < 1 AND Interest Coverage Ratio > 3 AND Piotroski score >= 6 AND
Return on capital employed > 15 AND Average return on capital employed 5Years > 15 AND
Sales growth 5Years > 10 AND Earnings yield > 6 AND PEG Ratio < 1.5 AND
Current price > DMA 200 AND DMA 50 > DMA 200 AND Return over 6months > 5 AND Return over 1year > 0
```

Realistic expectations: ~4-8% annualized excess over benchmark across cycles; 50-60% individual
winners; +20-30% in 6-18mo plausible in trending regimes, unlikely in flat/bear ones.

## 3. H1 2026 market recap (verified, dated)

- Nifty peak 26,373 (Jan 5) → low 22,182 (−15.9%, March worst) → 23,865.75 (Jun 30, +1.67% June) → 24,271 (Jul 3). H1: −7.1%
- Trigger: Strait of Hormuz crisis (US-Israel strike on Iran), Brent $60s → $120+ peak; ceasefire collapsed crude in June
- Record FPI exodus ~₹2.2 lakh cr ($30.6B) by early June — worst since 1993; March alone −₹1.17 lakh cr
- FPI ownership 14.7% (14-yr low); DIIs 18.9% now own more than FPIs; SIPs ₹32,000 cr/month record
- INR: 89.86 (Jan) → 96.84 all-time low (May 20) → ~94.35 (late June)
- RBI: repo held 5.25% (Feb & June); FY27 growth cut to 6.6%, inflation forecast raised to 5.1%
- Budget Feb 1: fiscal deficit target 4.3% GDP
- June sectors: Private Bank +6.43%, Bank +6.41%, FinServ +5.11% vs IT −9.56%, Metal −6.51%
- IT wreck: TCS/INFY/WIPRO/HCLTECH 52-week lows on Jul 1 (AI-disruption fears); Kotak cut estimates Jul 3
- GST June: ₹1,94,812 cr +13.9% YoY — domestic demand intact

## 4. Rejected candidates (and why)

- TMB — at 52-wk high, +80% off low (chasing); MOTILALOFS — Q4 net loss ₹219 cr; FEDERALBNK — PE 18.6 at high;
  GAIL/POWERGRID — ROCE <15 + falling/flat profits; VEDL — 15.5% yield but D/E ~2.2 + promoter leverage (optional
  high-risk slot only); BPCL — street TPs at/below price; TECHM/MPHASIS — not cheap enough;
  Can Fin Homes / Godawari Power — could not verify from live source.

## 5. Analyst targets captured (dated)

- INFY: Kotak Buy FV ₹1,220 (Jul 3), PL Buy TP ₹1,570 (May 14)
- PETRONET: MOFSL Buy ₹361, Investec ₹400 (Mar-Jul)
- ONGC: Emkay Add, 12-29% upside (Mar 5)
- HCLTECH: JPM underweight, PL Reduce ₹1,300 (caution)

---

# Addendum — 2026-07-05 (second sweep)

## Systematic universe screen (scripts/screen_universe.py)
500 constituents → 270 passed technical gates (above/near 200-DMA, RSI<72, not at high)
→ 43 passed value gates (PE<16, ROE>12%, mcap>₹1,500cr). Full list: data/universe_screen.json.
New picks sourced here: PFC, NATIONALUM (GESHIP to watchlist).

## Hidden-gems agent sweep (15 verified on screener.in, 2026-07-05)
Added as picks: TANLA (PE 14, ROCE 26.3, D/E 0.02, zero flags, 30% off high),
GPPL (ROCE 28, debt-free, 5.3% yield, near 52w LOW).
Added as watch: CPCL (PE 5.4 but peak-cycle refining — normalized math only +10%),
LICHSGFIN (0.74x book, 5.4x PE, ROE 14.4% just under bar).
Verified but rejected: MASTEK (mcap ₹5,026cr — N500 membership borderline, else attractive:
11.8x, ROCE 18, +31% Q), JKTYRE (D/E 0.81, promoter −4.5%/3yr), KTKBANK (0.75x book but ROE 10.4%),
SCI (ROCE 14.3, WC days doubling), RECLTD (profit −22% Q), NATCOPHARM (profit −34% Q, Revlimid cliff),
CANFINHOME (P/B 2.0), GULFOILLUB (flat Q, promoter −5%/3yr, EV threat), SARDAEN (PE 16.3),
J&K Bank (at 52w high), Nuvama (62.8% PLEDGE), MOIL (PE 21.5), GMDC (PE 34), NLCINDIA (debt+promoter selling),
Engineers India (PE 19.3), Maharashtra Seamless (profit −57%), Apollo Tyres (ROCE 13.8),
Deepak Fert (PE 28), Triveni (PE 36), Vardhman (PE 26), Manappuram (ROE 7%), Granules (at high).
Pledge caveat: screener.in shows a warning bullet when pledge is material — absence of warning
is the signal used, not a verified 0%.

## Technical suite (in refresh.py, shown per stock in dashboard)
RSI(14) Wilder EMA; MACD(12,26,9) + histogram; 20/50/200-DMA distances; Stage-2 flag (50>200);
Bollinger(20,2σ) band position; 20d/90d volume ratio; annualized volatility; 52w range position.
Desk pattern found across picks on 2026-07-05: Stage-2 uptrends in low-RSI pullbacks
(above 200-DMA, below 50-DMA, RSI 41-50) = classic accumulation zone, nothing overbought.
