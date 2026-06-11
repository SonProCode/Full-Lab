#!/usr/bin/env sh
set -eu
ES="${ELASTICSEARCH_URL:-http://elasticsearch:9200}"
until curl -fsS "$ES/_cluster/health" >/dev/null; do echo "waiting for Elasticsearch"; sleep 2; done

put() {
  description="$1"
  url="$2"
  data="$3"
  curl -fsS -o /dev/null -X PUT "$url" -H 'Content-Type: application/json' --data-binary "$data"
  echo "$description"
}

put "orders template ready" "$ES/_index_template/orders" @/templates/orders-template.json
put "logs-app template ready" "$ES/_index_template/logs-app" @/templates/logs-template.json

# A missing orders index is expected on the first run, so suppress that HEAD 404.
if curl -fs -I "$ES/orders" >/dev/null; then
  echo "orders index already exists"
else
  put "orders index created" "$ES/orders" '{}'
fi

put "orders slow logs configured" "$ES/orders/_settings" '{
  "index.search.slowlog.threshold.query.warn":"100ms",
  "index.search.slowlog.threshold.query.info":"50ms",
  "index.search.slowlog.threshold.fetch.warn":"100ms",
  "index.indexing.slowlog.threshold.index.warn":"100ms",
  "index.indexing.slowlog.threshold.index.info":"50ms",
  "index.indexing.slowlog.include.user":true
}'
put "snapshot repository ready" "$ES/_snapshot/lab-backups" '{
  "type":"fs",
  "settings":{"location":"/mnt/snapshots","compress":true}
}'
echo "Elasticsearch templates and orders index ready"
