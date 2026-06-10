#!/usr/bin/env sh
set -eu
docker compose --profile tools run --rm client idempotency
docker compose exec redis redis-cli --scan --pattern 'idempotency:*'
