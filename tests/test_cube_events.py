"""The smile fit, the event-variance extraction, the density and the cost model on synthetic inputs, plus the
recorded sample chain end to end."""
import datetime as dt
import os

import numpy as np
import pandas as pd
import pytest

from ratesvol import cube as C
from ratesvol import data as D
from ratesvol import density as Z
from ratesvol import events as E
from ratesvol import pricing as P
from ratesvol import rv as R

SAMPLE = os.path.join(D.ROOT, "data", "sample", "chains")


def test_normal_sabr_limits():
    K = np.linspace(70, 95, 26)
    flat = C.normal_sabr(K, 82.0, 0.25, 10.0, 0.0, 1e-9)
    np.testing.assert_allclose(flat, 10.0, rtol=1e-9)
    assert C.normal_sabr(82.0, 82.0, 0.25, 10.0, -0.3, 0.8) == pytest.approx(10.0 * (1 + (2 - 3 * 0.09) / 24 * 0.64 * 0.25))
    smile = C.normal_sabr(K, 82.0, 0.25, 10.0, 0.0, 0.8)
    assert smile[0] > smile[12] and smile[-1] > smile[12]           # convex with zero rho
    skew = C.normal_sabr(K, 82.0, 0.25, 10.0, -0.5, 0.8)
    assert skew[0] > skew[-1]                                        # negative rho: low strikes rich


def test_fit_recovers_synthetic_smile():
    F, T = 82.0, 0.2
    K = np.linspace(74, 90, 33)
    true = (11.0, -0.25, 0.9)
    sig = C.normal_sabr(K, F, T, *true)
    a, rho, nu, rmse = C.fit_normal_sabr(K, F, T, sig)
    assert rmse < 1e-6
    assert a == pytest.approx(true[0], rel=1e-4) and rho == pytest.approx(true[1], abs=1e-3) and nu == pytest.approx(true[2], rel=1e-3)


def test_forward_from_parity_synthetic():
    F, DF, T, r = 82.4, np.exp(-0.04 * 0.2), 0.2, 0.04
    rows = []
    for K in np.arange(76, 89, 0.5):
        sig = 0.15
        c, p = DF * P.black_price(F, K, T, sig, True), DF * P.black_price(F, K, T, sig, False)
        rows.append({"strike": K, "call": True, "bid": c - 0.01, "ask": c + 0.01})
        rows.append({"strike": K, "call": False, "bid": p - 0.01, "ask": p + 0.01})
    o = pd.DataFrame(rows)
    Fhat, DFhat, n, disp = C.forward_from_parity(o, 82.0, r, T)
    assert Fhat == pytest.approx(F, abs=1e-9) and DFhat == pytest.approx(DF) and n >= 10 and disp < 1e-9


def test_event_extraction_recovers_known_jumps():
    """A ladder built from a diffusive 70 bp vol plus a 7 bp FOMC on day 20 and a 5 bp NFP on day 45."""
    asof = pd.Timestamp("2026-09-18 16:00")
    days = np.array([5, 12, 19, 26, 33, 40, 47, 54, 68, 82])
    T = days / 365.0
    diff = 70.0
    jumps = {20: 7.0, 45: 5.0}
    tv = diff ** 2 * T + sum(j ** 2 * (days >= d) for d, j in jumps.items())
    slices = pd.DataFrame({"T": T, "days": days, "atm_bpvol": np.sqrt(tv / T), "asof": asof})
    events = pd.DataFrame({"date": [asof.normalize() + pd.Timedelta(days=20), asof.normalize() + pd.Timedelta(days=45)], "type": ["FOMC", "NFP"]})
    d, J, res = E.extract_event_variance(slices, events, asof)
    assert d == pytest.approx(diff, rel=1e-6) and res < 1e-6
    assert J.set_index("type").loc["FOMC", "J_bp"] == pytest.approx(7.0, rel=1e-6)
    assert J.set_index("type").loc["NFP", "J_bp"] == pytest.approx(5.0, rel=1e-6)
    assert J["identified"].all()


def test_two_events_in_one_interval_are_flagged():
    asof = pd.Timestamp("2026-09-18 16:00")
    days = np.array([5, 30, 60])
    slices = pd.DataFrame({"T": days / 365.0, "days": days, "atm_bpvol": 70.0, "asof": asof})
    events = pd.DataFrame({"date": [asof.normalize() + pd.Timedelta(days=10), asof.normalize() + pd.Timedelta(days=20)], "type": ["FOMC", "NFP"]})
    _, J, _ = E.extract_event_variance(slices, events, asof, min_expiries=3)
    assert not J["identified"].any()


def test_density_integrates_and_matches_flat_smile():
    row = {"F": 82.0, "T": 0.25, "duration": 15.0, "alpha": 12.0, "rho": 0.0, "nu": 1e-6, "atm_bpvol": P.price_vol_to_yield_bp(12.0, 82.0, 15.0), "expiry": "x", "days": 91}
    d = Z.price_density(row)
    assert d["mass_raw"].iloc[0] == pytest.approx(1.0, abs=2e-3)
    tp = Z.tail_probabilities(row)
    assert tp["sd_density_bp"] == pytest.approx(tp["sd_atm_bp"], rel=0.03)
    assert tp["p_up_25"] + tp["p_dn_25"] == pytest.approx(tp["p_abs_25_gauss"], abs=0.01)
    assert abs(tp["skewness"]) < 0.35            # the log map from price to yield skews a symmetric price density


def test_cost_model_orders():
    total, hedge = R.cost_model(0.001, 6e-5, 0.11)
    assert 0 < hedge < total and total == pytest.approx(0.2 + hedge)
    assert R.straddle_hedge_turnover(21) == pytest.approx(2 * 0.398942 * np.sqrt(2 / np.pi) * np.sqrt(21))


def test_nfp_rule():
    d = D.nfp_dates(dt.date(2024, 1, 1), dt.date(2024, 12, 31))
    assert all(x.weekday() == 4 for x in d) and len(d) == 12
    assert pd.Timestamp("2024-06-07") in d and pd.Timestamp("2024-10-04") in d
    assert pd.Timestamp("2027-01-08") in D.nfp_dates(dt.date(2026, 12, 1), dt.date(2027, 1, 31))   # Jan 1 shifts


@pytest.mark.skipif(not os.path.isdir(SAMPLE), reason="no sample chains")
def test_sample_chain_fits_end_to_end():
    p = D.closing_snapshot("TLT", raw_dir=SAMPLE)
    und, s, q = C.fit_snapshot(p, duration=14.5, funding=0.04)
    assert len(s) >= 10 and len(q) > 300
    assert (s["rmse_bpvol"] < 40).all() and (s["atm_bpvol"].between(30, 200)).all()
    assert q["inside_market"].mean() > 0.2
    atm1m = C.interpolate_atm(s, 30)
    assert 40 < atm1m < 150
    grid = C.surface_grid(s)
    assert len(grid) == len(s) * 31
    costs = C.taking_cost_table(q)
    assert (costs["halfspread_bpvol"] > 0).all()
