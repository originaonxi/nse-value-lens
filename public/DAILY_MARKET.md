# Daily NSE market context and disclosures

The daily market page adds official NSE EQ market breadth, index closes, gainers/losers,
traded value, share volume, tracked-stock sector summaries, moving-average participation,
and bulk/block disclosures. The HH/HL stock table has a separate disclosure filter.
It does not alter prices, chart drawing, classifications, entry rules or risk limits.

## Disclosures and interpretation

[NSE bulk/block reports](https://www.nseindia.com/report-detail/display-bulk-and-block-deals)
identify the security, participant, side, quantity and reported average price.
Bulk reporting concerns substantial same-day trading relative to the company's listed
shares; see [NSE's reporting explanation](https://nsearchives.nseindia.com/content/circulars/cmtr7864.htm).
Block transactions use a separate facility. The collector uses the exchange's own
classification rather than reclassifying trades using a hard-coded monetary threshold.

A bulk purchase is not necessarily new long-term institutional ownership: the same
participant may also sell that day, trade for liquidity provision, or transfer holdings.
Client names alone do not establish investor category or intent. Both buy and sell rows
remain visible. Summing both sides can double-count an economic transfer. The site does
not call this amount market inflow, net institutional demand, or a buy recommendation.

Current bulk/block CSVs are checked first. If their date does not match the expected
completed session, the collector requests that exact day from NSE's historical endpoint.
Every row's displayed date is validated; the UTC order field is not treated as the Indian
trade date. Invalid rows reject the report. Empty undated responses are unavailable,
not a confirmed zero-deal day. A valid full report with no tracked-stock matches really
does yield zero matches in the tracked-stock view.

The initial run checks seven calendar days for missing disclosure files. Every later run
does the same recovery. Normalized dated reports are retained under data/daily_market_history;
the UI exposes the available previous 30 days. Source URL, SHA-256 and retrieval time
identify each download. GitHub artifacts retain original response bytes for 30 days.
Rows are replaced by dated report, not appended again on each retry. History gaps remain
visible. There is no assertion that a whole year or every historical day has been collected.

## Breadth and prices

The official UDiFF cash-market bhavcopy supplies unadjusted close, previous close,
share volume and traded value. Scope is traded NSE EQ securities with a valid previous
close; it is not TradingView's broader NSE/BSE universe. Corporate actions and new listings
can affect raw percentage changes. Other series, invalid comparison rows and non-traded
securities are excluded and counted. The NSE-wide download must contain at least 1,000
valid EQ rows; a truncated report is not published as the whole market.

Advances, declines and unchanged sum to the eligible security count. A/D is advances
divided by declines; zero denominators display unavailable. Up/down volume excludes
unchanged securities. Index values come from the dated official index-close report.
Dash-valued index variants are excluded, never filled with a number.

Nifty 200 and F&O memberships come from the existing site's membership snapshots.
Moving-average percentages use only tracked stocks with valid adjusted histories through
the same session, with eligible denominators shown separately for 20/50/200 sessions.
Sector changes are equal-weight tracked-stock averages, not official sector-index returns.
F&O coverage remains underlying cash shares, not option premiums or futures contracts.

## Every-day operation

GitHub Actions runs .github/workflows/daily_market.yml every calendar day at
19:15, 21:15, 00:15 and 08:15 IST, plus after the existing HHHL refresh completes.
The holiday calendar is checked independently. The latest completed session is used;
weekends/holidays never acquire invented candles or new deal dates. The collector's
expected-session helper accepts explicitly supplied special weekend sessions, but automatic
detection of newly announced special sessions is not provided by the holiday endpoint.

On Railway, the running app also schedules 20:05, 23:05 and 09:05 IST checks, plus a
startup catch-up. There is a single in-process runner with a 15-minute timeout.
Local development does not run this cron unless ENABLE_DAILY_MARKET_CRON=1.
The Railway data route compares valid remote and local snapshots and serves the newer
expected session/attempt. The Pages site uses the committed JSON directly.
The existing F&O and global-market routes also retrieve the current validated GitHub
snapshots, with a one-minute cache and a dated local fallback if GitHub is unavailable.
Their existing refresh workflows continue to produce those datasets.

No hosted scheduler can guarantee an exact firing time or data-provider availability.
The site displays the last attempt and original report dates, flags refresh attempts
older than 36 hours, and retains old reports as stale after a failed fetch. GitHub
publishes failure status before making the workflow visibly fail, and verifies actual
publication on both public sites. The Railway backup protects the Railway site during
a GitHub delay; its local files do not directly publish GitHub Pages.

## Reproduce and verify

    python daily_market.py --strict
    python scripts/sync_daily_market.py
    python -m unittest discover -s tests -p test_daily_market.py -v
    node --test src/daily-deals.test.js
    python -m http.server 3232 --bind 127.0.0.1 --directory public
    python tests/browser_daily_market.py

The browser check covers all 36 disclosure filter combinations, market controls,
CSV exports, desktop/mobile layout, HH/HL integration, failed downloads and overdue data.
No automated trades are placed.
