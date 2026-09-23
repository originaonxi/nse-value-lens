# Kasandra scanner: public signal and accounting review

Reviewed 23 September 2026. This review follows the user-supplied scanner link.

## Result

**The available evidence does not establish a best profitable setup to copy into NSE Value Lens.** The public Bitcoin Dip record is positive over just four closed trades. Gold Zones, Dow Zones and Gold Tetris show losses in the same public response.

This is a review of public descriptions and supplied outputs, including an arithmetic check of the Gold Zones demo ledger. It is not an independent backtest of the private entry algorithm.

## Public record snapshot

The [public record endpoint](https://kasandra-scanner.com/api/record) returned a response timestamp of **2026-09-23 19:48:39 UTC**. Values below are the provider's figures as captured, not verified account returns.

| Engine | Record starts | Closed | Wins / losses | Win rate | Reported net and labeled unit |
| --- | --- | ---: | ---: | ---: | --- |
| Gold Zones | 2026-09-12 | 74 | 55 / 19 | 74.32% | -67.3 pips |
| Dow Zones | 2026-09-11 | 66 | 30 / 36 | 45.45% | -1,080 points |
| Gold Tetris | 2026-09-12 | 1 | 0 / 1 | 0% | -57.6 pips |
| Bitcoin Dip | 2026-09-12 | 4 | 3 / 1 | 75% | +112.6 dollars |

Dates use the supplied epochs; broker event clocks need normalization. Gold Tetris also reported one open position. Gold and Dow returned only 40 visible trade rows each, so those lists alone cannot reconstruct the complete reported totals. The [track-record page](https://kasandra-scanner.com/track.html) describes engine output, spread deducted and no slippage. It is not a customer-account equity curve. Different units must not be added or compared as portfolio returns.

## Check of the public Gold Zones demo

The [public demo](https://app.kasandra-scanner.com/demo) labels itself delayed. Its response confirmed a **1,800-second delay**, version 5.0, and 3,000 fifteen-minute bars. The snapshot contained 168 closed base trades and 117 linked runners, all closed. These are reconstructed scanner-history outputs, distinct from the live recorder.

Using its supplied payouts and linking each runner to its originating trade:

| Calculation | Gold quote-price units per initial position unit |
| --- | ---: |
| Base-trade payouts | -169.008712 |
| Runner payouts | +208.941597 |
| Combined before displayed spread allowance | +39.932885 |
| Spread allowance: 168 x 3.2 x 0.1 | -53.760000 |
| Combined after that allowance | **-13.827115** |

This calculation follows the demo's displayed cost formula. It adds no commission, slippage or financing. It is not a rupee, account-dollar or percentage return, and it does not independently verify fills or signal availability.

A second check matched the recorder's 74 Gold Zones trades against the demo history. The supplied base payouts sum to **-67.308229**, which rounds to the public summary's **-67.3**. Including linked runners gives **-46.228024**; applying the demo spread formula gives **-69.908024**. Thus the public summary's net field matches a different subtotal from the demo's net calculation. The gold unit label also needs clarification: the demo profile defines 0.1 quote-price unit per pip.

This is a reproducible accounting discrepancy, not proof of fraud. The vendor would need to clarify costs, units, complete runner accounting and the meaning of each headline field.

## What can be reproduced

The [guide](https://kasandra-scanner.com/guide.html) outlines four approaches: trend pullbacks into zones, block-based gold trend changes, Bitcoin dips against an established trend, and a faster gold zone strategy. The exact trend, zone, block-size and entry-filter formulas remain on its server. The demo exposes results rather than those formulas.

A faithful strategy replica cannot be produced from the public descriptions. An independent trend-pullback implementation with our own explicit parameters would be a new experiment and should be labeled accordingly. No private endpoints, login bypasses or account registration were used.

Useful product ideas are dated entries/exits, explicit partial exits, separate recorded and reconstructed histories, downloadable trades, and a clear pre-entry alert state. These features do not establish profitability.

The advertised Gold Scalp 5 strategy was absent from the captured public record response, which included Dow Zones instead. Its performance remains unassessed here.

## Reproduce the accounting audit

The original HTML and JSON were kept locally under ignored `artifacts/` paths. The repository stores original analysis and aggregate results, not a copy of the website or its signal feed.

Public inputs used:

- [Recorder JSON](https://kasandra-scanner.com/api/record)
- [Delayed Gold Zones demo JSON](https://app.kasandra-scanner.com/api/demo?sym=XAUUSD.s&tf=15&n=3000)

Save these as `artifacts/kasandra_record.json` and `artifacts/kasandra_demo_snapshot.json`, then run:

```text
python research/kasandra/audit_public_snapshot.py
```

The script makes no network requests and places no orders. It writes [aggregate findings](../data/kasandra_public_review.json), with SHA-256 hashes identifying the local inputs. Fresh downloads may produce different results. Counts, units, open positions, unmatched runners and partial coverage must be considered before interpreting them.

## Implication for NSE research

This scanner currently supplies gold, Bitcoin and Dow-related outputs, not NSE 200 stock evidence. Its public ledger does not justify promoting a new NSE strategy. For an exact replication or independent historical test, the missing inputs are a disclosed rule specification and complete timestamped data at the rules' required resolution. A member CSV could permit a fuller output audit, but would still not reveal the entry algorithm.
