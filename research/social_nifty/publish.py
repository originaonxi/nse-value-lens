"""Publish the frozen social-source experiments; never selects a live trade."""
from pathlib import Path
import html,json,hashlib
ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/'artifacts/social_nifty'
SOURCES=[
 ('Reddit: expiry-only 9:20 straddle','https://www.reddit.com/r/IndiaAlgoTrading/comments/1wfc7nr/backtested_over_800_yt_trading_videos_on_12_years/','Author reports a loss in 43 daily paper sessions and a profit over eight expiry sessions. Self-reported, small forward sample; no independently audited record. Not reproduced here. An old options archive was located, but this pass did not test option legs or expiry selling.'),
 ('GitHub: opening-gap reversion','https://github.com/CuriousObservator/Systematic-Intraday-Mean-reversion-Strategy','Claims 29% CAGR on Indian stocks, but withholds thresholds and filters. Ranks gaps using opening prices and assumes opening-price fills; executable timing needs verification. Our Nifty gap rules are independent adaptations, not replication of that claimed return.'),
 ('X: RSI intraday rules','https://x.com/aseem_singhal/status/1261562154563428353','A 2020 post describes 15-minute RSI(14) crossings at 30 and 70 on Nifty constituent stocks in 2018. This is not evidence for current Nifty index profitability. The RSI(2) daily test below is a separate rule.'),
 ('Zerodha / StockViz: 5/50 trend following','https://zerodha.com/z-connect/varsity/could-trend-following-be-a-successful-trading-strategy-part-i','Published comparison on Nifty total-return data discusses costs and several historical periods. Our actual-futures test adds a stop, expiry exits and a 20-session holding cap, so it is not an exact reproduction.'),
 ('Zenodo: one-minute Nifty archive','https://zenodo.org/records/10899828','Aparna Bhat archive, 2017-2020. Download checksum verified; API metadata lists CC0. We used spot and NIFTY_F1 minute bars. The continuous futures series does not identify each contract or document its roll and timestamp conventions.'),
 ('NR7 discussion archive','https://main.icharts.in/forum/files/trading_nr7_setup_126.pdf','Public forum discussion defines the narrowest range in seven sessions. Our version waits for a subsequent closing breakout and enters the following open; it is not the original intraday entry.'),
 ('Reddit: failed-breakdown discussion','https://www.reddit.com/r/Daytrading/comments/1witz8t/i_ran_21_setups_people_teach_here_exactly_as/','Discussion concerns US markets and unverified author results. We tested a distinct daily Nifty adaptation using a failed break of the previous 20-session range.'),
]
NAMES={'failed_breakout':'Failed 20-day breakout','nr7_confirmation':'NR7 with closing confirmation','inside_confirmation':'Inside bar with closing confirmation','sma5_50':'5/50 moving-average trend','rsi2':'RSI(2) dip above the 200-day average','gap_fade':'Opening-gap reversal','gap_fade_confirmed':'Opening-gap reversal with confirmation','opening_range':'15-minute opening-range breakout'}

def read(name):return json.loads((ART/name).read_text())
def esc(x):return html.escape(str(x),quote=True)
def pct(x):return f'{x:+.2f}%'
def cell(x):return f'<td class="{"positive" if x>0 else "negative" if x<0 else ""}">{pct(x)}</td>'
def compact(r):return {k:v for k,v in r.items() if k not in ('curve','trade_log','monthly_returns')}
def table(rows,headers,caption):return '<div class="table-wrap"><table><caption>'+esc(caption)+'</caption><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
def main():
 daily=read('results.json');trend=read('trend_results.json');minute=read('minute/results.json')
 combined={**daily['results'],**trend['results']};snapshot={'as_of':'2026-09-23','validated':False,'sources':[{'title':t,'url':u,'assessment':a} for t,u,a in SOURCES],'daily':daily,'trend':trend,'minute':minute,'invalid_experiment':{'name':'long ETF history','status':'INVALID_ETF_PRICE_HISTORY','reason':'Downloaded NIFTYBEES falls roughly 90% in December2019 and reverses; no ETF result from that download is used. The older five-year website ETF experiments do not include this 2019 anomaly.'}}
 snapshot['input_sha256']={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'.cache/swing/NSEI.csv',ROOT/'.cache/derivatives/nifty_futures.csv',ROOT/'.cache/social_nifty/spot_futures.zip']}
 daily_rows=[];old_rows=[]
 for key,r in combined.items():
  recent=r['recent'];daily_rows.append('<tr><td>'+esc(NAMES[key])+'</td>'+cell(r['middle']['return_pct'])+cell(recent['return_pct'])+cell(r['recent_stress']['return_pct'])+f'<td>{recent["closed_trades"]}</td><td>{recent["max_eod_drawdown_pct"]:.2f}%</td></tr>')
 for key,r in minute['results'].items():
  later=r['later_conservative'];old_rows.append('<tr><td>'+esc(NAMES[key])+'</td>'+cell(r['earlier_conservative']['return_pct'])+cell(later['return_pct'])+cell(r['later_lower_cost']['return_pct'])+cell(r['later_stress']['return_pct'])+f'<td>{later["closed_trades"]}</td></tr>')
 trade_sections=[]
 for key,r in {**combined,**minute['results']}.items():
  old=key in minute['results'];windows=['earlier_conservative','later_conservative'] if old else ['middle','recent']
  trades=sorted([t for w in windows for t in r[w]['trade_log']],key=lambda t:(t['entry_date'],t.get('entry_label','')),reverse=True)[:10]
  rows=[]
  for t in trades:
   direction=t['side'];direction='LONG' if direction==1 else 'SHORT' if direction==-1 else direction
   entry=t['entry_date']+(' / '+t['entry_label'] if old else '');exit=t['exit_date']+(' / '+t['exit_label'] if old else '')
   rows.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in [direction,entry,f"{t['entry_price']:.2f}",exit,f"{t['exit_price']:.2f}",t['qty'],f"{t['pnl']:+,.2f}",t['reason']])+ '</tr>')
  rule=minute['plan']['rules'][key] if old else trend['plan']['rules'][key] if key in trend['results'] else daily['plan']['rules'][key]
  trade_sections.append('<details class="trade-history"><summary>'+esc(NAMES[key])+'</summary><p>'+esc(rule)+'</p>'+table(rows,['Direction','Entry date / bar label','Entry','Exit date / bar label','Exit','Units','Net P&L (Rs)','Exit reason'],NAMES[key]+' latest ten simulated trades')+'</details>')
 sources='<div class="cards">'+''.join('<article class="card"><h3><a href="'+esc(u)+'" rel="noopener noreferrer">'+esc(t)+'</a></h3><p>'+esc(a)+'</p></article>' for t,u,a in SOURCES)+'</div>'
 page='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Social strategy research | NSE Value Lens</title><link rel="stylesheet" href="swing.css"><style>.card h3{font-size:17px;line-height:1.4}.card p{font-size:12px;color:var(--muted)}.section p{max-width:900px}.section a{color:var(--green);text-decoration:underline}.trade-history .table-wrap{max-width:100%}.rules-list{max-width:850px;padding-left:24px}.rules-list li{padding:6px 0}main{min-width:0}.hero>div:first-child{max-width:730px}@media(max-width:600px){h1{font-size:38px}}</style></head><body><div class="shell"><header><a class="brand" href="index.html"><span class="brand-icon">N</span>VALUE LENS</a><nav><a href="strategy-lab.html">Strategy lab</a><a href="#results">Results</a><a href="#trades">Trades</a></nav></header><main><div class="eyebrow">REDDIT / X / GITHUB / PUBLISHED RESEARCH</div><section class="hero"><div><h1>Claims into tests.<br><span>Eight fixed experiments.</span></h1><p class="intro">A small recent RSI gain. Losses in the earlier period.<br>Every result below is exploratory; no strategy is validated.</p></div><div class="session"><span class="label">RESEARCH SNAPSHOT</span><strong>23 Sep 2026</strong><span>Historical simulations, not live returns</span></div></section><div class="notice warning">These specific tests do not support daily income or an always-profitable setup. Different test periods and position sizing are shown separately. No orders are placed.</div><section class="section" id="candidate"><h2>The candidate with a recent gain</h2><p><strong>RSI(2) dip above the 200-day average:</strong> +1.30% over nine recent trades, versus -2.14% in the preceding period. Doubling costs reduces the recent gain to +0.20%. The small sample and earlier loss prevent a trading recommendation.</p><ol class="rules-list"><li>After a completed daily Nifty candle, require close above SMA200 and Wilder RSI(2) below 10.</li><li>Buy the selected Nifty futures contract at the following open, with modeled adverse slippage. Skip an opening gap larger than one prior spot ATR.</li><li>Initial stop: entry minus two prior spot ATR(14). A gap through the stop exits at the worse opening price.</li><li>Exit at the next open after RSI(2) exceeds 70, or after five trading sessions; close before contract expiry. Keep only one position.</li></ol><p class="muted">Research sizing: Rs20 lakh starting capital, whole historical lots, fully reserved notional. The daily tests do not cap loss at 0.5% of capital; stops can gap. The futures results are not options results.</p></section><section class="section" id="results"><h2>Five recent Nifty futures tests</h2><p class="muted">Net total returns, not annualized. Earlier: 10 Sep 2024-12 Sep 2025. Recent: 15 Sep 2025-23 Sep 2026. Base fees 0.05% plus slippage 0.02% per side; stress doubles both. Scenario costs, before personal income tax. Actual NSE contract OHLC and historical lots; zero missing held daily bars.</p>'''
 page+=table(daily_rows,['Rule','Earlier net','Recent net','Recent stress','Recent trades','Recent EOD drawdown'],'Recent Nifty futures strategy comparisons')
 page+='''</section><section class="section"><h2>Three older intraday checks</h2><p class="muted">Minute data: 2017-2018 and 2019-2020, not the recent market. Rs20 lakh capital; full notional collateral and at most 0.5% planned stop risk per trade, including estimated costs. Base and stress assumptions match the table above; lower cost uses 0.01% fees plus 0.02% slippage per side. Integer lot sizing can change which trades are affordable as costs rise.</p>'''
 page+=table(old_rows,['Rule','2017-18 base','2019-20 base','2019-20 lower cost','2019-20 stress','Later base trades'],'Historical intraday Nifty futures proxy comparisons')
 page+='''<p class="muted">The archive contains 987 regular sessions. No duplicate or invalid OHLC bars were found. Some held intervals contain gaps, potentially including exchange halts: one earlier gap-fade trade and two later opening-range trades at base costs. They remain included and flagged. Contract identities, roll rules and bar timestamp conventions are undocumented. Signals and entries use separated bars to avoid filling at the price used to form the signal. These are proxy research results, not audited execution records.</p></section><section class="section" id="trades"><h2>Last 10 dated trades for each rule</h2><p class="muted">Base-cost runs only, newest entry first across both windows. LONG means buy then sell; SHORT means sell then buy. Prices include slippage; P&amp;L includes fees. Intraday times are source bar labels, not independently verified clock fill times. The intraday histories end in 2020.</p>'''+''.join(trade_sections)+'''</section><section class="section" id="sources"><h2>What the public claims actually provide</h2>'''+sources+'''</section><section class="section"><h2>Evidence limits and reproduction</h2><p>All rules were recorded before their new calculations, but the recent market history had already been inspected in earlier research. This is not untouched out-of-sample validation. Testing more ideas increases the risk of finding a lucky winner. The daily inside-bar rule is an independently specified hypothesis; a web result that originally suggested it redirected to an unrelated page and is not treated as verified evidence.</p><p>A separate long-history ETF test was invalidated by a roughly 90% price-unit discontinuity in December 2019. None of those invalid results is used on this page.</p><p><a href="SOCIAL_RESEARCH.md">Read methodology and reproduction commands</a> &middot; <a href="data/social_research.json">Download the complete result snapshot and trade logs</a> &middot; <a href="https://github.com/originaonxi/nse-value-lens/tree/master/research/social_nifty">Inspect the research code</a></p></section></main><footer><span>NSE VALUE LENS / SOCIAL RESEARCH</span><p>Research only. No assured returns.</p><a href="strategy-lab.html">Back to strategy lab</a></footer></div></body></html>'''
 md='''# Social-source Nifty research - 23 September 2026

Eight new fixed rules were checked. No consistent profitable strategy was established. RSI(2) had a small recent gain with nine trades, an earlier loss, and little gain remaining under stress. This is a candidate for further evidence, not a live recommendation.

## Recent actual-contract futures tests

Starting capital Rs20 lakh. Full notional collateral, integer historical lots, one position, no leverage or fixed fractional risk cap. Fee scenario 0.05% and slippage 0.02% each side; stress doubles both. Returns are net total returns, before personal income tax; idle cash earns no interest. EOD drawdowns can understate intraday loss.

Earlier: 2024-09-10 through 2025-09-12. Recent: 2025-09-15 through 2026-09-23. Cash is reset for each independent window.

| Rule | Earlier | Recent | Recent stress | Recent trades |
|---|---:|---:|---:|---:|
'''
 for key,r in combined.items():md+=f"| {NAMES[key]} | {pct(r['middle']['return_pct'])} | {pct(r['recent']['return_pct'])} | {pct(r['recent_stress']['return_pct'])} | {r['recent']['closed_trades']} |\n"
 md+='''
Signals use completed spot sessions; entries use the following futures open. Contract selection uses previous-day volume and expiry more than three calendar days away. Entry gaps greater than one prior spot ATR are skipped. Failed-breakout, NR7 and inside-bar tests use a 1 ATR stop and five-session cap; 5/50 trend and RSI(2) use 2 ATR stops, with 20- and 5-session caps respectively and next-open signal exits. All close three calendar days before expiry or at the test boundary. Stops use the worse opening price when gapped. Zero missing held contract bars in these runs. Full rules are in the adjacent JSON plans and snapshot.

### RSI(2) candidate

Require Nifty close above its 200-session SMA and Wilder RSI(2) below 10. Exit on the next open after RSI(2) exceeds 70, or at the fifth holding-session close, with the stop and expiry constraints above. Recent: six wins in nine trades, +1.30% net, 1.79% maximum EOD drawdown. Doubled costs: +0.20%. Earlier: -2.14% over 13 trades. This does not establish a dependable edge.

## Historical intraday futures proxy tests

Zenodo archive, 2017-2020; 987 regular sessions, checksum verified, CC0 according to record API metadata. Only the 9 MB spot/futures archive was downloaded; the separate options archive was not backtested. Minute futures have no contract identities and undocumented timestamp/roll conventions. These are research proxy fills, not audited exchange executions.

Same Rs20 lakh capital but with a 0.5% planned risk cap including costs; gaps can exceed it. Lot size 75, consistent with the [NSE 2021 change circular](https://archives.nseindia.com/content/circulars/FAOP47854.pdf). Gap rules use the mean of the preceding 14 daily true ranges for ATR. Signals at label09:20 fill at label09:22 open; range-break signals fill two timestamp minutes later. This leaves at least one full minute between signal completion and entry under either standard timestamp convention. Targets require 0.05 point trade-through; ambiguous bars assign the stop first. Exit label15:15 open, no overnight positions. No signal thresholds were tuned after these outcomes.

| Rule | 2017-18 base | 2019-20 base | 2019-20 lower cost | 2019-20 stress |
|---|---:|---:|---:|---:|
'''
 for key,r in minute['results'].items():md+=f"| {NAMES[key]} | {pct(r['earlier_conservative']['return_pct'])} | {pct(r['later_conservative']['return_pct'])} | {pct(r['later_lower_cost']['return_pct'])} | {pct(r['later_stress']['return_pct'])} |\n"
 md+='''
Lower cost means 0.01% fees plus 0.02% slippage per side; it is not an exact historical tariff and may understate current taxes. Base and stress match the daily table. Cost changes also alter affordable lot counts and later equity. No duplicate or invalid OHLC bars; some missing intervals, potentially exchange halts, remain flagged within held trades. Base costs: one affected earlier gap-fade trade, one affected earlier confirmed-fade trade, two affected later opening-range trades. None was silently removed. Full data audits and exclusions are in the JSON.

## Sources and claim assessment

'''
 for title,url,assessment in SOURCES:md+=f'- [{title}]({url}): {assessment}\n\n'
 md+='''## Limits

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
'''
 for folder in [ROOT/'docs',ROOT/'public']:
  (folder/'social-research.html').write_text(page,encoding='utf-8')
  (folder/'SOCIAL_RESEARCH.md').write_text(md,encoding='utf-8')
  (folder/'data').mkdir(exist_ok=True)
  (folder/'data/social_research.json').write_text(json.dumps(snapshot,allow_nan=False,separators=(',',':')),encoding='utf-8')
  path=folder/'strategy-lab.html';existing=path.read_text(encoding='utf-8')
  if 'social-research.html' not in existing:
   existing=existing.replace('<main>','<main><p class="muted"><a href="social-research.html"><strong>New: Reddit, X and GitHub ideas tested on Nifty, with dated trades</strong></a></p>',1);path.write_text(existing,encoding='utf-8')
 print('Published eight rules, source audit, full JSON and last10 dated trades for each rule.')
if __name__=='__main__':main()
