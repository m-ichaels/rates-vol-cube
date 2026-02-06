#!/usr/bin/env python3
"""report.pdf from results/run.json and results/figures.   python scripts/report.py"""
import json
import os

import pandas as pd
from fpdf import FPDF

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(ROOT, "results", "figures")
R = json.load(open(os.path.join(ROOT, "results", "run.json")))


def clean(s):
    return str(s).encode("latin-1", "replace").decode("latin-1")


class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 6, "rates-vol-rv: the basis-point vol cube, event variance and the taking side of rates volatility", align="R")
        self.ln(8)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 8, f"{self.page_no()}", align="C")

    def heading(self, t, size=13):
        self.set_font("Helvetica", "B", size)
        self.multi_cell(0, 7, clean(t))
        self.ln(1)

    def para(self, t):
        self.set_font("Helvetica", "", 9.5)
        self.multi_cell(0, 4.8, clean(t))
        self.ln(2)

    def fig(self, name, caption, w=185):
        p = os.path.join(FIG, name)
        if os.path.exists(p):
            if self.get_y() > 200:
                self.add_page()
            self.image(p, w=w)
            self.set_font("Helvetica", "I", 8.5)
            self.multi_cell(0, 4.2, clean(caption))
            self.ln(3)

    def tab(self, df, cols, widths, fmt="{:.2f}", size=7.5):
        self.set_font("Helvetica", "B", size)
        for c, w in zip(cols, widths):
            self.cell(w, 5, clean(c)[:22], border="B")
        self.ln()
        self.set_font("Helvetica", "", size)
        for i, r in df.iterrows():
            self.cell(widths[0], 4.6, clean(i)[:34])
            for c, w in zip(cols[1:], widths[1:]):
                v = r[c]
                self.cell(w, 4.6, clean(fmt.format(v) if isinstance(v, float) else v)[:18])
            self.ln()
        self.ln(3)


pdf = PDF()
pdf.set_auto_page_break(auto=True, margin=15)
pdf.add_page()
pdf.heading("Rates volatility on the taking side: the bp-vol cube from listed fixed-income options, event variance, and what relative value survives measured costs", 14)
c = R.get("cube", {})
f = c.get("funds", {})
tlt = f.get("TLT", {})
s = pd.DataFrame(R["vrp"]["summary"]).set_index("index")
ev = pd.DataFrame(R["event_history"]["VXTLT"]["by_event"]).set_index("kind")
st = pd.DataFrame(R["strategies"]["strategies"]).set_index("strategy")
es = pd.DataFrame(R["strategies"]["event_strategies"]).set_index("strategy")
mult = R.get("event_day_multiple", {})
pdf.para(f"Question.  A rates vol desk quotes in basis-point vol by expiry and tenor, prices scheduled events separately from the diffusive day, and takes positions in the premium between implied and realised.  This project builds that toolkit on free data: the closing chains of the listed Treasury and credit ETF options recorded daily from Cboe (the desk's OPRA feed is not free), Cboe's index histories of TLT, 10y-note-futures and swaption implied vol (2004-2026), the ICE BofA MOVE index, the Treasury curve, and the SOFR-option-implied FOMC distributions the Atlanta Fed publishes.")
pdf.para(f"Answer.  (1) On {c.get('chain_date', '')} the TLT chain gives a one-month ATM normal vol of {tlt.get('atm_bpvol_1m', float('nan')):.0f} bp against MOVE {c.get('move_latest', float('nan')):.0f}; the normal-SABR fit of {tlt.get('n_quotes', 0)} quotes sits inside the market on {100 * tlt.get('inside_market', 0):.0f}% of them with a median error of {tlt.get('rmse_bpvol_median', float('nan')):.1f} bp vol.  (2) The expiry ladder prices the next FOMC at {mult.get('FOMC', float('nan')):.2f} and a payroll release at {mult.get('NFP', float('nan')):.2f} times a diffusive day.  (3) Over 22 years the realised move on a payroll day has been {ev.loc['NFP', 'ratio_vs_normal']:.2f} [{ev.loc['NFP', 'ratio_lo']:.2f}, {ev.loc['NFP', 'ratio_hi']:.2f}] times the index-implied move, an FOMC {ev.loc['FOMC', 'ratio_vs_normal']:.2f} [{ev.loc['FOMC', 'ratio_lo']:.2f}, {ev.loc['FOMC', 'ratio_hi']:.2f}], an ordinary day {ev.loc['none', 'ratio_vs_normal']:.2f} [{ev.loc['none', 'ratio_lo']:.2f}, {ev.loc['none', 'ratio_hi']:.2f}]: the premium is in the ordinary days, the payroll day is under-priced by the index but not by the event straddle once the ladder's multiple is applied.  (4) The variance risk premium is {s.loc['VXTLT', 'vrp_mean']:.2f} vol points [{s.loc['VXTLT', 'vrp_lo']:.2f}, {s.loc['VXTLT', 'vrp_hi']:.2f}] on TLT, {s.loc['TYVIX', 'vrp_mean']:.2f} [{s.loc['TYVIX', 'vrp_lo']:.2f}, {s.loc['TYVIX', 'vrp_hi']:.2f}] on the 10y future and {s.loc['SRVIX', 'vrp_mean']:.1f} bp [{s.loc['SRVIX', 'vrp_lo']:.1f}, {s.loc['SRVIX', 'vrp_hi']:.1f}] on 1y10y swaptions; implied vol adds to a HAR forecast of realised on every instrument.  (5) Short one-month vega on TLT, rolled monthly and net of the chain's measured costs, makes {st.iloc[0]['mean_net']:.2f} vol points per unit vega per month [{st.iloc[0]['net_lo']:.2f}, {st.iloc[0]['net_hi']:.2f}], Sharpe {st.iloc[0]['sharpe_net']:.2f}, with a {st.iloc[0]['max_drawdown']:.0f}-point drawdown in March 2020; the forecast signal adds nothing to always-short on TLT and everything on the 10y future ({st.loc[[i for i in st.index if i.startswith('TYVIX short vega when E[premium]>0') and 'costs' not in i][0], 'mean_net']:.2f} vs {st.loc['TYVIX always short vega', 'mean_net']:.2f}).  The tenor trade and the FOMC straddle are not tradable at this size; the payroll straddle looks tradable off the index and is not off the chain.")
pdf.fig("cube.png", "Figure 1.  Left: ATM basis-point vol by fund and expiry from the recorded chains, with MOVE.  Right: TLT smiles in yield space, normal SABR per expiry.")
pdf.fig("smile_fit.png", "Figure 2.  The one-month TLT slice: bid-ask in bp vol, mids and the normal-SABR fit.", w=120)
pdf.fig("events.png", "Figure 3.  Left: implied one-day move of each scheduled event from the TLT expiry ladder (NNLS on total variance); faded bars share an expiry interval with another event and are not identified.  Right: realised over index-implied one-day move by event type, 2004-2026, with bootstrap intervals.")
pdf.fig("vrp.png", "Figure 4.  Implied vol against the realised vol of the following 21 sessions for the four indices; the premium and its block-bootstrap interval in each title.")
pdf.fig("strategies.png", "Figure 5.  Cumulative net P&L of the vega strategies (left, vol points per unit vega) and the event straddles priced off the index (right).")
pdf.fig("taking_cost.png", "Figure 6.  TLT: half-spread in bp vol by tenor and strike bucket - what a taker pays to cross.", w=120)
pdf.fig("density.png", "Figure 7.  Left: tail probabilities of the 20y yield from the TLT smiles against the Gaussian at ATM vol.  Right: the SOFR-option-implied policy-rate distribution (Atlanta Fed MPT).")
pdf.add_page()
pdf.heading("Strategies net of measured costs", 12)
pdf.tab(st, ["strategy", "rolls", "mean_gross", "mean_cost", "mean_net", "net_lo", "net_hi", "sharpe_net", "max_drawdown"], [66, 12, 17, 16, 16, 14, 14, 16, 18])
pdf.heading("Event straddles", 12)
pdf.tab(es, ["strategy", "rolls", "mean_net", "net_lo", "net_hi", "always_short_net_mean", "always_short_net_lo", "always_short_net_hi", "always_long_net_mean"], [70, 12, 14, 14, 14, 16, 16, 16, 16])
pdf.heading("Variance risk premium and forecasts", 12)
pdf.tab(s, ["index", "from", "implied_mean", "realised_mean", "vrp_mean", "vrp_lo", "vrp_hi", "months_realised_above"], [18, 22, 20, 20, 16, 14, 14, 24])
fc = pd.DataFrame(R["vrp"]["forecast"]).set_index("index")
pdf.tab(fc, ["index", "n_oos", "r2_har", "r2_har_iv", "r2_iv_only", "r2_trailing22", "bias_iv_volpts"], [18, 14, 16, 16, 16, 18, 18], fmt="{:.3f}")
pdf.heading("Validation and limits", 12)
pdf.para("Bachelier and Black solvers round-trip to 1e-10; the normal-SABR formula reproduces a flat smile at nu = 0 and the ATM vol at K = F; the Breeden-Litzenberger density integrates to one and its variance matches the ATM vol on a flat smile; the event extraction recovers a synthetic ladder with a known jump; the empirical durations agree with the sponsors' stated durations (TLT, IEF, SHY within 10%).  Every strategy is walk-forward; the P&L of a delta-hedged one-month option is the variance-swap approximation vega x (realised - implied), not a replay of option prices, and the costs are today's spreads applied to the whole history.  The event-day multiple is measured on the recorded chains and grows with each day the recorder runs; the historical event tables price the straddle off a 30-day index, which the multiple corrects.  MOVE and SRVIX are compared with the realised bp vol of the 10y CMT, an approximation to the baskets they measure.  The listed-ETF chains are American; OTM quotes are treated as European.  CME futures options, swaption and cap vol histories are not free; the cube, the extraction and the RV code apply unchanged to them.")
pdf.output(os.path.join(ROOT, "report.pdf"))
print("report.pdf")
