# Automatic daily HH/HL refresh

The [scanner](https://originaonxi.github.io/nse-value-lens/hhhl.html) is refreshed by [HHHL daily refresh](https://github.com/originaonxi/nse-value-lens/actions/workflows/hhhl_daily.yml). No personal access token or manual daily command is required. GitHub's built-in repository token commits the data and deploys Pages explicitly.

## Schedule

| Purpose | IST | UTC cron |
| --- | --- | --- |
| Primary after-close check | 16:00 | 30 10 * * * |
| Catch-up | 16:25, 17:25, 19:25, 22:25 | 55 10,11,13,16 * * * |
| Overnight recovery | 08:25 next morning | 55 2 * * * |

Checks run every calendar day to include special weekend sessions. Before 16:00 IST, the current date is excluded. The dynamically fetched NSE holiday calendar supplies the expected session. Positive trading volume across at least 100 constituents can establish a special session. If the holiday API fails, weekends are known but an unverified weekday is never silently treated as a holiday. A late special session can be caught by the 22:25 or next-morning run.

16:00 is the **requested start**, not a promised completion time. Source publication, Actions queues, calculations and deployment take additional time.

## What each run does

1. Fetch the official Nifty 200 list; require exactly 200 unique EQ symbols. A failed constituent fetch retains the saved membership and explicitly marks it unverified.
2. Fetch adjusted daily history for all constituents and Nifty. Keep persistent, versioned histories in `data/hhhl_prices/`; the job survives an empty Actions cache. Request full history when adjustments change or the last stored session is too old.
3. Validate dates, OHLC and volume. Reject unfinished candles and future dates.
4. Where available, use NSE's official security-wise closing file. An ex-date corporate action or mismatched previous close prevents mixing that raw candle with adjusted history. Failure of the corporate-action feed disables this fallback. Official NSE index OHLC can repair missing benchmark sessions.
5. Recalculate confirmed HH/HL pivots, ATR, market gate, and BUY / SELL / WATCH / CAUTION / AVOID for all 200 stocks.
6. Publish a partial scan only when at least 190 current candles exist. Missing stocks remain CAUTION; an incomplete index gate blocks new BUY entries. A broader outage preserves the previous dated snapshot and publishes a waiting/failed status.
7. Commit histories, snapshot and status using a shared single-writer queue and bounded push retries. Each status carries its actual Actions run ID.
8. Deploy GitHub Pages **inside this workflow**. This avoids relying on a bot commit triggering another push workflow.
9. Verify both public websites with HTTP and Chromium: matching run ID and snapshot, all 200 unique stocks, five filters, detail view, 200-row CSV, mobile width, and no JavaScript errors. Save the report and screenshots as Actions artifacts.

Railway reads HH/HL data from the repository with a one-minute cache. It needs no daily code deployment. An already-open page reloads its data every five minutes.

## Visible status

- **Fresh:** 200 complete closes, all 200 rechecked for the target session, current membership verified, benchmark history complete.
- **Partial:** a usable dated scan, with the missing checks explicitly listed.
- **Waiting:** new closing data is not sufficiently available; the previous scan remains dated.
- **Failed:** a refresh error; the previous scan remains available.
- **Refresh overdue:** no heartbeat for more than 27 hours. This warning is computed in the browser, so it still appears if Actions stops entirely.

A passing workflow means that the refresh and publication pipeline operated correctly. It does **not** mean every upstream quote was available: inspect its fresh/partial/waiting state.

## Operation and recovery

To run the same complete pipeline manually:

```sh
gh workflow run hhhl_daily.yml
```

For a labelled end-to-end audit (the label does not bypass fetching or publishing):

```sh
gh workflow run hhhl_daily.yml -f test_label=E2E-01
```

Review the workflow summary, the `hhhl-refresh-audit` artifact, and `hhhl-end-to-end` artifact. A hard refresh error still publishes its failure status; live verification then fails visibly. There is no automatic order placement.

## Longevity and platform limits

There is no fixed expiry year in the date calculation. Daily status commits create continuing repository activity. Nevertheless, this cannot guarantee a century of unattended service: GitHub, Railway, account settings and market-data endpoints can change. GitHub schedules can be delayed or dropped, and scheduled workflows in inactive public repositories can be disabled after 60 days. Later cron slots recover individual missed runs; they cannot restart a workflow that GitHub has disabled.

See [GitHub schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) and [built-in token trigger behavior](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow). No cron job can prove tomorrow's scheduler delivery through today's manual tests.

The rules remain research signals, with no assured returns. Source-quality checks and operational tests do not validate trading profitability.
