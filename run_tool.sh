#!/usr/bin/env bash
# Lorehaven pricing simulator - macOS/Linux launcher.
#   Run:            bash run_tool.sh                  (Ctrl+C to stop)
#   Which Python?:  bash run_tool.sh --which-python   (prints the Python it would use, then exits)
#   Choose Python:  LOREHAVEN_PYTHON=/path/to/python bash run_tool.sh
# First run creates a local .venv (avoids "externally-managed-environment" errors) and installs Flask there.
#
# Why the search below: "bash run_tool.sh" starts a non-interactive shell that does not read ~/.zshrc, where
# Anaconda adds itself to PATH on macOS. "python3" then finds Apple's /usr/bin/python3 (3.9), which is too old.
# So we look for a suitable Python in the usual places instead of trusting PATH alone.
# Works with the bash 3.2 that ships with macOS.
set -e
cd "$(dirname "$0")"

CHECKED=""   # every candidate we looked at, one per line with its version, for the error message
FOUND=""     # the Python we will use

python_version() { "$1" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || echo "not runnable"; }

is_suitable() {   # Python 3.10-3.13 that can create a virtual environment
  [ -x "$1" ] && "$1" -c 'import sys, venv; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)' >/dev/null 2>&1
}

try() {   # try one candidate path; remember it in FOUND and stop searching if it is suitable
  [ -n "$1" ] && [ -x "$1" ] || return 1
  case "$CHECKED" in *"  $1 ("*) return 1 ;; esac          # already checked
  if is_suitable "$1"; then FOUND="$1"; return 0; fi
  CHECKED="$CHECKED
  $1 (Python $(python_version "$1"))"
  return 1
}

try_conda_root() {   # base Python of a conda install, then its environments
  try "$1/bin/python" && return 0
  for env_python in "$1"/envs/*/bin/python; do try "$env_python" && return 0; done
  return 1
}

find_python() {
  # 1. Explicit choice
  if [ -n "$LOREHAVEN_PYTHON" ]; then
    try "$LOREHAVEN_PYTHON" && return 0
    echo "LOREHAVEN_PYTHON=$LOREHAVEN_PYTHON is not a Python 3.10-3.13 ($(python_version "$LOREHAVEN_PYTHON"))." >&2
    return 1
  fi
  # 2. An active conda environment (after "conda activate ...")
  [ -n "$CONDA_PREFIX" ] && try "$CONDA_PREFIX/bin/python" && return 0
  # 3. Whatever is on PATH, newest first
  for name in python3.13 python3.12 python3.11 python3.10 python3 python; do
    candidate="$(command -v "$name" 2>/dev/null)" || continue
    # macOS: without Apple's developer tools, running /usr/bin/python3 only pops up an install dialog
    if [ "$candidate" = /usr/bin/python3 ] && [ "$(uname 2>/dev/null)" = Darwin ] && ! xcode-select -p >/dev/null 2>&1; then
      continue
    fi
    try "$candidate" && return 0
  done
  # 4. conda itself, if it is on PATH or was used before
  if command -v conda >/dev/null 2>&1; then
    try_conda_root "$(conda info --base 2>/dev/null)" && return 0
  fi
  [ -n "$CONDA_EXE" ] && try_conda_root "$(dirname "$(dirname "$CONDA_EXE")")" && return 0
  # 5. Usual install folders: Anaconda / Miniconda / Miniforge, then Homebrew, python.org and pyenv
  for root in "$HOME/anaconda3" "$HOME/miniconda3" "$HOME/miniforge3" "$HOME/mambaforge" \
              "$HOME/opt/anaconda3" "$HOME/opt/miniconda3" \
              /opt/anaconda3 /opt/miniconda3 /opt/miniforge3 /usr/local/anaconda3 /usr/local/miniconda3 \
              /opt/homebrew/anaconda3 /opt/homebrew/Caskroom/miniconda/base /opt/homebrew/Caskroom/miniforge/base \
              /usr/local/Caskroom/miniconda/base /usr/local/Caskroom/miniforge/base; do
    [ -d "$root" ] && try_conda_root "$root" && return 0
  done
  for minor in 13 12 11 10; do
    for candidate in "/opt/homebrew/bin/python3.$minor" "/usr/local/bin/python3.$minor" \
                     "/Library/Frameworks/Python.framework/Versions/3.$minor/bin/python3" \
                     "$HOME/.pyenv/shims/python3.$minor"; do
      try "$candidate" && return 0
    done
  done
  return 1
}

explain_and_exit() {
  echo "Could not find Python 3.10-3.13."
  [ -n "$CHECKED" ] && echo "Checked, but not suitable:$CHECKED"
  printf '%s\n' "" \
    'Fix it one of these ways, then run "bash run_tool.sh" again:' \
    '  1. Anaconda / Miniconda: open Terminal and run   conda activate base   (or your own environment).' \
    '  2. Tell the script which Python to use:' \
    '       LOREHAVEN_PYTHON=/path/to/python bash run_tool.sh' \
    '     To find the path for Anaconda:   conda activate base && which python' \
    '     (often ~/anaconda3/bin/python or ~/opt/anaconda3/bin/python)' \
    '  3. Install Python 3.12 from https://www.python.org/downloads/'
  exit 1
}

find_python || explain_and_exit
PY="$FOUND"

if [ "$1" = "--which-python" ]; then
  echo "$PY (Python $(python_version "$PY"))"; exit 0
fi

# Reuse .venv only if it works and already has Flask; otherwise (re)build it with the Python found above.
if ! .venv/bin/python -c 'import flask' >/dev/null 2>&1; then
  echo "Setting up .venv with Flask using $PY (Python $(python_version "$PY")). About 20 seconds..."
  rm -rf .venv
  "$PY" -m venv .venv
  if ! .venv/bin/python -m pip install --quiet -r requirements-tool.txt; then
    echo "Installing Flask failed (no internet?). Try again, or run:  $PY -m pip install flask==3.1.0 && $PY app/app.py"
    exit 1
  fi
fi
exec .venv/bin/python app/app.py
