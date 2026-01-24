"""The pipeline: durations -> the bp-vol cube and taking costs from today's chains -> event variance (today's
extraction and the 22-year history) -> the variance risk premium and the forecast test -> the four strategies
with measured costs -> results/run.json and data/derived/*.parquet.  `python -m ratesvol run [--chains DIR]`."""
from __future__ import annotations

import datetime as dt
import json
import os

import numpy as np
import pandas as pd

from . import cube as C
from . import data as D
from . import density as Z
from . import duration as U
from . import events as E
from . import rv as R
from . import vrp as V

FUNDS = ("SHY", "IEI", "IEF", "TLH", "TLT", "AGG", "LQD", "HYG")


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, pd.DataFrame):
        return _jsonable(o.reset_index().to_dict("records"))
    if isinstance(o, pd.Series):
        return _jsonable(o.to_dict())
    if isinstance(o, (pd.Timestamp, dt.date, dt.datetime)):
        return str(o)[:19]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return _jsonable(o.tolist())
    return o


def run(chains_dir=None, results_dir=None, derived_dir=None, fast=False):
    results_dir = results_dir or os.path.join(D.ROOT, "results")
    derived_dir = derived_dir or D.DERIVED
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(derived_dir, exist_ok=True)
    out = {"asof": dt.datetime.now().isoformat(timespec="seconds"), "fast": fast}
    t0 = dt.datetime.now()

    # ---- 1. durations ------------------------------------------------------------------------------------------------------
    dur_tab = U.duration_table()
    dur_ser = U.duration_series()
    dur_tab.to_parquet(os.path.join(derived_dir, "duration_table.parquet"))
    dur_ser.to_parquet(os.path.join(derived_dir, "durations.parquet"))
    out["duration"] = dur_tab
    print(f"durations: {len(dur_tab)} instruments", flush=True)

    # ---- 2. the cube from the latest chains -----------------------------------------------------------------------------------
    slices, quotes = C.cube(FUNDS, raw_dir=chains_dir)
    out["cube"] = {}
    if not slices.empty:
        slices.to_parquet(os.path.join(derived_dir, "slices.parquet"))
        quotes.drop(columns=["last_time"], errors="ignore").to_parquet(os.path.join(derived_dir, "quotes.parquet"))
        costs = C.taking_cost_table(quotes)
        costs.to_parquet(os.path.join(derived_dir, "taking_costs.parquet"))
        grid = C.surface_grid(slices)
        grid.to_parquet(os.path.join(derived_dir, "surface_grid.parquet"))
        atm = {}
        for sym, s in slices.groupby("symbol"):
            atm[sym] = {"label": D.FUND_LABEL.get(sym), "tenor": D.FUND_TENOR.get(sym), "spot": float(s["spot"].iloc[0]), "duration": float(s["duration"].iloc[0]),
                        "snapshot": s["snapshot"].iloc[0], "asof": s["asof"].iloc[0], "n_expiries": int(len(s)), "n_quotes": int(s["n_quotes"].sum()),
                        "atm_bpvol_1m": C.interpolate_atm(s, 30), "atm_bpvol_3m": C.interpolate_atm(s, 91), "atm_bpvol_6m": C.interpolate_atm(s, 182),
                        "atm_lnvol_1m": C.interpolate_atm(s, 30) * s["duration"].iloc[0] / 1e4,
                        "skew_50bp_1m": float(np.interp(30, s["days"], s["skew_50bp"])), "skew_100bp_3m": float(np.interp(91, s["days"], s["skew_100bp"])),
                        "rmse_bpvol_median": float(s["rmse_bpvol"].median()), "inside_market": float(s["inside_market"].mean()),
                        "atm_halfspread_vol_1m": float(np.interp(30, s["days"], s["atm_halfspread_vol"])) * 100,
                        "atm_halfspread_bpvol_1m": float(np.interp(30, s["days"], s["atm_halfspread_bpvol"])), "vendor_iv30": s["vendor_iv30"].iloc[0]}
        vi = D.vol_indices()
        out["cube"] = {"funds": atm, "n_slices": int(len(slices)), "n_quotes": int(len(quotes)), "chain_date": str(slices["asof"].iloc[0])[:10],
                       "move_latest": float(vi["MOVE"].dropna().iloc[-1]), "move_date": str(vi["MOVE"].dropna().index[-1].date()),
                       "vxtlt_latest": float(vi["VXTLT"].dropna().iloc[-1]), "taking_costs": costs}
        # density and event extraction per fund
        dens, extr, shares = [], [], []
        ev_cal = D.event_calendar(str(dt.date.today() - dt.timedelta(days=1)), str(dt.date.today() + dt.timedelta(days=400)))
        for sym, s in slices.groupby("symbol"):
            dd = Z.density_table(s)
            dd["symbol"] = sym
            dens.append(dd)
            if sym not in ("TLT", "IEF", "TLH", "IEI", "SHY") or len(s) < 6:      # the extraction needs a dense expiry ladder on a Treasury fund
                continue
            diff, J, res = E.extract_event_variance(s, ev_cal)
            if not J.empty:
                J["symbol"], J["diffusive_bpvol"], J["fit_resid_bpvol"] = sym, diff, res
                extr.append(J)
                sh = E.event_share(s, ev_cal)
                sh["symbol"] = sym
                shares.append(sh)
        if dens:
            pd.concat(dens).to_parquet(os.path.join(derived_dir, "density.parquet"))
            out["density"] = pd.concat(dens)[["symbol", "expiry", "days", "sd_atm_bp", "sd_density_bp", "skewness", "p_up_25", "p_dn_25", "p_abs_25_gauss", "p_up_50", "p_dn_50", "p_abs_50_gauss"]]
        if extr:
            ex = pd.concat(extr)
            ex.to_parquet(os.path.join(derived_dir, "event_extraction.parquet"))
            pd.concat(shares).to_parquet(os.path.join(derived_dir, "event_share.parquet"))
            out["event_extraction"] = ex
            tl = ex[ex["symbol"] == "TLT"] if "TLT" in set(ex["symbol"]) else ex
            diffusive_daily = float(tl["diffusive_bpvol"].iloc[0]) / np.sqrt(252)
            mult = {}
            for typ in ("FOMC", "NFP"):
                j = tl[tl["type"].str.contains(typ) & tl["identified"]]["J_bp"]
                if len(j):
                    mult[typ] = float(np.sqrt(diffusive_daily ** 2 + j.median() ** 2) / diffusive_daily)
            out["event_day_multiple"] = mult      # event-day implied move / diffusive-day implied move, from the chain
        print(f"cube: {len(slices)} slices, {len(quotes)} quotes on {out['cube']['chain_date']}", flush=True)

    # ---- 3. events: the history ---------------------------------------------------------------------------------------------------
    hist = {}
    ev_tables = {}
    for idx in ("VXTLT", "TYVIX"):
        df = E.implied_vs_realised(idx)
        ev_tables[idx] = df
        tab = E.event_premium_table(df)
        by_year = E.event_premium_by_year(df)
        cis = {}
        for kind in tab.index:
            d = df.copy()
            d["kind"] = d["event_next"].replace("", "none")
            sel = d["kind"].str.contains(kind) if kind != "none" else (d["kind"] == "none")
            if kind == "AUCTION":
                sel = d["kind"].str.startswith("AUCTION")
            x = (d.loc[sel, "ret_next"].abs() / d.loc[sel, "implied_move"] / np.sqrt(2 / np.pi)).values
            cis[kind] = E.bootstrap_ratio(x)
        tab["ratio_lo"] = [cis[k][1] for k in tab.index]
        tab["ratio_hi"] = [cis[k][2] for k in tab.index]
        hist[idx] = {"n_days": int(len(df)), "from": str(df.index[0].date()), "to": str(df.index[-1].date()), "by_event": tab, "fomc_by_year": by_year}
        df.assign(index=idx).reset_index().to_parquet(os.path.join(derived_dir, f"event_history_{idx}.parquet"))
    out["event_history"] = hist
    m = D.mpt()
    if m is not None:
        acc = Z.mpt_accuracy(m, D.fomc())
        acc.to_parquet(os.path.join(derived_dir, "mpt_accuracy.parquet"))
        mv = E.mpt_vs_realised(ev_tables["VXTLT"])
        out["mpt"] = {"n_meetings": int(len(acc)), "brier": float(acc["brier"].mean()), "modal_hit": float((acc["modal"] == acc["decision"]).mean()),
                      "table": acc, "iqr_vs_realised_corr": float(np.corrcoef(mv["iqr_bp"], mv["realised_move_bp"])[0, 1]) if mv is not None and len(mv) > 3 else None,
                      "iqr_vs_implied_corr": float(np.corrcoef(mv["iqr_bp"], mv["implied_move_bp"])[0, 1]) if mv is not None and len(mv) > 3 else None,
                      "n_fomc_matched": int(len(mv)) if mv is not None else 0}
    print("events: history and MPT done", flush=True)

    # ---- 4. the variance risk premium -----------------------------------------------------------------------------------------------
    prem = {n: V.premium_table(n) for n in ("VXTLT", "TYVIX", "MOVE", "SRVIX")}
    pd.concat([p.assign(index=n) for n, p in prem.items()]).reset_index().to_parquet(os.path.join(derived_dir, "premium.parquet"))
    out["vrp"] = {"summary": V.premium_summary(prem), "by_year": V.premium_by_year(prem), "forecast": V.forecast_table(prem, window=500 if fast else 750)}
    print("vrp: premium and forecasts done", flush=True)

    # ---- 5. strategies with measured costs ---------------------------------------------------------------------------------------------
    strat = {}
    if not slices.empty and "TLT" in set(slices["symbol"]):
        s_tlt = slices[slices["symbol"] == "TLT"]
        hs_vol, rel = R.measured_costs(s_tlt, quotes, "TLT")
        cost_tlt, hedge_tlt = R.cost_model(hs_vol, rel, s_tlt["atm_lnvol"].iloc[0])
    else:
        hs_vol, rel, cost_tlt, hedge_tlt = 0.001, 6e-5, 0.28, 0.08
    cost_zn = 0.4 * cost_tlt          # assumption: ZN options quote tighter in vol than TLT options; sensitivity below
    strat["costs"] = {"tlt_atm_halfspread_volpts": hs_vol * 100, "tlt_rel_halfspread": rel, "tlt_roundtrip_volpts": cost_tlt, "tlt_hedge_volpts": hedge_tlt,
                      "zn_roundtrip_volpts_assumed": cost_zn}
    rows, pnls = [], []
    for idx, c in (("VXTLT", cost_tlt), ("TYVIX", cost_zn)):
        a, b, _ = R.vrp_strategy(idx, c)
        rows.append(R.summarise(a, f"{idx} short vega when E[premium]>0"))
        rows.append(R.summarise(b, f"{idx} always short vega"))
        pnls.append(a.assign(strategy=f"vrp_signal_{idx}"))
        pnls.append(b.assign(strategy=f"vrp_always_{idx}"))
        for mult in (2, 4):
            a2, _, _ = R.vrp_strategy(idx, c * mult)
            rows.append(R.summarise(a2, f"{idx} short vega when E[premium]>0, costs x{mult}"))
    strat["vrp_threshold_sweep"] = R.vrp_threshold_sweep("VXTLT", cost_tlt)
    t, j = R.tenor_rv(cost_tlt, cost_zn)
    rows.append(R.summarise(t, "tenor RV: TLT vs ZN bp vol, |z|>1"))
    pnls.append(t.assign(strategy="tenor_rv"))
    strat["tenor_rv_predictive"] = R.tenor_rv_predictive(j)
    mult = out.get("event_day_multiple", {})
    ev_rows = []
    hs_price_frac = float(np.interp(1, s_tlt["days"], s_tlt["atm_halfspread_price"]) / (0.8 * s_tlt["spot"].iloc[0] * s_tlt["atm_lnvol"].iloc[0] / np.sqrt(252))) if not slices.empty and "TLT" in set(slices["symbol"]) else 0.05
    for ev in ("FOMC", "NFP"):
        e = R.event_strategy(ev_tables["VXTLT"], ev, cost_frac_of_premium=hs_price_frac)
        ev_rows.append(R.event_summary(e, f"{ev} straddle, signal = trailing 8 events, index-implied move"))
        pnls.append(e[["position", "gross", "cost", "net"]].assign(strategy=f"event_{ev}"))
        if ev in mult:
            e2 = R.event_strategy(ev_tables["VXTLT"], ev, cost_frac_of_premium=hs_price_frac, event_multiple=mult[ev])
            ev_rows.append(R.event_summary(e2, f"{ev} straddle, event-day implied x{mult[ev]:.2f} from the chain"))
    strat["strategies"] = pd.DataFrame(rows)
    strat["event_strategies"] = pd.DataFrame(ev_rows)
    strat["cross_market"] = R.cross_market_tables()
    strat["event_cost_frac_of_premium"] = hs_price_frac
    pd.concat(pnls).reset_index().to_parquet(os.path.join(derived_dir, "strategy_pnl.parquet"))
    out["strategies"] = strat
    print("strategies done", flush=True)

    out["elapsed_s"] = (dt.datetime.now() - t0).total_seconds()
    with open(os.path.join(results_dir, "run.json"), "w") as f:
        json.dump(_jsonable(out), f, indent=1)
    print(f"results -> {os.path.join(results_dir, 'run.json')} ({out['elapsed_s']:.0f}s)", flush=True)
    return out
