#!/usr/bin/env sh
set -eu
docker compose exec rabbitmq rabbitmqadmin publish exchange=orders.main routing_key=order \
  properties='{"delivery_mode":2,"headers":{"retry_count":0}}' \
  payload='{"id":"invalid-poison","request_id":"invalid","trace_id":"invalid","simulate_error":true}'
echo "Observe: docker compose logs -f consumer-worker"
