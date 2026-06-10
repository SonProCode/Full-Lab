# Operations

[Tiếng Việt](vi/operations.md) | English

Start with `make up`, initialize mappings with `make bootstrap`, and inspect health with `curl localhost:8000/ready`. Use `make ps` and `make logs` during incidents.

Backlog is `messages_ready`; active work is `messages_unacknowledged`. A rising backlog can indicate insufficient consumers, downstream latency, or poison-message retry churn.
