"""Loaders: the reference tables tools/download.py writes, the chain snapshots tools/record.py records, the event
calendar, and a DuckDB store over all of it for the SQL post-trade analysis."""
from __future__ import annotations

import datetime as dt
import glob
import gzip
import json
import os
import re

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(ROOT, "data", "reference")
RAW = os.path.join(ROOT, "data", "raw")
DERIVED = os.path.join(ROOT, "data", "derived")

# the fund's benchmark tenor on the Treasury curve: the CMT column its yield moves with (used for the empirical duration
# and for expressing the fund's option smile in yield space)
FUND_TENOR = {"SHY": "2Yr", "IEI": "5Yr", "IEF": "10Yr", "TLH": "20Yr", "TLT": "20Yr", "AGG": "7Yr", "LQD": "10Yr", "HYG": "5Yr", "TBT": "20Yr"}
FUND_LABEL = {"SHY": "1-3y Treasury", "IEI": "3-7y Treasury", "IEF": "7-10y Treasury", "TLH": "10-20y Treasury", "TLT": "20+y Treasury",
              "AGG": "US aggregate", "LQD": "IG credit", "HYG": "HY credit", "TBT": "-2x 20+y Treasury", "SPY": "S&P 500"}
# what each vol index measures: (underlying series in prices.parquet, benchmark tenor, description)
VOL_INDEX = {"VXTLT": ("TLT", "20Yr", "Cboe 30-day implied vol of TLT options, lognormal, % p.a."),
             "TYVIX": ("ZN=F", "10Yr", "Cboe/CBOT 30-day implied vol of 10y note futures options, lognormal, % p.a."),
             "MOVE": (None, "curve", "ICE BofA MOVE: 1-month normal vol of 2y/5y/10y/30y Treasury options, bp p.a."),
             "SRVIX": (None, "10Yr", "Cboe swap rate vol index: 1y x 10y USD swaptions, bp p.a."),
             "VIX": ("SPY", None, "Cboe 30-day implied vol of SPX options, % p.a.")}


def ref(name, **kw):
    p = os.path.join(REF, name)
    if not os.path.exists(p):
        return None
    if name.endswith(".parquet"):
        return pd.read_parquet(p)
    return pd.read_csv(p, **kw)


def prices(symbol=None):
    d = ref("prices.parquet")
    if d is None:
        return None
    d["date"] = pd.to_datetime(d["date"])
    if symbol:
        d = d[d["symbol"] == symbol].set_index("date").sort_index()
    return d


def close_panel(symbols):
    d = prices()
    return d[d["symbol"].isin(symbols)].pivot(index="date", columns="symbol", values="close").sort_index()


def vol_indices():
    d = ref("vol_indices.csv")
    if d is None:
        return None
    d["date"] = pd.to_datetime(d["date"])
    return d.pivot(index="date", columns="name", values="value").sort_index()


def cmt():
    d = ref("treasury_cmt.csv")
    if d is None:
        return None
    d["date"] = pd.to_datetime(d["date"])
    return d.set_index("date").sort_index().astype(float)


def fomc():
    d = ref("fomc_dates.csv")
    if d is None:
        return None
    d["date"] = pd.to_datetime(d["date"])
    return d.sort_values("date")


def auctions():
    d = ref("auctions.csv")
    if d is None:
        return None
    d["auction_date"] = pd.to_datetime(d["auction_date"])
    return d


def mpt():
    d = ref("mpt_histdata.parquet")
    return d


def fund_duration():
    d = ref("fund_duration.csv")
    return d.set_index("symbol")["effective_duration"] if d is not None else None


# ---- event calendar ------------------------------------------------------------------------------------------------------
NFP_HOLIDAY_SHIFT = {(1, 1), (7, 4)}                     # a release that falls on a holiday Friday moves to the next Friday


def nfp_dates(start=dt.date(2003, 1, 1), end=None):
    """Employment Situation release: the third Friday after the end of the reference week (the week containing the
    12th of the reference month) - the BLS rule, which lands on the first Friday of the next month except when the
    calendar pushes it to the second."""
    end = end or dt.date.today() + dt.timedelta(days=90)
    out = []
    y, m = (start.year - 1, 12) if start.month == 1 else (start.year, start.month - 1)   # January's release is December's reference month
    while dt.date(y, m, 1) <= end:
        ref_day = dt.date(y, m, 12)
        week_end = ref_day + dt.timedelta(days=(5 - ref_day.weekday()) % 7)        # the Saturday closing the reference week
        release = week_end + dt.timedelta(days=(4 - week_end.weekday()) % 7 + 14)   # third Friday after
        if (release.month, release.day) in NFP_HOLIDAY_SHIFT:
            release += dt.timedelta(days=7)
        out.append(release)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return pd.to_datetime([d for d in out if start <= d <= end])


def event_calendar(start="2003-01-01", end=None):
    """One row per (date, type): FOMC (scheduled statement days), NFP, and 10y / 30y auctions (new issues and
    reopenings; 'term' keeps the tenor).  The auction result is at 13:00 New York, the others 08:30 / 14:00."""
    rows = []
    f = fomc()
    if f is not None:
        for _, r in f[f["scheduled"]].iterrows():
            rows.append({"date": r["date"], "type": "FOMC", "detail": "statement 14:00"})
    for d in nfp_dates(pd.Timestamp(start).date(), pd.Timestamp(end).date() if end else None):
        rows.append({"date": d, "type": "NFP", "detail": "08:30"})
    a = auctions()
    if a is not None:
        for _, r in a.iterrows():
            term = str(r["term"])
            if re.match(r"(9-Year 1[01]-Month|10-Year)", term):
                rows.append({"date": r["auction_date"], "type": "AUCTION10", "detail": term})
            elif re.match(r"(29-Year 1[01]-Month|30-Year)", term):
                rows.append({"date": r["auction_date"], "type": "AUCTION30", "detail": term})
    d = pd.DataFrame(rows)
    d = d[(d["date"] >= pd.Timestamp(start)) & (d["date"] <= pd.Timestamp(end or "2100-01-01"))]
    return d.drop_duplicates(["date", "type"]).sort_values(["date", "type"]).reset_index(drop=True)


# ---- chain snapshots ----------------------------------------------------------------------------------------------------------
OCC = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


def parse_occ(s):
    m = OCC.match(s)
    if not m:
        return None, None, None, None
    root, ymd, cp, k = m.groups()
    return root, pd.Timestamp(dt.datetime.strptime(ymd, "%y%m%d").date()), cp == "C", int(k) / 1000.0


CHAINS = os.path.join(ROOT, "data", "chains")          # the archived closing chains (tracked); data/raw/cboe holds every snapshot


def chains_dir():
    return CHAINS if glob.glob(os.path.join(CHAINS, "*", "*.json.gz")) else os.path.join(RAW, "cboe")


def list_snapshots(symbol=None, raw_dir=None):
    d = raw_dir or chains_dir()
    pat = os.path.join(d, symbol or "*", "*.json.gz")
    return sorted(glob.glob(pat))


def read_snapshot(path):
    """One recorded chain -> (underlying dict, DataFrame of options with expiry, strike, call, bid, ask, iv, greeks)."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        j = json.load(f)
    d = j["data"]
    rows = []
    for o in d.get("options", []):
        root, exp, call, k = parse_occ(o["option"])
        if exp is None:
            continue
        rows.append({"expiry": exp, "strike": k, "call": call, "bid": o.get("bid", 0.0), "ask": o.get("ask", 0.0),
                     "bid_size": o.get("bid_size", 0.0), "ask_size": o.get("ask_size", 0.0), "vendor_iv": o.get("iv", np.nan),
                     "vendor_delta": o.get("delta", np.nan), "open_interest": o.get("open_interest", 0.0), "volume": o.get("volume", 0.0),
                     "last": o.get("last_trade_price", np.nan), "last_time": o.get("last_trade_time")})
    opts = pd.DataFrame(rows)
    rec = pd.Timestamp(j.get("recorded_ny", "")[:19]) if j.get("recorded_ny") else None
    und = {"symbol": d.get("symbol"), "spot": d.get("current_price"), "bid": d.get("bid"), "ask": d.get("ask"), "close": d.get("close"),
           "prev_close": d.get("prev_day_close"), "iv30": d.get("iv30"), "last_trade_time": d.get("last_trade_time"),
           "recorded": rec, "snapshot": os.path.basename(path), "path": path}
    return und, opts


def closing_snapshot(symbol, date=None, raw_dir=None):
    """The last snapshot of the day (the one nearest the close), or of the given date."""
    files = list_snapshots(symbol, raw_dir)
    if date:
        files = [f for f in files if os.path.basename(f).startswith(pd.Timestamp(date).strftime("%Y-%m-%d"))]
    return files[-1] if files else None


def snapshot_days(symbol, raw_dir=None):
    return sorted({os.path.basename(f)[:10] for f in list_snapshots(symbol, raw_dir)})


# ---- DuckDB store -------------------------------------------------------------------------------------------------------------
def store(path=None):
    """A DuckDB connection with views over the reference tables and the derived parquet files."""
    import duckdb
    con = duckdb.connect(path or ":memory:")

    def q(p):                                                  # a path literal, apostrophes escaped
        return p.replace(os.sep, "/").replace("'", "''")
    for name, f in (("prices", "prices.parquet"), ("mpt", "mpt_histdata.parquet")):
        p = os.path.join(REF, f)
        if os.path.exists(p):
            con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{q(p)}')")
    for name, f in (("vol_indices", "vol_indices.csv"), ("cmt", "treasury_cmt.csv"), ("fomc", "fomc_dates.csv"), ("auctions", "auctions.csv")):
        p = os.path.join(REF, f)
        if os.path.exists(p):
            con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_csv_auto('{q(p)}')")
    for p in glob.glob(os.path.join(DERIVED, "*.parquet")):
        name = os.path.splitext(os.path.basename(p))[0]
        con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{q(p)}')")
    return con
