"""
kronos_forecast.py — Daily Kronos fan-chart forecasts for NSE Value Lens.

Loads Kronos-small (NeoQuasar/Kronos-small, 24.7M params, CPU-only),
runs 100-sample stochastic inference for Nifty 50 + top HHHL stocks,
writes docs/kronos_forecast.json.

Usage:
    python kronos_forecast.py
    python kronos_forecast.py --offline   # skip if output already today's date
"""
import sys, json, argparse, warnings
from pathlib import Path
from datetime import date, timedelta

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))          # kronos_model/ must be a sibling directory

from kronos_model.kronos import KronosTokenizer, Kronos, KronosPredictor  # noqa: E402

TOKENIZER_ID = 'NeoQuasar/Kronos-Tokenizer-base'
MODEL_ID     = 'NeoQuasar/Kronos-small'
MAX_CONTEXT  = 512    # kronos-small context window (candles)
LOOKBACK     = 120    # daily bars fed to model (~6 months)
PRED_LEN     = 24     # trading days to predict (~1 month)
N_SAMPLES    = 100    # fan paths (100 independent samples)
TEMPERATURE  = 1.0    # >0 enables stochastic diversity between paths
TOP_P        = 0.9    # nucleus sampling threshold
MAX_STOCKS   = 24     # top HHHL stocks (plus NSEI = 25 total)

OUT        = ROOT / 'docs' / 'kronos_forecast.json'
NSEI_CSV   = ROOT / 'data' / 'hhhl_prices' / 'NSEI.csv'
HHHL_JSON  = ROOT / 'docs' / 'hhhl_scan.json'
PRICE_DIR  = ROOT / 'data' / 'hhhl_prices'


# ── Model loading ───────────────────────────────────────────────────────────
def load_predictor() -> KronosPredictor:
    print('[Kronos] Loading tokenizer:', TOKENIZER_ID)
    tokenizer = KronosTokenizer.from_pretrained(TOKENIZER_ID)
    print('[Kronos] Loading model:', MODEL_ID)
    model = Kronos.from_pretrained(MODEL_ID)
    predictor = KronosPredictor(model, tokenizer, device='cpu', max_context=MAX_CONTEXT)
    print('[Kronos] Kronos-small ready on CPU.')
    return predictor


# ── Date helpers ─────────────────────────────────────────────────────────────
def next_trading_dates(last_date, n: int) -> pd.DatetimeIndex:
    """Return n weekday dates after last_date (no NSE holiday calendar applied)."""
    dates, d = [], pd.Timestamp(last_date) + timedelta(days=1)
    while len(dates) < n:
        if d.weekday() < 5:      # Mon-Fri
            dates.append(d)
        d += timedelta(days=1)
    return pd.DatetimeIndex(dates)


# ── Data loading ──────────────────────────────────────────────────────────────
def load_ohlcv(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    df.columns = [c.strip().lower() for c in df.columns]
    required = ['open', 'high', 'low', 'close']
    if not all(c in df.columns for c in required):
        return pd.DataFrame()
    if 'volume' not in df.columns:
        df['volume'] = 0.0
    df = df[required + ['volume']].dropna()
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


# ── Kronos inference ──────────────────────────────────────────────────────────
def forecast_symbol(predictor: KronosPredictor, df: pd.DataFrame, symbol: str):
    """Run N_SAMPLES Kronos fan paths for one symbol. Returns dict or None."""
    if len(df) < LOOKBACK + 5:
        print(f'  {symbol}: only {len(df)} rows, skipping')
        return None

    hist = df.iloc[-LOOKBACK:].copy()
    x_ts = pd.Series(hist.index, name='timestamps')
    fut_idx = next_trading_dates(hist.index[-1], PRED_LEN)
    y_ts = pd.Series(fut_idx, name='timestamps')

    paths, failed = [], 0
    for i in range(N_SAMPLES):
        try:
            pred = predictor.predict(
                df=hist,
                x_timestamp=x_ts,
                y_timestamp=y_ts,
                pred_len=PRED_LEN,
                T=TEMPERATURE,
                top_p=TOP_P,
                sample_count=1,
                verbose=False,
            )
            paths.append([
                {
                    'd': str(fut_idx[j].date()),
                    'o': round(float(pred['open'].iloc[j]),  2),
                    'h': round(float(pred['high'].iloc[j]),  2),
                    'l': round(float(pred['low'].iloc[j]),   2),
                    'c': round(float(pred['close'].iloc[j]), 2),
                }
                for j in range(PRED_LEN)
            ])
        except Exception as e:
            failed += 1
            if failed == 1:
                print(f'  {symbol} sample error: {e}')

    if not paths:
        return None

    # Last 40 bars of history for chart context
    ctx = df.iloc[-40:]
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

    # Regime analysis: direction + dispersion of final closes
    last_close  = float(df['close'].iloc[-1])
    final_cls   = [p[-1]['c'] for p in paths]
    pct_above   = sum(1 for c in final_cls if c > last_close) / len(final_cls)
    spread_pct  = float(np.std(final_cls) / (abs(last_close) + 1e-6) * 100)
    median_ret  = float((np.median(final_cls) - last_close) / (last_close + 1e-6) * 100)

    if spread_pct < 1.5:
        regime = 'TRENDING \u2191' if pct_above > 0.6 else 'TRENDING \u2193' if pct_above < 0.4 else 'RANGING \u2194'
    elif spread_pct > 3.5:
        regime = 'CHOPPY \u2194'
    else:
        regime = 'MIXED \u2195'

    print(f'  {symbol}: {len(paths)} paths | {regime} | '
          f'above={pct_above:.0%} | spread={spread_pct:.1f}% | median ret={median_ret:+.1f}%')

    return {
        'last_close': round(last_close,  2),
        'history':    history,
        'paths':      paths,
        'regime':     regime,
        'pct_above':  round(pct_above,   3),
        'spread_pct': round(spread_pct,  2),
        'median_ret': round(median_ret,  2),
    }


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--offline', action='store_true',
                   help='Skip run if output already has today\'s date')
    args = p.parse_args()

    if args.offline and OUT.exists():
        existing = json.loads(OUT.read_text(encoding='utf-8'))
        if existing.get('as_of') == str(date.today()):
            print('[Kronos] Output already up-to-date, skipping.')
            return

    predictor = load_predictor()
    results = {}

    # 1. Nifty 50 index
    if NSEI_CSV.exists():
        print('Forecasting NSEI (Nifty 50)...')
        df = load_ohlcv(NSEI_CSV)
        r = forecast_symbol(predictor, df, 'NSEI')
        if r:
            results['NSEI'] = {'name': 'Nifty 50', **r}

    # 2. Top HHHL stocks (BUY → WATCH → CAUTION)
    if HHHL_JSON.exists():
        prio = {'BUY': 0, 'WATCH': 1, 'CAUTION': 2, 'AVOID': 3, 'SELL': 4}
        scan = json.loads(HHHL_JSON.read_text(encoding='utf-8'))
        rows = sorted(scan.get('rows', []),
                      key=lambda r: prio.get(r.get('status', 'AVOID'), 5))
        count = 0
        for row in rows:
            if count >= MAX_STOCKS:
                break
            sym = row.get('symbol', '')
            csv_p = PRICE_DIR / f'{sym}.NS.csv'
            if not csv_p.exists():
                continue
            print(f'Forecasting {sym} ({row.get("status","?")})...')
            df = load_ohlcv(csv_p)
            r = forecast_symbol(predictor, df, sym)
            if r:
                results[sym] = {
                    'name':   row.get('name', sym),
                    'status': row.get('status', ''),
                    **r
                }
                count += 1

    output = {
        'as_of':    str(date.today()),
        'model':    MODEL_ID,
        'lookback': LOOKBACK,
        'pred_len': PRED_LEN,
        'n_paths':  N_SAMPLES,
        'symbols':  results,
    }
    OUT.write_text(
        json.dumps(output, separators=(',', ':'), allow_nan=False, ensure_ascii=False),
        encoding='utf-8',
    )
    print(f'\n[Kronos] Done — {len(results)} symbols → {OUT}')


if __name__ == '__main__':
    main()
