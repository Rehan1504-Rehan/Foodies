#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# FOODIES build script — used by Render / Railway / Heroku style deploys.
#   ./build.sh
# It installs dependencies, collects static assets, runs migrations and
# (optionally) loads the demo dataset.
# ---------------------------------------------------------------------------
set -o errexit   # exit on error

echo "▶ Installing Python dependencies…"
pip install --upgrade pip
pip install -r requirements.txt

echo "▶ Collecting static files (WhiteNoise)…"
python manage.py collectstatic --no-input

echo "▶ Applying database migrations…"
python manage.py migrate --no-input

# Optional: seed demo data by setting SEED_DATA=True in the environment.
if [ "${SEED_DATA:-False}" = "True" ]; then
  echo "▶ Seeding demo data…"
  python manage.py seed_data
fi

echo "▶ Running a quick deployment health check…"
python manage.py check --deploy || true

echo "✅ FOODIES build complete."
