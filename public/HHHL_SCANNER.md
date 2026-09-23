> Daily automation starts at 16:00 IST with catch-up runs. [Schedule, freshness checks and recovery](HHHL_AUTOMATION.md). Any dated results below describe the original snapshot; current results are on the scanner.

# Nifty 200 HH/HL scanner

Snapshot: **23 September 2026**. Strategy: confirmed HH/HL breakout, maximum 10 trading sessions. This page classifies every stock in the repository's 200-member universe; it does not simulate an account or place orders.

- [Open scanner](https://originaonxi.github.io/nse-value-lens/hhhl.html)
- [Snapshot JSON](hhhl_scan.json)
- [Earlier indicator research](INDICATOR_RESEARCH.md)

## Classification

Each stock receives exactly one primary state, in this priority order:

| State | Condition | Meaning |
| --- | --- | --- |
| Caution: data | Missing/stale latest prices, insufficient pivots, missing recent sessions, or no trading volume. | No actionable zones are published. The stock stays in the full list. |
| Sell | Latest close below the most recently confirmed swing low. | Structure exit condition for an existing long, at the next opening. Not a short entry. |
| Avoid: entry screens | Price below Rs 50, 20-session average traded value below Rs 10 crore, or ATR14/price outside 0.5%-6%. | New entry is ineligible. |
| Buy | Two rising confirmed highs and lows; a fresh closing cross above the last confirmed high; complete benchmark and Nifty above SMA200. | Conditional next-session paper entry, subject to portfolio limits and actual opening price. |
| Caution: entry | Fresh breakout with blocked/incomplete market gate, or rising structure already above resistance without a fresh cross. | Do not enter from this state. |
| Watch | Rising confirmed highs and lows without a closing breakout. | Await a fresh signal. |
| Avoid: structure | Remaining stocks. | This HH/HL setup is absent; not a judgment about company value. |

The stock table can be filtered by state, symbol/company, sector and structure. All 200 rows are available by default. Downloaded CSV includes the currently filtered rows and their dates. An empty Buy filter is a valid result.

## Confirmed pivots and timing

A high must exceed the highs of two candles on each side; a low must be below the corresponding lows. A pivot at session t becomes known only at the close of session t+2. The detail panel displays both dates.

Require two increasing confirmed highs and two increasing confirmed lows. Entry signal is the first closing cross above the latest available confirmed high, using that day's and the preceding day's known levels. A pivot is never backdated as an available signal.

The scanner imports the existing confirmed-pivot, crossover and Wilder ATR functions from the indicator research module. Tests compare its HH/HL signals and ATR with that implementation on identical cleaned input.

## Price zones

- **Breakout reference:** last confirmed high. Crossing this price intraday is insufficient; the rule requires a fresh closing cross and all gates.
- **Structure exit:** last confirmed low. A closing break creates an exit condition for a held long.
- **Watch band:** from the greater of confirmed low or high minus one ATR, up to the confirmed high. This is a visual reference and has not been tested as an alternative entry rule.
- **Conditional opening band:** only calculated after a fresh closing breakout, from signal close minus one ATR to signal close plus one ATR. A blocked plan is labeled explicitly.
- **Initial stop:** actual entry minus two signal-day ATR. A displayed close-based stop is only an illustration until a fill exists.
- **No fixed target:** the tested rule exits on stop, structure reversal or session 10. A stop can fill worse on a gap.

The next-session entry window expires after that session's open; this fixed historical page is never an evergreen entry instruction. Position sizing and eligibility still depend on actual holdings: at most five positions, two per industry, 20% capital per stock and 0.5% planned stop risk including estimated costs. Gaps can exceed that risk.

## Data audit and 23 September findings

All **200** EQ symbols in root \`nifty200.csv\` are represented. **199** have a complete cached 23 September OHLCV candle. ICICIAMC's new Yahoo download returned missing OHLC prices for that date; its latest complete candle is 22 September. It remains Caution with zones withheld.

The available stock input is the previously downloaded Yahoo adjusted daily cache. Fresh verification requests returned incomplete 23 September stock candles and a lagging index response. Attempts to re-download the official constituent CSV, equity bhavcopy and index close files timed out. Consequently the report identifies its cache and repository-universe provenance rather than claiming a fresh exchange-verified download.

### Holiday placeholders removed

The stock cache included flat, zero-volume rows on market-wide holidays. Counting those rows would affect ATR windows and the two-session pivot confirmation delay. This scanner derives shared sessions from positive volume in at least 100 universe members and excludes zero-volume/non-session stock rows before calculating indicators. Per-file removal counts and SHA-256 hashes are in the JSON.

This is a data-cleaning correction. Earlier indicator backtest returns have **not** been recomputed using this normalization and must not be presented as validation of this exact snapshot pipeline.

### Market gate

The cached Nifty close is **23,446.8008**. Its average over 200 available observations is **24,466.4748**. The 22 September benchmark session is missing. The JSON therefore leaves the exact \`sma200\` field null, shows the available-observation average separately, and blocks new entries. No missing close is invented.

After normalization:

| Buy | Sell | Watch | Caution | Avoid | Total |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 16 | 9 | 3 | 172 | 200 |

APOLLOHOSP has a fresh structure breakout but is Caution because the market/data gate blocks entry. The labels apply to the requested date, not current intraday quotes.

## Reproduce

With the existing local \`.cache/swing/\` daily CSV inputs:

\`\`\`text
python hhhl_scanner.py --as-of 2026-09-23
python -m unittest discover -s tests -p test_hhhl_scanner.py -v
\`\`\`

The script performs no network requests. It writes the same \`hhhl_scan.json\` into \`screen_output/\`, \`docs/\` and \`public/data/\`. Dates after the requested cutoff are removed before calculations. The input files are ignored by Git; their hashes identify the snapshot used.

Browser checks cover all 200 rows, each status filter, empty Buy results, search and sector/structure filters, chart/zone details, stale-data treatment, CSV download, mobile overflow and failed data requests.

## Limits

This is a research scanner, not a validated profitable system or a list of orders. Historical membership, price adjustments and corporate actions require further validation. There is no earnings-event gate. A real position's stop or maximum holding time can require selling even when today's stock label is Watch or Avoid. The page does not know your holdings.

Primary formula context: [TradingView pivot points high/low](https://www.tradingview.com/support/solutions/43000589195-pivot-points-high-low/). This explains pivots, not profitable NSE execution.

## Top 10 current setups and strategy charts

The shortlist is a review order under the existing `hhhl_h10_nifty_above_200` rule, not a ranking by expected profit. It updates with every daily scan and contains up to 10 stocks; it is never padded with stocks that fail the stock-level screens.

1. Eligible fresh closing breakouts.
2. Fresh closing breakouts blocked by the Nifty market/data gate, still labelled **Caution**.
3. Confirmed HH/HL structures waiting below their trigger, labelled **Watch**.
4. Structures already above the trigger without a fresh cross, placed last.

Within each group, the smaller absolute distance between close and trigger, divided by ATR14, ranks first. Symbol breaks ties. Complete prices, sufficient history, two rising highs and lows, price, turnover and ATR screens must pass; an active structure exit excludes the stock. A high shortlist rank never overrides an entry gate. This ordering has not been validated as a return predictor.

### Reading a stock's chart

- **H1/H2 and L1/L2:** the last two confirmed highs and last two confirmed lows used by the current rule. Pair cards show their prices and dates; dashed guides show whether each pair rises. Only these four labels are emphasized initially. Enable **All swing labels** to inspect older HH, HL, LH, LL and equal extremes.
- **Confirmation:** strict pivots use two bars on each side. Click any label for the original pivot date and the date two sessions later when it became usable. Price levels begin on that confirmation date (or the beginning of the visible window if confirmed earlier). The newest two candles are shaded because their pivots are still unconfirmed.
- **Zigzag context:** a faint line connects alternating confirmed extremes, keeping the most extreme point in a run of same-type pivots. The line breaks on a daily bar that is both a high and a low because its intraday order is unknown. This display is separate from the four pivots used by the strategy; it does not add a percentage-reversal filter or an unconfirmed projected leg.
- **Closing events:** blue triangles mark fresh HH/HL closing crosses; red triangles mark the start of a close-below-confirmed-low condition. Click for the event date and level. These are historical structure events, not executed trades or proof that the historical market, liquidity and execution gates passed.
- **Price zones:** the closing trigger and structure exit are labelled on the price axis. The current watch band is shown from the latest candle forward. A conditional next-open band appears only for a fresh setup and stays amber/blocked when entry is ineligible. The stop reference assumes entry at the signal close; an actual initial stop must use the actual fill minus two signal-day ATR. No fixed profit target is added.
- **Rule checks:** nine checks identify which conditions pass, wait or block entry. Volume bars and their previous-20-session average are context; volume expansion is not a new entry requirement.
- **Controls:** 35, 70 and 140-session views, independent structure, historical label, zone, event and volume controls, plus candle OHLCV inspection. Mobile charts scroll horizontally to preserve readable candles.

The existing maximum hold is 10 trading sessions. A confirmed-low break exits at the next open; the initial stop and time exit can act independently of today's scanner status. The chart does not track real holdings or place orders.

### Reference conventions

[TradingView's Zig Zag description](https://www.tradingview.com/support/solutions/43000591664-zigzag-indicator/) explains pivot confirmation and why projected/recent zigzag legs can change. This scanner uses its own fixed two-left/two-right pivot rule and shows only confirmed events. [StockCharts' Dow Theory guide](https://chartschool.stockcharts.com/table-of-contents/market-analysis/dow-theory) provides background on rising highs/lows and trend confirmation. These sources explain chart conventions; neither validates this scanner's profitability in the NSE universe.

### Verification

Python regressions check causal chart metadata, prior-session volume averages, entry checks and shortlist order/exclusions. JavaScript tests check active pivot selection, confirmation dates and windowing. The daily GitHub workflow checks both public sites in Chromium: shortlist, active labels, confirmation clicks, price levels, blocked-entry treatment, all three chart windows, toggles and mobile layout. Workflow artifacts include screenshots and a JSON chart report.
