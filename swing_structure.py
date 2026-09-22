#!/usr/bin/env python3
"""
Swing Structure tab generator — Dow Theory HH/HL/LH/LL for all 200.

Reads screen_output/sr_levels.json (which now carries a `swing_structure`
block per stock, computed in daily_sr.py from 5-bar fractal pivots) and emits:
  - screen_output/swing_structure.json   (machine + website)
  - public/data/swing_structure.js        (window.SWING_STRUCTURE for Pages)

Structure states:
  UPTREND      last pivot pair = HH + HL   (higher highs, higher lows)
  DOWNTREND    last pivot pair = LH + LL   (lower highs, lower lows)
  REVERSAL_UP  a higher low (HL) formed after lower lows — 1-2-3 bottom forming;
               BUY trigger = break of the last swing high
  REVERSAL_DN  a lower high (LH) formed after higher highs — 1-2-3 top forming;
               SELL trigger = break of the last swing low
  MIXED        no clean structure yet

Plain-English, facts only. Not SEBI-registered advice.
"""
import json
from pathlib import Path
from datetime import date

HERE = Path(__file__).resolve().parent
OUT  = HERE / "screen_output"
JS_OUT = HERE / "public" / "data" / "swing_structure.js"

STATE_LABEL = {
    'UPTREND':     'Uptrend (HH + HL)',
    'DOWNTREND':   'Downtrend (LH + LL)',
    'REVERSAL_UP': 'Bullish reversal SETUP (unconfirmed)',
    'REVERSAL_DN': 'Bearish reversal SETUP (unconfirmed)',
    'MIXED':       'No clean structure',
}


def plain_for(sym, close, ss):
    """One-line plain English for the structure, with exact trigger numbers."""
    st = ss['structure']
    lh = ss['last_high']; ll = ss['last_low']
    trig = ss.get('reversal_trigger'); inval = ss.get('reversal_invalidate')
    if st == 'UPTREND':
        msg = (f"UPTREND — price is making higher highs and higher lows. "
               f"Last higher low ₹{ll['price']} is the trend support; while it holds, dips are buyable. "
               f"Break below ₹{ll['price']} would be the first crack.")
    elif st == 'DOWNTREND':
        msg = (f"DOWNTREND — price is making lower highs and lower lows. "
               f"Last lower high ₹{lh['price']} is the ceiling; rallies into it get sold. "
               f"A close above ₹{lh['price']} would be the first sign of a turn.")
    elif st == 'REVERSAL_UP':
        t = trig['price'] if trig else lh['price']
        iv = inval['price'] if inval else ll['price']
        msg = (f"REVERSAL UP FORMING — a higher low ₹{ll['price']} printed after lower lows (possible double bottom). "
               f"Buyers confirm on a close above ₹{t}; the setup fails on a close below ₹{iv}.")
    elif st == 'REVERSAL_DN':
        t = trig['price'] if trig else ll['price']
        iv = inval['price'] if inval else lh['price']
        msg = (f"REVERSAL DOWN FORMING — a lower high ₹{lh['price']} printed after higher highs (possible double top). "
               f"Sellers confirm on a close below ₹{t}; the setup fails on a close above ₹{iv}.")
    else:
        msg = (f"NO CLEAN STRUCTURE — swings are choppy. "
               f"Last swing high ₹{lh['price']}, last swing low ₹{ll['price']}. Wait for a clear HH/HL or LH/LL sequence.")
    if ss.get('extended_warning'):
        msg += f" ⚠️ {ss['extended_warning']}."
    return msg


def main():
    sr = json.loads((OUT / "sr_levels.json").read_text())
    as_of = sr.get("as_of", date.today().isoformat())
    rows = []
    for s in sr.get("stocks", []):
        if 'error' in s:
            continue
        ss = s.get("swing_structure")
        if not ss:
            continue
        rows.append({
            "symbol":      s["symbol"],
            "name":        s.get("name", ""),
            "close":       s.get("close"),
            "structure":   ss["structure"],
            "structure_label": STATE_LABEL.get(ss["structure"], ss["structure"]),
            "last_high":   ss["last_high"],
            "last_low":    ss["last_low"],
            "consec_hh":   ss.get("consec_hh", 0),
            "consec_ll":   ss.get("consec_ll", 0),
            "consec_lh":   ss.get("consec_lh", 0),
            "consec_hl":   ss.get("consec_hl", 0),
            "reversal_trigger":    ss.get("reversal_trigger"),
            "reversal_invalidate": ss.get("reversal_invalidate"),
            "extended_warning":    ss.get("extended_warning"),
            "sequence":    ss.get("sequence", []),
            "plain":       plain_for(s["symbol"], s.get("close"), ss),
            # audit flags the user asked for
            "at_second_ll": ss.get("consec_ll", 0) == 2,
            "at_second_hh": ss.get("consec_hh", 0) == 2,
        })

    # Sort: reversals first (actionable), then trends, then mixed
    order = {'REVERSAL_UP': 0, 'REVERSAL_DN': 1, 'UPTREND': 2, 'DOWNTREND': 3, 'MIXED': 4}
    rows.sort(key=lambda r: (order.get(r["structure"], 9), r["symbol"]))

    from collections import Counter
    counts = dict(Counter(r["structure"] for r in rows))

    payload = {
        "as_of":      as_of,
        "universe":   f"Nifty 200 ({len(rows)} stocks)",
        "method":     "Dow Theory HH/HL/LH/LL on 5-bar fractal swing pivots. Structure = last confirmed high+low pair.",
        "counts":     counts,
        "second_ll":  [r["symbol"] for r in rows if r["at_second_ll"]],
        "second_hh":  [r["symbol"] for r in rows if r["at_second_hh"]],
        "stocks":     rows,
    }
    (OUT / "swing_structure.json").write_text(json.dumps(payload, indent=1))
    JS_OUT.parent.mkdir(parents=True, exist_ok=True)
    JS_OUT.write_text("// generated by swing_structure.py — do not edit by hand\nwindow.SWING_STRUCTURE = " + json.dumps(payload) + ";\n")
    print(f"Saved: swing_structure.json + swing_structure.js ({len(rows)} stocks)")
    print(f"Structure counts: {counts}")
    print(f"At 2nd LL (double-bottom watch): {payload['second_ll'][:15]}")
    print(f"At 2nd HH (double-top watch):    {payload['second_hh'][:15]}")


if __name__ == "__main__":
    main()
