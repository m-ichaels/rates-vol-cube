"""Option pricing in the two conventions a rates desk uses: Black (1976) on the forward, in which listed ETF and
futures options are quoted, and Bachelier (normal), in which swaptions and STIR options are quoted and in which a
rates trader thinks - a normal vol is a basis-point vol, comparable across strikes, tenors and instruments.

Everything is vectorised over numpy arrays.  T in years, r continuously compounded, F the forward, K the strike;
prices are undiscounted (forward) values unless `df` is given.  Implied vols are solved by a safeguarded Newton
iteration from a bracketing bisection start; tests check the round trip to 1e-10 in vol.
"""
from __future__ import annotations

import numpy as np
from scipy.special import erf

SQRT2 = np.sqrt(2.0)
INV_SQRT_2PI = 1.0 / np.sqrt(2.0 * np.pi)


def ncdf(x):
    return 0.5 * (1.0 + erf(np.asarray(x, dtype=float) / SQRT2))


def npdf(x):
    x = np.asarray(x, dtype=float)
    return INV_SQRT_2PI * np.exp(-0.5 * x * x)


# ---- Black (1976) ------------------------------------------------------------------------------------------------------
def black_price(F, K, T, sigma, call=True, df=1.0):
    F, K, T, sigma = (np.asarray(v, dtype=float) for v in (F, K, T, sigma))
    s = np.maximum(sigma, 1e-12) * np.sqrt(np.maximum(T, 1e-12))
    d1 = np.log(F / K) / s + 0.5 * s
    d2 = d1 - s
    sign = 1.0 if call else -1.0
    intrinsic = np.maximum(sign * (F - K), 0.0)
    val = sign * (F * ncdf(sign * d1) - K * ncdf(sign * d2))
    return df * np.where(T <= 0, intrinsic, val)


def black_vega(F, K, T, sigma, df=1.0):
    F, K, T, sigma = (np.asarray(v, dtype=float) for v in (F, K, T, sigma))
    s = np.maximum(sigma, 1e-12) * np.sqrt(np.maximum(T, 1e-12))
    d1 = np.log(F / K) / s + 0.5 * s
    return df * F * npdf(d1) * np.sqrt(np.maximum(T, 1e-12))


def black_delta(F, K, T, sigma, call=True, df=1.0):
    F, K, T, sigma = (np.asarray(v, dtype=float) for v in (F, K, T, sigma))
    s = np.maximum(sigma, 1e-12) * np.sqrt(np.maximum(T, 1e-12))
    d1 = np.log(F / K) / s + 0.5 * s
    return df * (ncdf(d1) if call else ncdf(d1) - 1.0)


def black_gamma(F, K, T, sigma, df=1.0):
    F, K, T, sigma = (np.asarray(v, dtype=float) for v in (F, K, T, sigma))
    s = np.maximum(sigma, 1e-12) * np.sqrt(np.maximum(T, 1e-12))
    d1 = np.log(F / K) / s + 0.5 * s
    return df * npdf(d1) / (F * s)


# ---- Bachelier (normal) ----------------------------------------------------------------------------------------------
def bachelier_price(F, K, T, sigma_n, call=True, df=1.0):
    """sigma_n in price units per sqrt(year) (for an ETF: dollars; for a rate: decimal or bp, consistently)."""
    F, K, T, sigma_n = (np.asarray(v, dtype=float) for v in (F, K, T, sigma_n))
    s = np.maximum(sigma_n, 1e-14) * np.sqrt(np.maximum(T, 1e-12))
    sign = 1.0 if call else -1.0
    d = sign * (F - K) / s
    intrinsic = np.maximum(sign * (F - K), 0.0)
    val = sign * (F - K) * ncdf(d) + s * npdf(d)
    return df * np.where(T <= 0, intrinsic, val)


def bachelier_vega(F, K, T, sigma_n, df=1.0):
    F, K, T, sigma_n = (np.asarray(v, dtype=float) for v in (F, K, T, sigma_n))
    sT = np.sqrt(np.maximum(T, 1e-12))
    d = (F - K) / (np.maximum(sigma_n, 1e-14) * sT)
    return df * sT * npdf(d)


def bachelier_delta(F, K, T, sigma_n, call=True, df=1.0):
    F, K, T, sigma_n = (np.asarray(v, dtype=float) for v in (F, K, T, sigma_n))
    d = (F - K) / (np.maximum(sigma_n, 1e-14) * np.sqrt(np.maximum(T, 1e-12)))
    return df * (ncdf(d) if call else ncdf(d) - 1.0)


def bachelier_gamma(F, K, T, sigma_n, df=1.0):
    F, K, T, sigma_n = (np.asarray(v, dtype=float) for v in (F, K, T, sigma_n))
    s = np.maximum(sigma_n, 1e-14) * np.sqrt(np.maximum(T, 1e-12))
    return df * npdf((F - K) / s) / s


# ---- implied vols --------------------------------------------------------------------------------------------------------
def _implied(price_fn, vega_fn, price, F, K, T, call, lo, hi, tol=1e-10, max_iter=100):
    """Bisection to bracket, then Newton with the bisection bracket as a safeguard.  NaN where the price is
    outside the no-arbitrage bounds (below intrinsic or above the forward / strike)."""
    price, F, K, T = np.broadcast_arrays(*(np.asarray(v, dtype=float) for v in (price, F, K, T)))
    price, F, K, T = (np.array(v, dtype=float).ravel() for v in (price, F, K, T))
    n = price.size
    lo = np.full(n, lo)
    hi = np.full(n, hi)
    sign = 1.0 if call else -1.0
    intrinsic = np.maximum(sign * (F - K), 0.0)
    upper = F if call else K                                    # a call is worth less than the forward, a put less than the strike
    ok = (price > intrinsic) & (price < upper) & (T > 0) & np.isfinite(price)
    sig = np.full(n, np.nan)
    if not ok.any():
        return sig.reshape(np.broadcast(np.asarray(price)).shape)
    # widen the upper bracket until the model price exceeds the target (or give up)
    for _ in range(40):
        p_hi = price_fn(F, K, T, hi, call)
        need = ok & (p_hi < price)
        if not need.any():
            break
        hi = np.where(need, hi * 2.0, hi)
    x = 0.5 * (lo + hi)
    for _ in range(max_iter):
        p = price_fn(F, K, T, x, call)
        v = vega_fn(F, K, T, x)
        diff = p - price
        # update the bracket
        lo = np.where(diff < 0, x, lo)
        hi = np.where(diff > 0, x, hi)
        newton = x - diff / np.where(v > 1e-300, v, np.nan)
        inside = np.isfinite(newton) & (newton > lo) & (newton < hi)
        x_new = np.where(inside, newton, 0.5 * (lo + hi))
        done = np.abs(x_new - x) < tol * np.maximum(1.0, x)
        x = np.where(ok, x_new, x)
        if done[ok].all():
            break
    sig[ok] = x[ok]
    return sig


def black_implied(price, F, K, T, call=True):
    return _implied(lambda F, K, T, s, c: black_price(F, K, T, s, c), lambda F, K, T, s: black_vega(F, K, T, s),
                    price, F, K, T, call, lo=1e-6, hi=2.0)


def bachelier_implied(price, F, K, T, call=True):
    F_arr = np.asarray(F, dtype=float)
    scale = float(np.nanmedian(F_arr)) if F_arr.size else 1.0
    return _implied(lambda F, K, T, s, c: bachelier_price(F, K, T, s, c), lambda F, K, T, s: bachelier_vega(F, K, T, s),
                    price, F, K, T, call, lo=1e-9 * scale, hi=0.5 * scale)


# ---- conversions ----------------------------------------------------------------------------------------------------------
def lognormal_to_normal(sigma_ln, F, K, T):
    """Hagan et al. (2002) eq. (A.3): the normal vol that matches a lognormal vol at strike K (second order in T)."""
    sigma_ln, F, K, T = (np.asarray(v, dtype=float) for v in (sigma_ln, F, K, T))
    lk = np.log(F / K)
    ratio = np.where(np.abs(lk) < 1e-8, np.sqrt(F * K) * (1 + lk * lk / 24), (F - K) / np.where(np.abs(lk) < 1e-12, 1e-12, lk))
    return sigma_ln * ratio * (1 - sigma_ln * sigma_ln * T / 24) / (1 + lk * lk / 24)


def price_vol_to_yield_bp(sigma_price_normal, price, duration):
    """A normal price vol in dollars per sqrt(year) on a bond fund with modified duration D and price P is a
    yield vol of sigma / (D P) in decimal per sqrt(year): 1e4 x that is the annualised basis-point vol MOVE and the
    swaption market quote.  Daily bp vol = annualised / sqrt(252)."""
    return 1e4 * np.asarray(sigma_price_normal, dtype=float) / (np.asarray(duration, dtype=float) * np.asarray(price, dtype=float))


def strike_to_yield_bp(K, F, duration):
    """Moneyness of a strike in basis points of yield: dy = -ln(K/F) / D, positive for strikes below the forward
    (higher yields).  Puts on the fund are payer swaptions; calls are receivers."""
    return -1e4 * np.log(np.asarray(K, dtype=float) / np.asarray(F, dtype=float)) / np.asarray(duration, dtype=float)


def straddle_price_normal(F, T, sigma_n):
    """ATM straddle under Bachelier: 2 sigma sqrt(T) phi(0) = sigma sqrt(T) sqrt(2/pi) ... times 2."""
    return 2.0 * np.asarray(sigma_n, dtype=float) * np.sqrt(np.asarray(T, dtype=float)) * INV_SQRT_2PI
