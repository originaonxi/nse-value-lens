"""Check actual publication of the daily collector, without re-fetching market data."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import requests

root = Path(__file__).resolve().parents[1]
expected = json.loads((root/'docs/daily_market.json').read_text(encoding='utf-8'))
urls = ['https://originaonxi.github.io/nse-value-lens/daily_market.json']
for url in urls:
    error = None
    for attempt in range(12):
        try:
            response = requests.get(url, params={'verify':int(time.time())}, timeout=15)
            response.raise_for_status(); data=response.json()
            assert data['as_of'] >= expected['as_of'], 'Older session than committed output'
            assert data['attempted_at'] >= expected['attempted_at'], 'Latest attempt not published'
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(data['attempted_at'])).total_seconds()
            assert -300 <= age < 36*3600, 'Daily refresh overdue'
            for kind in ('market','indices','bulk','block'):
                assert data[kind]['state']=='fresh', f'{kind}: {data[kind]["state"]}'
                assert data[kind]['as_of']==data['as_of'], f'{kind}: source date differs'
            print(url, data['as_of'], 'verified', flush=True);error=None;break
        except (requests.RequestException, ValueError, KeyError, AssertionError) as exc:
            error=exc
            if attempt < 11:time.sleep(15)
    if error:raise SystemExit(f'{url}: {error}')
