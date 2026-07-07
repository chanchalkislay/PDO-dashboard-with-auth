#!/bin/bash
# ============================================================
# Pune DO Dashboard — Local Launcher (macOS)
# Use this to test the app on your PC BEFORE committing/pushing
# to GitHub. Runs a local integrity check first, then launches
# the dashboard in your browser.
# ============================================================

cd "$(dirname "$0")"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/app"
DB_PATH="$APP_DIR/pune_do.db"

echo "================================================"
echo " Pune DO Dashboard — LOCAL TEST RUN"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================"

if [ ! -f "$DB_PATH" ]; then
    echo "ERROR: Database not found at $DB_PATH"
    read -p "Press Enter to close..."
    exit 1
fi

if command -v python3 &>/dev/null; then
    PY=python3
else
    echo "ERROR: python3 not found. Install Python 3 first."
    read -p "Press Enter to close..."
    exit 1
fi

echo "Checking requirements..."
$PY -m pip install -r "$APP_DIR/requirements.txt" -q --break-system-packages 2>/dev/null || \
$PY -m pip install -r "$APP_DIR/requirements.txt" -q

echo "Running DB/app integrity check (verify.py)..."
cd "$APP_DIR"
$PY verify.py
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Integrity check failed. Fix the reported issue(s) before"
    echo "committing to GitHub. Aborting launch."
    read -p "Press Enter to close..."
    exit 1
fi

echo ""
echo "All checks passed."
echo "Launching dashboard at http://localhost:8501"
echo "Close this window (or press Ctrl+C) to stop the app."
echo ""

export PUNE_DO_DB="$DB_PATH"
$PY -m streamlit run "$APP_DIR/app.py" --server.port 8501
