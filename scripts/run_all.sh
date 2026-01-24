#!/usr/bin/env bash
# Full pipeline: data -> record today's chains -> archive the closes -> run -> figures -> summary -> report -> notebook.
# Usage: scripts/run_all.sh [--skip-download] [--skip-record]
set -euo pipefail
cd "$(dirname "$0")/.."
[[ " $* " == *" --skip-download "* ]] || python tools/download.py
[[ " $* " == *" --skip-record "* ]] || python tools/record.py
python tools/record.py --archive
python -m ratesvol run
python scripts/plots.py
python scripts/summarize.py
python scripts/report.py
python scripts/make_notebook.py
python -m pytest
echo done
