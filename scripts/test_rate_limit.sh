#!/usr/bin/env sh
set -eu
docker compose --profile tools run --rm client rate-limit --count 12
docker compose exec redis redis-cli --scan --pattern 'rate:*'
