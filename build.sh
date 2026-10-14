#!/usr/bin/env bash
# Builds Meeting Intelligence into one folder of compiled programs: release/MeetingIntelligence/
# Needs: Python 3.11+ and Node.js 18+. Build on the operating system you want to run it on.
set -euo pipefail
cd "$(dirname "$0")"; ROOT="$PWD"
echo "[1/4] Python build environment"
python3 -m venv .build-venv
# shellcheck disable=SC1091
source .build-venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r backend/requirements-build.txt
# Optional PostgreSQL driver: only from a ready-made package (never compiled); skipped quietly when none exists for this Python.
pip install --quiet --only-binary :all: -r backend/requirements-postgres-optional.txt || echo "  (PostgreSQL driver not installed - fine for the local SQLite build)"
echo "[2/4] Web app"
( cd frontend && npm install --no-audit --no-fund && VITE_DEMO_MODE=true VITE_API_BASE=/api/v1 npm run build )
echo "[3/4] Compiling program"
rm -rf release build-tmp
( cd backend && WEB_SRC="$ROOT/frontend/dist" pyinstaller --noconfirm --clean --distpath "$ROOT/release" --workpath "$ROOT/build-tmp" meeting_intelligence.spec )
echo "[4/4] Finishing"
cp .env.example release/MeetingIntelligence/.env.example
cat > release/MeetingIntelligence/README.txt <<'T'
Meeting Intelligence - compiled build
Run MeetingIntelligence (MeetingIntelligence.exe on Windows). Your browser opens automatically.
Sign in as admin / Meeting$1, or use Sign up.
Data and logs are kept in the "docs" folder next to the program (created on first run).
Optional settings: copy .env.example to .env in this folder, edit, and restart.
To stop: press Ctrl+C in the terminal.
T
rm -rf build-tmp
echo "Done: $ROOT/release/MeetingIntelligence"
