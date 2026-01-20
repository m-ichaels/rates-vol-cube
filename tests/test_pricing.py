"""Pricing identities: solver round trips, parity, the lognormal-normal conversion, the bp conversions."""
import numpy as np
import pytest

from ratesvol import pricing as P


@pytest.fixture
def grid():
    F = np.full(7, 82.0)
    K = np.array([70, 76, 80, 82, 84, 88, 95.0])
    T = np.array([0.02, 0.05, 0.1, 0.25, 0.5, 1.0, 1.5])
    s = np.array([0.22, 0.17, 0.15, 0.14, 0.15, 0.17, 0.2])
    return F, K, T, s


def test_black_round_trip(grid):
    F, K, T, s = grid
    for call in (True, False):
        px = P.black_price(F, K, T, s, call)
        np.testing.assert_allclose(P.black_implied(px, F, K, T, call), s, atol=1e-9)


def test_bachelier_round_trip(grid):
    F, K, T, s = grid
    sn = s * F
    for call in (True, False):
        px = P.bachelier_price(F, K, T, sn, call)
        np.testing.assert_allclose(P.bachelier_implied(px, F, K, T, call), sn, atol=1e-8)


def test_put_call_parity(grid):
    F, K, T, s = grid
    np.testing.assert_allclose(P.black_price(F, K, T, s, True) - P.black_price(F, K, T, s, False), F - K, atol=1e-12)
    np.testing.assert_allclose(P.bachelier_price(F, K, T, s * F, True) - P.bachelier_price(F, K, T, s * F, False), F - K, atol=1e-12)


def test_prices_outside_bounds_give_nan():
    iv = P.black_implied(np.array([0.0, 100.0, -1.0]), 82.0, 82.0, 0.1, True)
    assert np.isnan(iv).all()
    assert np.isnan(P.bachelier_implied(np.array([90.0]), 82.0, 82.0, 0.1, True)).all()


def test_greeks_by_bump(grid):
    F, K, T, s = grid
    h = 1e-4
    vega_fd = (P.black_price(F, K, T, s + h, True) - P.black_price(F, K, T, s - h, True)) / (2 * h)
    np.testing.assert_allclose(P.black_vega(F, K, T, s), vega_fd, rtol=1e-4)
    delta_fd = (P.black_price(F + h, K, T, s, True) - P.black_price(F - h, K, T, s, True)) / (2 * h)
    np.testing.assert_allclose(P.black_delta(F, K, T, s, True), delta_fd, rtol=1e-5)
    gamma_fd = (P.black_price(F + h, K, T, s, True) - 2 * P.black_price(F, K, T, s, True) + P.black_price(F - h, K, T, s, True)) / h ** 2
    np.testing.assert_allclose(P.black_gamma(F, K, T, s), gamma_fd, rtol=1e-3, atol=1e-5)
    sn = s * F
    vega_n = (P.bachelier_price(F, K, T, sn + h, True) - P.bachelier_price(F, K, T, sn - h, True)) / (2 * h)
    np.testing.assert_allclose(P.bachelier_vega(F, K, T, sn), vega_n, rtol=1e-4)
    gamma_n = (P.bachelier_price(F + h, K, T, sn, True) - 2 * P.bachelier_price(F, K, T, sn, True) + P.bachelier_price(F - h, K, T, sn, True)) / h ** 2
    np.testing.assert_allclose(P.bachelier_gamma(F, K, T, sn), gamma_n, rtol=1e-3, atol=1e-5)


def test_lognormal_to_normal_matches_the_solver(grid):
    """Hagan's second-order conversion against the exact Bachelier implied vol of the Black price."""
    F, K, T, s = grid
    px = P.black_price(F, K, T, s, True)
    exact = P.bachelier_implied(px, F, K, T, True)
    approx = P.lognormal_to_normal(s, F, K, T)
    np.testing.assert_allclose(approx, exact, rtol=2e-3)


def test_bp_conversions():
    # 15 % lognormal on a fund with duration 15 at price 80: normal $ vol 12 -> 100 bp of yield per year
    assert P.price_vol_to_yield_bp(0.15 * 80, 80, 15) == pytest.approx(100.0)
    # a strike 1 % below the forward on duration 10 is ~10 bp higher in yield
    assert P.strike_to_yield_bp(80 * np.exp(-0.01), 80, 10) == pytest.approx(10.0)
    assert P.strike_to_yield_bp(80, 80, 10) == 0.0


def test_atm_straddle_normal():
    F, T, sn = 82.0, 0.25, 12.0
    straddle = P.bachelier_price(F, F, T, sn, True) + P.bachelier_price(F, F, T, sn, False)
    assert P.straddle_price_normal(F, T, sn) == pytest.approx(straddle)
    assert straddle == pytest.approx(sn * np.sqrt(T) * np.sqrt(2 / np.pi))
