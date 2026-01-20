#!/usr/bin/env python3
"""Free data for the rates-vol project.   python tools/download.py [all|prices|indices|cmt|fomc|auctions|mpt|ishares]

  prices    Yahoo daily bars: TLT IEF SHY IEI TLH AGG HYG LQD TBT SPY, ZN=F ZF=F ZB=F, ^VIX ^MOVE ^TNX   -> data/reference/prices.parquet
  indices   Cboe daily histories: VXTLT (TLT 30-day implied vol, 2004-), TYVIX (10y note futures vol, 2003-2023),
            SRVIX (swaption vol, 2012-2022); MOVE and VIX from Yahoo                                       -> data/reference/vol_indices.csv
  cmt       Treasury daily par yield curve, 2002-                                                          -> data/reference/treasury_cmt.csv
  fomc      FOMC meeting dates 2004- (statement day = last day of the meeting; unscheduled flagged)       -> data/reference/fomc_dates.csv
  auctions  TreasuryDirect note and bond auctions, 2004-                                                   -> data/reference/auctions.csv
  mpt       Atlanta Fed Market Probability Tracker (SOFR-option-implied FOMC distributions, 2023-)        -> data/reference/mpt_histdata.parquet
  ishares   stated effective duration of each fund today                                                   -> data/reference/fund_duration.csv

Every source is public and needs no key.  Files are rewritten in full (they are small); the recorder in
tools/record.py is the incremental one.
"""
import datetime as dt
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(ROOT, "data", "reference")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
      "Accept": "*/*", "Accept-Language": "en-GB,en;q=0.9"}

ETFS = ["TLT", "IEF", "SHY", "IEI", "TLH", "AGG", "HYG", "LQD", "TBT", "SPY"]
FUTURES = ["ZN=F", "ZF=F", "ZB=F"]
YAHOO_INDICES = ["^VIX", "^MOVE", "^TNX"]


def get(url, retries=4, timeout=90, binary=False):
    for k in range(retries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)
            b = r.read()
            return b if binary else b.decode("utf-8", "ignore")
        except Exception as e:                                   # noqa: BLE001
            if k == retries - 1:
                print(f"   {url[:90]} {e}", flush=True)
                return None
            time.sleep(2 * (k + 1))


# ---- Yahoo daily bars (chunked by two years so the response stays daily) -------------------------------------------
def yahoo_daily(symbol, start=dt.date(2002, 1, 1)):
    frames = []
    a = start
    while a < dt.date.today():
        b = min(a + dt.timedelta(days=730), dt.date.today() + dt.timedelta(days=1))
        p1, p2 = int(time.mktime(a.timetuple())), int(time.mktime(b.timetuple()))
        u = f"https://query2.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?period1={p1}&period2={p2}&interval=1d&events=div"
        t = get(u)
        if t:
            try:
                r = json.loads(t)["chart"]["result"][0]
                q = r["indicators"]["quote"][0]
                adj = r["indicators"].get("adjclose", [{}])[0].get("adjclose", [None] * len(r["timestamp"]))
                f = pd.DataFrame({"date": pd.to_datetime(r["timestamp"], unit="s").tz_localize("UTC").tz_convert("America/New_York").date,
                                  "open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"], "adjclose": adj, "volume": q["volume"]})
                f["symbol"] = symbol
                frames.append(f.dropna(subset=["close"]))
            except (KeyError, IndexError, TypeError):
                pass
        a = b
        time.sleep(0.3)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames).drop_duplicates("date").sort_values("date")
    out["date"] = pd.to_datetime(out["date"])
    return out


def prices():
    frames = []
    for s in ETFS + FUTURES + YAHOO_INDICES:
        f = yahoo_daily(s)
        print(f"  {s}: {len(f)} days {f['date'].min().date() if len(f) else ''} .. {f['date'].max().date() if len(f) else ''}", flush=True)
        frames.append(f)
    out = pd.concat(frames)
    out.to_parquet(os.path.join(REF, "prices.parquet"), index=False)


# ---- Cboe volatility index histories -------------------------------------------------------------------------------
def indices():
    rows = []
    for name in ("VXTLT", "TYVIX", "SRVIX"):
        t = get(f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{name}_History.csv")
        if not t:
            continue
        d = pd.read_csv(io.StringIO(t))
        col = "CLOSE" if "CLOSE" in d.columns else name
        d = d.rename(columns={"DATE": "date", col: "value"})[["date", "value"]]
        d["date"] = pd.to_datetime(d["date"])
        d["name"] = name
        rows.append(d)
        print(f"  {name}: {len(d)} days {d['date'].min().date()} .. {d['date'].max().date()}", flush=True)
    for s, name in (("^MOVE", "MOVE"), ("^VIX", "VIX")):
        f = yahoo_daily(s)
        d = f[["date", "close"]].rename(columns={"close": "value"})
        d["name"] = name
        rows.append(d)
        print(f"  {name}: {len(d)} days {d['date'].min().date()} .. {d['date'].max().date()}", flush=True)
    pd.concat(rows).dropna().to_csv(os.path.join(REF, "vol_indices.csv"), index=False)


# ---- Treasury par curve --------------------------------------------------------------------------------------------
def cmt():
    frames = []
    for y in range(2002, dt.date.today().year + 1):
        t = get(f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv")
        if not t:
            continue
        d = pd.read_csv(io.StringIO(t))
        d.columns = [c.strip() for c in d.columns]
        frames.append(d)
        print(f"  CMT {y}: {len(d)} days", flush=True)
        time.sleep(0.3)
    d = pd.concat(frames)
    d["Date"] = pd.to_datetime(d["Date"])
    keep = {"Date": "date", "1 Mo": "1Mo", "2 Mo": "2Mo", "3 Mo": "3Mo", "6 Mo": "6Mo", "1 Yr": "1Yr", "2 Yr": "2Yr", "3 Yr": "3Yr",
            "5 Yr": "5Yr", "7 Yr": "7Yr", "10 Yr": "10Yr", "20 Yr": "20Yr", "30 Yr": "30Yr"}
    d = d[[c for c in keep if c in d.columns]].rename(columns=keep).sort_values("date")
    d.to_csv(os.path.join(REF, "treasury_cmt.csv"), index=False)


# ---- FOMC meeting dates --------------------------------------------------------------------------------------------
MONTHS = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"])}
MONTHS_ABBR = {m[:3]: i for m, i in MONTHS.items()}


def _span_end(year, month_text, days):
    """The last day of a meeting: 'January', '26-27' -> Jan 27; 'Jan/Feb', '31-1' -> Feb 1."""
    months = [MONTHS_ABBR.get(x.strip()[:3].title()) for x in month_text.split("/")]
    nums = [int(x) for x in re.findall(r"\d+", days)]
    if not nums or not months or months[0] is None:
        raise ValueError(month_text + " " + days)
    month = months[-1] if (len(nums) > 1 and nums[-1] < nums[0] and len(months) > 1 and months[-1]) else months[0]
    return dt.date(year, month, nums[-1])


def fomc():
    rows = []
    for y in range(2004, 2021):
        h = get(f"https://www.federalreserve.gov/monetarypolicy/fomchistorical{y}.htm")
        if not h:
            continue
        for head in re.findall(r"<h5[^>]*>\s*([^<]+?)\s*</h5>", h):
            m = re.match(r"([A-Za-z/]+)\s+([\d\-]+)\s*(\([^)]*\))?\s*(Meeting|Conference Call|notation vote)?.*-\s*(\d{4})", head)
            if not m:
                continue
            month, days, note, kind, year = m.groups()
            note = (note or "").strip("()")
            scheduled = kind == "Meeting" and note not in ("unscheduled", "cancelled") and "notation" not in head
            if kind == "Conference Call" or "notation" in head or note == "cancelled":
                scheduled = False
            try:
                rows.append({"date": _span_end(int(year), month, days), "scheduled": scheduled, "note": note or kind or ""})
            except ValueError:
                pass
    h = get("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm")
    if h:
        year = None
        for chunk in re.split(r'(?=<div class="[^"]*fomc-meeting"[^>]*>)|(?=<h4)', h):
            ym = re.search(r"(\d{4}) FOMC Meetings", chunk[:300])
            if ym:
                year = int(ym.group(1))
                continue
            if year is None or not re.match(r'<div class="[^"]*fomc-meeting"', chunk):
                continue
            mm = re.search(r'fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>', chunk)
            dm = re.search(r'fomc-meeting__date[^>]*>([^<]+)<', chunk)
            if not mm or not dm:
                continue
            raw = dm.group(1)
            unsched = "unscheduled" in raw.lower() or "unscheduled" in chunk.lower()[:600]
            try:
                rows.append({"date": _span_end(year, mm.group(1), raw), "scheduled": not unsched, "note": "unscheduled" if unsched else "Meeting"})
            except ValueError:
                pass
    d = pd.DataFrame(rows)
    # two rows the page formats differently: the July 31 - August 1, 2012 meeting, and a non-meeting entry in August 2025
    d.loc[d["date"] == dt.date(2012, 7, 31), ["date", "scheduled", "note"]] = [dt.date(2012, 8, 1), True, "Meeting"]
    d = d[d["date"] != dt.date(2025, 8, 22)]
    d = d.drop_duplicates("date").sort_values("date")
    d.to_csv(os.path.join(REF, "fomc_dates.csv"), index=False)
    print(f"  FOMC: {len(d)} dates {d['date'].min()} .. {d['date'].max()} ({int(d['scheduled'].sum())} scheduled)", flush=True)


# ---- Treasury auctions ---------------------------------------------------------------------------------------------
def auctions():
    rows = []
    for typ in ("Note", "Bond"):
        for y in range(2004, dt.date.today().year + 1):
            t = get(f"https://www.treasurydirect.gov/TA_WS/securities/search?format=json&type={typ}&dateFieldName=auctionDate&startDate={y}-01-01&endDate={y}-12-31")
            if not t:
                continue
            for r in json.loads(t):
                rows.append({"auction_date": r["auctionDate"][:10], "type": typ, "term": r.get("securityTerm", ""), "cusip": r.get("cusip", ""),
                             "reopening": r.get("reopening", ""), "offering_amount": r.get("offeringAmount", "")})
            time.sleep(0.2)
    d = pd.DataFrame(rows).sort_values("auction_date")
    d.to_csv(os.path.join(REF, "auctions.csv"), index=False)
    print(f"  auctions: {len(d)} {d['auction_date'].min()} .. {d['auction_date'].max()}", flush=True)


# ---- Atlanta Fed Market Probability Tracker -------------------------------------------------------------------------
def mpt():
    b = get("https://www.atlantafed.org/-/media/Project/Atlanta/FRBA/Documents/cenfis/market-probability-tracker/mpt_histdata.xlsx", binary=True)
    if not b:
        return
    d = pd.read_excel(io.BytesIO(b), sheet_name="DATA")
    d.columns = [c.strip() for c in d.columns]
    d["date"] = pd.to_datetime(d["date"])
    d["reference_start"] = pd.to_datetime(d["reference_start"])
    d.to_parquet(os.path.join(REF, "mpt_histdata.parquet"), index=False)
    print(f"  MPT: {len(d)} rows, {d['date'].nunique()} dates {d['date'].min().date()} .. {d['date'].max().date()}", flush=True)


# ---- iShares stated durations -----------------------------------------------------------------------------------------
ISHARES = {"TLT": "239454/ishares-20-year-treasury-bond-etf", "IEF": "239456/ishares-7-10-year-treasury-bond-etf",
           "SHY": "239452/ishares-1-3-year-treasury-bond-etf", "IEI": "239455/ishares-3-7-year-treasury-bond-etf",
           "TLH": "239453/ishares-10-20-year-treasury-bond-etf", "AGG": "239458/ishares-core-total-us-bond-market-etf",
           "HYG": "239565/ishares-iboxx-high-yield-corporate-bond-etf", "LQD": "239566/ishares-iboxx-investment-grade-corporate-bond-etf"}


def ishares():
    rows = []
    for sym, path in ISHARES.items():
        h = get(f"https://www.ishares.com/us/products/{path}")
        dur = None
        if h:
            for pat in (r'"effectiveDuration"[^{}]*?"r":\s*([\d.]+)', r'Effective Duration[^0-9]{0,400}?([\d]+\.[\d]+)\s*(?:yrs|years|<)'):
                m = re.search(pat, h, re.S)
                if m:
                    dur = float(m.group(1))
                    break
        rows.append({"symbol": sym, "effective_duration": dur, "asof": dt.date.today().isoformat()})
        print(f"  {sym}: duration {dur}", flush=True)
        time.sleep(0.5)
    pd.DataFrame(rows).to_csv(os.path.join(REF, "fund_duration.csv"), index=False)


STEPS = {"prices": prices, "indices": indices, "cmt": cmt, "fomc": fomc, "auctions": auctions, "mpt": mpt, "ishares": ishares}

if __name__ == "__main__":
    os.makedirs(REF, exist_ok=True)
    which = sys.argv[1:] or ["all"]
    for name, fn in STEPS.items():
        if "all" in which or name in which:
            print(name, flush=True)
            fn()
