"""Empirical duration: the number that turns a fund's price vol into a yield vol.

A bond fund's stated effective duration is a point-in-time number from the sponsor; for a 22-year history the
project needs the duration on every day.  Regressing the fund's daily log return on the change in its benchmark
CMT yield over a trailing window, dP/P = -D dy + e, gives the realised duration D (Treasury funds: R^2 above 0.9;
credit funds: lower, because the spread moves too - that is reported, not hidden).  The Treasury futures get the
same treatment against the 10y (ZN), 5y (ZF) and 30y (ZB) CMT.  Today's estimate is checked against the
sponsor's stated duration in the tests and the README.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data as D

BENCH = dict(D.FUND_TENOR, **{"ZN=F": "10Yr", "ZF=F": "5Yr", "ZB=F": "30Yr"})


def rolling_duration(symbol, window=250, min_obs=120):
    """Daily series: empirical duration, its standard error, the R^2 and the residual (spread) vol in bp/day."""
    px = D.prices(symbol)
    cm = D.cmt()
    if px is None or cm is None or symbol not in BENCH:
        return None
    tenor = BENCH[symbol]
    r = np.log(px["adjclose"].where(px["adjclose"] > 0, px["close"])).diff()
    dy = cm[tenor].diff() / 100.0                                              # decimal
    df = pd.concat([r.rename("r"), dy.rename("dy")], axis=1, sort=True).dropna()
    df = df[(df["dy"].abs() < 0.01) & (df["r"].abs() < 0.2)]                    # drop data errors, keep 2020
    out = []
    x, y = df["dy"].values, df["r"].values
    idx = df.index
    for i in range(min_obs, len(df) + 1):
        a = max(0, i - window)
        xs, ys = x[a:i], y[a:i]
        xm, ym = xs.mean(), ys.mean()
        sxx = ((xs - xm) ** 2).sum()
        if sxx <= 0:
            continue
        b = ((xs - xm) * (ys - ym)).sum() / sxx
        res = ys - ym - b * (xs - xm)
        n = len(xs)
        se = np.sqrt((res ** 2).sum() / (n - 2) / sxx)
        r2 = 1 - (res ** 2).sum() / ((ys - ym) ** 2).sum()
        out.append({"date": idx[i - 1], "duration": -b, "se": se, "r2": r2, "resid_bp_day": 1e4 * res.std() / max(-b, 1e-6)})
    return pd.DataFrame(out).set_index("date")


def duration_table(symbols=("SHY", "IEI", "IEF", "TLH", "TLT", "AGG", "LQD", "HYG", "ZF=F", "ZN=F", "ZB=F"), window=250):
    """Latest empirical duration per symbol next to the sponsor's stated number."""
    stated = D.fund_duration()
    rows = []
    for s in symbols:
        d = rolling_duration(s, window)
        if d is None or d.empty:
            continue
        last = d.iloc[-1]
        rows.append({"symbol": s, "benchmark": BENCH[s], "empirical_duration": last["duration"], "se": last["se"], "r2": last["r2"],
                     "resid_bp_day": last["resid_bp_day"], "stated_duration": float(stated.get(s, np.nan)) if stated is not None else np.nan,
                     "asof": d.index[-1].date().isoformat(), "n_days": len(d)})
    return pd.DataFrame(rows).set_index("symbol")


def duration_series(symbols=("SHY", "IEI", "IEF", "TLH", "TLT", "ZN=F"), window=250):
    """Wide daily table of empirical durations (forward-filled to every trading day)."""
    cols = {}
    for s in symbols:
        d = rolling_duration(s, window)
        if d is not None and not d.empty:
            cols[s] = d["duration"]
    return pd.DataFrame(cols).ffill()
