#!/usr/bin/env sh
set -eu

ES="${ELASTICSEARCH_URL:-http://localhost:${ELASTICSEARCH_PORT:-9200}}"
REPOSITORY="${SNAPSHOT_REPOSITORY:-lab-backups}"
COMMAND="${1:-create}"
SNAPSHOT="${2:-snapshot-$(date -u +%Y%m%dT%H%M%SZ)}"

case "$COMMAND" in
  create)
    curl -fsS -X PUT "$ES/_snapshot/$REPOSITORY/$SNAPSHOT?wait_for_completion=true" \
      -H 'Content-Type: application/json' \
      -d '{"indices":"orders,logs-app-*","include_global_state":false}'
    printf '\nCreated snapshot: %s\n' "$SNAPSHOT"
    ;;
  list)
    curl -fsS "$ES/_cat/snapshots/$REPOSITORY?v&s=end_epoch:desc"
    ;;
  status)
    curl -fsS "$ES/_snapshot/$REPOSITORY/$SNAPSHOT/_status?pretty"
    ;;
  restore-orders)
    curl -fsS -X POST "$ES/_snapshot/$REPOSITORY/$SNAPSHOT/_restore?wait_for_completion=true" \
      -H 'Content-Type: application/json' \
      -d '{"indices":"orders","include_global_state":false,"rename_pattern":"orders","rename_replacement":"orders-restored"}'
    printf '\nRestored orders as index: orders-restored\n'
    ;;
  *)
    echo "Usage: $0 {create|list|status|restore-orders} [snapshot-name]" >&2
    exit 2
    ;;
esac
