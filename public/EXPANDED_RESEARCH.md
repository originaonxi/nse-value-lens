# Expanded strategy research - 23 September 2026

## Result

No daily-profit strategy was established. All six additional stock experiments failed the fixed exploratory gate. Both actual-contract futures experiments lost money in the recent period. ETF results include positive returns, but substantial losing days, selection bias and cost sensitivity prevent a claim of a proven edge.

The lab is a fixed dated research snapshot, separate from the daily swing scanner. No orders or account connections were added.

| Experiment | Earlier total % | Middle total % | Recent total % | Recent doubled costs % |
|---|---:|---:|---:|---:|
| Stock momentum rotation | 17.34 | -2.86 | -9.14 | -10.04 |
| Stock low volatility | 20.18 | -8.88 | -3.81 | -5.97 |
| Weekly reversal | -5.81 | -3.92 | -9.69 | -12.15 |
| Intraday trend long | -43.94 | -11.29 | -28.41 | -40.67 |
| Intraday trend short | 6.76 | -11.26 | -12.22 | -23.17 |
| Intraday reversal | -57.46 | -28.08 | -27.98 | -45.93 |
| Equity/gold dual momentum | -8.76 | 16.07 | 18.62 | 13.51 |
| Equity/gold diversified trend | 0.15 | 5.89 | 5.32 | 1.24 |
| Nifty ETF buy-and-hold benchmark | 52.83 | 1.44 | -5.48 | -5.87 |
| Gold ETF buy-and-hold benchmark | 31.80 | 50.22 | 33.58 | 33.02 |
| Actual Nifty futures swing | unavailable | 1.11 | -2.74 | -5.09 |
| Actual Nifty futures intraday | unavailable | -14.28 | -23.26 | -25.16 |

Earlier: 2022-07-27 to 2024-09-09. Middle: 2024-09-10 to 2025-09-12. Recent: 2025-09-15 to 2026-09-23 (252 market sessions). These are total returns over unequal durations, not annualized returns. Each period starts with fresh capital and no positions.

The diversified ETF model lost equity on 125 of 252 recent sessions and had a 16.11% end-of-day drawdown. A follow-up sensitivity check, added after observing the small earlier gain, changes its earlier +0.15% to -9.17% at doubled costs. Gold buy-and-hold gained 33.58% recently but lost equity on 119 sessions and had a 24.44% drawdown. That is historical gold exposure, not proof of daily income or a recommendation to buy gold now.

## Fixed hypotheses and implementation

Read EXPANDED_RESEARCH_PLAN.json, CROSS_ASSET_RESEARCH_PLAN.json and FUTURES_RESEARCH_PLAN.json for the exact rules. Their hashes are embedded in the reports. Each batch was specified before running that batch, but all periods are retrospective and were already available for inspection. ETF and futures batches were added after seeing earlier failures. No untouched holdout or live forward record exists.

Stock tests use 199 current Nifty 200 constituents with sufficient history, Rs 100,000 starting capital, at most five holdings, two per current industry, 20% notional per stock, 0.5% planned stop risk per stock and no leverage. Short cash positions are intraday only and reserve full notional. Prior-session indicators select the next open; ambiguous OHLC stop/target bars assume the stop first. Overnight stop gaps use the worse opening price. Missing/zero-volume entry bars are skipped without substituting another ranked name.

ETF tests use Rs 100,000 and actual adjusted NIFTYBEES/GOLDBEES daily prices. Every 20 sessions, dual momentum picks the ETF with the highest positive 126-session return, otherwise cash. Diversified trend allocates half to each ETF only above its prior 200-session average; inactive allocations stay in cash. They have no per-position stop and can use 100% notional. Each 20-session block is liquidated at its last close, so the model incurs repeated round trips even when retaining the same ETF. This is the specified strategy, not a cost-minimizing continuous holding model. Benchmark ETFs are bought once per window and liquidated at its end. ETF histories and choices introduce hindsight and selection bias; they are not directly comparable in risk to the capped stock system.

Futures use 504 official NSE daily archives with actual instrument IDs, expiry dates and historical lot sizes. Select the previous session's highest-volume eligible Nifty futures contract, expiry more than three calendar days away, then enter next open. Prior Nifty close above SMA50 means long; otherwise short. Swing stop is 2 prior spot ATR with a 20-session/expiry exit. Intraday stop is 1 ATR and exit is the session close. Rs 2,000,000 is fully reserved against contract notional: no leverage. This is a collateralized P&L simulation, not historical broker margin/settlement accounting. No recent held-contract bars were missing. Futures have only two evaluation periods and fail even before a longer validation requirement could be met.

## Costs, accounting and limits

Per-side scenario assumptions: stock swing and ETFs 0.15% fees/taxes plus 0.05% slippage; stock intraday 0.05% fees/taxes plus 0.05% slippage; futures 0.05% fees/taxes plus 0.02% slippage. Stress doubles both components. These are proportional scenarios, not verified historical broker tariffs or personal income tax. Actual DP charges, brokerage caps, dated tax changes and instrument-specific levies need reconciliation before any execution decision. ETF assumptions are deliberately conservative; gold and equity ETFs have different tax treatment. Do not interpret scenario costs as a broker quote.

Equity is marked at each close. Profitable, losing and flat days count the full evaluation calendar, including cash days, relative to starting capital on the first day. They do not mean cash income was paid out daily. Drawdown uses closing equity and can miss deeper intraday losses. Open stock/futures positions are marked with an estimated exit-cost reserve at the final date; closed-trade statistics exclude them. The UI displays the last ten closed base trades across windows, with setup, entry and exit dates and actual modeled buy/sell direction; stress duplicates are excluded. All prices and trades are simulations, not contemporaneously published orders.

Current constituents and industry classifications cause survivorship bias. Daily candles cannot establish order-book depth, intrabar sequence, exchange circuits, or historical short eligibility. Adjusted prices are not a complete corporate-action cash ledger. We have not validated a live trading edge or ranked strategies by a trustworthy expected future return.

## Intraday and options data audit

The 200-stock five-minute download provided roughly 59 sessions each. Only 424 of 11,800 opening bars had positive recorded volume (3.59%); no symbol supplied the required 21 positive opening observations. The volume-based opening-range experiment is blocked. Zero recorded volume is a feed quality issue here, not evidence of no actual trading. No ORB profitability result was manufactured from these bars.

NSE end-of-day option records exist, but synchronized multi-leg bid/ask and historical intraday execution/margin inputs are absent. Options were investigated but not backtested. Spot returns were not relabelled as option P&L. Further options or opening-range conclusions require an execution-quality dataset, not another parameter search on these inputs.

## Research and GitHub review

- [Nifty 200 Momentum 30 methodology](https://niftyindices.com/indices/equity/strategy-indices/nifty200-momentum-30) provides a published Indian momentum reference; the stock experiments here are different short-horizon hypotheses, not index replication.
- [Momentum crashes, NBER](https://www.nber.org/papers/w20439) documents an important limitation of momentum; a published factor does not promise profits every day.
- [Opening-range research by Zarattini, Barbon and Aziz](https://www.alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content) studies US equities. Our proposed NSE adaptation changes execution and risk assumptions; it is not a replication and has no valid result yet.
- [Meb Faber's timing model](https://mebfaber.com/timing-model/) motivates examining asset trends. Our two-ETF India adaptation is a separate retrospective experiment.
- [Official NSE derivatives reports](https://www.nseindia.com/all-reports-derivatives) supply the actual futures contract data. The downloader uses archives.nseindia.com UDiFF daily bhavcopies.
- [NSE F&O data-bank repository](https://github.com/SantoshSrinivas79/NSE-FNO-Data-bank) was inspected as a data-discovery resource. No third-party strategy code was executed; futures tests use direct NSE archives. A GitHub repository or reported return is not independent proof of an edge.
- [Zerodha ETF tax explanation](https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/stt-etfs) shows why the simple cost scenarios require instrument-specific reconciliation.

The earlier SWING_RESEARCH.md contains the initial repository comparisons and original three strategies. All unsuccessful tests remain visible.

## Reproduce

Install requirements.txt. Run these from the repository root (network required for downloads):

```sh
python swing_research.py
python expanded_research.py
python cross_asset_research.py --download
python research_derivatives_data.py
python futures_research.py
python research_intraday.py
python research_data_audit.py
python -m unittest discover -s tests -p "test_*.py" -v
npm test
```

Downloads use rolling vendor history and can change with the run date and revisions. Published JSON preserves this run's dates, trade logs, curves and specification hashes. Data caches are local and ignored by Git. Intraday audit uses the local cached opening bars. Expanded lab snapshots are deliberately not regenerated by the daily swing refresh job.
