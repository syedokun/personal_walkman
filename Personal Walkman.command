#!/bin/bash
# Double-click launcher for macOS.
cd "$(dirname "$0")" || exit 1

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "Python 3 was not found. Install it from https://www.python.org/downloads/ then try again."
  read -r -p "Press Enter to close…"
  exit 1
fi

"$PYTHON" run.py
status=$?
if [ "$status" -ne 0 ]; then
  echo
  read -r -p "Press Enter to close…"
fi
exit "$status"
