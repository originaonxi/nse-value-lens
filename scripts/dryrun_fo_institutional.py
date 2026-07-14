#!/usr/bin/env python3
import os, sys, json, re, time
from datetime import datetime
from urllib.request import Request, urlopen

AKEY = os.environ.get('AIRTABLE_API_KEY')
BASE_ID = os.environ.get('AIRTABLE_BASE_ID', 'appQsIke1wuAVOkpF')
TABLE = 'fo_tracker'
DRY = ['IRFC','COCHINSHIP','RBLBANK']
if not AKEY:
    print('❌ AIRTABLE_API_KEY not set')
    sys.exit(1)

TABLE_URL = f'https://api.airtable.com/v0/{BASE_ID}/{TABLE}'


def at_get_all():
    recs, offset = [], ''
    while True:
        url = TABLE_URL + '?fields[]=Symbol' + (f'&offset={offset}' if offset else '')
        req = Request(url, headers={'Authorization': f'Bearer {AKEY}'})
        with urlopen(req) as r:
            d = json.loads(r.read())
        recs += d.get('records', [])
        offset = d.get('offset', '')
        if not offset: break
    return recs


def at_patch(rec_id, fields):
    body = json.dumps({'fields': fields}).encode()
    req = Request(f'{TABLE_URL}/{rec_id}', data=body,
                  headers={'Authorization': f'Bearer {AKEY}', 'Content-Type': 'application/json'},
                  method='PATCH')
    with urlopen(req) as r:
        return json.loads(r.read())


def extract_row_values(html, label):
    idx = html.find(label)
    if idx == -1:
        return []
    snip = html[idx: idx + 2200]
    vals = re.findall(r'<td>\s*([0-9]+\.[0-9]+)%\s*</td>', snip)
    return [float(v) for v in vals[:8]]


def parse_screener(symbol):
    req = Request(
        f'https://www.screener.in/company/{symbol}/consolidated/',
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    )
    html = urlopen(req, timeout=12).read().decode('utf-8', 'ignore')
    # quarterly values appear latest → oldest in the row as rendered
    promoters = extract_row_values(html, "Company.showShareholders('promoters', 'quarterly'")
    fiis      = extract_row_values(html, "Company.showShareholders('foreign_institutions', 'quarterly'")
    diis      = extract_row_values(html, "Company.showShareholders('domestic_institutions', 'quarterly'")
    publics   = extract_row_values(html, "Company.showShareholders('public', 'quarterly'")
    # rough price from page text
    pm = re.search(r'₹\s*([0-9,]+\.?[0-9]*)', html) or re.search(r'"price"\s*:\s*"?([0-9,]+\.?[0-9]*)', html)
    price = float(pm.group(1).replace(',', '')) if pm else None

    out = {
        'promoter_vals': promoters,
        'fii_vals': fiis,
        'dii_vals': diis,
        'public_vals': publics,
    }
    if fiis: out['FII_Pct'] = fiis[0]
    if len(fiis) >= 2: out['FII_Change_Q'] = round(fiis[0] - fiis[1], 2)
    if diis: out['DII_Pct'] = diis[0]
    if len(diis) >= 2: out['DII_Change_Q'] = round(diis[0] - diis[1], 2)
    if promoters: out['Promoter_Pct'] = promoters[0]
    if len(promoters) >= 2: out['Promoter_Change_Q'] = round(promoters[0] - promoters[1], 2)
    if price is not None: out['Price'] = price

    if out.get('FII_Change_Q', 0) <= -1 or out.get('DII_Change_Q', 0) <= -1:
        out['Signal'] = 'SELLING'
    elif out.get('FII_Change_Q', 0) >= 1 or out.get('DII_Change_Q', 0) >= 1:
        out['Signal'] = 'BUYING'
    else:
        out['Signal'] = 'WATCH'
    out['Last_Updated'] = datetime.now().isoformat()
    return out


records = at_get_all()
by_sym = {r['fields'].get('Symbol'): r['id'] for r in records}
print(f'📋 Loaded {len(records)} Airtable rows')

for sym in DRY:
    rec_id = by_sym.get(sym)
    if not rec_id:
        print(f'❌ {sym}: no Airtable row found')
        continue
    d = parse_screener(sym)
    print(f'\\n=== {sym} ===')
    print('FII row:', d.get('fii_vals'))
    print('DII row:', d.get('dii_vals'))
    print('Promoter row:', d.get('promoter_vals'))
    patch_fields = {}
    for k in ['FII_Pct','FII_Change_Q','DII_Pct','DII_Change_Q','Promoter_Pct','Promoter_Change_Q','Price','Signal','Last_Updated']:
        if k in d:
            patch_fields[k] = d[k]
    print('Patch fields:', patch_fields)
    at_patch(rec_id, patch_fields)
    print('✅ Airtable PATCH ok')
    time.sleep(0.5)

print('\\n✅ Dry-run complete — 3 symbols parsed and patched')