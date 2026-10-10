#!/bin/sh
# Serve one snapshot read-only: INSPECT_DB if set, else the newest golden snapshot, else the newest snapshot.
# Never opens the live WAL database.
set -eu
file="${INSPECT_DB:-}"
if [ -z "$file" ]; then
    file="$(ls -t /snapshots/*-golden.db 2>/dev/null | head -n 1 || true)"
fi
if [ -z "$file" ]; then
    file="$(ls -t /snapshots/app-*.db 2>/dev/null | head -n 1 || true)"
fi
if [ -z "$file" ]; then
    echo "No snapshot in /snapshots. Run: docker compose exec api python -m database.cli snapshot" >&2
    exit 1
fi
echo "Serving $file"
cp "$file" /tmp/bmw.db
exec datasette serve -i /tmp/bmw.db --metadata /inspect/metadata.json -h 0.0.0.0 -p 8001 \
    --setting sql_time_limit_ms 5000 --setting max_returned_rows 2000
