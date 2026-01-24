"""Realised variance, the variance risk premium in rates, and whether implied vol forecasts realised.

Realised variance over the next 21 sessions from close-to-close returns and from the range estimators (Parkinson,
Garman-Klass, Yang-Zhang), against each implied index on the same underlying: VXTLT vs TLT, TYVIX vs ZN, and
MOVE / SRVIX against the CMT 10y yield in bp.  The premium is implied^2 - realised^2 in variance units and
implied - realised in vol points and bp; the forecast test is HAR-RV (Corsi 2009) with and without the implied
vol, walk-forward.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data as D

ANN = 252.0


# ---- realised variance estimators (annualised variance of log price) ---------------------------------------------------------
def rv_close(r):
    return ANN * (r ** 2)


def rv_parkinson(h, l):
    return ANN * (np.log(h / l) ** 2) / (4 * np.log(2))


def rv_garman_klass(o, h, l, c):
    return ANN * (0.5 * np.log(h / l) ** 2 - (2 * np.log(2) - 1) * np.log(c / o) ** 2)


def rv_yang_zhang(o, h, l, c, window=21):
    """Yang & Zhang (2000): overnight + open-to-close + Rogers-Satchell, minimum-variance weights."""
    co = np.log(o / c.shift(1))
    oc = np.log(c / o)
    rs = np.log(h / o) * np.log(h / c) + np.log(l / o) * np.log(l / c)
    k = 0.34 / (1.34 + (window + 1) / (window - 1))
    v_o = co.rolling(window).var()
    v_c = oc.rolling(window).var()
    v_rs = rs.rolling(window).mean()
    return ANN * (v_o + k * v_c + (1 - k) * v_rs)


def realised_table(symbol, window=21):
    """Daily: forward-looking realised vol over the next `window` sessions under each estimator (% p.a.), and
    the trailing ones (the forecasters' inputs)."""
    px = D.prices(symbol)
    c = px["close"]
    r = np.log(c).diff()
    d = pd.DataFrame(index=px.index)
    d["ret"] = r
    d["rv1"] = rv_close(r)
    d["rv_park"] = rv_parkinson(px["high"], px["low"])
    d["rv_gk"] = rv_garman_klass(px["open"], px["high"], px["low"], c)
    d["rv_yz"] = rv_yang_zhang(px["open"], px["high"], px["low"], c, window)
    # forward realised over the next `window` sessions (annualised vol, %)
    d["rvol_fwd"] = 100 * np.sqrt(d["rv1"].shift(-1).rolling(window).mean().shift(-(window - 1)))
    d["rvol_fwd_park"] = 100 * np.sqrt(d["rv_park"].shift(-1).rolling(window).mean().shift(-(window - 1)))
    d["rvol_fwd_gk"] = 100 * np.sqrt(d["rv_gk"].shift(-1).rolling(window).mean().shift(-(window - 1)))
    # trailing
    for w, name in ((1, "rvol_1"), (5, "rvol_5"), (22, "rvol_22"), (66, "rvol_66")):
        d[name] = 100 * np.sqrt(d["rv1"].rolling(w).mean())
    d["rvol_yz_22"] = 100 * np.sqrt(d["rv_yz"])
    return d


def cmt_realised(tenor="10Yr", window=21):
    """Realised bp vol of a CMT yield (annualised bp), for MOVE and SRVIX which are quoted in bp."""
    y = D.cmt()[tenor].dropna()
    dy = y.diff() * 100.0                                    # bp
    d = pd.DataFrame({"dy_bp": dy})
    d["rv1"] = ANN * dy ** 2
    d["rvol_fwd"] = np.sqrt(d["rv1"].shift(-1).rolling(window).mean().shift(-(window - 1)))
    for w, name in ((1, "rvol_1"), (5, "rvol_5"), (22, "rvol_22"), (66, "rvol_66")):
        d[name] = np.sqrt(d["rv1"].rolling(w).mean())
    return d


# ---- premium ------------------------------------------------------------------------------------------------------------------
def premium_table(index_name, window=21, start="2004-01-01"):
    """implied vs forward realised, daily, for one index; vol points (and bp for the price indices via the
    empirical duration; MOVE and SRVIX are already bp)."""
    vi = D.vol_indices()
    und, tenor, _ = D.VOL_INDEX[index_name]
    if und is not None:
        rt = realised_table(und, window)
        from .duration import rolling_duration
        dur = rolling_duration(und)["duration"]
        d = pd.DataFrame({"iv": vi[index_name]}).join(rt).join(dur.rename("duration")).dropna(subset=["iv", "rvol_fwd"])
        d["duration"] = d["duration"].ffill()
        d["iv_bp"] = 1e4 * d["iv"] / 100 / d["duration"]
        d["rvol_fwd_bp"] = 1e4 * d["rvol_fwd"] / 100 / d["duration"]
        d["rvol_22_bp"] = 1e4 * d["rvol_22"] / 100 / d["duration"]
    else:
        rt = cmt_realised(tenor if tenor != "curve" else "10Yr", window)
        d = pd.DataFrame({"iv": vi[index_name]}).join(rt).dropna(subset=["iv", "rvol_fwd"])
        d["iv_bp"], d["rvol_fwd_bp"], d["rvol_22_bp"] = d["iv"], d["rvol_fwd"], d["rvol_22"]
    d = d[d.index >= pd.Timestamp(start)]
    d["vrp"] = d["iv"] - d["rvol_fwd"]                        # vol points (or bp)
    d["vrp_var"] = d["iv"] ** 2 - d["rvol_fwd"] ** 2
    d["vrp_bp"] = d["iv_bp"] - d["rvol_fwd_bp"]
    d["log_ratio"] = np.log(d["iv"] / d["rvol_fwd"])
    d["index"] = index_name
    return d


def premium_summary(tables):
    """One row per index: mean premium, its block-bootstrap CI (monthly blocks, the overlap of the 21-day windows),
    the fraction of months with realised above implied, and the same split by regime."""
    rows = []
    for name, d in tables.items():
        m = d["vrp"].resample("ME").mean().dropna()
        mean, lo, hi = block_bootstrap_mean(d["vrp"].values, block=21)
        rows.append({"index": name, "n_days": len(d), "from": d.index[0].date(), "to": d.index[-1].date(), "implied_mean": d["iv"].mean(),
                     "realised_mean": d["rvol_fwd"].mean(), "vrp_mean": mean, "vrp_lo": lo, "vrp_hi": hi, "vrp_bp_mean": d["vrp_bp"].mean(),
                     "log_ratio_mean": d["log_ratio"].mean(), "months_realised_above": float((m < 0).mean()),
                     "corr_iv_fwd": d["iv"].corr(d["rvol_fwd"]), "corr_trailing_fwd": d["rvol_22"].corr(d["rvol_fwd"])})
    return pd.DataFrame(rows).set_index("index")


def premium_by_year(tables):
    out = {}
    for name, d in tables.items():
        out[name] = d.groupby(d.index.year)["vrp"].mean()
    return pd.DataFrame(out).rename_axis("year")


def block_bootstrap_mean(x, block=21, B=2000, seed=7):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = x.size
    if n < 2 * block:
        return float(x.mean()) if n else np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=(B, nb))
    offs = np.arange(block)
    means = np.array([x[(st[:, None] + offs).ravel()[:n]].mean() for st in starts])
    return float(x.mean()), float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


# ---- HAR-RV with and without implied -------------------------------------------------------------------------------------------
def har_forecast(d, window=750, refit=21, use_iv=False, target="rvol_fwd"):
    """Walk-forward HAR: log rvol_fwd ~ log rvol_1 + log rvol_5 + log rvol_22 (+ log iv).  Refitted every `refit`
    sessions on the trailing `window`; the target for the fit stops `21` sessions before the forecast date so the
    training window never contains the forecast's own realisation."""
    cols = ["rvol_1", "rvol_5", "rvol_22"] + (["iv"] if use_iv else [])
    X = np.log(d[cols].replace(0, np.nan)).values
    y = np.log(d[target].replace(0, np.nan)).values
    ok = np.isfinite(X).all(axis=1) & np.isfinite(y)
    n = len(d)
    pred = np.full(n, np.nan)
    beta = None
    for t in range(window + 21, n):
        if (t - window - 21) % refit == 0 or beta is None:
            a, b = t - window - 21, t - 21
            m = ok[a:b]
            if m.sum() < 100:
                continue
            A = np.column_stack([np.ones(m.sum()), X[a:b][m]])
            beta = np.linalg.lstsq(A, y[a:b][m], rcond=None)[0]
        if ok[t] and beta is not None:
            pred[t] = beta[0] + X[t] @ beta[1:]
    return pd.Series(np.exp(pred), index=d.index)


def forecast_table(tables, window=750):
    """Out-of-sample R^2 of log realised vol: HAR, HAR + implied, implied alone, trailing 22-day alone."""
    rows = []
    for name, d in tables.items():
        y = np.log(d["rvol_fwd"])
        f_har = np.log(har_forecast(d, window, use_iv=False))
        f_hiv = np.log(har_forecast(d, window, use_iv=True))
        m = f_har.notna() & f_hiv.notna() & y.notna()
        yy = y[m]

        def r2(f):
            return 1 - ((yy - f[m]) ** 2).sum() / ((yy - yy.mean()) ** 2).sum()

        rows.append({"index": name, "n_oos": int(m.sum()), "from": yy.index[0].date(), "r2_har": r2(f_har), "r2_har_iv": r2(f_hiv),
                     "r2_iv_only": r2(np.log(d["iv"])), "r2_trailing22": r2(np.log(d["rvol_22"])),
                     "mae_har_volpts": (np.exp(yy) - np.exp(f_har[m])).abs().mean(), "mae_har_iv_volpts": (np.exp(yy) - np.exp(f_hiv[m])).abs().mean(),
                     "bias_iv_volpts": (d["iv"][m] - np.exp(yy)).mean()})
    return pd.DataFrame(rows).set_index("index")
