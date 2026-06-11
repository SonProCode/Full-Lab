COMPOSE=docker compose
FULL=$(COMPOSE) -f docker-compose.full.yml

.PHONY: up up-full down clean ps logs bootstrap perf-full-http perf-full-search perf-full-rabbit perf-full-observe es-snapshot es-snapshot-list test-normal test-idempotency test-rate-limit test-dlq test-log-trace \
 chaos-stop-consumer chaos-start-consumer chaos-stop-rabbit-node chaos-start-rabbit-node chaos-stop-redis chaos-start-redis chaos-stop-elasticsearch chaos-start-elasticsearch

up:
	$(COMPOSE) up -d --build
up-full:
	$(FULL) up -d --build
down:
	$(COMPOSE) down --remove-orphans
	$(FULL) down --remove-orphans
clean:
	$(COMPOSE) down -v --remove-orphans
	$(FULL) down -v --remove-orphans
ps:
	$(COMPOSE) ps
logs:
	$(COMPOSE) logs -f --tail=100
bootstrap:
	$(COMPOSE) --profile tools run --rm es-init
perf-full-http:
	$(FULL) --profile tools run --rm --build --entrypoint python client perf_test.py http --count 2000 --concurrency 50
perf-full-search:
	$(FULL) --profile tools run --rm --build --entrypoint python client perf_test.py search --count 2000 --concurrency 50
perf-full-rabbit:
	$(FULL) --profile tools run --rm --build --entrypoint python client perf_test.py rabbit-persistence --count 5000 --payload-bytes 1024
perf-full-observe:
	./scripts/perf/observe_full.sh
es-snapshot:
	./scripts/elasticsearch/snapshot.sh create
es-snapshot-list:
	./scripts/elasticsearch/snapshot.sh list
test-normal:
	./scripts/test_normal_flow.sh
test-idempotency:
	./scripts/test_idempotency.sh
test-rate-limit:
	./scripts/test_rate_limit.sh
test-dlq:
	./scripts/test_retry_dlq.sh
test-log-trace:
	./scripts/test_log_trace.sh
chaos-stop-consumer:
	$(COMPOSE) stop consumer-worker
chaos-start-consumer:
	$(COMPOSE) start consumer-worker
chaos-stop-rabbit-node:
	$(FULL) stop rabbitmq2
chaos-start-rabbit-node:
	$(FULL) start rabbitmq2
chaos-stop-redis:
	$(COMPOSE) stop redis
chaos-start-redis:
	$(COMPOSE) start redis
chaos-stop-elasticsearch:
	$(COMPOSE) stop elasticsearch
chaos-start-elasticsearch:
	$(COMPOSE) start elasticsearch
