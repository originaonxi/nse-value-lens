# Nifty 200 and stock F&O coverage

The stock page has three views: Nifty 200, all NSE stock F&O underlyings, and
their combined list with duplicates removed. Counts come from the actual lists.
The initial addition has 210 F&O stocks, 184 already in the site's Nifty 200
list and 26 extra stocks: 226 unique shares altogether.

These are daily **underlying share-price** charts. F&O membership does not
turn a share-price chart into an option-premium or futures-contract chart.
The existing Buy/Sell/Watch/Caution/Avoid rules and bold explanations apply.

## Membership and prices

NSE's [permitted lot-size CSV](https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv)
supplies membership. Index contracts, repeated CSV headers, duplicate symbols
and entries without a positive lot for the nearest active contract month are
excluded or rejected. The source month, retrieval time and hash are published.
Membership is checked on every refresh; a failed check retains the last verified
list with a visible warning. Sector metadata comes from the official Nifty 500
constituent file when available; an unknown sector is explicitly labelled.

Additional share histories use Yahoo Finance via yfinance, adjusted for splits
and dividends, just like the stock scanner. A full adjusted history is replaced
together to avoid mixing price scales. Invalid candles, zero-volume placeholders
and dates outside the stock scanner's shared trading calendar are excluded.
The existing `hhhl_scanner.scan_stock` function supplies every classification,
chart candle, confirmed pivot and entry check. The published Nifty benchmark
and scan date are reused. No changes to those rules are made for F&O stocks.

Only `data/fno_prices/`, `docs/hhhl_fno.json` and
`public/data/hhhl_fno.json` are written. The original Nifty scan, prices,
membership CSV and daily workflow remain unchanged. Stocks common to both
lists always use the original Nifty snapshot row, without recalculation.

Missing extra-stock data stays visible as Caution. A failed price download
keeps saved candles and blocks a fresh entry. The browser also blocks entries
for extra stocks when their session/benchmark differs from the Nifty snapshot,
their refresh is overdue, or the extra snapshot cannot be rechecked. The
saved chart keeps its true candle dates. Membership changes cannot silently
omit a new F&O stock: it remains visible as Caution until history arrives.

## Daily automation

`fno_daily.yml` runs after the existing HHHL daily workflow completes, with an
independent backup at 12:30 UTC / 18:00 IST daily. It stages only F&O files and
publishes Pages explicitly. Failure does not block the existing stock refresh.
Scheduled GitHub jobs can run later than their nominal time.

Local refresh: `python fno_refresh.py`.
UI mirror: `python scripts/sync_hhhl_universe.py`.
Backend checks: `python -m unittest discover -s tests -p 'test_fno*.py' -v`.
Frontend checks: `node --test src/hhhl-universe.test.js`.
Browser checks: `python tests/browser_fno.py` (local comparison server).
