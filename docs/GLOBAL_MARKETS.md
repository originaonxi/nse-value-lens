# Commodity and forex charts

This is an independent addition to the Nifty 200 site. Its navigation link is
the only change to the existing stock page. Stock prices, classifications,
chart code, and the HHHL daily workflow are unchanged.

The watchlist contains 15 widely followed commodity futures benchmarks and 11
currency pairs, including USD/INR. It is a curated list, not a ranked measure of
global trading volume. Open `global-markets.html` and choose either dropdown.

## Sources and daily prices

Prices come from [Yahoo Finance](https://finance.yahoo.com/markets/commodities/)
through the maintained [yfinance project](https://github.com/ranaroussi/yfinance).
Commodity charts use provider daily futures OHLCV. Quotes retain their native
units: dollars per ounce/barrel, cents per bushel/pound, and so on. Rolling
contracts can introduce price gaps. The provider close is not presented as an
official exchange settlement. Data availability and permitted use follow the
provider's terms; this is a research display, not an exchange-grade data feed.

Direct Yahoo daily FX OHLC failed consistency checks during validation. The FX
charts therefore aggregate Yahoo hourly OHLC into sessions ending at 17:00
America/New_York (including daylight-saving changes). Open is the first reported
hour's open, high/low are observed extremes, and close is the last reported
hour's close. The current UTC date is excluded. No missing hour is filled with
an invented price. Weekend sessions and invalid days are omitted; at least 20
reported hourly observations are required per major-pair session, or eight for
the more limited indicative USD/INR feed. This is a coverage screen, not a
guarantee of every market tick. USD/INR is not the RBI reference rate.

Each FX candle uses actual available observations. FX volume is null and its
volume chart is hidden. The provider offers no centralized FX volume. Missing
or inconsistent recent records result in Caution; delayed candles retain their
real dates. The price-source foldout lists excluded dates and the session method.

## Chart rules

The new page retains the candle/HH-HL visual design. Quote precision and axis
padding accommodate forex rates and commodity units. The existing stock renderer
is not modified. High/low confirmation uses two earlier and two later sessions,
as in the stock chart. Global statuses describe price structure only:

- **BREAKOUT:** fresh close above the confirmed high with rising highs and lows.
- **BELOW LOW:** close below the latest confirmed low.
- **WATCH:** rising highs and lows without a fresh upward closing breakout.
- **NO SETUP:** highs and lows are not both rising.
- **CAUTION:** unreliable/late data, insufficient pivots, or an already-passed
  breakout level without a fresh crossing.

No Nifty gate, rupee price threshold, equity turnover minimum, or stock entry
band is applied to other asset classes. These labels are not a backtested
commodity or forex trading strategy.

## Automation and isolation

`.github/workflows/global_markets.yml` runs Monday–Saturday at **04:35, 07:35,
and 10:35 UTC** (10:05, 13:05, and 16:05 IST). Saturday captures Friday's global
session. The schedule is subject to GitHub Actions delays. The page shows the
last attempt time and flags an overdue refresh.

The workflow runs `global_markets.py`, stages only `data/global_prices/`,
`docs/global_markets.json`, and `public/data/global_markets.json`, and publishes
Pages explicitly after the bot commit. A failed provider download preserves the
last saved chart and its original retrieval/date information with Caution.
There is no dependency from the existing stock refresh to this workflow.

Local refresh: `python global_markets.py`.
UI mirror: `python scripts/sync_global_site.py`.
Data tests: `python -m unittest discover -s tests -p 'test_global_markets.py' -v`.
Browser checks: `python tests/browser_global_markets.py` with a local server.
