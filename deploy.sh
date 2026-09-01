#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

printf '\n🏰 Updating Nottingham bot...\n'
git pull --ff-only
mkdir -p data

docker compose up -d --build --remove-orphans

docker image prune -f --filter dangling=true >/dev/null 2>&1 || true

printf '\n✅ Nottingham bot is running:\n'
docker compose ps
printf '\n📜 Logs: docker compose logs -f --tail=100\n\n'
