#!/usr/bin/env python3
"""
Setup: download NSE FO bhavcopy → extract 210 F&O stocks → populate Airtable fo_tracker
Run: node scripts/setup_fo_tracker.js  (or python directly with AIRTABLE_API_KEY set)
"""
import os, sys, json, zipfile, io
from datetime import datetime, timedelta
from urllib.request import Request, urlopen

AKEY = os.environ.get("AIRTABLE_API_KEY")
if not AKEY:
    print("❌ AIRTABLE_API_KEY not set")
    sys.exit(1)

BASE_ID = "appQsIke1wuAVOkpF"  # Sam Terminal Brain

def api(method, url_path, body=None):
    url = f"https://api.airtable.com/v0/meta/{url_path}" if not url_path.startswith("https://") else url_path
    h = {"Authorization": f"Bearer {AKEY}", "Content-Type": "application/json"}
    d = json.dumps(body).encode() if body else None
    req = Request(url, data=d, headers=h, method=method)
    with urlopen(req) as r:
        return json.loads(r.read())

# ─── Fetch FO bhavcopy ───────────────────────────────────────────────
print("📡 Downloading NSE FO bhavcopy...")
syms = None
for i in range(20):
    d = datetime.now() - timedelta(days=i)
    if d.weekday() >= 5: continue
    ds = d.strftime("%Y%m%d")
    url = f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{ds}_F_0000.csv.zip"
    try:
        resp = urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=10)
        z = zipfile.ZipFile(io.BytesIO(resp.read()))
        csv = z.read([n for n in z.namelist() if n.endswith(".csv")][0]).decode("latin-1")
        lines = [l.strip() for l in csv.split("\n") if l.strip()]
        hdr = lines[0].split(",")
        si, ti = hdr.index("TckrSymb"), hdr.index("FinInstrmTp")
        syms = sorted({c[si].strip('"') for c in [l.split(",") for l in lines[1:]] if c[ti].strip('"') in ("FUTSTK", "STF")})
        print(f"✅ {ds}: {len(syms)} F&O stocks")
        break
    except: continue
if not syms: print("❌ No FO bhavcopy found"); sys.exit(1)

# ─── Table schema ────────────────────────────────────────────────────
FIELDS = [
    {"name": "Symbol", "type": "singleLineText"},
    {"name": "FII_Pct", "type": "percent"},
    {"name": "FII_Change_Q", "type": "number"},
    {"name": "DII_Pct", "type": "percent"},
    {"name": "DII_Change_Q", "type": "number"},
    {"name": "MF_Pct", "type": "percent"},
    {"name": "MF_Change_Q", "type": "number"},
    {"name": "Promoter_Pct", "type": "percent"},
    {"name": "Promoter_Change_Q", "type": "number"},
    {"name": "Price", "type": "currency", "options": {"precision": 1, "symbol": "₹"}},
    {"name": "Bulk_Deals", "type": "multilineText"},
    {"name": "Signal", "type": "singleSelect", "options": {
        "choices": [{"name": "SELLING"}, {"name": "WATCH"}, {"name": "NEUTRAL"}, {"name": "BUYING"}]
    }},
    {"name": "Last_Updated", "type": "dateTime"},
]

# ─── Replace table in Sam Terminal Brain ─────────────────────────────
print(f"📋 Setting up fo_tracker table in Sam Terminal Brain ({BASE_ID})...")
tables = api("GET", f"bases/{BASE_ID}/tables")
old = next((t for t in tables.get("tables", []) if t["name"] == "fo_tracker"), None)
if old:
    api("DELETE", f"bases/{BASE_ID}/tables/{old['id']}")
    print("  🗑️ Deleted old fo_tracker table")
api("POST", f"bases/{BASE_ID}/tables", {"name": "fo_tracker", "fields": FIELDS})
print("✅ Table fo_tracker created")

# ─── Populate (batches of 10) ────────────────────────────────────────
print(f"📥 Populating {len(syms)} stocks...")
TABLE_URL = f"https://api.airtable.com/v0/{BASE_ID}/fo_tracker"
ok = 0
for i in range(0, len(syms), 10):
    batch = [{"fields": {"Symbol": s, "Last_Updated": datetime.now().isoformat()}} for s in syms[i:i+10]]
    body = json.dumps({"records": batch}).encode()
    req = Request(TABLE_URL, data=body, headers={"Authorization": f"Bearer {AKEY}", "Content-Type": "application/json"}, method="POST")
    with urlopen(req) as r:
        resp = json.loads(r.read())
        ok += len(resp.get("records", []))
    print(f"\r  {ok}/{len(syms)}", end="", flush=True)
print(f"\n✅ Done! {ok} F&O stocks in Airtable: https://airtable.com/{BASE_ID}/fo_tracker")