"""Kotak Neo live market data — READ ONLY.

Logs in with the documented TOTP -> MPIN flow and reads quotes. There are deliberately
NO order / modify / cancel functions in this module: it can only read prices, so it can
never place a trade. Credentials come from the gitignored .env, never from code.

Flow (per Kotak Neo v2 docs):
  1. POST https://mis.kotaksecurities.com/login/1.0/tradeApiLogin   (Authorization: access token,
     neo-fin-key: neotradeapi; body mobileNumber/ucc/totp) -> view token + sid
  2. POST https://mis.kotaksecurities.com/login/1.0/tradeApiValidate (sid + Auth = view token;
     body mpin) -> session token + sid + baseUrl + dataCenter
  3. GET  {baseUrl}/script-details/1.0/quotes/neosymbol/<queries>/all (Authorization: access token)

CLI:
  py -3 kotak_live.py --check        # show which credentials are present (values never printed)
  py -3 kotak_live.py --login        # perform a live login, cache the session (needs all creds + IP whitelist)
  py -3 kotak_live.py --refresh      # login if needed, fetch live index quotes, write docs/nifty_live.json
"""
import argparse
import json
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import pyotp
except ImportError:  # pragma: no cover
    pyotp = None

ROOT = pathlib.Path(__file__).resolve().parent
ENV = ROOT / ".env"
CACHE = ROOT / ".cache" / "kotak_session.json"
LIVE_OUT = ROOT / "docs" / "nifty_live.json"
LOGIN_BASE = "https://mis.kotaksecurities.com/login/1.0"
FIN_KEY = "neotradeapi"
SESSION_MAX_AGE = 8 * 3600  # re-login after 8h; baseUrl/token are stable for the day
# Index quotes use the exact case-sensitive index name on nse_cm.
INDEX_QUERIES = ["nse_cm|Nifty 50", "nse_cm|Nifty Bank", "nse_cm|India VIX"]
REQUIRED = ("KOTAK_ACCESS_TOKEN", "KOTAK_TOTP_SECRET", "KOTAK_MOBILE", "KOTAK_UCC", "KOTAK_MPIN")


def _env():
    out = {}
    if ENV.exists():
        for ln in ENV.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#") or "=" not in ln:
                continue
            k, _, v = ln.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    for k in REQUIRED:
        if os.environ.get(k):
            out[k] = os.environ[k]
    return out


def credentials_present():
    """Return {name: bool} for each required credential. Values are never returned or printed."""
    e = _env()
    return {k: bool(e.get(k)) for k in REQUIRED}


def totp_now(secret=None):
    if pyotp is None:
        raise RuntimeError("pyotp not installed: pip install pyotp")
    secret = secret or _env().get("KOTAK_TOTP_SECRET")
    if not secret:
        raise RuntimeError("KOTAK_TOTP_SECRET missing in .env")
    return pyotp.TOTP(secret).now()


def _with_retry(fn, tries=4):
    """Kotak's gateway intermittently drops TLS handshakes (SSL EOF) or times out. Retry with backoff;
    HTTP 4xx errors (bad request / auth) are not retried."""
    for i in range(tries):
        try:
            return fn()
        except urllib.error.HTTPError as e:
            if e.code < 500 or i == tries - 1:
                raise
        except OSError:  # URLError, SSL EOF, socket timeouts
            if i == tries - 1:
                raise
        time.sleep(1.5 * (i + 1))


def _post(url, headers, body):
    data = json.dumps(body).encode("utf-8")

    def call():
        req = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    return _with_retry(call)


def _get(url, headers):
    def call():
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    return _with_retry(call)


def login(force=False):
    """Two-step TOTP+MPIN login. Caches and reuses the session token/sid/baseUrl for the day."""
    if not force and CACHE.exists():
        try:
            cached = json.loads(CACHE.read_text(encoding="utf-8"))
            if time.time() - cached.get("at", 0) < SESSION_MAX_AGE and cached.get("session_token"):
                return cached
        except (OSError, ValueError):
            pass
    e = _env()
    missing = [k for k in REQUIRED if not e.get(k)]
    if missing:
        raise RuntimeError("Missing Kotak credentials in .env: " + ", ".join(missing))
    access = e["KOTAK_ACCESS_TOKEN"]
    auth_headers = {"Authorization": access, "neo-fin-key": FIN_KEY}
    # Step 1: TOTP login -> view token + sid
    r1 = _post(f"{LOGIN_BASE}/tradeApiLogin", auth_headers,
               {"mobileNumber": e["KOTAK_MOBILE"], "ucc": e["KOTAK_UCC"], "totp": totp_now(e["KOTAK_TOTP_SECRET"])})
    d1 = r1.get("data") or {}
    if d1.get("status") == "error" or not d1.get("token"):
        raise RuntimeError(f"tradeApiLogin failed: {r1.get('message') or r1}")
    view_token, view_sid = d1["token"], d1["sid"]
    # Step 2: MPIN validate -> session token + sid + baseUrl
    r2 = _post(f"{LOGIN_BASE}/tradeApiValidate", {**auth_headers, "sid": view_sid, "Auth": view_token}, {"mpin": e["KOTAK_MPIN"]})
    d2 = r2.get("data") or {}
    if d2.get("status") == "error" or not d2.get("token"):
        raise RuntimeError(f"tradeApiValidate failed: {r2.get('message') or r2}")
    sess = dict(at=time.time(), access_token=access, session_token=d2["token"], sid=d2["sid"],
                base_url=d2.get("baseUrl"), data_center=d2.get("dataCenter"))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(sess), encoding="utf-8")
    return sess


def quotes(queries, filt="all", sess=None):
    """GET live quotes for a list of 'segment|instrument' queries (read-only)."""
    sess = sess or login()
    path = urllib.parse.quote(",".join(queries), safe="|,")
    url = f"{sess['base_url']}/script-details/1.0/quotes/neosymbol/{path}/{filt}"
    return _get(url, {"Authorization": sess["access_token"], "Content-Type": "application/json"})


def _one(rows, name):
    for q in rows or []:
        if str(q.get("exchange_token")) == name or q.get("display_symbol", "").startswith(name):
            o = q.get("ohlc") or {}
            return dict(ltp=_f(q.get("ltp")), change=_f(q.get("change")), per_change=_f(q.get("per_change")),
                        open=_f(o.get("open")), high=_f(o.get("high")), low=_f(o.get("low")), close=_f(o.get("close")))
    return None


def _f(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def nifty_live(sess=None):
    """Live Nifty 50 / Bank Nifty / India VIX snapshot. Read-only."""
    rows = quotes(INDEX_QUERIES, sess=sess)
    rows = rows if isinstance(rows, list) else rows.get("data", [])
    return dict(generated_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                source="Kotak Neo live quotes (official, read-only)",
                nifty50=_one(rows, "Nifty 50"), bank_nifty=_one(rows, "Nifty Bank"), india_vix=_one(rows, "India VIX"))


SCRIP_MASTER = "https://lapi.kotaksecurities.com/wso2-scripmaster/v1/prod/{date}/transformed/nse_fo.csv"
SCRIP_CACHE = ROOT / ".cache" / "nse_fo_scrip.json"
# Kotak monthly expiry code -> real calendar month. Monthly uses 3-letter (26OCT); weekly uses day code (26O19).
MONTH_CODES = {1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
               7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"}


def _scrip_master_rows(date_str=None):
    """Download (and cache for the day) the NSE F&O scrip master. Read-only CSV of tradeable contracts."""
    import csv, io, datetime
    date_str = date_str or (datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")
    # Day-level disk cache: avoid re-downloading the ~85k-row CSV every poll.
    try:
        if SCRIP_CACHE.exists():
            cached = json.loads(SCRIP_CACHE.read_text(encoding="utf-8"))
            if cached.get("date") == date_str and cached.get("rows"):
                return cached["rows"]
    except Exception:
        pass
    url = SCRIP_MASTER.format(date=date_str)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        txt = r.read().decode("utf-8", "replace")
    rows = []
    for row in csv.DictReader(io.StringIO(txt)):
        rows.append({k.strip().rstrip(";").strip(): (v or "").strip() for k, v in row.items()})
    try:
        SCRIP_CACHE.parent.mkdir(parents=True, exist_ok=True)
        SCRIP_CACHE.write_text(json.dumps({"date": date_str, "rows": rows}, separators=(",", ":")), encoding="utf-8")
    except Exception:
        pass
    return rows


# Kotak scrip-master expiry epochs count seconds from 1980-01-01 00:00 IST, not 1970 UTC.
KOTAK_EPOCH_OFFSET = 315513000


def kotak_expiry_date(raw):
    """Kotak lExpiryDate/pExpiryDate -> ISO date (IST). Verified: 1478183400 -> 2026-11-03."""
    import datetime
    try:
        secs = int(float(raw)) + KOTAK_EPOCH_OFFSET
    except (TypeError, ValueError):
        return None
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.datetime.fromtimestamp(secs, ist).date().isoformat()


def resolve_option(symbol_name, expiry_iso, strike, opt_type, rows=None):
    """Find the Kotak pSymbol for an option on the EXACT expiry date and strike.

    Matching by the monthly code (NIFTY26NOV...) silently picked the monthly contract when the
    chain trades a weekly expiry, so every live price was the wrong contract. This matches the
    scrip master's own expiry date and strike (dStrikePrice is in paise).
    Returns dict(pSymbol, trd, lot, expiry) or None when that exact contract is not listed.
    """
    rows = rows if rows is not None else _scrip_master_rows()
    want_strike = round(float(strike), 2)
    for r in rows:
        if r.get("pSymbolName") != symbol_name or r.get("pOptionType") != opt_type:
            continue
        try:
            k = round(float(r.get("dStrikePrice")) / 100.0, 2)
        except (TypeError, ValueError):
            continue
        if k != want_strike:
            continue
        if kotak_expiry_date(r.get("lExpiryDate") or r.get("pExpiryDate")) == expiry_iso:
            return dict(pSymbol=r.get("pSymbol"), trd=r.get("pTrdSymbol"), lot=_f(r.get("lLotSize")),
                        expiry=expiry_iso)
    return None


def option_quotes(legs, sess=None, rows=None):
    """Given chain legs [{name,strike,expiry,option_type,side,ref_close,lot}], fetch live LTP for each.

    Returns list of dicts {name, strike, option_type, side, ref_close, live_ltp, pSymbol}. Read-only.
    """
    sess = sess or login()
    rows = rows if rows is not None else _scrip_master_rows()
    resolved, by_ps = [], {}
    for leg in legs:
        opt = (leg.get("option_type") or leg.get("name", "")[-2:]).upper()
        info = resolve_option("NIFTY", leg.get("expiry"), float(leg.get("strike")), opt, rows=rows)
        entry = dict(name=leg.get("name"), strike=leg.get("strike"), option_type=opt,
                     side=leg.get("side"), ref_close=leg.get("ref_close"), lot=leg.get("lot"),
                     expiry=leg.get("expiry"), pSymbol=info.get("pSymbol") if info else None, live_ltp=None)
        resolved.append(entry)
        if info and info.get("pSymbol"):
            by_ps[info["pSymbol"]] = entry
    if by_ps:
        q = quotes(["nse_fo|" + ps for ps in by_ps], sess=sess)
        qrows = q if isinstance(q, list) else q.get("data", [])
        for qr in qrows or []:
            ps = str(qr.get("exchange_token") or qr.get("pSymbol") or "")
            # match by display symbol suffix if exchange_token missing
            for ps_key, entry in by_ps.items():
                sym = qr.get("display_symbol") or qr.get("trading_symbol") or ""
                if ps == ps_key or sym == entry["name"] or sym.endswith(str(int(float(entry["strike"]))) + entry["option_type"]):
                    entry["live_ltp"] = _f(qr.get("ltp"))
                    break
    return resolved


def _setup_legs_from_chain(chain_path=None):
    """Read the firing setup's legs + best-structure candidate legs from docs/nifty_chain.json."""
    chain_path = chain_path or (ROOT / "docs" / "nifty_chain.json")
    try:
        d = json.loads(pathlib.Path(chain_path).read_text(encoding="utf-8"))
    except Exception:
        return [], None
    legs = []
    seen = set()
    trade_exp = None
    for s in d.get("setups", []):
        for l in s.get("legs", []):
            if l.get("expiry"):
                trade_exp = l.get("expiry")
            key = (l.get("strike"), l.get("option_type") or l.get("name", "")[-2:], l.get("expiry"))
            if key not in seen:
                seen.add(key)
                legs.append(l)
    # include comparison candidate legs so the best-structure table also reprices live
    for c in (d.get("comparison") or {}).get("candidates", []):
        for l in c.get("legs", []):
            exp = l.get("expiry") or trade_exp
            opt = l.get("option_type") or (l.get("name", "") or "")[-2:]
            key = (l.get("strike"), opt, exp)
            if l.get("strike") and exp and key not in seen:
                seen.add(key)
                legs.append(dict(l, expiry=exp, option_type=opt))
    return legs, d.get("as_of")



def reprice_live_maths(chain_path=None):
    """Recompute every setup + comparison candidate from LIVE option prices using the SAME audited
    math as nifty_chain.py (Black-Scholes, lognormal exit distribution, P(profit), return-on-risk).
    Live LTP is substituted as each leg's entry price. Returns a dict to merge into nifty_live.json.
    Browser only displays these — no math runs in the browser."""
    import importlib
    nc = importlib.import_module("nifty_chain")
    chain_path = chain_path or (ROOT / "docs" / "nifty_chain.json")
    d = json.loads(pathlib.Path(chain_path).read_text(encoding="utf-8"))
    idx = d.get("index", {})
    sigma = (idx.get("atm_iv") or 0) / 100.0 or None
    sess = login()
    rows = _scrip_master_rows()
    # live spot
    spot = None
    try:
        spot = (nifty_live(sess=sess).get("nifty50") or {}).get("ltp")
    except Exception:
        pass
    spot = spot or idx.get("close")
    out = {"spot": spot, "setups": [], "comparison": {"candidates": []}}

    def live_legs(legs, trade_exp):
        """Attach live_ltp to each leg; return (legs_with_live_ref, ok)."""
        quoted = option_quotes([dict(l, expiry=l.get("expiry") or trade_exp,
                                     option_type=l.get("option_type") or (l.get("name", "") or "")[-2:])
                                for l in legs], sess=sess, rows=rows)
        by_key = {(round(float(q["strike"])), q["option_type"]): q.get("live_ltp") for q in quoted}
        priced, ok = [], True
        for l in legs:
            opt = l.get("option_type") or (l.get("name", "") or "")[-2:]
            ltp = by_key.get((round(float(l["strike"])), opt))
            if ltp is None:
                ok = False
                break
            priced.append(dict(option_type=opt, strike=float(l["strike"]), side=l["side"],
                               ref_close=float(ltp), lot=int(l.get("lot") or idx.get("lot") or 65)))
        return priced, ok

    dte = None
    # recompute each setup
    for s in d.get("setups", []):
        legs = s.get("legs", [])
        trade_exp = (legs[0] or {}).get("expiry") if legs else None
        if dte is None and trade_exp:
            try:
                dte = (dt_date_fromiso(trade_exp) - dt_date_fromiso(d.get("as_of"))).days
            except Exception:
                dte = None
        priced, ok = live_legs(legs, trade_exp)
        if not ok or spot is None or not sigma or not dte:
            continue
        lot = priced[0]["lot"]
        pay = nc.payoff_profile(priced, float(spot), lot, sigma, int(dte))
        ex = nc.exit_payoff_profile(priced, float(spot), lot, sigma, int(dte), nc.HOLD)
        out["setups"].append(dict(rule=s.get("rule"),
                                  legs=[dict(side=p["side"], strike=p["strike"], option_type=p["option_type"],
                                             live_ltp=p["ref_close"], lot=p["lot"]) for p in priced],
                                  payoff=pay, exit=ex,
                                  stop_loss=_stop_loss(priced, pay, lot)))
    # recompute comparison candidates
    for c in (d.get("comparison") or {}).get("candidates", []):
        legs = c.get("legs", [])
        if not legs:
            continue
        priced, ok = live_legs(legs, c.get("expiry") or trade_exp)
        if not ok or spot is None or not sigma or not dte:
            continue
        lot = priced[0]["lot"]
        pay = nc.payoff_profile(priced, float(spot), lot, sigma, int(dte))
        ex = nc.exit_payoff_profile(priced, float(spot), lot, sigma, int(dte), nc.HOLD)
        maxrisk = abs(pay.get("max_loss") or 0) or 1
        out["comparison"]["candidates"].append(dict(id=c.get("id"), name=c.get("name"),
            max_profit_at_expiry=pay.get("max_profit"), max_loss_at_expiry=pay.get("max_loss"),
            exit=ex, exp_return_on_risk_pct=round(100.0 * (ex or {}).get("exp_pnl_per_lot", 0) / maxrisk, 2),
            stop_loss=_stop_loss(priced, pay, lot)))
    # re-rank by live expected return on risk
    cands = out["comparison"]["candidates"]
    cands.sort(key=lambda x: -(x.get("exp_return_on_risk_pct") or -1e9))
    if cands:
        out["comparison"]["best_id"] = cands[0]["id"]
    return out


def _stop_loss(priced, payoff, lot):
    """A simple, defined stop: for debit spreads/longs, stop at 50% of debit paid; for credit, at 2x credit.
    Returns the rupee loss level per lot where the position should be closed."""
    net = sum((1 if p["side"] == "BUY" else -1) * p["ref_close"] for p in priced)  # +debit / -credit
    if net > 0:  # debit paid
        return dict(type="debit", rule="Close if the position loses 50% of the debit paid",
                    level_per_lot=round(-0.5 * net * lot, 2))
    else:        # credit received
        return dict(type="credit", rule="Close if the loss reaches 2x the credit received",
                    level_per_lot=round(2.0 * net * lot, 2))


def dt_date_fromiso(s):
    import datetime
    return datetime.date.fromisoformat(s)

def write_live(path=LIVE_OUT):
    sess = login()
    data = nifty_live(sess=sess)
    # Add live option legs for the firing setup + best-structure candidates
    try:
        legs, as_of = _setup_legs_from_chain()
        if legs:
            rows = _scrip_master_rows()
            quoted = option_quotes(legs, sess=sess, rows=rows)
            data["option_legs"] = quoted
            data["chain_as_of"] = as_of
    except Exception as e:
        data["option_legs_error"] = str(e)[:200]
    # Full live maths (all setups + comparison recomputed with audited nifty_chain formulas)
    try:
        data["live_maths"] = reprice_live_maths()
    except Exception as e:
        data["live_maths_error"] = str(e)[:200]
    pathlib.Path(path).write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return data


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--check", action="store_true", help="show which credentials are present (values never printed)")
    p.add_argument("--login", action="store_true", help="perform a live login and cache the session")
    p.add_argument("--refresh", action="store_true", help="fetch live index quotes and write docs/nifty_live.json")
    a = p.parse_args()
    if a.check or not (a.login or a.refresh):
        present = credentials_present()
        print("Kotak credentials present (values hidden):")
        for k, ok in present.items():
            print(f"  {k:<20} {'yes' if ok else 'MISSING'}")
        if pyotp is not None and present.get("KOTAK_TOTP_SECRET"):
            print("TOTP generation: OK (6-digit code available)")
        return
    if a.login:
        sess = login(force=True)
        print("Login OK. baseUrl captured:", bool(sess.get("base_url")), "| data_center:", sess.get("data_center"))
    if a.refresh:
        data = write_live()
        n = data.get("nifty50") or {}
        print("Wrote", LIVE_OUT.name, "| Nifty 50 LTP:", n.get("ltp"))


if __name__ == "__main__":
    main()
