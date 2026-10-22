"""Live trade cards for NSE Value Lens. Writes docs/live_cards.json.

Inputs (all real, nothing invented):
  * Kotak Neo live quotes (read-only): Nifty spot, every setup leg on the exact chain expiry,
    and cash-market LTP for HH/HL stocks.
  * docs/nifty_chain.json: today's setups (strikes), rule backtests, Jev tiers.
  * docs/kronos_forecast.json: NeoQuasar/Kronos-small close paths (provenance-checked).
  * docs/hhhl_scan.json: structural trigger / stop levels per stock.

Maths reuses nifty_chain.py's audited Black-Scholes payoff and planned-exit P&L. Implied
volatility is solved from the live ATM call and put. Research output, not investment advice.

  py -3 live_cards.py            # needs KOTAK_* credentials in env or .env
"""
import csv
import datetime as dt
import io
import json
import pathlib
import sys
import urllib.request

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import kotak_live as kl  # noqa: E402
import nifty_chain as nc  # noqa: E402

DOCS = ROOT / "docs"
OUT = DOCS / "live_cards.json"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
HOLD = 5          # option plan: exit after 5 sessions (same as nifty_chain)
STOCK_HOLD = 10   # HH/HL plan holding window (hhhl_scan rules.holding_sessions)
KRONOS_MODEL = "NeoQuasar/Kronos-small"
NSE_CM = "https://lapi.kotaksecurities.com/wso2-scripmaster/v1/prod/{date}/transformed/nse_cm.csv"

# The card the user traded: "Bear put spread" — BUY 22600 PE / SELL 22150 PE, expiry 2026-10-27
# (rules lhll_bear_put_spread + fii_short_bear_put_spread). Published in docs/nifty_chain.json
# @ c710c6a4 (EOD 2026-10-15: 204.90 / 75.00, plan exit by 2026-10-22) and repriced live in
# docs/nifty_live.json @ a2083bd6 (2026-10-16 07:07 PT: 47.90 / 16.85).
PREVIOUS_CARD = dict(label="Bear put spread", published="2026-10-15", expiry="2026-10-27", exit_by="2026-10-22",
                     legs=[dict(side="BUY", strike=22600, option_type="PE", eod_then=204.9, live_then=47.9),
                           dict(side="SELL", strike=22150, option_type="PE", eod_then=75.0, live_then=16.85)])

def _retrying(fn, tries=4):
    """Kotak's gateway drops TLS handshakes intermittently; retry read-only GETs with backoff."""
    import time

    def wrapped(*a, **kw):
        for i in range(tries):
            try:
                return fn(*a, **kw)
            except OSError:  # URLError, SSL EOF, timeouts are OSError subclasses
                if i == tries - 1:
                    raise
                time.sleep(2 * (i + 1))
    return wrapped


kl._get = _retrying(kl._get)


def load(name):
    return json.loads((DOCS / name).read_text(encoding="utf-8"))


def holidays():
    p = ROOT / "data" / "hhhl_calendar.json"
    return set(json.loads(p.read_text(encoding="utf-8")).get("holidays", [])) if p.exists() else set()


def add_sessions(day, n, hol):
    d = day
    while n > 0:
        d += dt.timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in hol:
            n -= 1
    return d


def implied_vol(price, spot, strike, t, call):
    if not (price and price > 0 and t > 0):
        return None
    lo, hi = 0.01, 1.5
    for _ in range(80):
        mid = (lo + hi) / 2
        if float(nc._bs_price(spot, strike, t, mid, call)) > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def rnd(v, d=2):
    return None if v is None or not np.isfinite(v) else round(float(v), d)


def quote_map(sess, tokens):
    """tokens: {segment|pSymbol: key}. Returns {key: ltp}. Batches requests."""
    out, items = {}, list(tokens.items())
    for i in range(0, len(items), 40):
        chunk = dict(items[i:i + 40])
        res = kl.quotes(list(chunk), sess=sess)
        res = res if isinstance(res, list) else (res or {}).get("data", [])
        for q in res or []:
            key = chunk.get(f"{q.get('exchange')}|{q.get('exchange_token')}")
            ltp = kl._f(q.get("ltp"))
            if key is not None and ltp and ltp > 0:
                out[key] = ltp
    return out


# ── Kronos ──────────────────────────────────────────────────────────────────
def kronos_entry(kronos, symbol, as_of):
    """Return a provenance-checked entry or None (same gates as the UI)."""
    if not kronos or kronos.get("model") != KRONOS_MODEL or (kronos.get("provenance") or {}).get("kind") != "kronos-neural":
        return None
    e = (kronos.get("symbols") or {}).get(symbol)
    if not e or e.get("input_stale") or e.get("data_as_of") != as_of:
        return None
    prov = e.get("provenance") or {}
    if prov.get("kind") != "kronos-neural" or prov.get("model") != KRONOS_MODEL:
        return None
    paths = [p for p in e.get("paths") or [] if p and all(np.isfinite(b.get("c", np.nan)) and b["c"] > 0 for b in p)]
    return dict(e, paths=paths) if paths else None


def kronos_for_option(entry, exit_iso, spot, xs, ys):
    """Kronos close on the exit date for each path, re-anchored to live spot, valued on the exit P&L curve."""
    if not entry:
        return None
    scale = spot / entry["last_close"]
    closes = [b["c"] * scale for p in entry["paths"] for b in p if b["d"] == exit_iso]
    if not closes:
        return None
    pnl = [float(np.interp(c, xs, ys)) for c in closes]
    return dict(exit_date=exit_iso, input_date=entry["data_as_of"], paths=len(closes),
                paths_in_profit=int(sum(v > 0 for v in pnl)),
                median_close=rnd(np.median(closes)), median_pnl_per_lot=rnd(np.median(pnl)),
                anchored_to_live_spot=round(scale, 5))


def kronos_for_stock(entry, trigger, stop, hold):
    if not entry:
        return None
    paths = [p[:hold] for p in entry["paths"] if len(p) >= hold]
    if not paths:
        return None
    last = entry["last_close"]
    ends = [p[-1]["c"] for p in paths]
    return dict(input_date=entry["data_as_of"], sessions=hold, paths=len(paths),
                end_above_close=int(sum(c > last for c in ends)),
                close_above_trigger=int(sum(any(b["c"] > trigger for b in p) for p in paths)) if trigger else None,
                close_below_stop=int(sum(any(b["c"] < stop for b in p) for p in paths)) if stop else None,
                median_end_pct=rnd((np.median(ends) / last - 1) * 100, 1), end_date=paths[0][-1]["d"])


# ── Nifty option cards ──────────────────────────────────────────────────────
def stop_levels(xs, ys, spot, stop_pnl):
    lo = [x for x, y in zip(xs, ys) if x < spot and y <= stop_pnl]
    hi = [x for x, y in zip(xs, ys) if x > spot and y <= stop_pnl]
    return dict(below=rnd(max(lo), 0) if lo else None, above=rnd(min(hi), 0) if hi else None)


def decide(defined, ev, kr, status, t_stat):
    if not defined:
        return "AVOID", "Undefined risk: a naked short leg means the loss is not capped."
    ev_ok = ev is not None and ev > 0
    k_ok = bool(kr) and kr["paths_in_profit"] / kr["paths"] >= 0.6
    bt_ok = status != "NO_EDGE" and (t_stat is None or t_stat >= 0)
    parts = [f"model exit P&L {'positive' if ev_ok else 'negative'} ({ev:+,.0f}/lot)" if ev is not None else "exit P&L unavailable",
             f"Kronos {kr['paths_in_profit']}/{kr['paths']} paths in profit at exit" if kr else "Kronos unavailable",
             f"backtest {status}" + (f", t-stat {t_stat:+.2f}" if t_stat is not None else "")]
    if ev_ok and k_ok and bt_ok:
        return "CANDIDATE", "Maths, Kronos and backtest agree: " + "; ".join(parts) + "."
    if ev_ok or k_ok:
        return "WATCH", "Mixed: " + "; ".join(parts) + "."
    return "AVOID", "Against: " + "; ".join(parts) + "."


def nifty_cards(sess, chain, kronos, today, hol):
    idx, expiry = chain["index"], chain["index"]["trade_expiry"]
    live = kl.nifty_live(sess=sess)
    spot = (live.get("nifty50") or {}).get("ltp")
    if not spot:
        raise RuntimeError("Kotak returned no live Nifty 50 LTP")
    rows = kl._scrip_master_rows()
    want = {(float(l["strike"]), l["option_type"]) for s in chain["setups"] for l in s["legs"]}
    contracts, tokens = {}, {}
    for k, o in want:
        info = kl.resolve_option("NIFTY", expiry, k, o, rows=rows)
        if info:
            contracts[(k, o)] = info
            tokens[f"nse_fo|{info['pSymbol']}"] = (k, o)
    ltp = quote_map(sess, tokens)
    lot = int(next(iter(contracts.values()))["lot"] or idx.get("lot") or 65)
    dte = (dt.date.fromisoformat(expiry) - today).days
    exit_by = add_sessions(today, HOLD, hol)
    horizon = (exit_by - today).days
    t = dte / 365.0
    atm = min({k for k, _ in want}, key=lambda k: abs(k - spot))
    ivs = [v for v in (implied_vol(ltp.get((atm, o)), spot, atm, t, o == "CE") for o in ("CE", "PE")) if v]
    sigma = sum(ivs) / len(ivs) if ivs else idx["atm_iv"] / 100.0
    kentry, ksource = live_kronos(today), "live"
    if not kentry:
        kentry, ksource = kronos_entry(kronos, "NSEI", chain["as_of"]), "eod"
    rules = {r["id"]: r for r in chain["rules"]}
    cards = []
    for s in chain["setups"]:
        priced, legs = [], []
        for l in s["legs"]:
            key = (float(l["strike"]), l["option_type"])
            if key not in ltp:
                priced = None
                break
            priced.append(dict(option_type=l["option_type"], strike=key[0], side=l["side"], ref_close=ltp[key], lot=lot))
            legs.append(dict(side=l["side"], strike=key[0], option_type=l["option_type"], expiry=expiry,
                             contract=contracts[key]["trd"], live_ltp=ltp[key]))
        if not priced:
            continue
        pay = nc.payoff_profile(priced, spot, lot, sigma, dte)
        ex = nc.exit_payoff_profile(priced, spot, lot, sigma, dte, HOLD, horizon_days=horizon) or {}
        xs, ys = np.array(ex["curve"]["price"]), np.array(ex["curve"]["pnl"])
        net = sum((1 if p["side"] == "BUY" else -1) * p["ref_close"] for p in priced)
        stop = kl._stop_loss(priced, pay, lot)
        stop["nifty_levels"] = stop_levels(xs, ys, spot, stop["level_per_lot"])
        kr = kronos_for_option(kentry, exit_by.isoformat(), spot, xs, ys)
        rule = rules.get(s["rule"], {})
        st = rule.get("stats") or {}
        status = rule.get("status") or s.get("status")
        defined = pay.get("max_loss") is not None
        verdict, why = decide(defined, ex.get("exp_pnl_per_lot"), kr, status, st.get("t_stat"))
        cards.append(dict(
            rule=s["rule"], label=s["label"], action=s.get("action"), view=s.get("view"), firing_today=s.get("firing"),
            verdict=verdict, why=why, legs=legs,
            net=dict(type="debit" if net > 0 else "credit", per_unit=rnd(abs(net)), per_lot=rnd(abs(net) * lot)),
            max_profit=pay.get("max_profit"), max_loss=pay.get("max_loss"), breakevens=pay.get("breakevens"),
            exit=dict(by=exit_by.isoformat(), sessions=HOLD, exp_pnl_per_lot=ex.get("exp_pnl_per_lot"),
                      p_profit_model=ex.get("p_profit"), worst5=ex.get("pnl_worst5"), median=ex.get("pnl_median"),
                      best5=ex.get("pnl_best5"), costs=ex.get("round_trip_costs")),
            stop=stop, kronos=kr,
            backtest=dict(status=status, trades=st.get("trades"), win_rate=st.get("win_rate"),
                          mean_return_pct=st.get("mean_return_pct"), t_stat=st.get("t_stat")),
            jev=(s.get("jev_priority") or {}).get("tier")))
    order = {"CANDIDATE": 0, "WATCH": 1, "AVOID": 2}
    cards.sort(key=lambda c: (order[c["verdict"]], -(c["exit"]["exp_pnl_per_lot"] or -1e12)))
    return dict(spot=spot, bank_nifty=(live.get("bank_nifty") or {}).get("ltp"), expiry=expiry, lot=lot,
                dte=dte, live_iv_pct=rnd(sigma * 100), eod_iv_pct=idx.get("atm_iv"), chain_as_of=chain["as_of"],
                kronos_input=kentry["data_as_of"] if kentry else None,
                kronos_source=ksource if kentry else None,
                kronos_generated_at=kentry.get("generated_at") if kentry else None,
                direction=direction_evidence(chain, spot, kentry, exit_by.isoformat()), cards=cards), rows


def live_kronos(today, max_age_min=120):
    """Kronos run that includes today's provisional Kotak bar (kronos_live.py). None if absent or old."""
    p = DOCS / "kronos_live_nsei.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None
    prov = d.get("provenance") or {}
    gen = dt.datetime.fromisoformat(d.get("generated_at", "1970-01-01T00:00:00+00:00"))
    if (prov.get("kind") != "kronos-neural" or prov.get("model") != KRONOS_MODEL
            or (d.get("live_bar") or {}).get("date") != today.isoformat()
            or (dt.datetime.now(IST) - gen).total_seconds() > max_age_min * 60):
        return None
    paths = [q for q in d.get("paths") or [] if q and all(np.isfinite(b.get("c", np.nan)) and b["c"] > 0 for b in q)]
    return dict(d, paths=paths) if paths and d.get("last_close") else None


def direction_evidence(chain, spot, kentry, exit_iso):
    """Every directional input we have, as votes. Nothing here is a forecast of its own."""
    idx, h = chain["index"], chain.get("hhhl") or {}
    closes = [c for c in h.get("close") or [] if isinstance(c, (int, float))] + [spot]
    ema9 = None
    if len(closes) >= 9:
        ema9 = sum(closes[:9]) / 9
        for c in closes[9:]:
            ema9 = c * 0.2 + ema9 * 0.8
    hs, ls, cs = (h.get(k) or [] for k in ("high", "low", "close"))
    typ = [(a + b + c) / 3 for a, b, c in list(zip(hs, ls, cs))[-20:] if all(isinstance(v, (int, float)) for v in (a, b, c))]
    vwap20 = sum(typ) / len(typ) if typ else None
    jev = (chain.get("jev") or {}).get("index") or {}
    jd, jp = jev.get("direction") or {}, jev.get("positioning") or {}
    st = (idx.get("structure") or {})
    votes = []

    def vote(name, value, side, detail):
        votes.append(dict(name=name, value=value, side=side, detail=detail))

    prev = idx.get("close")
    chg = (spot / prev - 1) * 100 if prev else None
    vote("Live move today", f"{chg:+.2f}%" if chg is not None else "—",
         "bear" if chg is not None and chg < -0.25 else "bull" if chg is not None and chg > 0.25 else "neutral",
         f"Kotak {spot:,.2f} vs previous close {prev:,.2f}")
    if ema9:
        vote("Live price vs EMA 9", f"{spot - ema9:+.0f} pts", "bear" if spot < ema9 else "bull", f"EMA 9 incl. live price {ema9:,.0f}")
    if vwap20:
        vote("Live price vs 20-day VWAP", f"{spot - vwap20:+.0f} pts", "bear" if spot < vwap20 else "bull", f"VWAP-20 {vwap20:,.0f} (EOD bars)")
    s = st.get("structure") or ""
    vote("Swing structure", s or "—", "bear" if s.startswith("LH") and "LL" in s else "bull" if s.startswith("HH") else "neutral",
         f"confirmed high {st.get('confirmed_high')}, confirmed low {st.get('confirmed_low')}")
    if idx.get("fii_long_share") is not None:
        f = idx["fii_long_share"]
        vote("FII index-futures long share", f"{f}%", "bear" if f < 40 else "bull" if f > 60 else "neutral", "NSE participant OI (EOD)")
    if jp.get("choice"):
        vote("Jev positioning", f"{jp['choice']} ({round(100 * (jp.get('probabilities') or {}).get(jp['choice'], 0))}%)",
             "bear" if "bearish" in jp["choice"] else "bull" if "bullish" in jp["choice"] else "neutral", "Jev reading of participant data")
    if jd.get("choice"):
        pr = jd.get("probabilities") or {}
        vote("Jev direction", f"{jd['choice']} (bull {round(100 * pr.get('bullish', 0))}% / bear {round(100 * pr.get('bearish', 0))}%)",
             "bear" if jd["choice"] == "bearish" else "bull" if jd["choice"] == "bullish" else "neutral", "low-confidence index assessment")
    if kentry:
        scale = spot / kentry["last_close"]
        ends = sorted(b["c"] * scale for p in kentry["paths"] for b in p if b["d"] == exit_iso)
        if ends:
            up = sum(e > spot for e in ends)
            med = ends[len(ends) // 2]
            vote(f"Kronos paths on {exit_iso}", f"{up}/{len(ends)} above live, median {med:,.0f}",
                 "bull" if up >= 0.65 * len(ends) else "bear" if up <= 0.35 * len(ends) else "neutral",
                 f"range {ends[0]:,.0f}–{ends[-1]:,.0f}; input {kentry['data_as_of']}")
    bull = sum(v["side"] == "bull" for v in votes)
    bear = sum(v["side"] == "bear" for v in votes)
    lean = "BEARISH" if bear >= bull + 2 else "BULLISH" if bull >= bear + 2 else "MIXED"
    return dict(lean=lean, bull=bull, bear=bear, neutral=len(votes) - bull - bear, votes=votes)


def previous_card(sess, rows):
    """Live value of the bear put spread the user traded vs. both published reference entries."""
    toks = {}
    for l in PREVIOUS_CARD["legs"]:
        info = kl.resolve_option("NIFTY", PREVIOUS_CARD["expiry"], l["strike"], l["option_type"], rows=rows)
        if info:
            toks[f"nse_fo|{info['pSymbol']}"] = l["strike"]
    now = quote_map(sess, toks) if toks else {}
    buy, sell = PREVIOUS_CARD["legs"]
    if buy["strike"] not in now or sell["strike"] not in now:
        return dict(PREVIOUS_CARD, available=False)
    cur = now[buy["strike"]] - now[sell["strike"]]
    width = buy["strike"] - sell["strike"]
    refs = {}
    for name in ("eod_then", "live_then"):
        debit = buy[name] - sell[name]
        refs[name] = dict(debit=rnd(debit), pnl_per_unit=rnd(cur - debit), return_pct=rnd((cur / debit - 1) * 100, 1),
                          max_profit_per_unit=rnd(width - debit))
    return dict(PREVIOUS_CARD, available=True, ltp_now={str(k): v for k, v in now.items()},
                spread_now=rnd(cur), width=width, refs=refs)


# ── HH/HL stock cards ───────────────────────────────────────────────────────
def stock_ltps(sess, symbols, today):
    try:
        cache = ROOT / ".cache" / f"nse_cm_{today.isoformat()}.csv"
        if cache.exists():
            txt = cache.read_text(encoding="utf-8")
        else:
            url = NSE_CM.format(date=today.isoformat())
            txt = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=90).read().decode("utf-8", "replace")
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(txt, encoding="utf-8")
        rows = [{k.strip().rstrip(";").strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO(txt))]
        by = {r.get("pTrdSymbol"): r.get("pSymbol") for r in rows}
        toks = {f"nse_cm|{by[s + '-EQ']}": s for s in symbols if by.get(s + "-EQ")}
        return quote_map(sess, toks)
    except Exception as e:  # live stock prices are optional; EOD levels still stand
        print("[live_cards] stock LTP unavailable:", str(e)[:120])
        return {}


ACTIONS = {"BUY": "BUY at next open (scanner entry rules met)",
           "WATCH": "WAIT: buy only after a daily close above the trigger",
           "CAUTION": "DO NOT CHASE: already above the trigger",
           "SELL": "EXIT if holding: closed below the structure stop",
           "AVOID": "NO TRADE"}


def stock_cards(sess, scan, kronos, today):
    rows = [r for r in scan["rows"] if r["status"] in ("BUY", "WATCH", "CAUTION", "SELL")]
    live = stock_ltps(sess, [r["symbol"] for r in rows], today)
    gate = bool((scan.get("market") or {}).get("new_entries_allowed"))
    out = []
    for r in rows:
        z = r.get("zones") or {}
        trig, stop = z.get("breakout_above"), z.get("structure_exit_below")
        px = live.get(r["symbol"]) or r["close"]
        kr = kronos_for_stock(kronos_entry(kronos, r["symbol"], scan["as_of"]), trig, stop, STOCK_HOLD)
        out.append(dict(symbol=r["symbol"], name=r.get("name"), sector=r.get("sector"), status=r["status"],
                        action=ACTIONS[r["status"]] + ("" if gate or r["status"] != "BUY" else " — blocked: market gate closed"),
                        reason=r.get("reason"), eod_close=r["close"], live_ltp=live.get(r["symbol"]),
                        trigger=trig, stop=stop, overextended_above=z.get("extended_above"),
                        risk_pct_from_price=rnd((px - stop) / px * 100, 1) if stop and px > stop else None,
                        kronos=kr))
    order = {"BUY": 0, "WATCH": 1, "CAUTION": 2, "SELL": 3}
    out.sort(key=lambda c: (order[c["status"]], -((c["kronos"] or {}).get("end_above_close") or -1)))
    return dict(market_gate_open=gate, scan_as_of=scan["as_of"], cards=out)


def main():
    now = dt.datetime.now(IST)
    today = now.date()
    sess = kl.login()
    chain, kronos, scan = load("nifty_chain.json"), load("kronos_forecast.json"), load("hhhl_scan.json")
    nifty, rows = nifty_cards(sess, chain, kronos, today, holidays())
    doc = dict(version=1, generated_at=now.isoformat(timespec="seconds"),
               source="Kotak Neo live quotes (read-only) + nifty_chain maths + NeoQuasar/Kronos-small + Jev + rule backtests",
               nifty=nifty, previous_card=previous_card(sess, rows), stocks=stock_cards(sess, scan, kronos, today),
               disclaimer="Research output from live quotes and models. Not investment advice; fills, margin and slippage differ.")
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    tmp.replace(OUT)
    c = nifty["cards"]
    print(f"[live_cards] {now:%H:%M} IST spot={nifty['spot']} iv={nifty['live_iv_pct']}% cards={len(c)} "
          f"candidates={sum(x['verdict']=='CANDIDATE' for x in c)} stocks={len(doc['stocks']['cards'])}")


if __name__ == "__main__":
    main()
