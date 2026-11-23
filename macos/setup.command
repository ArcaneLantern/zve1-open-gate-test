#!/bin/bash
# Creates macos/.venv with the packages the launchers need (pyusb, pycryptodomex, and libusb-package, which brings
# libusb itself, so no Homebrew is needed). Needs Python 3.9 or later.
cd "$(dirname "$0")" || exit 1
close() { echo; read -r -p "Press Return to close. "; exit "$1"; }
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
  echo "Python 3.9 or later not found. Install it from python.org, or the Xcode Command Line Tools"
  echo "(run: xcode-select --install), then run this again."
  close 1
fi
python3 -m venv .venv || close 1
.venv/bin/python -m pip install --upgrade pip || close 1
.venv/bin/python -m pip install -r requirements.txt || close 1
echo
echo "Done. No driver is needed on macOS: the launchers ask for your password instead, see README.md."
close 0
