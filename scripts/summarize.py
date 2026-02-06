#!/usr/bin/env python3
"""results/summary.md from results/run.json.   python scripts/summarize.py"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = json.load(open(os.path.join(ROOT, "results", "run.json")))
out = []
P = out.append


def table(df, cols=None, fmt="{:.2f}", index=True):
    df = df if cols is None else df[cols]
    rows = []
    hdr = ([df.index.name or ""] if index else []) + [str(c) for c in df.columns]
    rows.append("| " + " | ".join(hdr) + " |")
    rows.append("|" + "---|" * len(hdr))
    for i, r in df.iterrows():
        cells = ([str(i)] if index else []) + [(fmt.format(v) if isinstance(v, (float, np.floating)) and np.isfinite(v) else str(v)) for v in r.values]
        rows.append("| " + " | ".join(cells) + " |")
    out.extend(rows)
    P("")


P(f"# Results summary\n\nRun {R['asof'][:16]}.  Every number below is reproduced by `python -m ratesvol run`.\n")

# ---- cube ------------------------------------------------------------------------------------------------------------------
c = R.get("cube", {})
if c.get("funds"):
    P(f"## The bp-vol cube, chains of {c['chain_date']}\n")
    f = pd.DataFrame(c["funds"]).T
    f.index.name = "fund"
    P(f"{c['n_slices']} expiry slices, {c['n_quotes']} two-sided OTM quotes.  MOVE {c['move_latest']:.1f} on {c['move_date']}; VXTLT {c['vxtlt_latest']:.2f}.  ATM normal vol in bp per year from the fund's price vol through its empirical duration; skew = bp vol 50 bp above the forward yield minus 50 bp below (positive = payers rich).\n")
    table(f, ["label", "duration", "n_expiries", "n_quotes", "atm_bpvol_1m", "atm_bpvol_3m", "atm_bpvol_6m", "atm_lnvol_1m", "skew_50bp_1m", "rmse_bpvol_median", "inside_market", "atm_halfspread_vol_1m", "vendor_iv30"])
    if "event_day_multiple" in R:
        P("Event-day multiple (event-day implied move / diffusive-day implied move, TLT, identified events only): " + ", ".join(f"{k} {v:.2f}x" for k, v in R["event_day_multiple"].items()) + ".\n")
if "event_extraction" in R:
    P("### Event variance from the expiry ladder\n")
    e = pd.DataFrame(R["event_extraction"])
    table(e.set_index("symbol")[["date", "type", "J_bp", "days", "identified", "diffusive_bpvol", "fit_resid_bpvol"]])

# ---- history ---------------------------------------------------------------------------------------------------------------
P("## Scheduled events, 2004-2026: realised over implied one-day move\n")
P("Implied one-day move = index / sqrt(252) (VXTLT on TLT, TYVIX on the 10y note future), in bp through the empirical duration.  Ratio normalised so that a Gaussian day is 1; bootstrap 95% intervals.\n")
for idx, h in R["event_history"].items():
    P(f"**{idx}** ({h['from']} .. {h['to']}, {h['n_days']} days)\n")
    t = pd.DataFrame(h["by_event"]).set_index("kind")
    table(t, ["n", "implied_bp", "realised_bp", "ratio_vs_normal", "ratio_lo", "ratio_hi", "frac_beyond_1sigma", "iv_change_next"])
if "mpt" in R:
    m = R["mpt"]
    P(f"SOFR-option-implied FOMC distribution (Atlanta Fed tracker, {m['n_meetings']} quarterly meetings since 2023): modal outcome right {100 * m['modal_hit']:.0f}% of the time, Brier {m['brier']:.3f}; the implied 25-75 range the day before an FOMC correlates {m['iqr_vs_realised_corr']:.2f} with the realised 20y move on the day (n = {m['n_fomc_matched']}) and {m['iqr_vs_implied_corr']:.2f} with VXTLT's implied move.\n")

# ---- premium ---------------------------------------------------------------------------------------------------------------
P("## The variance risk premium in rates\n")
P("Implied minus realised vol over the next 21 sessions, daily; block-bootstrap 95% interval (21-day blocks).  VXTLT and TYVIX in vol points (and bp through the duration), MOVE and SRVIX in bp against the realised bp vol of the 10y CMT.\n")
s = pd.DataFrame(R["vrp"]["summary"]).set_index("index")
table(s, ["from", "to", "implied_mean", "realised_mean", "vrp_mean", "vrp_lo", "vrp_hi", "vrp_bp_mean", "months_realised_above", "corr_iv_fwd"])
P("### Does implied vol forecast realised?  Out-of-sample R^2 of log realised vol, walk-forward\n")
fc = pd.DataFrame(R["vrp"]["forecast"]).set_index("index")
table(fc, ["n_oos", "from", "r2_har", "r2_har_iv", "r2_iv_only", "r2_trailing22", "mae_har_volpts", "mae_har_iv_volpts", "bias_iv_volpts"], fmt="{:.3f}")
P("### Premium by year (vol points; MOVE and SRVIX in bp)\n")
by = pd.DataFrame(R["vrp"]["by_year"]).set_index("year").T
by.index.name = "index"
table(by, fmt="{:.1f}")

# ---- strategies ------------------------------------------------------------------------------------------------------------
st = R["strategies"]
P("## Strategies on the taking side, net of measured costs\n")
k = st["costs"]
P(f"Costs from the TLT chain: ATM half-spread {k['tlt_atm_halfspread_volpts']:.3f} vol points, fund half-spread {1e4 * k['tlt_rel_halfspread']:.2f} bp of price; a delta-hedged one-month straddle pays {k['tlt_roundtrip_volpts']:.2f} vol points per unit vega round trip ({k['tlt_hedge_volpts']:.2f} of it hedging).  ZN options assumed at {k['zn_roundtrip_volpts_assumed']:.2f} (0.4x TLT; the x2 / x4 rows are the sensitivity).  P&L = vega x (realised - implied) per monthly roll, vol points per unit vega; block-bootstrap intervals; Sharpe annualised from monthly rolls.\n")
table(pd.DataFrame(st["strategies"]).set_index("strategy"), ["rolls", "from", "active_share", "mean_gross", "mean_cost", "mean_net", "net_lo", "net_hi", "sharpe_net", "hit_rate", "max_drawdown", "worst_roll"])
P("Threshold sweep, TLT (short when the HAR+IV expected premium exceeds the threshold):\n")
table(pd.DataFrame(st["vrp_threshold_sweep"]).set_index("threshold"), ["active_share", "mean_net", "net_lo", "net_hi", "sharpe_net", "hit_rate", "max_drawdown"])
tp = st["tenor_rv_predictive"]
P(f"Tenor RV: the z-score of log(TLT bp vol / ZN bp vol) predicts the next-month change in the ratio with slope {tp['slope']:.3f} [{tp['lo']:.3f}, {tp['hi']:.3f}] per unit z (corr {tp['corr']:.2f}, n = {tp['n']}): the ratio mean-reverts, but the P&L table shows what that is worth after costs.\n")
P("### Event straddles\n")
P(f"One-day straddle priced off the index-implied move (VXTLT / sqrt(252)), payoff |realised move|, bp of yield per unit implied move; cost {100 * st['event_cost_frac_of_premium']:.1f}% of the premium (the TLT ATM half-spread over a one-day straddle).  The second row of each event re-prices the straddle at the event-day multiple the chain's expiry ladder implies today - the index-implied number is not what the event straddle costs.\n")
table(pd.DataFrame(st["event_strategies"]).set_index("strategy"), ["rolls", "mean_net", "net_lo", "net_hi", "hit_rate", "always_short_net_mean", "always_short_net_lo", "always_short_net_hi", "always_long_net_mean", "always_long_net_lo", "always_long_net_hi"])
P("### Cross-market bases\n")
table(pd.DataFrame(st["cross_market"]), fmt="{:.3f}")

# ---- durations -------------------------------------------------------------------------------------------------------------
P("## Empirical durations\n")
d = pd.DataFrame(R["duration"]).set_index("symbol")
table(d, ["benchmark", "empirical_duration", "se", "r2", "resid_bp_day", "stated_duration", "asof"])

open(os.path.join(ROOT, "results", "summary.md"), "w", encoding="utf-8").write("\n".join(out))
print("results/summary.md")
