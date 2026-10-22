"""Intraday Kronos run for Nifty 50 that includes TODAY's live Kotak bar.

The daily forecast (kronos_forecast.py) only sees completed EOD candles, so during the session it
cannot know about today's move. This appends today's provisional bar (Kotak open/high/low and LTP as
close) to the official NSEI history and runs the same pinned NeoQuasar/Kronos-small model.
The bar is labelled provisional: it is not a completed candle until 15:30 IST.

  py -3 kronos_live.py [--samples 20]      # needs KOTAK_* credentials; writes docs/kronos_live_nsei.json
"""
import argparse
import datetime as dt
import json
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import kotak_live as kl  # noqa: E402
import kronos_forecast as kf  # noqa: E402

OUT = ROOT / "docs" / "kronos_live_nsei.json"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--samples", type=int, default=20)
    a = ap.parse_args()
    now = dt.datetime.now(IST)
    live = kl.nifty_live().get("nifty50") or {}
    o, h, l, c = (live.get(k) for k in ("open", "high", "low", "ltp"))
    if not all(isinstance(v, (int, float)) and v > 0 for v in (o, h, l, c)):
        raise SystemExit("Kotak returned no usable live Nifty bar")
    h, l = max(h, o, c), min(l, o, c)
    df = kf.load_ohlcv(kf.NSEI_CSV)
    today = pd.Timestamp(now.date())
    if df.index[-1] >= today:
        raise SystemExit(f"history already contains {df.index[-1].date()}; live bar not needed")
    vol = float(df["volume"].iloc[-20:].median())
    df.loc[today] = [o, h, l, c, vol]
    kf.torch.set_num_threads(2)
    pred = kf.load_predictor()
    res = kf.forecast_symbol(pred, df, "NSEI", n_samples=a.samples, batch_size=10)
    if not res:
        raise SystemExit("Kronos produced no valid paths")
    res.pop("history", None)
    doc = dict(generated_at=now.isoformat(timespec="seconds"), model=kf.MODEL_ID,
               provenance=dict(kind="kronos-neural", model=kf.MODEL_ID, model_revision=kf.MODEL_REVISION,
                               tokenizer_revision=kf.TOKENIZER_REVISION, script="live-1"),
               live_bar=dict(date=now.date().isoformat(), open=o, high=h, low=l, close=c, provisional=True,
                             note="Today's bar from Kotak live quotes; close is the LTP at run time"),
               prev_close=float(df["close"].iloc[-2]), **res)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    tmp.replace(OUT)
    ends = sorted(p[4]["c"] for p in res["paths"])
    print(f"[kronos_live] {now:%H:%M} IST live close {c} | {len(res['paths'])} paths | "
          f"day-5 range {ends[0]:.0f}-{ends[-1]:.0f} | above live {sum(e > c for e in ends)}/{len(ends)}")


if __name__ == "__main__":
    main()
