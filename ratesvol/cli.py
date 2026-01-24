"""python -m ratesvol <run|cube|events|vrp|density|sql> [options]

  run       [--chains DIR] [--fast]         the whole pipeline -> results/run.json, data/derived/
  cube      [--symbol TLT] [--date D]       fit and print the bp-vol slices of one fund's closing chain
  events    [--symbol TLT]                  the event-variance extraction on the latest chain, and the history table
  vrp                                       the premium summary and the forecast table
  density   [--symbol TLT]                  tail probabilities from the smile by expiry
  sql       "SELECT ..."                    run a query against the DuckDB views (prices, cmt, vol_indices, slices, quotes, ...)
"""
from __future__ import annotations

import sys

import pandas as pd


def _args(argv):
    out, i = {}, 0
    while i < len(argv):
        if argv[i].startswith("--"):
            k = argv[i][2:]
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                out[k] = argv[i + 1]
                i += 2
            else:
                out[k] = True
                i += 1
        else:
            out.setdefault("_", []).append(argv[i])
            i += 1
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 1
    cmd, a = argv[0], _args(argv[1:])
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 40)
    if cmd == "run":
        from .run import run
        run(chains_dir=a.get("chains"), fast=bool(a.get("fast")))
        return 0
    if cmd == "cube":
        from . import cube as C, data as D
        sym = a.get("symbol", "TLT")
        p = D.closing_snapshot(sym, a.get("date"), a.get("chains"))
        if not p:
            print("no chain recorded for", sym)
            return 1
        und, s, q = C.fit_snapshot(p)
        print(f"{sym} {und['recorded']} spot {und['spot']} duration {s['duration'].iloc[0]:.2f}")
        print(s[["expiry", "days", "F", "n_quotes", "atm_bpvol", "atm_bpvol_daily", "atm_lnvol", "skew_50bp", "fly_100bp", "rho", "nu", "rmse_bpvol", "inside_market", "atm_halfspread_bpvol"]].round(3).to_string(index=False))
        print(f"ATM bp vol 1m {C.interpolate_atm(s, 30):.1f}  3m {C.interpolate_atm(s, 91):.1f}  6m {C.interpolate_atm(s, 182):.1f}")
        return 0
    if cmd == "events":
        from . import cube as C, data as D, events as E
        import datetime as dt
        sym = a.get("symbol", "TLT")
        p = D.closing_snapshot(sym, a.get("date"), a.get("chains"))
        if p:
            und, s, q = C.fit_snapshot(p)
            cal = D.event_calendar(str(dt.date.today() - dt.timedelta(days=1)), str(dt.date.today() + dt.timedelta(days=400)))
            diff, J, res = E.extract_event_variance(s, cal)
            print(f"{sym}: diffusive bp vol {diff:.1f} ({diff / 252 ** 0.5:.2f} bp/day), fit residual {res:.2f} bp vol")
            print(J.round(2).to_string(index=False))
        idx = "VXTLT" if sym in ("TLT", "TLH") else "TYVIX"
        df = E.implied_vs_realised(idx)
        print(f"\n{idx} history {df.index[0].date()} .. {df.index[-1].date()}: realised / implied one-day move by event")
        print(E.event_premium_table(df).round(3).to_string())
        return 0
    if cmd == "vrp":
        from . import vrp as V
        prem = {n: V.premium_table(n) for n in ("VXTLT", "TYVIX", "MOVE", "SRVIX")}
        print(V.premium_summary(prem).round(3).to_string())
        print(V.forecast_table(prem).round(3).to_string())
        return 0
    if cmd == "density":
        from . import cube as C, data as D, density as Z
        sym = a.get("symbol", "TLT")
        p = D.closing_snapshot(sym, a.get("date"), a.get("chains"))
        und, s, q = C.fit_snapshot(p)
        print(Z.density_table(s).round(3).to_string(index=False))
        return 0
    if cmd == "sql":
        from . import data as D
        con = D.store()
        print(con.execute(" ".join(a.get("_", []))).df().to_string())
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
