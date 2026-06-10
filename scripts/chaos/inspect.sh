#!/usr/bin/env sh
set -eu
docker compose exec rabbitmq rabbitmqctl list_queues name type messages_ready messages_unacknowledged
docker compose exec redis redis-cli --scan --pattern '*'
curl -fsS "http://localhost:${ELASTICSEARCH_PORT:-9200}/orders/_search?pretty"
curl -fsS "http://localhost:${ELASTICSEARCH_PORT:-9200}/logs-app-*/_search?pretty&size=5"
