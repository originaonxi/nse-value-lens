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

## Chart structure overlay

The daily refresh also supplies the full chart window of confirmed swing events. HH/HL are green; LH/LL are red; EH/EL indicate equal extremes. Click a label for its price, original pivot date and later confirmation date. Labels compare consecutive same-type confirmed pivots. The zigzag connects alternating extremes, keeping the most extreme point in a run of same-type pivots. If one daily bar is both a swing high and low, the line breaks because intraday order cannot be inferred. The newest two candles have no confirmed swing labels. Price-zone and structure toggles are independent. Mobile charts scroll horizontally to keep candles readable.
