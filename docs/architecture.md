# Architecture

[Tiếng Việt](vi/architecture.md) | English

The API owns request validation, rate limiting, idempotency, and publishing. RabbitMQ decouples request latency from processing. The worker owns business processing, current Redis status, and the Elasticsearch business document. Logstash independently converts shared JSON log files into searchable `logs-app-*` events.

Delivery is at-least-once. A worker crash after indexing but before acknowledgement can redeliver a message. Production code should make the processing write idempotent, commonly by using the order ID as the document ID and guarding non-idempotent side effects.

Light mode prioritizes laptop resource use. Full mode prioritizes RabbitMQ availability exercises while retaining single-node Elasticsearch.
