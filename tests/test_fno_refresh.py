import copy
from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import fno_refresh as fno

NOW = datetime(2026, 9, 27, 20, tzinfo=timezone.utc)


def listing():
    return 'UNDERLYING,SYMBOL,SEP-26,OCT-26\nNIFTY BANK,BANKNIFTY,30,30\nName,Symbol,Lot,Lot\n'+''.join(
        f'Company {i},STOCK{i},100,100\n' for i in range(100))


def prices():
    days = pd.bdate_range(end='2026-09-25', periods=240)
    close = 120+np.sin(np.arange(240)/3)*10+np.arange(240)/10
    return pd.DataFrame({'Open':close-.5,'High':close+2,'Low':close-2,'Close':close,'Volume':2e6},index=days)


class FnoDataTests(unittest.TestCase):
    def test_exchange_sections_and_future_only_entries_are_not_current_stocks(self):
        data = listing()+'Future listing,FUTURE,,500\nNIFTY 50,NIFTY,65,65\n'
        members, month = fno.parse_membership(data, NOW.date())
        self.assertEqual(len(members),100)
        self.assertEqual(month,'SEP-26')
        self.assertNotIn('FUTURE',{m['symbol'] for m in members})

    def test_wrong_month_truncated_duplicate_and_html_sources_are_rejected(self):
        for text in [listing().replace('SEP-26','JUL-26').replace('OCT-26','AUG-26'),
                     listing()+'Duplicate,STOCK1,100,100\n',
                     'UNDERLYING,SYMBOL,SEP-26\nOnly,ONLY,1\n','<html>Access denied</html>']:
            with self.subTest(text=text[:60]), self.assertRaises(ValueError):
                fno.parse_membership(text,NOW.date())

    def test_after_expiry_next_month_is_valid_but_distant_contracts_are_not(self):
        members, month = fno.parse_membership(listing(),date(2026,10,1))
        self.assertEqual(month,'OCT-26')
        self.assertEqual(len(members),100)
        with self.assertRaises(ValueError):
            fno.parse_membership(listing().replace('SEP-26','DEC-26').replace('OCT-26','JAN-27'),NOW.date())

    def test_failed_membership_download_retains_original_verification(self):
        prior={'members':[{'symbol':'SAVED'}],'verified':True,'verified_at':'2026-09-25T12:00:00Z'}
        original=copy.deepcopy(prior)
        with patch.object(fno,'get_text',side_effect=TimeoutError('offline')):
            saved=fno.membership(prior,NOW)
            with self.assertRaises(ValueError):fno.membership(None,NOW)
        self.assertFalse(saved['verified'])
        self.assertEqual(saved['verified_at'],prior['verified_at'])
        self.assertEqual(prior,original)

    def run_stock(self,root,raw,error=None):
        base={'as_of':'2026-09-25','market':{'data_ready':True,'reference_filter_passed':True}}
        meta={'Symbol':'SAMPLE','Company Name':'Sample','Industry':'Example'}
        with patch.object(fno.yf,'Ticker') as ticker:
            ticker.return_value.history.side_effect=error
            ticker.return_value.history.return_value=raw
            return fno.fetch_stock(meta,base,prices().index,Path(root),NOW)

    def test_incomplete_latest_bar_is_not_turned_into_a_current_signal(self):
        raw=prices();raw.loc[raw.index[-1],'High']=1
        with tempfile.TemporaryDirectory() as folder:
            row=self.run_stock(folder,raw)
        self.assertEqual(row['status'],'CAUTION')
        self.assertEqual(row['data_date'],'2026-09-24')
        self.assertFalse(row['entry_allowed'])
        self.assertFalse(row['zones'])

    def test_failed_download_keeps_saved_candles_and_never_mutates_stock_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'SAMPLE.NS.csv';prices().to_csv(path,index_label='Date')
            original=path.read_bytes()
            row=self.run_stock(folder,None,TimeoutError('offline'))
            self.assertEqual(path.read_bytes(),original)
        self.assertEqual(row['status'],'CAUTION')
        self.assertEqual(row['data_date'],'2026-09-25')
        self.assertEqual(len(row['chart']),140)
        self.assertFalse(row['entry_allowed'])
        self.assertIsNone(row['retrieved_at'])

    def test_revised_adjusted_history_replaces_whole_scale(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'SAMPLE.NS.csv';old=prices();old.to_csv(path,index_label='Date')
            revised=prices();revised[fno.OHLCV[:4]]/=2
            row=self.run_stock(folder,revised)
            saved=pd.read_csv(path)
        self.assertAlmostEqual(saved.Close.iloc[0],revised.Close.iloc[0])
        self.assertAlmostEqual(row['close'],revised.Close.iloc[-1],places=3)
        self.assertIsNotNone(row['retrieved_at'])

    def test_regressed_or_short_history_preserves_good_cache(self):
        for raw in [prices().iloc[:-1],prices().tail(30)]:
            with self.subTest(size=len(raw)), tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'SAMPLE.NS.csv';prices().to_csv(path,index_label='Date')
                original=path.read_bytes();row=self.run_stock(folder,raw)
                self.assertEqual(path.read_bytes(),original)
                self.assertEqual(row['status'],'CAUTION')

    def test_future_and_market_holiday_candles_are_excluded(self):
        raw=prices()
        for day in ['2026-09-26','2026-09-28']:raw.loc[pd.Timestamp(day)]=raw.iloc[-1]
        with tempfile.TemporaryDirectory() as folder:
            row=self.run_stock(folder,raw)
        self.assertEqual(row['chart'][-1]['date'],'2026-09-25')
        self.assertTrue(all(b['date']<='2026-09-25' for b in row['chart']))

    def test_writer_cannot_overwrite_the_original_scan(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'docs').mkdir();stock=root/'docs/hhhl_scan.json';stock.write_text('unchanged')
            fno.write_snapshot(root,{'rows':[]})
            self.assertEqual(stock.read_text(),'unchanged')
            self.assertEqual(json.loads((root/'public/data/hhhl_fno.json').read_text()),{'rows':[]})


if __name__=='__main__':unittest.main()
