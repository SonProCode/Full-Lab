#!/usr/bin/env sh
set -eu

COMPOSE="docker compose -f docker-compose.full.yml"
INTERVAL="${INTERVAL:-5}"

while true; do
  printf '\n===== %s =====\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "--- containers ---"
  $COMPOSE stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}'
  echo "--- rabbitmq queues ---"
  $COMPOSE exec -T rabbitmq1 rabbitmqctl list_queues name type messages_ready messages_unacknowledged message_bytes 2>/dev/null
  echo "--- redis ---"
  $COMPOSE exec -T redis redis-cli --no-raw INFO stats 2>/dev/null |
    sed -n '/instantaneous_ops_per_sec/p;/total_error_replies/p;/evicted_keys/p;/keyspace_hits/p;/keyspace_misses/p'
  $COMPOSE exec -T redis redis-cli --no-raw INFO memory 2>/dev/null |
    sed -n '/used_memory_human/p;/used_memory_peak_human/p;/mem_fragmentation_ratio/p'
  echo "--- elasticsearch ---"
  curl -fsS 'http://localhost:'"${ELASTICSEARCH_PORT:-9200}"'/_cat/thread_pool/write,search?v&h=node_name,name,active,queue,rejected,completed'
  curl -fsS 'http://localhost:'"${ELASTICSEARCH_PORT:-9200}"'/_cat/indices/orders?v&h=health,index,docs.count,store.size'
  curl -fsS 'http://localhost:'"${ELASTICSEARCH_PORT:-9200}"'/_nodes/stats/indices/indexing,search?filter_path=nodes.*.indices.indexing.*,nodes.*.indices.search.*'
  sleep "$INTERVAL"
done
