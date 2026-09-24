"""Fetch public Nifty Indices TRI records in at-most-one-year requests."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import requests
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT/'.cache/vcp'
URL = 'https://www.niftyindices.com/BackPage/getTotalReturnIndexString'


def fetch(year):
    path = CACHE/f'tri_{year}.json'
    if path.exists():
        return json.loads(path.read_text())
    end = f'31-Dec-{year}' if year < 2026 else '23-Sep-2026'
    info = {'name':'NIFTY 200','indexName':'NIFTY 200','startDate':f'01-Jan-{year}','endDate':end}
    r = requests.post(URL, json={'cinfo':json.dumps(info)},
                      headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.niftyindices.com/reports/historical-data'},
                      timeout=25)
    r.raise_for_status()
    rows = r.json()
    if isinstance(rows,dict) and 'd' in rows:
        rows = rows['d']
    if isinstance(rows,str):
        rows = json.loads(rows)
    if not isinstance(rows,list) or not rows:
        raise ValueError(f'No TRI rows: {str(rows)[:100]}')
    path.write_text(json.dumps(rows),encoding='utf-8')
    return rows


def fetch_missing_price_dates():
    audit_path = ROOT/'research/vcp/data_audit.json'
    path = CACHE/'index_price_repairs.json'
    if path.exists():
        return
    audit = json.loads(audit_path.read_text())
    requests_log, records = [], []
    url = 'https://www.niftyindices.com/BackPage/getHistoricaldatatabletoString'
    missing_dates = sorted(set(audit['benchmark_missing']) | set(audit['benchmark'].get('official_repairs',[])))
    for date in missing_dates:
        date = pd.Timestamp(date)
        info = {'name':'NIFTY 200','indexName':'NIFTY 200',
                'startDate':(date-pd.Timedelta(days=2)).strftime('%d-%b-%Y'),
                'endDate':(date+pd.Timedelta(days=2)).strftime('%d-%b-%Y')}
        try:
            r = requests.post(url,json={'cinfo':json.dumps(info)},
                              headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.niftyindices.com/reports/historical-data'},timeout=25)
            r.raise_for_status()
            rows = r.json()
            if isinstance(rows,dict) and 'd' in rows:
                rows = rows['d']
            if isinstance(rows,str):
                rows = json.loads(rows)
            if not isinstance(rows,list):
                raise ValueError('No official price records')
            records.extend(rows)
            requests_log.append({'date':str(date.date()),'records':len(rows)})
            print('Official price repair',str(date.date()),rows,flush=True)
        except Exception as exc:
            requests_log.append({'date':str(date.date()),'error':str(exc)[:200]})
    path.write_text(json.dumps({'url':url,'requests':requests_log,'rows':records},indent=2),encoding='utf-8')


if __name__ == '__main__':
    errors, all_rows = {}, []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(fetch,y):y for y in range(2015,2027)}
        for future in as_completed(futures):
            year = futures[future]
            try:
                rows = future.result()
                all_rows.extend(rows)
                print(year, len(rows), rows[0], flush=True)
            except Exception as exc:
                errors[str(year)] = str(exc)[:220]
                print(year, errors[str(year)], flush=True)
    pd.DataFrame(all_rows).to_csv(CACHE/'nifty200_tri_raw.csv',index=False)
    (CACHE/'tri_audit.json').write_text(json.dumps({'url':URL,'errors':errors,'rows':len(all_rows)},indent=2))
    fetch_missing_price_dates()
