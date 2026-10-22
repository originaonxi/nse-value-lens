"""
tests/test_kronos_forecast.py — Unit tests for kronos_forecast.py (v3).

No model download required: torch and kronos_model are stubbed before import.
Run with: python -m unittest tests/test_kronos_forecast.py -v
"""
import copy, hashlib, json, sys, types, tempfile, unittest
from pathlib import Path
from unittest import mock

# ── Stub heavy dependencies before importing kronos_forecast ──────────────────

_torch = types.ModuleType('torch')
_torch.set_num_threads = lambda n: None
_torch.set_num_interop_threads = lambda n: None


class _FakeCtx:
    def __enter__(self): return self
    def __exit__(self, *a): return False


_torch.no_grad = lambda: _FakeCtx()
sys.modules.setdefault('torch', _torch)

for _m in ('kronos_model', 'kronos_model.kronos', 'kronos_model.module'):
    sys.modules.setdefault(_m, types.ModuleType(_m))

_km = sys.modules['kronos_model.kronos']
_km.KronosTokenizer  = mock.MagicMock()
_km.Kronos           = mock.MagicMock()
_km.KronosPredictor  = mock.MagicMock()

# Now safe to import
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import kronos_forecast as kf


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ohlcv_df(rows: int = 130, close: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range('2024-01-01', periods=rows, freq='B')
    return pd.DataFrame({
        'open':   np.full(rows, close - 1),
        'high':   np.full(rows, close + 1),
        'low':    np.full(rows, close - 2),
        'close':  np.full(rows, close),
        'volume': np.full(rows, 1000.0),
    }, index=idx)


def _make_mock_predictor(pred_len: int, close_val: float = 101.0,
                         bad_finite: bool = False, envelope_viol: bool = False):
    """Mock predictor returning DataFrames with configurable validity.

    bad_finite=True  → NaN open + negative close  → every path rejected
    envelope_viol=True → high < low (all positive/finite) → paths kept, violations counted
    """
    def fake_batch(df_list, x_timestamp_list, y_timestamp_list, pred_len, **kw):
        idx = pd.date_range('2025-06-01', periods=pred_len, freq='B')
        frames = []
        for _ in df_list:
            if bad_finite:
                # Non-finite open, non-positive close → must be rejected
                o = [float('nan')] * pred_len
                h = [101.] * pred_len
                l = [99.]  * pred_len
                c = [-1.]  * pred_len
            elif envelope_viol:
                # high(99) < low(102) — both positive+finite → path kept
                o = [100.] * pred_len
                h = [99.]  * pred_len
                l = [102.] * pred_len
                c = [close_val] * pred_len
            else:
                o = [close_val - 1] * pred_len
                h = [close_val + 1] * pred_len
                l = [close_val - 2] * pred_len
                c = [close_val]     * pred_len
            frames.append(pd.DataFrame({
                'open':   o, 'high': h, 'low': l, 'close': c,
                'volume': [0.] * pred_len, 'amount': [0.] * pred_len,
            }, index=idx))
        return frames

    p = mock.MagicMock()
    p.predict_batch.side_effect = fake_batch
    return p


def _fresh_entry(cfg: dict, csv_sha: str, n_paths: int = None,
                 first_close: float = 101.0) -> dict:
    """Return a minimal entry that passes entry_is_fresh (v3: close-path format)."""
    n  = n_paths if n_paths is not None else cfg['n_samples']
    pl = cfg['pred_len']
    # Close-only paths — no 'o', 'h', 'l' keys (pre-v3 OHLC format is rejected)
    path = [{'d': f'2025-01-{(i % 28) + 1:02d}', 'c': first_close}
            for i in range(pl)]
    return {
        'data_as_of':  '2025-10-20',
        'input_sha256': csv_sha,
        'provenance': {
            'kind':               kf.PROVENANCE_KIND,
            'model':              kf.MODEL_ID,
            'model_revision':     kf.MODEL_REVISION,
            'tokenizer_revision': kf.TOKENIZER_REVISION,
            'script':             kf.SCRIPT_VERSION,
        },
        'config': dict(cfg),
        'paths':  [list(path)] * n,
    }


# ── TestSha256File ─────────────────────────────────────────────────────────────

class TestSha256File(unittest.TestCase):
    def test_known_content(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f:
            f.write(b'hello world')
            p = Path(f.name)
        try:
            expected = hashlib.sha256(b'hello world').hexdigest()
            self.assertEqual(kf.sha256_file(p), expected)
        finally:
            p.unlink()

    def test_different_content_different_hash(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / 'a.bin'
            b = Path(d) / 'b.bin'
            a.write_bytes(b'aaa')
            b.write_bytes(b'bbb')
            self.assertNotEqual(kf.sha256_file(a), kf.sha256_file(b))


# ── TestEntryIsFresh ───────────────────────────────────────────────────────────

class TestEntryIsFresh(unittest.TestCase):
    CFG = {
        'lookback':           120,
        'pred_len':           24,
        'n_samples':          10,
        'version':            kf.SCRIPT_VERSION,      # '3'
        'model_revision':     kf.MODEL_REVISION,
        'tokenizer_revision': kf.TOKENIZER_REVISION,
    }
    SHA = 'abc123deadbeef'

    def _entry(self, **overrides) -> dict:
        """Deep-copy a fresh entry and apply overrides to top-level keys."""
        base = copy.deepcopy(_fresh_entry(self.CFG, self.SHA))
        for k, v in overrides.items():
            base[k] = v
        return base

    # ── passes ────────────────────────────────────────────────────────────

    def test_fresh_passes(self):
        self.assertTrue(kf.entry_is_fresh(self._entry(), self.SHA, self.CFG))

    # ── provenance failures ────────────────────────────────────────────────

    def test_wrong_provenance_kind(self):
        e = self._entry()
        e['provenance']['kind'] = 'heuristic'
        self.assertFalse(kf.entry_is_fresh(e, self.SHA, self.CFG))

    def test_missing_provenance(self):
        e = self._entry()
        del e['provenance']
        self.assertFalse(kf.entry_is_fresh(e, self.SHA, self.CFG))

    def test_wrong_model_id(self):
        e = self._entry()
        e['provenance']['model'] = 'some/other-model'
        self.assertFalse(kf.entry_is_fresh(e, self.SHA, self.CFG))

    def test_wrong_model_revision(self):
        e = self._entry()
        e['provenance']['model_revision'] = 'deadbeef' * 5
        self.assertFalse(kf.entry_is_fresh(e, self.SHA, self.CFG))

    def test_wrong_tokenizer_revision(self):
        e = self._entry()
        e['provenance']['tokenizer_revision'] = 'cafebabe' * 5
        self.assertFalse(kf.entry_is_fresh(e, self.SHA, self.CFG))

    def test_wrong_script_version_in_provenance(self):
        e = self._entry()
        e['provenance']['script'] = '1'
        self.assertFalse(kf.entry_is_fresh(e, self.SHA, self.CFG))

    # ── identity failures ─────────────────────────────────────────────────

    def test_wrong_sha256(self):
        self.assertFalse(kf.entry_is_fresh(self._entry(), 'different_sha', self.CFG))

    def test_missing_data_as_of(self):
        e = self._entry()
        del e['data_as_of']
        self.assertFalse(kf.entry_is_fresh(e, self.SHA, self.CFG))

    def test_empty_data_as_of(self):
        e = self._entry()
        e['data_as_of'] = ''
        self.assertFalse(kf.entry_is_fresh(e, self.SHA, self.CFG))

    # ── path-count failures ───────────────────────────────────────────────

    def test_wrong_n_samples_in_config(self):
        cfg = dict(self.CFG, n_samples=5)
        self.assertFalse(kf.entry_is_fresh(self._entry(), self.SHA, cfg))

    def test_partial_paths_count(self):
        e = _fresh_entry(self.CFG, self.SHA, n_paths=5)
        self.assertFalse(kf.entry_is_fresh(e, self.SHA, self.CFG))

    def test_empty_paths(self):
        e = self._entry()
        e['paths'] = []
        self.assertFalse(kf.entry_is_fresh(e, self.SHA, self.CFG))

    def test_wrong_path_length(self):
        e = self._entry()
        e['paths'][0] = e['paths'][0][:3]   # truncate one path
        self.assertFalse(kf.entry_is_fresh(e, self.SHA, self.CFG))

    # ── path-format failures ──────────────────────────────────────────────

    def test_missing_d_key(self):
        e = self._entry()
        del e['paths'][0][0]['d']
        self.assertFalse(kf.entry_is_fresh(e, self.SHA, self.CFG))

    def test_missing_c_key(self):
        e = self._entry()
        del e['paths'][0][0]['c']
        self.assertFalse(kf.entry_is_fresh(e, self.SHA, self.CFG))

    def test_old_ohlc_format_rejected(self):
        """Pre-v3 entries with 'o' key in paths must be rejected."""
        e = self._entry()
        e['paths'][0][0]['o'] = 99.0   # inject old-format field
        self.assertFalse(kf.entry_is_fresh(e, self.SHA, self.CFG))

    def test_zero_close_rejected(self):
        e = self._entry()
        e['paths'][0][0]['c'] = 0.0
        self.assertFalse(kf.entry_is_fresh(e, self.SHA, self.CFG))

    def test_negative_close_rejected(self):
        e = self._entry()
        e['paths'][0][0]['c'] = -5.0
        self.assertFalse(kf.entry_is_fresh(e, self.SHA, self.CFG))

    # ── config failures ───────────────────────────────────────────────────

    def test_wrong_lookback(self):
        cfg = dict(self.CFG, lookback=60)
        self.assertFalse(kf.entry_is_fresh(self._entry(), self.SHA, cfg))

    def test_wrong_version(self):
        cfg = dict(self.CFG, version='1')
        self.assertFalse(kf.entry_is_fresh(self._entry(), self.SHA, cfg))

    def test_wrong_model_revision_in_config(self):
        cfg = dict(self.CFG, model_revision='oldrevision')
        self.assertFalse(kf.entry_is_fresh(self._entry(), self.SHA, cfg))


# ── TestNextTradingDates ───────────────────────────────────────────────────────

class TestNextTradingDates(unittest.TestCase):
    def test_correct_count(self):
        dates = kf.next_trading_dates('2024-01-01', 24)
        self.assertEqual(len(dates), 24)

    def test_no_weekends(self):
        dates = kf.next_trading_dates('2024-10-18', 10)   # Friday
        for d in dates:
            self.assertLess(d.weekday(), 5, f'{d} is a weekend')

    def test_starts_after_last_date(self):
        dates = kf.next_trading_dates('2024-10-18', 1)
        self.assertGreater(dates[0], pd.Timestamp('2024-10-18'))

    def test_known_calendar_holiday_skipped(self):
        """2026-10-20 is in hhhl_calendar.json; must not appear in results."""
        cal_path = kf.CALENDAR_PATH
        if not cal_path.exists():
            self.skipTest('hhhl_calendar.json not found')
        import json as _json
        cal = _json.loads(cal_path.read_text())
        if '2026-10-20' not in cal.get('holidays', []):
            self.skipTest('2026-10-20 not in calendar')
        dates = kf.next_trading_dates('2026-10-19', 5)
        date_strs = [str(d.date()) for d in dates]
        self.assertNotIn('2026-10-20', date_strs)

    def test_injected_holiday_skipped(self):
        """Directly inject a holiday and confirm it is excluded."""
        orig_holidays = kf._NSE_HOLIDAYS.copy()
        orig_loaded   = kf._CALENDAR_LOADED
        try:
            kf._NSE_HOLIDAYS   = {'2024-01-03'}   # inject Wed 2024-01-03
            kf._CALENDAR_LOADED = True
            dates = kf.next_trading_dates('2024-01-01', 3)
            date_strs = [str(d.date()) for d in dates]
            self.assertNotIn('2024-01-03', date_strs)
            self.assertEqual(len(dates), 3)
        finally:
            kf._NSE_HOLIDAYS   = orig_holidays
            kf._CALENDAR_LOADED = orig_loaded


# ── TestLoadOhlcv ──────────────────────────────────────────────────────────────

class TestLoadOhlcv(unittest.TestCase):
    def _write_csv(self, content: str) -> Path:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv',
                                        delete=False, encoding='utf-8') as f:
            f.write(content)
            return Path(f.name)

    def test_basic_csv(self):
        p = self._write_csv(
            'Date,Open,High,Low,Close,Volume\n'
            '2024-01-01,100,102,98,101,10000\n'
            '2024-01-02,101,103,99,102,12000\n'
        )
        try:
            df = kf.load_ohlcv(p)
            self.assertFalse(df.empty)
            self.assertIn('close', df.columns)
            self.assertEqual(len(df), 2)
        finally:
            p.unlink()

    def test_volume_added_if_missing(self):
        p = self._write_csv(
            'Date,Open,High,Low,Close\n'
            '2024-01-01,100,102,98,101\n'
        )
        try:
            df = kf.load_ohlcv(p)
            self.assertIn('volume', df.columns)
            self.assertEqual(df['volume'].iloc[0], 0.0)
        finally:
            p.unlink()

    def test_missing_required_col_returns_empty(self):
        p = self._write_csv(
            'Date,Open,High,Low\n'
            '2024-01-01,100,102,98\n'   # missing Close
        )
        try:
            self.assertTrue(kf.load_ohlcv(p).empty)
        finally:
            p.unlink()

    def test_column_names_case_insensitive(self):
        p = self._write_csv(
            'date,OPEN,HIGH,LOW,CLOSE\n'
            '2024-01-01,100,102,98,101\n'
        )
        try:
            df = kf.load_ohlcv(p)
            self.assertFalse(df.empty)
            self.assertIn('close', df.columns)
        finally:
            p.unlink()

    def test_invalid_envelope_rows_dropped_keeps_valid(self):
        """Rows where high < low are invalid; valid rows are preserved."""
        p = self._write_csv(
            'Date,Open,High,Low,Close,Volume\n'
            '2024-01-01,100,102,98,101,1000\n'   # valid
            '2024-01-02,100,95,105,101,1000\n'   # high(95)<low(105) → invalid
            '2024-01-03,100,103,99,102,1000\n'   # valid
        )
        try:
            df = kf.load_ohlcv(p)
            self.assertEqual(len(df), 2)
            self.assertTrue((df['high'] >= df['low']).all())
        finally:
            p.unlink()

    def test_nonpositive_rows_dropped(self):
        """Rows with zero or negative OHLC values must be dropped."""
        p = self._write_csv(
            'Date,Open,High,Low,Close,Volume\n'
            '2024-01-01,100,102,98,101,1000\n'   # valid
            '2024-01-02,0,102,98,101,1000\n'     # open=0 → invalid
            '2024-01-03,100,102,98,-1,1000\n'    # close=-1 → invalid
        )
        try:
            df = kf.load_ohlcv(p)
            self.assertEqual(len(df), 1)
        finally:
            p.unlink()

    def test_high_lt_open_dropped(self):
        """Row where high < open is an envelope violation → dropped."""
        p = self._write_csv(
            'Date,Open,High,Low,Close,Volume\n'
            '2024-01-01,100,102,98,101,1000\n'   # valid
            '2024-01-02,105,102,98,101,1000\n'   # open(105)>high(102) → invalid
        )
        try:
            df = kf.load_ohlcv(p)
            self.assertEqual(len(df), 1)
            # Remaining row passes envelope
            self.assertTrue((df['high'] >= df['open']).all())
        finally:
            p.unlink()

    def test_all_invalid_returns_empty(self):
        p = self._write_csv(
            'Date,Open,High,Low,Close,Volume\n'
            '2024-01-01,105,102,98,101,1000\n'   # high<open → invalid
            '2024-01-02,100,95,105,101,1000\n'   # high<low → invalid
        )
        try:
            df = kf.load_ohlcv(p)
            self.assertTrue(df.empty)
        finally:
            p.unlink()


# ── TestWriteAtomic ────────────────────────────────────────────────────────────

class TestWriteAtomic(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'out.json'
            kf.write_atomic(p, {'key': 'value', 'n': 42})
            loaded = json.loads(p.read_text())
            self.assertEqual(loaded['key'], 'value')
            self.assertEqual(loaded['n'], 42)

    def test_no_tmp_file_left(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'out.json'
            kf.write_atomic(p, {'x': 1})
            self.assertFalse(p.with_suffix('.tmp.json').exists())

    def test_overwrites_existing(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'out.json'
            kf.write_atomic(p, {'v': 1})
            kf.write_atomic(p, {'v': 2})
            self.assertEqual(json.loads(p.read_text())['v'], 2)


# ── TestForecastSymbol ─────────────────────────────────────────────────────────

class TestForecastSymbol(unittest.TestCase):
    PRED_LEN = 5
    LOOKBACK  = 120

    def _run(self, df, n_samples=4, batch_size=2, close=100.0,
             bad_finite=False, envelope_viol=False):
        pred = _make_mock_predictor(
            self.PRED_LEN, close_val=close + 1,
            bad_finite=bad_finite, envelope_viol=envelope_viol,
        )
        return kf.forecast_symbol(
            pred, df, 'TEST',
            n_samples=n_samples,
            batch_size=batch_size,
            pred_len=self.PRED_LEN,
            lookback=self.LOOKBACK,
        )

    # ── basic behaviour ────────────────────────────────────────────────────

    def test_returns_none_if_below_min_lookback(self):
        df = _make_ohlcv_df(rows=kf.MIN_LOOKBACK - 1)
        self.assertIsNone(self._run(df))

    def test_runs_with_short_history(self):
        df = _make_ohlcv_df(rows=kf.MIN_LOOKBACK + 5)
        result = self._run(df)
        self.assertIsNotNone(result)
        self.assertEqual(result['actual_lookback'], kf.MIN_LOOKBACK + 5)

    def test_actual_lookback_capped_at_lookback(self):
        df = _make_ohlcv_df(rows=200)
        result = self._run(df)
        self.assertIsNotNone(result)
        self.assertEqual(result['actual_lookback'], self.LOOKBACK)

    def test_no_regime_field(self):
        df = _make_ohlcv_df(rows=130)
        result = self._run(df)
        self.assertNotIn('regime', result)

    def test_has_all_descriptive_stats(self):
        df = _make_ohlcv_df(rows=130)
        result = self._run(df)
        for field in ('pct_above', 'spread_pct', 'median_ret',
                      'mean_ret', 'p25_ret', 'p75_ret'):
            self.assertIn(field, result, f'missing field: {field}')

    def test_data_as_of_is_last_hist_bar(self):
        df = _make_ohlcv_df(rows=130)
        result = self._run(df)
        expected = str(df.iloc[-self.LOOKBACK:].index[-1].date())
        self.assertEqual(result['data_as_of'], expected)

    def test_correct_path_count(self):
        df = _make_ohlcv_df(rows=130)
        result = self._run(df, n_samples=6, batch_size=2)
        self.assertEqual(len(result['paths']), 6)
        self.assertEqual(result['paths_produced'], 6)
        self.assertEqual(result['paths_requested'], 6)
        self.assertEqual(result['paths_rejected'], 0)

    # ── output schema ─────────────────────────────────────────────────────

    def test_paths_are_close_only(self):
        """Paths must be [{d, c}] — no 'o', 'h', 'l' keys allowed."""
        df = _make_ohlcv_df(rows=130)
        result = self._run(df)
        self.assertIsNotNone(result)
        for candle in result['paths'][0]:
            self.assertIn('d',  candle, "'d' missing from path candle")
            self.assertIn('c',  candle, "'c' missing from path candle")
            self.assertNotIn('o', candle, "'o' must not appear in close-path")
            self.assertNotIn('h', candle, "'h' must not appear in close-path")
            self.assertNotIn('l', candle, "'l' must not appear in close-path")

    def test_path_length_equals_pred_len(self):
        df = _make_ohlcv_df(rows=130)
        result = self._run(df)
        for path in result['paths']:
            self.assertEqual(len(path), self.PRED_LEN)

    def test_history_has_full_ohlc_keys(self):
        """History is real validated data — keeps full OHLC for chart context."""
        df = _make_ohlcv_df(rows=130)
        result = self._run(df)
        self.assertIn('history', result)
        for bar in result['history']:
            for key in ('d', 'o', 'h', 'l', 'c'):
                self.assertIn(key, bar, f"history bar missing '{key}'")

    def test_history_context_bars(self):
        df = _make_ohlcv_df(rows=130)
        result = self._run(df)
        self.assertLessEqual(len(result['history']), 40)
        self.assertGreater(len(result['history']), 0)

    def test_output_fields_present(self):
        df = _make_ohlcv_df(rows=130)
        result = self._run(df)
        required = (
            'data_as_of', 'actual_lookback', 'last_close', 'history', 'paths',
            'paths_requested', 'paths_produced', 'paths_rejected',
            'ohlc_envelope_violations',
        )
        for field in required:
            self.assertIn(field, result, f'missing field: {field}')

    # ── validation behaviour ───────────────────────────────────────────────

    def test_nonfinite_path_rejected_returns_none(self):
        """Paths with non-finite/non-positive values are discarded.
        When ALL paths fail, forecast_symbol returns None."""
        df = _make_ohlcv_df(rows=130)
        result = self._run(df, bad_finite=True, n_samples=4)
        self.assertIsNone(result)

    def test_ohlc_violations_counted_paths_kept(self):
        """OHLC envelope violations are counted but never cause path rejection.
        Empirically: ALL benchmark paths had violations (46/240 candles)."""
        df = _make_ohlcv_df(rows=130)
        result = self._run(df, envelope_viol=True, n_samples=4)
        # Path must NOT be discarded
        self.assertIsNotNone(result)
        self.assertEqual(len(result['paths']), 4)
        self.assertEqual(result['paths_rejected'], 0,
                         'OHLC envelope violations must never cause rejection')
        # Violations must be counted
        self.assertGreater(result['ohlc_envelope_violations'], 0)

    def test_sample_count_always_one(self):
        """predict_batch must always be called with sample_count=1."""
        recorded = []

        def fake_batch(df_list, x_timestamp_list, y_timestamp_list, pred_len, **kw):
            recorded.append(kw.get('sample_count', 'MISSING'))
            idx = pd.date_range('2025-06-01', periods=pred_len, freq='B')
            return [
                pd.DataFrame({
                    'open':   [100.] * pred_len, 'high': [102.] * pred_len,
                    'low':    [98.]  * pred_len, 'close': [101.] * pred_len,
                    'volume': [0.]   * pred_len, 'amount': [0.] * pred_len,
                }, index=idx)
                for _ in df_list
            ]

        pred = mock.MagicMock()
        pred.predict_batch.side_effect = fake_batch
        df = _make_ohlcv_df(rows=130)
        kf.forecast_symbol(pred, df, 'TEST', n_samples=4, batch_size=2,
                           pred_len=self.PRED_LEN, lookback=self.LOOKBACK)
        for sc in recorded:
            self.assertEqual(sc, 1, 'sample_count must be 1 in all predict_batch calls')


# ── TestArgValidators ──────────────────────────────────────────────────────────

class TestArgValidators(unittest.TestCase):
    def test_positive_int_accepts_positive(self):
        self.assertEqual(kf._positive_int('1'), 1)
        self.assertEqual(kf._positive_int('100'), 100)

    def test_positive_int_rejects_zero(self):
        with self.assertRaises(Exception):
            kf._positive_int('0')

    def test_positive_int_rejects_negative(self):
        with self.assertRaises(Exception):
            kf._positive_int('-5')

    def test_nonneg_int_accepts_zero(self):
        self.assertEqual(kf._nonneg_int('0'), 0)

    def test_nonneg_int_accepts_positive(self):
        self.assertEqual(kf._nonneg_int('7'), 7)

    def test_nonneg_int_rejects_negative(self):
        with self.assertRaises(Exception):
            kf._nonneg_int('-1')


# ── TestArgDefaults ────────────────────────────────────────────────────────────

class TestArgDefaults(unittest.TestCase):
    def test_samples_default(self):
        self.assertEqual(kf.DEFAULT_SAMPLES, 100)

    def test_batch_default(self):
        self.assertEqual(kf.DEFAULT_BATCH, 10)

    def test_threads_default(self):
        self.assertEqual(kf.DEFAULT_THREADS, 2)

    def test_provenance_kind(self):
        self.assertEqual(kf.PROVENANCE_KIND, 'kronos-neural')

    def test_model_id(self):
        self.assertEqual(kf.MODEL_ID, 'NeoQuasar/Kronos-small')

    def test_script_version_string(self):
        self.assertIsInstance(kf.SCRIPT_VERSION, str)

    def test_script_version_three(self):
        """Version must be '3' for close-path / pinned-revision schema."""
        self.assertEqual(kf.SCRIPT_VERSION, '3')

    def test_max_context(self):
        self.assertEqual(kf.MAX_CONTEXT, 512)

    def test_min_lookback_positive(self):
        self.assertGreater(kf.MIN_LOOKBACK, 0)
        self.assertLess(kf.MIN_LOOKBACK, kf.LOOKBACK)

    def test_model_revision_set(self):
        self.assertIsInstance(kf.MODEL_REVISION, str)
        self.assertGreater(len(kf.MODEL_REVISION), 0)

    def test_tokenizer_revision_set(self):
        self.assertIsInstance(kf.TOKENIZER_REVISION, str)
        self.assertGreater(len(kf.TOKENIZER_REVISION), 0)

    def test_model_revision_pinned(self):
        """Pinned revision must match the verified-installed snapshot."""
        self.assertEqual(kf.MODEL_REVISION,
                         '901c26c1332695a2a8f243eb2f37243a37bea320')

    def test_tokenizer_revision_pinned(self):
        """Pinned revision must match the verified-installed snapshot."""
        self.assertEqual(kf.TOKENIZER_REVISION,
                         '0e0117387f39004a9016484a186a908917e22426')


if __name__ == '__main__':
    unittest.main(verbosity=2)
