# Results summary

Run 2026-09-18T09:05.  Every number below is reproduced by `python -m ratesvol run`.

## The bp-vol cube, chains of 2026-09-18

66 expiry slices, 1436 two-sided OTM quotes.  MOVE 76.2 on 2026-09-17; VXTLT 11.96.  ATM normal vol in bp per year from the fund's price vol through its empirical duration; skew = bp vol 50 bp above the forward yield minus 50 bp below (positive = payers rich).

| fund | label | duration | n_expiries | n_quotes | atm_bpvol_1m | atm_bpvol_3m | atm_bpvol_6m | atm_lnvol_1m | skew_50bp_1m | rmse_bpvol_median | inside_market | atm_halfspread_vol_1m | vendor_iv30 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AGG | US aggregate | 5.09 | 3 | 21 | 93.64 | 95.68 | 100.74 | 0.05 | 10.36 | 30.82 | 1.00 | 0.53 | 4.16 |
| HYG | HY credit | 2.86 | 7 | 49 | 128.45 | 113.98 | 163.94 | 0.04 | 182.86 | 208.99 | 0.96 | 1.16 | 3.79 |
| IEF | 7-10y Treasury | 6.97 | 12 | 288 | 82.71 | 91.07 | 88.70 | 0.06 | -5.41 | 7.79 | 0.63 | 0.11 | 5.73 |
| IEI | 3-7y Treasury | 3.97 | 2 | 30 | 108.12 | 108.12 | 105.11 | 0.04 | 9.07 | 5.02 | 1.00 | 0.36 | 3.87 |
| LQD | IG credit | 7.23 | 12 | 168 | 88.47 | 90.64 | 96.31 | 0.06 | 24.42 | 11.03 | 1.00 | 3.70 | 5.95 |
| SHY | 1-3y Treasury | 1.66 | 2 | 13 | 153.75 | 153.75 | 153.75 | 0.03 | -13.48 | 9.11 | 1.00 | 0.42 | 2.39 |
| TLH | 10-20y Treasury | 12.19 | 2 | 14 | 89.89 | 89.89 | 82.77 | 0.11 | 2.69 | 6.95 | 1.00 | 7.96 | 10.70 |
| TLT | 20+y Treasury | 14.45 | 26 | 853 | 73.53 | 78.68 | 78.32 | 0.11 | 0.38 | 4.71 | 0.38 | 0.08 | 10.51 |

Event-day multiple (event-day implied move / diffusive-day implied move, TLT, identified events only): FOMC 1.75x, NFP 1.67x.

### Event variance from the expiry ladder

| symbol | date | type | J_bp | days | identified | diffusive_bpvol | fit_resid_bpvol |
|---|---|---|---|---|---|---|---|
| IEF | 2026-10-02 00:00:00 | NFP | 4.16 | 13 | True | 82.02 | 1.26 |
| IEF | 2026-10-28 00:00:00 | FOMC | 7.52 | 39 | True | 82.02 | 1.26 |
| IEF | 2026-11-06 00:00:00 | NFP | 8.92 | 48 | True | 82.02 | 1.26 |
| IEF | 2026-12-04 00:00:00 | NFP | 15.54 | 76 | False | 82.02 | 1.26 |
| IEF | 2026-12-09 00:00:00 | FOMC | 0.00 | 81 | False | 82.02 | 1.26 |
| IEF | 2027-01-08 00:00:00 | NFP | 4.24 | 111 | True | 82.02 | 1.26 |
| TLT | 2026-10-02 00:00:00 | NFP | 5.90 | 13 | True | 70.19 | 2.49 |
| TLT | 2026-10-28 00:00:00 | FOMC | 6.34 | 39 | True | 70.19 | 2.49 |
| TLT | 2026-11-06 00:00:00 | NFP | 8.99 | 48 | True | 70.19 | 2.49 |
| TLT | 2026-12-04 00:00:00 | NFP | 12.88 | 76 | False | 70.19 | 2.49 |
| TLT | 2026-12-09 00:00:00 | FOMC | 0.00 | 81 | False | 70.19 | 2.49 |
| TLT | 2027-01-08 00:00:00 | NFP | 4.26 | 111 | True | 70.19 | 2.49 |

## Scheduled events, 2004-2026: realised over implied one-day move

Implied one-day move = index / sqrt(252) (VXTLT on TLT, TYVIX on the 10y note future), in bp through the empirical duration.  Ratio normalised so that a Gaussian day is 1; bootstrap 95% intervals.

**VXTLT** (2004-01-02 .. 2026-09-16, 5700 days)

| kind | n | implied_bp | realised_bp | ratio_vs_normal | ratio_lo | ratio_hi | frac_beyond_1sigma | iv_change_next |
|---|---|---|---|---|---|---|---|---|
| AUCTION | 461.00 | 5.89 | 4.50 | 0.95 | 0.88 | 1.02 | 0.28 | -0.06 |
| FOMC | 181.00 | 5.93 | 4.70 | 0.99 | 0.88 | 1.09 | 0.34 | -0.35 |
| NFP | 259.00 | 5.98 | 5.80 | 1.23 | 1.12 | 1.33 | 0.42 | -0.28 |
| none | 4799.00 | 5.88 | 4.21 | 0.89 | 0.87 | 0.91 | 0.25 | 0.03 |

**TYVIX** (2004-01-02 .. 2023-07-13, 4375 days)

| kind | n | implied_bp | realised_bp | ratio_vs_normal | ratio_lo | ratio_hi | frac_beyond_1sigma | iv_change_next |
|---|---|---|---|---|---|---|---|---|
| AUCTION | 369.00 | 5.94 | 4.37 | 0.93 | 0.86 | 1.02 | 0.25 | 0.00 |
| FOMC | 137.00 | 6.22 | 5.72 | 1.13 | 0.98 | 1.30 | 0.35 | -0.18 |
| NFP | 198.00 | 6.20 | 6.65 | 1.35 | 1.21 | 1.49 | 0.46 | -0.16 |
| none | 3671.00 | 6.14 | 4.48 | 0.92 | 0.89 | 0.95 | 0.25 | 0.01 |

SOFR-option-implied FOMC distribution (Atlanta Fed tracker, 13 quarterly meetings since 2023): modal outcome right 100% of the time, Brier 0.041; the implied 25-75 range the day before an FOMC correlates 0.06 with the realised 20y move on the day (n = 28) and -0.05 with VXTLT's implied move.

## The variance risk premium in rates

Implied minus realised vol over the next 21 sessions, daily; block-bootstrap 95% interval (21-day blocks).  VXTLT and TYVIX in vol points (and bp through the duration), MOVE and SRVIX in bp against the realised bp vol of the 10y CMT.

| index | from | to | implied_mean | realised_mean | vrp_mean | vrp_lo | vrp_hi | vrp_bp_mean | months_realised_above | corr_iv_fwd |
|---|---|---|---|---|---|---|---|---|---|---|
| VXTLT | 2004-01-02 | 2026-08-18 | 14.70 | 13.32 | 1.38 | 0.98 | 1.75 | 8.55 | 0.24 | 0.70 |
| TYVIX | 2004-01-02 | 2023-07-14 | 5.85 | 5.55 | 0.29 | 0.07 | 0.51 | 5.04 | 0.28 | 0.66 |
| MOVE | 2004-01-02 | 2026-08-18 | 85.52 | 83.61 | 1.91 | -0.22 | 3.96 | 1.91 | 0.43 | 0.76 |
| SRVIX | 2012-06-18 | 2022-02-11 | 79.79 | 67.78 | 12.01 | 8.36 | 15.14 | 12.01 | 0.21 | 0.27 |

### Does implied vol forecast realised?  Out-of-sample R^2 of log realised vol, walk-forward

| index | n_oos | from | r2_har | r2_har_iv | r2_iv_only | r2_trailing22 | mae_har_volpts | mae_har_iv_volpts | bias_iv_volpts |
|---|---|---|---|---|---|---|---|---|---|
| VXTLT | 4888 | 2007-01-31 | 0.342 | 0.430 | 0.357 | 0.270 | 2.999 | 2.802 | 1.450 |
| TYVIX | 3531 | 2009-03-09 | 0.345 | 0.437 | 0.179 | 0.218 | 1.252 | 1.145 | 0.265 |
| MOVE | 4468 | 2007-02-02 | 0.420 | 0.568 | 0.581 | 0.374 | 19.422 | 16.558 | 1.093 |
| SRVIX | 1445 | 2015-07-22 | 0.026 | 0.016 | -0.316 | -0.267 | 14.756 | 14.575 | 9.608 |

### Premium by year (vol points; MOVE and SRVIX in bp)

| index | 2004 | 2005 | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| VXTLT | 0.7 | 0.9 | 1.3 | 0.2 | 1.3 | 2.0 | -0.4 | 0.1 | 2.5 | 1.0 | 0.8 | 0.6 | 1.5 | 1.7 | 1.4 | 0.1 | 1.3 | 2.8 | 2.5 | 1.4 | 2.1 | 4.1 | 2.6 |
| TYVIX | 1.1 | nan | 0.8 | 0.5 | 0.0 | 0.8 | 0.5 | 1.3 | 0.9 | 0.4 | 0.8 | 0.4 | 0.9 | 1.0 | 0.5 | -0.0 | 1.0 | 0.5 | -3.2 | -3.4 | nan | nan | nan |
| MOVE | 13.8 | 7.1 | 5.7 | 2.7 | 17.8 | 3.2 | -9.3 | -5.5 | -0.1 | -3.2 | 0.1 | -2.8 | 3.6 | 2.5 | -1.7 | -4.1 | -15.0 | -5.5 | -4.0 | 6.8 | 14.3 | 14.3 | 3.9 |
| SRVIX | nan | nan | nan | nan | nan | nan | nan | nan | 23.9 | 18.1 | 21.0 | 4.4 | 15.5 | 23.6 | 15.9 | 1.2 | -7.2 | 11.9 | -10.2 | nan | nan | nan | nan |

## Strategies on the taking side, net of measured costs

Costs from the TLT chain: ATM half-spread 0.091 vol points, fund half-spread 0.61 bp of price; a delta-hedged one-month straddle pays 0.26 vol points per unit vega round trip (0.08 of it hedging).  ZN options assumed at 0.10 (0.4x TLT; the x2 / x4 rows are the sensitivity).  P&L = vega x (realised - implied) per monthly roll, vol points per unit vega; block-bootstrap intervals; Sharpe annualised from monthly rolls.

| strategy | rolls | from | active_share | mean_gross | mean_cost | mean_net | net_lo | net_hi | sharpe_net | hit_rate | max_drawdown | worst_roll |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| VXTLT short vega when E[premium]>0 | 223 | 2008-01-02 | 0.96 | 1.40 | 0.25 | 1.15 | 0.56 | 1.68 | 0.87 | 0.67 | 49.07 | -39.59 |
| VXTLT always short vega | 223 | 2008-01-02 | 1.00 | 1.47 | 0.26 | 1.21 | 0.61 | 1.77 | 0.90 | 0.70 | 49.07 | -39.59 |
| VXTLT short vega when E[premium]>0, costs x2 | 223 | 2008-01-02 | 0.96 | 1.40 | 0.50 | 0.91 | 0.32 | 1.43 | 0.68 | 0.63 | 52.59 | -39.85 |
| VXTLT short vega when E[premium]>0, costs x4 | 223 | 2008-01-02 | 0.96 | 1.40 | 1.00 | 0.41 | -0.18 | 0.93 | 0.31 | 0.57 | 61.56 | -40.37 |
| TYVIX short vega when E[premium]>0 | 186 | 2008-01-02 | 0.78 | 0.53 | 0.08 | 0.45 | 0.26 | 0.67 | 1.10 | 0.57 | 10.94 | -7.91 |
| TYVIX always short vega | 186 | 2008-01-02 | 1.00 | 0.26 | 0.10 | 0.16 | -0.19 | 0.52 | 0.26 | 0.66 | 64.26 | -9.05 |
| TYVIX short vega when E[premium]>0, costs x2 | 186 | 2008-01-02 | 0.78 | 0.53 | 0.16 | 0.37 | 0.18 | 0.58 | 0.91 | 0.55 | 12.09 | -8.01 |
| TYVIX short vega when E[premium]>0, costs x4 | 186 | 2008-01-02 | 0.78 | 0.53 | 0.33 | 0.21 | 0.02 | 0.41 | 0.51 | 0.52 | 14.74 | -8.22 |
| tenor RV: TLT vs ZN bp vol, |z|>1 | 197 | 2007-01-29 | 0.40 | 0.53 | 0.14 | 0.39 | -0.00 | 0.87 | 0.48 | 0.21 | 21.52 | -5.78 |

Threshold sweep, TLT (short when the HAR+IV expected premium exceeds the threshold):

| threshold | active_share | mean_net | net_lo | net_hi | sharpe_net | hit_rate | max_drawdown |
|---|---|---|---|---|---|---|---|
| -1.0 | 0.99 | 1.15 | 0.56 | 1.68 | 0.87 | 0.69 | 49.07 |
| 0.0 | 0.96 | 1.15 | 0.56 | 1.68 | 0.87 | 0.67 | 49.07 |
| 0.5 | 0.87 | 1.25 | 0.69 | 1.76 | 0.97 | 0.63 | 48.03 |
| 1.0 | 0.65 | 0.97 | 0.43 | 1.41 | 0.79 | 0.48 | 45.69 |
| 1.5 | 0.45 | 0.80 | 0.31 | 1.23 | 0.69 | 0.33 | 41.01 |
| 2.0 | 0.35 | 0.85 | 0.51 | 1.21 | 1.12 | 0.26 | 8.76 |

Tenor RV: the z-score of log(TLT bp vol / ZN bp vol) predicts the next-month change in the ratio with slope -0.037 [-0.047, -0.027] per unit z (corr -0.35, n = 4097): the ratio mean-reverts, but the P&L table shows what that is worth after costs.

### Event straddles

One-day straddle priced off the index-implied move (VXTLT / sqrt(252)), payoff |realised move|, bp of yield per unit implied move; cost 1.3% of the premium (the TLT ATM half-spread over a one-day straddle).  The second row of each event re-prices the straddle at the event-day multiple the chain's expiry ladder implies today - the index-implied number is not what the event straddle costs.

| strategy | rolls | mean_net | net_lo | net_hi | hit_rate | always_short_net_mean | always_short_net_lo | always_short_net_hi | always_long_net_mean | always_long_net_lo | always_long_net_hi |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FOMC straddle, signal = trailing 8 events, index-implied move | 157.00 | -0.54 | -1.10 | 0.08 | 0.43 | -0.04 | -0.70 | 0.55 | -0.09 | -0.68 | 0.57 |
| FOMC straddle, event-day implied x1.75 from the chain | 157.00 | 3.52 | 2.91 | 4.11 | 0.85 | 3.52 | 2.90 | 4.10 | -3.74 | -4.34 | -3.12 |
| NFP straddle, signal = trailing 8 events, index-implied move | 229.00 | 0.32 | -0.20 | 0.86 | 0.50 | -0.90 | -1.47 | -0.36 | 0.77 | 0.23 | 1.34 |
| NFP straddle, event-day implied x1.67 from the chain | 229.00 | 1.88 | 1.15 | 2.54 | 0.70 | 2.28 | 1.70 | 2.86 | -2.50 | -3.08 | -1.91 |

### Cross-market bases

|  | index | n | mean_basis_bp | slope_on_change | corr | from | to | mean_ratio | corr_with_MOVE_premium |
|---|---|---|---|---|---|---|---|---|---|
| 0 | SRVIX-TYVIX bp | 2135 | -4.225 | -6.308 | -0.457 | 2012-06-18 | 2022-02-11 | nan | nan |
| 1 | log MOVE/VIX | 5627 | nan | -0.053 | -0.315 | 2002-11-12 | 2026-09-17 | 4.594 | 0.087 |

## Empirical durations

| symbol | benchmark | empirical_duration | se | r2 | resid_bp_day | stated_duration | asof |
|---|---|---|---|---|---|---|---|
| SHY | 2Yr | 1.66 | 0.05 | 0.82 | 2.10 | 1.82 | 2026-09-17 |
| IEI | 5Yr | 3.97 | 0.07 | 0.94 | 1.18 | 4.23 | 2026-09-17 |
| IEF | 10Yr | 6.97 | 0.11 | 0.94 | 1.04 | 6.90 | 2026-09-17 |
| TLH | 20Yr | 12.19 | 0.19 | 0.94 | 0.95 | 11.66 | 2026-09-17 |
| TLT | 20Yr | 14.45 | 0.28 | 0.92 | 1.16 | 14.99 | 2026-09-17 |
| AGG | 7Yr | 5.09 | 0.12 | 0.89 | 1.57 | 5.75 | 2026-09-17 |
| LQD | 10Yr | 7.23 | 0.24 | 0.79 | 2.13 | 7.70 | 2026-09-17 |
| HYG | 5Yr | 2.86 | 0.28 | 0.30 | 6.91 | 3.10 | 2026-09-17 |
| ZF=F | 5Yr | 3.65 | 0.08 | 0.90 | 1.50 | nan | 2026-09-17 |
| ZN=F | 10Yr | 5.87 | 0.15 | 0.86 | 1.65 | nan | 2026-09-17 |
| ZB=F | 30Yr | 12.18 | 0.33 | 0.85 | 1.51 | nan | 2026-09-17 |
