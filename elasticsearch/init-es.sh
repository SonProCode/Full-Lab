#!/usr/bin/env sh
set -eu
ES="${ELASTICSEARCH_URL:-http://elasticsearch:9200}"
until curl -fsS "$ES/_cluster/health" >/dev/null; do echo "waiting for Elasticsearch"; sleep 2; done
curl -fsS -X PUT "$ES/_index_template/orders" -H 'Content-Type: application/json' --data-binary @/templates/orders-template.json
curl -fsS -X PUT "$ES/_index_template/logs-app" -H 'Content-Type: application/json' --data-binary @/templates/logs-template.json
curl -fsS -I "$ES/orders" >/dev/null || curl -fsS -X PUT "$ES/orders" -H 'Content-Type: application/json' -d '{}'
echo "Elasticsearch templates and orders index ready"
