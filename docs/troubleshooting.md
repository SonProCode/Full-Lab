# Troubleshooting

[Tiếng Việt](vi/troubleshooting.md) | English

- API unavailable: inspect `docker compose ps` and `docker compose logs api-server`.
- `/ready` is 503: its JSON detail identifies RabbitMQ, Redis, or Elasticsearch.
- Queue inequivalent-argument error: classic and quorum queues cannot share an existing name; clean volumes when changing mode.
- Logs missing: inspect `docker compose logs log-parser`, then check `curl localhost:9200/_cat/indices?v`.
- Elasticsearch exits: allocate more Docker memory and set host `vm.max_map_count=262144`.
- Full RabbitMQ cluster incomplete: run `docker compose -f docker-compose.full.yml exec rabbitmq1 rabbitmqctl cluster_status`.
