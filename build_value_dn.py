#!/usr/bin/env python3
"""
Value-Down — Sector-aware fundamental mispricing screener
Nifty 200 universe | 48 financials / 152 non-financials

NON-FINANCIAL score (152 stocks):
  value  = PE_z(inverted)*0.3 + PB_z(inverted)*0.3 + cashYield_z*0.4 (cash/mktcap)
  quality= ROE_z*0.5 + margin_z(gross)*0.3 + lowDebt_z(inverted debt/cash)*0.2
  price  = drawdown_z (price vs 52w high, more negative = more beaten down = higher score)
  total  = 0.40*value + 0.35*quality + 0.25*price

FINANCIAL score (48 banks/NBFCs):
  value  = PE_z(inverted)*0.4 + PB_z(inverted)*0.6
  quality= ROE_z*1.0  (only field available that's meaningful for banks)
  price  = drawdown_z (same as non-financial)
  total  = 0.50*value + 0.30*quality + 0.20*price
  NOTE: cash/debt excluded for banks — they look "debt heavy" by structure

Cross-sector: z-scores computed SEPARATELY per group so banks
and industrials aren't compared directly on the same scale.

For each stock report: which fields are MISSING so we never
pretend we have data we don't have.
"""
import argparse
import csv
import json
import statistics
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

warnings.filterwarnings('ignore')
import yfinance as yf

HERE = Path(__file__).resolve().parent
OUT  = HERE / "screen_output"
UNIVERSE = HERE / "nifty200.csv"
SEED = 1_000_000

BANK_KEYWORDS = {'bank','financial','finance','nbfc','insur','hfcl','housing','finserv','bajajfin','investment','investcorp','holdings','holding'}


def is_financial(name):
    n = name.lower()
    return any(k in n for k in BANK_KEYWORDS)


def fetch_fundamentals(symbol, name):
    """Fetch yfinance .info. Return dict with all needed fields (None = MISSING)."""
    try:
        t = symbol + '.NS'
        info = yf.Ticker(t).info
        pe       = info.get('trailingPE')
        pb       = info.get('priceToBook')
        roe      = info.get('returnOnEquity')
        cash     = info.get('totalCash')
        debt     = info.get('totalDebt')
        cash_op  = info.get('operatingCashflow')
        fcf      = info.get('freeCashflow')
        mc       = info.get('marketCap')
        nm       = info.get('netMargins')
        gm       = info.get('grossMargins')
        price    = info.get('currentPrice')
        return {
            'symbol': symbol, 'name': name, 'fin': is_financial(name),
            'pe': pe, 'pb': pb, 'roe': roe, 'cash': cash, 'debt': debt,
            'cash_op': cash_op, 'fcf': fcf, 'mc': mc, 'nm': nm, 'gm': gm,
            'price': price,
        }
    except Exception:
        return {'symbol': symbol, 'name': name, 'fin': is_financial(name),
                'pe': None, 'pb': None, 'roe': None, 'cash': None, 'debt': None,
                'cash_op': None, 'fcf': None, 'mc': None, 'nm': None, 'gm': None,
                'price': None}


def safe_z(vals, invert_high_is_better=False):
    """Cross-sectional z-score. Missing = excluded from stats. invert=True means lower raw value = higher score."""
    valid = [(i,v) for i,v in enumerate(vals) if v is not None]
    if len(valid) < 5:
        return [None]*len(vals)
    arr = [v for _,v in valid]
    mu  = statistics.mean(arr)
    sd  = statistics.stdev(arr)
    if sd == 0:
        return [0.0 if i is not None else None for i,_ in enumerate(vals)]
    z = [(v-mu)/sd if not invert_high_is_better else (mu-v)/sd for _,v in valid]
    out = [None]*len(vals)
    for (i,_), zi in zip(valid, z):
        out[i] = zi
    return out


def drawdown_z(stocks):
    """Price-damage z-score from price_dd.json fields (fetched via fetch_dd.py).
    Composite per stock: 50% dd_52wh + 30% drop_1m + 20% drop_5d
    Sign: negate so more-beaten-down = higher score."""
    def dmg(s):
        dd52 = s.get('dd_52wh_pct')
        d1m  = s.get('drop_1m_pct')
        d5d  = s.get('drop_5d_pct')
        if dd52 is None:
            return None
        return 0.5 * dd52 + 0.3 * (d1m or 0) + 0.2 * (d5d or 0)
    raw = [-dmg(s) if dmg(s) is not None else None for s in stocks]
    return safe_z(raw)


def build():
    print("Fetching fundamentals for 194 stocks (parallel, ~60s)...", flush=True)
    rows = list(csv.DictReader(open(UNIVERSE, newline='', encoding='utf-8-sig')))
    syms = [(r['Symbol'].strip(), r.get('Company Name','').strip()) for r in rows
            if r.get('Series','EQ').strip()=='EQ']

    # Load real price-damage data from fetch_dd.py output
    _price_dd = {}
    try:
        _price_dd = json.load(open(OUT/'price_dd.json', encoding='utf-8'))
    except FileNotFoundError:
        print('ERROR: screen_output/price_dd.json not found. Run: python fetch_dd.py first')
        raise SystemExit(1)
    print(f'  Loaded {len(_price_dd)} price-damage records (52w/1m/5d)')

    stocks = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(fetch_fundamentals, s, n): s for s,n in syms}
        done = 0
        for f in as_completed(futures):
            r = f.result()
            sym = futures[f]
            dd = _price_dd.get(sym, {})
            r['dd_52wh_pct'] = dd.get('dd_52wh_pct')
            r['drop_1m_pct'] = dd.get('drop_1m_pct')
            r['drop_5d_pct'] = dd.get('drop_5d_pct')
            stocks.append(r)
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(syms)} fetched...", flush=True)

    fins  = [s for s in stocks if s['fin']]
    nfins = [s for s in stocks if not s['fin']]
    print(f"\nFetched {len(stocks)} total  |  {len(nfins)} non-financial  {len(fins)} financial")

    # ── NON-FINANCIAL z-scores ───────────────────────────────────────────
    def g(key):
        return [s[key] for s in nfins]

    # Value: lower PE/PB better, higher cash-yield better
    z_pe    = safe_z(g('pe'),    invert_high_is_better=True)   # PE low = good
    z_pb    = safe_z(g('pb'),    invert_high_is_better=True)   # PB low = good
    cash_y  = [s['cash']/s['mc'] if s['cash'] and s['mc'] else None for s in nfins]
    z_cy    = safe_z(cash_y)                                     # cash high = good

    # Quality
    z_roe   = safe_z(g('roe'))
    z_gm    = safe_z(g('gm'))
    debt_cf = [s['debt']/max(s['cash'],1) if s['debt'] and s['cash'] else None for s in nfins]
    z_debt  = safe_z(debt_cf, invert_high_is_better=True)       # low debt/cash = good

    # Price: drawdown
    z_dd    = drawdown_z(nfins)

    NF_CORE = ['pe','pb','roe','cash','debt','gm']
    NF_REQUIRED = ['pe','pb','roe']   # hard requirement: no PE/PB/ROE -> cannot call it 'fundamentally good'
    n_filtered = 0
    for i, s in enumerate(nfins):
        s['_missing'] = sum(1 for k in NF_CORE if s[k] is None)
        req_missing = sum(1 for k in NF_REQUIRED if s[k] is None)
        if req_missing > 0 or s['_missing'] >= 3:
            s['_score'] = None   # missing PE/PB/ROE = unverifiable fundamentals — exclude
            n_filtered += 1
            continue
        val_z   = 0.3*(z_pe[i] or 0) + 0.3*(z_pb[i] or 0) + 0.4*(z_cy[i] or 0)
        qual_z  = 0.5*(z_roe[i] or 0) + 0.3*(z_gm[i] or 0) + 0.2*(z_debt[i] or 0)
        prc_z   = z_dd[i] or 0
        s['_score']    = 0.40*val_z + 0.35*qual_z + 0.25*prc_z - 0.15*s['_missing']  # penalize each missing field
        s['_val_z']    = val_z
        s['_qual_z']   = qual_z
        s['_prc_z']    = prc_z
    print(f'  Non-financial: {n_filtered}/{len(nfins)} excluded for too many missing fields (>=3/6)')

    # ── FINANCIAL z-scores ───────────────────────────────────────────────
    def gf(key):
        return [s[key] for s in fins]

    fz_pe   = safe_z(gf('pe'), invert_high_is_better=True)
    fz_pb   = safe_z(gf('pb'), invert_high_is_better=True)
    fz_roe  = safe_z(gf('roe'))
    fz_dd   = drawdown_z(fins)

    f_filtered = 0
    for i, s in enumerate(fins):
        s['_missing'] = sum(1 for k in ['pe','pb','roe'] if s[k] is None)
        if s['_missing'] >= 1:   # banks: require ALL of PE/PB/ROE present
            s['_score'] = None
            f_filtered += 1
            continue
        val_z  = 0.4*(fz_pe[i] or 0) + 0.6*(fz_pb[i] or 0)
        qual_z = 1.0*(fz_roe[i] or 0)
        prc_z  = fz_dd[i] or 0
        s['_score']  = 0.50*val_z + 0.30*qual_z + 0.20*prc_z - 0.15*s['_missing']
        s['_val_z']  = val_z
        s['_qual_z'] = qual_z
        s['_prc_z']  = prc_z
    print(f'  Financial:     {f_filtered}/{len(fins)} excluded for too many missing fields (>=2/3)')

    # Combine + rank
    all_scored = [s for s in stocks if s['_score'] is not None]
    all_scored.sort(key=lambda s: s['_score'], reverse=True)

    # Stats
    nf_missing = statistics.mean(s['_missing'] for s in nfins)
    f_missing  = statistics.mean(s['_missing'] for s in fins)
    print(f"Avg missing fields:  non-fin={nf_missing:.1f}/6  fin={f_missing:.1f}/3")

    top = all_scored[:30]
    N = 10
    picks = top[:N]
    alloc = SEED / N

    holdings = []
    deployed = 0
    for i, s in enumerate(picks, 1):
        # Build readable row
        typ = 'FIN' if s['fin'] else 'NON'
        pe_s  = f"{s['pe']:.1f}"   if s['pe'] else 'N/A'
        pb_s  = f"{s['pb']:.2f}"   if s['pb'] else 'N/A'
        roe_s = f"{s['roe']*100:.1f}%" if s['roe'] else 'N/A'
        cy_s  = f"{s['cash']/s['mc']*100:.1f}%" if s['cash'] and s['mc'] else 'N/A'
        dd_s  = f"{s['_prc_z']:.2f}" if s['_prc_z'] is not None else 'N/A'
        price_s = f"{s['price']:.2f}" if s['price'] else 'N/A'
        shares = int(alloc // s['price']) if s['price'] else 0
        value  = shares * s['price'] if s['price'] else 0
        deployed += value
        print(f"{i:2d} [{typ}] {s['symbol']:<14} score={s['_score']:+.3f}  PE={pe_s} PB={pb_s} ROE={roe_s} CashYield={cy_s}  price={price_s}  shares={shares}")
        holdings.append({**{k: s[k] for k in ['symbol','name','fin','pe','pb','roe','cash','debt','mc','gm','nm','price','dd_52wh_pct','drop_1m_pct','drop_5d_pct','_score','_val_z','_qual_z','_prc_z','_missing']},
                         'shares': shares, 'value_rs': round(value,2), 'type': typ,
                         'deployed': round(deployed,0)})

    cash_left = SEED - deployed
    # Print comparison note
    print(f"\nDeployed Rs {deployed:,.0f} / Rs {SEED:,}  |  Cash Rs {cash_left:,.0f}  ({cash_left/SEED*100:.2f}%)")
    print(f"Financial picks: {sum(1 for h in holdings if h['fin'])} / {len(holdings)}")
    print(f"Avg missing fields: {sum(h['_missing'] for h in holdings)/len(holdings):.1f}")

    result = {
        'fund': f'Value-Down (Sector-Aware ₹10L)',
        'as_of': date.today().isoformat(),
        'seed_rs': SEED,
        'deployed_rs': round(deployed,0),
        'cash_rs': round(cash_left,2),
        'cash_pct': round(cash_left/SEED*100,2),
        'universe_size': len(stocks),
        'fin_count': len(fins),
        'nonfin_count': len(nfins),
        'holdings_count': len(holdings),
        'score_note': "Non-fin: 0.4*(PE+PB+cash_yield z) + 0.35*(ROE+margin+lowDebt z) + 0.25*dmg_z  |  Fin: 0.5*(PE+PB z) + 0.3*ROE_z + 0.2*dmg_z  |  dmg = 0.5*dd52wh + 0.3*drop1m + 0.2*drop5d (real yfinance history)  |  z-scored per sector  |  PE+PB+ROE required",
        'rebalance': 'monthly (re-run script)',
        'holdings': holdings,
    }

    (OUT/'value_dn.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    with open(OUT/'value_dn.csv','w',newline='',encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['rank','symbol','name','type','score','PE','PB','ROE%','cash_yield%','dd_52wh%','drop_1m%','drop_5d%','price','shares','value_rs','missing_fields'])
        for i,h in enumerate(holdings,1):
            w.writerow([i,h['symbol'],h['name'],h['type'],h['_score'],
                        h['pe'] or '',h['pb'] or '',(h['roe']*100) if h['roe'] else '',
                        h['cash']/h['mc']*100 if h['cash'] and h['mc'] else '',
                        h['dd_52wh_pct'] if h['dd_52wh_pct'] is not None else '',
                        h['drop_1m_pct'] if h['drop_1m_pct'] is not None else '',
                        h['drop_5d_pct'] if h['drop_5d_pct'] is not None else '',
                        h['price'] or '', h['shares'],h['value_rs'],h['_missing']])
    print(f"\nSaved: screen_output/value_dn.json + .csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.parse_args()
    build()
