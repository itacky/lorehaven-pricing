#!/usr/bin/env bash
# Lorehaven pricing simulator - macOS/Linux launcher. Run: bash run_tool.sh   (Ctrl+C to stop)
# Creates a local .venv on first run (avoids "externally-managed-environment" errors) and installs Flask there.
set -e
cd "$(dirname "$0")"
PY=$(command -v python3 || command -v python || true)
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)'; then
  echo "Need Python 3.10-3.13. Install it from https://www.python.org and run this again."; exit 1
fi
if [ ! -x .venv/bin/python ]; then
  echo "First run: creating .venv and installing Flask (about 20 seconds)..."
  "$PY" -m venv .venv
  .venv/bin/python -m pip install --quiet -r requirements-tool.txt
fi
exec .venv/bin/python app/app.py
