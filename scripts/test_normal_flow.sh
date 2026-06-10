#!/usr/bin/env sh
set -eu
docker compose --profile tools run --rm client normal
sleep 2
curl -fsS "http://localhost:${ELASTICSEARCH_PORT:-9200}/orders/_search?pretty"
