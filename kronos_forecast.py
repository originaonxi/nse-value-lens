"""
kronos_forecast.py — Daily Kronos fan-chart forecasts for NSE Value Lens.

Loads Kronos-small (NeoQuasar/Kronos-small, 24.7M params, CPU-only),
runs stochastic inference for Nifty 50 + all HHHL scan rows,
writes docs/kronos_forecast.json with genuine per-symbol provenance.

PREDICTED-CANDLE OHLC NOTE (empirically measured 2026-10-22):
  10 NSEI paths (61s incl. model load): ALL paths have raw OHLC envelope
  violations (46/240 candles; e.g. open 23155.89 < low 23180.64).
  Paths are rejected ONLY when any price is non-finite or non-positive.
  OHLC envelope violations are tallied in 'ohlc_envelope_violations' but
  NEVER cause path rejection.  Output 'paths' field is close-only [{d, c}].
  Historical candles ('history') are real validated data and keep full OHLC.

Batching: predict_batch() called with --batch-size copies of the same
series (sample_count=1 each) for independent stochastic paths.
sample_count>1 averages internally — never use it here.

Usage:
    python kronos_forecast.py                            # all HHHL rows, 100 paths
    python kronos_forecast.py --offline                  # skip fresh symbols
    python kronos_forecast.py --symbols NSEI --samples 10 # smoke run
    python kronos_forecast.py --max-stocks 3 --samples 2  # quick test
    python kronos_forecast.py --shard-index 0 --shard-count 20  # CI shard 0/20
    python kronos_forecast.py --output /tmp/kf.json      # custom output
"""
import sys, json, argparse, hashlib, os, warnings, math
from pathlib import Path
from datetime import date, timedelta

import numpy as np
import pandas as pd
import torch

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from kronos_model.kronos import KronosTokenizer, Kronos, KronosPredictor  # noqa: E402

TOKENIZER_ID  = 'NeoQuasar/Kronos-Tokenizer-base'
MODEL_ID      = 'NeoQuasar/Kronos-small'
# Pinned HuggingFace revisions (glob-verified locally 2026-10-22)
MODEL_REVISION     = '901c26c1332695a2a8f243eb2f37243a37bea320'
TOKENIZER_REVISION = '0e0117387f39004a9016484a186a908917e22426'

MIN_LOOKBACK    = 30      # minimum bars to attempt inference
MAX_CONTEXT     = 512     # kronos-small context window (candles)
LOOKBACK        = 120     # daily bars fed to model (~6 months)
PRED_LEN        = 24      # trading days to predict (~1 month)
DEFAULT_SAMPLES = 100     # CLI default; workflow daily uses 10 via --samples arg
DEFAULT_BATCH   = 10      # batch-size for predict_batch (sample_count=1 per call)
DEFAULT_THREADS = 2       # conservative — avoids OMP oversubscription on CI

OUT_DEFAULT    = ROOT / 'docs' / 'kronos_forecast.json'
NSEI_CSV       = ROOT / 'data' / 'hhhl_prices' / 'NSEI.csv'
HHHL_JSON      = ROOT / 'docs' / 'hhhl_scan.json'
PRICE_DIR      = ROOT / 'data' / 'hhhl_prices'
CALENDAR_PATH  = ROOT / 'data' / 'hhhl_calendar.json'

PROVENANCE_KIND = 'kronos-neural'
SCRIPT_VERSION  = '3'   # bumped: close-path output, pinned revisions, shard support


# ── NSE Holiday calendar ───────────────────────────────────────────────────────

_NSE_HOLIDAYS:    set[str] = set()
_CALENDAR_LOADED: bool     = False


def _load_calendar() -> None:
    global _NSE_HOLIDAYS, _CALENDAR_LOADED
    if _CALENDAR_LOADED:
        return
    _CALENDAR_LOADED = True
    if CALENDAR_PATH.exists():
        try:
            cal = json.loads(CALENDAR_PATH.read_text(encoding='utf-8'))
            _NSE_HOLIDAYS = set(cal.get('holidays', []))
            print(f'[Kronos] Holiday calendar: {len(_NSE_HOLIDAYS)} holidays')
        except Exception as exc:
            print(f'[Kronos] WARNING: calendar load failed: {exc}')
    else:
        print(f'[Kronos] WARNING: {CALENDAR_PATH} not found — weekday-only future dates')


# ── Helpers ────────────────────────────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    """Return hex SHA-256 of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_atomic(path: Path, obj: dict) -> None:
    """Write JSON atomically via tmp-file + rename (same filesystem)."""
    tmp = path.with_suffix('.tmp.json')
    tmp.write_text(
        json.dumps(obj, separators=(',', ':'), allow_nan=False, ensure_ascii=False),
        encoding='utf-8',
    )
    tmp.replace(path)


def build_config(args) -> dict:
    """Canonical config dict embedded in every entry for freshness checking."""
    return {
        'lookback':           LOOKBACK,
        'pred_len':           PRED_LEN,
        'n_samples':          args.samples,
        'batch_size':         args.batch_size,
        'version':            SCRIPT_VERSION,
        'model_revision':     MODEL_REVISION,
        'tokenizer_revision': TOKENIZER_REVISION,
    }


def entry_is_fresh(entry: dict, csv_sha: str, cfg: dict) -> bool:
    """
    True only when the stored entry has genuine neural provenance, matches
    the current input SHA-256, matches model identity (incl. pinned revisions),
    and contains exactly the expected number of valid close-only paths.

    Rejects:
      - pending / mock / heuristic / error entries
      - wrong model, revision, or script version
      - wrong or missing input SHA-256
      - missing data_as_of
      - fewer or more paths than requested
      - paths with wrong length, missing 'd'/'c' keys
      - paths in old OHLC format (have 'o' key — pre-v3 schema)
      - non-finite or non-positive close values in any path candle
      - mismatched config (lookback, pred_len, n_samples, version, revisions)
    """
    prov = entry.get('provenance', {})
    if prov.get('kind') != PROVENANCE_KIND:
        return False
    if prov.get('model') != MODEL_ID:
        return False
    if prov.get('model_revision') != MODEL_REVISION:
        return False
    if prov.get('tokenizer_revision') != TOKENIZER_REVISION:
        return False
    # Script version compared against cfg so tests can use alternate versions
    if prov.get('script') != cfg.get('version'):
        return False
    if entry.get('input_sha256') != csv_sha:
        return False
    if not entry.get('data_as_of'):
        return False

    paths      = entry.get('paths', [])
    expected_n  = cfg['n_samples']
    expected_pl = cfg['pred_len']
    if len(paths) != expected_n:
        return False

    for path in paths:
        if len(path) != expected_pl:
            return False
        for candle in path:
            # Close-path format: must have 'd' and 'c', must NOT have 'o'/'h'/'l'
            if 'd' not in candle or 'c' not in candle:
                return False
            if 'o' in candle or 'h' in candle or 'l' in candle:
                return False  # old OHLC format (pre-v3)
            try:
                c = float(candle['c'])
                if not (np.isfinite(c) and c > 0):
                    return False
            except (TypeError, ValueError):
                return False

    ec = entry.get('config', {})
    return (
        ec.get('lookback')           == cfg['lookback']                and
        ec.get('pred_len')           == cfg['pred_len']                and
        ec.get('n_samples')          == cfg['n_samples']               and
        ec.get('version')            == cfg['version']                 and
        ec.get('model_revision')     == cfg.get('model_revision')      and
        ec.get('tokenizer_revision') == cfg.get('tokenizer_revision')
    )


# ── Date helpers ─────────────────────────────────────────────────────────────

def next_trading_dates(last_date, n: int) -> pd.DatetimeIndex:
    """Return n NSE trading dates after last_date.

    Skips weekends and dates in data/hhhl_calendar.json (verified NSE holidays
    for the current year).  Future dates beyond the calendar year are
    weekday-only — no holiday adjustment beyond the calendar's coverage.
    """
    _load_calendar()
    dates, d = [], pd.Timestamp(last_date) + timedelta(days=1)
    while len(dates) < n:
        if d.weekday() < 5 and str(d.date()) not in _NSE_HOLIDAYS:
            dates.append(d)
        d += timedelta(days=1)
    return pd.DatetimeIndex(dates)


# ── Data loading ──────────────────────────────────────────────────────────────

def load_ohlcv(csv_path: Path) -> pd.DataFrame:
    """Load and strictly validate OHLCV from CSV.

    Drops rows where any OHLC value is:
      - non-finite (NaN, inf, -inf) or non-positive (<= 0)
      - OHLC-envelope invalid:
          high < open   |  high < close
          low  > open   |  low  > close
          high < low

    Returns an empty DataFrame when the file has no usable rows.
    """
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    df.columns = [c.strip().lower() for c in df.columns]
    required = ['open', 'high', 'low', 'close']
    if not all(c in df.columns for c in required):
        return pd.DataFrame()
    if 'volume' not in df.columns:
        df['volume'] = 0.0
    df = df[required + ['volume']].dropna()
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    if df.empty:
        return df

    ohlc = df[required].values.astype(float)
    finite_pos = np.isfinite(ohlc).all(axis=1) & (ohlc > 0).all(axis=1)
    envelope = (
        (ohlc[:, 1] >= ohlc[:, 0]) &   # high >= open
        (ohlc[:, 1] >= ohlc[:, 3]) &   # high >= close
        (ohlc[:, 2] <= ohlc[:, 0]) &   # low  <= open
        (ohlc[:, 2] <= ohlc[:, 3]) &   # low  <= close
        (ohlc[:, 1] >= ohlc[:, 2])     # high >= low
    )
    valid = finite_pos & envelope
    n_bad = int((~valid).sum())
    if n_bad:
        print(f'  [DATA] dropped {n_bad} invalid OHLC input row(s) from {csv_path.name}')
    return df[valid]


# ── Model loading ────────────────────────────────────────────────────────────

def load_predictor() -> KronosPredictor:
    print(f'[Kronos] Loading tokenizer: {TOKENIZER_ID} @ {TOKENIZER_REVISION[:8]}')
    try:
        tokenizer = KronosTokenizer.from_pretrained(
            TOKENIZER_ID, revision=TOKENIZER_REVISION,
        )
    except Exception as e:
        sys.exit(f'[Kronos] UNAVAILABLE: cannot load tokenizer {TOKENIZER_ID}: {e}')
    print(f'[Kronos] Loading model: {MODEL_ID} @ {MODEL_REVISION[:8]}')
    try:
        model = Kronos.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    except Exception as e:
        sys.exit(f'[Kronos] UNAVAILABLE: cannot load model {MODEL_ID}: {e}')
    predictor = KronosPredictor(model, tokenizer, device='cpu', max_context=MAX_CONTEXT)
    print('[Kronos] Kronos-small ready on CPU.')
    return predictor


# ── Kronos inference ──────────────────────────────────────────────────────────

def forecast_symbol(
    predictor: KronosPredictor,
    df: pd.DataFrame,
    symbol: str,
    n_samples: int,
    batch_size: int,
    pred_len: int = PRED_LEN,
    lookback: int = LOOKBACK,
    temperature: float = 1.0,
    top_p: float = 0.9,
) -> dict | None:
    """
    Run n_samples independent Kronos fan paths for one symbol.

    Close-path output: 'paths' is [[{d, c}, ...], ...] — close only.
    History is full OHLC (real validated data for chart context).

    Paths are REJECTED only when any predicted price is non-finite or
    non-positive.  OHLC envelope violations (empirically present in ALL
    benchmark paths) are counted in 'ohlc_envelope_violations' but NEVER
    cause rejection.

    Returns a result dict, or None when no paths survive validation.
    """
    actual_lookback = min(lookback, len(df))
    if actual_lookback < MIN_LOOKBACK:
        print(f'  [SKIP] {symbol}: only {len(df)} rows (need {MIN_LOOKBACK} minimum)')
        return None
    if actual_lookback < lookback:
        print(f'  [NOTE] {symbol}: {actual_lookback} bars available '
              f'(requested {lookback}); running with actual context')

    hist       = df.iloc[-actual_lookback:].copy()
    x_ts       = pd.Series(hist.index, name='timestamps')
    fut_idx    = next_trading_dates(hist.index[-1], pred_len)
    y_ts       = pd.Series(fut_idx, name='timestamps')
    data_as_of = str(hist.index[-1].date())

    paths:                list[list[dict]] = []   # close-only [{d, c}]
    total_ohlc_violations: int             = 0
    rejected:              int             = 0    # paths rejected (non-finite/non-positive)
    total_attempted:       int             = 0    # circuit-breaker: total paths extracted
    failed:                int             = 0    # consecutive batch errors
    remaining:             int             = n_samples

    # Circuit breaker: if we've extracted 3× n_samples without enough valid paths,
    # the model is consistently producing unusable output — give up.
    while remaining > 0 and total_attempted < n_samples * 3:
        bs = min(batch_size, remaining)
        try:
            preds_list = predictor.predict_batch(
                df_list=[hist] * bs,
                x_timestamp_list=[x_ts] * bs,
                y_timestamp_list=[y_ts] * bs,
                pred_len=pred_len,
                T=temperature,
                top_p=top_p,
                sample_count=1,
                verbose=False,
            )
            failed = 0   # reset consecutive counter on success
            total_attempted += len(preds_list)
            for pred in preds_list:
                # Extract raw OHLC array for this path
                try:
                    ohlc_arr = np.array(
                        [[float(pred['open'].iloc[j]),
                          float(pred['high'].iloc[j]),
                          float(pred['low'].iloc[j]),
                          float(pred['close'].iloc[j])]
                         for j in range(pred_len)],
                        dtype=float,
                    )
                except (KeyError, IndexError, ValueError) as exc:
                    rejected += 1
                    print(f'  [REJECT] {symbol}: extraction error: {exc}')
                    continue

                # Reject path if any value is non-finite or non-positive
                if not (np.isfinite(ohlc_arr).all() and (ohlc_arr > 0).all()):
                    rejected += 1
                    n_bad = int((~np.isfinite(ohlc_arr) | (ohlc_arr <= 0)).sum())
                    print(f'  [REJECT] {symbol}: {n_bad} non-finite/non-positive '
                          f'value(s) in path — discarded')
                    continue

                # Count OHLC envelope violations — never reject for these
                o, h, l, c = (ohlc_arr[:, 0], ohlc_arr[:, 1],
                               ohlc_arr[:, 2], ohlc_arr[:, 3])
                viol = int(
                    ((h < np.maximum(o, c)) |
                     (l > np.minimum(o, c)) |
                     (h < l)).sum()
                )
                total_ohlc_violations += viol

                # Store close-only path
                paths.append([
                    {'d': str(fut_idx[j].date()), 'c': round(float(ohlc_arr[j, 3]), 2)}
                    for j in range(pred_len)
                ])
                remaining -= 1

        except Exception as exc:
            failed += 1
            print(f'  [ERR] {symbol} batch error ({failed}/3): {exc}')
            if failed >= 3:
                print(f'  [FAIL] {symbol}: giving up after {failed} consecutive errors')
                break

    if not paths:
        return None

    # Last 40 bars of history — real validated data, full OHLC for chart context
    ctx     = df.iloc[-40:]
    history = [
        {
            'd': str(ctx.index[i].date()),
            'o': round(float(ctx['open'].iloc[i]),  2),
            'h': round(float(ctx['high'].iloc[i]),  2),
            'l': round(float(ctx['low'].iloc[i]),   2),
            'c': round(float(ctx['close'].iloc[i]), 2),
        }
        for i in range(len(ctx))
    ]

    # Descriptive stats on final-close distribution — no regime labelling
    last_close = float(df['close'].iloc[-1])
    final_cls  = [p[-1]['c'] for p in paths]
    denom      = abs(last_close) + 1e-6

    pct_above  = round(sum(1 for c in final_cls if c > last_close) / len(final_cls), 4)
    spread_pct = round(float(np.std(final_cls))            / denom * 100, 4)
    median_ret = round(float(np.median(final_cls)          - last_close) / denom * 100, 4)
    mean_ret   = round(float(np.mean(final_cls)            - last_close) / denom * 100, 4)
    p25_ret    = round(float(np.percentile(final_cls, 25)  - last_close) / denom * 100, 4)
    p75_ret    = round(float(np.percentile(final_cls, 75)  - last_close) / denom * 100, 4)

    n_good = len(paths)
    print(f'  {symbol}: {n_good}/{n_samples} paths | rejected={rejected} '
          f'ohlc_violations={total_ohlc_violations} | '
          f'pct_above={pct_above:.0%} spread={spread_pct:.1f}% median={median_ret:+.1f}%')

    return {
        'data_as_of':               data_as_of,
        'actual_lookback':          actual_lookback,
        'last_close':               round(last_close, 2),
        'history':                  history,
        'paths':                    paths,
        'paths_requested':          n_samples,
        'paths_produced':           n_good,
        'paths_rejected':           rejected,
        'ohlc_envelope_violations': total_ohlc_violations,
        'pct_above':                pct_above,
        'spread_pct':               spread_pct,
        'median_ret':               median_ret,
        'mean_ret':                 mean_ret,
        'p25_ret':                  p25_ret,
        'p75_ret':                  p75_ret,
    }


# ── Arg validators ─────────────────────────────────────────────────────────────

def _positive_int(val: str) -> int:
    n = int(val)
    if n <= 0:
        raise argparse.ArgumentTypeError(f'{val!r} must be a positive integer (got {n})')
    return n


def _nonneg_int(val: str) -> int:
    n = int(val)
    if n < 0:
        raise argparse.ArgumentTypeError(f'{val!r} must be >= 0 (got {n})')
    return n


# ── Checkpoint writer ──────────────────────────────────────────────────────────

def _write_checkpoint(
    out_path: Path,
    cfg: dict,
    results: dict,
    errors: dict,
    stale_syms: set,
    expected_count: int,
    n_samples: int,
) -> None:
    """Atomic checkpoint — call after every symbol; uploaded even on failure."""
    actual_coverage = sum(
        1 for r in results.values()
        if r.get('provenance', {}).get('kind') == PROVENANCE_KIND
        and not r.get('input_stale')
    )
    doc = {
        'as_of':           str(date.today()),
        'model':           MODEL_ID,
        'model_revision':  MODEL_REVISION,
        'lookback':        LOOKBACK,
        'pred_len':        PRED_LEN,
        'n_paths':         n_samples,
        'config':          cfg,
        'provenance':      {'kind': PROVENANCE_KIND},
        'expected_count':  expected_count,
        'actual_coverage': actual_coverage,
        'error_count':     len(errors),
        'stale_count':     len(stale_syms),
        'errors':          errors,
        'symbols':         results,
    }
    try:
        write_atomic(out_path, doc)
        print(f'  [CKPT] {len(results)} symbol(s) | '
              f'coverage={actual_coverage} → {out_path.name}')
    except Exception as exc:
        print(f'  [CKPT ERROR] {exc}', file=sys.stderr)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument('--samples',     type=_positive_int, default=DEFAULT_SAMPLES,
                    help=f'Stochastic paths per symbol (default {DEFAULT_SAMPLES})')
    ap.add_argument('--batch-size',  type=_positive_int, default=DEFAULT_BATCH,
                    help=f'Batch size per predict_batch call (default {DEFAULT_BATCH})')
    ap.add_argument('--max-stocks',  type=_nonneg_int,   default=0,
                    help='Max HHHL scan rows; 0 = all rows (default 0)')
    ap.add_argument('--symbols',     type=str,           default='',
                    help='Comma-separated symbols, overrides HHHL scan (e.g. NSEI,TCS)')
    ap.add_argument('--output',      type=Path,          default=OUT_DEFAULT,
                    help=f'Output JSON path (default {OUT_DEFAULT})')
    ap.add_argument('--threads',     type=_positive_int,
                    default=int(os.environ.get('OMP_NUM_THREADS', DEFAULT_THREADS)),
                    help=f'PyTorch intra-op CPU threads (default {DEFAULT_THREADS})')
    ap.add_argument('--offline',     action='store_true',
                    help='Skip symbols already fresh (matching SHA, config, revisions)')
    ap.add_argument('--shard-index', type=_nonneg_int,   default=0,
                    help='0-based shard index for parallel GitHub matrix (default 0)')
    ap.add_argument('--shard-count', type=_positive_int, default=1,
                    help='Total shards; 1 = no sharding (default 1)')
    args = ap.parse_args()

    if args.shard_index >= args.shard_count:
        ap.error(
            f'--shard-index {args.shard_index} must be < '
            f'--shard-count {args.shard_count}'
        )

    OUT = args.output
    cfg = build_config(args)

    # Write a minimal stub immediately so something is always uploadable even
    # if the process crashes before the first per-symbol checkpoint.
    try:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(OUT, {
            'as_of': str(date.today()), 'error': 'shard in progress',
            'expected_count': 0, 'actual_coverage': 0,
            'symbols': {}, 'errors': {},
        })
    except Exception:
        pass

    # ── CPU thread cap ────────────────────────────────────────────────────────
    torch.set_num_threads(args.threads)
    try:
        torch.set_num_interop_threads(max(1, args.threads // 2))
    except RuntimeError:
        pass   # already set (e.g. re-entrant call in tests)
    print(f'[Kronos] CPU threads: {args.threads} intra, '
          f'{max(1, args.threads // 2)} inter')
    print(f'[Kronos] Model: {MODEL_ID} @ {MODEL_REVISION[:8]}')
    print(f'[Kronos] Script version: {SCRIPT_VERSION}')

    # ── Build ordered symbol queue ─────────────────────────────────────────
    explicit_syms = [s.strip() for s in args.symbols.split(',') if s.strip()]
    symbol_queue: list[tuple[str, Path, dict]] = []
    scan_as_of: str = ''

    if explicit_syms:
        for sym in explicit_syms:
            csv_p = NSEI_CSV if sym == 'NSEI' else PRICE_DIR / f'{sym}.NS.csv'
            meta  = {'name': 'Nifty 50'} if sym == 'NSEI' else {'name': sym}
            symbol_queue.append((sym, Path(csv_p), meta))
    else:
        symbol_queue.append(('NSEI', NSEI_CSV, {'name': 'Nifty 50'}))
        if HHHL_JSON.exists():
            scan      = json.loads(HHHL_JSON.read_text(encoding='utf-8'))
            scan_as_of = scan.get('as_of', '')
            rows      = scan.get('rows', [])
            if args.max_stocks > 0:
                rows = rows[: args.max_stocks]
            for row in rows:
                sym = row.get('symbol', '').strip()
                if not sym:
                    continue
                csv_p = PRICE_DIR / f'{sym}.NS.csv'
                meta  = {
                    'name':   row.get('name', sym),
                    'status': row.get('status', ''),
                }
                symbol_queue.append((sym, Path(csv_p), meta))
        else:
            print(f'[Kronos] WARNING: {HHHL_JSON} not found — only NSEI will run')

    total_expected = len(symbol_queue)   # whole-universe count (before sharding)

    # ── Apply sharding (even distribution) ────────────────────────────────
    if args.shard_count > 1:
        n     = len(symbol_queue)
        base  = n // args.shard_count
        extra = n % args.shard_count
        start = args.shard_index * base + min(args.shard_index, extra)
        count = base + (1 if args.shard_index < extra else 0)
        symbol_queue = symbol_queue[start: start + count]
        print(f'[Kronos] Shard {args.shard_index}/{args.shard_count}: '
              f'{len(symbol_queue)} of {total_expected} symbols '
              f'(symbols {start}–{start + len(symbol_queue) - 1})')
    shard_expected = len(symbol_queue)

    # ── Load existing checkpoint for offline resume ────────────────────────
    existing: dict[str, dict] = {}
    if args.offline and OUT.exists():
        try:
            doc      = json.loads(OUT.read_text(encoding='utf-8'))
            existing = doc.get('symbols', {})
        except Exception as exc:
            print(f'[Kronos] WARNING: could not parse existing output: {exc}')

    # ── Categorise symbols: fresh / unavailable / todo ────────────────────
    results:       dict[str, dict] = {}
    errors:        dict[str, str]  = {}
    stale_syms:    set[str]        = set()
    verified_fresh: set[str]       = set()
    todo:          list[tuple]     = []

    for sym, csv_path, meta in symbol_queue:
        if not csv_path.exists():
            reason = f'price CSV not found: {csv_path.name}'
            print(f'[Kronos] UNAVAILABLE: {sym} — {reason}')
            errors[sym]  = reason
            results[sym] = {
                **meta,
                'error':      reason,
                'provenance': {'kind': 'unavailable'},
                'config':     cfg,
            }
            continue
        if args.offline and sym in existing:
            try:
                if entry_is_fresh(existing[sym], sha256_file(csv_path), cfg):
                    verified_fresh.add(sym)
                    continue
            except Exception:
                pass   # hash failure or malformed entry → recompute
        todo.append((sym, csv_path, meta))

    if verified_fresh:
        results.update({sym: existing[sym] for sym in verified_fresh})
        print(f'[Kronos] Offline: {len(verified_fresh)} symbol(s) already fresh')

    print(f'[Kronos] Queue: {len(todo)} to run, '
          f'{len(verified_fresh)} fresh, {len(errors)} unavailable')

    # Write initial checkpoint with unavailables recorded
    _write_checkpoint(OUT, cfg, results, errors, stale_syms,
                      shard_expected, args.samples)

    # ── Load model (only if anything to do) ───────────────────────────────
    predictor = None
    if todo:
        predictor = load_predictor()

    # ── Inference loop ─────────────────────────────────────────────────────
    for sym, csv_path, meta in todo:
        print(f'\n[Kronos] {sym} ...')

        try:
            csv_sha = sha256_file(csv_path)
        except Exception as exc:
            reason = f'cannot hash {csv_path.name}: {exc}'
            print(f'  [ERR] {sym}: {reason}')
            errors[sym]  = reason
            results[sym] = {
                **meta, 'error': reason,
                'provenance': {'kind': 'error'}, 'config': cfg,
            }
            _write_checkpoint(OUT, cfg, results, errors, stale_syms,
                              shard_expected, args.samples)
            continue

        df = load_ohlcv(csv_path)
        if df.empty:
            reason = f'no valid OHLCV rows in {csv_path.name}'
            print(f'  [UNAVAILABLE] {sym}: {reason}')
            errors[sym]  = reason
            results[sym] = {
                **meta, 'error': reason,
                'provenance': {'kind': 'unavailable'}, 'config': cfg,
            }
            _write_checkpoint(OUT, cfg, results, errors, stale_syms,
                              shard_expected, args.samples)
            continue

        r = forecast_symbol(
            predictor, df, sym,
            n_samples=args.samples,
            batch_size=args.batch_size,
            pred_len=PRED_LEN,
            lookback=LOOKBACK,
        )
        if r is None:
            reason = 'inference returned no valid paths'
            print(f'  [UNAVAILABLE] {sym}: {reason}')
            errors[sym]  = reason
            results[sym] = {
                **meta, 'error': reason,
                'provenance': {'kind': 'error'}, 'config': cfg,
            }
            _write_checkpoint(OUT, cfg, results, errors, stale_syms,
                              shard_expected, args.samples)
            continue

        # Strict equality: data date must match scan date (not merely >=)
        input_stale = bool(scan_as_of and r.get('data_as_of', '') != scan_as_of)
        if input_stale:
            stale_syms.add(sym)
            print(f'  [STALE] {sym}: data_as_of={r["data_as_of"]!r} '
                  f'!= scan.as_of={scan_as_of!r}')

        results[sym] = {
            **meta,
            **r,
            'input_sha256': csv_sha,
            'input_stale':  input_stale,
            'stale_reason': (
                f'data_as_of {r["data_as_of"]!r} != scan_as_of {scan_as_of!r}'
                if input_stale else None
            ),
            'provenance': {
                'kind':               PROVENANCE_KIND,
                'model':              MODEL_ID,
                'model_revision':     MODEL_REVISION,
                'tokenizer_revision': TOKENIZER_REVISION,
                'script':             SCRIPT_VERSION,
            },
            'config': cfg,
        }

        _write_checkpoint(OUT, cfg, results, errors, stale_syms,
                          shard_expected, args.samples)

    # ── Final summary and exit code ────────────────────────────────────────
    actual_coverage = sum(
        1 for r in results.values()
        if r.get('provenance', {}).get('kind') == PROVENANCE_KIND
        and not r.get('input_stale')
    )
    _write_checkpoint(OUT, cfg, results, errors, stale_syms,
                      shard_expected, args.samples)

    print(f'\n[Kronos] Done — {len(results)}/{shard_expected} symbols | '
          f'coverage={actual_coverage} errors={len(errors)} '
          f'stale={len(stale_syms)} → {OUT}')

    if actual_coverage == 0:
        print('[Kronos] ERROR: no non-stale valid output produced',
              file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
