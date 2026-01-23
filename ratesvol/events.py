"""Event variance: what the options say a scheduled release is worth, and what it turned out to be worth.

Two layers.  On a recorded chain, the ATM total variance of each expiry is a diffusive rate times time plus the
jump variance of every scheduled event before that expiry; with weekly expiries the system is over-determined and
solved by non-negative least squares (Ederington & Lee 1996 for the idea; the extraction is the standard desk
"event vol" calculation).  On the 22-year index histories, the implied one-day move before each event is the
index level scaled to a day, the realised move is the close-to-close change, and the premium is their ratio - by
event type, by fund, by year, with the crush in the index on the event day.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import nnls

from . import data as D

DAY = 1.0 / 252.0


# ---- extraction from a chain ---------------------------------------------------------------------------------------------
def extract_event_variance(slices, events, asof=None, max_days=130, min_expiries=4):
    """slices: one fund's SABR table (T, atm_bpvol).  events: DataFrame(date, type).  Solves
        sigma_atm_i^2 T_i = s_d^2 T_i + sum_e J_e^2 1[t_e <= T_i]      (all in bp^2, T in years)
    for s_d (the diffusive bp vol) and J_e (the implied one-day move of each event, bp), NNLS.  Events on the same
    date are one unknown.  Returns (diffusive_bpvol, DataFrame(event, date, J_bp, days), fit residual in bp vol)."""
    s = slices[slices["days"] <= max_days].sort_values("T")
    if len(s) < min_expiries:
        return np.nan, pd.DataFrame(), np.nan
    asof = pd.Timestamp(asof or s["asof"].iloc[0])
    horizon = asof + pd.Timedelta(days=float(s["days"].max()))
    ev = events[(events["date"] > asof.normalize()) & (events["date"] <= horizon)].copy()
    ev = ev.groupby("date")["type"].apply(lambda x: "+".join(sorted(set(x)))).reset_index()
    T = s["T"].values
    tv = (s["atm_bpvol"].values ** 2) * T
    A = np.column_stack([T] + [((ev_date - asof).total_seconds() / (365 * 86400.0) <= T).astype(float) for ev_date in ev["date"]])
    x, rnorm = nnls(A, tv)
    diffusive = float(np.sqrt(x[0]))
    out = ev.assign(J_bp=np.sqrt(x[1:]), days=[(d - asof).days for d in ev["date"]])
    # two events between the same pair of expiries share one unknown: only the sole event of an interval is identified
    expiry_days = np.sort(s["days"].values)
    interval = np.searchsorted(expiry_days, out["days"].values, side="left")
    counts = pd.Series(interval).value_counts()
    out["identified"] = [counts[i] == 1 for i in interval]
    fitted = A @ x
    resid = np.sqrt(np.abs(fitted) / T) - np.sqrt(tv / T)
    return diffusive, out, float(np.sqrt(np.mean(resid ** 2)))


def event_share(slices, events, asof=None):
    """For each expiry: the share of its total variance that is scheduled events."""
    diff, ev, _ = extract_event_variance(slices, events, asof)
    if ev.empty:
        return pd.DataFrame()
    asof = pd.Timestamp(asof or slices["asof"].iloc[0])
    rows = []
    for _, s in slices.sort_values("T").iterrows():
        inside = ev[ev["days"] <= s["days"]]
        jump = float((inside["J_bp"] ** 2).sum())
        tot = s["atm_bpvol"] ** 2 * s["T"]
        rows.append({"expiry": s["expiry"], "days": s["days"], "atm_bpvol": s["atm_bpvol"], "diffusive_bpvol": diff,
                     "event_var_share": jump / tot if tot > 0 else np.nan, "events_inside": ", ".join(inside["type"])})
    return pd.DataFrame(rows)


# ---- history ----------------------------------------------------------------------------------------------------------------
def implied_vs_realised(index_name="VXTLT", start="2004-01-01", event_types=("FOMC", "NFP", "AUCTION10", "AUCTION30")):
    """Daily table for one vol index and its underlying: implied one-day move (index level scaled to a day, in
    % of price and in bp of yield through the empirical duration), the realised close-to-close move, the index
    change on the day, and the scheduled events on the day."""
    vi = D.vol_indices()
    und_sym, tenor, _ = D.VOL_INDEX[index_name]
    if und_sym is None:
        raise ValueError("no traded underlying for " + index_name)
    px = D.prices(und_sym)
    from .duration import rolling_duration
    dur = rolling_duration(und_sym)
    df = pd.DataFrame({"iv": vi[index_name]}).join(px[["close", "open", "high", "low"]]).join(dur["duration"].rename("duration"))
    df = df[df.index >= pd.Timestamp(start)].dropna(subset=["iv", "close"])
    df["duration"] = df["duration"].ffill()
    df["ret"] = np.log(df["close"]).diff()
    df["ret_next"] = df["ret"].shift(-1)                                   # the move over the next session
    df["implied_move"] = df["iv"] / 100.0 * np.sqrt(DAY)                   # 1-sigma one-day move, fraction of price
    df["implied_move_bp"] = 1e4 * df["implied_move"] / df["duration"]
    df["realised_move_bp"] = 1e4 * df["ret_next"].abs() / df["duration"]
    df["iv_change_next"] = df["iv"].shift(-1) - df["iv"]                    # the crush (or not) over the event day
    ev = D.event_calendar(start)
    ev = ev[ev["type"].isin(event_types)]
    tag = ev.groupby("date")["type"].apply(lambda x: "+".join(sorted(x)))
    # the event that falls on the NEXT session (the move ret_next spans it)
    nxt = pd.Series(df.index, index=df.index).shift(-1)
    df["event_next"] = [tag.get(d, "") if pd.notna(d) else "" for d in nxt]
    return df.dropna(subset=["ret_next"])


def event_premium_table(df, by="event_next"):
    """Ratio of realised to implied one-day move, mean |realised| / implied, the vol crush, by event type."""
    d = df.copy()
    d["kind"] = d[by].replace("", "none")
    d["kind"] = d["kind"].where(~d["kind"].str.contains("FOMC"), "FOMC")     # FOMC dominates a shared day
    d["kind"] = d["kind"].where(~d["kind"].str.contains("NFP") | (d["kind"] == "FOMC"), "NFP")
    d["kind"] = d["kind"].where(~d["kind"].str.startswith("AUCTION") | d["kind"].isin(["FOMC", "NFP"]), "AUCTION")
    d["ratio"] = d["realised_move_bp"] / d["implied_move_bp"]
    d["abs_ret_over_implied"] = d["ret_next"].abs() / d["implied_move"]
    g = d.groupby("kind").agg(n=("ratio", "size"), implied_bp=("implied_move_bp", "mean"), realised_bp=("realised_move_bp", "mean"),
                              ratio_mean=("abs_ret_over_implied", "mean"), ratio_median=("abs_ret_over_implied", "median"),
                              frac_beyond_1sigma=("abs_ret_over_implied", lambda x: float((x > 1).mean())),
                              iv_change_next=("iv_change_next", "mean"), iv_change_median=("iv_change_next", "median"))
    # a normal move has E|z| = sqrt(2/pi) = 0.798 and P(|z|>1) = 0.317
    g["ratio_vs_normal"] = g["ratio_mean"] / np.sqrt(2 / np.pi)
    return g


def event_premium_by_year(df):
    d = df[df["event_next"].str.contains("FOMC")].copy()
    d["year"] = d.index.year
    d["ratio"] = d["ret_next"].abs() / d["implied_move"] / np.sqrt(2 / np.pi)
    return d.groupby("year").agg(n=("ratio", "size"), realised_over_implied=("ratio", "mean"), implied_bp=("implied_move_bp", "mean"),
                                 realised_bp=("realised_move_bp", "mean"), crush=("iv_change_next", "mean"))


def bootstrap_ratio(x, B=2000, seed=7):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 5:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    m = np.array([x[rng.integers(0, x.size, x.size)].mean() for _ in range(B)])
    return float(x.mean()), float(np.quantile(m, 0.025)), float(np.quantile(m, 0.975))


# ---- the Atlanta Fed distribution as the STIR-implied event input ----------------------------------------------------------
def mpt_uncertainty():
    """From the Market Probability Tracker: for each date, the next reference window's 25th-75th percentile range
    of the implied policy rate (bp), P(cut), P(hike) - the SOFR-option-implied uncertainty about the next FOMC."""
    m = D.mpt()
    if m is None:
        return None
    m = m[m["field"].isin(["Rate: 25th percentile", "Rate: 75th percentile", "Rate: mean", "Prob: cut", "Prob: hike"])]
    w = m.pivot_table(index=["date", "reference_start"], columns="field", values="value").reset_index()
    w = w.rename(columns={"Rate: 25th percentile": "p25", "Rate: 75th percentile": "p75", "Rate: mean": "mean", "Prob: cut": "p_cut", "Prob: hike": "p_hike"})
    w = w[w["reference_start"] > w["date"]]
    nxt = w.sort_values(["date", "reference_start"]).groupby("date").first()
    nxt["iqr_bp"] = nxt["p75"] - nxt["p25"]
    nxt["days_to_meeting"] = (nxt["reference_start"] - nxt.index).dt.days
    return nxt


def mpt_vs_realised(df_vxtlt):
    """Does the SOFR-implied uncertainty the day before an FOMC explain the size of the long-end move on the day?"""
    u = mpt_uncertainty()
    if u is None:
        return None
    ev = df_vxtlt[df_vxtlt["event_next"].str.contains("FOMC")].copy()
    ev = ev.join(u[["iqr_bp", "p_cut", "p_hike", "days_to_meeting"]], how="inner")
    ev["undecided"] = 1 - (ev[["p_cut", "p_hike"]].max(axis=1) / 100).clip(0, 1)
    return ev
