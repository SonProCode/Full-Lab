# RabbitMQ

[Tiếng Việt](vi/rabbitmq.md) | English

Topology: `orders.main` -> `orders.main.q`; failures publish to `orders.retry` -> `orders.retry.q`; queue TTL dead-letters them back to main. Exhausted messages publish to `orders.dlx` -> `orders.dlq`.

Messages and topology are durable, publishes use delivery mode 2, consumers use manual acknowledgements and configurable prefetch. Full mode declares quorum queues. Inspect with:

```bash
docker compose exec rabbitmq rabbitmqctl list_queues name type messages_ready messages_unacknowledged
```
