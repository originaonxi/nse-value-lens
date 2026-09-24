# Nifty 200 VCP scanner

Live: https://nifty.up.railway.app/vcp.html · mirror: https://originaonxi.github.io/nse-value-lens/vcp.html

The page includes every current constituent, every active matching setup (no top-ten limit), weekly OHLCV charts, contraction depths and dates, daily ATR20 and per-stock rule checks. Zero matches is a valid result. Missing data is displayed separately.

The default is three contractions or a second contraction at least 70% smaller than the first. The strict three-only and exploratory two-smaller versions are separate views. All use `daily_features`, `weekly_features`, `update_pivots`, `pattern_at` and the entry schedule from `vcp_research.py`; the live scanner does not pick whichever version recently made the most money.

## Timing and states

Weekly filters use completed Friday-labelled weeks. Daily prices update the pending entry state in between. One full later week must confirm each swing. A historical pivot cannot become a signal before its confirmation.

- **Awaiting breakout:** completed weekly filters and VCP pass, current history is clean, and this pattern's trigger has not previously been touched while eligible. Entry reference: final swing high × 1.001. Stop preview assumes entry at that reference and uses the latest completed daily ATR20, capped at 10% of entry. Actual fills and gaps change risk.
- **Already triggered:** an eligible daily high has already touched the trigger. This is an observation, not evidence of a real fill or a new recommendation.
- **Invalidated / expired:** the contraction low failed or the close moved beyond the pivot without an eligible trigger observation.
- **Filters only:** stock selection passed, but no complete VCP qualifies under the selected definition.
- **Filters not passed:** at least one required weekly stock filter failed.
- **Data incomplete:** missing, stale, short or suspect price history blocks eligibility and entry levels. The stock remains visible.

The site does not monitor actual holdings, infer executions or send orders. The weekly 10-week SMA is an exit reference for an existing position, not a portfolio sell alert.

## Data and automation

`hhhl_daily.yml` runs at 16:00 IST with scheduled retries. It refreshes the official constituent list and adjusted daily history using `hhhl_refresh.py`, then runs `vcp_scanner.py`. Both scanners use `data/hhhl_prices`; VCP does not redownload 200 separate histories. Shared calendars require positive-volume observations from at least 100 members. Missing stock sessions stay missing.

The VCP scanner requires 512 valid daily observations, no missing sessions or >40% one-day adjusted jumps in the recent 520 sessions, and a candle for the target session. This adds a conservative current-data guard to the historical experiment. The price floor uses today's adjusted price scale; this is not exact historical nominal-price accounting. Corporate-action adjustment defects can remain in public data. Earnings and sales in the book image are not modeled.

Each run publishes `vcp_scan.json` and `vcp_refresh_status.json` to `screen_output/`, `docs/` and `public/data/`. A failed run retains the dated snapshot and publishes a failure status. Fewer than 190 current stocks prevents replacement; any missing stock is blocked individually. The snapshot never moves backwards. Workflow-run identities connect the inputs, snapshot and refresh status.

The workflow commits data and explicitly republishes GitHub Pages. Railway fetches the validated JSON from GitHub with a one-minute cache, avoiding daily app deployments. Failed upstream requests serve a labelled cached fallback. The UI warns about fallback, failed/partial refreshes, mismatched run identities and attempts older than 36 hours. Daily end-of-day data is not an intraday quote feed.

## Reproduction and verification

```sh
python hhhl_refresh.py
python vcp_scanner.py
python scripts/sync_vcp_site.py
python -m unittest discover -s tests -p 'test_*.py' -v
npm test
python tests/browser_vcp.py --url http://localhost:3220/vcp.html --fixtures
```

The browser check verifies all 200 rows, all definitions and state filters, charts, downloads, mobile overflow, published evidence links and optional expected workflow-run identity. Local synthetic fixtures test lists longer than ten and data-load failure; fixtures are never published as market data. Scanner tests cover confirmation timing, previously triggered patterns, missing history, gaps, suspicious adjustments and stop references.

The original dated study remains [the historical report](../research/vcp/REPORT.md), with all 72 comparisons and trade logs. It did not establish a validated profitable edge. The website's historical report is frozen at 23 September 2026; only the scan updates daily.
