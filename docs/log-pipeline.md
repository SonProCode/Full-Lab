# Log Pipeline

[Tiếng Việt](vi/log-pipeline.md) | English

API and worker loggers emit one JSON object per line to stdout and a shared volume. Logstash tails those files, parses JSON, normalizes `timestamp` into `@timestamp`, enforces `environment=lab`, and writes daily `logs-app-*` data streams using create operations.

Search by exact `request_id` or `trace_id`, which are keyword fields. Ingestion is asynchronous, so new logs may take several seconds to appear.
