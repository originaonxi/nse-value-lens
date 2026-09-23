# Research library: 50 sources reviewed for NSE Value Lens

Checked: **23 September 2026**

## Scope and conclusion

All 50 supplied entries were attempted. This is a directory audit with selected deeper reading of publisher summaries, data documentation and access pages. It is not a claim to have read every paper, book, archive or video. Some sites only returned metadata or official-domain search results; CSInvesting remained unverified. Entry 50 is a probable identification.

The list contains useful research, but the headline overstates its contents. It combines delayed US disclosures, education, research, data tools and commercial products. It does not establish what billionaires currently buy or read. Several services have limited free tiers.

For this project's NSE 200 work, **momentum, quality and implementation costs are the highest-priority research themes**. This is a research judgment, not a new backtest result or a claim of daily profitability. The existing swing results remain the relevant measured evidence.

The [machine-readable directory](../data/research_library.json) records review depth, initial fetch outcomes, corrected URLs and access limitations. The [research corpus](../data/trading_research_sources.json) retains the project's earlier sources and adds the selected readings below.

## What the selected readings contribute

### 1. Momentum has evidence worth investigating

AQR's 2017 publisher summary discusses seven years of live portfolio experience and reports that momentum survived implementation frictions in the portfolios studied. This supports testing disciplined stock selection and turnover control. It does not validate an NSE 200 strategy with a maximum 20-session holding period. [Implementing Momentum: What Have We Learned?](https://www.aqr.com/Insights/Research/Working-Paper/Implementing-Momentum-What-Have-We-Learned)

Keep the evidence horizon explicit. The official Nifty200 Momentum 30 uses volatility-adjusted six- and twelve-month returns and semiannual rebalancing. A 20-session exit changes that strategy and needs independent evaluation. [NSE Indices methodology overview](https://www.niftyindices.com/indices/equity/strategy-indices/nifty200-momentum-30)

### 2. Quality is a separate hypothesis

AQR's Quality Minus Junk summary describes international evidence for profitable, growing, well-managed firms. Its long/short portfolio evidence cannot be carried directly into a long-only Indian swing test. A useful project question is whether a separately tested quality filter improves momentum's net return or drawdown. [Quality Minus Junk](https://www.aqr.com/Insights/Research/Working-Paper/Quality-Minus-Junk)

Quality data must have been public on the signal date. Compare appropriate accounting ratios within sectors; bank leverage is not directly comparable with industrial-company leverage. Adding valuation, quality and momentum into one arbitrary score would obscure which component helped.

### 3. Costs depend on the market and execution

AQR's trading-cost study uses institutional execution data across developed equity markets. Its cost estimates should not be copied into an Indian retail backtest. Report gross return, net return, turnover, slippage assumptions and cost stress separately. [Trading Costs](https://www.aqr.com/insights/research/working-paper/trading-costs)

### 4. The available date matters as much as the value

US 13F reports can arrive up to 45 days after quarter-end, omit short positions and describe holdings rather than precise trading decisions. Dataroma, WhaleWisdom and 13F.info are discovery tools; copying a quarter-end position before its filing date creates look-ahead bias. [SEC Form 13F FAQ](https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f)

ALFRED preserves historical vintages of macroeconomic series. A historical strategy must use the release available then, not today's revised value. [ALFRED](https://alfred.stlouisfed.org/)

For Indian fundamentals, collect exchange or issuer publications with broadcast timestamps, accounting periods, consolidated/standalone status and revision history. The quarter-end date is not the information-availability date. Start with [NSE corporate filings](https://www.nseindia.com/companies-listing/corporate-filings-application?id=allAnnouncements) and the linked financial-results/integrated-filing sections. Historical constituent membership is also required; today's NSE 200 list creates survivorship bias.

### 5. Valuation resources have coverage limits

Damodaran's data page provides industry and regional datasets, but explicitly says company-level data can no longer be shared. It is useful for valuation context and models, not a ready-made historical NSE company-fundamentals feed. [Damodaran data page](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/data.html)

### 6. Risk and behavior belong in the evaluation

Housel's essay emphasizes uncertainty, luck and the difficulty of living through investment outcomes. The project implication is to measure adverse outcomes and choose exposure that can be maintained through them. [The Psychology of Money](https://collabfund.com/blog/the-psychology-of-money/)

A losing year alone does not disprove positive long-run expectancy. Evaluate returns after costs, uncertainty, drawdown, recovery, concentration, benchmark exposure and genuinely unseen data. A rule that requires profits in every window is different from a useful investment objective. Reusing already examined periods does not create a fresh holdout.

## Concrete next research priorities

These are proposed experiments, **not implemented or validated trading recommendations**.

| Priority | Experiment | Required evidence/data |
| --- | --- | --- |
| 1 | Reproduce the official momentum methodology as a reference; separately freeze a 20-session swing adaptation before testing. | Historical NSE 200 membership, corporate-action-adjusted prices, official rebalance records, dated signals and cost assumptions. |
| 2 | Compare the same momentum rule with and without one predefined quality filter. | Financial statements as originally published, public timestamps, sector-appropriate metrics; no current fundamentals inserted into earlier dates. |
| 3 | Investigate continuation after earnings announcements. | Exact announcement times, consistent quarterly metrics, next-session fills and a fixed exit. An earnings surprise requires a defined expectation; revenue growth alone is not a surprise measure. |

First resolve data availability, then specify each experiment and reserve unseen data or forward paper-trading observations. Compare with a tradable broad-market benchmark and the unfiltered rule at comparable exposure. Retain all trials and dated trades, including rejected ideas. Publishing a research source must not change a strategy's validation status.

## Full 50-entry directory

Access descriptions reflect this review, not a promise that all features or downloads are free. Each name links to the most useful checked entrypoint; initial URLs and review methods are preserved in JSON.

| # | Source | Access observed | Use for this project / limitation |
| --- | --- | --- | --- |
| 1 | [Dataroma](https://www.dataroma.com/m/home.php) | Public holdings pages | Study disclosed US investor holdings; portfolio snapshots are delayed and incomplete trading signals. |
| 2 | [WhaleWisdom](https://whalewisdom.com/pricing) | Free tier; deeper history/tools paid | 13F research ideas. Verify publication dates and licensing before using historical downloads or automation. |
| 3 | [Capitol Trades](https://www.capitoltrades.com/about-us) | Public pages indexed; direct fetch failed | US politician transaction disclosures; distinguish transaction date from public disclosure date. |
| 4 | [OpenInsider](https://openinsider.com/) | Public screener indexed; direct fetch failed | US Form 4 transactions. Separate purchases from grants, gifts and option exercises; this is not NSE insider data. |
| 5 | [13F.info](https://13f.info/) | Public filing directory | Readable US fund filings; use filing availability, not quarter-end, as the earliest signal date. |
| 6 | [SEC EDGAR](https://www.sec.gov/search-filings) | Public official filings | Primary US filings. The supplied /edgar path redirected to submission tools; search-filings is the useful research entry. |
| 7 | [Berkshire Hathaway](https://www.berkshirehathaway.com/letters/letters.html) | Public letter archive | Business economics and capital allocation; long-term investment reasoning does not define a weekly entry rule. |
| 8 | [CNBC Buffett Archive](https://buffett.cnbc.com/annual-meetings/) | Official archive indexed; direct fetch blocked | Meeting recordings and transcripts for investing context. No videos watched in this review. |
| 9 | [Oaktree Capital](https://www.oaktreecapital.com/insights/memos) | Public memo index | Risk and cycle research; translate any proposed overlay into a measurable hypothesis. |
| 10 | [Bridgewater](https://www.bridgewater.com/research-and-insights) | Public research indexed; direct fetch failed | Macro frameworks; published essays do not reveal the firm's complete trading models. |
| 11 | [Principles](https://www.principles.com/) | Public material plus commercial books/products | Decision processes and risk thinking; the entire commercial catalog is not free. |
| 12 | [GMO](https://www.gmo.com/americas/research-library/) | Public research entry; full entitlements not audited | Long-horizon valuation and asset-allocation views; use dates and horizons explicitly. |
| 13 | [AQR](https://www.aqr.com/Insights/Research) | Public research and publisher summaries | Highest research priority here: momentum, quality and implementation costs. International results need separate NSE validation. |
| 14 | [Damodaran Online](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/data.html) | Public datasets and models; company-level data restricted | Industry/region valuation context. Data page says company-level data can no longer be shared. |
| 15 | [Damodaran blog](https://aswathdamodaran.blogspot.com/) | Public essays | Cash-flow and discount-rate reasoning; a valuation thesis alone does not specify a short holding period. |
| 16 | [Collaborative Fund](https://collabfund.com/blog/) | Public essays | Morgan Housel's work informs position sizing and the ability to endure adverse outcomes, rather than a mechanical buy signal. |
| 17 | [Farnam Street](https://fs.blog/) | Public articles/newsletter; membership and books offered | Mental models and decision journals; no quantified NSE trading edge established. |
| 18 | [JPMorgan Guide to the Markets](https://am.jpmorgan.com/us/en/asset-management/adv/insights/market-insights/guide-to-the-markets/) | Public guide landing page; full deck not reviewed | Market and valuation context. Trace each chart to its dated source before adding a feature. |
| 19 | [ARK Invest](https://www.ark-invest.com/research-center) | Public research center indexed; old path failed | Innovation theses from an asset manager; independently test valuation and forecasts. |
| 20 | [a16z](https://a16z.com/) | Public essays | Venture and technology research; limited direct fit for one-month NSE stock trading. |
| 21 | [CSInvesting](https://csinvesting.org/) | Unverified: direct access blocked | User-described value-investing lecture archive. Current content and availability could not be confirmed. |
| 22 | [Columbia value investing](https://business.columbia.edu/heilbrunn/resources/graham-and-doddsville-newsletter) | Current university pages indexed; old path failed | Use the Heilbrunn Center and Graham and Doddsville archive for case studies. |
| 23 | [FRED](https://fred.stlouisfed.org/) | Public official data | Macro inputs need release dates and vintages. ALFRED helps prevent use of later revisions in backtests. |
| 24 | [Federal Reserve](https://www.federalreserve.gov/) | Public official publications | Policy announcements and releases; align actual release time with the next tradable NSE session. |
| 25 | [European Central Bank](https://www.ecb.europa.eu/) | Public official publications | European policy and macro context; not a direct NSE earnings dataset. |
| 26 | [BIS](https://www.bis.org/) | Public official research/data entry | International credit and banking context; reporting frequency may be too slow for short swing signals. |
| 27 | [Trading Economics](https://tradingeconomics.com/api/pricing.aspx) | Public pages; commercial API | Useful macro discovery; chart access does not imply unlimited free historical data or redistribution rights. |
| 28 | [Macrotrends](https://www.macrotrends.net/) | Public pages indexed; direct fetch failed | Historical chart discovery. NSE coverage, adjustment quality and point-in-time fundamentals were not audited. |
| 29 | [Stock Analysis](https://stockanalysis.com/) | Public entry; full entitlements not audited | Company financial-data discovery. Confirm NSE coverage, restatements and download rights before research use. |
| 30 | [CompaniesMarketCap](https://companiesmarketcap.com/) | Public ranking entry | Current rankings provide context; they cannot reconstruct historical index membership. |
| 31 | [Finviz](https://finviz.com/) | Public screener; Elite paid | Predominantly US screening and charts; not the historical NSE 200 universe. |
| 32 | [Portfolio Visualizer](https://www.portfoliovisualizer.com/pricing) | Free tier has asset/history limits; paid plans | Useful portfolio comparisons; not a substitute for NSE order timing and cost modeling. |
| 33 | [TradingView](https://www.tradingview.com/) | Public/basic tools; paid features | Charts and explicit signal prototypes. Community scripts need independent timing and repainting checks. |
| 34 | [Koyfin](https://www.koyfin.com/pricing/) | Free and paid tiers | Visual market research; verify data coverage and export entitlements before pipeline use. |
| 35 | [AnnualReports](https://www.annualreports.com/) | Public archive entry | Locate company reports, then establish the original publication date and accounting version. |
| 36 | [Investor.gov](https://www.investor.gov/) | Public SEC education | Investor education and fraud awareness; not strategy performance evidence. |
| 37 | [Bogleheads wiki](https://www.bogleheads.org/wiki/Main_Page) | Public wiki indexed; direct fetch blocked | Diversification, costs and passive benchmarks provide a useful comparison for active trading. |
| 38 | [Investopedia](https://www.investopedia.com/) | Public explanatory articles | Terminology and concepts; trace empirical strategy claims to original research. |
| 39 | [Corporate Finance Institute](https://corporatefinanceinstitute.com/resources/) | Free resource guides; paid training | Accounting and valuation definitions; distinguish guides from paid credentials. |
| 40 | [CFA Institute](https://www.cfainstitute.org/insights) | Public research entry; full journal access not audited | Professional research and methodology; check availability and the actual paper behind each claim. |
| 41 | [Morningstar](https://www.morningstar.com/business/insights/research) | Public research plus paid Investor product | Fund and stock research; ratings alone are not point-in-time NSE swing signals. |
| 42 | [Simply Wall St](https://simplywall.st/plans) | Limited free tier; paid plans | Visual fundamentals and screening; snapshot financials cannot be inserted into earlier backtest dates. |
| 43 | [Value Investors Club](https://www.valueinvestorsclub.com/) | Registration gives delayed ideas; current access selective | Free registered access is delayed 45 days. Treat theses as research leads with publication timestamps. |
| 44 | [ETF Database](https://etfdb.com/tools/) | Public tools indexed; Pro paid; direct root blocked | ETF holdings and classification; US ETF coverage does not establish NSE stock-selection skill. |
| 45 | [Curvo](https://curvo.eu/backtest/en) | Public Backtest tool; investing service separate | European fund portfolio backtests. Correct tool is /backtest/en; not an NSE execution engine. |
| 46 | [Of Dollars and Data](https://ofdollarsanddata.com/) | Public blog | Data-based investing essays; inspect dataset, sample and portfolio assumptions behind each conclusion. |
| 47 | [A Wealth of Common Sense](https://awealthofcommonsense.com/) | Public blog | Market history and portfolio behavior; useful context rather than a ready-made NSE signal. |
| 48 | [The Irrelevant Investor](https://www.theirrelevantinvestor.com/) | Official blog indexed; initial URL rate-limited | Market and investor-behavior commentary; use the current www address. |
| 49 | [Visual Capitalist](https://www.visualcapitalist.com/about/) | Public material indexed; VC+ paid; direct root blocked | Charts for discovery; obtain the original underlying data before building a strategy. |
| 50 | [Our Finite World (probable match)](https://ourfiniteworld.com/) | Public blog; identity inferred from incomplete user entry | Gail Tverberg's energy/economy commentary. User supplied no confirming note; not a holdings tracker. |

## Corrections and access details

- **SEC:** use [Search Filings](https://www.sec.gov/search-filings); the supplied /edgar route redirected to filing submission.
- **Columbia:** the current university resource is the [Heilbrunn Center](https://business.columbia.edu/heilbrunn), including Graham and Doddsville.
- **ARK and Curvo:** use the research-center and backtest links in the table.
- **Value Investors Club:** its landing page describes 45-day-delayed ideas after registration; current access requires acceptance. No registration was performed.
- **WhaleWisdom:** its [subscription information](https://whalewisdom.com/info/subscription_info) limits free access and prohibits automated scripting on the free service. Public readability is not an API license.
- **Our Finite World:** the likely match is Gail Tverberg's energy/economy blog. The user supplied an incomplete name and no confirming note, so the match remains explicitly unconfirmed.
- Free-tier limits and endpoints may change; verify the relevant product and data terms before building an ingestion pipeline.

Only source metadata and original summaries are stored here. This review adds no simulated profits and does not revise previous strategy results.
