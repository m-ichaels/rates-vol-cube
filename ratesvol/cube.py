"""The basis-point vol cube from a recorded chain.

For each expiry: the forward and discount factor from put-call parity on the quotes, Black and Bachelier implied
vols of the out-of-the-money mids, the conversion of every quote into yield space (moneyness in bp of yield through
the fund's duration, vol in bp per year), and a normal SABR (beta = 0) fit per expiry, which is the form rates
desks quote swaption smiles in.  The result is a table (expiry x ATM bp vol x payer/receiver skew x fit error) per
fund; across funds the fund's benchmark tenor is the second axis of the cube.  A separate table carries the
bid-ask of every quote in vol points and bp vol, which is what the taking-side strategies pay.

Hagan, Kumar, Lesniewski, Woodward (2002) "Managing smile risk", Wilmott, eqs. (A.59)-(A.60) for the normal SABR
formula with beta = 0.
"""
from __future__ import annotations

import datetime as dt
import os

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from . import data as D
from . import pricing as P

EXPIRY_TIME = dt.time(16, 0)


def _tenor_years(expiry, asof):
    exp_ts = pd.Timestamp(dt.datetime.combine(expiry.date(), EXPIRY_TIME))
    return max((exp_ts - asof).total_seconds() / (365.0 * 86400.0), 1e-6)


def normal_sabr(K, F, T, alpha, rho, nu):
    """Normal vol at strike K for beta = 0 (Hagan et al. 2002, A.59 with beta = 0)."""
    K, F = np.asarray(K, dtype=float), float(F)
    z = (nu / alpha) * (F - K)
    x = np.log((np.sqrt(1 - 2 * rho * z + z * z) + z - rho) / (1 - rho))
    ratio = np.where(np.abs(z) < 1e-8, 1.0, z / np.where(np.abs(x) < 1e-14, 1e-14, x))
    return alpha * ratio * (1 + (2 - 3 * rho * rho) / 24 * nu * nu * T)


def fit_normal_sabr(K, F, T, sigma_n, w=None):
    """Least squares in normal vol; returns (alpha, rho, nu, rmse)."""
    K, sigma_n = np.asarray(K, dtype=float), np.asarray(sigma_n, dtype=float)
    w = np.ones_like(sigma_n) if w is None else np.asarray(w, dtype=float)
    atm = sigma_n[np.argmin(np.abs(K - F))]

    def resid(p):
        return w * (normal_sabr(K, F, T, p[0], p[1], p[2]) - sigma_n)

    best = None
    for rho0 in (-0.3, 0.0, 0.3):
        for nu0 in (0.2, 0.8):
            r = least_squares(resid, [atm, rho0, nu0], bounds=([1e-8, -0.999, 0.0], [np.inf, 0.999, 20.0]), max_nfev=400)
            if best is None or r.cost < best.cost:
                best = r
    a, rho, nu = best.x
    rmse = float(np.sqrt(np.mean((normal_sabr(K, F, T, a, rho, nu) - sigma_n) ** 2)))
    return a, rho, nu, rmse


def forward_from_parity(opts, spot, r, T, band=0.12):
    """F and DF per expiry from two-sided call/put pairs near the money: C - P = DF (F - K).  DF is taken from
    the funding rate (a regression slope on a handful of strikes is too noisy for a 1-2 month option); F is the
    median of K + (C - P) / DF over the pairs.  Returns (F, DF, n_pairs, dispersion of F across pairs)."""
    df = float(np.exp(-r * T))
    two = opts[(opts["bid"] > 0) & (opts["ask"] > 0)].copy()
    two["mid"] = 0.5 * (two["bid"] + two["ask"])
    c = two[two["call"]].set_index("strike")["mid"]
    p = two[~two["call"]].set_index("strike")["mid"]
    ks = c.index.intersection(p.index)
    ks = ks[(ks > spot * (1 - band)) & (ks < spot * (1 + band))]
    if len(ks) < 2:
        return np.nan, df, 0, np.nan
    Fk = ks.values + (c.loc[ks].values - p.loc[ks].values) / df
    return float(np.median(Fk)), df, int(len(ks)), float(np.std(Fk))


def quotes_in_yield_space(opts, F, DF, T, duration):
    """OTM two-sided quotes -> Black and Bachelier IVs of the mid, bid-ask in vol, moneyness and vol in bp."""
    q = opts[(opts["bid"] > 0) & (opts["ask"] > 0)].copy()
    q = q[(q["call"] & (q["strike"] >= F)) | (~q["call"] & (q["strike"] < F))]
    if q.empty:
        return q
    for side in ("bid", "ask"):
        q[f"{side}_fwd"] = q[side] / DF
    q["mid_fwd"] = 0.5 * (q["bid_fwd"] + q["ask_fwd"])
    for side in ("bid", "ask", "mid"):
        col = q[f"{side}_fwd"].values
        q[f"iv_{side}"] = np.where(q["call"], P.black_implied(col, F, q["strike"].values, T, True), P.black_implied(col, F, q["strike"].values, T, False))
        q[f"nv_{side}"] = np.where(q["call"], P.bachelier_implied(col, F, q["strike"].values, T, True), P.bachelier_implied(col, F, q["strike"].values, T, False))
    q = q.dropna(subset=["iv_mid", "nv_mid"])
    q["moneyness_bp"] = P.strike_to_yield_bp(q["strike"].values, F, duration)
    for side in ("bid", "ask", "mid"):
        q[f"bpvol_{side}"] = P.price_vol_to_yield_bp(q[f"nv_{side}"].values, F, duration)
    q["spread_vol"] = q["iv_ask"] - q["iv_bid"]                       # lognormal vol points
    q["spread_bpvol"] = q["bpvol_ask"] - q["bpvol_bid"]
    q["spread_price"] = q["ask"] - q["bid"]
    q["vega_fwd"] = P.black_vega(F, q["strike"].values, T, q["iv_mid"].values)
    q["T"] = T
    return q


def fit_snapshot(path, duration=None, funding=None, min_quotes=5, max_T=1.5):
    """Everything for one recorded chain: per-expiry SABR table and the quote-level table."""
    und, opts = D.read_snapshot(path)
    sym = und["symbol"]
    asof = und["recorded"] or pd.Timestamp.now()
    spot = float(und["spot"])
    if duration is None:
        from .duration import rolling_duration
        d = rolling_duration(sym) if sym in D.FUND_TENOR else None
        duration = float(d["duration"].iloc[-1]) if d is not None and not d.empty else float(D.fund_duration().get(sym, np.nan))
    if funding is None:
        cm = D.cmt()
        funding = float(cm["3Mo"].dropna().iloc[-1]) / 100.0 if cm is not None else 0.04
    rows, quotes = [], []
    for exp, o in opts.groupby("expiry"):
        T = _tenor_years(exp, asof)
        if T > max_T or T < 1.0 / 365:
            continue
        F, DF, npairs, disp = forward_from_parity(o, spot, funding, T)
        if not np.isfinite(F) or npairs < 2:
            continue
        q = quotes_in_yield_space(o, F, DF, T, duration)
        if len(q) < min_quotes:
            continue
        w = 1.0 / np.maximum(q["spread_bpvol"].values, 0.25)
        a, rho, nu, rmse = fit_normal_sabr(q["strike"].values, F, T, q["nv_mid"].values, w)
        q["nv_fit"] = normal_sabr(q["strike"].values, F, T, a, rho, nu)
        q["bpvol_fit"] = P.price_vol_to_yield_bp(q["nv_fit"].values, F, duration)
        q["inside_market"] = (q["nv_fit"] >= q["nv_bid"]) & (q["nv_fit"] <= q["nv_ask"])
        q["symbol"], q["expiry"], q["snapshot"], q["F"], q["DF"] = sym, exp, und["snapshot"], F, DF
        quotes.append(q)
        atm_n = normal_sabr(F, F, T, a, rho, nu)
        K_up, K_dn = F * np.exp(-50e-4 * duration), F * np.exp(+50e-4 * duration)        # +50 bp yield (lower price), -50 bp
        K_up2, K_dn2 = F * np.exp(-100e-4 * duration), F * np.exp(+100e-4 * duration)
        bp = lambda k: P.price_vol_to_yield_bp(normal_sabr(k, F, T, a, rho, nu), F, duration)
        atm_bp = P.price_vol_to_yield_bp(atm_n, F, duration)
        near = q.iloc[np.argsort(np.abs(q["moneyness_bp"].values))[:4]]
        rows.append({"symbol": sym, "snapshot": und["snapshot"], "asof": asof, "expiry": exp, "T": T, "days": T * 365, "spot": spot, "F": F, "DF": DF,
                     "n_pairs": npairs, "F_dispersion": disp, "duration": duration, "n_quotes": len(q),
                     "atm_bpvol": atm_bp, "atm_bpvol_daily": atm_bp / np.sqrt(252), "atm_lnvol": atm_n / F,
                     "skew_50bp": bp(K_up) - bp(K_dn), "skew_100bp": bp(K_up2) - bp(K_dn2), "fly_100bp": 0.5 * (bp(K_up2) + bp(K_dn2)) - atm_bp,
                     "alpha": a, "rho": rho, "nu": nu, "rmse_bpvol": P.price_vol_to_yield_bp(rmse, F, duration),
                     "inside_market": float(q["inside_market"].mean()), "atm_halfspread_bpvol": 0.5 * near["spread_bpvol"].mean(),
                     "atm_halfspread_vol": 0.5 * near["spread_vol"].mean(), "atm_halfspread_price": 0.5 * near["spread_price"].mean(),
                     "vendor_iv30": und.get("iv30")})
    slices = pd.DataFrame(rows)
    quotes = pd.concat(quotes, ignore_index=True) if quotes else pd.DataFrame()
    return und, slices, quotes


def interpolate_atm(slices, days):
    """ATM bp vol at a constant maturity by linear interpolation in total variance."""
    s = slices.sort_values("T")
    if s.empty:
        return np.nan
    T = days / 365.0
    tv = (s["atm_bpvol"] ** 2 * s["T"]).values
    if T <= s["T"].iloc[0]:
        return float(s["atm_bpvol"].iloc[0])
    if T >= s["T"].iloc[-1]:
        return float(s["atm_bpvol"].iloc[-1])
    v = np.interp(T, s["T"].values, tv)
    return float(np.sqrt(v / T))


def surface_grid(slices, moneyness_bp=np.arange(-150, 151, 10)):
    """bp vol on a (expiry x moneyness) grid from the fitted SABR slices, for the plots."""
    rows = []
    for _, s in slices.iterrows():
        K = s["F"] * np.exp(-moneyness_bp * 1e-4 * s["duration"])
        v = P.price_vol_to_yield_bp(normal_sabr(K, s["F"], s["T"], s["alpha"], s["rho"], s["nu"]), s["F"], s["duration"])
        for m, x in zip(moneyness_bp, v):
            rows.append({"symbol": s["symbol"], "expiry": s["expiry"], "days": s["days"], "moneyness_bp": m, "bpvol": x})
    return pd.DataFrame(rows)


def cube(symbols=("SHY", "IEI", "IEF", "TLH", "TLT", "AGG", "LQD", "HYG"), date=None, raw_dir=None):
    """Fit the closing snapshot of every fund on a date (default: the latest) -> (slices, quotes) tables."""
    from .duration import duration_series
    durs = duration_series(tuple(s for s in symbols if s in D.FUND_TENOR)) if any(s in D.FUND_TENOR for s in symbols) else pd.DataFrame()
    stated = D.fund_duration()
    S, Q = [], []
    for sym in symbols:
        p = D.closing_snapshot(sym, date, raw_dir)
        if not p:
            continue
        dur = float(durs[sym].dropna().iloc[-1]) if sym in durs.columns and durs[sym].notna().any() else (float(stated.get(sym, np.nan)) if stated is not None else np.nan)
        if not np.isfinite(dur):
            continue
        _, s, q = fit_snapshot(p, duration=dur)
        S.append(s)
        Q.append(q)
    slices = pd.concat(S, ignore_index=True) if S else pd.DataFrame()
    quotes = pd.concat(Q, ignore_index=True) if Q else pd.DataFrame()
    if not slices.empty:
        slices["tenor"] = slices["symbol"].map(D.FUND_TENOR)
        slices["label"] = slices["symbol"].map(D.FUND_LABEL)
    return slices, quotes


def taking_cost_table(quotes):
    """Bid-ask by tenor bucket and moneyness bucket: what a taker pays to cross, in vol points, bp vol and as a
    fraction of the mid - the cost side of every strategy in rv.py."""
    if quotes.empty:
        return pd.DataFrame()
    q = quotes.copy()
    q["tenor_bucket"] = pd.cut(q["T"] * 365, [0, 10, 35, 70, 130, 400, 1000], labels=["<10d", "10-35d", "35-70d", "70-130d", "130-400d", ">400d"])
    q["money_bucket"] = pd.cut(q["moneyness_bp"], [-1e9, -100, -50, -20, 20, 50, 100, 1e9],
                               labels=["<-100bp", "-100..-50", "-50..-20", "ATM +-20", "20..50", "50..100", ">100bp"])
    q["rel_spread"] = q["spread_price"] / (0.5 * (q["bid"] + q["ask"]))
    g = q.groupby(["symbol", "tenor_bucket", "money_bucket"], observed=True).agg(
        n=("strike", "size"), halfspread_vol=("spread_vol", lambda x: 0.5 * x.median()), halfspread_bpvol=("spread_bpvol", lambda x: 0.5 * x.median()),
        halfspread_price=("spread_price", lambda x: 0.5 * x.median()), rel_halfspread=("rel_spread", lambda x: 0.5 * x.median()),
        open_interest=("open_interest", "sum"), volume=("volume", "sum")).reset_index()
    return g
