"""Risk-neutral densities from the fitted smiles (Breeden & Litzenberger 1978) and the policy-rate distribution
the SOFR options imply (from the Atlanta Fed's tracker, which is built from CME SOFR options the way a desk
would build it - the reference this project checks the long end against).

The density of the fund's price at expiry is the second strike-derivative of the undiscounted call price off the
normal-SABR smile; mapped to yield through the duration it gives the probability the benchmark yield moves more
than x bp by the expiry, which is what a rates trader asks of a smile.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import pricing as P
from .cube import normal_sabr


def price_density(slice_row, n=801, width_bp=400):
    """Density of the fund price at expiry on a grid spanning +-width_bp of yield, from the SABR slice."""
    F, T, D = slice_row["F"], slice_row["T"], slice_row["duration"]
    a, rho, nu = slice_row["alpha"], slice_row["rho"], slice_row["nu"]
    y_bp = np.linspace(-width_bp, width_bp, n)
    K = F * np.exp(-y_bp * 1e-4 * D)                                         # yield up -> price down
    K = np.sort(K)
    sig = normal_sabr(K, F, T, a, rho, nu)
    C = P.bachelier_price(F, K, T, sig, call=True)
    dK = np.gradient(K)
    dens = np.gradient(np.gradient(C, K), K)
    dens = np.clip(dens, 0, None)
    mass = np.trapezoid(dens, K)
    dens = dens / mass if mass > 0 else dens
    y_of_K = -1e4 * np.log(K / F) / D
    dens_y = dens * np.abs(np.gradient(K, y_of_K))                           # change of variable to yield bp
    order = np.argsort(y_of_K)
    return pd.DataFrame({"K": K[order], "yield_bp": y_of_K[order], "density_price": dens[order], "density_yield": dens_y[order], "mass_raw": mass})


def tail_probabilities(slice_row, thresholds=(10, 25, 50, 100)):
    """P(|yield move| > x bp by expiry) from the smile, next to the Gaussian value at the ATM bp vol."""
    d = price_density(slice_row)
    y, f = d["yield_bp"].values, d["density_yield"].values
    f = f / np.trapezoid(f, y)
    sd_atm = slice_row["atm_bpvol"] * np.sqrt(slice_row["T"])
    out = {"expiry": slice_row["expiry"], "days": slice_row["days"], "sd_atm_bp": sd_atm, "sd_density_bp": float(np.sqrt(np.trapezoid(f * y ** 2, y) - np.trapezoid(f * y, y) ** 2)),
           "mean_bp": float(np.trapezoid(f * y, y)), "skewness": np.nan}
    m = out["mean_bp"]
    var = out["sd_density_bp"] ** 2
    out["skewness"] = float(np.trapezoid(f * (y - m) ** 3, y) / var ** 1.5) if var > 0 else np.nan
    from scipy.stats import norm
    for x in thresholds:
        out[f"p_up_{x}"] = float(np.trapezoid(f[y > x], y[y > x]))
        out[f"p_dn_{x}"] = float(np.trapezoid(f[y < -x], y[y < -x]))
        out[f"p_abs_{x}_gauss"] = float(2 * norm.sf(x / sd_atm))
    return out


def density_table(slices, max_days=200):
    rows = [tail_probabilities(r) for _, r in slices[slices["days"] <= max_days].sort_values("T").iterrows()]
    return pd.DataFrame(rows)


# ---- the SOFR-implied policy distribution ---------------------------------------------------------------------------------------
def mpt_snapshot(m, date=None):
    """The full implied distribution over policy-rate buckets for every reference window on one date."""
    m = m[m["field"].str.startswith("Prob: ") & ~m["field"].isin(["Prob: cut", "Prob: hike"])].copy()
    if date is None:
        date = m["date"].max()
    s = m[m["date"] == pd.Timestamp(date)].copy()
    s["bucket_lo"] = s["field"].str.extract(r"(\d+)bps").astype(float)
    return s.pivot_table(index="bucket_lo", columns="reference_start", values="value").fillna(0.0)


def mpt_accuracy(m, fomc, cmt_2y=None):
    """Did the SOFR options know?  For each FOMC since 2023: the day-before P(cut), P(hike) and the modal bucket
    against the decision (from the change in the target-range field), plus a Brier score."""
    f = m[m["field"].isin(["Prob: cut", "Prob: hike"])].pivot_table(index=["date", "reference_start"], columns="field", values="value").reset_index()
    tr = m[["date", "reference_start", "target_range"]].drop_duplicates()
    rows = []
    meetings = sorted(m["reference_start"].unique())
    for i, ref in enumerate(meetings):
        before = f[(f["reference_start"] == ref) & (f["date"] < ref)].sort_values("date")
        if before.empty:
            continue
        last = before.iloc[-1]
        # the realised decision: the target range in force on the first date after the meeting vs before
        rng_before = tr[tr["date"] == last["date"]]["target_range"].iloc[0]
        after = tr[tr["date"] > ref]
        if after.empty:
            continue
        rng_after = after.sort_values("date")["target_range"].iloc[0]
        lo_b = float(rng_before.split("bps")[0])
        lo_a = float(rng_after.split("bps")[0])
        decision = "cut" if lo_a < lo_b else ("hike" if lo_a > lo_b else "hold")
        p_cut, p_hike = last["Prob: cut"] / 100, last["Prob: hike"] / 100
        p_hold = max(0.0, 1 - p_cut - p_hike)
        probs = {"cut": p_cut, "hike": p_hike, "hold": p_hold}
        brier = sum((probs[k] - (1.0 if k == decision else 0.0)) ** 2 for k in probs)
        rows.append({"meeting": pd.Timestamp(ref).date(), "asof": last["date"].date(), "p_cut": p_cut, "p_hike": p_hike, "p_hold": p_hold,
                     "decision": decision, "modal": max(probs, key=probs.get), "brier": brier})
    return pd.DataFrame(rows)
