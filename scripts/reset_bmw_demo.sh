#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

case "${1:-predecision}" in
  predecision)
    snapshot="database/snapshots/app-20261011T033717381575Z-bmw-predecision.db"
    expected="4d2fb748119e8be91c988f451e3aeec59de94be48e5b3e1cc56fa5fa0015de52"
    expected_records=4365
    ;;
  after-update)
    snapshot="database/snapshots/app-20261011T033741205747Z-bmw-after-update.db"
    expected="9804739c0e59fbec1f32649b95901f3569179df87932e1ba14ca4f74c3c308d3"
    expected_records=4366
    ;;
  *)
    echo "Usage: $0 [predecision|after-update]" >&2
    exit 2
    ;;
esac

if [[ ! -f "$snapshot" || ! -d database/local/originals ]]; then
  echo "Local snapshot or archived originals are missing; see notes/bmw-demo-claim-ledger.md" >&2
  exit 1
fi
actual="$(shasum -a 256 "$snapshot" | cut -d ' ' -f 1)"
if [[ "$actual" != "$expected" ]]; then
  echo "Snapshot checksum mismatch: $snapshot" >&2
  exit 1
fi

export COMPOSE_PROJECT_NAME=bmw-demo-core API_PORT=18200 MCP_PORT=18201 WEB_PORT=13203
docker compose --profile web down
cp "$snapshot" database/local/app.db
rm -f database/local/app.db-shm database/local/app.db-wal
docker compose --profile web up -d --build
node web/scripts/demo-preflight.mjs http://127.0.0.1:13203 | tee /tmp/bmw-demo-preflight.txt
if ! rg -q "PASS · $expected_records evidence records" /tmp/bmw-demo-preflight.txt; then
  echo "Demo record count differs from the frozen $expected_records" >&2
  exit 1
fi
