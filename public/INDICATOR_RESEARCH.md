# Top 100 NSE indicator strategy rules

## What was tested

144 configurations on 199 available stocks from the current Nifty 200 universe: 18 signal definitions across 11 indicator families, four maximum holding periods (same day, 5, 10 and 20 trading sessions), and two market entry filters (unrestricted or prior Nifty close above its 200-session moving average). A rule is an indicator definition plus holding limit plus market filter. These are correlated variations, not 144 independent discoveries or the best 100 rules in the world.

The fixed specification is INDICATOR_RESEARCH_PLAN.json. Each report includes its canonical JSON SHA-256 fingerprint. Data are the same adjusted daily Yahoo histories cached for the preceding experiments, ending 2026-09-23. This is a dated research report, not a fresh intraday feed.

## Findings

Six of 144 configurations had a positive recent base return. Zero passed the fixed cross-period exploratory screen. Zero had 100% winning trades across the three base periods with at least 30 trades. This does not establish that profitable technical strategies do not exist; it describes this finite search, data, implementation and cost model.

| Example | Earlier total | Middle total | Recent total | Recent doubled costs |
|---|---:|---:|---:|---:|
| Confirmed HH/HL, 10 sessions, Nifty above 200 DMA | 10.25% | -10.15% | 6.29% | 3.07% |
| Ichimoku TK cross, same day, Nifty above 200 DMA | -18.78% | -11.79% | 5.34% | 1.39% |
| Supertrend 7/2 flip, 20 sessions, unrestricted | 24.48% | 1.47% | -4.83% | -8.20% |

The two positive recent examples were identified after seeing recent results and are not validated selections. The Supertrend configuration was selected using earlier and middle data before computing recent performance. That selection's recent loss remains visible.

HH/HL's recent result comprised 65 trades with a 47.69% win rate and a 2.61% end-of-day drawdown. Across all three windows, it won 202 and lost 240 trades. A positive return does not require winning every trade; its preceding period still lost money.

## Ranking and selection

Earlier: 2022-07-27 to 2024-09-09. Middle: 2024-09-10 to 2025-09-12. Recent: 2025-09-15 to 2026-09-23, 252 sessions. All columns are total returns over unequal durations; the internal ranking uses annualized returns. Start each period flat with Rs 100,000 and force liquidation at its last available close. Cash earns zero.

The top-100 ordering is calculated only from earlier and middle results. Positive results in both periods with at least 30 trades each and no held-bar gaps come first. Within that group, and among the remaining rules, rank by the minimum of annualized return divided by max(end-of-day drawdown, 5%) across those periods. Ties use the configuration ID. Lower-ranked failures are still displayed to fulfill the 100-rule comparison. A ranking position does not mean a strategy passed or has positive expected returns.

INDICATOR_SELECTION.json is written before recent simulations. Using earlier data only selected Ichimoku cloud breakout / 20 sessions / Nifty above 200 DMA for the middle period; it returned -6.15% in that subsequent period. Earlier plus middle data selected Supertrend 7/2 / 20 sessions / unrestricted for the recent period; it returned -4.83%. These are chronological selections in this run, not pristine out-of-sample proof: market periods had already been inspected in prior experiments.

The exploratory screen requires positive base returns in all three periods, positive doubled-cost returns in middle and recent, at least 30 recent closed trades, and no missing held-position bars. All three stress periods are published, including earlier stress. No result passed. This screen does not correct for multiple comparisons, quantify statistical confidence, or remove survivorship bias. No strategy has been forward validated.

## Shared execution and risk

Use completed daily data only. A signal at close t can fill at the next session open, only within one prior ATR above/below the signal close. Rank candidates by prior 20-session average rupee turnover, ties by symbol. All entries are long cash equities. Same-day rules use the previous daily indicator signal and exit during the next session; these are not minute-chart strategies.

Minimum prior price Rs 50; prior 20-session average turnover Rs 10 crore; Wilder ATR14/price 0.5%-6%. Maximum five simultaneous stocks, two per current industry, 20% allocation per name and 0.5% planned stop risk per name including modeled stop costs. No leverage. Whole shares only. Signal rules do not share a universal stock trend gate: RSI2 explicitly requires close above SMA200, while other conditions are listed in the plan. Nifty filter gates new entries only.

Initial stop is two prior ATR below the actual modeled entry. It stays fixed. Indicator reversal is observed at a close and exits at the following open. Otherwise a gap through the stop uses the worse opening price; an intraday stop fills the stop price plus adverse slippage. The holding cap exits at the close, counting the entry session. No profit target. The last window date forces a close with costs. New entries are processed before today's exits, so capital released later in a session cannot fund earlier entries. Future closing prices are never used to size entries. Entire missing or zero-volume entry bars are treated as unexecutable; daily bars still cannot establish auction liquidity or order-book fills.

Per-side costs: delivery 0.15% fee/tax scenario plus 0.05% adverse slippage; same-day 0.05% fee/tax scenario plus 0.05% adverse slippage. Stress doubles both and reruns the whole portfolio, so trade counts can change. These are scenarios, not historical broker invoices; fixed DP fees, brokerage caps and dated tax rates are not reconstructed. Personal income tax is excluded.

Daily equity is marked to close. Win rates and profit factors use net closed-trade P&L. End-of-day drawdown can understate intraday loss. Planned stop risk can be exceeded by gaps. Full trade logs and curves are downloadable in indicator_trades.json.gz; the main JSON includes all period metrics, recent curves, the latest ten base trades per rule and snapshot signals. Historical simulation entries were not published signals or actual executed orders at the time.

## Indicator implementation

- Supertrend variants: Wilder ATR with an initial arithmetic-mean seed; final bands use only current/prior bars. Flip strategies require a bearish-to-bullish transition; the trend-state variant also permits re-entry while bullish. Initial risk stop remains the shared 2 ATR; a bearish indicator exits next open.
- HH/HL: strict swing pivots need two bars on the left and two on the right. Pivots become available only at the close of the second right bar; no backdating. Require two rising confirmed highs and two rising confirmed lows, then a close crossing the latest confirmed high. A close below the latest confirmed low triggers next-open exit. No overnight short position is inferred from LL/LH.
- Ichimoku: 9/26/52 rolling midpoints; both visible cloud spans shifted forward 26 rows. Cloud breakout requires close crossing above its visible top and Tenkan above Kijun. TK-cross requires a bullish conversion/base cross above the visible cloud. The lagging line is not read from future prices. These explicit conventions can differ slightly from charting packages with alternative offset/seed conventions.
- Other rules: Donchian 20/55, EMA 9/21 and 20/50, MACD 12/26/9, Wilder ADX/DI14, RSI2/14, Bollinger SMA20 with 2 population standard deviations, Keltner EMA20 with 2 ATR20, and stochastic 14/3/3. Exact thresholds and exits are in the plan and selected-rule UI.

Primary formula references: [TradingView Supertrend](https://www.tradingview.com/support/solutions/43000634738-supertrend/), [TradingView Ichimoku](https://www.tradingview.com/support/solutions/43000589152-ichimoku-cloud/), [TradingView pivot points high/low](https://www.tradingview.com/support/solutions/43000589195-pivot-points-high-low/). These define indicators, not evidence that the selected NSE trading rules are profitable.

## Fundamental and universe audit

The existing data/pre_analyzed.json contains manual ratios, and screen_output/stock_profiles.json contains company snapshots without historical per-value publication timestamps. The existing universe_snapshots.json itself reports missing historical membership data. Applying current ratios or current constituent membership as though they were known years ago would introduce bias.

No fundamental strategy is included in the numeric profitability ranking. Testing earnings surprise, earnings acceleration, value/quality plus technical confirmation requires dated filings or a point-in-time fundamental ledger and realistic announcement-to-entry timing. No data subscription or live brokerage connection was purchased. Current-stock survivorship bias remains in every indicator result; delisted/removed stocks and historical industry changes are not reconstructed. This matters even when code is causal.

## Reproduction and verification

```sh
pip install -r requirements.txt
python -m unittest discover -s tests -p "test_*.py" -v
python indicator_research.py
npm test
```

The script uses .cache/swing OHLCV files from swing_research.py. The checked-in plan fixes the evaluation dates and rejects a changed market snapshot end date. Vendor rolling histories and revisions can change a later replay: preserve matching inputs, or create a clearly versioned new plan/report. It writes all research JSON, the full gzip archive and the chronological selection record. It does not refresh automatically with the daily swing scanner.

Tests cover prefix invariance of every indicator, the Ichimoku offset, delayed pivot confirmation, Wilder seeding, Supertrend initialization, next-open entry, reversal exit timing, adverse stop gaps, cash/risk constraints, fees, market gates, and exclusion of recent data from selection. Browser checks cover ranking/filter behavior, dated trades, missing data, mobile overflow and page errors. Passing tests verifies these mechanics, not future profitability.
