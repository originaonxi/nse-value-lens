# Swing desk: rules, evidence and GitHub review

Reviewed 23 September 2026. Delivery-only, long-only research.
No tested strategy is a validated winner. The website places no orders.

## Repository audit

The project had different Railway and GitHub Pages dashboards, many overlapping
signal layers, and a README targeting 6–18 month investments. Both homepages now
provide a focused swing workflow. The previous dashboards remain at research.html.

Existing backtest_verdict.json records unsuccessful breakout and mean-reversion
experiments. backtest_indicators.json says its indicator proxy does not replay
the live SAM/JEV composite. Those experiments do not validate that live score.
The new scanner and simulator use the same setup() and fill() functions.

## Public repositories reviewed

| Project | Useful reference | Decision |
| --- | --- | --- |
| [backtesting.py](https://github.com/kernc/backtesting.py) | Explicit commissions and order timing; AGPL-3.0 | Useful simulation conventions. A framework does not prove an NSE edge. No source copied. |
| [QuantConnect LEAN](https://github.com/QuantConnect/Lean) | Event-driven research/execution platform; Apache-2.0 | More infrastructure than this daily scanner requires. No migration or copying. |
| [hardikjh/swing_trade](https://github.com/hardikjh/swing_trade) | NSE scanner with entry, stop, target and sizing | Its README describes several simultaneous indicator filters. No independently verified live edge established here. No root license found; no code reused. |

This was a targeted architecture/README review, not a full code, security or
performance audit of these projects. Popularity and reported returns are not proof.

## Research sources

- [Nifty200 Momentum 30](https://niftyindices.com/indices/equity/strategy-indices/nifty200-momentum-30)
  uses volatility-adjusted 6- and 12-month returns. That supports studying
  momentum, but does not validate one-week entry timing.
- [Daniel and Moskowitz, Momentum Crashes](https://www.nber.org/papers/w20439)
  documents momentum crash risk. Its portfolio differs from this long-only scanner.
- [Nagel, Evaporating Liquidity](https://www.nber.org/papers/w17653) studies short
  reversals and liquidity provision in a different market. It motivates a
  hypothesis, not a proven NSE rule.
- [NSE impact cost](https://www.nseindia.com/static/products-services/indices-impact-cost)
  explains execution liquidity costs beyond quoted prices.

## Frozen rules

All candidates require Nifty close > SMA50 > SMA200; stock close > SMA200;
price >= Rs 50; average 20-session traded value >= Rs 10 crore; ATR/price
between 0.5% and 6%. These are hypotheses, not fitted optimal thresholds.

1. Breakout: close above PRIOR 20-session high and SMA50; volume >= 1.5x prior
   20-session average; positive 63-session relative return versus Nifty.
   Maximum 20 sessions.
2. Trend pullback: previous close <= previous EMA20; close > EMA20 > SMA50;
   volume >= prior average; positive 63-session relative return. Maximum 10 sessions.
3. Mean reversion: RSI(2) < 10 while above SMA50. Maximum 5 sessions.

Signal at close t; enter only at t+1 open, including slippage, within close(t)
+/- 0.5 ATR(t). Skip gaps outside the band. Stop = close(t) - 2 ATR(t).
Target = actual entry + 2 * (actual entry - stop). Exit at stop, target or
the close of the final permitted holding session. A bar touching both stop and
target takes the stop first. A gap below stop executes at the worse opening price.

Rank simultaneous plans by relative return, then symbol. Initial Rs 100,000
cash account, 0.5% planned risk including estimated stop costs, 20% allocation
cap, five positions maximum, two per industry. Gaps can exceed planned loss.
The web calculator assumes an empty account.

## Historical comparison

Five years of adjusted Yahoo daily OHLCV. First 210 benchmark sessions provide
warm-up. Last 252 benchmark sessions form the recent window; the earlier window
ends before it. Each window starts flat. No parameter search or automatic winner.
These are retrospective diagnostics, not an untouched prospective test.

Costs per side: 0.15% fee/tax assumption plus 0.05% slippage; stress doubles both.
These are scenarios, not a verified broker tariff. Fixed DP charges, actual
spreads, circuit locks and suspension execution are not faithfully replicated.
Benchmark = Nifty 50 price return without dividends or exposure adjustment.

Equity includes marked open positions and reserves their estimated closing costs
at the end. Closed-trade statistics exclude open holdings. Missing held-stock
bars freeze the last mark and are counted, never treated as executable prices.

Current Nifty 200 membership and current industry labels cause survivorship
and classification limitations. Missing securities, IPOs, historical removals
and corporate actions require further review. No earnings-event calendar gate
is available. Check results dates and corporate actions before any manual trade.

Validation needs point-in-time membership, exchange-verified data, locked rules,
separate forward paper execution, and reconciled broker costs. Repeatedly
inspecting a recent window makes it unsuitable for an untouched final test.

## Reproduce and operate

    pip install -r requirements.txt
    python -m unittest discover -s tests -p test_swing.py -v
    python swing_research.py
    python swing_research.py --cached
    npm ci
    npm test
    npm start

Cache: ignored .cache/swing CSV files, never executable pickle.
Snapshots: screen_output, docs and public/data. JSON files are atomically replaced.
The Swing desk refresh workflow updates signals and evidence after market close.
Download swing_evidence.json for the daily equity series and closed trade log.

No matching setup is valid. Old entry bands are hidden after the next weekday
opening window; this deliberately conservative guard does not infer holidays.
Data failures and incomplete coverage are visible. Prior experiment verdicts are
preserved and must not be blended with these new results.


Railway serves refreshed GitHub datasets with a five-minute cache and a local fallback.
The browser expires fallback entry levels too. Refresh aborts below 90% universe coverage.

## Last 10 filled setups

History combines the base-cost earlier and recent simulations, never the duplicate
stress run. Sort is setup date descending, entry date descending, then symbol and
strategy. Filtering happens before taking ten rows. Strategies represent separate
portfolios; the same stock may appear in different strategies.

Each row records the signal's session, actual simulated fill dates/prices,
initial stop, fill-adjusted target, and net P/L after modelled costs. Net percentage
return uses the position's entry cost including fees, not whole-account capital.
Prices are adjusted historical prices including simulated slippage.
Open-at-window-end records have no invented exit price, realized P/L or sell date.
This is a retrospective reconstruction, not a log of recommendations published
on those historical dates. Skipped and unfilled signals are not included.
