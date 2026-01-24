"""Relative-value strategies on the taking side, with the cost of taking measured rather than assumed.

Positions are vega-sized and the P&L of a delta-hedged one-month option is taken as the variance-swap
approximation vega x (realised vol - implied vol) over its life (Carr & Wu 2009 for the premium; Carr & Lee 2009
for the vol-swap approximation).  Costs are what the recorded chains say a taker pays: the ATM half-spread in
vol points per leg on entry and exit, plus the delta-hedging cost from the underlying's half-spread and the
expected hedge turnover of a straddle.  Every strategy is walk-forward: the signal on a decision date uses only
data before it.  Everything is reported gross and net, with a block-bootstrap interval, and against the "always
on" baseline so the reader can see what the signal adds over the premium itself.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data as D
from . import vrp as V

MONTH = 21
SQRT_2_PI = np.sqrt(2 / np.pi)


# ---- costs -----------------------------------------------------------------------------------------------------------------------
def straddle_hedge_turnover(days=MONTH):
    """Expected sum of |delta changes| x S over the life of an ATM straddle, as a multiple of S: daily
    Gamma x E|dS| summed, Gamma = 2 phi(0) / (S sigma sqrt(T)), E|dS| = S sigma sqrt(2/pi) / sqrt(252):
    = 2 phi(0) sqrt(2/pi) sqrt(days).  About 2.9 S for a month."""
    return 2 * 0.398942 * SQRT_2_PI * np.sqrt(days)


def cost_model(halfspread_vol, underlying_rel_halfspread, sigma, days=MONTH):
    """Round-trip cost of a delta-hedged straddle per unit of straddle vega, in vol points:
       option legs: half-spread in vol on entry and exit = 2 x halfspread_vol
       hedging: turnover x rel half-spread of the underlying, converted to vol points through the straddle's vega
                (vega per unit S = 2 phi(0) sqrt(T)), i.e. cost_S / vega_S."""
    T = days / 252.0
    vega_per_S = 2 * 0.398942 * np.sqrt(T)                  # per 1.00 of vol (decimal); vol points = x 100
    hedge = straddle_hedge_turnover(days) * underlying_rel_halfspread / vega_per_S * 100.0
    return 2 * halfspread_vol * 100.0 + hedge, hedge


def measured_costs(slices, quotes, und_symbol, days=MONTH):
    """From today's chain: the ATM half-spread (vol points) nearest the horizon, and the fund's relative half-spread."""
    s = slices.iloc[(slices["days"] - days).abs().argsort()[:2]]
    hs_vol = float(s["atm_halfspread_vol"].mean())          # decimal
    px = D.prices(und_symbol)
    rel = float(0.005 / px["close"].iloc[-1])                # a penny-wide ETF quote: half a cent
    return hs_vol, rel


# ---- P&L engine -------------------------------------------------------------------------------------------------------------------
def monthly_positions(d, signal, side, cost_volpts, start=None):
    """Roll every MONTH sessions: position = side(signal) in {-1, 0, +1} units of vega; P&L per roll =
    position x (rvol_fwd - iv) - |position| x cost.  Returns one row per roll."""
    d = d.dropna(subset=["iv", "rvol_fwd"])
    if start:
        d = d[d.index >= pd.Timestamp(start)]
    idx = d.index[::MONTH]
    rows = []
    for t in idx:
        pos = side(signal.get(t, np.nan)) if signal is not None else -1
        if not np.isfinite(pos):
            continue
        gross = pos * (d.at[t, "rvol_fwd"] - d.at[t, "iv"])
        rows.append({"date": t, "position": pos, "iv": d.at[t, "iv"], "rvol_fwd": d.at[t, "rvol_fwd"], "gross": gross,
                     "cost": abs(pos) * cost_volpts, "net": gross - abs(pos) * cost_volpts})
    return pd.DataFrame(rows).set_index("date")


def summarise(pnl, label, col="net"):
    x = pnl[col].values
    mean, lo, hi = V.block_bootstrap_mean(x, block=3)
    n = len(x)
    sd = x.std(ddof=1) if n > 1 else np.nan
    cum = np.cumsum(x)
    dd = float((np.maximum.accumulate(cum) - cum).max()) if n else np.nan
    return {"strategy": label, "rolls": n, "from": pnl.index[0].date() if n else None, "to": pnl.index[-1].date() if n else None,
            "active_share": float((pnl["position"] != 0).mean()), "mean_gross": pnl["gross"].mean(), "mean_cost": pnl["cost"].mean(),
            "mean_net": mean, "net_lo": lo, "net_hi": hi, "sharpe_net": mean / sd * np.sqrt(12) if sd and sd > 0 else np.nan,
            "hit_rate": float((x > 0).mean()) if n else np.nan, "max_drawdown": dd, "worst_roll": float(x.min()) if n else np.nan}


# ---- (a) the variance risk premium as a trade ---------------------------------------------------------------------------------------
def vrp_strategy(index_name, cost_volpts, window=750, threshold=0.0, start="2008-01-01"):
    """Short one-month vega when the HAR+IV forecast says implied exceeds expected realised by more than
    `threshold` vol points; flat otherwise.  Baseline: always short."""
    d = V.premium_table(index_name)
    f = V.har_forecast(d, window, use_iv=True)
    expected_premium = d["iv"] - f
    sig = expected_premium
    side = lambda x: -1.0 if x > threshold else 0.0
    active = monthly_positions(d, sig, side, cost_volpts, start)
    always = monthly_positions(d, None, None, cost_volpts, start)
    always = always[always.index >= active.index[0]]
    return active, always, expected_premium


def vrp_threshold_sweep(index_name, cost_volpts, thresholds=(-1, 0, 0.5, 1, 1.5, 2), start="2008-01-01"):
    rows = []
    for th in thresholds:
        a, _, _ = vrp_strategy(index_name, cost_volpts, threshold=th, start=start)
        rows.append({"threshold": th, **{k: v for k, v in summarise(a, f"{index_name} short if E[premium]>{th}").items() if k != "strategy"}})
    return pd.DataFrame(rows).set_index("threshold")


# ---- (b) tenor relative value: long-end vs 10y bp vol ------------------------------------------------------------------------------------
def tenor_rv(cost_long_volpts, cost_ten_volpts, lookback=250, entry=1.0, start="2006-01-01"):
    """z-score of log(VXTLT bp vol / TYVIX bp vol) against its trailing distribution.  z > entry: long-end vol rich
    -> short TLT vega, long ZN vega in equal bp-vol notional; z < -entry the reverse; else flat.  Each leg's P&L is
    its realised - implied in bp; costs per leg from the chains (TLT measured; ZN options taken as the same
    fraction of vol, stated as an assumption)."""
    a = V.premium_table("VXTLT")
    b = V.premium_table("TYVIX")
    j = a[["iv_bp", "rvol_fwd_bp", "duration"]].join(b[["iv_bp", "rvol_fwd_bp", "duration"]], lsuffix="_tlt", rsuffix="_zn", how="inner")
    j["lr"] = np.log(j["iv_bp_tlt"] / j["iv_bp_zn"])
    j["z"] = (j["lr"] - j["lr"].rolling(lookback).mean()) / j["lr"].rolling(lookback).std()
    j = j[j.index >= pd.Timestamp(start)].dropna(subset=["z", "rvol_fwd_bp_tlt", "rvol_fwd_bp_zn"])
    rows = []
    for t in j.index[::MONTH]:
        z = j.at[t, "z"]
        pos = -1.0 if z > entry else (1.0 if z < -entry else 0.0)          # sign of the TLT leg
        # bp P&L converted to vol points of each leg through its duration (so the two legs are comparable to (a))
        tlt = pos * (j.at[t, "rvol_fwd_bp_tlt"] - j.at[t, "iv_bp_tlt"]) * j.at[t, "duration_tlt"] / 100
        zn = -pos * (j.at[t, "rvol_fwd_bp_zn"] - j.at[t, "iv_bp_zn"]) * j.at[t, "duration_zn"] / 100
        cost = abs(pos) * (cost_long_volpts + cost_ten_volpts)
        rows.append({"date": t, "z": z, "position": pos, "gross": tlt + zn, "leg_tlt": tlt, "leg_zn": zn, "cost": cost, "net": tlt + zn - cost})
    return pd.DataFrame(rows).set_index("date"), j


def tenor_rv_predictive(j, horizon=MONTH):
    """Does the z-score predict the change in the ratio (mean reversion), and each leg's premium?  OLS with
    Newey-West-free block bootstrap on the slope."""
    x = j["z"]
    y = j["lr"].shift(-horizon) - j["lr"]
    m = x.notna() & y.notna()
    slope = np.polyfit(x[m], y[m], 1)[0]
    boots = []
    rng = np.random.default_rng(3)
    xs, ys = x[m].values, y[m].values
    n = len(xs)
    nb = int(np.ceil(n / horizon))
    for _ in range(500):
        st = rng.integers(0, n - horizon + 1, nb)
        idx = (st[:, None] + np.arange(horizon)).ravel()[:n]
        boots.append(np.polyfit(xs[idx], ys[idx], 1)[0])
    return {"slope": slope, "lo": float(np.quantile(boots, 0.025)), "hi": float(np.quantile(boots, 0.975)), "n": int(m.sum()),
            "corr": float(np.corrcoef(xs, ys)[0, 1])}


# ---- (c) the FOMC straddle --------------------------------------------------------------------------------------------------------------
def event_strategy(df, event="FOMC", lookback=8, cost_frac_of_premium=0.05, start="2006-01-01", event_multiple=1.0):
    """Per scheduled event: the one-day straddle priced off the implied daily move (index / sqrt(252), times
    `event_multiple` when the chain's event-variance extraction says the event day carries more than a diffusive
    day), payoff |realised move|.  Signal: the trailing `lookback` events' mean realised/implied ratio; below 1
    sell the straddle, above 1 buy it.  P&L in bp of yield per unit of implied move, costs as a fraction of the
    straddle premium (the ATM half-spread in price over the straddle price, from the chain)."""
    e = df[df["event_next"].str.contains(event)].copy()
    e = e[e.index >= pd.Timestamp(start)]
    e["implied_bp"] = e["implied_move_bp"] * event_multiple
    e["premium_bp"] = e["implied_bp"] * SQRT_2_PI                      # straddle price in bp of yield (normal)
    e["payoff_bp"] = e["realised_move_bp"]
    e["ratio"] = e["payoff_bp"] / e["premium_bp"]
    e["signal"] = e["ratio"].shift(1).rolling(lookback).mean()
    e["position"] = np.where(e["signal"].isna(), np.nan, np.where(e["signal"] < 1, -1.0, 1.0))
    e["gross"] = e["position"] * (e["payoff_bp"] - e["premium_bp"])
    e["cost"] = cost_frac_of_premium * e["premium_bp"]
    e["net"] = e["gross"] - e["cost"]
    e["always_short_net"] = -(e["payoff_bp"] - e["premium_bp"]) - e["cost"]
    e["always_long_net"] = (e["payoff_bp"] - e["premium_bp"]) - e["cost"]
    return e.dropna(subset=["position"])


def event_summary(e, label):
    out = summarise(e.rename(columns={"net": "net"}), label)
    for col in ("always_short_net", "always_long_net"):
        m, lo, hi = V.block_bootstrap_mean(e[col].values, block=2)
        out[f"{col}_mean"], out[f"{col}_lo"], out[f"{col}_hi"] = m, lo, hi
    return out


# ---- (d) cross-market: swaption vs futures option vol, rates vs equity vol ---------------------------------------------------------------
def cross_market_tables(horizon=MONTH, lookback=250):
    """Two bases: SRVIX - TYVIX in bp (swaption vol minus futures-option vol, both on the 10y) and log(MOVE / VIX).
    For each: the z-score's predictive slope on the next-month change (mean reversion) and on the next-month
    realised-minus-implied of the rich leg."""
    vi = D.vol_indices()
    b = V.premium_table("TYVIX")
    out = {}
    if "SRVIX" in vi.columns:
        basis = (vi["SRVIX"] - b["iv_bp"]).dropna()
        z = (basis - basis.rolling(lookback).mean()) / basis.rolling(lookback).std()
        chg = basis.shift(-horizon) - basis
        m = z.notna() & chg.notna()
        out["SRVIX-TYVIX bp"] = {"n": int(m.sum()), "mean_basis_bp": float(basis.mean()), "slope_on_change": float(np.polyfit(z[m], chg[m], 1)[0]),
                                 "corr": float(np.corrcoef(z[m], chg[m])[0, 1]), "from": basis.index[0].date(), "to": basis.index[-1].date()}
    r = np.log(vi["MOVE"] / vi["VIX"]).dropna()
    z = (r - r.rolling(lookback).mean()) / r.rolling(lookback).std()
    chg = r.shift(-horizon) - r
    m = z.notna() & chg.notna()
    mv = V.premium_table("MOVE")
    prem = mv["vrp"].reindex(z.index)
    mm = m & prem.notna()
    out["log MOVE/VIX"] = {"n": int(m.sum()), "mean_ratio": float(np.exp(r.mean())), "slope_on_change": float(np.polyfit(z[m], chg[m], 1)[0]),
                           "corr": float(np.corrcoef(z[m], chg[m])[0, 1]), "corr_with_MOVE_premium": float(np.corrcoef(z[mm], prem[mm])[0, 1]),
                           "from": r.index[0].date(), "to": r.index[-1].date()}
    return pd.DataFrame(out).T
