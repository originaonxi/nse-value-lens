"""Render the reproducible VCP research report and static research figures."""
from __future__ import annotations
from datetime import datetime, timezone
import gzip
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
sys.path.append(str(ROOT/'.cache/vcp-plot'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import matplotlib.dates as mdates
import vcp_research as v

OUT = v.OUT
LABELS = {'atr_trail':'Daily 2-ATR trailing stop', 'weekly_sma10':'Weekly close below 10-week SMA',
          'target_3r':'Profit target at 3 times initial risk'}


def pct(x):
    return 'n/a' if x is None else f'{x:+.2f}%'


def rupees(x):
    return f'Rs {x:,.0f}'


def metric_table(rows):
    return ('| Version | Full return | Annualized | Drawdown | Trades | Later return | Later, doubled costs |\n'
            '|---|---:|---:|---:|---:|---:|---:|\n' + '\n'.join(
            f"| {LABELS[r['config']['exit']]} | {pct(r['full']['total_return_pct'])} | {pct(r['full']['cagr_pct'])} | "
            f"{r['full']['max_drawdown_pct']:.2f}% | {r['full']['closed_trades']} | {pct(r['later']['total_return_pct'])} | "
            f"{pct(r['later_stress']['total_return_pct'])} |" for r in rows))


def plot_summary(result, selected):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'axes.titleweight':'bold',
                         'figure.facecolor':'#faf9f6','axes.facecolor':'#faf9f6'})
    fig,axes = plt.subplots(2,2,figsize=(14,9),gridspec_kw={'height_ratios':[1.25,1]})
    full = selected['full']
    tri = result['total_return_benchmarks']['full']
    for records,label,color in [(full['curve'],'VCP: selected using 2016-2023','#167b80'),
                                (tri['curve'],'Nifty 200 total-return index','#6a6a78')]:
        data = pd.DataFrame(records)
        dates = pd.to_datetime(data.date)
        axes[0,0].plot(dates,data.equity/100000,label=label,color=color,lw=2)
        equity = np.r_[100000,data.equity.to_numpy()]
        drawdown = 100*(equity/np.maximum.accumulate(equity)-1)[1:]
        axes[1,0].plot(dates,drawdown,color=color,lw=1.3,label=label)
    axes[0,0].set_title('Growth of Rs 1 lakh | 2016-2026',loc='left')
    axes[0,0].set_ylabel('Account value, lakh rupees')
    axes[0,0].legend(frameon=False,fontsize=8,loc='upper left')
    axes[1,0].set_title('Daily closing drawdown',loc='left')
    axes[1,0].set_ylabel('Drawdown (%)')
    axes[1,0].axhline(0,color='#bbbbbb',lw=.6)
    compare = [r for r in result['results'] if r['config']['pattern']=='three_or_two_smaller'
               and r['config']['entry']=='intraday_pivot' and not r['config']['market_filter'] and not r['config']['pyramid']]
    labels = ['2-ATR trail','10-week exit','3R target']
    x = np.arange(3)
    axes[0,1].bar(x-.18,[r['later']['total_return_pct'] for r in compare],.36,label='Base costs',color='#167b80')
    axes[0,1].bar(x+.18,[r['later_stress']['total_return_pct'] for r in compare],.36,label='Doubled costs',color='#d46b4c')
    axes[0,1].set_xticks(x,labels)
    axes[0,1].set_ylabel('Total return (%)')
    axes[0,1].set_title('Later period | Jan 2024-Sep 2026',loc='left')
    axes[0,1].axhline(0,color='#aaa',lw=.7)
    axes[0,1].legend(frameon=False,fontsize=9)
    years = full['metrics']['annual_returns_pct']
    colors = ['#167b80' if val>=0 else '#d46b4c' for val in years.values()]
    axes[1,1].bar(list(years),list(years.values()),color=colors)
    axes[1,1].set_title('Selected rule: calendar-year returns',loc='left')
    axes[1,1].set_ylabel('Return (%)')
    axes[1,1].tick_params(axis='x',rotation=45)
    axes[1,1].axhline(0,color='#aaa',lw=.7)
    for ax in axes.flat:
        ax.grid(axis='y',alpha=.18)
        ax.set_axisbelow(True)
    fig.suptitle('VCP on the current Nifty 200 stocks: some profit, limited evidence',x=.055,y=.98,ha='left',fontsize=18,fontweight='bold')
    fig.text(.055,.928,'Frozen 72-variant comparison. Selected model allows two shrinking pullbacks; strict three-pullback rule trades rarely.',fontsize=10,color='#555')
    fig.text(.055,.018,f"As of 23 Sep 2026. Current-member survivorship bias. Strategy averages {full['metrics']['average_exposure_pct']:.1f}% invested; index is fully invested.\n"
             'Adjusted-price simulation, costs included; cash earns zero. This is not a risk-matched alpha comparison.',fontsize=9,color='#555')
    fig.tight_layout(rect=[.04,.065,.99,.905],h_pad=2.4,w_pad=2)
    for extension in ['png','svg']:
        fig.savefig(OUT/f'vcp_results.{extension}',dpi=170)
        if extension == 'svg':
            svg = OUT/'vcp_results.svg'
            svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines())+'\n', encoding='utf-8', newline='\n')
    plt.close(fig)


def plot_examples(selected):
    trades = sorted(selected['later']['trades'],key=lambda t:t['entry_date'])
    examples = [next(t for t in trades if t['net_pnl']>0), next(t for t in trades if t['net_pnl']<0)]
    fig,axes = plt.subplots(2,2,figsize=(14,8),gridspec_kw={'height_ratios':[3,1]},sharex='col')
    captions = []
    for col,t in enumerate(examples):
        d,_ = v.load_prices(v.CACHE/(t['symbol']+'.NS.csv'),v.PLAN['as_of'])
        d = d.loc[d.Volume>0]
        w = d.resample('W-FRI').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
        w['sma10'] = w.Close.rolling(10).mean()
        first = pd.Timestamp(t['pattern']['pivot_dates'][0])-pd.Timedelta(weeks=4)
        last = pd.Timestamp(t['exit_date'])+pd.Timedelta(weeks=2)
        w = w.loc[first:last]
        x = mdates.date2num(w.index)
        price_ax,vol_ax = axes[0,col],axes[1,col]
        colors = np.where(w.Close>=w.Open,'#167b80','#d46b4c')
        for xx,row,color in zip(x,w.itertuples(),colors):
            price_ax.vlines(xx,row.Low,row.High,color=color,lw=.9)
            price_ax.add_patch(Rectangle((xx-2.1,min(row.Open,row.Close)),4.2,
                                        max(abs(row.Close-row.Open),.001*row.Close),color=color,alpha=.9))
        price_ax.plot(w.index,w.sma10,color='#888',lw=1.2,label='10-week SMA')
        price_ax.axhline(t['pattern']['pivot'],color='#3377aa',ls='--',lw=1,label='Known buy pivot')
        price_ax.axvline(pd.Timestamp(t['entry_date']),color='#222',ls=':',lw=1)
        price_ax.scatter([pd.Timestamp(t['entry_date'])],[t['entry_price']],marker='^',s=85,color='#167b80',zorder=5)
        price_ax.scatter([pd.Timestamp(t['exit_date'])],[t['exit_price']],marker='v',s=85,color='#d46b4c',zorder=5)
        points = t['pattern']['pivot_dates']
        for j,date in enumerate(points):
            week_end = pd.Timestamp(date).to_period('W-FRI').end_time.normalize()
            if week_end not in w.index:
                continue
            value = w.loc[week_end,'High' if j%2==0 else 'Low']
            label = f'H{j//2+1}' if j%2==0 else f'L{j//2+1}'
            price_ax.annotate(label,(week_end,value),xytext=(0,13 if j%2==0 else -17),
                              textcoords='offset points',ha='center',fontsize=8,fontweight='bold')
        depth_text = ' > '.join(f'{100*depth:.1f}%' for depth in t['pattern']['depths'])
        price_ax.set_title(f"{t['symbol']} | {pct(t['net_return_pct'])} net position return",loc='left',fontsize=12)
        price_ax.text(.015,.98,f"{t['pattern']['count']} pullbacks: {depth_text}\nEntry {t['entry_date']} | Exit {t['exit_date']}",
                      transform=price_ax.transAxes,va='top',fontsize=9,bbox={'facecolor':'white','alpha':.85,'edgecolor':'none'})
        price_ax.set_ylabel('Adjusted price (Rs)')
        vol_ax.bar(w.index,w.Volume/1e6,color=colors,width=4.5)
        vol_ax.set_ylabel('Volume (m)')
        vol_ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3,maxticks=6))
        vol_ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
        price_ax.grid(axis='y',alpha=.15)
        vol_ax.grid(axis='y',alpha=.15)
        captions.append({'symbol':t['symbol'],'entry_date':t['entry_date'],'exit_date':t['exit_date'],
                         'pattern':t['pattern'],'net_return_pct':t['net_return_pct']})
    fig.suptitle('One winner and one loser from the later-period test',x=.06,y=.97,ha='left',fontsize=17,fontweight='bold')
    fig.text(.06,.925,'Examples chosen as the earliest-entry winning and losing positions; green/red triangles show simulated entry/exit.',fontsize=10)
    fig.text(.06,.015,'Weekly candles and volume. Pivots become usable only after the following week closes. These are retrospective examples, not published live calls.',fontsize=9)
    fig.tight_layout(rect=[.04,.06,.99,.90],h_pad=.7,w_pad=2)
    fig.savefig(OUT/'vcp_examples.png',dpi=170)
    plt.close(fig)
    v.json_write(OUT/'chart_examples.json',captions)


def make_report(result,selected,sensitivity):
    row = next(r for r in result['results'] if r['id']==result['selected_id'])
    same_entries = [r for r in result['results'] if r['config']['pattern']=='three_or_two_smaller'
                    and r['config']['entry']=='intraday_pivot' and not r['config']['market_filter'] and not r['config']['pyramid']]
    strict = [r for r in result['results'] if r['config']['pattern']=='three'
              and r['config']['entry']=='intraday_pivot' and not r['config']['market_filter'] and not r['config']['pyramid']]
    benchmark = result['total_return_benchmarks']
    full,later = row['full'],row['later']
    late_conf = result['selected_later_uncertainty']['mean_r_95pct_interval']
    audit = json.loads((OUT/'data_audit.json').read_text())
    lines = [
        '# Minervini-style VCP on the current Nifty 200 universe',
        '', 'Snapshot: **23 September 2026**. Test: **1 January 2016 to 23 September 2026**, with 2014-2015 for warm-up.', '',
        '**Verdict: some mechanical variants made money after costs, but this study does not establish a reliable or attractive standalone strategy.** '
        'The strict three-contraction rule generated too few trades. The more permissive two-contraction version was profitable with a weekly trend exit, '
        'but its gains were concentrated, average investment was low, and later results were sensitive to account size and costs.', '',
        f"The rule selected using 2016-2023 data turned **Rs 100,000 into {rupees(full['ending_equity'])}**: "
        f"**{pct(full['total_return_pct'])} total**, **{pct(full['cagr_pct'])} annualized**, **{full['max_drawdown_pct']:.2f}%** closing drawdown. "
        f"It closed **{full['closed_trades']} trades**, winning **{full['win_rate_pct']:.2f}%**, with net profit factor **{full['profit_factor']:.2f}**. "
        f"Average capital invested was only **{full['average_exposure_pct']:.2f}%**; idle cash earned zero.", '',
        f"Over the same period, the official Nifty 200 total-return index grew **{pct(benchmark['full']['metrics']['total_return_pct'])}** "
        f"(**{pct(benchmark['full']['metrics']['cagr_pct'])} annualized**). It remained fully invested and had "
        f"**{benchmark['full']['metrics']['max_drawdown_pct']:.2f}%** closing drawdown. This is an account-growth comparison, not risk-matched alpha. "
        'The index includes gross reinvested dividends but excludes fund costs. [Official index-history source](https://www.niftyindices.com/reports/historical-data).', '',
        '![Equity, drawdown and exit comparisons](vcp_results.png)', '',
        '## Exit comparison', '',
        'Identical entries: three shrinking weekly pullbacks, or two with any positive reduction; intraday pivot entry; no index gate; no additions. '
        'Later period starts flat on 1 January 2024 and ends 23 September 2026. All numbers include costs.', '',
        metric_table(same_entries), '',
        'These are total portfolio returns, not the return from putting all capital into every signal. Three exit rules were specified before calculating returns. '
        'The profitable weekly exit lets occasional large winners run; the tight daily ATR trail and fixed 3R target performed less well.', '',
        '## What happened to the strict version?', '',
        'Keeping the three-contraction requirement, the same intraday/no-index-filter entry produced:', '',
        *[f"- {LABELS[r['config']['exit']]}: **{pct(r['full']['total_return_pct'])}**, {r['full']['closed_trades']} closed trades over the entire test." for r in strict], '',
        'The two-contraction exception was tested both as at least 70% smaller and as simply smaller. Relaxing that exception is a different implementation; '
        'the permissive version must not be presented as proof that the strict rule works. Adding to winners was included in the grid, but **no new higher qualifying VCP add occurred while a position was held**. '
        'The add-on/off variants therefore do not provide empirical evidence about pyramiding.', '',
        '## Selection, later evidence and sensitivity', '',
        'The 72 combinations cover 3 contraction definitions x 2 entry methods x 3 exits x 2 market gates x 2 add policies. '
        'They are correlated variations, not 72 independent discoveries. The criteria and dates are in [plan.json](plan.json). '
        '[selection.json](selection.json) was written before later-period simulations. Development: 2016-2020; validation: 2021-2023; later: 2024-September 2026. '
        'No rule reached the predeclared minimum of 20 trades and positive returns in each earlier period. The selected rule is an exploratory choice, not a qualified winner. '
        'The later years were already used in other repository research, so they are not pristine unseen or prospective evidence.', '',
        f"- Selected rule: earlier total **{pct(row['development']['total_return_pct'])}** ({row['development']['closed_trades']} trades); "
        f"validation **{pct(row['validation']['total_return_pct'])}** ({row['validation']['closed_trades']} trades); "
        f"later **{pct(later['total_return_pct'])}** ({later['closed_trades']} trades).",
        f"- Later doubled-cost result at Rs 1 lakh: **{pct(row['later_stress']['total_return_pct'])}**. "
        'A higher per-share risk prevented the single-share DIXON trade from fitting the 0.5% risk budget. This is a real whole-unit/account-size sensitivity in the model, not only fee drag.',
        f"- Rs 10 lakh account, same 0.5% risk rule: later **{pct(sensitivity['capital_1000000_later_cost1']['total_return_pct'])}** at base costs and "
        f"**{pct(sensitivity['capital_1000000_later_cost2']['total_return_pct'])}** at doubled costs. Increasing capital changes rounding and fixed-charge effects; this is not extra leverage.",
        f"- Restricting bases to 4-8 weeks, without reselecting the model: full **{pct(sensitivity['four_to_eight_weeks_full']['total_return_pct'])}** "
        f"({sensitivity['four_to_eight_weeks_full']['closed_trades']} trades); later **{pct(sensitivity['four_to_eight_weeks_later']['total_return_pct'])}**.",
        f"- Excluding every security with a flagged >40% adjusted daily jump: full **{pct(sensitivity['exclude_flagged_full']['total_return_pct'])}**; "
        f"later **{pct(sensitivity['exclude_flagged_later']['total_return_pct'])}**. This is a retrospective source-quality diagnostic, not a deployable filter.",
        f"- Later mean net R has a 95% entry-month cluster-bootstrap interval of **{late_conf[0]:.2f} to {late_conf[1]:.2f} R**. "
        'It includes losses. With only six entry-month clusters, uncertainty is large; this does not correct for trying multiple variants.',
        f"- Removing the best later trade's P/L arithmetically leaves **{rupees(sensitivity['profit_concentration_later']['arithmetic_pnl_without_best_trade'])}**. "
        'This is a contribution diagnostic, not a replay with different capital sizing.', '',
        'Full-run annual returns differ from separately restarted periods because existing positions can cross period boundaries. IRFC was entered in December 2023 and exited in April 2024; '
        'it contributes to the continuous full run but is not retroactively inserted into a later-period portfolio that starts flat.', '',
        '![A winning and losing later-period VCP](vcp_examples.png)', '',
        '## Exact translation of the image and supplied rules', '',
        '| Supplied idea | Reproducible implementation |', '|---|---|',
        '| Weekly stock selection | Refresh after the last session of a completed Friday-ending week; list usable next session. Incomplete latest week excluded. |',
        '| Price and trend filters | Nominal-price proxy >= Rs 30; adjusted close >=75% of 252-session high and >=2x 252-session low; close > SMA50 > SMA200. SMA200 increases at each of the last 13 weekly observations. |',
        '| High every 4-6 months | At least one fresh 252-session high in each of the last two 26-week blocks, with no high drought longer than 26 weeks. This is an explicit interpretation. |',
        '| Contracting price and time | Weekly pivots confirmed with one week on each side; 3 H-to-L depth reductions, rising lows, non-increasing pullback duration. Two-pullback alternatives disclosed separately. |',
        '| Contracting volume | Final pullback average volume below prior pullback and preceding rally; below prior 10-week volume average; up-week volume exceeds down-week volume over the base. |',
        '| Base duration | 4-26 weeks for the main test; final low no more than 8 weeks old. The image itself depicts a multimonth pattern. Separate 4-8-week sensitivity provided. |',
        '| Daily breakout entry | Either a buy-stop at the known pivot plus 0.1%, or a daily closing breakout with volume >=1.5x prior 50-day average followed by next-open entry. Reject fills >5% above pivot. |',
        '| Stop | Entry minus min(2 x prior daily Wilder ATR20, 10% of entry). Gaps can exceed the stop. No fixed maximum hold. |',
        '| Add to winners | At most one add on a different higher VCP after >=1R unrealized profit, with 0.25% add risk and 0.5% combined planned open risk. No qualifying adds occurred. |',
        '| Post-buy character | Green/red days, tennis-ball behavior and shallow pullbacks are qualitative observations, not fully specified rules. No future-looking post-entry success filter was applied. |',
        '| Earnings and sales in image | Not tested: the repo lacks publication-dated historical earnings/sales data. This is the requested price/volume proxy, not the entire discretionary SEPA system. |', '',
        'Additional declared execution assumptions: prior average turnover >= Rs 1 crore; start Rs 1 lakh; 0.5% planned risk per stock including costs; '
        'maximum five stocks, two per current industry, 20% initial allocation per stock; no borrowing. Rank candidates by final contraction depth, then prior turnover and symbol. '
        'Cash and slots are reserved before observing the day\'s high. Cash from same-day sales is not recycled into earlier entries. '
        'Stop and target touched on the same bar takes the stop first. The entry-day low is handled pessimistically where OHLC ordering is ambiguous. '
        'Trailing stops only move for the next session. Missing held bars freeze the last mark and are counted. Period-end positions are liquidated with costs.', '',
        'Cost scenario per side: **0.15% fees/taxes + 0.05% adverse slippage**, plus **Rs 20 per stock exit**. Stress doubles all three and reruns the portfolio. '
        'This is a scenario, not reconstructed broker invoices or historical tariffs. NSE lists 0.1% delivery STT on each side and 0.015% buy stamp duty; other charges and slippage motivate the allowance. '
        '[NSE statutory charges](https://www.nseindia.com/static/invest/first-time-investor-sebi-turnover-fees-stt-other-levies). Personal income tax is excluded.', '',
        '## Data audit and limits', '',
        f"All 200 current symbols were loaded, with real IPO start dates and input hashes. Stock histories were downloaded from Yahoo Finance for 2014-2026; "
        f"a session requires positive volume in at least 100 stocks. **{sum(d['invalid_rows'] for d in audit['stocks'].values())} invalid rows** were rejected and "
        f"**{sum(d['missing_sessions_after_first'] for d in audit['stocks'].values())} missing stock-session observations** were recorded. "
        f"Five Yahoo index gaps were filled from NSE official price records after checking overlapping dates for agreement; "
        f"{len(audit['benchmark_missing'])} missing benchmark sessions remain. Gaps had included special Muhurat/Budget sessions, so leaving them missing would unfairly block index-gated variants for subsequent SMA200 windows. "
        'Missing history is not filled with made-up candles.', '',
        f"Large adjusted jumps were flagged in {len(sensitivity['flagged_securities'])} securities. MOTILALOFS has an apparent inconsistent pre-2024 split-adjustment scale; "
        'TMPV/VEDL have corporate-action complications. Other large moves may be real. **No simulated trade in the full/later evidence crosses any flagged >40% jump**, '
        'but signals may still be affected by vendor quality. The source-quality sensitivity excludes all flagged securities and is reported separately. '
        'No selective manual price repair was used to improve returns.', '',
        '**Historical Nifty 200 membership is not available.** The tested group is today\'s 200 stocks, including their pre-membership histories; '
        'removed, failed or delisted past constituents are absent. NSE monthly archives checked for 2022 and 2026 did not contain full Nifty 200 constituent histories. '
        'This survivorship bias prevents a clean claim about the historical index universe. Current industry labels have the same timing limitation.', '',
        'Adjusted OHLC provides a dividend-adjusted return proxy, not a complete broker cash/dividend ledger. Whole adjusted-price research units can differ from historical legal share counts after corporate actions. '
        'Exchange price limits, locked circuits, exact auction liquidity, market impact and earnings-event calendars are not modeled. '
        'End-of-day drawdown understates possible intraday drawdown. Twenty-six mechanical regression tests and six actual-history prefix checks validate implementation behavior; '
        'they do not validate predictive profitability.', '',
        '## Evidence and reproduction', '',
        '- [All 72 variants and periods (CSV)](comparison.csv)',
        '- [Selected strategy trade ledger (CSV)](selected_trades.csv)',
        '- [Selected equity curves and full trades (JSON)](selected_evidence.json)',
        '- [All full/later trades and curves (compressed JSON)](evidence.json.gz)',
        '- [Metrics, benchmark curves and limitations](results.json)',
        '- [Account-size, timing and data-quality sensitivities](sensitivity.json)',
        '- [Per-security data hashes and defects](data_audit.json)',
        '- [Frozen plan](plan.json) and [chronological selection](selection.json)', '',
        '```text', 'python scripts/fetch_vcp_data.py', 'python scripts/fetch_vcp_benchmark.py',
        'python -m unittest discover -s tests -p test_vcp.py -v',
        'python vcp_research.py --phase all', 'python scripts/vcp_sensitivity.py',
        'python scripts/report_vcp.py', '```', '',
        'Charts additionally require matplotlib (installed locally in `.cache/vcp-plot`). Raw vendor snapshots remain in `.cache/vcp`; '
        'fresh downloads may be revised and must be compared with the recorded hashes. No production scanner, daily job, or order system was changed.', '',
        '**Decision:** retain this as an exploratory price/volume hypothesis. The weekly exit deserves more research than the tight trail or fixed target, '
        'but the present evidence is too sparse and biased to call VCP a proven profitable Nifty 200 system. A clean next test needs point-in-time constituents, '
        'corporate-action-verified data, explicit earnings filters if reproducing the image, and forward paper trades under frozen rules.', '',
    ]
    report = '\n'.join(lines)
    (OUT/'REPORT.md').write_text(report,encoding='utf-8')


def main():
    result = json.loads((OUT/'results.json').read_text())
    selected = json.loads((OUT/'selected_evidence.json').read_text())
    sensitivity = json.loads((OUT/'sensitivity.json').read_text())
    benchmark = pd.read_csv(v.CACHE/'nifty200_tri_raw.csv')
    benchmark['Date'] = pd.to_datetime(benchmark.Date,format='%d %b %Y')
    benchmark.sort_values('Date')[['Date','TotalReturnsIndex']].to_csv(OUT/'nifty200_tri.csv',index=False)
    (OUT/'benchmark_repairs.json').write_text((v.CACHE/'index_price_repairs.json').read_text(encoding='utf-8'),encoding='utf-8')
    plot_summary(result,selected)
    plot_examples(selected)
    make_report(result,selected,sensitivity)
    import re
    test_log = (v.CACHE/'regression_tests.log').read_text(encoding='utf-8')
    match = re.search(r'Ran (\d+) tests',test_log)
    if not match or not re.search(r'^OK$',test_log,re.MULTILINE):
        raise ValueError('Passing regression test evidence missing')
    v.json_write(OUT/'verification.json',{
        'research_test_count':int(match.group(1)), 'test_status':'passed',
        'real_history_prefix_checks':sensitivity['real_history_prefix_checks'],
        'configs':result['variant_count'],
        'plan_sha256':result['plan_sha256'], 'selection_sha256':result['selection_sha256'],
        'large_jump_trade_overlaps':sensitivity['trades_crossing_flagged_jumps'],
        'benchmark_repairs':json.loads((OUT/'data_audit.json').read_text())['benchmark']['official_repairs'],
        'source_hashes':{name:v.hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                          ['vcp_research.py','tests/test_vcp.py','scripts/vcp_sensitivity.py']},
    })
    print('Wrote research/vcp/REPORT.md, vcp_results.png/svg and vcp_examples.png')


if __name__ == '__main__':
    main()
