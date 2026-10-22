"""Offline tests for nifty_scenarios maths: payoffs, fills, probabilities, triggers, selection."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nifty_scenarios as ns  # noqa: E402


def leg(side, strike, typ, fill):
    return dict(side=side, strike=strike, type=typ, fill=fill)


def test_bull_call_spread_max_profit_and_loss():
    legs = [leg("BUY", 22800, "CE", 176.95), leg("SELL", 23150, "CE", 73.15)]
    mp, ml = ns.max_pl(legs, 65)
    debit = 176.95 - 73.15
    assert ml == pytest.approx(-debit * 65)
    assert mp == pytest.approx((350 - debit) * 65)


def test_bear_put_spread_breakeven_and_caps():
    legs = [leg("BUY", 22500, "PE", 182.3), leg("SELL", 22100, "PE", 75.9)]
    mp, ml = ns.max_pl(legs, 65)
    assert ml == pytest.approx(-(182.3 - 75.9) * 65)
    assert mp == pytest.approx((400 - 106.4) * 65)
    (be,) = ns.breakevens(legs, 22600)
    assert be == pytest.approx(22500 - 106.4, abs=1)


def test_iron_butterfly_defined_risk_both_sides():
    legs = [leg("SELL", 22600, "PE", 223.3), leg("SELL", 22600, "CE", 272.2),
            leg("BUY", 22100, "PE", 76.3), leg("BUY", 23100, "CE", 83.75)]
    mp, ml = ns.max_pl(legs, 65)
    credit = 223.3 + 272.2 - 76.3 - 83.75
    assert mp == pytest.approx(credit * 65)
    assert ml == pytest.approx(-(500 - credit) * 65)
    assert len(ns.breakevens(legs, 22600)) == 2


def test_naked_short_call_has_no_max_loss():
    mp, ml = ns.max_pl([leg("SELL", 23000, "CE", 50)], 65)
    assert ml is None and mp == pytest.approx(50 * 65)


def test_fill_uses_ask_to_buy_bid_to_sell_and_ltp_when_wide():
    tight = dict(bid=100.0, ask=101.0, ltp=100.5)
    assert ns.fill(tight, "BUY") == (101.0, "ask")
    assert ns.fill(tight, "SELL") == (100.0, "bid")
    wide = dict(bid=80.0, ask=120.0, ltp=100.0)
    assert ns.fill(wide, "BUY") == (100.0, "ltp")


def test_bucket_and_blend_sum_to_one():
    b = ns.bucket([0.02, -0.02, 0.0, 0.005, -0.011])
    assert b["bull"] + b["side"] + b["bear"] == pytest.approx(1)
    assert b["bear"] == pytest.approx(0.4)
    srcs = dict(a=dict(bull=.2, side=.5, bear=.3), b=dict(bull=.4, side=.3, bear=.3), c=None)
    out = ns.blend(srcs)
    assert sum(out.values()) == pytest.approx(1, abs=1e-3)
    assert out["bull"] == pytest.approx(0.3, abs=1e-3)


def test_implied_probs_reasonable():
    p = ns.implied_probs(0.15, 7)
    assert p["bull"] + p["side"] + p["bear"] == pytest.approx(1)
    sig = 0.15 * math.sqrt(7 / 365)
    assert p["side"] == pytest.approx(ns.ncdf(0.01 / sig) - ns.ncdf(-0.01 / sig), abs=0.03)


def test_triggers_bear_active_below_averages():
    a = dict(values=dict(ema9=22768, tp20=22754), structure=dict(high=22776, low=22288),
             oi=dict(call_wall=23000, put_wall=22000), prev=dict(high=23121, low=22650, close=22811))
    t = ns.triggers(a, dict(low=22555, high=22785), 22620)
    assert t["bear"]["active"] and not t["bull"]["active"]
    assert t["bear"]["stop"] == pytest.approx(22768, abs=1)
    assert t["side"]["range"] == [22288, 22776]


def test_best_structures_requires_profit_in_its_scenario():
    good = dict(scenario="bear", kind="Bear put spread", if_=dict(bull=-5, side=-1, bear=50), cond=dict(bull=-6, side=-1, bear=60),
                center=30, max_loss=-100)
    bad = dict(scenario="bear", kind="Long put", if_=dict(bull=-5, side=-1, bear=-1), cond=dict(bull=-6, side=-1, bear=-1),
               center=-1, max_loss=-100)
    picked = ns.best_structures([good, bad], "bear", dict(bull=.3, side=.4, bear=.3))
    assert picked == [good] and good["score"] == pytest.approx(0.5)


def _ev(name, scen, kind, own, risk=100):
    cond = {s: (own if s == scen else -own / 2) for s in ("bull", "side", "bear")}
    return dict(name=name, scenario=scen, kind=kind, if_=dict(cond), cond=dict(cond), center=own, max_loss=-risk)


def test_select_cards_covers_all_views_and_caps_count():
    evals = [_ev(f"b{i}", "bull", "Bull call spread", 10 + i) for i in range(5)]
    evals += [_ev(f"r{i}", "bear", "Bear put spread", 20 + i) for i in range(5)]
    evals += [_ev(f"s{i}", "side", "Iron condor", 5 + i) for i in range(5)]
    evals += [_ev("loser", "bull", "Long call", -5)]
    picked = ns.select_cards(evals, dict(bull=.3, side=.4, bear=.3), n=8)
    names = [p["name"] for p in picked]
    assert len(picked) == 8 and len(set(names)) == 8 and "loser" not in names
    assert {p["scenario"] for p in picked} == {"bull", "side", "bear"}


def test_scenario_stats_best_worst_avg():
    pnl = np.where(ns.GRID < 0, -100.0, 200.0)
    e = dict(_pnl_x=pnl, cond=dict(bull=200, side=50, bear=-100))
    st = ns.scenario_stats(e)
    assert st["bull"]["best"] == 200 and st["bear"]["worst"] == -100
    assert st["side"]["best"] == 200 and st["side"]["worst"] == -100 and st["side"]["avg"] == 50
