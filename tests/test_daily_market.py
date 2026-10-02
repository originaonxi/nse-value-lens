import io
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import zipfile

from daily_market import (parse_deals, parse_bhavcopy, breadth, expected_session,
                          refresh_deals, parse_indices, retain)

HEADER = b'Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,Trade Price / Wght. Avg. Price,Remarks\n'
ROWS = HEADER + b'01-OCT-2026,BSE,BSE Ltd,Example buyer,BUY,100000,100.50,-\n01-OCT-2026,BSE,BSE Ltd,Example buyer,SELL,100000,101.50,-\n'


class DailyMarketTests(unittest.TestCase):
    def test_both_sides_remain_visible_not_automatic_accumulation(self):
        rows = parse_deals(ROWS, 'bulk', '2026-10-01')
        self.assertEqual([r['side'] for r in rows], ['BUY', 'SELL'])
        self.assertEqual(rows[0]['value_crore'], 1.005)
        self.assertEqual(sum(r['quantity'] * (1 if r['side'] == 'BUY' else -1) for r in rows), 0)

    def test_reject_future_wrong_date_html_and_undated_empty(self):
        for raw in (HEADER, b'<html>Access denied</html>', ROWS.replace(b'01-OCT', b'02-OCT')):
            with self.assertRaises(ValueError): parse_deals(raw, 'bulk', '2026-10-01')
        with self.assertRaises(ValueError): parse_deals(b'{"data":[]}', 'bulk', '2026-10-01', True)

    def test_reject_invalid_quantity_price_side(self):
        for raw in (ROWS.replace(b'100000', b'-2'), ROWS.replace(b'100.50', b'NaN'), ROWS.replace(b'BUY', b'UNKNOWN')):
            with self.assertRaises(ValueError): parse_deals(raw, 'bulk', '2026-10-01')

    def test_api_uses_display_date_not_utc_midnight_field(self):
        raw = json.dumps({'data':[{'BD_DT_DATE':'01-OCT-2026','BD_DT_ORDER':'2026-09-30T18:30:00Z',
                                  'BD_SYMBOL':'M&M','BD_SCRIP_NAME':'M&M','BD_CLIENT_NAME':'Example',
                                  'BD_BUY_SELL':'BUY','BD_QTY_TRD':123,'BD_TP_WATP':12.5}]}).encode()
        row = parse_deals(raw, 'bulk', '2026-10-01', True)[0]
        self.assertEqual(row['date'], '2026-10-01'); self.assertEqual(row['symbol'], 'M&M')

    def test_holiday_weekend_before_close_and_special_session(self):
        calendar={'year':2026,'holidays':['2026-10-02']}
        for stamp in ('2026-10-02T18:00:00+00:00','2026-10-04T10:00:00+00:00','2026-10-05T09:00:00+00:00'):
            self.assertEqual(expected_session(datetime.fromisoformat(stamp),calendar),'2026-10-01')
        calendar['special_sessions']=['2026-10-03']
        self.assertEqual(expected_session(datetime.fromisoformat('2026-10-03T12:00:00+00:00'),calendar),'2026-10-03')

    def test_failed_refresh_retains_old_date_and_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            previous={'as_of':'2026-09-30','state':'fresh','rows':[{'symbol':'BSE'}]}
            downloader=Mock(); downloader.get.return_value=(b'<html>unavailable</html>',{})
            result=refresh_deals('bulk','2026-10-01',previous,downloader,Path(directory),{})
            self.assertEqual(result['state'],'stale');self.assertEqual(result['as_of'],'2026-09-30')
            self.assertEqual(result['rows'],previous['rows']);self.assertEqual(previous['state'],'fresh')

    def test_no_previous_data_is_unavailable_not_zero_deals(self):
        self.assertEqual(retain(None,'2026-10-01','Unavailable')['state'],'unavailable')

    def test_bhavcopy_scope_and_breadth_accounting(self):
        content='TradDt,TckrSymb,SctySrs,ClsPric,PrvsClsgPric,TtlTradgVol,TtlTrfVal\n2026-10-01,A,EQ,110,100,1000,110000\n2026-10-01,B,EQ,90,100,2000,180000\n2026-10-01,C,EQ,100,100,3000,300000\n2026-10-01,D,GB,100,100,100,10000\n2026-10-01,E,EQ,100,100,0,0\n'
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as z:z.writestr('report.csv',content)
        rows,excluded=parse_bhavcopy(buffer.getvalue(),'2026-10-01')
        result=breadth(rows)
        self.assertEqual((result['count'],result['advances'],result['declines'],result['unchanged']),(3,1,1,1))
        self.assertEqual(result['up_volume_pct'],33.33);self.assertEqual(excluded,1)
        with self.assertRaises(ValueError):parse_bhavcopy(buffer.getvalue(),'2026-10-02')

    def test_index_dash_is_excluded_not_fabricated(self):
        raw=b'Index Name,Index Date,Closing Index Value,Change(%)\nNifty 50,01-10-2026,100,-1\nNifty50 Dividend Points,01-10-2026,20,-\n'
        self.assertEqual(len(parse_indices(raw,'2026-10-01')),1)


if __name__=='__main__':unittest.main()
