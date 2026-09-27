from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import global_markets as gm

NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
FX = next(i for i in gm.INSTRUMENTS if i['symbol'] == 'EURUSD=X')
GOLD = gm.INSTRUMENTS[0]


def daily(end='2026-09-25', periods=160):
    index = pd.bdate_range(end=end, periods=periods)
    price = 100 + np.sin(np.arange(periods)*.7)*5 + np.arange(periods)*.02
    return pd.DataFrame({'Open': price, 'High': price+1, 'Low': price-1,
                         'Close': price+.2, 'Volume': 1000.0}, index=index)


def hourly():
    dates = pd.bdate_range(end='2026-09-25', periods=100)
    stamps = []
    for day in dates:
        end = pd.Timestamp(day.date()).tz_localize(gm.NY)+pd.Timedelta(hours=16)
        stamps.extend(pd.date_range(end=end, periods=24, freq='h'))
    price = 1.10 + np.sin(np.arange(len(stamps))*.08)*.01
    return pd.DataFrame({'Open': price, 'High': price+.001, 'Low': price-.001,
                         'Close': price+.0002, 'Volume': 0}, index=pd.DatetimeIndex(stamps))


class GlobalMarketsTests(unittest.TestCase):
    def test_watchlist_ids_unique_with_15_commodities_and_11_fx(self):
        self.assertEqual(len({r['symbol'] for r in gm.INSTRUMENTS}), 26)
        self.assertEqual(sum(r['group']=='commodity' for r in gm.INSTRUMENTS), 15)
        self.assertEqual(sum(r['group']=='forex' for r in gm.INSTRUMENTS), 11)
        self.assertEqual(next(r['unit'] for r in gm.INSTRUMENTS if r['symbol']=='ZC=F'), 'US cents per bushel')

    def test_weekend_and_current_utc_date_are_not_expected_complete_sessions(self):
        self.assertEqual(gm.expected_date(NOW).isoformat(), '2026-09-25')
        self.assertEqual(gm.expected_date(datetime(2026,9,28,20,tzinfo=timezone.utc)).isoformat(), '2026-09-25')

    def test_fx_daily_ohlc_uses_actual_hours_and_no_fabricated_volume(self):
        raw = hourly()
        frame, audit = gm.prepare_prices(raw, FX, NOW)
        last = raw.tail(24)
        self.assertAlmostEqual(frame.iloc[-1].Open, last.iloc[0].Open)
        self.assertAlmostEqual(frame.iloc[-1].High, last.High.max())
        self.assertAlmostEqual(frame.iloc[-1].Low, last.Low.min())
        self.assertAlmostEqual(frame.iloc[-1].Close, last.iloc[-1].Close)
        self.assertTrue(frame.Volume.isna().all())
        self.assertEqual(audit['hour_counts']['2026-09-25'], 24)

    def test_fx_sunday_evening_belongs_to_monday(self):
        frame, _ = gm.prepare_prices(hourly(), FX, NOW)
        self.assertTrue(all(d.weekday()<5 for d in frame.index))
        self.assertEqual(len(frame), 100)

    def test_ny_close_tracks_daylight_saving_instead_of_fixed_utc(self):
        winter = pd.Timestamp('2026-03-06 16:00',tz=gm.NY).tz_convert('UTC')
        summer = pd.Timestamp('2026-03-09 16:00',tz=gm.NY).tz_convert('UTC')
        self.assertEqual(winter.hour, 21)
        self.assertEqual(summer.hour, 20)
        # The next hour is the next session, on both sides of the clock change.
        for stamp in [winter,summer]:
            self.assertEqual(stamp.tz_convert(gm.NY).hour, 16)
            self.assertEqual((stamp+pd.Timedelta(hours=1)).tz_convert(gm.NY).hour, 17)

    def test_invalid_hour_rejects_entire_daily_candle_without_repairing_extremes(self):
        raw = hourly()
        raw.iloc[-3, raw.columns.get_loc('High')] = raw.iloc[-3].Low-1
        frame, audit = gm.prepare_prices(raw, FX, NOW)
        self.assertEqual(audit['invalid_dates'], ['2026-09-25'])
        self.assertEqual(frame.index[-1].date().isoformat(), '2026-09-24')

    def test_sparse_fx_day_is_excluded_and_recorded(self):
        raw = hourly().drop(hourly().tail(24).index[:8])
        frame, audit = gm.prepare_prices(raw, FX, NOW)
        self.assertIn('2026-09-25', audit['partial_dates'])
        self.assertEqual(frame.index[-1].date().isoformat(), '2026-09-24')

    def test_hourly_feed_without_timezone_is_rejected(self):
        raw = hourly();raw.index=raw.index.tz_localize(None)
        with self.assertRaisesRegex(ValueError, 'timezone'):
            gm.prepare_prices(raw, FX, NOW)

    def test_current_date_candle_and_zero_volume_futures_are_excluded(self):
        raw = daily(end='2026-09-28')
        raw.loc[pd.Timestamp('2026-09-25'),'Volume'] = 0
        frame, _ = gm.prepare_prices(raw,GOLD,datetime(2026,9,28,12,tzinfo=timezone.utc))
        self.assertEqual(frame.index[-1].date().isoformat(),'2026-09-24')

    def test_daily_candles_with_close_outside_range_are_not_silently_repaired(self):
        raw=daily();raw.iloc[-1,raw.columns.get_loc('Close')]=10000
        frame,audit=gm.prepare_prices(raw,GOLD,NOW)
        self.assertEqual(frame.index[-1].date().isoformat(),'2026-09-24')
        self.assertEqual(audit['invalid_dates'],['2026-09-25'])

    def test_last_two_sessions_never_generate_confirmed_pivots(self):
        raw=daily();raw.iloc[-1,raw.columns.get_loc('High')]=10000
        events=gm.pivots(raw)
        cutoff=raw.index[-3].date().isoformat()
        self.assertTrue(all(p['pivot_date']<=cutoff and p['confirmed_on']<=raw.index[-1].date().isoformat() for ps in events.values() for p in ps))

    def test_delayed_or_invalid_data_overrides_price_structure_signal(self):
        raw=daily(end='2026-09-24')
        audit={'invalid_dates':[],'partial_dates':[],'hour_counts':{}}
        self.assertEqual(gm.scan(GOLD,raw,audit,NOW)['status'],'CAUTION')
        audit['invalid_dates']=['2026-09-23']
        row=gm.scan(GOLD,daily(),audit,NOW)
        self.assertEqual(row['status'],'CAUTION');self.assertEqual(row['data_state'],'limited')

    def test_price_only_fx_analysis_does_not_require_volume_or_fifty_rupee_price(self):
        frame,audit=gm.prepare_prices(hourly(),FX,NOW)
        row=gm.scan(FX,frame,audit,NOW)
        self.assertEqual(row['data_state'],'ready')
        self.assertTrue(all(b['volume'] is None and b['volume_average20'] is None for b in row['chart']))
        self.assertIsNone(row['entry_plan'])
        self.assertLess(row['close'],50)

    def test_failed_refresh_preserves_dates_and_candles_without_mutating_previous(self):
        previous=gm.scan(GOLD,daily(),{'invalid_dates':[],'partial_dates':[],'hour_counts':{}},NOW)
        frozen=deepcopy(previous)
        later=NOW+timedelta(days=3)
        row=gm.unavailable(GOLD,previous,later,'Provider unavailable')
        self.assertEqual(row['chart'],previous['chart'])
        self.assertEqual(row['data_date'],previous['data_date'])
        self.assertEqual(row['retrieved_at'],previous['retrieved_at'])
        self.assertEqual(row['status'],'CAUTION');self.assertEqual(row['data_state'],'cached')
        self.assertEqual(previous,frozen)

    def test_network_failure_preserves_last_good_snapshot(self):
        previous=gm.scan(GOLD,daily(),{'invalid_dates':[],'partial_dates':[],'hour_counts':{}},NOW)
        with tempfile.TemporaryDirectory() as directory,patch.object(gm.yf,'Ticker',side_effect=RuntimeError('temporary failure')):
            row=gm.refresh_one(GOLD,previous,NOW,Path(directory))
            self.assertEqual(row['data_state'],'cached');self.assertEqual(row['chart'],previous['chart'])

    def test_publishing_cannot_touch_stock_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ['docs/hhhl_scan.json','public/data/hhhl_scan.json','data/hhhl_prices/STOCK.csv']:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('original')
            gm.write_snapshot(root,{'rows':[]})
            for name in ['docs/hhhl_scan.json','public/data/hhhl_scan.json','data/hhhl_prices/STOCK.csv']:
                self.assertEqual((root/name).read_text(),'original')

if __name__=='__main__':unittest.main()
