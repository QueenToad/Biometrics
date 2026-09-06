#!/usr/bin/env bash
# Pull the last few days and push them into Notion.
# Overlapping the window means a day missed while the laptop was asleep gets
# filled in on the next run, and re-syncing a day just corrects it in place.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p logs

echo "--- $(date '+%Y-%m-%d %H:%M:%S') ---"
exec "$ROOT/.venv/bin/python" -m src.main --days "${SYNC_DAYS:-3}" --sync
