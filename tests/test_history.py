"""The history layer on the reference data: durations against the sponsors, the premium tables, the walk-forward
forecasts never see their target, the strategies' accounting identities."""
import os

import numpy as np
import pandas as pd
import pytest

from ratesvol import data as D
from ratesvol import duration as U
from ratesvol import rv as R
from ratesvol import vrp as V

HAVE = os.path.exists(os.path.join(D.REF, "prices.parquet")) and os.path.exists(os.path.join(D.REF, "vol_indices.csv"))
pytestmark = pytest.mark.skipif(not HAVE, reason="reference data not downloaded")


def test_empirical_duration_matches_stated():
    t = U.duration_table(("TLT", "IEF", "SHY"))
    for s in ("TLT", "IEF", "SHY"):
        row = t.loc[s]
        assert row["r2"] > 0.75
        if np.isfinite(row["stated_duration"]):
            assert abs(row["empirical_duration"] / row["stated_duration"] - 1) < 0.15


def test_event_calendar_shape():
    ev = D.event_calendar("2015-01-01", "2025-12-31")
    by = ev.groupby("type").size()
    assert 85 <= by["FOMC"] <= 90 and by["NFP"] == 132 and by["AUCTION10"] > 100


def test_premium_table_conventions():
    d = V.premium_table("VXTLT")
    assert (d["vrp"] == d["iv"] - d["rvol_fwd"]).all()
    assert d["rvol_fwd"].between(1, 80).all() and d["iv"].between(3, 80).all()
    # the forward realised at t uses returns t+1 .. t+21 only
    px = D.prices("TLT")["close"]
    r = np.log(px).diff()
    t = d.index[1000]
    i = px.index.get_loc(t)
    manual = 100 * np.sqrt(252 * (r.iloc[i + 1:i + 22] ** 2).mean())
    assert d.at[t, "rvol_fwd"] == pytest.approx(manual, rel=1e-9)


def test_har_forecast_is_walk_forward():
    d = V.premium_table("VXTLT").iloc[-2500:]
    f = V.har_forecast(d, window=750, use_iv=True)
    assert f.notna().sum() > 1000
    # perturbing the target after date t leaves the forecast at t unchanged
    d2 = d.copy()
    t = f.dropna().index[200]
    d2.loc[d2.index > t, "rvol_fwd"] *= 3
    f2 = V.har_forecast(d2, window=750, use_iv=True)
    assert f2.loc[:t].dropna().round(10).equals(f.loc[:t].dropna().round(10))


def test_strategy_accounting():
    a, b, _ = R.vrp_strategy("VXTLT", 0.3, start="2015-01-01")
    for p in (a, b):
        np.testing.assert_allclose(p["net"], p["gross"] - p["cost"])
        np.testing.assert_allclose(p["gross"], p["position"] * (p["rvol_fwd"] - p["iv"]))
    assert (b["position"] == -1).all() and set(a["position"].unique()) <= {-1.0, 0.0}
    s = R.summarise(a, "x")
    assert s["net_lo"] <= s["mean_net"] <= s["net_hi"]


def test_block_bootstrap_interval_contains_mean():
    x = np.random.default_rng(0).standard_normal(500) + 0.2
    m, lo, hi = V.block_bootstrap_mean(x, block=21)
    assert lo < m < hi and m == pytest.approx(x.mean())
