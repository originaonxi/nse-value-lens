#!/usr/bin/env python3
"""
Open Mutual Fund — Best of Both Worlds (₹10L, 2-sleeve construction)
======================================================================
Sleeve A  Momentum  ₹5L → top 5 by corrected M5 score:
           ram6=mom6%/vol%  ram12=mom12%/vol%  score=(z(ram6)+z(ram12))/2
           Source: computed inline from screen_output/quant_upgrade_master.csv
           Thesis: price is going up and keeps going up

Sleeve B  Value-Down ₹5L → top 5 by value score (PE/PB/ROE proven)
           Source: screen_output/value_dn.json
           Thesis: fundamentals are good, price is wrongly beaten down

Dedup rule: if a stock appears in BOTH sleeves, it keeps its Sleeve A spot
            and Sleeve B promotes its next-best name (and vice versa).

Deep check (yfinance balance_sheet + cashflow for all 10):
  ✓ Cash position vs debt
  ✓ Free Cash Flow (operating CF - capex)
  ✓ ROE / net margin
  ✓ Revenue  
  Red-flag warnings printed if: debt > 3x cash, FCF negative, ROE < 8%

₹1L per stock (equal within each sleeve), integer shares at last close.

Outputs: screen_output/combined_portfolio.json
         screen_output/stock_profiles.json (all 194 stocks, powers click modal)
"""
import csv, json, statistics, warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

warnings.filterwarnings('ignore')
import yfinance as yf

HERE = Path(__file__).resolve().parent
OUT  = HERE / "screen_output"
SEED = 1_000_000
ALLOC_PER = SEED // 10          # ₹1,00,000 per stock



def zscore(vals):
    """Cross-sectional z-score. None values excluded from mean/std, returned as None."""
    valid = [(i, v) for i, v in enumerate(vals) if v is not None]
    if len(valid) < 5:
        return [None] * len(vals)
    arr = [v for _, v in valid]
    mu  = statistics.mean(arr)
    sd  = statistics.stdev(arr)
    if sd == 0:
        return [0.0 if v is not None else None for v in vals]
    out = [None] * len(vals)
    for (i, _), v in zip(valid, arr):
        out[i] = (v - mu) / sd
    return out
# ── helpers ──────────────────────────────────────────────────────────────

def inr(n): return f"₹{n:,.0f}"

def fetch_deep(symbol):
    """Balance sheet + cashflow — raw numbers for cross-checking."""
    try:
        t    = yf.Ticker(symbol + '.NS')
        info = t.info
        bs   = t.balance_sheet
        cf   = t.cashflow

        def row(df, *names):
            for n in names:
                if n in df.index:
                    v = df.loc[n].iloc[0]
                    return float(v) if v is not None else None
            return None

        cash_bs  = row(bs, 'Cash And Cash Equivalents',
                           'Cash Cash Equivalents And Short Term Investments')
        total_debt = row(bs, 'Total Debt', 'Long Term Debt')
        equity     = row(bs, 'Stockholders Equity', 'Common Stock Equity')
        total_assets = row(bs, 'Total Assets')
        op_cf      = row(cf, 'Operating Cash Flow')
        capex      = row(cf, 'Capital Expenditure')
        fcf        = (op_cf - abs(capex)) if (op_cf and capex) else None

        return symbol, {
            # from .info (first-pass, known gaps)
            'pe':           info.get('trailingPE'),
            'pb':           info.get('priceToBook'),
            'roe':          info.get('returnOnEquity'),
            'net_margin':   info.get('netMargins'),
            'gross_margin': info.get('grossMargins'),
            'total_cash_info': info.get('totalCash'),
            'total_debt_info': info.get('totalDebt'),
            'market_cap':   info.get('marketCap'),
            'revenue':      info.get('totalRevenue'),
            'ebitda':       info.get('ebitda'),
            'eps':          info.get('trailingEps'),
            'div_yield':    info.get('dividendYield'),
            'beta':         info.get('beta'),
            'sector':       info.get('sector', ''),
            'industry':     info.get('industry', ''),
            # from balance_sheet (more reliable for cash/debt)
            'cash_bs':      cash_bs,
            'total_debt_bs': total_debt,
            'equity':       equity,
            'total_assets': total_assets,
            # cashflow
            'op_cf':        op_cf,
            'capex':        capex,
            'fcf':          fcf,
            # derived
            'debt_to_cash': round(total_debt/cash_bs, 2) if (total_debt and cash_bs and cash_bs > 0) else None,
            'fcf_yield':    round(fcf/info.get('marketCap',1)*100, 2) if (fcf and info.get('marketCap')) else None,
        }
    except Exception as e:
        return symbol, {'_error': str(e)}


FIN_KW = {'bank','financial','finance','nbfc','insur','housing','investment',
           'investcorp','muthoot','bajajfin','holding','finserv'}

def is_fin_sym(name_or_sym):
    return any(k in name_or_sym.lower() for k in FIN_KW)


def red_flags(sym, d, fin=False):
    """Sector-aware warnings.
    fin=True (bank/NBFC): debt/cash and FCF are structurally high — not flagged as risks.
    Only flag universal problems: loss-making, very low ROE (non-fin only).
    """
    flags = []
    nm = d.get('net_margin')
    if nm is not None and nm < 0:
        flags.append(f"LOSS-MAKING: net margin {nm*100:.1f}%")
    if not fin:
        dc = d.get('debt_to_cash')
        if dc and dc > 3:
            flags.append(f"HIGH DEBT: debt is {dc:.1f}× cash")
        fcf = d.get('fcf')
        if fcf is not None and fcf < 0:
            flags.append(f"NEGATIVE FCF: {inr(fcf)}")
    roe = d.get('roe')
    if roe is not None and roe < 0.08:
        flags.append(f"LOW ROE: {roe*100:.1f}%")
    return flags


def build():
    # ── 1. Compute corrected M5 scores for ALL 194 stocks ────────────────
    # Formula: ram6=mom6%/vol%, ram12=mom12%/vol%  → score=(z(ram6)+z(ram12))/2
    # Same as build_m5.py — cross-sectional z-score of risk-adjusted ratios
    print("Computing M5 scores for all 194 stocks…")
    mom_rows = list(csv.DictReader(open(OUT/'quant_upgrade_master.csv',
                                        newline='', encoding='utf-8-sig')))
    all_mom_raw = []
    for r in mom_rows:
        try:
            all_mom_raw.append({
                'symbol': r['symbol'].strip(),
                'mom12': float(r['mom12%']), 'mom6': float(r['mom6%']),
                'vol': max(float(r['vol%']), 1.0),
                'price': float(r['price']),
                'z_ram': float(r['z_ram']),
                'above_dma': r.get('above_dma','').lower()=='true',
                'in_fno':    r.get('in_fno','').lower()=='true',
            })
        except (ValueError, KeyError):
            continue

    # Risk-adjusted ratios first, then cross-sectional z-score
    ram6_list  = [s['mom6']  / s['vol'] for s in all_mom_raw]
    ram12_list = [s['mom12'] / s['vol'] for s in all_mom_raw]
    zr6  = zscore(ram6_list)
    zr12 = zscore(ram12_list)
    for i, s in enumerate(all_mom_raw):
        s['m5_score'] = (zr6[i] + zr12[i]) / 2

    # Sort all 194 by M5 score → this is the full momentum ranking
    all_mom_ranked = sorted(all_mom_raw, key=lambda s: s['m5_score'], reverse=True)
    all_mom = [(s['symbol'], s) for s in all_mom_ranked]
    print(f"  M5 top-5: {[s for s,_ in all_mom[:5]]}")

    # ── 2. Load Sleeve B (value top by score) ────────────────────────────
    try:
        val_data  = json.load(open(OUT/'value_dn.json'))
        val_picks = [(h['symbol'], h) for h in val_data['holdings']]
    except FileNotFoundError:
        print("ERROR: value_dn.json missing — run build_value_dn.py first")
        raise SystemExit(1)

    # ── 2b. Load price-damage data for ALL stocks (for modal drawdown fields) ──
    try:
        price_dd = json.load(open(OUT/'price_dd.json', encoding='utf-8'))
    except FileNotFoundError:
        print("WARNING: price_dd.json missing — run fetch_dd.py; drawdown fields will be null")
        price_dd = {}

    # ── 3. Sector-aware gate ─────────────────────────────────────────────
    # FIN stocks (banks/NBFCs): FCF and debt/cash are structurally misleading
    #   → only gate on net_margin < 0
    # NON-FIN stocks:
    #   HARD FAIL = (debt/cash > 20 AND fcf < 0) OR net_margin < 0
    #   These are replaced by the next-best in the same sleeve
    # is_fin_sym and FIN_KW are at module level — use name lookup via val_picks for accuracy
    def is_fin_sym_named(sym):
        name = next((dat.get('name','') for s,dat in val_picks if s==sym), sym)
        return is_fin_sym(name)

    def hard_fail(sym, d):
        """True = stock must be replaced."""
        nm = d.get('net_margin')
        if nm is not None and nm < 0:
            return True, "LOSS-MAKING"
        if not is_fin_sym(sym):          # skip debt/FCF gate for financials
            dc  = d.get('debt_to_cash')
            fcf = d.get('fcf')
            if dc and fcf is not None and dc > 20 and fcf < 0:
                return True, f"debt {dc:.0f}× cash AND FCF negative — too risky"
        return False, ""

    # ── 4. Dedup then deep-check with replacement ─────────────────────────
    def pick_sleeve(ranked, exclude, n=5):
        out = []
        for sym, data in ranked:
            if sym not in exclude and len(out) < n:
                out.append((sym, data))
        return out

    val_syms = {s for s, _ in val_picks}
    sleeve_a  = pick_sleeve(all_mom, exclude=set(), n=5)
    a_syms    = {s for s, _ in sleeve_a}
    sleeve_b  = []
    for sym, h in val_picks:
        if sym not in a_syms and len(sleeve_b) < 5:
            sleeve_b.append((sym, h))
        elif sym in a_syms:
            print(f"  DEDUP: {sym} in both → keeping in A, promoting next in B")
    if not (a_syms & val_syms):
        print("  No overlap — good diversification")

    # First pass: deep-check initial candidates
    all_picks_init = [s for s,_ in sleeve_a] + [s for s,_ in sleeve_b]
    print(f"\nDeep-checking {len(all_picks_init)} initial candidates…")
    deep = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(fetch_deep, s): s for s in all_picks_init}
        for f in as_completed(futs):
            sym, data = f.result()
            deep[sym] = data

    # Apply gate to Sleeve A — replace failures with next M5 rank
    print("\n── Gate check Sleeve A (Momentum) ─────────────────────────────")
    final_a = []
    used = {s for s,_ in sleeve_b}
    for sym, mdat in sleeve_a:
        d = deep.get(sym, {})
        fail, reason = hard_fail(sym, d)
        roe_s = f"{d['roe']*100:.1f}%" if d.get('roe') else 'N/A'
        dc_s  = f"{d.get('debt_to_cash','N/A')}"
        dc_s  = f"{d['debt_to_cash']:.1f}×" if d.get('debt_to_cash') else 'N/A'
        fcf_s = inr(d['fcf']) if d.get('fcf') else 'N/A'
        if fail:
            # Find replacement: next in M5 ranking not already used
            rep = None
            for rs, rd in all_mom:
                if rs not in {s for s,_ in final_a} and rs not in used and rs != sym:
                    # fetch deep for replacement
                    _, rd2 = fetch_deep(rs)
                    deep[rs] = rd2
                    rf, rr = hard_fail(rs, rd2)
                    if not rf:
                        rep = (rs, rd)
                        break
            if rep:
                print(f"  ✗ {sym:<12} REPLACED ({reason})")
                print(f"  → {rep[0]:<12} substituted (M5 score {rep[1].get('m5_score',0):.3f})")
                final_a.append(rep)
                used.add(rep[0])
            else:
                print(f"  ⚠ {sym:<12} FLAGGED ({reason}) — no clean replacement, keeping with warning")
                final_a.append((sym, mdat))
                used.add(sym)
        else:
            soft = red_flags(sym, d, fin=is_fin_sym_named(sym))
            tag  = ' ⚠ '+', '.join(soft) if soft else ' ✓'
            print(f"  ✓ {sym:<12} ROE={roe_s}  debt/cash={dc_s}  FCF={fcf_s}{tag}")
            final_a.append((sym, mdat))
            used.add(sym)
    sleeve_a = final_a

    # Apply gate to Sleeve B — value screen already enforces PE/PB/ROE
    print("\n── Gate check Sleeve B (Value-Down) ────────────────────────────")
    final_b = []
    used_b  = {s for s,_ in sleeve_a}
    b_iter  = iter(val_picks)
    b_queue = list(val_picks)  # full ranked list for replacements
    b_idx   = 0
    for sym, vdat in sleeve_b:
        d = deep.get(sym, {})
        fail, reason = hard_fail(sym, d)
        roe_s = f"{vdat.get('roe_pct','?')}%"
        dd_s  = f"{vdat.get('dd_52wh_pct','?')}%"
        if fail and not is_fin_sym(sym):
            # find next value pick not already used
            rep = None
            for rs, rh in b_queue:
                if rs not in used_b and rs not in {s for s,_ in final_b}:
                    _, rd2 = fetch_deep(rs) if rs not in deep else (rs, deep[rs])
                    if rs not in deep:
                        _, rd2 = fetch_deep(rs)
                        deep[rs] = rd2
                    rf, rr = hard_fail(rs, deep.get(rs,{}))
                    if not rf:
                        rep = (rs, rh)
                        break
            if rep:
                print(f"  ✗ {sym:<12} REPLACED ({reason})")
                print(f"  → {rep[0]:<12} substituted")
                final_b.append(rep); used_b.add(rep[0])
            else:
                print(f"  ⚠ {sym:<12} FLAGGED — keeping with warning")
                final_b.append((sym, vdat)); used_b.add(sym)
        else:
            soft = red_flags(sym, d, fin=is_fin_sym_named(sym))
            tag  = ' ⚠ '+', '.join(soft) if soft else ' ✓'
            print(f"  ✓ {sym:<12} ROE={roe_s}  52wDD={dd_s}{tag}")
            final_b.append((sym, vdat)); used_b.add(sym)
    sleeve_b = final_b

    # ── 5. Build holdings ─────────────────────────────────────────────────
    def make_holding(sym, sleeve, label, rank_in_sleeve):
        d     = deep.get(sym, {})
        flags = red_flags(sym, d, fin=is_fin_sym_named(sym))
        # Price from momentum data if available, else yfinance
        price = dict(all_mom).get(sym, {}).get('price') or d.get('pe') and None
        # Robust price lookup
        for src_list in [all_mom]:
            for s2, dat in src_list:
                if s2 == sym: price = dat['price']; break
        if not price:
            price = next((h['price'] for s2, h in val_picks if s2 == sym), None)
        if not price: return None
        shares = int(ALLOC_PER // price)
        value  = shares * price
        return {
            'symbol':       sym,
            'name':         next((dat.get('name', sym) for s2, dat in val_picks if s2 == sym), sym),
            'sleeve':       sleeve,
            'label':        label,
            'rank':         rank_in_sleeve,
            'price':        round(price, 2),
            'shares':       shares,
            'value_rs':     round(value, 2),
            # momentum
            'z_ram':        dict(all_mom).get(sym, {}).get('z_ram'),
            'mom12_pct':    dict(all_mom).get(sym, {}).get('mom12'),
            'mom6_pct':     dict(all_mom).get(sym, {}).get('mom6'),
            'vol_pct':      dict(all_mom).get(sym, {}).get('vol'),
            'above_dma':    dict(all_mom).get(sym, {}).get('above_dma'),
            'in_fno':       dict(all_mom).get(sym, {}).get('in_fno'),
            # fundamentals (from deep)
            'pe':           d.get('pe'), 'pb': d.get('pb'),
            'roe_pct':      round(d['roe']*100,1) if d.get('roe') else None,
            'net_margin_pct': round(d['net_margin']*100,1) if d.get('net_margin') else None,
            'gross_margin_pct': round(d['gross_margin']*100,1) if d.get('gross_margin') else None,
            'total_cash':   d.get('cash_bs') or d.get('total_cash_info'),
            'total_debt':   d.get('total_debt_bs') or d.get('total_debt_info'),
            'debt_to_cash': d.get('debt_to_cash'),
            'fcf':          d.get('fcf'),
            'fcf_yield_pct': d.get('fcf_yield'),
            'market_cap':   d.get('market_cap'),
            'revenue':      d.get('revenue'),
            'ebitda':       d.get('ebitda'),
            'eps':          d.get('eps'),
            'div_yield_pct': round(d['div_yield']*100,2) if d.get('div_yield') else None,
            'beta':         d.get('beta'),
            'sector':       d.get('sector'),
            'industry':     d.get('industry'),
            # price damage
            'dd_52wh_pct':  next((h.get('dd_52wh_pct') for s2,h in val_picks if s2==sym), None),
            # red flags
            'red_flags':    flags,
        }

    # Build name map from value sleeve
    val_name = {s: h.get('name', s) for s, h in val_picks}

    holdings = []
    deployed = 0.0
    print("\n── Sleeve A: Momentum ──────────────────────────────────────────")
    for i, (sym, mdat) in enumerate(sleeve_a, 1):
        d      = deep.get(sym, {})
        price  = mdat['price']
        shares = int(ALLOC_PER // price)
        value  = shares * price
        deployed += value
        flags  = red_flags(sym, d, fin=is_fin_sym_named(sym))
        roe_s  = f"{d['roe']*100:.1f}%" if d.get('roe') else 'N/A'
        flag_s = ' ⚠ '+', '.join(flags) if flags else ' ✓'
        print(f"  A{i} {sym:<12} m5={mdat['m5_score']:.3f}  12m={mdat['mom12']:.1f}%"
              f"  ROE={roe_s}  {shares}sh×{inr(price)}={inr(value)}{flag_s}")
        name = val_name.get(sym, sym)
        holdings.append({
            'symbol': sym, 'name': name, 'sleeve': 'A', 'label': 'Momentum',
            'rank': i, 'price': round(price,2), 'shares': shares, 'value_rs': round(value,2),
            'm5_score': mdat['m5_score'], 'z_ram': mdat['z_ram'],
            'mom12_pct': mdat['mom12'], 'mom6_pct': mdat['mom6'],
            'vol_pct': mdat['vol'], 'above_dma': mdat['above_dma'], 'in_fno': mdat['in_fno'],
            'pe': d.get('pe'), 'pb': d.get('pb'),
            'roe_pct': round(d['roe']*100,1) if d.get('roe') else None,
            'net_margin_pct': round(d['net_margin']*100,1) if d.get('net_margin') else None,
            'gross_margin_pct': round(d['gross_margin']*100,1) if d.get('gross_margin') else None,
            'total_cash': d.get('cash_bs') or d.get('total_cash_info'),
            'total_debt': d.get('total_debt_bs') or d.get('total_debt_info'),
            'debt_to_cash': d.get('debt_to_cash'), 'fcf': d.get('fcf'),
            'fcf_yield_pct': d.get('fcf_yield'), 'market_cap': d.get('market_cap'),
            'revenue': d.get('revenue'), 'ebitda': d.get('ebitda'),
            'eps': d.get('eps'),
            'div_yield_pct': round(d['div_yield']*100,2) if d.get('div_yield') else None,
            'beta': d.get('beta'), 'sector': d.get('sector',''), 'industry': d.get('industry',''),
            'dd_52wh_pct': price_dd.get(sym, {}).get('dd_52wh_pct'),
            'drop_1m_pct': price_dd.get(sym, {}).get('drop_1m_pct'),
            'drop_5d_pct': price_dd.get(sym, {}).get('drop_5d_pct'),
            'red_flags': red_flags(sym, d, fin=is_fin_sym_named(sym)),
        })

    print("\n── Sleeve B: Value-Down ─────────────────────────────────────────")
    for i, (sym, vdat) in enumerate(sleeve_b, 1):
        d      = deep.get(sym, {})
        price  = vdat.get('price') or 0
        if not price:
            price = d.get('pe') and None  # no price fallback
        shares = int(ALLOC_PER // price) if price else 0
        value  = shares * price if price else 0
        deployed += value
        flags  = red_flags(sym, d, fin=is_fin_sym_named(sym))
        mom_s  = f"z_ram={dict(all_mom).get(sym,{}).get('z_ram','N/A')}"
        flag_s = ' ⚠ '+', '.join(flags) if flags else ' ✓'
        roe_s  = f"{vdat.get('roe_pct','?')}%"
        print(f"  B{i} {sym:<12} val={vdat.get('_score',0):.3f}  PE={vdat.get('pe','?')}"
              f"  ROE={roe_s}  dd52={vdat.get('dd_52wh_pct','?')}%"
              f"  {mom_s}  {shares}sh×{inr(price)}={inr(value)}{flag_s}")
        holdings.append({
            'symbol': sym, 'name': vdat.get('name', sym), 'sleeve': 'B', 'label': 'Value-Down',
            'rank': i, 'price': round(price,2) if price else None,
            'shares': shares, 'value_rs': round(value,2),
            'z_ram': dict(all_mom).get(sym, {}).get('z_ram'),
            'mom12_pct': dict(all_mom).get(sym, {}).get('mom12'),
            'mom6_pct': dict(all_mom).get(sym, {}).get('mom6'),
            'vol_pct': dict(all_mom).get(sym, {}).get('vol'),
            'above_dma': dict(all_mom).get(sym, {}).get('above_dma'),
            'in_fno': dict(all_mom).get(sym, {}).get('in_fno'),
            'pe': vdat.get('pe'), 'pb': vdat.get('pb'),
            'roe_pct': round(vdat['roe']*100,1) if vdat.get('roe') else None,
            'net_margin_pct': round(d['net_margin']*100,1) if d.get('net_margin') else None,
            'gross_margin_pct': round(d['gross_margin']*100,1) if d.get('gross_margin') else None,
            'total_cash': d.get('cash_bs') or d.get('total_cash_info'),
            'total_debt': d.get('total_debt_bs') or d.get('total_debt_info'),
            'debt_to_cash': d.get('debt_to_cash'), 'fcf': d.get('fcf'),
            'fcf_yield_pct': d.get('fcf_yield'), 'market_cap': d.get('market_cap'),
            'revenue': d.get('revenue'), 'ebitda': d.get('ebitda'),
            'eps': d.get('eps'),
            'div_yield_pct': round(d['div_yield']*100,2) if d.get('div_yield') else None,
            'beta': d.get('beta'), 'sector': d.get('sector',''), 'industry': d.get('industry',''),
            'dd_52wh_pct': vdat.get('dd_52wh_pct'),
            'drop_1m_pct': vdat.get('drop_1m_pct'), 'drop_5d_pct': vdat.get('drop_5d_pct'),
            'val_score': vdat.get('_score'),
            'red_flags': red_flags(sym, d, fin=is_fin_sym_named(sym)),
        })

    cash_left = round(SEED - deployed, 2)

    # ── 6. Save portfolio + stock profiles ───────────────────────────────
    portfolio = {
        'fund': 'Open Mutual Fund — Best of Both Worlds',
        'as_of': date.today().isoformat(),
        'seed_rs': SEED, 'deployed_rs': round(deployed,2),
        'cash_rs': cash_left, 'cash_pct': round(cash_left/SEED*100,2),
        'sleeve_a_rs': 500_000, 'sleeve_b_rs': 500_000,
        'holdings_count': len(holdings),
        'method': (
            'Sleeve A (₹5L): top-5 by M5 score = (z(mom6/vol) + z(mom12/vol)) / 2 '
            '— same corrected formula as build_m5.py, applied to all 194 | '
            'Sleeve B (₹5L): top-5 by sector-aware fundamental score '
            '(PE/PB/ROE required, price-damage = 0.5×dd52wh + 0.3×drop1m + 0.2×drop5d) | '
            'Gate: non-fin replaced if debt/cash>20 AND FCF<0, or net_margin<0 | '
            'Dedup: overlap kept in A, B promotes next-best | ₹1L equal weight per stock'
        ),
        'data_caveat': (
            'Fundamentals from yfinance .info + balance_sheet — first-pass only. '
            'Known gaps: cash/debt fields may not match annual-report totals. '
            'Validate against NSE exchange filings before real capital deployment.'
        ),
        'rebalance': 'monthly (re-run all build scripts)',
        'holdings': holdings,
    }
    (OUT/'combined_portfolio.json').write_text(json.dumps(portfolio, indent=2), encoding='utf-8')

    # Stock profiles for all 194 (modal data source)
    profiles = {}
    for sym, mdat in all_mom:
        d = deep.get(sym, {})
        # find in value sleeve
        vh = next((h for s2,h in val_picks if s2==sym), {})
        profiles[sym] = {
            **mdat,
            'pe': d.get('pe'), 'pb': d.get('pb'),
            'roe_pct': round(d['roe']*100,1) if d.get('roe') else None,
            'net_margin_pct': round(d['net_margin']*100,1) if d.get('net_margin') else None,
            'gross_margin_pct': round(d['gross_margin']*100,1) if d.get('gross_margin') else None,
            'total_cash': d.get('cash_bs') or d.get('total_cash_info'),
            'total_debt': d.get('total_debt_bs') or d.get('total_debt_info'),
            'debt_to_cash': d.get('debt_to_cash'), 'fcf': d.get('fcf'),
            'fcf_yield_pct': d.get('fcf_yield'), 'market_cap': d.get('market_cap'),
            'revenue': d.get('revenue'), 'ebitda': d.get('ebitda'),
            'eps': d.get('eps'), 'beta': d.get('beta'),
            'sector': d.get('sector',''), 'industry': d.get('industry',''),
            'div_yield_pct': round(d['div_yield']*100,2) if d.get('div_yield') else None,
            'val_score': vh.get('_score'),
            # sleeve assigned after holdings are built — patched below
            'dd_52wh_pct': price_dd.get(sym, {}).get('dd_52wh_pct') or vh.get('dd_52wh_pct'),
            'drop_1m_pct': price_dd.get(sym, {}).get('drop_1m_pct') or vh.get('drop_1m_pct'),
            'drop_5d_pct': price_dd.get(sym, {}).get('drop_5d_pct') or vh.get('drop_5d_pct'),
            'red_flags': red_flags(sym, d, fin=is_fin_sym_named(sym)),
        }
    # Patch sleeve/label/scores into profiles from final holdings so modal has complete data
    for h in holdings:
        sym = h['symbol']
        if sym in profiles:
            profiles[sym]['sleeve']    = h['sleeve']
            profiles[sym]['label']     = h['label']
            profiles[sym]['m5_score']  = h.get('m5_score')
            profiles[sym]['val_score'] = h.get('val_score')
            profiles[sym]['roe_pct']   = profiles[sym].get('roe_pct') or h.get('roe_pct')

    (OUT/'stock_profiles.json').write_text(json.dumps(profiles, indent=2), encoding='utf-8')

    print(f"\n{'='*60}")
    print(f"Deployed {inr(deployed)} / {inr(SEED)}  |  Cash {inr(cash_left)} ({cash_left/SEED*100:.2f}%)")
    total_flags = sum(len(h['red_flags']) for h in holdings)
    print(f"Red flags across 10 picks: {total_flags} (see above)")
    print(f"Saved: combined_portfolio.json + stock_profiles.json ({len(profiles)} stocks)")


if __name__ == '__main__':
    build()
