#!/usr/bin/env sh
set -eu
docker compose --profile tools run --rm client dlq
echo "Waiting for TTL retries..."
sleep 15
docker compose exec rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged
