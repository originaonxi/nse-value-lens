#!/usr/bin/env python3
"""
Daily refresh: fetches institutional holding data for NSE F&O stocks
Sources:
  1. NSE bulk/block deals (public CSV from NSE archives)
  2. Screener.in quarterly FII/DII/Promoter holding changes (public)
Sends email alert when a stock shows net institutional selling > 1%

Run: AIRTABLE_API_KEY=xxx GMAIL_FROM=xxx GMAIL_APP_PWD=xxx ALERT_TO=xxx python refresh_fo_institutional.py
"""
import os, sys, json, zipfile, io, re, time, smtplib
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── Env ────────────────────────────────────────────────────────────────
AKEY      = os.environ.get("AIRTABLE_API_KEY")
BASE_ID   = os.environ.get("AIRTABLE_BASE_ID", "appQsIke1wuAVOkpF")
GMAIL_FROM = os.environ.get("GMAIL_FROM", "")
GMAIL_PWD  = os.environ.get("GMAIL_APP_PWD", "")
ALERT_TO   = os.environ.get("ALERT_TO", GMAIL_FROM)

if not AKEY: print("❌ AIRTABLE_API_KEY not set"); sys.exit(1)
TABLE_URL = f"https://api.airtable.com/v0/{BASE_ID}/fo_tracker"

# ── Helpers ─────────────────────────────────────────────────────────────
def at_get(path, params=""):
    url = f"https://api.airtable.com/v0/meta/{path}" if not path.startswith("https://") else path
    if params: url += "?" + params
    req = Request(url, headers={"Authorization": f"Bearer {AKEY}"})
    with urlopen(req) as r: return json.loads(r.read())

def at_patch(rec_id, fields):
    data = json.dumps({"fields": fields}).encode()
    req = Request(f"{TABLE_URL}/{rec_id}", data=data,
                  headers={"Authorization": f"Bearer {AKEY}", "Content-Type": "application/json"},
                  method="PATCH")
    with urlopen(req) as r: return json.loads(r.read())

def fetch_all_records():
    records, offset = [], ""
    while True:
        d = at_get(TABLE_URL, "fields[]=Symbol&fields[]=FII_Pct&fields[]=DII_Pct&fields[]=Promoter_Pct" + (f"&offset={offset}" if offset else ""))
        records += d.get("records", [])
        offset = d.get("offset", "")
        if not offset: break
    return records

# ── 1. NSE Bulk/Block Deals ─────────────────────────────────────────────
def fetch_bulk_deals():
    """Temporary stub until stable NSE bulk/block archive URL is wired."""
    print("📊 Bulk/block deals source not yet wired — leaving Bulk_Deals blank for this run")
    return {}

# ── 2. Screener.in holding data ─────────────────────────────────────────
def extract_row_values(html, label_anchor):
    idx = html.find(label_anchor)
    if idx == -1:
        return []
    snip = html[idx: idx + 2200]
    vals = re.findall(r'<td>\s*([0-9]+\.[0-9]+)%\s*</td>', snip)
    return [float(v) for v in vals[:8]]

def fetch_screener(symbol):
    """Fetch latest quarterly FII/DII/Promoter values from screener.in."""
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        html = urlopen(req, timeout=12).read().decode("utf-8", errors="ignore")
        promoters = extract_row_values(html, "Company.showShareholders('promoters', 'quarterly'")
        fiis      = extract_row_values(html, "Company.showShareholders('foreign_institutions', 'quarterly'")
        diis      = extract_row_values(html, "Company.showShareholders('domestic_institutions', 'quarterly'")
        pm = re.search(r'₹\s*([0-9,]+\.?[0-9]*)', html) or re.search(r'"price"\s*:\s*"?([0-9,]+\.?[0-9]*)', html)
        price = float(pm.group(1).replace(',', '')) if pm else None
        out = {'promoter_vals': promoters, 'fii_vals': fiis, 'dii_vals': diis}
        if fiis: out["fii"] = fiis[0]
        if len(fiis) >= 2: out["fii_change_q"] = round(fiis[0] - fiis[1], 2)
        if diis: out["dii"] = diis[0]
        if len(diis) >= 2: out["dii_change_q"] = round(diis[0] - diis[1], 2)
        if promoters: out["promoter"] = promoters[0]
        if len(promoters) >= 2: out["promoter_change_q"] = round(promoters[0] - promoters[1], 2)
        if price is not None: out["price"] = price
        return out
    except:
        return {}

# ── 3. Email alert ───────────────────────────────────────────────────────
def send_alert(sellers):
    if not GMAIL_FROM or not GMAIL_PWD or not sellers:
        if sellers:
            print(f"⚠️ Email not configured. Alert: {', '.join(s['sym'] for s in sellers)}")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔴 NSE F&O Net Sellers Alert — {datetime.now().strftime('%d %b %Y')}"
    msg["From"] = GMAIL_FROM
    msg["To"] = ALERT_TO
    rows = ""
    for s in sellers:
        rows += f"""<tr>
          <td><b>{s['sym']}</b></td>
          <td style='color:red'>{s['fii_change']:+.1f}% FII</td>
          <td style='color:orange'>{s['dii_change']:+.1f}% DII</td>
          <td>{s.get('deals','—')}</td>
        </tr>"""
    html = f"""<html><body style='font-family:sans-serif'>
      <h2>🔴 NSE F&O Institutional Net Sellers — {datetime.now().strftime('%d %b %Y')}</h2>
      <p>The following stocks show institutional selling (FII or DII holding down ≥1% QoQ):</p>
      <table border='1' cellpadding='6' cellspacing='0'>
        <tr><th>Stock</th><th>FII Change</th><th>DII Change</th><th>Recent Deals</th></tr>
        {rows}
      </table>
      <p style='color:grey;font-size:12px'>Source: Screener.in (quarterly) + NSE bulk deal archives.
      Not SEBI-registered advice. Educational tracker.</p>
    </body></html>"""
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_FROM, GMAIL_PWD)
            s.sendmail(GMAIL_FROM, ALERT_TO, msg.as_string())
        print(f"✅ Alert email sent to {ALERT_TO}")
    except Exception as e:
        print(f"❌ Email failed: {e}")

# ── Main ─────────────────────────────────────────────────────────────────
print(f"🚀 F&O Institutional Tracker refresh — {datetime.now().strftime('%d %b %Y %H:%M')}")

records = fetch_all_records()
print(f"📋 {len(records)} stocks to refresh")

bulk_deals = fetch_bulk_deals()

sellers = []
updated = 0
for rec in records:
    sym = rec["fields"].get("Symbol", "")
    if not sym: continue
    old_fii = rec["fields"].get("FII_Pct") or 0
    old_dii = rec["fields"].get("DII_Pct") or 0
    old_prom = rec["fields"].get("Promoter_Pct") or 0

    d = fetch_screener(sym)
    time.sleep(0.5)  # Respectful delay

    new_fii = d.get("fii", old_fii)
    new_dii = d.get("dii", old_dii)
    new_prom = d.get("promoter", old_prom)
    # Use Screener quarterly changes directly when available
    fii_chg = d.get("fii_change_q", round(new_fii - old_fii, 2))
    dii_chg = d.get("dii_change_q", round(new_dii - old_dii, 2))
    prom_chg = d.get("promoter_change_q", round(new_prom - old_prom, 2))

    deals_txt = "\n".join(bulk_deals.get(sym, [])[:5])

    if fii_chg <= -1 or dii_chg <= -1:
        signal = "SELLING"
        sellers.append({"sym": sym, "fii_change": fii_chg, "dii_change": dii_chg, "deals": deals_txt or "—"})
    elif fii_chg >= 1 or dii_chg >= 1:
        signal = "BUYING"
    elif deals_txt:
        signal = "WATCH"
    else:
        signal = "NEUTRAL"

    # Airtable allowlist only — never patch unknown fields
    fields = {
        "FII_Pct": new_fii,
        "FII_Change_Q": fii_chg,
        "DII_Pct": new_dii,
        "DII_Change_Q": dii_chg,
        "Promoter_Pct": new_prom,
        "Promoter_Change_Q": prom_chg,
        "Signal": signal,
        "Last_Updated": datetime.now().isoformat(),
    }
    if d.get("price") is not None:
        fields["Price"] = d["price"]
    if deals_txt:
        fields["Bulk_Deals"] = deals_txt

    at_patch(rec["id"], fields)
    updated += 1
    sys.stdout.write(f"\r  {updated}/{len(records)} — {sym} [{signal}]   ")
    sys.stdout.flush()

print(f"\n✅ Updated {updated} stocks | 🔴 {len(sellers)} net sellers")
send_alert(sellers)
