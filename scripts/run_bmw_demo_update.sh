#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# This command cannot approve a requirement. A PM must first decide the exact
# current version and score in the web app. The imported record is labelled
# simulated in both source and record metadata.
uv run python -m scripts.prepare_bmw_demo simulate-update \
  --api-url http://127.0.0.1:18200
