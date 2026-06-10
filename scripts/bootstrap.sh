#!/usr/bin/env sh
set -eu
docker compose --profile tools run --rm es-init
curl -fsS "http://localhost:${API_PORT:-8000}/ready"
echo
