#!/usr/bin/env python3
import os, json, math, urllib.parse, smtplib
from datetime import datetime
from urllib.request import Request, urlopen
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import yfinance as yf
import pandas as pd

AKEY = os.environ.get('AIRTABLE_API_KEY')
BASE_ID = os.environ.get('AIRTABLE_BASE_ID', 'appQsIke1wuAVOkpF')
TABLE = 'fo_tracker'
GMAIL_FROM = os.environ.get('GMAIL_FROM','')
GMAIL_PWD = os.environ.get('GMAIL_APP_PWD','').replace(' ','')
ALERT_TO = os.environ.get('ALERT_TO', GMAIL_FROM)
if not AKEY:
    print('❌ AIRTABLE_API_KEY not set')
    raise SystemExit(1)

TABLE_URL = f'https://api.airtable.com/v0/{BASE_ID}/{TABLE}'
META_TABLES = f'https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables'
HEADERS = {'Authorization': f'Bearer {AKEY}'}


def at_get_all():
    rows, offset = [], ''
    while True:
        url = TABLE_URL + ('?' + urllib.parse.urlencode({'offset': offset}) if offset else '')
        with urlopen(Request(url, headers=HEADERS)) as r:
            d = json.loads(r.read())
        rows += d.get('records', [])
        offset = d.get('offset','')
        if not offset: break
    return rows


def at_patch(rec_id, fields):
    body = json.dumps({'fields': fields}).encode()
    req = Request(f'{TABLE_URL}/{rec_id}', data=body,
                  headers={'Authorization': f'Bearer {AKEY}', 'Content-Type': 'application/json'}, method='PATCH')
    with urlopen(req) as r:
        return json.loads(r.read())


def ensure_fields():
    with urlopen(Request(META_TABLES, headers=HEADERS)) as r:
        d = json.loads(r.read())
    table = [t for t in d['tables'] if t['name'] == TABLE][0]
    table_id = table['id']
    existing = {f['name'] for f in table['fields']}
    needed = [
        ('Rank', {'type':'number','options':{'precision':0}}),
        ('Rank_Score', {'type':'number','options':{'precision':2}}),
        ('Rank_Change', {'type':'number','options':{'precision':0}}),
        ('Ret_6M', {'type':'number','options':{'precision':2}}),
        ('Ret_12M', {'type':'number','options':{'precision':2}}),
        ('RSI14', {'type':'number','options':{'precision':2}}),
        ('DMA50', {'type':'number','options':{'precision':2}}),
        ('DMA200', {'type':'number','options':{'precision':2}}),
        ('Trend_Signal', {'type':'singleLineText'}),
        ('Ranking_Updated', {'type':'dateTime','options':{'dateFormat':{'name':'iso'},'timeFormat':{'name':'24hour'},'timeZone':'Asia/Kolkata'}}),
    ]
    for name,spec in needed:
        if name in existing: continue
        body = json.dumps({'name':name, **spec}).encode()
        req = Request(f'https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables/{table_id}/fields', data=body,
                      headers={'Authorization': f'Bearer {AKEY}', 'Content-Type': 'application/json'}, method='POST')
        with urlopen(req) as r: json.loads(r.read())
        print('added field', name)


def rsi14(close):
    diff = close.diff()
    gain = diff.clip(lower=0)
    loss = (-diff).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    out = 100 - 100/(1+rs)
    return float(out.dropna().iloc[-1]) if not out.dropna().empty else None


def score_row(f, q):
    score = 50.0
    # institutional factor
    fii = f.get('FII_Change_Q') or 0
    dii = f.get('DII_Change_Q') or 0
    score += max(-20, min(20, (fii + dii) * 6))
    # valuation / quality
    pe = f.get('PE'); peg = f.get('PEG'); roe = f.get('ROE'); roce = f.get('ROCE'); de = f.get('Debt_Equity')
    if pe is not None and pe < 18: score += 5
    if peg is not None and peg < 1: score += 6
    elif peg is not None and peg > 2: score -= 4
    if roe is not None and roe > 15: score += 4
    if roce is not None and roce > 15: score += 4
    if de is not None and de < 1: score += 3
    elif de is not None and de > 2: score -= 5
    # technical / momentum
    r6 = q.get('ret6',0); r12 = q.get('ret12',0)
    score += max(-10, min(10, r6 / 3))
    score += max(-10, min(10, r12 / 8))
    if q.get('price') and q.get('dma200') and q['price'] > q['dma200']: score += 6
    else: score -= 6
    if q.get('price') and q.get('dma50') and q['price'] > q['dma50']: score += 3
    rsi = q.get('rsi')
    if rsi is not None:
        if 35 <= rsi <= 60: score += 3
        elif rsi > 75: score -= 4
    return round(max(0, min(100, score)), 2)


print('📈 Loading Airtable rows...')
ensure_fields()
rows = at_get_all()
print(f'✅ {len(rows)} rows loaded')
syms = [r['fields'].get('Symbol') for r in rows if r['fields'].get('Symbol')]
tickers = ' '.join([s + '.NS' for s in syms])
print('📡 Downloading Yahoo Finance batch...')
raw = yf.download(tickers=tickers, period='1y', auto_adjust=True, group_by='ticker', threads=True, progress=False)

quotes = {}
for sym in syms:
    try:
        df = raw[sym + '.NS'].dropna()
        if df.empty or len(df) < 50: continue
        close = df['Close']
        price = float(close.iloc[-1])
        dma50 = float(close.rolling(50).mean().iloc[-1])
        dma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
        ret6 = round((price / float(close.iloc[max(0, len(close)-126)]) - 1) * 100, 2) if len(close) > 126 else None
        ret12 = round((price / float(close.iloc[0]) - 1) * 100, 2)
        quotes[sym] = {
            'price': price, 'dma50': dma50, 'dma200': dma200,
            'ret6': ret6 or 0, 'ret12': ret12 or 0,
            'rsi': rsi14(close)
        }
    except Exception:
        continue
print(f'✅ Quotes for {len(quotes)} stocks')

scored = []
for r in rows:
    f = r['fields']
    sym = f.get('Symbol')
    q = quotes.get(sym, {})
    sc = score_row(f, q)
    scored.append((sym, sc, r, q))
scored.sort(key=lambda x: x[1], reverse=True)
rank_map = {sym:i+1 for i,(sym,_,_,_) in enumerate(scored)}

print('✍️ Patching Airtable rankings...')
updated = 0
for sym, sc, rec, q in scored:
    old_rank = rec['fields'].get('Rank')
    new_rank = rank_map[sym]
    rank_change = (old_rank - new_rank) if old_rank is not None else None
    trend = 'UPTREND' if q.get('price') and q.get('dma200') and q['price'] > q['dma200'] else 'DOWNTREND'
    fields = {
        'Rank': new_rank,
        'Rank_Score': sc,
        'Trend_Signal': trend,
        'Ranking_Updated': datetime.now().isoformat(),
    }
    if rank_change is not None: fields['Rank_Change'] = rank_change
    if q.get('ret6') is not None: fields['Ret_6M'] = q['ret6']
    if q.get('ret12') is not None: fields['Ret_12M'] = q['ret12']
    if q.get('rsi') is not None: fields['RSI14'] = q['rsi']
    if q.get('dma50') is not None: fields['DMA50'] = q['dma50']
    if q.get('dma200') is not None: fields['DMA200'] = q['dma200']
    if q.get('price') is not None: fields['Price'] = q['price']
    at_patch(rec['id'], fields)
    updated += 1
    if updated % 25 == 0: print(' ', updated, '/', len(scored))
print(f'✅ Ranked and updated {updated} stocks')

# Email daily ranking digest
if GMAIL_FROM and GMAIL_PWD and ALERT_TO:
    top = scored[:25]
    rows_html=''.join(f"<tr><td>{i+1}</td><td><b>{sym}</b></td><td>{sc}</td><td>{quotes.get(sym,{}).get('ret6','—')}</td><td>{quotes.get(sym,{}).get('rsi','—')}</td><td>{(rows[[rr['fields'].get('Symbol') for rr in rows].index(sym)]['fields'].get('Signal') if sym in [rr['fields'].get('Symbol') for rr in rows] else '—')}</td></tr>" for i,(sym,sc,_,_) in enumerate(top))
    html=f"<html><body style='font-family:Arial,sans-serif'><h2>NSE F&O Daily Ranking</h2><p>Top 25 ranked F&O stocks updated daily.</p><table border='1' cellpadding='6' cellspacing='0'><tr><th>Rank</th><th>Symbol</th><th>Score</th><th>6M %</th><th>RSI</th><th>Signal</th></tr>{rows_html}</table><p>Signals combine institutional flows, quality, valuation, and momentum. Net seller digest is sent separately.</p></body></html>"
    msg=MIMEMultipart('alternative'); msg['Subject']='NSE F&O Daily Ranking'; msg['From']=GMAIL_FROM; msg['To']=ALERT_TO; msg.attach(MIMEText(html,'html'))
    with smtplib.SMTP_SSL('smtp.gmail.com',465,timeout=25) as s:
        s.login(GMAIL_FROM,GMAIL_PWD)
        s.sendmail(GMAIL_FROM,[ALERT_TO],msg.as_string())
    print('✅ Ranking email sent')
else:
    print('⚠️ Ranking email skipped (mail env incomplete)')
