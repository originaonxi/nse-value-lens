# HH/HL daily automation: acceptance report

**Result: 10/10 real GitHub Actions pipelines passed.** Both public websites served fresh, complete 23 September 2026 closing data for all 200 stocks in every run.

These were sequential manual dispatches of the production workflow, including live source requests, recalculation, bot commits, Pages deployment, and HTTP/Chromium checks. They were not dry runs, cached UI-only replays, or ten assertions counted as ten runs.

## Run evidence

| Run | GitHub Actions evidence | Started (UTC) | Completed (UTC) | Both sites |
| --- | --- | --- | --- | --- |
| 1 | [35921569651](https://github.com/originaonxi/nse-value-lens/actions/runs/35921569651) | 2026-09-23T21:18:05Z | 2026-09-23T21:20:06Z | Fresh, 200/200, passed |
| 2 | [35921800620](https://github.com/originaonxi/nse-value-lens/actions/runs/35921800620) | 2026-09-23T21:20:18Z | 2026-09-23T21:23:25Z | Fresh, 200/200, passed |
| 3 | [35922151234](https://github.com/originaonxi/nse-value-lens/actions/runs/35922151234) | 2026-09-23T21:23:39Z | 2026-09-23T21:27:50Z | Fresh, 200/200, passed |
| 4 | [35922614603](https://github.com/originaonxi/nse-value-lens/actions/runs/35922614603) | 2026-09-23T21:28:06Z | 2026-09-23T21:30:15Z | Fresh, 200/200, passed |
| 5 | [35922860443](https://github.com/originaonxi/nse-value-lens/actions/runs/35922860443) | 2026-09-23T21:30:27Z | 2026-09-23T21:33:08Z | Fresh, 200/200, passed |
| 6 | [35923172875](https://github.com/originaonxi/nse-value-lens/actions/runs/35923172875) | 2026-09-23T21:33:23Z | 2026-09-23T21:36:17Z | Fresh, 200/200, passed |
| 7 | [35923482883](https://github.com/originaonxi/nse-value-lens/actions/runs/35923482883) | 2026-09-23T21:36:25Z | 2026-09-23T21:38:34Z | Fresh, 200/200, passed |
| 8 | [35923729534](https://github.com/originaonxi/nse-value-lens/actions/runs/35923729534) | 2026-09-23T21:38:52Z | 2026-09-23T21:41:11Z | Fresh, 200/200, passed |
| 9 | [35923980710](https://github.com/originaonxi/nse-value-lens/actions/runs/35923980710) | 2026-09-23T21:41:21Z | 2026-09-23T21:45:31Z | Fresh, 200/200, passed |
| 10 | [35924408101](https://github.com/originaonxi/nse-value-lens/actions/runs/35924408101) | 2026-09-23T21:45:41Z | 2026-09-23T21:47:55Z | Fresh, 200/200, passed |

## What passed

- Target date and exact refresh run ID reached GitHub Pages and Railway.
- Both sites served the corresponding snapshot generation time.
- All 200 unique stocks, category counts and BUY/data gates passed validation.
- All five filters, stock details, 200-row CSV download, mobile page width and JavaScript checks passed.
- The source refresh and bot commit led to an explicit Pages deployment on every run.
- Railway consumed the changing GitHub data without a data-only redeployment.

## Requested chart enhancement

The HH/HL chart overlay was added while the automation audit continued. Run 10 additionally verified the new charts on **both** live sites: the full confirmed swing history, 70 candles, zigzag, overlay toggles, clickable pivot/confirmation dates, and mobile scrolling. Earlier runs validated the original chart and automation.

HH/HL labels are green and LH/LL labels are red. Labels come from the scanner's full-history confirmed pivots. The latest two bars do not receive premature swing labels. Same-day high/low ambiguity breaks the connector rather than inventing intraday order.

The chart deployment on Railway reached SUCCESS: `5aa7b42c-4571-4ee6-b2a5-120db05677ee`.

## Additional checks

- 59 Python tests and 12 Node tests passed in [CI](https://github.com/originaonxi/nse-value-lens/actions/runs/35924349679).
- Regression cases cover the IST close cutoff, holidays, a future year, vendor failure, invalid candles, corporate actions, price-scale mismatches, future-bar leakage and pivot confirmation.
- A CI header encoding issue found during preparation was fixed before this ten-run acceptance audit began.

## Schedule and limits

The primary cron is 10:30 UTC / **16:00 IST**. Catch-up runs are at 16:25, 17:25, 19:25 and 22:25 IST, plus 08:25 the next morning. The page reports incomplete data and an overdue heartbeat.

The code has no fixed expiry year. These tests establish that the complete pipeline worked during this audit; they do not prove future cron delivery, precise 16:00 completion, uninterrupted data-provider availability, or 100 years of uptime. [GitHub documents schedule delays and inactivity limits](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

[Automation and recovery guide](HHHL_AUTOMATION.md) | [Machine-readable test report](hhhl_automation_test_report.json) | [Live scanner](https://originaonxi.github.io/nse-value-lens/hhhl.html)
