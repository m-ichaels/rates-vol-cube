#!/usr/bin/env python3
"""notebooks/results.ipynb: the results walk-through, built from results/run.json so it never drifts from the run."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def md(s):
    return {"cell_type": "markdown", "metadata": {}, "source": s}


def code(s):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s}


cells = [
    md("# rates-vol-rv: results\n\nEverything here reads `results/run.json` and `data/derived/*.parquet` written by `python -m ratesvol run`; re-run the pipeline and re-execute to refresh."),
    code("import json, os, sys\nimport numpy as np, pandas as pd\nimport matplotlib.pyplot as plt\nsys.path.insert(0, os.path.abspath('..'))\nfrom ratesvol import data as D, cube as C, events as E, vrp as V, rv as R, density as Z\nR_ = json.load(open('../results/run.json'))\npd.set_option('display.width', 200); pd.set_option('display.max_columns', 40)"),
    md("## 1. The bp-vol cube\n\nATM normal vol by fund (the tenor axis) and expiry, from the recorded closing chains; MOVE for reference.  Skew is the bp vol 50 bp above the forward yield minus 50 bp below."),
    code("funds = pd.DataFrame(R_['cube']['funds']).T\nfunds[['label','duration','n_expiries','n_quotes','atm_bpvol_1m','atm_bpvol_3m','atm_bpvol_6m','skew_50bp_1m','rmse_bpvol_median','inside_market','atm_halfspread_vol_1m']]"),
    code("from IPython.display import Image, display\ndisplay(Image('../results/figures/cube.png')); display(Image('../results/figures/smile_fit.png'))"),
    md("## 2. Event variance\n\nLeft: the implied one-day move of each scheduled event from the TLT expiry ladder (NNLS on total variance).  Right: 22 years of realised over index-implied one-day moves by event type."),
    code("pd.DataFrame(R_.get('event_extraction', []))"),
    code("display(Image('../results/figures/events.png'))\nfor k, h in R_['event_history'].items():\n    print(k, h['from'], h['to']); display(pd.DataFrame(h['by_event']).set_index('kind').round(3))"),
    md("## 3. The variance risk premium and the forecast test"),
    code("display(pd.DataFrame(R_['vrp']['summary']).set_index('index').round(3))\ndisplay(pd.DataFrame(R_['vrp']['forecast']).set_index('index').round(3))\ndisplay(Image('../results/figures/vrp.png'))"),
    md("## 4. Strategies on the taking side, net of measured costs"),
    code("print(R_['strategies']['costs'])\ndisplay(pd.DataFrame(R_['strategies']['strategies']).set_index('strategy').round(3))\ndisplay(pd.DataFrame(R_['strategies']['event_strategies']).set_index('strategy').round(3))\ndisplay(Image('../results/figures/strategies.png'))"),
    md("## 5. Taking costs, densities and the policy distribution"),
    code("display(Image('../results/figures/taking_cost.png')); display(Image('../results/figures/density.png'))\nif 'mpt' in R_: print({k: v for k, v in R_['mpt'].items() if k != 'table'})"),
    md("## 6. SQL over the store\n\nThe DuckDB views cover the reference tables and every derived parquet."),
    code("con = D.store()\ncon.execute(\"SELECT symbol, tenor_bucket, money_bucket, n, halfspread_bpvol FROM taking_costs WHERE symbol='TLT' ORDER BY tenor_bucket, money_bucket\").df()"),
]
nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
for c in nb["cells"]:
    c["source"] = c["source"]
os.makedirs(os.path.join(ROOT, "notebooks"), exist_ok=True)
json.dump(nb, open(os.path.join(ROOT, "notebooks", "results.ipynb"), "w"), indent=1)
print("notebooks/results.ipynb")
