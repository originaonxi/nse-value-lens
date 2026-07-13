#!/usr/bin/env python3
"""
NSE Value Lens — Enhanced Math + Support/Resistance Engine
Computes for each stock:
  - 1-year OHLCV-based support & resistance levels (swing highs/lows + volume clusters)
  - 50-equation comprehensive math breakdown
  - Integrated confidence score (fundamentals + technicals + news + sentiment)
  - Buy/sell price zones
  - Breakout/breakdown detection vs July 13 2026 closing

Usage:
    cd /tmp/nse-value-lens
    python3 scripts/enhance_math.py
"""
import json, re, sys, math
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parent.parent
STOCKS_JS = ROOT / "public" / "data" / "stocks.js"
OUT_JS = ROOT / "public" / "data" / "stocks.js"

# ─── Load existing stocks.js ────────────────────────────────────────────────
raw = STOCKS_JS.read_text(encoding="utf-8")
m = re.search(r'window\.STOCK_DATA\s*=\s*(\{.*\})\s*;?\s*$', raw, re.DOTALL)
if not m:
    sys.exit("ERROR: Could not parse window.STOCK_DATA from stocks.js")
data = json.loads(m.group(1))
stocks = data["stocks"]
print(f"Loaded {len(stocks)} stocks from stocks.js")

# ─── Fetch 1-year OHLCV via yfinance ────────────────────────────────────────
try:
    import yfinance as yf
    HAVE_YF = True
except ImportError:
    HAVE_YF = False
    print("WARNING: yfinance not installed — S/R will be derived from existing price fields only")

def fetch_ohlcv(symbol):
    """Fetch 1-year daily OHLCV for NSE symbol. Returns list of dicts or None."""
    if not HAVE_YF:
        return None
    try:
        ticker = symbol + ".NS"
        h = yf.Ticker(ticker).history(period="1y", auto_adjust=True)
        if h.empty or len(h) < 20:
            return None
        rows = []
        for dt, row in h.iterrows():
            rows.append({
                "date": str(dt.date()),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row["Volume"]),
            })
        return rows
    except Exception as e:
        print(f"  [yf error] {symbol}: {e}")
        return None

# ─── Support / Resistance Computation ───────────────────────────────────────
def swing_highs_lows(ohlcv, window=5):
    """Find swing highs and lows using a rolling window."""
    highs, lows = [], []
    n = len(ohlcv)
    for i in range(window, n - window):
        h = ohlcv[i]["high"]
        l = ohlcv[i]["low"]
        if all(h >= ohlcv[j]["high"] for j in range(i-window, i+window+1) if j != i):
            highs.append(h)
        if all(l <= ohlcv[j]["low"] for j in range(i-window, i+window+1) if j != i):
            lows.append(l)
    return highs, lows

def cluster_levels(levels, pct_tol=0.025):
    """Cluster nearby price levels within pct_tol of each other."""
    if not levels:
        return []
    sorted_lvls = sorted(levels)
    clusters = []
    current = [sorted_lvls[0]]
    for lv in sorted_lvls[1:]:
        if (lv - current[0]) / current[0] < pct_tol:
            current.append(lv)
        else:
            clusters.append(round(sum(current) / len(current), 1))
            current = [lv]
    clusters.append(round(sum(current) / len(current), 1))
    return clusters

def volume_profile_levels(ohlcv, n_bins=20):
    """Find high-volume price nodes — these act as strong S/R."""
    if not ohlcv:
        return []
    # Drop NaN / zero rows before any arithmetic
    clean = [r for r in ohlcv
             if r["high"] == r["high"] and r["low"] == r["low"]
             and r["volume"] == r["volume"]
             and r["high"] > 0 and r["low"] > 0]
    if not clean:
        return []
    prices = [(r["high"] + r["low"]) / 2 for r in clean]
    vols   = [r["volume"] for r in clean]
    mn, mx = min(prices), max(prices)
    if mx == mn:
        return [round(mn, 1)]
    bin_size = (mx - mn) / n_bins
    bins = [0.0] * n_bins
    for p, v in zip(prices, vols):
        idx = min(int((p - mn) / bin_size), n_bins - 1)
        bins[idx] += v
    top = sorted(range(n_bins), key=lambda i: bins[i], reverse=True)[:3]
    return [round(mn + (t + 0.5) * bin_size, 1) for t in sorted(top)]

def compute_sr(ohlcv, price, dma50, dma200):
    """Compute support and resistance levels from 1-year data."""
    if not ohlcv:
        # Fallback: classify each DMA strictly by side of current price
        sup_list, res_list = [], []
        for lv in [dma200, dma50]:
            if lv is None: continue
            if lv < price:   sup_list.append(round(lv, 1))
            elif lv > price: res_list.append(round(lv, 1))
        near_sup_fb = sorted(sup_list, reverse=True)[0] if sup_list else round(price * 0.93, 1)
        near_res_fb = sorted(res_list)[0]               if res_list else round(price * 1.10, 1)
        return {
            "support": sup_list, "resistance": res_list, "method": "derived_from_dma",
            "near_support": near_sup_fb, "near_resistance": near_res_fb,
            "support_dist_pct": round((near_sup_fb / price - 1) * 100, 1) if price else 0,
            "resistance_dist_pct": round((near_res_fb / price - 1) * 100, 1) if price else 0,
            "breaking_out": False, "breaking_down": False,
        }

    swing_h, swing_l = swing_highs_lows(ohlcv)
    vol_nodes = volume_profile_levels(ohlcv)

    # All candidate resistance = swing highs + vol nodes above price
    all_res = [h for h in swing_h if h > price * 1.005] + [v for v in vol_nodes if v > price * 1.005]
    # All candidate support = swing lows + vol nodes + DMAs below price
    all_sup = [l for l in swing_l if l < price * 0.995] + [v for v in vol_nodes if v < price * 0.995]
    if dma200 and dma200 < price:
        all_sup.append(dma200)
    elif dma200 and dma200 > price:
        all_res.append(dma200)
    if dma50 and dma50 < price:
        all_sup.append(dma50)
    elif dma50 and dma50 > price:
        all_res.append(dma50)

    res_clustered = cluster_levels(all_res)
    sup_clustered = cluster_levels(all_sup)

    # Final safety clamp — guarantee support < price, resistance > price
    sup_levels = sorted([v for v in sup_clustered if v < price], reverse=True)[:3]
    res_levels = sorted([v for v in res_clustered if v > price])[:3]

    # 52-week high / low
    hi52 = max(r["high"] for r in ohlcv)
    lo52 = min(r["low"] for r in ohlcv)

    # Breakout/breakdown — latest close only vs nearest level; mutually exclusive
    last_close = ohlcv[-1]["close"]
    prev_close = ohlcv[-2]["close"] if len(ohlcv) >= 2 else last_close
    breaking_out  = bool(res_levels and last_close > res_levels[0] and prev_close <= res_levels[0])
    breaking_down = bool(sup_levels and last_close < sup_levels[0] and prev_close >= sup_levels[0])
    if breaking_out and breaking_down:   # can't be both — keep whichever is larger move
        if abs(last_close - res_levels[0]) >= abs(last_close - sup_levels[0]):
            breaking_down = False
        else:
            breaking_out  = False

    # Distance to nearest — fallback always strictly on the correct side
    near_sup = sup_levels[0] if sup_levels else (dma200 if dma200 and dma200 < price else price * 0.93)
    near_res = res_levels[0] if res_levels else (dma200 if dma200 and dma200 > price else price * 1.10)
    sup_dist_pct = round((near_sup / price - 1) * 100, 1)
    res_dist_pct = round((near_res / price - 1) * 100, 1)

    return {
        "support": [round(s, 1) for s in sup_levels],
        "resistance": [round(r, 1) for r in res_levels],
        "hi_52w": round(hi52, 1),
        "lo_52w": round(lo52, 1),
        "near_support": round(near_sup, 1),
        "near_resistance": round(near_res, 1),
        "support_dist_pct": sup_dist_pct,
        "resistance_dist_pct": res_dist_pct,
        "breaking_out": breaking_out,
        "breaking_down": breaking_down,
        "vol_nodes": [round(v, 1) for v in vol_nodes],
        "method": "ohlcv_swing_volume"
    }

# ─── 50-Equation Comprehensive Math Engine ──────────────────────────────────
WACC_DEFAULT = 12.0  # India WACC proxy for industrials

def sector_pe(sector):
    """Sector median PE benchmarks (India 2026 estimates)."""
    MAP = {
        "Metals": 12, "Mining": 10, "Refining": 8, "Power": 16,
        "Defence": 35, "Capital Goods": 28, "Railways": 30,
        "Shipbuilding": 22, "Pharmaceuticals": 25, "FMCG": 40,
        "IT": 22, "Banks": 12, "NBFC": 14, "Insurance": 28,
        "Chemicals": 22, "Cement": 18, "Auto": 20, "Oil": 8,
        "Fertilisers": 12, "Telecom": 18, "Ports": 20,
        "Water": 20, "Electronics": 30, "Nuclear": 35,
    }
    for key, pe in MAP.items():
        if key.lower() in sector.lower():
            return pe
    return 20  # default

def wacc_for(de, sector):
    """Estimate WACC: Ke*E/(D+E) + Kd*(1-t)*D/(D+E)."""
    Ke = 14.0   # cost of equity (CAPM proxy, India risk premium)
    Kd = 9.5    # cost of debt (India avg lending rate 2026)
    t = 0.25    # corporate tax
    if de is None or de == 0:
        return Ke
    D = de; E = 1.0
    return round((Ke * E + Kd * (1 - t) * D) / (D + E), 2)

def graham_number(eps, bvps):
    """Benjamin Graham intrinsic value: sqrt(22.5 * EPS * BVPS)."""
    if eps and bvps and eps > 0 and bvps > 0:
        return round(math.sqrt(22.5 * eps * bvps), 1)
    return None

def dcf_simple(eps, growth_pct, target_pe, years=3):
    """Simple forward DCF: project EPS n years at growth rate, apply target PE."""
    if eps and eps > 0:
        fwd_eps = eps * ((1 + growth_pct / 100) ** years)
        return round(fwd_eps * target_pe, 1)
    return None

def build_math_detail(s, sr):
    """Build comprehensive 50-equation math breakdown for one stock."""
    price = s.get("price", 0)
    pe    = s.get("pe")
    pb    = s.get("pb")
    roce  = s.get("roce", 0)
    roe   = s.get("roe", 0)
    de    = s.get("de", 0)
    div   = s.get("div_yield", 0)
    pg    = s.get("profit_growth", 0)
    prom  = s.get("promoter_holding", 0)
    pledg = s.get("pledged", 0)
    rsi   = s.get("rsi14")
    macd  = s.get("macd")
    macd_h = s.get("macd_hist")
    bb    = s.get("bb_pos")
    vol_r = s.get("vol_ratio_20_90")
    vann  = s.get("volatility_ann")
    ab200 = s.get("above_200dma")
    ab50  = s.get("above_50dma")
    dma200 = s.get("dma200")
    dma50  = s.get("dma50")
    ret6  = s.get("ret_6m", 0)
    ret12 = s.get("ret_12m", 0)
    h52   = s.get("pct_off_52w_high")
    l52   = s.get("pct_above_52w_low")
    sector = s.get("sector", "")
    sc    = s.get("scores", {})
    conf  = s.get("confidence", {})
    math_old = s.get("math", {})
    news  = s.get("news", {})
    holders = s.get("holders", {})
    scen  = s.get("scenarios", {})
    policy = s.get("policy", 5)
    geopt  = s.get("theme", "other")

    # ── Derived fundamentals ──
    eps  = round(price / pe, 2) if pe and pe > 0 and price else None
    bvps = round(price / pb, 2) if pb and pb > 0 and price else None
    sp   = sector_pe(sector)
    wacc = wacc_for(de, sector)
    roce_spread = round(roce - wacc, 1) if roce else None
    roe_spread  = round(roe - wacc, 1) if roe else None
    graham = graham_number(eps, bvps)
    growth = math_old.get("growth_pct", pg or 5) if math_old else (pg or 5)
    tgt_pe = math_old.get("target_multiple", sp) if math_old else sp
    fwd_dcf = dcf_simple(eps, growth, tgt_pe, years=3)
    peg = round(pe / growth, 2) if pe and growth and growth > 0 else None
    div_support = round(price * div / 100 / 0.035, 1) if div and div > 0 else None  # 3.5% yield floor

    # ── S/R distances — safe side-aware fallback + hard clamp ──
    _sup_fb = (dma200 if dma200 and dma200 < price else
               dma50  if dma50  and dma50  < price else price * 0.92)
    _res_fb = (dma200 if dma200 and dma200 > price else
               dma50  if dma50  and dma50  > price else price * 1.10)
    near_sup = sr.get("near_support", _sup_fb)
    near_res = sr.get("near_resistance", _res_fb)
    # Hard clamp — never let support be at or above price (or resistance at or below)
    if near_sup >= price: near_sup = price * 0.92
    if near_res <= price: near_res = price * 1.10
    sup_pct  = round((near_sup / price - 1) * 100, 1) if price else 0
    res_pct  = round((near_res / price - 1) * 100, 1) if price else 0
    risk_reward_sr = round(abs(res_pct / sup_pct), 2) if sup_pct != 0 else None

    # ── 50 equations ──
    equations = [
        # VALUATION (1-12)
        {"id": 1, "group": "Valuation", "name": "Price-to-Earnings (PE)",
         "formula": "Price ÷ EPS",
         "value": f"{pe}x" if pe else "N/A",
         "benchmark": f"Sector median {sp}x",
         "verdict": "CHEAP" if pe and pe < sp * 0.75 else ("FAIR" if pe and pe < sp else "EXPENSIVE"),
         "score": 10 if pe and pe < sp * 0.6 else (7 if pe and pe < sp * 0.8 else (5 if pe and pe < sp else 2))},
        {"id": 2, "group": "Valuation", "name": "Price-to-Book (PB)",
         "formula": "Price ÷ Book Value Per Share",
         "value": f"{pb}x" if pb else "N/A",
         "benchmark": "PB < 2.5x = value territory for most sectors",
         "verdict": "DEEP VALUE" if pb and pb < 1.5 else ("VALUE" if pb and pb < 2.5 else ("FAIR" if pb and pb < 4 else "RICH")),
         "score": 10 if pb and pb < 1.0 else (8 if pb and pb < 1.5 else (6 if pb and pb < 2.5 else 3))},
        {"id": 3, "group": "Valuation", "name": "Dividend Yield",
         "formula": "Annual Dividend ÷ Price × 100",
         "value": f"{div}%" if div else "0%",
         "benchmark": "India 10Y gsec ~7.2%; yield >3.5% = price floor support",
         "verdict": "STRONG YIELD" if div and div > 4 else ("YIELD SUPPORT" if div and div > 2.5 else ("WEAK" if div and div > 1 else "NO YIELD")),
         "score": 10 if div and div > 5 else (8 if div and div > 3.5 else (5 if div and div > 1.5 else 2))},
        {"id": 4, "group": "Valuation", "name": "Graham Number",
         "formula": "√(22.5 × EPS × BVPS)",
         "value": f"₹{graham}" if graham else "N/A",
         "benchmark": f"Current price ₹{price}",
         "verdict": f"{'BELOW GRAHAM (+margin of safety)' if graham and price < graham else 'ABOVE GRAHAM (less margin)'}" if graham else "N/A",
         "score": 9 if graham and price < graham * 0.8 else (7 if graham and price < graham else 4)},
        {"id": 5, "group": "Valuation", "name": "Forward DCF (3-year)",
         "formula": f"EPS × (1 + {growth}%)³ × {tgt_pe}x PE",
         "value": f"₹{fwd_dcf}" if fwd_dcf else "N/A",
         "benchmark": f"Current ₹{price} — upside to target",
         "verdict": f"{'UNDERVALUED' if fwd_dcf and price < fwd_dcf * 0.85 else ('FAIR' if fwd_dcf and price < fwd_dcf else 'OVERVALUED')}" if fwd_dcf else "N/A",
         "score": 9 if fwd_dcf and price < fwd_dcf * 0.75 else (7 if fwd_dcf and price < fwd_dcf * 0.9 else (5 if fwd_dcf and price < fwd_dcf else 2))},
        {"id": 6, "group": "Valuation", "name": "PEG Ratio",
         "formula": "PE ÷ Earnings Growth Rate",
         "value": f"{peg}" if peg else "N/A",
         "benchmark": "PEG < 1 = potentially undervalued",
         "verdict": "GREAT" if peg and peg < 0.5 else ("GOOD" if peg and peg < 1.0 else ("FAIR" if peg and peg < 1.5 else "STRETCHED")),
         "score": 10 if peg and peg < 0.5 else (7 if peg and peg < 1.0 else (4 if peg and peg < 1.5 else 2))},
        {"id": 7, "group": "Valuation", "name": "Dividend Discount Price Floor",
         "formula": "Annual DPS ÷ 3.5% (yield floor)",
         "value": f"₹{div_support}" if div_support else "N/A",
         "benchmark": "Price below this = institutional buying zone on yield",
         "verdict": f"{'BELOW FLOOR (buy zone)' if div_support and price < div_support else 'ABOVE FLOOR'}" if div_support else "N/A",
         "score": 8 if div_support and price < div_support else 5},
        {"id": 8, "group": "Valuation", "name": "PE Discount to Sector",
         "formula": "(Sector PE − Stock PE) ÷ Sector PE × 100",
         "value": f"{round((sp - pe) / sp * 100, 1)}% discount" if pe else "N/A",
         "benchmark": f"Sector PE: {sp}x | Stock PE: {pe}x",
         "verdict": "DEEP DISCOUNT" if pe and pe < sp * 0.65 else ("DISCOUNT" if pe and pe < sp * 0.85 else ("INLINE" if pe and pe < sp * 1.1 else "PREMIUM")),
         "score": 10 if pe and pe < sp * 0.55 else (7 if pe and pe < sp * 0.75 else (5 if pe and pe < sp else 2))},
        {"id": 9, "group": "Valuation", "name": "52-Week High Discount",
         "formula": "(Current Price − 52W High) ÷ 52W High × 100",
         "value": f"{h52}%" if h52 is not None else "N/A",
         "benchmark": "Below −15% from 52W high = value opportunity (George & Hwang momentum flip zone)",
         "verdict": "DEEP PULLBACK" if h52 and h52 < -20 else ("PULLBACK" if h52 and h52 < -10 else ("NEAR HIGH" if h52 and h52 > -5 else "MODERATE")),
         "score": 8 if h52 and h52 < -20 else (6 if h52 and h52 < -10 else (4 if h52 and h52 > -5 else 5))},
        {"id": 10, "group": "Valuation", "name": "52-Week Low Margin",
         "formula": "(Current − 52W Low) ÷ 52W Low × 100",
         "value": f"+{l52}%" if l52 is not None else "N/A",
         "benchmark": "Stocks that have doubled off lows often have further to run",
         "verdict": "STRONG RECOVERY" if l52 and l52 > 80 else ("RECOVERED" if l52 and l52 > 30 else "NEAR LOW"),
         "score": 7 if l52 and l52 > 60 else (5 if l52 and l52 > 20 else 3)},
        {"id": 11, "group": "Valuation", "name": "Market Cap Reasonableness",
         "formula": "Market Cap = Price × Shares Outstanding",
         "value": f"₹{s.get('market_cap_cr', '?')}Cr" if s.get('market_cap_cr') else "N/A",
         "benchmark": ">₹1,500Cr = institutional liquidity gate",
         "verdict": "LIQUID" if s.get('market_cap_cr') and s['market_cap_cr'] > 5000 else ("ADEQUATE" if s.get('market_cap_cr') and s['market_cap_cr'] > 1500 else "ILLIQUID"),
         "score": 8 if s.get('market_cap_cr') and s['market_cap_cr'] > 50000 else (6 if s.get('market_cap_cr') and s['market_cap_cr'] > 5000 else 4)},
        {"id": 12, "group": "Valuation", "name": "EPS Anchor",
         "formula": "Price ÷ PE = EPS",
         "value": f"₹{eps}/share" if eps else "N/A",
         "benchmark": f"EPS × target PE {tgt_pe}x = target ₹{fwd_dcf}",
         "verdict": "ANCHORED" if eps and eps > 0 else "NO EARNINGS",
         "score": 7 if eps and eps > 20 else (5 if eps and eps > 5 else 2)},

        # QUALITY (13-24)
        {"id": 13, "group": "Quality", "name": "ROCE (Return on Capital Employed)",
         "formula": "EBIT ÷ (Total Assets − Current Liabilities) × 100",
         "value": f"{roce}%",
         "benchmark": ">15% = decent | >25% = strong moat",
         "verdict": "STRONG MOAT" if roce and roce > 30 else ("GOOD" if roce and roce > 20 else ("DECENT" if roce and roce > 12 else "WEAK")),
         "score": 10 if roce and roce > 35 else (8 if roce and roce > 25 else (5 if roce and roce > 15 else 2))},
        {"id": 14, "group": "Quality", "name": "ROE (Return on Equity)",
         "formula": "Net Profit ÷ Shareholders Equity × 100",
         "value": f"{roe}%",
         "benchmark": ">15% = healthy | >25% = excellent",
         "verdict": "EXCELLENT" if roe and roe > 25 else ("HEALTHY" if roe and roe > 15 else ("DECENT" if roe and roe > 10 else "WEAK")),
         "score": 10 if roe and roe > 30 else (7 if roe and roe > 20 else (5 if roe and roe > 12 else 2))},
        {"id": 15, "group": "Quality", "name": "ROCE vs WACC Spread",
         "formula": f"ROCE − WACC (est. {wacc}%)",
         "value": f"+{roce_spread}%" if roce_spread and roce_spread > 0 else (f"{roce_spread}%" if roce_spread else "N/A"),
         "benchmark": "Positive spread = value creation | negative = value destruction",
         "verdict": "GREAT VALUE CREATOR" if roce_spread and roce_spread > 20 else ("VALUE CREATOR" if roce_spread and roce_spread > 5 else ("BORDERLINE" if roce_spread and roce_spread > 0 else "DESTROYS VALUE")),
         "score": 10 if roce_spread and roce_spread > 25 else (8 if roce_spread and roce_spread > 15 else (5 if roce_spread and roce_spread > 0 else 1))},
        {"id": 16, "group": "Quality", "name": "Debt-to-Equity Ratio",
         "formula": "Total Debt ÷ Shareholders Equity",
         "value": f"{de}x" if de is not None else "N/A",
         "benchmark": "<0.5 = safe | >1.5 = leveraged | >3 = risky",
         "verdict": "DEBT FREE" if de is not None and de < 0.05 else ("SAFE" if de is not None and de < 0.5 else ("MODERATE" if de is not None and de < 1.5 else "HIGH DEBT")),
         "score": 10 if de is not None and de < 0.1 else (8 if de is not None and de < 0.5 else (5 if de is not None and de < 1.0 else 2))},
        {"id": 17, "group": "Quality", "name": "WACC Estimate",
         "formula": f"Ke×E/(D+E) + Kd×(1−t)×D/(D+E) | Ke=14%, Kd=9.5%, t=25%, D/E={de}",
         "value": f"{wacc}%",
         "benchmark": "Hurdle rate — ROCE must beat WACC to create value",
         "verdict": f"HURDLE RATE · ROCE spread = +{roce_spread}%" if roce_spread else "HURDLE RATE",
         "score": 7},
        {"id": 18, "group": "Quality", "name": "Profit Growth",
         "formula": "(Net Profit FY26 − Net Profit FY25) ÷ Net Profit FY25 × 100",
         "value": f"{pg}%" if pg else "N/A",
         "benchmark": ">15% = good | >30% = strong | >50% = exceptional",
         "verdict": "EXCEPTIONAL" if pg and pg > 50 else ("STRONG" if pg and pg > 30 else ("GOOD" if pg and pg > 15 else ("WEAK" if pg and pg > 0 else "DECLINING"))),
         "score": 10 if pg and pg > 50 else (8 if pg and pg > 30 else (6 if pg and pg > 15 else (3 if pg and pg > 0 else 0)))},
        {"id": 19, "group": "Quality", "name": "Promoter Holding",
         "formula": "Promoter Shares ÷ Total Shares × 100",
         "value": f"{prom}%",
         "benchmark": ">50% = management aligned | <30% = concern",
         "verdict": "HIGHLY ALIGNED" if prom and prom > 55 else ("ALIGNED" if prom and prom > 40 else ("MODERATE" if prom and prom > 25 else "LOW CONVICTION")),
         "score": 9 if prom and prom > 55 else (7 if prom and prom > 45 else (5 if prom and prom > 30 else 2))},
        {"id": 20, "group": "Quality", "name": "Promoter Pledge",
         "formula": "Pledged Shares ÷ Promoter Shares × 100",
         "value": f"{pledg}%",
         "benchmark": "0% = clean | >5% = concern | >15% = red flag | >50% = KILL",
         "verdict": "CLEAN" if pledg == 0 else ("CAUTION" if pledg < 5 else ("RED FLAG" if pledg < 15 else "AVOID")),
         "score": 10 if pledg == 0 else (6 if pledg < 5 else (2 if pledg < 15 else 0))},
        {"id": 21, "group": "Quality", "name": "DuPont ROE Decomposition",
         "formula": "Net Margin × Asset Turnover × Equity Multiplier",
         "value": f"{roe}% total ROE",
         "benchmark": "Identifies whether ROE comes from margins, efficiency, or leverage",
         "verdict": "QUALITY ROE" if roe and roe > 20 and de is not None and de < 1.0 else ("LEVERAGED ROE" if roe and roe > 20 else ("WEAK" if roe and roe < 12 else "MODERATE")),
         "score": 9 if roe and roe > 20 and de is not None and de < 0.5 else (6 if roe and roe > 15 else 3)},
        {"id": 22, "group": "Quality", "name": "FII Flow Signal",
         "formula": "FII Holdings Change (QoQ)",
         "value": holders.get("trend", "N/A")[:50] if holders.get("trend") else "N/A",
         "benchmark": "Rising FII = institutional validation of the thesis",
         "verdict": "STRONG BUY SIGNAL" if holders.get("flow", 0) >= 8 else ("POSITIVE" if holders.get("flow", 0) >= 6 else ("NEUTRAL" if holders.get("flow", 0) >= 4 else "SELLING")),
         "score": holders.get("flow", 5)},
        {"id": 23, "group": "Quality", "name": "News Verdict",
         "formula": "Recent news sweep (Jun-Jul 2026) — catalyst / risk scan",
         "value": news.get("verdict", "N/A"),
         "benchmark": "CLEAR = no negative catalyst | CAUTION = watch for risks",
         "verdict": news.get("note", "")[:80] if news.get("note") else "N/A",
         "score": 9 if news.get("verdict") == "CLEAR" else (5 if news.get("verdict") == "CAUTION" else 3)},
        {"id": 24, "group": "Quality", "name": "Policy Tailwind",
         "formula": "Union Budget FY22-27 directness score (0-10)",
         "value": f"{policy}/10",
         "benchmark": "8-10 = directly in government spend | 5-7 = indirect | <5 = minimal",
         "verdict": "DIRECT BENEFICIARY" if policy >= 8 else ("INDIRECT" if policy >= 5 else "NO TAILWIND"),
         "score": policy},

        # MOMENTUM (25-36)
        {"id": 25, "group": "Momentum", "name": "6-Month Price Return",
         "formula": "(Current Price − Price 6M ago) ÷ Price 6M ago × 100",
         "value": f"{ret6}%" if ret6 is not None else "N/A",
         "benchmark": f"Nifty H1 2026: −7.5% | Outperforming = positive alpha",
         "verdict": "OUTPERFORMING" if ret6 and ret6 > -7.5 else "UNDERPERFORMING",
         "score": 10 if ret6 and ret6 > 10 else (7 if ret6 and ret6 > -5 else (5 if ret6 and ret6 > -15 else 2))},
        {"id": 26, "group": "Momentum", "name": "12-Month Price Return",
         "formula": "(Current Price − Price 12M ago) ÷ Price 12M ago × 100",
         "value": f"{ret12}%" if ret12 is not None else "N/A",
         "benchmark": "Nifty 1Y = ~−7%; strong momentum stocks >20%",
         "verdict": "STRONG MOMENTUM" if ret12 and ret12 > 30 else ("GOOD" if ret12 and ret12 > 10 else ("NEUTRAL" if ret12 and ret12 > -5 else "WEAK")),
         "score": 10 if ret12 and ret12 > 50 else (8 if ret12 and ret12 > 20 else (5 if ret12 and ret12 > 0 else 2))},
        {"id": 27, "group": "Momentum", "name": "Price vs 200-DMA",
         "formula": "(Price − DMA200) ÷ DMA200 × 100",
         "value": f"{ab200}%" if ab200 is not None else "N/A",
         "benchmark": "Above 200-DMA = long-term uptrend confirmed",
         "verdict": "UPTREND" if ab200 and ab200 > 0 else "DOWNTREND",
         "score": 9 if ab200 and ab200 > 10 else (7 if ab200 and ab200 > 0 else (3 if ab200 and ab200 > -10 else 1))},
        {"id": 28, "group": "Momentum", "name": "Price vs 50-DMA",
         "formula": "(Price − DMA50) ÷ DMA50 × 100",
         "value": f"{ab50}%" if ab50 is not None else "N/A",
         "benchmark": "Above 50-DMA = short-term uptrend | Below = correction phase",
         "verdict": "SHORT-TERM BULL" if ab50 and ab50 > 0 else "SHORT-TERM CORRECTION",
         "score": 8 if ab50 and ab50 > 5 else (6 if ab50 and ab50 > 0 else (4 if ab50 and ab50 > -5 else 2))},
        {"id": 29, "group": "Momentum", "name": "Golden Cross / Death Cross",
         "formula": "50-DMA vs 200-DMA relationship",
         "value": f"50-DMA {dma50} vs 200-DMA {dma200}" if dma50 and dma200 else "N/A",
         "benchmark": "50>200 = Golden Cross (bullish) | 50<200 = Death Cross (bearish)",
         "verdict": "GOLDEN CROSS ✓" if s.get("dma50_gt_dma200") else "DEATH CROSS ✗",
         "score": 9 if s.get("dma50_gt_dma200") else 2},
        {"id": 30, "group": "Momentum", "name": "RSI-14",
         "formula": "100 − 100 ÷ (1 + Avg14Gain ÷ Avg14Loss)",
         "value": f"{rsi}" if rsi else "N/A",
         "benchmark": "<30 = oversold (buy zone) | 30-70 = neutral | >70 = overbought",
         "verdict": "OVERSOLD (buy signal)" if rsi and rsi < 30 else ("NEUTRAL" if rsi and rsi < 55 else ("APPROACHING OVERBOUGHT" if rsi and rsi < 70 else "OVERBOUGHT")),
         "score": 9 if rsi and rsi < 35 else (8 if rsi and rsi < 50 else (6 if rsi and rsi < 60 else (4 if rsi and rsi < 70 else 2)))},
        {"id": 31, "group": "Momentum", "name": "MACD Signal",
         "formula": "EMA12 − EMA26 = MACD | MACD − EMA9(MACD) = Histogram",
         "value": f"MACD {round(macd,1)} | Signal | Hist {round(macd_h,1)}" if macd and macd_h else "N/A",
         "benchmark": "Positive histogram = bulls strengthening | negative = bears",
         "verdict": "BULLISH MOMENTUM" if s.get("macd_bull") else "BEARISH MOMENTUM",
         "score": 8 if s.get("macd_bull") and macd_h and macd_h > 0 else (5 if s.get("macd_bull") else 2)},
        {"id": 32, "group": "Momentum", "name": "Bollinger Band Position",
         "formula": "(Price − Lower Band) ÷ (Upper − Lower) × 100",
         "value": f"{bb}%" if bb is not None else "N/A",
         "benchmark": "<20% = near lower band (oversold zone) | >80% = overbought zone",
         "verdict": "NEAR LOWER BAND (buy zone)" if bb is not None and bb < 25 else ("MIDDLE (neutral)" if bb is not None and bb < 70 else "UPPER BAND (caution)"),
         "score": 9 if bb is not None and bb < 25 else (7 if bb is not None and bb < 55 else (5 if bb is not None and bb < 75 else 3))},
        {"id": 33, "group": "Momentum", "name": "Volume Ratio",
         "formula": "20-day avg volume ÷ 90-day avg volume",
         "value": f"{vol_r}x" if vol_r else "N/A",
         "benchmark": ">1.2 = money flowing in now | <0.8 = money leaving",
         "verdict": "ACCUMULATION" if vol_r and vol_r > 1.2 else ("NORMAL" if vol_r and vol_r > 0.8 else "DISTRIBUTION"),
         "score": 9 if vol_r and vol_r > 1.3 else (7 if vol_r and vol_r > 0.9 else (5 if vol_r and vol_r > 0.7 else 3))},
        {"id": 34, "group": "Momentum", "name": "Annualized Volatility",
         "formula": "Std Dev of Daily Returns × √252 × 100",
         "value": f"{vann}%" if vann else "N/A",
         "benchmark": "<25% = low risk | 25-40% = normal | >50% = high",
         "verdict": "LOW RISK" if vann and vann < 25 else ("NORMAL" if vann and vann < 40 else ("HIGH VOL" if vann and vann < 55 else "VERY HIGH VOL")),
         "score": 9 if vann and vann < 20 else (7 if vann and vann < 35 else (5 if vann and vann < 50 else 2))},
        {"id": 35, "group": "Momentum", "name": "Support Distance",
         "formula": "(Near Support − Current Price) ÷ Current Price × 100",
         "value": f"{sup_pct}%",
         "benchmark": "How far price must fall to hit nearest support",
         "verdict": "TIGHT SUPPORT" if abs(sup_pct) < 5 else ("MODERATE" if abs(sup_pct) < 12 else "FAR FROM SUPPORT"),
         "score": 8 if abs(sup_pct) < 5 else (6 if abs(sup_pct) < 10 else 4)},
        {"id": 36, "group": "Momentum", "name": "Resistance Distance",
         "formula": "(Near Resistance − Current Price) ÷ Current Price × 100",
         "value": f"+{res_pct}%",
         "benchmark": "How much upside before hitting selling pressure",
         "verdict": "CLEAR RUNWAY" if res_pct > 15 else ("MODERATE ROOM" if res_pct > 7 else "NEAR RESISTANCE"),
         "score": 9 if res_pct > 20 else (7 if res_pct > 10 else (5 if res_pct > 5 else 2))},

        # SAFETY (37-44)
        {"id": 37, "group": "Safety", "name": "Promoter Pledge Gate",
         "formula": "Pledged % = Pledged Promoter Shares ÷ Total Promoter Shares",
         "value": f"{pledg}% pledged",
         "benchmark": "HARD RULE: any pledge >5% = automatic caution; >15% = KILL signal",
         "verdict": "PASS ✓" if pledg == 0 else ("CAUTION ⚠" if pledg < 5 else "FAIL ✗"),
         "score": 10 if pledg == 0 else (5 if pledg < 5 else 0)},
        {"id": 38, "group": "Safety", "name": "Debt Safety",
         "formula": "D/E < 1.0 gate",
         "value": f"D/E = {de}x",
         "benchmark": "D/E > 1 = leveraged | >2 = risky | >3 = AVOID",
         "verdict": "PASS ✓" if de is not None and de < 1.0 else "FAIL ✗",
         "score": 10 if de is not None and de < 0.3 else (7 if de is not None and de < 1.0 else (3 if de is not None and de < 2.0 else 0))},
        {"id": 39, "group": "Safety", "name": "Profit Positive Gate",
         "formula": "Net Profit > 0 (PAT positive)",
         "value": "POSITIVE" if pe and pe > 0 else "NEGATIVE",
         "benchmark": "Loss-making companies excluded from screen",
         "verdict": "PASS ✓" if pe and pe > 0 else "FAIL ✗",
         "score": 10 if pe and pe > 0 else 0},
        {"id": 40, "group": "Safety", "name": "NIFTY 500 Membership Gate",
         "formula": "Listed on NIFTY 500 = minimum liquidity",
         "value": "IN NIFTY 500" if s.get("in_nifty200") or s.get("top_pick") else "N500 ONLY",
         "benchmark": "NIFTY 500 = minimum size/liquidity gate for institutional tradability",
         "verdict": "PASS ✓",
         "score": 8 if s.get("in_nifty200") else 6},
        {"id": 41, "group": "Safety", "name": "Position Sizing Rule",
         "formula": "Max position ≤ 5% of portfolio",
         "value": "≤5% cap",
         "benchmark": "Never bet more than 5% on one name regardless of conviction",
         "verdict": "APPLY THIS RULE",
         "score": 7},
        {"id": 42, "group": "Safety", "name": "Stop-Loss: 200-DMA Rule",
         "formula": "Sell if price < 200-DMA for 15+ consecutive sessions",
         "value": f"200-DMA = ₹{dma200}" if dma200 else "N/A",
         "benchmark": f"{'ABOVE 200-DMA ✓' if ab200 and ab200 > 0 else 'BELOW 200-DMA ✗ — monitor closely'}",
         "verdict": "HOLD" if ab200 and ab200 > 0 else "STOP-LOSS ZONE",
         "score": 9 if ab200 and ab200 > 0 else 2},
        {"id": 43, "group": "Safety", "name": "Risk/Reward Ratio (S/R based)",
         "formula": "Upside to Resistance ÷ Downside to Support",
         "value": f"{risk_reward_sr}" if risk_reward_sr else "N/A",
         "benchmark": ">2:1 = good trade setup | >3:1 = excellent",
         "verdict": "EXCELLENT SETUP" if risk_reward_sr and risk_reward_sr > 3 else ("GOOD" if risk_reward_sr and risk_reward_sr > 2 else ("FAIR" if risk_reward_sr and risk_reward_sr > 1.5 else "POOR")),
         "score": 10 if risk_reward_sr and risk_reward_sr > 3 else (7 if risk_reward_sr and risk_reward_sr > 2 else (4 if risk_reward_sr and risk_reward_sr > 1 else 2))},
        {"id": 44, "group": "Safety", "name": "Scenario Expected Value",
         "formula": "Bull×P(bull) + Base×P(base) + Bear×P(bear)",
         "value": f"+{scen.get('expected_value_pct','?')}% EV" if scen else "N/A",
         "benchmark": "EV > 0 = positive expected value | EV > 15% = strong bet",
         "verdict": "STRONG POSITIVE EV" if scen and scen.get("expected_value_pct", 0) > 20 else ("POSITIVE EV" if scen and scen.get("expected_value_pct", 0) > 5 else "MARGINAL"),
         "score": 10 if scen and scen.get("expected_value_pct", 0) > 25 else (7 if scen and scen.get("expected_value_pct", 0) > 10 else 4)},

        # CONFIDENCE + ZONE (45-50)
        {"id": 45, "group": "Confidence", "name": "Breakout / Breakdown Status",
         "formula": "Is price breaking key S/R levels in last 5 sessions?",
         "value": "BREAKING OUT ↑" if sr.get("breaking_out") else ("BREAKING DOWN ↓" if sr.get("breaking_down") else "RANGE-BOUND"),
         "benchmark": "Breakout above resistance = fresh buy | Breakdown below support = exit",
         "verdict": "STRONG BUY SIGNAL" if sr.get("breaking_out") else ("EXIT SIGNAL" if sr.get("breaking_down") else "WAIT FOR BREAKOUT"),
         "score": 10 if sr.get("breaking_out") else (2 if sr.get("breaking_down") else 6)},
        {"id": 46, "group": "Confidence", "name": "Zone Classification",
         "formula": "Current price vs support and resistance bands",
         "value": "BUY ZONE" if price <= near_sup * 1.04 else ("SELL ZONE" if price >= near_res * 0.97 else "HOLD ZONE"),
         "benchmark": "Near support = accumulate | Near resistance = take profit",
         "verdict": ("ACCUMULATE HERE" if price <= near_sup * 1.05
                     else ("BOOK PROFITS" if price >= near_res * 0.96
                     else "HOLD")),
         "score": 9 if price <= near_sup * 1.04 else (4 if price >= near_res * 0.97 else 7)},
        {"id": 47, "group": "Confidence", "name": "IVQM Composite Score",
         "formula": "Value(30) + Quality(30) + Momentum(25) + Safety(15)",
         "value": f"{sc.get('composite', '?')}/100",
         "benchmark": ">75 = strong | 60-75 = good | 45-60 = neutral | <45 = weak",
         "verdict": "STRONG BUY" if sc.get('composite', 0) > 75 else ("BUY" if sc.get('composite', 0) > 60 else ("NEUTRAL" if sc.get('composite', 0) > 45 else "AVOID")),
         "score": sc.get('composite', 50) // 10},
        {"id": 48, "group": "Confidence", "name": "Confidence Band",
         "formula": "Weighted average of all 47 sub-scores",
         "value": conf.get("band", "N/A"),
         "benchmark": "HIGH = strong conviction | MEDIUM = standard | LOW = speculative",
         "verdict": conf.get("why", "")[:80] if conf.get("why") else "N/A",
         "score": 9 if conf.get("band") == "HIGH" else (6 if conf.get("band") == "MEDIUM" else 3)},
        {"id": 49, "group": "Confidence", "name": "Catalyst / Trigger",
         "formula": "What event would confirm or invalidate the thesis",
         "value": conf.get("trigger", "N/A"),
         "benchmark": "Specific dates/events > vague catalysts",
         "verdict": conf.get("trigger", "N/A"),
         "score": 7},
        {"id": 50, "group": "Confidence", "name": "FINAL VERDICT — Overall Score",
         "formula": "All 49 equations → weighted composite signal",
         "value": None,  # computed below
         "benchmark": "≥75 = Strong Buy | 60-74 = Buy | 45-59 = Neutral | <45 = Avoid",
         "verdict": None,  # computed below
         "score": None},  # computed below
    ]

    # Compute equation 50 overall score
    scored = [e for e in equations[:-1] if e["score"] is not None]
    avg_score = sum(e["score"] for e in scored) / len(scored) if scored else 5
    overall = round(avg_score * 10, 1)
    verdict50 = ("STRONG BUY 🟢" if overall >= 75 else
                 "BUY 🟡" if overall >= 60 else
                 "NEUTRAL ⚪" if overall >= 45 else
                 "AVOID 🔴")
    equations[-1]["value"] = f"{overall}/100"
    equations[-1]["verdict"] = verdict50
    equations[-1]["score"] = round(avg_score, 1)

    # Price zones
    sup_lvls = sr.get("support", [])
    res_lvls = sr.get("resistance", [])
    buy_zone_lo = sup_lvls[1] if len(sup_lvls) > 1 else (near_sup * 0.97)
    buy_zone_hi = sup_lvls[0] if sup_lvls else (near_sup * 1.02)
    sell_zone_lo = res_lvls[0] if res_lvls else near_res
    sell_zone_hi = res_lvls[1] if len(res_lvls) > 1 else (near_res * 1.05)

    return {
        "as_of": str(date.today()),
        "overall_score": overall,
        "overall_verdict": verdict50,
        "equations": equations,
        "price_zones": {
            "buy_zone": {"lo": round(buy_zone_lo, 1), "hi": round(buy_zone_hi, 1),
                         "note": "Accumulation zone — where buying support is expected"},
            "sell_zone": {"lo": round(sell_zone_lo, 1), "hi": round(sell_zone_hi, 1),
                          "note": "Distribution zone — where selling pressure is expected"},
            "current_price": price,
            "zone": ("BUY ZONE" if price <= buy_zone_hi * 1.04 else
                     ("SELL ZONE" if price >= sell_zone_lo * 0.97 else "HOLD ZONE")),
        },
        "support_resistance": sr,
    }

# ─── Main Loop ───────────────────────────────────────────────────────────────
print("\nFetching 1-year OHLCV and computing math for each stock...\n")
for s in stocks:
    sym = s["symbol"]
    print(f"  {sym}...", end=" ", flush=True)
    ohlcv = fetch_ohlcv(sym)
    sr = compute_sr(
        ohlcv,
        s.get("price", 0),
        s.get("dma50"),
        s.get("dma200"),
    )
    s["math_detail"] = build_math_detail(s, sr)
    print(f"✓ ({len(ohlcv)} days)" if ohlcv else "✓ (derived)")

# ─── Write enhanced stocks.js ────────────────────────────────────────────────
out_str = "// generated by scripts/enhance_math.py — do not edit by hand\nwindow.STOCK_DATA = "
out_str += json.dumps(data, ensure_ascii=False, indent=1)
out_str += ";"
OUT_JS.write_text(out_str, encoding="utf-8")
print(f"\n✅ Written {len(stocks)} stocks with math_detail → {OUT_JS}")
print("   Run: git add public/data/stocks.js && git commit -m 'feat: enhanced 50-eq math' && git push")
