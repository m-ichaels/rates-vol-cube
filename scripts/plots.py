#!/usr/bin/env python3
"""Figures from results/run.json and data/derived/*.parquet -> results/figures/.   python scripts/plots.py"""
import json
import os
import sys

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ratesvol import data as D  # noqa: E402

DER = D.DERIVED
FIG = os.path.join(ROOT, "results", "figures")
os.makedirs(FIG, exist_ok=True)
plt.rcParams.update({"figure.dpi": 130, "font.size": 9, "axes.grid": True, "grid.alpha": 0.3, "axes.spines.top": False, "axes.spines.right": False})
R = json.load(open(os.path.join(ROOT, "results", "run.json")))


def load(name):
    p = os.path.join(DER, name)
    return pd.read_parquet(p) if os.path.exists(p) else None


def save(name):
    plt.tight_layout()
    plt.savefig(os.path.join(FIG, name))
    plt.close()
    print("  ", name)


# 1. the cube: ATM bp vol term structure per fund, and the smiles of TLT
slices = load("slices.parquet")
grid = load("surface_grid.parquet")
if slices is not None:
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for sym, s in slices.sort_values("T").groupby("symbol"):
        if sym in ("HYG", "LQD", "AGG"):
            continue
        ax[0].plot(s["days"], s["atm_bpvol"], "o-", ms=3, label=f"{sym} ({D.FUND_LABEL.get(sym)}, D={s['duration'].iloc[0]:.1f})")
    ax[0].axhline(R["cube"]["move_latest"], color="k", ls="--", lw=1, label=f"MOVE {R['cube']['move_latest']:.0f} ({R['cube']['move_date']})")
    ax[0].set_xscale("log")
    ax[0].set_xlabel("days to expiry")
    ax[0].set_ylabel("ATM normal vol, bp / year")
    ax[0].set_title(f"ATM basis-point vol by fund, {R['cube']['chain_date']}")
    ax[0].legend(fontsize=7)
    g = grid[grid["symbol"] == "TLT"]
    for days in sorted(g["days"].unique()):
        if 20 < days < 200:
            gg = g[g["days"] == days]
            ax[1].plot(gg["moneyness_bp"], gg["bpvol"], label=f"{days:.0f}d")
    ax[1].set_xlabel("strike in bp of yield above the forward (puts on the fund = payers)")
    ax[1].set_ylabel("normal vol, bp / year")
    ax[1].set_title("TLT smiles in yield space (normal SABR)")
    ax[1].legend(fontsize=7, ncol=2)
    save("cube.png")

    q = load("quotes.parquet")
    if q is not None:
        t = q[q["symbol"] == "TLT"]
        exp = t.iloc[(t["T"] * 365 - 30).abs().argsort()[:1]]["expiry"].iloc[0]
        t = t[t["expiry"] == exp].sort_values("strike")
        fig, ax = plt.subplots(figsize=(6.5, 4))
        ax.fill_between(t["moneyness_bp"], t["bpvol_bid"], t["bpvol_ask"], alpha=0.3, label="bid-ask")
        ax.plot(t["moneyness_bp"], t["bpvol_mid"], "k.", ms=4, label="mid")
        ax.plot(t["moneyness_bp"], t["bpvol_fit"], "r-", lw=1.2, label="normal SABR")
        ax.set_xlabel("strike, bp of yield above forward")
        ax.set_ylabel("bp vol")
        ax.set_title(f"TLT {str(exp)[:10]} ({t['T'].iloc[0] * 365:.0f}d): quotes and fit")
        ax.legend()
        save("smile_fit.png")

# 2. event variance extraction and the event history
ex = load("event_extraction.parquet")
if ex is not None and (ex["symbol"] == "TLT").any():
    e = ex[ex["symbol"] == "TLT"]
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    colors = e["type"].map(lambda t: "C3" if "FOMC" in t else ("C0" if "NFP" in t else "C2"))
    bars = ax[0].bar(range(len(e)), e["J_bp"], color=colors)
    for b, ident in zip(bars, e["identified"]):
        b.set_alpha(1.0 if ident else 0.35)
    ax[0].set_xticks(range(len(e)))
    ax[0].set_xticklabels([f"{t}\n{str(d)[:10]}" for t, d in zip(e["type"], e["date"])], fontsize=7)
    ax[0].axhline(e["diffusive_bpvol"].iloc[0] / np.sqrt(252), color="k", ls="--", lw=1, label="diffusive day")
    ax[0].set_ylabel("implied one-day move, bp")
    ax[0].set_title("TLT: event variance from the expiry ladder (faded = not identified)")
    ax[0].legend()
    for idx, c in (("VXTLT", "C0"), ("TYVIX", "C1")):
        tab = pd.DataFrame(R["event_history"][idx]["by_event"]).set_index("kind")
        x = np.arange(len(tab)) + (0.2 if idx == "TYVIX" else -0.2)
        ax[1].bar(x, tab["ratio_vs_normal"], 0.4, yerr=[tab["ratio_vs_normal"] - tab["ratio_lo"], tab["ratio_hi"] - tab["ratio_vs_normal"]], color=c, label=idx, capsize=2)
        ax[1].set_xticks(np.arange(len(tab)))
        ax[1].set_xticklabels(tab.index)
    ax[1].axhline(1, color="k", lw=1)
    ax[1].set_ylabel("realised / implied one-day move")
    ax[1].set_title("2004-2026: realised move over the index-implied move, by event")
    ax[1].legend()
    save("events.png")

# 3. the premium: implied vs realised through time, and by year
prem = load("premium.parquet")
if prem is not None:
    fig, ax = plt.subplots(2, 2, figsize=(11, 6.5))
    for a, idx in zip(ax.ravel(), ("VXTLT", "TYVIX", "MOVE", "SRVIX")):
        p = prem[prem["index"] == idx].set_index("date")
        a.plot(p.index, p["iv"], lw=0.8, label="implied")
        a.plot(p.index, p["rvol_fwd"], lw=0.8, alpha=0.8, label="realised, next 21 sessions")
        s = pd.DataFrame(R["vrp"]["summary"]).set_index("index").loc[idx]
        a.set_title(f"{idx}: premium {s['vrp_mean']:.2f} [{s['vrp_lo']:.2f}, {s['vrp_hi']:.2f}] {'bp' if idx in ('MOVE', 'SRVIX') else 'vol pts'}")
        a.legend(fontsize=7)
    save("vrp.png")

# 4. strategies: cumulative net P&L
pnl = load("strategy_pnl.parquet")
if pnl is not None:
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for name, lab in (("vrp_signal_VXTLT", "TLT: short vega when E[premium]>0"), ("vrp_always_VXTLT", "TLT: always short"),
                      ("vrp_signal_TYVIX", "ZN: short vega when E[premium]>0"), ("vrp_always_TYVIX", "ZN: always short"), ("tenor_rv", "tenor RV TLT vs ZN")):
        p = pnl[pnl["strategy"] == name].sort_values("date")
        if len(p):
            ax[0].plot(p["date"], p["net"].cumsum(), lw=1, label=lab)
    ax[0].set_ylabel("cumulative net P&L, vol points per unit vega")
    ax[0].set_title("one-month vega positions, rolled monthly, net of measured costs")
    ax[0].legend(fontsize=7)
    for name, lab in (("event_FOMC", "FOMC straddle, signal"), ("event_NFP", "NFP straddle, signal")):
        p = pnl[pnl["strategy"] == name].sort_values("date")
        if len(p):
            ax[1].plot(p["date"], p["net"].cumsum(), lw=1, label=lab)
    ax[1].set_ylabel("cumulative net P&L, bp of yield per unit implied move")
    ax[1].set_title("event straddles off the index-implied move (see the multiple)")
    ax[1].legend(fontsize=7)
    save("strategies.png")

# 5. taking costs: half-spread in bp vol by tenor and moneyness (TLT)
tc = load("taking_costs.parquet")
if tc is not None and (tc["symbol"] == "TLT").any():
    t = tc[tc["symbol"] == "TLT"].pivot_table(index="money_bucket", columns="tenor_bucket", values="halfspread_bpvol", observed=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    im = ax.imshow(t.values, aspect="auto", cmap="viridis")
    ax.set_xticks(range(t.shape[1]))
    ax.set_xticklabels(t.columns)
    ax.set_yticks(range(t.shape[0]))
    ax.set_yticklabels(t.index)
    for i in range(t.shape[0]):
        for j in range(t.shape[1]):
            if np.isfinite(t.values[i, j]):
                ax.text(j, i, f"{t.values[i, j]:.1f}", ha="center", va="center", color="w", fontsize=7)
    plt.colorbar(im, label="half-spread, bp vol")
    ax.set_title("TLT: what a taker pays to cross, by tenor and strike")
    save("taking_cost.png")

# 6. densities and the policy distribution
dens = load("density.parquet")
mp = D.mpt()
if dens is not None:
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    d = dens[dens["symbol"] == "TLT"]
    ax[0].plot(d["days"], d["p_up_25"] + d["p_dn_25"], "o-", ms=3, label="P(|move| > 25 bp), smile")
    ax[0].plot(d["days"], d["p_abs_25_gauss"], "--", label="Gaussian at ATM vol")
    ax[0].plot(d["days"], d["p_up_50"] + d["p_dn_50"], "o-", ms=3, label="P(|move| > 50 bp), smile")
    ax[0].plot(d["days"], d["p_abs_50_gauss"], "--", label="Gaussian at ATM vol")
    ax[0].set_xlabel("days to expiry")
    ax[0].set_ylabel("probability")
    ax[0].set_title("TLT: tail probabilities of the 20y yield from the smile")
    ax[0].legend(fontsize=7)
    if mp is not None:
        from ratesvol.density import mpt_snapshot
        snap = mpt_snapshot(mp)
        for col in snap.columns[:3]:
            ax[1].plot(snap.index, snap[col], "o-", ms=3, label=str(col)[:10])
        ax[1].set_xlabel("policy rate bucket, bp (lower bound)")
        ax[1].set_ylabel("probability, %")
        ax[1].set_title(f"SOFR-option-implied policy rate (Atlanta Fed MPT, {str(mp['date'].max())[:10]})")
        ax[1].legend(fontsize=7)
        ax[1].set_xlim(250, 650)
    save("density.png")

# 7. empirical durations through time
dur = load("durations.parquet")
if dur is not None:
    fig, ax = plt.subplots(figsize=(7, 3.5))
    for c in dur.columns:
        ax.plot(dur.index, dur[c], lw=0.9, label=c)
    ax.set_ylabel("empirical duration, years")
    ax.set_title("empirical duration: -d ln P / dy on the benchmark CMT, trailing 250 days")
    ax.legend(fontsize=7, ncol=3)
    save("duration.png")
