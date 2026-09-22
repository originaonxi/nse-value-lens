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
    'UPTREND_BROKEN':   'Uptrend broken — CHoCH ⚠️ (unconfirmed)',
    'DOWNTREND_BROKEN': 'Downtrend broken — CHoCH ⚠️ (unconfirmed)',
    'MIXED':       'No clean structure',
}


def plain_for(sym, close, ss):
    """Plain English for the structure with BOS/CHoCH status and Wyckoff conviction."""
    st   = ss['structure']
    lh   = ss['last_high']; ll = ss['last_low']
    trig = ss.get('reversal_trigger'); inval = ss.get('reversal_invalidate')
    bos  = ss.get('bos') or {}; choch = ss.get('choch') or {}
    wy   = ss.get('wyckoff') or {}

    # Core structure sentence
    if st == 'UPTREND':
        msg = (f"UPTREND — higher highs + higher lows. Last HL ₹{ll['price']} is trend support; "
               f"dips toward it are buyable. Break below = first crack.")
    elif st == 'DOWNTREND':
        msg = (f"DOWNTREND — lower highs + lower lows. Last LH ₹{lh['price']} is ceiling; "
               f"rallies into it get sold. Close above = first turn signal.")
    elif st == 'REVERSAL_UP':
        t = trig['price'] if trig else lh['price']
        iv = inval['price'] if inval else ll['price']
        msg = (f"BULLISH REVERSAL SETUP — HL ₹{ll['price']} formed after lower lows. "
               f"Confirm on close above ₹{t}; fails below ₹{iv}.")
    elif st == 'REVERSAL_DN':
        t = trig['price'] if trig else ll['price']
        iv = inval['price'] if inval else lh['price']
        msg = (f"BEARISH REVERSAL SETUP — LH ₹{lh['price']} formed after higher highs. "
               f"Confirm on close below ₹{t}; fails above ₹{iv}.")
    elif st == 'UPTREND_BROKEN':
        msg = (f"UPTREND BROKEN (CHoCH ⚠️) — closed ₹{close} below last HL ₹{ll['price']}. "
               f"Character change, NOT a confirmed downtrend yet (pivots still HH/HL). "
               f"Reclaim ₹{ll['price']} to repair; a fresh LH+LL confirms downtrend.")
    elif st == 'DOWNTREND_BROKEN':
        msg = (f"DOWNTREND BROKEN (CHoCH ⚠️) — closed ₹{close} above last LH ₹{lh['price']}. "
               f"Character change, NOT a confirmed uptrend yet (pivots still LH/LL). "
               f"Lose ₹{lh['price']} to resume down; a fresh HH+HL confirms uptrend.")
    else:
        msg = (f"NO CLEAN STRUCTURE — last swing high ₹{lh['price']}, last swing low ₹{ll['price']}. "
               f"Wait for HH/HL or LH/LL sequence.")

    # BOS/CHoCH overlay
    if bos.get('fired'):
        msg += f" {bos['desc']}."
    elif choch.get('fired') is False:
        msg += f" {choch.get('desc','Setup failed')}."
    elif choch.get('fired'):
        msg += f" {choch['desc']}."

    # Wyckoff conviction tag
    if wy.get('note'):
        msg += f" Wyckoff: {wy['note']}"
    if ss.get('extended_warning'):
        msg += f" ⚠️ {ss['extended_warning']}."
    return msg


def main():
    sr = json.loads((OUT / "sr_levels.json").read_text())
    as_of = sr.get("as_of", date.today().isoformat())
    rows = []
    for s in sr.get("stocks", []):
        if 'error' in s: continue
        ss = s.get("swing_structure")
        if not ss: continue
        bos   = ss.get("bos") or {}
        choch = ss.get("choch") or {}
        wy    = ss.get("wyckoff") or {}
        rows.append({
            "symbol":      s["symbol"],
            "name":        s.get("name", ""),
            "close":       s.get("close"),
            "structure":   ss["structure"],
            "raw_structure":   ss.get("raw_structure", ss["structure"]),
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
            # BOS / CHoCH
            "bos":         bos,
            "bos_fired":   bool(bos.get("fired")),
            "bos_dir":     bos.get("dir"),
            "choch":       choch,
            "choch_fired": bool(choch.get("fired")),
            "choch_dir":   choch.get("dir"),
            # Wyckoff
            "wyckoff":          wy,
            "wyckoff_phase":    wy.get("phase"),
            "wyckoff_conviction": wy.get("conviction"),
            "wyckoff_note":     wy.get("note"),
            "sequence":    ss.get("sequence", []),
            "plain":       plain_for(s["symbol"], s.get("close"), ss),
            "at_second_ll": ss.get("consec_ll", 0) == 2,
            "at_second_hh": ss.get("consec_hh", 0) == 2,
        })

    # Sort: reversals first (actionable), then trends, then mixed
    order = {'REVERSAL_UP': 0, 'REVERSAL_DN': 1, 'UPTREND_BROKEN': 2, 'DOWNTREND_BROKEN': 3, 'UPTREND': 4, 'DOWNTREND': 5, 'MIXED': 6}
    rows.sort(key=lambda r: (order.get(r["structure"], 9), r["symbol"]))

    from collections import Counter
    counts = dict(Counter(r["structure"] for r in rows))

    payload = {
        "as_of":      as_of,
        "universe":   f"Nifty 200 ({len(rows)} stocks)",
        "method":     "Dow HH/HL/LH/LL on 5-bar fractals + BOS/CHoCH labels + Wyckoff volume phase. Informational — not action-changing until calibrated.",
        "counts":     counts,
        "second_ll":  [r["symbol"] for r in rows if r["at_second_ll"]],
        "second_hh":  [r["symbol"] for r in rows if r["at_second_hh"]],
        "bos_fired":  [r["symbol"] for r in rows if r["bos_fired"]],
        "choch_fired":[r["symbol"] for r in rows if r["choch_fired"]],
        "high_conviction_reversals": [
            r["symbol"] for r in rows
            if r["structure"] in ("REVERSAL_UP","REVERSAL_DN")
            and r.get("wyckoff_conviction") == "HIGH"
        ],
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
