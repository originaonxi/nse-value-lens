"""Mechanics of the Nifty chain desk: Greeks, official-file parsers, swing structure, strikes, payoffs, no look-ahead.

Synthetic data only, so the suite runs in CI without the bhavcopy cache or network access."""
import math
import unittest

import numpy as np
import pandas as pd

import nifty_chain as nc
import options_desk as od

PARTICIPANT_TEXT = '''""Participant wise Open Interest (no. of contracts) in Equity Derivatives as on Oct 14, 2026"",,,,,,,,,,,,,,
Client Type,Future Index Long,Future Index Short,Future Stock Long,Future Stock Short       ,Option Index Call Long,Option Index Put Long,Option Index Call Short,Option Index Put Short,Option Stock Call Long,Option Stock Put Long,Option Stock Call Short,Option Stock Put Short,Total Long Contracts      ,Total Short Contracts
Client,296818,51460,3442948,220873,3171120,2489251,2983699,3195752,2305477,926001,1317864,1144399,12631615,8914047
DII,48983,18961,311483,4708564,100123,75950,1740,0,12320,46150,380316,41830,595009,5151411
FII,34282,330979,3594546,2850560,675757,1095900,1008663,551135,258814,372071,424801,239005,6031370,5405143
Pro,54685,33368,843800,412780,1056241,896996,1009140,811210,1029723,1077563,1483353,996551,4959009,4746402
TOTAL,434768,434768,8192777,8192777,5003242,4558097,5003242,4558097,3606334,2421785,3606334,2421785,24217002,24217002
'''

INDEX_TEXT = '''Index Name,Index Date,Open Index Value,High Index Value,Low Index Value,Closing Index Value,Points Change,Change(%),Volume,Turnover (Rs. Cr.),P/E,P/B,Div Yield
Nifty 50,14-10-2026,22715.75,22757.95,22558.95,22622.7,-99.25,-.44,333248082,30396.7,19.33,2.78,1.52
India VIX,14-10-2026,14.12,15.015,13.795,14.63,0.51,3.58,-,-,-,-,-
'''


class GreekTests(unittest.TestCase):
    def test_put_call_delta_and_shared_gamma_vega(self):
        s, k, t, v = 22600.0, np.array([22000.0, 22600.0, 23200.0]), 13 / 365, 0.13
        c, p = nc.greeks(s, k, t, v, 1.0), nc.greeks(s, k, t, v, 0.0)
        np.testing.assert_allclose(c["delta"] - p["delta"], 1.0, atol=1e-12)
        np.testing.assert_allclose(c["gamma"], p["gamma"])
        np.testing.assert_allclose(c["vega"], p["vega"])
        self.assertTrue((c["theta"] < 0).all())
        self.assertTrue((np.diff(c["delta"]) < 0).all())  # call delta falls as strike rises

    def test_greeks_match_finite_differences_of_the_desk_pricer(self):
        s, k, t, v = 22600.0, 22800.0, 20 / 365, 0.14
        for call in (1.0, 0.0):
            g = nc.greeks(s, k, t, v, call)
            price = lambda ss=s, tt=t, vv=v: float(od.bs_price(ss, k, tt, vv, call))
            h = 1.0
            self.assertAlmostEqual(float(g["delta"]), (price(ss=s + h) - price(ss=s - h)) / (2 * h), places=4)
            self.assertAlmostEqual(float(g["gamma"]), (price(ss=s + h) - 2 * price() + price(ss=s - h)) / h ** 2, places=5)
            self.assertAlmostEqual(float(g["vega"]), (price(vv=v + 1e-4) - price(vv=v - 1e-4)) / 2e-4 / 100, places=3)
            self.assertAlmostEqual(float(g["theta"]), (price(tt=t - 1 / 365) - price()) , delta=abs(float(g["theta"])) * 0.03)

    def test_strike_picks_from_a_model_priced_chain(self):
        spot, dte, vol = 22600.0, 20, 0.15
        strikes = np.arange(21000.0, 24250.0, 50.0)
        t = dte / 365
        rows = []
        for opt, call in (("CE", 1.0), ("PE", 0.0)):
            prices = od.bs_price(spot, strikes, t, vol, call)
            for k, pr in zip(strikes, prices):
                rows.append(dict(OptnTp=opt, StrkPric=k, mark=round(float(pr), 2), OpnIntrst=1000 + (5000 if (opt, k) in (("CE", 23500.0), ("PE", 22000.0)) else 0),
                                 ChngInOpnIntrst=0, TtlTradgVol=10, NewBrdLotQty=65, ClsPric=round(float(pr), 2), exp="2026-11-03"))
        tab = nc.strike_table(pd.DataFrame(rows), spot, dte)
        pk = nc.picks(tab, spot, dte)
        self.assertEqual(pk["atm"], 22600.0)
        self.assertAlmostEqual(pk["atm_iv"], 15.0, delta=0.1)
        self.assertEqual(pk["call_wall"], 23500.0)
        self.assertEqual(pk["put_wall"], 22000.0)
        c20 = float(nc.greeks(spot, pk["c20"], t, vol, 1.0)["delta"])
        p20 = float(nc.greeks(spot, pk["p20"], t, vol, 0.0)["delta"])
        self.assertAlmostEqual(c20, 0.20, delta=0.03)
        self.assertAlmostEqual(p20, -0.20, delta=0.03)
        self.assertGreater(pk["cw"], pk["c20"])
        self.assertLess(pk["pw"], pk["p20"])
        self.assertAlmostEqual(pk["skew25"], 0.0, delta=0.1)  # flat smile in, flat skew out


class OfficialFileTests(unittest.TestCase):
    def test_participant_file(self):
        p = nc.parse_participants(PARTICIPANT_TEXT)
        self.assertEqual(p["FII"]["fut_long"], 34282)
        self.assertEqual(p["FII"]["fut_short"], 330979)
        self.assertEqual(p["Client"]["put_short"], 3195752)
        total_long = sum(p[w]["fut_long"] for w in nc.PARTICIPANTS)
        self.assertEqual(total_long, p["TOTAL"]["fut_long"])

    def test_participant_file_rejects_truncation(self):
        with self.assertRaises(ValueError):
            nc.parse_participants("\n".join(PARTICIPANT_TEXT.splitlines()[:4]))

    def test_index_close_file(self):
        ic = nc.parse_index_close(INDEX_TEXT)
        self.assertEqual(ic["Nifty 50"]["close"], 22622.7)
        self.assertEqual(ic["India VIX"]["close"], 14.63)
        self.assertIsNone(ic["India VIX"]["pe"])
        with self.assertRaises(ValueError):
            nc.parse_index_close(INDEX_TEXT.replace("Nifty 50", "Nifty Next 50"))


def ohlc_from(closes):
    idx = pd.bdate_range("2026-01-01", periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame(dict(Open=c, High=c + 5, Low=c - 5, Close=c, Volume=0.0))


class StructureTests(unittest.TestCase):
    def wave(self, drift):
        base = [100, 110, 120, 110, 100, 115, 130, 118, 106, 125, 140, 128, 116, 135, 150, 138, 126]
        return [b + drift * i for i, b in enumerate(base)] if drift >= 0 else [300 - b + drift * i for i, b in enumerate(base)]

    def test_rising_and_falling_structure(self):
        up = nc.swing_structure(ohlc_from(self.wave(0)))
        self.assertTrue(bool(up.rising.iloc[-1]))
        self.assertEqual(up.structure.iloc[-1], "HH / HL")
        down = nc.swing_structure(ohlc_from(self.wave(-1)))
        self.assertTrue(bool(down.falling.iloc[-1]))
        self.assertEqual(down.structure.iloc[-1], "LH / LL")

    def test_pivot_is_known_only_two_sessions_later(self):
        closes = self.wave(0)
        full = nc.swing_structure(ohlc_from(closes))
        for cut in range(5, len(closes)):
            part = nc.swing_structure(ohlc_from(closes[:cut]))
            pd.testing.assert_frame_equal(part, full.iloc[:cut], check_freq=False)
        # peak at bar 2 (120) is confirmed at bar 4, not before
        self.assertTrue(np.isnan(full.confirmed_high.iloc[3]))
        self.assertEqual(full.confirmed_high.iloc[4], 125.0)


class PayoffAndCapitalTests(unittest.TestCase):
    def test_bull_call_spread_payoff(self):
        legs = [dict(option_type="CE", strike=22600.0, side="BUY", ref_close=250.0),
                dict(option_type="CE", strike=23050.0, side="SELL", ref_close=90.0)]
        p = nc.payoff_profile(legs, 22600.0, 65, 0.13, 13)
        self.assertAlmostEqual(p["max_loss"], -160 * 65, delta=1)
        self.assertAlmostEqual(p["max_profit"], (450 - 160) * 65, delta=1)
        self.assertEqual(len(p["breakevens"]), 1)
        self.assertAlmostEqual(p["breakevens"][0], 22760.0, delta=1)
        self.assertTrue(0 < p["prob_profit_model"] < 50)

    def test_short_straddle_is_unlimited(self):
        legs = [dict(option_type="CE", strike=22600.0, side="SELL", ref_close=250.0),
                dict(option_type="PE", strike=22600.0, side="SELL", ref_close=200.0)]
        p = nc.payoff_profile(legs, 22600.0, 65, 0.13, 13)
        self.assertIsNone(p["max_loss"])
        self.assertAlmostEqual(p["max_profit"], 450 * 65, delta=1)
        self.assertEqual(len(p["breakevens"]), 2)

    def test_capital_bases(self):
        debit = [dict(opt="CE", strike=100, side="BUY", entry=10), dict(opt="CE", strike=110, side="SELL", entry=4)]
        self.assertAlmostEqual(nc.capital("debit", debit, 100, 2), 12)
        condor = [dict(opt="CE", strike=110, side="SELL", entry=3), dict(opt="CE", strike=115, side="BUY", entry=1),
                  dict(opt="PE", strike=90, side="SELL", entry=3), dict(opt="PE", strike=85, side="BUY", entry=1)]
        self.assertAlmostEqual(nc.capital("defined", condor, 100, 1), 5 - 4)  # wing width minus net credit
        self.assertAlmostEqual(nc.capital("margin", condor, 100, 2), od.MARGIN["index"] * 100 * 2)


def features(n=40):
    days = pd.bdate_range("2026-01-01", periods=n).strftime("%Y-%m-%d").tolist()
    feat = pd.DataFrame(dict(date=days, spot=[22000 + 10 * i for i in range(n)], lot=65, foi=[1e7 + 1e4 * i for i in range(n)],
                             fut_close=[22020 + 10 * i for i in range(n)], ce_oi=1e6, pe_oi=[9e5 + 1e3 * i for i in range(n)],
                             texp="2026-12-29", dte=30, atm=22000.0, atm_ce=200.0, atm_pe=180.0, atm_iv=[12 + (i % 5) for i in range(n)],
                             skew25=2.0))
    part = pd.DataFrame([dict(date=d, **{f"{w.lower()}_{k}": 1000 + i * (5 if w == "FII" else 1) for k in nc.PART_COLS.values()})
                         for i, d in enumerate(days) for w in ["FII"]][:n])
    for w in ("dii", "pro", "client"):
        for k in nc.PART_COLS.values():
            part[f"{w}_{k}"] = 500
    return feat, part, days


class NoLookaheadTests(unittest.TestCase):
    def test_derived_features_ignore_future_sessions(self):
        feat, part, days = features()
        ohlc = ohlc_from(list(feat.spot))
        ohlc.index = pd.to_datetime(days)
        full = nc.derive(feat, ohlc, part, days)
        cut = 30
        early = nc.derive(feat.iloc[:cut], ohlc.iloc[:cut], part.iloc[:cut], days[:cut])
        cols = ["ret5", "sig5", "z5", "rv20", "pcr", "pcr_chg5", "foi5", "iv_pct", "vrp", "rising", "falling", "fii_ratio", "fii_ratio_chg5", "valid"]
        pd.testing.assert_frame_equal(early[cols].reset_index(drop=True), full[cols].iloc[:cut].reset_index(drop=True))

    def test_gap_in_sessions_blocks_lagged_values(self):
        feat, part, days = features()
        ohlc = ohlc_from(list(feat.spot))
        ohlc.index = pd.to_datetime(days)
        holed = feat.drop(index=20).reset_index(drop=True)
        d = nc.derive(holed, ohlc, part, days)
        self.assertTrue(np.isnan(d[d.date == days[21]].iloc[0].ret1))
        self.assertTrue(np.isnan(d[d.date == days[25]].iloc[0].ret5))

    def test_simulation_enters_next_open_and_charges_costs(self):
        days = pd.bdate_range("2026-03-02", periods=8).strftime("%Y-%m-%d").tolist()
        sig = pd.DataFrame([dict(date=days[0], sidx=0, spot=22000.0, lot=65, texp="2026-04-28", symbol="NIFTY", kind="index",
                                 rule="base_buy_call", nlegs=1, l0_opt="CE", l0_strike=22000.0, l0_side="BUY", l0_ref=200.0)])
        sig = od.non_overlapping(sig, days)
        key = ("2026-04-28", 22000.0, "CE")
        books = {d: {key: (200.0 + 10 * i, 205.0 + 10 * i)} for i, d in enumerate(days)}
        t = nc.simulate(sig, books, days)
        self.assertEqual(t.iloc[0].entry_date, days[1])
        self.assertEqual(t.iloc[0].exit_date, days[nc.HOLD])
        entry, exit_ = 215.0, 200.0 + 10 * nc.HOLD
        gross = (exit_ - entry) * 65
        self.assertLess(t.iloc[0].pnl_per_lot, gross)
        self.assertGreater(t.iloc[0].pnl_per_lot, gross - 0.05 * gross - 200)
        self.assertAlmostEqual(t.iloc[0].return_pct, 100 * t.iloc[0].pnl_per_lot / (entry * 65), places=6)

    def test_unfilled_leg_drops_the_trade(self):
        days = pd.bdate_range("2026-03-02", periods=8).strftime("%Y-%m-%d").tolist()
        sig = od.non_overlapping(pd.DataFrame([dict(date=days[0], sidx=0, spot=22000.0, lot=65, texp="2026-04-28", symbol="NIFTY",
                                                    kind="index", rule="base_bull_call_spread", nlegs=2, l0_opt="CE", l0_strike=22000.0,
                                                    l0_side="BUY", l0_ref=200.0, l1_opt="CE", l1_strike=22450.0, l1_side="SELL", l1_ref=60.0)]), days)
        books = {d: {("2026-04-28", 22000.0, "CE"): (200.0, 201.0), ("2026-04-28", 22450.0, "CE"): (60.0, float("nan"))} for d in days}
        self.assertTrue(nc.simulate(sig, books, days).empty)


class RuleTests(unittest.TestCase):
    def test_every_rule_has_a_baseline_and_known_strike_keys(self):
        keys = {"atm", "bcs", "bps", "c20", "p20", "cw", "pw"}
        for r in nc.RULES:
            self.assertIn(nc.BASELINE_FOR[r["action"]], nc.RULE_BY_ID)
            for opt, key, side in r["legs"]:
                self.assertIn(key, keys)
                self.assertIn(opt, ("CE", "PE"))
                self.assertIn(side, ("BUY", "SELL"))

    def test_jev_setup_choices_cover_every_tradable_rule(self):
        rules = [dict(id=r["id"], label=r["label"], action=r["action"], status="WEAK", baseline=r["baseline"]) for r in nc.RULES]
        crit = nc._setup_criteria(rules)
        self.assertIn("no_trade", crit)
        self.assertEqual(set(crit) - {"no_trade"}, {r["id"] for r in nc.RULES if not r["baseline"]})


if __name__ == "__main__":
    unittest.main()
