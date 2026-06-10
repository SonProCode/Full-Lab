#!/usr/bin/env sh
set -eu
docker compose stop consumer-worker
docker compose --profile tools run --rm client backlog --count 30
docker compose exec rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged
echo "Recovery: docker compose start consumer-worker"
