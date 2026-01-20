#!/usr/bin/env python3
"""Record the listed fixed-income option chains from Cboe's delayed-quote API.
   python tools/record.py [--symbols TLT,IEF,...] [--loop SECONDS] [--out data/raw/cboe]

Each call writes one gzip JSON snapshot per symbol, data/raw/cboe/<SYM>/<YYYY-MM-DD>T<HHMM>.json.gz, carrying the
underlying quote and every listed option (bid, ask, sizes, IV, Greeks, open interest, volume, last trade).  Quotes
are 15 minutes delayed; a snapshot at 16:05 New York is the closing chain.  The chain history that the desk would
buy (OPRA, or CME for the futures options) is not free; this recorder is how the project builds its own.  With
--loop it keeps recording every N seconds until 16:20 New York, then exits.
"""
import argparse
import datetime as dt
import gzip
import json
import os
import sys
import time
import urllib.request
import zoneinfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NY = zoneinfo.ZoneInfo("America/New_York")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36", "Accept": "application/json"}
DEFAULT = ["TLT", "IEF", "SHY", "IEI", "TLH", "AGG", "HYG", "LQD", "TBT", "SPY"]


def fetch(symbol, timeout=60):
    """The chain and the server's clock (the HTTP Date header): the recorder is timestamped by the server, not
    by the machine, so a wrong local clock cannot mislabel a snapshot."""
    u = f"https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
    for k in range(3):
        try:
            r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=timeout)
            server = r.headers.get("Date")
            now = dt.datetime.strptime(server, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=dt.timezone.utc).astimezone(NY) if server else dt.datetime.now(NY)
            return json.loads(r.read()), now
        except Exception as e:                                   # noqa: BLE001
            if k == 2:
                print(f"  {symbol}: {e}", file=sys.stderr, flush=True)
            time.sleep(3)
    return None, None


def server_now():
    """New York time from the server clock (falls back to the machine)."""
    try:
        r = urllib.request.urlopen(urllib.request.Request("https://cdn.cboe.com/api/global/delayed_quotes/options/TLT.json", headers=UA), timeout=30)
        return dt.datetime.strptime(r.headers["Date"], "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=dt.timezone.utc).astimezone(NY)
    except Exception:                                            # noqa: BLE001
        return dt.datetime.now(NY)


def snapshot(symbols, out):
    n = 0
    for s in symbols:
        j, now = fetch(s)
        if not j or "data" not in j:
            continue
        d = os.path.join(out, s)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, now.strftime("%Y-%m-%dT%H%M") + ".json.gz")
        j["recorded_ny"] = now.isoformat()
        with gzip.open(p, "wt", encoding="utf-8") as f:
            json.dump(j, f)
        n += 1
        print(f"  {s}: {len(j['data'].get('options', []))} options, spot {j['data'].get('current_price')} -> {os.path.relpath(p, ROOT)}", flush=True)
        time.sleep(0.5)
    return n


def archive(raw=None, chains=None):
    """Copy the closing snapshot of every recorded day (the last one at or after 16:00 New York, else the last of
    the day) to data/chains/<SYM>/<date>.json.gz, the tracked archive the pipeline reads."""
    import glob
    import shutil
    raw = raw or os.path.join(ROOT, "data", "raw", "cboe")
    chains = chains or os.path.join(ROOT, "data", "chains")
    n = 0
    for symdir in sorted(glob.glob(os.path.join(raw, "*"))):
        sym = os.path.basename(symdir)
        by_day = {}
        for f in sorted(glob.glob(os.path.join(symdir, "*.json.gz"))):
            by_day.setdefault(os.path.basename(f)[:10], []).append(f)
        for day, files in by_day.items():
            closing = [f for f in files if os.path.basename(f)[11:15] >= "1600"]
            src = (closing or files)[-1]
            now = server_now()
            if not closing and day == now.strftime("%Y-%m-%d") and now.time() < dt.time(16, 0):
                continue                                                   # today's close has not been recorded yet
            dst = os.path.join(chains, sym, day + ".json.gz")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst):
                shutil.copy2(src, dst)
                n += 1
    print(f"archived {n} closing chains -> {os.path.relpath(chains, ROOT)}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(DEFAULT))
    ap.add_argument("--loop", type=int, default=0, help="seconds between snapshots; 0 = one snapshot")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "raw", "cboe"))
    ap.add_argument("--archive", action="store_true", help="only archive the closing snapshots to data/chains")
    a = ap.parse_args()
    if a.archive:
        archive(a.out)
        sys.exit(0)
    syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    while True:
        print(server_now().strftime("%Y-%m-%d %H:%M New York"), flush=True)
        snapshot(syms, a.out)
        if not a.loop or server_now().time() > dt.time(16, 20):
            archive(a.out)
            break
        time.sleep(a.loop)
