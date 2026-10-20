#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "Starting stack with privacyIDEA overlay..."
docker compose -f docker-compose.yml -f docker-compose.privacyidea.yml up --build "$@"
