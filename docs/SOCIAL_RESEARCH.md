# Social-source Nifty research - 23 September 2026

Eight new fixed rules were checked. No consistent profitable strategy was established. RSI(2) had a small recent gain with nine trades, an earlier loss, and little gain remaining under stress. This is a candidate for further evidence, not a live recommendation.

## Recent actual-contract futures tests

Starting capital Rs20 lakh. Full notional collateral, integer historical lots, one position, no leverage or fixed fractional risk cap. Fee scenario 0.05% and slippage 0.02% each side; stress doubles both. Returns are net total returns, before personal income tax; idle cash earns no interest. EOD drawdowns can understate intraday loss.

Earlier: 2024-09-10 through 2025-09-12. Recent: 2025-09-15 through 2026-09-23. Cash is reset for each independent window.

| Rule | Earlier | Recent | Recent stress | Recent trades |
|---|---:|---:|---:|---:|
| Failed 20-day breakout | -2.05% | -0.19% | -1.93% | 16 |
| NR7 with closing confirmation | +1.37% | -1.51% | -3.67% | 20 |
| Inside bar with closing confirmation | -5.29% | -2.16% | -2.97% | 8 |
| 5/50 moving-average trend | -6.68% | -9.40% | -11.75% | 19 |
| RSI(2) dip above the 200-day average | -2.14% | +1.30% | +0.20% | 9 |

Signals use completed spot sessions; entries use the following futures open. Contract selection uses previous-day volume and expiry more than three calendar days away. Entry gaps greater than one prior spot ATR are skipped. Failed-breakout, NR7 and inside-bar tests use a 1 ATR stop and five-session cap; 5/50 trend and RSI(2) use 2 ATR stops, with 20- and 5-session caps respectively and next-open signal exits. All close three calendar days before expiry or at the test boundary. Stops use the worse opening price when gapped. Zero missing held contract bars in these runs. Full rules are in the adjacent JSON plans and snapshot.

### RSI(2) candidate

Require Nifty close above its 200-session SMA and Wilder RSI(2) below 10. Exit on the next open after RSI(2) exceeds 70, or at the fifth holding-session close, with the stop and expiry constraints above. Recent: six wins in nine trades, +1.30% net, 1.79% maximum EOD drawdown. Doubled costs: +0.20%. Earlier: -2.14% over 13 trades. This does not establish a dependable edge.

## Historical intraday futures proxy tests

Zenodo archive, 2017-2020; 987 regular sessions, checksum verified, CC0 according to record API metadata. Only the 9 MB spot/futures archive was downloaded; the separate options archive was not backtested. Minute futures have no contract identities and undocumented timestamp/roll conventions. These are research proxy fills, not audited exchange executions.

Same Rs20 lakh capital but with a 0.5% planned risk cap including costs; gaps can exceed it. Lot size 75, consistent with the [NSE 2021 change circular](https://archives.nseindia.com/content/circulars/FAOP47854.pdf). Gap rules use the mean of the preceding 14 daily true ranges for ATR. Signals at label09:20 fill at label09:22 open; range-break signals fill two timestamp minutes later. This leaves at least one full minute between signal completion and entry under either standard timestamp convention. Targets require 0.05 point trade-through; ambiguous bars assign the stop first. Exit label15:15 open, no overnight positions. No signal thresholds were tuned after these outcomes.

| Rule | 2017-18 base | 2019-20 base | 2019-20 lower cost | 2019-20 stress |
|---|---:|---:|---:|---:|
| Opening-gap reversal | -6.19% | -9.60% | -3.09% | -11.55% |
| Opening-gap reversal with confirmation | -3.32% | -4.35% | -1.49% | -7.60% |
| 15-minute opening-range breakout | -27.31% | -20.03% | -10.03% | -31.08% |

Lower cost means 0.01% fees plus 0.02% slippage per side; it is not an exact historical tariff and may understate current taxes. Base and stress match the daily table. Cost changes also alter affordable lot counts and later equity. No duplicate or invalid OHLC bars; some missing intervals, potentially exchange halts, remain flagged within held trades. Base costs: one affected earlier gap-fade trade, one affected earlier confirmed-fade trade, two affected later opening-range trades. None was silently removed. Full data audits and exclusions are in the JSON.

## Sources and claim assessment

- [Reddit: expiry-only 9:20 straddle](https://www.reddit.com/r/IndiaAlgoTrading/comments/1wfc7nr/backtested_over_800_yt_trading_videos_on_12_years/): Author reports a loss in 43 daily paper sessions and a profit over eight expiry sessions. Self-reported, small forward sample; no independently audited record. Not reproduced here. An old options archive was located, but this pass did not test option legs or expiry selling.

- [GitHub: opening-gap reversion](https://github.com/CuriousObservator/Systematic-Intraday-Mean-reversion-Strategy): Claims 29% CAGR on Indian stocks, but withholds thresholds and filters. Ranks gaps using opening prices and assumes opening-price fills; executable timing needs verification. Our Nifty gap rules are independent adaptations, not replication of that claimed return.

- [X: RSI intraday rules](https://x.com/aseem_singhal/status/1261562154563428353): A 2020 post describes 15-minute RSI(14) crossings at 30 and 70 on Nifty constituent stocks in 2018. This is not evidence for current Nifty index profitability. The RSI(2) daily test below is a separate rule.

- [Zerodha / StockViz: 5/50 trend following](https://zerodha.com/z-connect/varsity/could-trend-following-be-a-successful-trading-strategy-part-i): Published comparison on Nifty total-return data discusses costs and several historical periods. Our actual-futures test adds a stop, expiry exits and a 20-session holding cap, so it is not an exact reproduction.

- [Zenodo: one-minute Nifty archive](https://zenodo.org/records/10899828): Aparna Bhat archive, 2017-2020. Download checksum verified; API metadata lists CC0. We used spot and NIFTY_F1 minute bars. The continuous futures series does not identify each contract or document its roll and timestamp conventions.

- [NR7 discussion archive](https://main.icharts.in/forum/files/trading_nr7_setup_126.pdf): Public forum discussion defines the narrowest range in seven sessions. Our version waits for a subsequent closing breakout and enters the following open; it is not the original intraday entry.

- [Reddit: failed-breakdown discussion](https://www.reddit.com/r/Daytrading/comments/1witz8t/i_ran_21_setups_people_teach_here_exactly_as/): Discussion concerns US markets and unverified author results. We tested a distinct daily Nifty adaptation using a failed break of the previous 20-session range.

## Limits

Rules are adaptations, not exact reproductions of social profit claims. These previously inspected periods are not a pristine out-of-sample test. This research sits alongside earlier strategy searches; selecting the best recent result from many tests introduces selection bias. A separate downloaded long ETF history was invalidated after a roughly 90% December2019 unit anomaly; none of its returns is evidence here. The older five-year ETF website experiments exclude that date and are separate.

An inside-bar web search result redirected to an unrelated product page. It is retained in the original frozen plan as an audit trail, not cited as validated evidence. The inside-bar rule used here is independently specified.

## Reproduction

Run from repository root with its Python dependencies installed. Daily experiments require the existing `.cache/swing/NSEI.csv` history and official NSE `.cache/derivatives/nifty_futures.csv` collected by the existing research pipeline. Snapshot dates matter; rerunning against a later refreshed cache may change overlapping tests. Raw third-party minute data stays ignored under `.cache/`.

```powershell
python research/social_nifty/download_minute.py
python research/social_nifty/check.py
python research/social_nifty/trend_check.py
python research/social_nifty/minute/check.py
python research/social_nifty/publish.py
python -m unittest discover -s tests -p test_social_minute.py -v
```

Original plans are versioned beside their scripts. Generated intermediate outputs are in ignored `artifacts/social_nifty/`. The published JSON contains every cost scenario, curve, trade and plan, including dates, directions, entry/exit prices and fees where available. No automatic order placement is implemented.
